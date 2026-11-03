"""
Camada Bronze da E3 — ingestão direta do CSV da Câmara para Delta Lake (ADR-0004).

Contrato:
  * Uma partição Delta por ano de arquivo (`ano_arquivo`). Reexecutar um ano
    SUBSTITUI apenas aquela partição (replaceWhere) -> idempotente e permite backfill
    ano a ano sem tocar nos demais.
  * Todas as colunas de origem entram como texto, sem coerção (fidelidade ao dado bruto).
    Tipagem e regras de domínio ficam na Silver (dbt).
  * Exceção deliberada (LGPD, minimização): a coluna `cpf` do parlamentar NÃO é gravada.
    Ela não é necessária à pergunta de gestão; a chave do parlamentar é `nuDeputadoId`.
  * `_hash_lancamento`: md5 de TODOS os campos de origem (inclusive cpf, antes do descarte).
    Medido em 2026-11-03: as 785.929 linhas dos CSVs 2023–2026 são todas distintas, mas
    `ideDocumento` NÃO é único (30.357 linhas com valor 0 e bilhetes SIGEPA com até 9
    trechos sob o mesmo id). Por isso o grão do fato é o lançamento, não o documento.

Injeção de falha (para exercitar retry/backfill na orquestração):
  * CEAP_FONTE_DIR aponta para o diretório dos CSVs. Apontar para um diretório vazio
    simula a fonte fora do ar (falha permanente).
  * CEAP_FALHA_TRANSITORIA=N faz as N primeiras tentativas de cada ano falharem com
    erro de I/O (falha transitória que o retry deve absorver).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
from deltalake import DeltaTable, write_deltalake

RAIZ = Path(__file__).resolve().parents[1]
FONTE_DIR = Path(os.getenv("CEAP_FONTE_DIR", RAIZ / "base-dados"))
LAKEHOUSE = Path(os.getenv("LAKEHOUSE_PATH", RAIZ / "lakehouse"))
BRONZE_PATH = LAKEHOUSE / "bronze" / "ceap_lancamento"
CONTADOR_FALHAS = LAKEHOUSE / "_controle" / "tentativas"

COLUNAS_ORIGEM = [
    "txNomeParlamentar", "cpf", "ideCadastro", "nuCarteiraParlamentar", "nuLegislatura",
    "sgUF", "sgPartido", "codLegislatura", "numSubCota", "txtDescricao",
    "numEspecificacaoSubCota", "txtDescricaoEspecificacao", "txtFornecedor", "txtCNPJCPF",
    "txtNumero", "indTipoDocumento", "datEmissao", "vlrDocumento", "vlrGlosa", "vlrLiquido",
    "numMes", "numAno", "numParcela", "txtPassageiro", "txtTrecho", "numLote",
    "numRessarcimento", "datPagamentoRestituicao", "vlrRestituicao", "nuDeputadoId",
    "ideDocumento", "urlDocumento",
]


class FonteIndisponivel(RuntimeError):
    """A dependência externa (arquivo da Câmara) não está acessível."""


def _falha_transitoria_injetada(ano: int) -> None:
    n = int(os.getenv("CEAP_FALHA_TRANSITORIA", "0"))
    if n <= 0:
        return
    CONTADOR_FALHAS.mkdir(parents=True, exist_ok=True)
    arq = CONTADOR_FALHAS / f"{ano}.txt"
    tentativas = int(arq.read_text()) if arq.exists() else 0
    arq.write_text(str(tentativas + 1))
    if tentativas < n:
        raise OSError(f"[falha injetada] leitura de Ano-{ano}.csv interrompida "
                      f"(tentativa {tentativas + 1} de {n} que devem falhar)")


def ingerir_ano(ano: int) -> dict:
    """Lê Ano-<ano>.csv e substitui a partição `ano_arquivo=<ano>` na Bronze."""
    _falha_transitoria_injetada(ano)

    csv = FONTE_DIR / f"Ano-{ano}.csv"
    if not csv.exists():
        raise FonteIndisponivel(f"Fonte da Câmara indisponível: {csv} não encontrado")

    hash_expr = "md5(concat_ws(chr(31), " + ", ".join(
        f"coalesce(\"{c}\", '<nulo>')" for c in COLUNAS_ORIGEM) + "))"
    colunas_gravadas = ", ".join(f'"{c}"' for c in COLUNAS_ORIGEM if c != "cpf")
    ingerido_em = datetime.now(timezone.utc).isoformat(timespec="seconds")

    con = duckdb.connect()
    tabela = con.execute(f"""
        SELECT
            {colunas_gravadas},
            {hash_expr}                      AS _hash_lancamento,
            '{csv.name}'                     AS _arquivo_origem,
            '{ingerido_em}'                  AS _ingerido_em,
            '{ano}'                          AS ano_arquivo
        FROM read_csv('{csv}', delim=';', header=true, all_varchar=true,
                      quote='"', escape='"', strict_mode=false)
    """).arrow()
    con.close()

    if tabela.num_rows == 0:
        raise FonteIndisponivel(f"{csv.name} veio vazio — recusando sobrescrever a partição")

    BRONZE_PATH.parent.mkdir(parents=True, exist_ok=True)
    existe = (BRONZE_PATH / "_delta_log").exists()
    write_deltalake(
        str(BRONZE_PATH),
        tabela,
        mode="overwrite" if existe else "append",
        partition_by=["ano_arquivo"],
        predicate=f"ano_arquivo = '{ano}'" if existe else None,
    )
    versao = DeltaTable(str(BRONZE_PATH)).version()
    return {"ano": ano, "linhas": tabela.num_rows, "arquivo": csv.name,
            "versao_delta": versao, "ingerido_em": ingerido_em}


if __name__ == "__main__":
    anos = [int(a) for a in (sys.argv[1:] or os.getenv("ANOS", "2023,2024,2025,2026").split(","))]
    for a in anos:
        print(ingerir_ano(a))
