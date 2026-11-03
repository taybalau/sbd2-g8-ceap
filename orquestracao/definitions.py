"""
Orquestração da E3 (Dagster + dagster-dbt).

Grafo:
    bronze_ceap_lancamento [particionado por ano, retry 3x exponencial]
        └─> bronze_camara_deputado_historico [retry 3x; precisa dos ids da CEAP]
              └─> modelos dbt (staging → silver → gold) com os testes do dbt como asset checks

Garantias que este arquivo implementa (e que orquestracao/demo_falhas.py exercita):
  * Retry: falha transitória de I/O é absorvida (RetryPolicy com backoff exponencial).
  * Falha permanente não propaga lixo: se a Bronze falha, o dbt não roda e a Gold
    continua com o último estado válido. Se um teste de dados do dbt falha, o `dbt build`
    pula os modelos que dependem do modelo reprovado.
  * Backfill: a Bronze é particionada por ano; reprocessar 2024 substitui só a partição
    2024 (replaceWhere no Delta), sem tocar nos outros anos.
"""

import os
import sys
from pathlib import Path

from dagster import (
    AssetExecutionContext,
    AssetSelection,
    DagsterRunStatus,
    RunRequest,
    AssetKey,
    Backoff,
    Definitions,
    MaterializeResult,
    MetadataValue,
    RetryPolicy,
    StaticPartitionsDefinition,
    asset,
    define_asset_job,
    run_status_sensor,
    schedule,
)
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "ingestao"))
os.environ.setdefault("LAKEHOUSE_PATH", str(RAIZ / "lakehouse"))

import bronze  # noqa: E402
import bronze_historico  # noqa: E402

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
            return AssetKey(["bronze", dbt_resource_props["name"]])
        return super().get_asset_key(dbt_resource_props)

    def get_group_name(self, dbt_resource_props):
        caminho = dbt_resource_props.get("fqn", [])
        if "gestao" in caminho:
            return "gold"
        if dbt_resource_props["resource_type"] == "seed":
            return "regras"
        return "silver"


@dbt_assets(manifest=dbt_project.manifest_path, dagster_dbt_translator=Tradutor())
def modelos_dbt(context: AssetExecutionContext, dbt: DbtCliResource):
    # `build` = run + test na ordem do grafo; teste reprovado pula os modelos a jusante
    yield from dbt.cli(["build"], context=context).stream()


# Dois jobs porque a Bronze da CEAP é particionada por ano e o restante não é.
ingestao_ceap = define_asset_job(
    "ingestao_ceap", selection=AssetSelection.keys(AssetKey(["bronze", "ceap_lancamento"])),
    partitions_def=ANOS,
)
transformacao = define_asset_job(
    "transformacao",
    selection=AssetSelection.all() - AssetSelection.keys(AssetKey(["bronze", "ceap_lancamento"])),
)


@schedule(job=ingestao_ceap, cron_schedule="0 6 * * *", execution_timezone="America/Sao_Paulo")
def diario_ano_corrente(context):
    """Todo dia reingere só o ano corrente (anos fechados mudam pouco; backfill sob demanda)."""
    ano = str(context.scheduled_execution_time.year)
    if ano in ANOS.get_partition_keys():
        yield RunRequest(run_key=f"{ano}-{context.scheduled_execution_time:%Y%m%d}", partition_key=ano)


@run_status_sensor(run_status=DagsterRunStatus.SUCCESS, monitored_jobs=[ingestao_ceap],
                   request_job=transformacao)
def transforma_apos_ingestao(context):
    """Só transforma depois de uma ingestão BEM-SUCEDIDA. Ingestão que falhou não dispara nada."""
    return RunRequest(run_key=context.dagster_run.run_id)


defs = Definitions(
    assets=[bronze_ceap_lancamento, bronze_camara_deputado_historico, modelos_dbt],
    jobs=[ingestao_ceap, transformacao],
    schedules=[diario_ano_corrente],
    sensors=[transforma_apos_ingestao],
    resources={"dbt": DbtCliResource(
        project_dir=dbt_project,
        # usa o dbt do mesmo ambiente Python do Dagster (venv local ou imagem Docker)
        dbt_executable=str(Path(sys.executable).with_name("dbt")),
    )},
)
