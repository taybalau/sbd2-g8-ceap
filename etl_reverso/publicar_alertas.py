"""
ETL reverso da E4 (issue #7): publica os parlamentares em alerta na fila de auditoria do PostgreSQL.

Origem:  camada semântica (semantico.met_parlamentar com em_alerta, e semantico.met_contexto), no
         lakehouse/ceap.duckdb. A métrica vem pronta; nada é recalculado aqui.
Destino: alerta.desvio_parlamentar no PostgreSQL da E1 (migrations/006_etl_reverso.sql), lida pelo
         auditor na view alerta.vw_fila_auditoria.

Push, diário: o Dagster roda isto no fim do job `transformacao`, logo depois do dbt (asset
alerta_desvio_postgres em orquestracao/definitions.py), com 3 tentativas e espera crescente.

Idempotente: a chave (referencia_dados, id_deputado) faz republicar os mesmos dados não criar linha
nova. Tudo numa transação só: se o banco cair no meio, nada fica pela metade.

Uso direto:  python etl_reverso/publicar_alertas.py
Conexão:     DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD (as mesmas variáveis da ingestão da E1).
"""
import json
import os
from pathlib import Path

import duckdb
import psycopg

RAIZ = Path(__file__).resolve().parents[1]
BANCO_LAKE = Path(os.getenv("LAKEHOUSE_PATH", RAIZ / "lakehouse")) / "ceap.duckdb"

COLUNAS = ["referencia_dados", "id_deputado", "nome_parlamentar", "partido_atual", "sigla_uf",
           "posicao_ranking", "desvio_acumulado", "desvio_relativo", "meses_acima_mediana",
           "meses_com_gasto", "janela_inicio", "janela_fim"]


def conectar_destino(timeout: int = 5) -> psycopg.Connection:
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "ceap_oltp"), user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"), connect_timeout=timeout,
        application_name="etl_reverso_ceap")


def ler_alertas() -> list[tuple]:
    """Lê da camada semântica só o que está em alerta, já com as métricas prontas."""
    con = duckdb.connect(str(BANCO_LAKE), read_only=True)
    try:
        return con.execute("""
            select c.atualizado_em, p.id_deputado, p.nome_parlamentar, p.partido_atual, p.sigla_uf,
                   p.posicao_ranking, round(p.desvio_acumulado, 2), round(p.desvio_relativo, 4),
                   p.meses_acima_mediana, p.meses_com_gasto, c.janela_inicio, c.janela_fim
            from semantico.met_parlamentar p cross join semantico.met_contexto c
            where p.em_alerta
            order by p.posicao_ranking, p.id_deputado""").fetchall()
    finally:
        con.close()


def publicar(origem: str = "manual", ensaio: bool = False) -> dict:
    """Publica na fila. Com ensaio=True faz todo o trabalho e desfaz a transação no fim (medições)."""
    alertas = ler_alertas()
    if not alertas:
        raise RuntimeError("a camada semântica não tem nenhum parlamentar em alerta: nada a publicar")
    referencia = alertas[0][0]
    insert = (f"insert into alerta.desvio_parlamentar ({', '.join(COLUNAS)}) "
              f"values ({', '.join(['%s'] * len(COLUNAS))}) "
              "on conflict (referencia_dados, id_deputado) do nothing")
    with conectar_destino() as con, con.transaction(force_rollback=ensaio), con.cursor() as cur:
        novas = 0
        for linha in alertas:
            cur.execute(insert, linha)
            novas += cur.rowcount
        cur.execute("insert into alerta.execucao (referencia_dados, linhas_recebidas, linhas_novas, origem) "
                    "values (%s, %s, %s, %s)", (referencia, len(alertas), novas, origem))
    return {"referencia_dados": referencia.isoformat(), "linhas_recebidas": len(alertas),
            "linhas_novas": novas, "ids_em_alerta": [a[1] for a in alertas]}


def ids_publicados(referencia=None) -> list[int]:
    """Ids do retrato mais recente (ou de uma referência) no destino, para conferência."""
    with conectar_destino() as con:
        filtro = "%s" if referencia else "(select max(referencia_dados) from alerta.desvio_parlamentar)"
        return [r[0] for r in con.execute(
            f"select id_deputado from alerta.desvio_parlamentar where referencia_dados = {filtro} "
            "order by posicao_ranking, id_deputado", [referencia] if referencia else []).fetchall()]


if __name__ == "__main__":
    print(json.dumps(publicar("linha de comando"), ensure_ascii=False, indent=2))
