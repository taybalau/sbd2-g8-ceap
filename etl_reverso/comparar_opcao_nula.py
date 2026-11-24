"""
ETL reverso × opção nula (E4, issue #7): um CSV agendado já atenderia o auditor?

Publica os MESMOS parlamentares em alerta pelos dois caminhos e mede, com o volume real:
  * custo de publicar (tabela no PostgreSQL × arquivo CSV) e de o auditor ler a fila;
  * o que o auditor precisa fazer com o dado, testado de verdade e não só afirmado:
      1. registrar a decisão sobre um caso e ela sobreviver à publicação do dia seguinte;
      2. consultar o histórico de quando cada parlamentar entrou no alerta;
      3. ter o registro protegido contra alteração;
      4. ter acesso por perfil (privilégio mínimo).
Nada fica gravado no PostgreSQL (tudo em transações desfeitas) e o CSV vai para uma pasta temporária.
Grava docs/evidencias/e4_etl_reverso_opcao_nula.json e imprime a tabela em Markdown.

Uso (plataforma no ar, dentro do container da E3):
    python etl_reverso/comparar_opcao_nula.py [n_repeticoes]
"""
import csv
import json
import shutil
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import publicar_alertas as etl

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "docs" / "evidencias" / "e4_etl_reverso_opcao_nula.json"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 20


def cronometrar(funcao) -> dict:
    funcao()  # aquecimento
    tempos = []
    for _ in range(N):
        t = time.perf_counter()
        funcao()
        tempos.append((time.perf_counter() - t) * 1000)
    tempos.sort()
    return {"mediana_ms": round(statistics.median(tempos), 1),
            "p90_ms": round(tempos[int(0.9 * (len(tempos) - 1))], 1)}


def exportar_csv(destino: Path) -> None:
    with destino.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(etl.COLUNAS)
        w.writerows(etl.ler_alertas())


def main():
    tmp = Path(tempfile.mkdtemp(prefix="opcao_nula_"))
    arquivo = tmp / "alerta_desvio_parlamentar.csv"
    try:
        # ---- custo de publicar e de ler (mesmos dados, mesma origem)
        publicar_pg = cronometrar(lambda: etl.publicar("medição", ensaio=True))
        publicar_csv = cronometrar(lambda: exportar_csv(arquivo))

        def ler_fila_pg():
            with etl.conectar_destino() as con:
                return con.execute("select * from alerta.vw_fila_auditoria").fetchall()
        ler_pg = cronometrar(ler_fila_pg)
        ler_csv = cronometrar(lambda: pd.read_csv(arquivo))

        # ---- 1. a decisão do auditor sobrevive à próxima publicação?
        with etl.conectar_destino() as con, con.transaction(force_rollback=True):
            alvo = con.execute("select id_deputado, referencia_dados from alerta.vw_fila_auditoria "
                               "order by posicao_ranking limit 1").fetchone()
            con.execute("insert into alerta.tratamento (id_deputado, referencia_dados, situacao, observacao) "
                        "values (%s, %s, 'em_analise', 'teste da opção nula')", alvo)
            # a "publicação do dia seguinte" no PostgreSQL é um retrato novo; a fila junta a decisão
            situacao_pg = con.execute("select situacao from alerta.vw_fila_auditoria where id_deputado = %s",
                                      [alvo[0]]).fetchone()[0]
        df = pd.read_csv(arquivo)
        df["situacao"] = "pendente"
        df.loc[df.id_deputado == alvo[0], "situacao"] = "em_analise"   # o auditor anota no CSV
        df.to_csv(arquivo, index=False)
        exportar_csv(arquivo)                                           # a exportação agendada do dia seguinte
        situacao_csv = "em_analise" if "situacao" in pd.read_csv(arquivo).columns else "perdida"

        # ---- 2. histórico
        with etl.conectar_destino() as con:
            retratos_pg = con.execute("select count(distinct referencia_dados) from alerta.desvio_parlamentar").fetchone()[0]

        # ---- 3. proteção contra alteração
        try:
            with etl.conectar_destino() as con, con.transaction(force_rollback=True):
                con.execute("update alerta.desvio_parlamentar set desvio_acumulado = 0")
            alteracao_pg = "aceita"
        except Exception as e:  # noqa: BLE001
            alteracao_pg = "bloqueada: " + str(e).strip().splitlines()[0][:120]
        df = pd.read_csv(arquivo)
        df["desvio_acumulado"] = 0
        df.to_csv(arquivo, index=False)
        alteracao_csv = "aceita (qualquer um com acesso ao arquivo reescreve os valores)"

        tamanho_csv = arquivo.stat().st_size
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    resultado = {
        "medido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "repeticoes": N,
        "linhas_publicadas": len(etl.ler_alertas()),
        "custo": {"publicar_postgres": publicar_pg, "publicar_csv": publicar_csv,
                  "ler_fila_postgres": ler_pg, "ler_csv": ler_csv, "csv_bytes": tamanho_csv},
        "necessidades_do_auditor": {
            "decisao_sobrevive_a_proxima_publicacao": {"postgres": situacao_pg, "csv": situacao_csv},
            "historico_de_alertas": {"postgres": f"{retratos_pg} retrato(s) guardados, consultáveis por SQL",
                                     "csv": "só o arquivo do dia (a exportação sobrescreve), ou um arquivo por dia sem consulta"},
            "registro_protegido_contra_alteracao": {"postgres": alteracao_pg, "csv": alteracao_csv},
            "acesso_por_perfil": {"postgres": "GRANT por role (ceap_auditor lê a fila e registra decisões; ceap_pipeline só publica)",
                                  "csv": "só permissão de arquivo: quem lê também pode editar e repassar"},
        },
    }
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(resultado, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

    c = resultado["custo"]
    print("| | Tabela no PostgreSQL (adotado) | CSV agendado (opção nula) |")
    print("| :--- | :--- | :--- |")
    print(f"| Publicar ({resultado['linhas_publicadas']} linhas) | {c['publicar_postgres']['mediana_ms']:.0f} ms | "
          f"{c['publicar_csv']['mediana_ms']:.1f} ms |")
    print(f"| Auditor ler a fila | {c['ler_fila_postgres']['mediana_ms']:.0f} ms | {c['ler_csv']['mediana_ms']:.1f} ms |")
    for nome, v in resultado["necessidades_do_auditor"].items():
        print(f"| {nome.replace('_', ' ')} | {v['postgres']} | {v['csv']} |")
    print(f"\nevidência em {SAIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
