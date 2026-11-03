"""
Bronze — histórico de eventos dos deputados (API de Dados Abertos da Câmara).

Por que esta fonte existe: o campo `sgPartido` dos CSVs da CEAP é regravado com o partido
ATUAL do deputado quando a Câmara regera o arquivo. Exemplo verificado em 2026-11-03:
o deputado de ideCadastro 204494 aparece como PRD em lançamentos de fev/2023 no
Ano-2023.csv, mas o histórico oficial (GET /api/v2/deputados/204494/historico) registra
PATRIOTA de 01/02/2023 até a "Alteração de partido" para PRD em 07/02/2024.
Ou seja, a fonte já faz SCD tipo 1. A única forma de recuperar a filiação da época é
este endpoint de histórico, que guarda cada evento com data e hora.

Contrato:
  * Uma linha por evento retornado pela API, sem coerção (texto), mais metadados.
  * Snapshot completo a cada execução (overwrite) + cache JSON por deputado em
    lakehouse/_cache/historico/, para que uma queda da API não apague o último estado bom.
  * Deputados = todos os ideCadastro presentes na Bronze da CEAP.

Injeção de falha:
  * CEAP_API_BASE pode apontar para um host inexistente para simular a API fora do ar.
  * CEAP_USAR_CACHE=1 permite usar o cache local quando a API cair (modo degradado explícito).
"""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pyarrow as pa
import requests
from deltalake import write_deltalake

RAIZ = Path(__file__).resolve().parents[1]
LAKEHOUSE = Path(os.getenv("LAKEHOUSE_PATH", RAIZ / "lakehouse"))
BRONZE_CEAP = LAKEHOUSE / "bronze" / "ceap_lancamento"
BRONZE_HIST = LAKEHOUSE / "bronze" / "camara_deputado_historico"
CACHE = LAKEHOUSE / "_cache" / "historico"
API = os.getenv("CEAP_API_BASE", "https://dadosabertos.camara.leg.br/api/v2")
CAMPOS = ["id", "nome", "nomeEleitoral", "siglaPartido", "siglaUf", "idLegislatura",
          "dataHora", "situacao", "condicaoEleitoral", "descricaoStatus"]


class ApiIndisponivel(RuntimeError):
    """A API da Câmara não respondeu para uma parte relevante dos deputados."""


def _ids_deputados() -> list[int]:
    con = duckdb.connect()
    ids = [r[0] for r in con.execute(f"""
        SELECT DISTINCT ideCadastro::INTEGER FROM delta_scan('{BRONZE_CEAP}')
        WHERE nullif(ideCadastro, '') IS NOT NULL ORDER BY 1""").fetchall()]
    con.close()
    return ids


def _buscar(id_cadastro: int, sessao: requests.Session) -> tuple[int, list[dict] | None, str | None]:
    url = f"{API}/deputados/{id_cadastro}/historico"
    erro = None
    for tentativa in range(3):  # retry curto por deputado; o retry do job inteiro é do orquestrador
        try:
            r = sessao.get(url, headers={"Accept": "application/json"}, timeout=20)
            r.raise_for_status()
            dados = r.json()["dados"]
            CACHE.mkdir(parents=True, exist_ok=True)
            (CACHE / f"{id_cadastro}.json").write_text(json.dumps(dados, ensure_ascii=False))
            return id_cadastro, dados, None
        except (requests.RequestException, KeyError, ValueError) as e:
            erro = f"{type(e).__name__}: {e}"
            time.sleep(1.5 * (tentativa + 1))
    if os.getenv("CEAP_USAR_CACHE") == "1" and (CACHE / f"{id_cadastro}.json").exists():
        return id_cadastro, json.loads((CACHE / f"{id_cadastro}.json").read_text()), "cache"
    return id_cadastro, None, erro


def ingerir_historico(max_falhas_pct: float = 1.0) -> dict:
    ids = _ids_deputados()
    extraido_em = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if os.getenv("CEAP_USAR_CACHE") != "1":
        # Sonda antes de abrir 800 requisições: API fora do ar falha rápido e o retry
        # com backoff fica a cargo do orquestrador (RetryPolicy), não de 800 laços locais.
        try:
            requests.get(f"{API}/deputados/{ids[0]}/historico",
                         headers={"Accept": "application/json"}, timeout=10).raise_for_status()
        except requests.RequestException as e:
            raise ApiIndisponivel(f"API da Câmara inacessível em {API}: {type(e).__name__}") from e
    with requests.Session() as s, ThreadPoolExecutor(max_workers=8) as pool:
        resultados = list(pool.map(lambda i: _buscar(i, s), ids))

    falhas = [(i, e) for i, d, e in resultados if d is None]
    de_cache = sum(1 for _, d, e in resultados if d is not None and e == "cache")
    pct = 100 * len(falhas) / max(len(ids), 1)
    if pct > max_falhas_pct:
        # Não grava nada: o snapshot anterior continua valendo (falha não destrói o último estado bom)
        raise ApiIndisponivel(
            f"{len(falhas)}/{len(ids)} deputados sem histórico ({pct:.1f}% > {max_falhas_pct}%). "
            f"Exemplo: {falhas[0] if falhas else '-'}")

    linhas = []
    for id_cad, dados, origem in resultados:
        for ordem, ev in enumerate(dados or []):
            linha = {c: (None if ev.get(c) is None else str(ev.get(c))) for c in CAMPOS}
            linha.update({"_id_consultado": str(id_cad), "_ordem_evento": str(ordem),
                          "_extraido_em": extraido_em,
                          "_origem": "cache" if origem == "cache" else "api"})
            linhas.append(linha)
    tabela = pa.Table.from_pylist(linhas, schema=pa.schema([(c, pa.string()) for c in linhas[0]]))
    BRONZE_HIST.parent.mkdir(parents=True, exist_ok=True)
    write_deltalake(str(BRONZE_HIST), tabela, mode="overwrite", schema_mode="overwrite")
    return {"deputados": len(ids), "eventos": tabela.num_rows, "falhas": len(falhas),
            "de_cache": de_cache, "extraido_em": extraido_em}


if __name__ == "__main__":
    print(ingerir_historico())
