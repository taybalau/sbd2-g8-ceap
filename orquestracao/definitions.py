"""
Orquestração da E3 (Dagster + dagster-dbt).

Grafo:
    bronze_ceap_lancamento [particionado por ano, retry 3x exponencial]
        └─> bronze_camara_deputado_historico [retry 3x; precisa dos ids da CEAP]
              └─> modelos dbt (staging → silver → gold → semantico) com os testes do dbt como asset checks
                    └─> alerta/desvio_parlamentar_postgres [ETL reverso da E4; retry 3x exponencial]

Garantias que este arquivo implementa (e que orquestracao/demo_falhas.py exercita):
  * Retry: falha transitória de I/O é absorvida (RetryPolicy com backoff exponencial).
  * Falha permanente não propaga lixo: se a Bronze falha, o dbt não roda e a Gold
    continua com o último estado válido. Se um teste de dados do dbt falha, o `dbt build`
    pula os modelos que dependem do modelo reprovado.
  * Backfill: a Bronze é particionada por ano; reprocessar 2024 substitui só a partição
    2024 (replaceWhere no Delta), sem tocar nos outros anos.
  * ETL reverso (E4): depois do dbt, os parlamentares em alerta da camada semântica são
    empurrados para a fila de auditoria do PostgreSQL. Destino fora do ar: 3 tentativas com
    espera crescente; se ainda falhar, o run fica vermelho, a Gold e o painel não mudam e a
    próxima execução publica (a carga é idempotente).
"""

import os
import sys
from pathlib import Path

from dagster import (
    AssetCheckResult,
    AssetExecutionContext,
    AssetSelection,
    DagsterRunStatus,
    DefaultScheduleStatus,
    DefaultSensorStatus,
    RunRequest,
    AssetKey,
    Backoff,
    Definitions,
    MaterializeResult,
    MetadataValue,
    RetryPolicy,
    StaticPartitionsDefinition,
    asset,
    asset_check,
    define_asset_job,
    run_status_sensor,
    schedule,
)
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets, get_asset_key_for_model

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "ingestao"))
sys.path.insert(0, str(RAIZ / "etl_reverso"))
os.environ.setdefault("LAKEHOUSE_PATH", str(RAIZ / "lakehouse"))

import bronze  # noqa: E402
import bronze_historico  # noqa: E402
import publicar_alertas  # noqa: E402

ANOS = StaticPartitionsDefinition(os.getenv("ANOS", "2023,2024,2025,2026").split(","))

RETRY_FONTE = RetryPolicy(max_retries=3, delay=2, backoff=Backoff.EXPONENTIAL)


@asset(
    key=AssetKey(["bronze", "ceap_lancamento"]),
    partitions_def=ANOS,
    retry_policy=RETRY_FONTE,
    group_name="bronze",
    description="CSV anual da CEAP → Delta (partição ano_arquivo). Idempotente por partição.",
)
def bronze_ceap_lancamento(context: AssetExecutionContext) -> MaterializeResult:
    ano = int(context.partition_key)
    context.log.info(f"Tentativa {context.retry_number + 1} para Ano-{ano}.csv")
    r = bronze.ingerir_ano(ano)
    return MaterializeResult(metadata={
        "linhas": r["linhas"],
        "versao_delta": r["versao_delta"],
        "arquivo": r["arquivo"],
        "tentativa": context.retry_number + 1,
    })


@asset(
    key=AssetKey(["bronze", "camara_deputado_historico"]),
    deps=[AssetKey(["bronze", "ceap_lancamento"])],
    retry_policy=RetryPolicy(max_retries=3, delay=5, backoff=Backoff.EXPONENTIAL),
    group_name="bronze",
    description="Histórico oficial de eventos dos deputados (fonte do SCD2). Snapshot completo.",
)
def bronze_camara_deputado_historico(context: AssetExecutionContext) -> MaterializeResult:
    context.log.info(f"Tentativa {context.retry_number + 1} na API da Câmara")
    r = bronze_historico.ingerir_historico()
    return MaterializeResult(metadata={k: MetadataValue.text(str(v)) for k, v in r.items()})


# ---------------------------------------------------------------- dbt
DBT_DIR = RAIZ / "dbt_ceap"
dbt_project = DbtProject(project_dir=DBT_DIR, profiles_dir=DBT_DIR)
dbt_project.prepare_if_dev()


class Tradutor(DagsterDbtTranslator):
    """Liga as sources do dbt às assets Bronze acima (mesma chave), formando um só grafo."""

    def get_asset_key(self, dbt_resource_props):
        if dbt_resource_props["resource_type"] == "source":
            # auditoria.resultado_build é gravada pelo próprio dbt (on-run-end), não pela ingestão
            if dbt_resource_props["source_name"] == "auditoria":
                return AssetKey(["auditoria", dbt_resource_props["name"]])
            return AssetKey(["bronze", dbt_resource_props["name"]])
        return super().get_asset_key(dbt_resource_props)

    def get_group_name(self, dbt_resource_props):
        caminho = dbt_resource_props.get("fqn", [])
        if "gestao" in caminho:
            return "gold"
        if "semantic" in caminho:
            return "semantico"
        if dbt_resource_props["resource_type"] == "seed":
            return "regras"
        return "silver"


@dbt_assets(manifest=dbt_project.manifest_path, dagster_dbt_translator=Tradutor())
def modelos_dbt(context: AssetExecutionContext, dbt: DbtCliResource):
    # `build` = run + test na ordem do grafo; teste reprovado pula os modelos a jusante
    yield from dbt.cli(["build"], context=context).stream()


# ---------------------------------------------------------------- ETL reverso (E4)
RETRY_DESTINO = RetryPolicy(max_retries=3, delay=2, backoff=Backoff.EXPONENTIAL)
ALERTA = AssetKey(["alerta", "desvio_parlamentar_postgres"])


@asset(
    key=ALERTA,
    deps=[get_asset_key_for_model([modelos_dbt], "met_parlamentar"),
          get_asset_key_for_model([modelos_dbt], "met_contexto")],
    retry_policy=RETRY_DESTINO,
    group_name="etl_reverso",
    description="Push dos parlamentares em alerta (semantico.met_parlamentar.em_alerta) para a fila de "
                "auditoria alerta.desvio_parlamentar no PostgreSQL. Idempotente; uma transação só.",
)
def alerta_desvio_postgres(context: AssetExecutionContext) -> MaterializeResult:
    context.log.info(f"Tentativa {context.retry_number + 1} de publicar no PostgreSQL")
    r = publicar_alertas.publicar(origem=f"dagster run {context.run_id[:8]}")
    return MaterializeResult(metadata={
        "referencia_dados": r["referencia_dados"], "linhas_recebidas": r["linhas_recebidas"],
        "linhas_novas": r["linhas_novas"], "tentativa": context.retry_number + 1})


@asset_check(asset=ALERTA, description="O retrato publicado no PostgreSQL tem os mesmos parlamentares "
                                        "em alerta da camada semântica (mesmo número nas duas telas).")
def alerta_igual_a_camada_semantica() -> AssetCheckResult:
    esperados = [a[1] for a in publicar_alertas.ler_alertas()]
    publicados = publicar_alertas.ids_publicados()
    return AssetCheckResult(passed=esperados == publicados, metadata={
        "em_alerta_na_camada": len(esperados), "no_postgres": len(publicados),
        "so_na_camada": str(sorted(set(esperados) - set(publicados))),
        "so_no_postgres": str(sorted(set(publicados) - set(esperados)))})


# Dois jobs principais porque a Bronze da CEAP é particionada por ano e o restante não é.
ingestao_ceap = define_asset_job(
    "ingestao_ceap", selection=AssetSelection.keys(AssetKey(["bronze", "ceap_lancamento"])),
    partitions_def=ANOS,
)
transformacao = define_asset_job(
    "transformacao",
    selection=AssetSelection.all() - AssetSelection.keys(AssetKey(["bronze", "ceap_lancamento"])),
)
# Só o ETL reverso: republicar à mão depois de o destino voltar, sem refazer o dbt.
etl_reverso = define_asset_job("etl_reverso", selection=AssetSelection.keys(ALERTA))


# Ligados por padrão: sem isso o `dagster dev` sobe com agenda e sensor desligados e o grafo
# não roda sozinho.
@schedule(job=ingestao_ceap, cron_schedule="0 6 * * *", execution_timezone="America/Sao_Paulo",
          default_status=DefaultScheduleStatus.RUNNING)
def diario_ano_corrente(context):
    """Todo dia reingere só o ano corrente (anos fechados mudam pouco; backfill sob demanda)."""
    ano = str(context.scheduled_execution_time.year)
    if ano in ANOS.get_partition_keys():
        yield RunRequest(run_key=f"{ano}-{context.scheduled_execution_time:%Y%m%d}", partition_key=ano)


@run_status_sensor(run_status=DagsterRunStatus.SUCCESS, monitored_jobs=[ingestao_ceap],
                   request_job=transformacao, default_status=DefaultSensorStatus.RUNNING)
def transforma_apos_ingestao(context):
    """Só transforma depois de uma ingestão BEM-SUCEDIDA. Ingestão que falhou não dispara nada."""
    return RunRequest(run_key=context.dagster_run.run_id)


defs = Definitions(
    assets=[bronze_ceap_lancamento, bronze_camara_deputado_historico, modelos_dbt, alerta_desvio_postgres],
    asset_checks=[alerta_igual_a_camada_semantica],
    jobs=[ingestao_ceap, transformacao, etl_reverso],
    schedules=[diario_ano_corrente],
    sensors=[transforma_apos_ingestao],
    resources={"dbt": DbtCliResource(
        project_dir=dbt_project,
        # usa o dbt do mesmo ambiente Python do Dagster (venv local ou imagem Docker)
        dbt_executable=str(Path(sys.executable).with_name("dbt")),
    )},
)
