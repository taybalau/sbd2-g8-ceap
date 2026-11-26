"""
Medições da E4 para o ADR-0008: quanto custa ao consumidor (o painel) ler as métricas por cada caminho.

Caminhos medidos, sempre com as MESMAS consultas que o painel faz ao abrir (uma por view que ele lê
inteira) e o volume real do lakehouse:
  1. warehouse, views      — DuckDB lendo as views do schema `semantico` (o que o painel usa hoje);
  2. warehouse, tabelas    — as mesmas métricas materializadas como tabelas (custo de não usar views);
  3. cópia em Parquet      — um arquivo por view, lido com DuckDB;
  4. cópia em CSV          — a opção nula: um arquivo por view, lido com pandas.

Para cada caminho: latência de leitura (mediana e p90 de N leituras, cada uma com conexão nova),
custo de produzir a cópia (tempo de exportação) e espaço em disco. Mede também a consulta filtrada
dos lançamentos (met_lancamento_parlamentar, um parlamentar e uma categoria), que o painel faz a cada
seleção em vez de ler a view inteira. Grava o JSON e imprime a tabela em Markdown.

A medição da entrega E4 (5 views; citada no ADR-0008) está em docs/evidencias/e4_leitura_semantica.json.
Medições posteriores vão para outro arquivo, para não reescrever a evidência da entrega.

Uso (com o lakehouse gerado, dentro do container da E3):
    python scripts/medir_leitura_semantica.py [n_leituras] [arquivo_saida.json]
"""
import json
import os
import platform
import shutil
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
BANCO = Path(os.getenv("LAKEHOUSE_PATH", RAIZ / "lakehouse")) / "ceap.duckdb"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
SAIDA = (RAIZ / sys.argv[2]) if len(sys.argv) > 2 else RAIZ / "docs" / "evidencias" / "painel_leitura_semantica.json"
# as views que o painel lê inteiras ao abrir (painel/app.py, carregar())
VIEWS = ["met_parlamentar", "met_parlamentar_mes", "met_partido", "met_categoria_parlamentar",
         "met_fornecedor_parlamentar", "met_contexto", "met_qualidade_build"]


def tamanho(caminho: Path) -> int:
    return caminho.stat().st_size if caminho.is_file() else sum(p.stat().st_size for p in caminho.rglob("*") if p.is_file())


def medir(ler) -> dict:
    ler()  # aquecimento: a primeira leitura paga o carregamento das extensões
    tempos = []
    for _ in range(N):
        t = time.perf_counter()
        linhas = ler()
        tempos.append((time.perf_counter() - t) * 1000)
    tempos.sort()
    return {"latencia_mediana_ms": round(statistics.median(tempos), 1),
            "latencia_p90_ms": round(tempos[int(0.9 * (len(tempos) - 1))], 1), "linhas_lidas": linhas}


def ler_duckdb(arquivo: Path, schema: str):
    def ler():
        con = duckdb.connect(str(arquivo), read_only=True)
        n = sum(len(con.execute(f"select * from {schema}.{v}").df()) for v in VIEWS)
        con.close()
        return n
    return ler


def main():
    tmp = Path(tempfile.mkdtemp(prefix="medicao_e4_"))
    resultados = {}
    try:
        resultados["warehouse_views"] = {**medir(ler_duckdb(BANCO, "semantico")), "custo_copia_ms": 0,
                                         "bytes": None, "defasagem": "nenhuma (lê a Gold atual)"}

        # 2. tabelas materializadas num banco à parte (o lakehouse não é alterado)
        t = time.perf_counter()
        tab = tmp / "tabelas.duckdb"
        con = duckdb.connect(str(tab))
        con.execute(f"attach '{BANCO}' as ceap (read_only)")  # as views referenciam o banco pelo nome ceap
        con.execute("create schema semantico")
        for v in VIEWS:
            con.execute(f"create table semantico.{v} as select * from ceap.semantico.{v}")
        con.close()
        resultados["warehouse_tabelas"] = {**medir(ler_duckdb(tab, "semantico")),
                                           "custo_copia_ms": round((time.perf_counter() - t) * 1000, 1),
                                           "bytes": tamanho(tab), "defasagem": "até o próximo build"}

        # 3 e 4. cópias em arquivo, exportadas das views
        for formato in ("parquet", "csv"):
            pasta = tmp / formato
            pasta.mkdir()
            t = time.perf_counter()
            con = duckdb.connect(str(BANCO), read_only=True)
            for v in VIEWS:
                opcao = "(format parquet)" if formato == "parquet" else "(header, delimiter ',')"
                con.execute(f"copy (select * from semantico.{v}) to '{pasta / v}.{formato}' {opcao}")
            con.close()
            custo = round((time.perf_counter() - t) * 1000, 1)
            if formato == "parquet":
                def ler(p=pasta):
                    con = duckdb.connect()
                    n = sum(len(con.execute(f"select * from read_parquet('{p / v}.parquet')").df()) for v in VIEWS)
                    con.close()
                    return n
            else:
                def ler(p=pasta):
                    return sum(len(pd.read_csv(p / f"{v}.csv")) for v in VIEWS)
            resultados[f"copia_{formato}"] = {**medir(ler), "custo_copia_ms": custo, "bytes": tamanho(pasta),
                                              "defasagem": "até a próxima exportação agendada"}
        # consulta filtrada que o painel faz a cada seleção: os maiores lançamentos do líder na categoria 1
        con = duckdb.connect(str(BANCO), read_only=True)
        dep, cat = con.execute(
            "select p.id_deputado, c.num_subcota from semantico.met_parlamentar p "
            "join semantico.met_categoria_parlamentar c using (id_deputado) "
            "where p.posicao_ranking = 1 and c.posicao_excesso = 1 limit 1").fetchone()
        con.close()

        def ler_lancamentos():
            con = duckdb.connect(str(BANCO), read_only=True)
            n = len(con.execute("select * from semantico.met_lancamento_parlamentar where id_deputado = ? "
                                "and num_subcota = ? and posicao_valor <= 15", [dep, cat]).df())
            con.close()
            return n
        lancamentos = medir(ler_lancamentos)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    con = duckdb.connect(str(BANCO), read_only=True)
    volume = {
        "lancamentos_no_fato": con.execute("select count(*) from silver.fct_lancamento_ceap").fetchone()[0],
        "linhas_por_view": {v: con.execute(f"select count(*) from semantico.{v}").fetchone()[0] for v in VIEWS},
    }
    con.close()
    evidencia = {"medido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "n_leituras": N,
                 "ambiente": f"{platform.system()} {platform.machine()}, Python {platform.python_version()}, "
                             f"DuckDB {duckdb.__version__}",
                 "banco_bytes": tamanho(BANCO), "volume": volume, "caminhos": resultados,
                 "lancamentos_por_selecao": lancamentos}
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(evidencia, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    nomes = {"warehouse_views": "Warehouse (views `semantico`)", "warehouse_tabelas": "Warehouse (tabelas)",
             "copia_parquet": "Cópia em Parquet", "copia_csv": "Cópia em CSV (opção nula)"}
    print(f"| Caminho | Leitura (mediana) | Leitura (p90) | Custo de gerar a cópia | Espaço | Defasagem |")
    print("| :--- | ---: | ---: | ---: | ---: | :--- |")
    for k, r in resultados.items():
        espaco = "— (lê o banco)" if r["bytes"] is None else f"{r['bytes'] / 1024:,.0f} KiB".replace(",", ".")
        print(f"| {nomes[k]} | {r['latencia_mediana_ms']:.0f} ms | {r['latencia_p90_ms']:.0f} ms | "
              f"{r['custo_copia_ms']:.0f} ms | {espaco} | {r['defasagem']} |")
    print(f"\nLançamentos de um parlamentar numa categoria (a cada seleção): mediana "
          f"{lancamentos['latencia_mediana_ms']:.0f} ms, p90 {lancamentos['latencia_p90_ms']:.0f} ms")
    print(f"\n{volume} — {N} leituras por caminho; evidência em {SAIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
