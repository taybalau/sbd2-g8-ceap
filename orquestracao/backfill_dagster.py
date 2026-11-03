"""
Backfill de verdade pelo Dagster (não execução em processo): submete um backfill das partições
2023 e 2024 do job `ingestao_ceap`, espera o daemon executá-lo e espera o sensor
`transforma_apos_ingestao` disparar a transformação. Grava orquestracao/evidencias/backfill_dagster.json.

Precisa do `dagster dev` no ar com o mesmo DAGSTER_HOME (é o que o daemon usa):
    docker compose exec e3-dagster python orquestracao/backfill_dagster.py
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dagster import DagsterInstance, DagsterRunStatus, RunsFilter

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "orquestracao"))
from demo_falhas import LAKE, _impressao_digital  # noqa: E402

PARTICOES = os.getenv("PARTICOES_BACKFILL", "2023,2024")
FIM = {DagsterRunStatus.SUCCESS, DagsterRunStatus.FAILURE, DagsterRunStatus.CANCELED}


def _resumo(run):
    stats = instancia.get_run_stats(run.run_id)
    return {"run_id": run.run_id, "job": run.job_name, "status": run.status.value,
            "particao": run.tags.get("dagster/partition"),
            "disparado_por": run.tags.get("dagster/sensor_name") or
                             ("backfill " + run.tags["dagster/backfill"]
                              if "dagster/backfill" in run.tags else "manual"),
            "inicio": datetime.fromtimestamp(stats.start_time, timezone.utc).isoformat()
                      if stats.start_time else None,
            "fim": datetime.fromtimestamp(stats.end_time, timezone.utc).isoformat()
                   if stats.end_time else None}


def _esperar(filtro, quantidade, limite_s):
    fim = time.time() + limite_s
    while time.time() < fim:
        runs = instancia.get_runs(filters=filtro)
        if len(runs) >= quantidade and all(r.status in FIM for r in runs):
            return runs
        time.sleep(10)
    return instancia.get_runs(filters=filtro)


def _bronze_por_ano():
    import duckdb
    con = duckdb.connect()
    con.execute("LOAD delta")
    return [list(map(str, x)) for x in con.execute(f"""
        select ano_arquivo, count(*), min(_ingerido_em)
        from delta_scan('{LAKE}/bronze/ceap_lancamento') group by 1 order by 1""").fetchall()]


if __name__ == "__main__":
    instancia = DagsterInstance.get()
    inicio = datetime.now(timezone.utc)
    antes = {"estado": _impressao_digital(LAKE), "bronze_por_ano": _bronze_por_ano()}

    cmd = ["dagster", "job", "backfill", "-f", str(RAIZ / "orquestracao" / "definitions.py"),
           "-j", "ingestao_ceap", "--partitions", PARTICOES, "--noprompt"]
    print("$", " ".join(cmd))
    subprocess.run(cmd, check=True)

    backfill = instancia.get_backfills()[0]   # mais recente primeiro
    print(f"backfill {backfill.backfill_id} submetido; aguardando o daemon")
    runs_backfill = _esperar(RunsFilter(tags={"dagster/backfill": backfill.backfill_id}),
                             len(PARTICOES.split(",")), 15 * 60)
    print("aguardando o sensor disparar a transformação")
    runs_sensor = _esperar(RunsFilter(job_name="transformacao", created_after=inicio,
                                      tags={"dagster/sensor_name": "transforma_apos_ingestao"}),
                           len(PARTICOES.split(",")), 30 * 60)

    depois = {"estado": _impressao_digital(LAKE), "bronze_por_ano": _bronze_por_ano()}
    backfill = instancia.get_backfill(backfill.backfill_id)
    saida = {
        "comando": " ".join(cmd),
        "backfill_id": backfill.backfill_id,
        "backfill_status": backfill.status.value,
        "runs_do_backfill": [_resumo(r) for r in runs_backfill],
        "runs_disparados_pelo_sensor": [_resumo(r) for r in runs_sensor],
        "antes": antes,
        "depois": depois,
    }
    destino = RAIZ / "orquestracao" / "evidencias" / "backfill_dagster.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(saida, ensure_ascii=False, indent=2, default=str))
    print(json.dumps(saida, ensure_ascii=False, indent=2, default=str))
    ok = (all(r.status == DagsterRunStatus.SUCCESS for r in runs_backfill)
          and any(r.status == DagsterRunStatus.SUCCESS for r in runs_sensor))
    sys.exit(0 if ok else 1)
