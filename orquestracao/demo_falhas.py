"""
Exercita a orquestração de propósito: retry, dependência derrubada, teste de dados
reprovado e backfill. Cada cenário roda num subprocesso com o ambiente adulterado e
grava as execuções no DAGSTER_HOME (aparecem depois na UI do Dagster).

Uso:
    python orquestracao/demo_falhas.py            # roda todos os cenários
    python orquestracao/demo_falhas.py retry      # roda um cenário

Saída: um resumo por cenário + orquestracao/evidencias/<cenario>.json
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
EVID = RAIZ / "orquestracao" / "evidencias"
LAKE = Path(os.getenv("LAKEHOUSE_PATH", RAIZ / "lakehouse"))
os.environ.setdefault("DAGSTER_HOME", str(RAIZ / "orquestracao" / ".dagster_home"))
Path(os.environ["DAGSTER_HOME"]).mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------- execução (subprocesso)
def _executar(job: str, particao: str | None) -> dict:
    sys.path.insert(0, str(RAIZ / "orquestracao"))
    from dagster import DagsterEventType, DagsterInstance
    from definitions import defs

    instancia = DagsterInstance.get()
    res = defs.get_job_def(job).execute_in_process(
        instance=instancia, partition_key=particao, raise_on_error=False)
    eventos = Counter()
    falhas, iniciados, erros_tentativas = [], set(), []
    for ev in res.all_events:
        eventos[ev.event_type_value] += 1
        if ev.event_type == DagsterEventType.STEP_START:
            iniciados.add(ev.step_key)
        if ev.event_type == DagsterEventType.STEP_UP_FOR_RETRY:
            err = ev.event_specific_data.error
            causa = (err.cause or err) if err else None
            msg = (causa.message or "").strip().splitlines() if causa else []
            erros_tentativas.append(msg[-1][:200] if msg else "?")
        if ev.event_type == DagsterEventType.STEP_FAILURE:
            falhas.append({"passo": ev.step_key,
                           "erro": (ev.step_failure_data.error.message or "").strip()[:300]})
    todos = {n.name for n in res.job_def.graph.nodes}
    asset_checks = [e for e in res.all_events if e.event_type_value == "ASSET_CHECK_EVALUATION"]
    checks_reprovados = [e.event_specific_data.asset_check_key.name for e in asset_checks
                         if not e.event_specific_data.passed]
    materializados = sorted({"/".join(e.asset_key.path) for e in res.all_events
                             if e.event_type == DagsterEventType.ASSET_MATERIALIZATION})
    # Testes singulares que tocam vários modelos não viram asset check no dagster-dbt;
    # o resultado autoritativo do dbt está no run_results.json da pasta deste run.
    dbt_resumo = {}
    for rr in (RAIZ / "dbt_ceap" / "target").glob(f"modelos_dbt-{res.run_id[:7]}-*/run_results.json"):
        nos = json.loads(rr.read_text())["results"]
        nome = lambda x: x["unique_id"].split(".")[2] if x["unique_id"].startswith("test.") \
            and len(x["unique_id"].split(".")) > 3 else x["unique_id"].split(".")[-1]
        dbt_resumo = {
            "testes_reprovados": sorted(nome(x) for x in nos if x["status"] in ("fail", "error")),
            "testes_com_aviso": sorted(nome(x) for x in nos if x["status"] == "warn"),
            "modelos_pulados": sorted(x["unique_id"].split(".")[-1] for x in nos
                                      if x["status"] == "skipped" and x["unique_id"].startswith("model.")),
            "testes_aprovados": sum(1 for x in nos if x["status"] == "pass"),
        }
    return {"job": job, "particao": particao, "sucesso": res.success, "run_id": res.run_id,
            "dbt": dbt_resumo,
            "tentativas_extras": eventos.get("STEP_UP_FOR_RETRY", 0),
            "erros_das_tentativas": erros_tentativas,
            "passos_com_falha": falhas,
            "passos_iniciados": sorted(iniciados),
            "passos_nao_executados": sorted(todos - iniciados),
            "assets_materializados": materializados,
            "checks_dbt_reprovados": checks_reprovados}


def _impressao_digital(lake: Path) -> dict:
    """Estado da Gold e da Bronze: se não mudou, a falha não propagou nada."""
    import duckdb
    from deltalake import DeltaTable
    out = {}
    try:
        con = duckdb.connect(str(lake / "ceap.duckdb"), read_only=True)
        out["gold_linhas"], out["gold_hash"] = con.execute("""
            select count(*), md5(string_agg(id_deputado || ':' || round(desvio_acumulado, 2), ',' order by id_deputado))
            from gold.mart_desvio_parlamentar""").fetchone()
        out["silver_fato_linhas"] = con.execute("select count(*) from silver.fct_lancamento_ceap").fetchone()[0]
        con.close()
    except Exception as e:  # noqa: BLE001
        out["gold_erro"] = str(e)[:200]
    for nome in ("ceap_lancamento", "camara_deputado_historico"):
        p = lake / "bronze" / nome
        if (p / "_delta_log").exists():
            out[f"bronze_{nome}_versao"] = DeltaTable(str(p)).version()
    return out


def _sub(job: str, particao: str | None = None, **env) -> dict:
    ambiente = {**os.environ, **{k: str(v) for k, v in env.items()}}
    cmd = [sys.executable, __file__, "--executar", job] + ([particao] if particao else [])
    p = subprocess.run(cmd, env=ambiente, capture_output=True, text=True, cwd=RAIZ)
    linha = [l for l in p.stdout.splitlines() if l.startswith("@@RESULTADO@@")]
    if not linha:
        raise RuntimeError(f"subprocesso sem resultado:\n{p.stdout[-2000:]}\n{p.stderr[-3000:]}")
    return json.loads(linha[-1].removeprefix("@@RESULTADO@@"))


def _limpa_contadores(lake: Path = LAKE):
    shutil.rmtree(lake / "_controle", ignore_errors=True)


# ----------------------------------------------------------------- cenários
def cenario_base():
    """Execução normal de ponta a ponta (estado de referência)."""
    r = [_sub("ingestao_ceap", a) for a in ("2023", "2024", "2025", "2026")]
    r.append(_sub("transformacao"))
    return {"execucoes": r, "estado": _impressao_digital(LAKE)}


def cenario_retry():
    """Falha transitória: as 2 primeiras leituras do CSV falham; o retry tem de absorver."""
    _limpa_contadores()
    antes = _impressao_digital(LAKE)
    r = _sub("ingestao_ceap", "2025", CEAP_FALHA_TRANSITORIA=2)
    _limpa_contadores()
    return {"execucao": r, "antes": antes, "depois": _impressao_digital(LAKE)}


def cenario_fonte_fora():
    """Dependência derrubada: o diretório da Câmara some. Deve falhar após 3 retries,
    não gravar partição vazia e não disparar a transformação (o sensor só reage a SUCESSO)."""
    vazio = tempfile.mkdtemp(prefix="fonte_vazia_")
    antes = _impressao_digital(LAKE)
    r = _sub("ingestao_ceap", "2026", CEAP_FONTE_DIR=vazio)
    return {"execucao": r, "antes": antes, "depois": _impressao_digital(LAKE),
            "transformacao_disparada": False,
            "motivo": "sensor transforma_apos_ingestao só observa DagsterRunStatus.SUCCESS"}


def cenario_api_fora():
    """Dependência derrubada no meio do grafo: a API de histórico (fonte do SCD2) fica
    inacessível. O passo falha após retries e TODOS os modelos dbt são pulados no mesmo run."""
    antes = _impressao_digital(LAKE)
    r = _sub("transformacao", CEAP_API_BASE="http://127.0.0.1:9/api/v2")
    return {"execucao": r, "antes": antes, "depois": _impressao_digital(LAKE)}


def cenario_dado_sujo():
    """Teste de dados reprovado: injeta um combustível com valor negativo numa CÓPIA do
    lakehouse. O dbt build tem de reprovar o teste e não reconstruir a Gold."""
    tmp = Path(tempfile.mkdtemp(prefix="lake_sujo_"))
    shutil.copytree(LAKE, tmp / "lakehouse", ignore=shutil.ignore_patterns("_cache"))
    lake = tmp / "lakehouse"
    fonte = tmp / "fonte"
    fonte.mkdir()
    src = (RAIZ / "base-dados" / "Ano-2026.csv").read_text(encoding="utf-8-sig").splitlines()
    cab, linhas = src[0], src[1:]
    idx = next(i for i, l in enumerate(linhas) if '"COMBUSTÍVEIS E LUBRIFICANTES."' in l)
    campos = linhas[idx].split('";"')
    campos[19] = "-999.99"                       # vlrLiquido
    linhas[idx] = '";"'.join(campos)
    (fonte / "Ano-2026.csv").write_text("\n".join([cab] + linhas), encoding="utf-8")
    antes = _impressao_digital(lake)
    r1 = _sub("ingestao_ceap", "2026", CEAP_FONTE_DIR=fonte, LAKEHOUSE_PATH=lake,
              CEAP_USAR_CACHE="1")
    shutil.copytree(LAKE / "_cache", lake / "_cache", dirs_exist_ok=True)
    r2 = _sub("transformacao", LAKEHOUSE_PATH=lake, CEAP_USAR_CACHE="1")
    depois = _impressao_digital(lake)
    shutil.rmtree(tmp, ignore_errors=True)
    return {"ingestao": r1, "transformacao": r2, "antes": antes, "depois": depois}


def cenario_backfill():
    """Backfill: reprocessa 2023 e 2024. Só essas partições ganham versão nova no Delta;
    a contagem total não muda (idempotência) e a Gold fica idêntica."""
    import duckdb
    antes = _impressao_digital(LAKE)
    r = [_sub("ingestao_ceap", a) for a in ("2023", "2024")]
    r.append(_sub("transformacao"))
    con = duckdb.connect()
    por_ano = con.execute(f"""select ano_arquivo, count(*), min(_ingerido_em)
        from delta_scan('{LAKE}/bronze/ceap_lancamento') group by 1 order by 1""").fetchall()
    return {"execucoes": r, "antes": antes, "depois": _impressao_digital(LAKE),
            "bronze_por_ano": [list(map(str, x)) for x in por_ano]}


CENARIOS = {"base": cenario_base, "retry": cenario_retry, "fonte_fora": cenario_fonte_fora,
            "api_fora": cenario_api_fora, "dado_sujo": cenario_dado_sujo,
            "backfill": cenario_backfill}

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--executar":
        r = _executar(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
        print("@@RESULTADO@@" + json.dumps(r, ensure_ascii=False))
        sys.exit(0)
    EVID.mkdir(parents=True, exist_ok=True)
    for nome in (sys.argv[1:] or list(CENARIOS)):
        print(f"\n===== cenário: {nome} =====\n{CENARIOS[nome].__doc__.strip()}")
        out = CENARIOS[nome]()
        (EVID / f"{nome}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        # Nos outros cenários a falha é provocada; na execução normal ela tem de virar erro,
        # senão o `docker compose up` termina "com sucesso" sem Gold para o painel.
        if nome == "base" and not all(e["sucesso"] for e in out["execucoes"]):
            sys.exit(f"cenário base falhou: {[e['job'] for e in out['execucoes'] if not e['sucesso']]}")
