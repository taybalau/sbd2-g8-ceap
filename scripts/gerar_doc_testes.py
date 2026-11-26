"""
Gera docs/testes.md a partir do próprio dbt: todos os testes declarados (manifest.json), o
resultado da última execução (run_results.json) e a freshness das fontes (sources.json).

Uso (depois de um `dbt build` e de um `dbt source freshness`, por exemplo dentro do container):
    python scripts/gerar_doc_testes.py [pasta_target_do_dbt] [arquivo_de_saida]
"""
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
TARGET = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "dbt_ceap" / "target"
SAIDA = Path(sys.argv[2]) if len(sys.argv) > 2 else RAIZ / "docs" / "testes.md"

# Categoria do checklist da E3 de cada teste singular (os genéricos saem pelo tipo).
CATEGORIA_SINGULAR = {
    "assert_fato_reconcilia_com_bronze": "Volume",
    "assert_gold_reconcilia_com_fato": "Volume",
    "assert_desvio_alocado_reconcilia": "Volume",
    "assert_serie_mensal_sem_lacuna": "Volume",
    "assert_todos_os_anos_presentes": "Volume",
    "assert_serie_mensal_sem_salto": "Distribuição",
    "assert_subcota_sem_salto": "Distribuição",
    "assert_valor_inconsistente_sob_controle": "Distribuição",
    "assert_negativo_somente_em_subcota_de_compensacao": "Domínio (dado sujo)",
    "assert_subcota_nao_some_entre_anos": "Domínio (dado sujo)",
    "assert_deputado_ativo_nao_some_no_meio": "Domínio (dado sujo)",
    "assert_divergencia_csv_vs_historico": "Domínio (dado sujo)",
    "assert_scd_janelas_contiguas": "SCD tipo 2",
    "assert_scd_preserva_partido_da_epoca": "SCD tipo 2",
    "assert_scd_caso_conhecido_204494": "SCD tipo 2",
    "assert_gold_dentro_do_sla": "Freshness e SLA",
    "assert_semantico_gasto_consistente": "Consumo duplo (E4)",
    "assert_semantico_desvio_consistente": "Consumo duplo (E4)",
    "assert_semantico_sem_cpf_completo": "Privacidade (LGPD)",
}
# O que cada teste singular verifica, em uma frase (o detalhe fica no comentário do .sql).
DESCRICAO_SINGULAR = {
    "assert_fato_reconcilia_com_bronze": "o fato tem a mesma contagem e a mesma soma da Bronze (nenhuma junção duplicou ou perdeu linha)",
    "assert_gold_reconcilia_com_fato": "o fato mensal soma exatamente o fato no mesmo recorte (57ª, sem lideranças)",
    "assert_desvio_alocado_reconcilia": "o desvio rateado entre as versões de um mês de troca de partido soma o desvio do mês",
    "assert_serie_mensal_sem_lacuna": "nenhum mês sem lançamentos entre a primeira e a última competência",
    "assert_todos_os_anos_presentes": "cada ano esperado (2023 a 2026) está na Bronze e no fato",
    "assert_serie_mensal_sem_salto": "o gasto total e o nº de deputados de cada mês fechado ficam entre 0,60 e 1,70 da mediana dos 6 meses anteriores",
    "assert_subcota_sem_salto": "nenhuma subcota relevante cai abaixo de 25% da sua mediana dos 6 meses anteriores",
    "assert_valor_inconsistente_sob_controle": "lançamentos com líquido ≠ documento − glosa ficam abaixo de 0,3% do total",
    "assert_negativo_somente_em_subcota_de_compensacao": "valor negativo só nas subcotas de compensação (40, 996, 998, 999)",
    "assert_subcota_nao_some_entre_anos": "subcota com 100+ lançamentos num ano não desaparece no ano seguinte",
    "assert_deputado_ativo_nao_some_no_meio": "deputado sem gasto por 3+ meses no meio do mandato (lista para conferência)",
    "assert_divergencia_csv_vs_historico": "mede quantos lançamentos têm no CSV um partido diferente do vigente na data do gasto",
    "assert_scd_janelas_contiguas": "as versões de cada deputado não se sobrepõem, não têm buraco e há uma única versão atual",
    "assert_scd_preserva_partido_da_epoca": "cada lançamento aponta para a versão vigente na data do gasto, e não para a atual",
    "assert_scd_caso_conhecido_204494": "regressão com caso real: o deputado 204494 é PATRIOTA até 07/02/2024 e PRD depois",
    "assert_gold_dentro_do_sla": "a Gold foi construída até 26 h depois da ingestão mais recente",
    "assert_semantico_gasto_consistente": "o gasto total é o mesmo número por parlamentar, por partido, por categoria, por fornecedor, mês a mês, lançamento a lançamento e no fato",
    "assert_semantico_desvio_consistente": "o desvio por partido bate com o por parlamentar, a série mensal de cada deputado soma o desvio acumulado dele, e o erro da sobrescrita do contexto bate com o dos partidos",
    "assert_semantico_sem_cpf_completo": "nenhuma view da camada semântica entrega CPF completo de fornecedor pessoa física (documento, nome de MEI ou link do recibo)",
}
CATEGORIA_GENERICO = {"not_null": "Esquema", "unique": "Unicidade", "grao_unico": "Unicidade",
                      "relationships": "Integridade referencial"}
ORDEM = ["Esquema", "Volume", "Unicidade", "Integridade referencial", "Distribuição",
         "Domínio (dado sujo)", "SCD tipo 2", "Freshness e SLA", "Consumo duplo (E4)",
         "Privacidade (LGPD)"]
STATUS = {"pass": "✅ passou", "fail": "❌ reprovou", "warn": "⚠️ aviso", "error": "❌ erro",
          "skipped": "⏭️ pulado", "runtime error": "❌ erro"}


def _nome(uid, manifest):
    if uid in manifest["nodes"]:
        return manifest["nodes"][uid]["name"]
    if uid in manifest["sources"]:
        s = manifest["sources"][uid]
        return f"{s['source_name']}.{s['name']}"
    return uid


def _modelo(no, manifest):
    if no.get("attached_node"):
        return _nome(no["attached_node"], manifest)
    return ", ".join(sorted(_nome(u, manifest) for u in no.get("depends_on", {}).get("nodes", [])))


def _descricao_singular(no):
    sql = Path(RAIZ / "dbt_ceap" / no["original_file_path"]).read_text(encoding="utf-8")
    linhas = []
    for l in sql.splitlines():
        if l.startswith("{{"):
            continue
        if not l.startswith("--"):
            break
        linhas.append(l.lstrip("- ").strip())
    texto = " ".join(linhas)
    frase = re.split(r"(?<=[.:])\s", texto, maxsplit=1)[0]
    return frase.rstrip(":").strip()


def _descricao_generico(no, manifest):
    meta = no["test_metadata"]
    k = meta.get("kwargs", {})
    col = k.get("column_name") or no.get("column_name")
    nome = meta["name"]
    if nome == "not_null":
        return f"`{col}` nunca é nulo"
    if nome == "unique":
        return f"`{col}` não se repete"
    if nome == "grao_unico":
        return "uma linha por (" + ", ".join(f"`{c}`" for c in k.get("colunas", [])) + ")"
    if nome == "relationships":
        destino = re.search(r"ref\('([^']+)'\)", k.get("to", ""))
        return f"todo `{col}` existe em `{destino.group(1) if destino else k.get('to')}.{k.get('field')}`"
    return nome


def main():
    manifest = json.loads((TARGET / "manifest.json").read_text())
    resultados = {}
    executado_em = None
    if (TARGET / "run_results.json").exists():
        rr = json.loads((TARGET / "run_results.json").read_text())
        executado_em = rr["metadata"]["generated_at"]
        resultados = {r["unique_id"]: r for r in rr["results"]}

    por_categoria = defaultdict(list)
    for uid, no in manifest["nodes"].items():
        if no["resource_type"] != "test" or no["package_name"] != "ceap":
            continue
        generico = "test_metadata" in no and no["test_metadata"]
        if generico:
            categoria = CATEGORIA_GENERICO.get(no["test_metadata"]["name"], "Outros")
            descricao = _descricao_generico(no, manifest)
            nome = no["test_metadata"]["name"]
        else:
            categoria = CATEGORIA_SINGULAR.get(no["name"], "Outros")
            descricao = DESCRICAO_SINGULAR.get(no["name"]) or _descricao_singular(no)
            nome = no["name"]
        r = resultados.get(uid, {})
        status = STATUS.get(r.get("status"), "não executado")
        falhas = r.get("failures")
        if r.get("status") in ("fail", "warn") and falhas:
            status += f" ({falhas} linha{'s' if falhas != 1 else ''})"
        por_categoria[categoria].append({
            "nome": nome, "modelo": _modelo(no, manifest), "descricao": descricao,
            "severidade": "aviso" if no["config"].get("severity", "error").lower() == "warn" else "erro",
            "status": status, "singular": not generico})

    total = sum(len(v) for v in por_categoria.values())
    contagem = defaultdict(int)
    for v in por_categoria.values():
        for t in v:
            contagem[t["status"].split(" (")[0]] += 1

    out = ["# Testes de dados", "",
           "> Página gerada por `scripts/gerar_doc_testes.py` a partir do `manifest.json` e do",
           "> `run_results.json` do dbt. Não edite à mão: rode o script depois de um `dbt build`.", ""]
    if executado_em:
        quando = datetime.fromisoformat(executado_em.replace("Z", "+00:00")).astimezone(timezone.utc)
        out += [f"**Última execução:** {quando:%d/%m/%Y %H:%M} UTC, numa subida do zero "
                f"(`docker compose up --build`) com os CSVs da Câmara baixados no mesmo dia.", ""]
    out += ["| Resultado | Testes |", "| :--- | ---: |"]
    out += [f"| {s} | {n} |" for s, n in sorted(contagem.items())]
    out += [f"| **Total** | **{total}** |", ""]

    out += ["## Cobertura do checklist da E3 e da E4", "",
            "| Categoria | Testes | O que garante |", "| :--- | ---: | :--- |"]
    garante = {
        "Esquema": "colunas obrigatórias preenchidas; o contrato das tabelas de consumo (abaixo) fixa colunas e tipos",
        "Volume": "nenhuma linha perdida ou duplicada entre Bronze, fato e Gold; nenhum ano ou mês faltando",
        "Unicidade": "o grão declarado de cada modelo vale (uma linha por chave)",
        "Integridade referencial": "toda chave do fato aponta para uma linha existente da dimensão",
        "Distribuição": "o total e cada subcota não saltam fora da faixa calibrada com os dados reais (erro silencioso)",
        "Domínio (dado sujo)": "valor negativo onde não cabe, subcota ou deputado que some, sobrescrita da fonte",
        "SCD tipo 2": "o partido usado é o da data do gasto, sem buracos nem sobreposição de versões",
        "Freshness e SLA": "a Gold não é publicada sobre uma Bronze mais velha que o SLA de 26 h",
        "Consumo duplo (E4)": "a mesma métrica dá o mesmo número em todas as visões da camada semântica "
                              "(o painel lê só dela; scripts/verificar_consumo_duplo.py confere a tela)",
        "Privacidade (LGPD)": "o CPF de fornecedor pessoa física não chega completo ao consumo (docs/lgpd.md, L1 e L10)",
    }
    for c in ORDEM:
        if c in por_categoria:
            out.append(f"| [{c}](#{_ancora(c)}) | {len(por_categoria[c])} | {garante.get(c, '')} |")
    out.append("")

    contratos = [n for n in manifest["nodes"].values()
                 if n["resource_type"] == "model" and n["config"].get("contract", {}).get("enforced")]
    if contratos:
        out += ["### Contratos de esquema", "",
                "Estas tabelas têm `contract: enforced`: o `dbt build` reprova se uma coluna sumir, mudar",
                "de nome ou mudar de tipo em relação ao declarado. As colunas e os tipos estão no",
                "[dicionário de dados](dicionario-de-dados.md).", "",
                "| Tabela | Colunas sob contrato |", "| :--- | ---: |"]
        out += [f"| `{n['schema']}.{n['name']}` | {len(n['columns'])} |" for n in sorted(contratos, key=lambda x: x["name"])]
        out += ["", "Contrato violado de propósito em `mart_desvio_parlamentar` (2026-11-17): primeiro declarando",
                "um tipo errado, depois tirando uma coluna do SQL. Nos dois casos a tabela não é criada:", "",
                "```text",
                "This model has an enforced contract that failed.",
                "| column_name      | definition_type | contract_type | mismatch_reason       |",
                "| posicao_ranking  | BIGINT          | VARCHAR       | data type mismatch    |",
                "| hhi_fornecedores |                 | DOUBLE        | missing in definition |",
                "```", ""]

    for c in ORDEM + sorted(set(por_categoria) - set(ORDEM)):
        if c not in por_categoria:
            continue
        out += [f"## {c}", "", "| Teste | Tabela | O que verifica | Severidade | Última execução |",
                "| :--- | :--- | :--- | :--- | :--- |"]
        for t in sorted(por_categoria[c], key=lambda x: (x["modelo"], x["nome"])):
            nome = f"`{t['nome']}`" + (" (singular)" if t["singular"] else "")
            tabelas = ", ".join(f"`{m}`" for m in t["modelo"].split(", "))
            out.append(f"| {nome} | {tabelas} | {t['descricao']} | {t['severidade']} | {t['status']} |")
        out.append("")

    fontes = TARGET / "sources.json"
    if fontes.exists():
        out += ["## Freshness das fontes (`dbt source freshness`)", "",
                "| Fonte | Carregada em (UTC) | Idade | Limites | Resultado |", "| :--- | :--- | ---: | :--- | :--- |"]
        limites = {"ceap_lancamento": "aviso 26 h · erro 48 h", "camara_deputado_historico": "aviso 7 dias · erro 30 dias"}
        for r in json.loads(fontes.read_text())["results"]:
            nome = r["unique_id"].split(".")[-1]
            carregado = (r.get("max_loaded_at") or "")[:16].replace("T", " ")
            out.append(f"| `bronze.{nome}` | {carregado} | {r.get('age', 0) / 3600:.1f} h | "
                       f"{limites.get(nome, '')} | {STATUS.get(r['status'], r['status'])} |")
        out.append("")

    out += ["## Outros testes da plataforma", "",
            "Além dos testes de dados do dbt, a plataforma tem testes de comportamento, com evidência versionada:", "",
            "| Teste | O que verifica | Onde |", "| :--- | :--- | :--- |",
            "| Falha transitória (`retry`) | 2 leituras do CSV falham e o retry absorve | `orquestracao/evidencias/retry.json` |",
            "| Fonte fora (`fonte_fora`) | CSV indisponível: 3 retries, Bronze e Gold intactas | `orquestracao/evidencias/fonte_fora.json` |",
            "| API fora (`api_fora`) | histórico indisponível: o dbt nem inicia | `orquestracao/evidencias/api_fora.json` |",
            "| Dado sujo (`dado_sujo`) | negativo injetado: teste reprova e a Gold não é publicada | `orquestracao/evidencias/dado_sujo.json` |",
            "| Backfill (`backfill`, `backfill_dagster`) | reprocessar 2023 e 2024 não muda a Gold (hash idêntico) | `orquestracao/evidencias/backfill*.json` |",
            "| SLA violado de propósito | `--vars '{sla_horas_gold: 0}'` reprova `assert_gold_dentro_do_sla` | [E3, seção 7](e3.md#7-freshness-e-sla) |",
            "| Consulta otimizada | antes e depois devolvem o mesmo resultado | `scripts/explain_desvio.sh`, [EXPLAIN](explain/README.md) |",
            "| Aceite da E2 | idempotência do lote, CDC, dado atrasado, deduplicação, UBO | `scripts/test_e2_pipeline.py`, [Lakehouse e CDC](lakehouse.md#testes-de-aceite) |",
            "", "## Como rodar", "",
            "Todos os testes de dados rodam sozinhos no `docker compose up --build` (container `e3-pipeline`).",
            "Para rodar de novo com a plataforma no ar e regerar esta página e o dicionário de dados:", "", "```bash",
            "docker compose run --build --rm --no-deps -e HOST_UID=\"$(id -u)\" -e HOST_GID=\"$(id -g)\" \\",
            "    -v ./docs:/app/docs -v ./scripts:/app/scripts e3-pipeline bash scripts/gerar_docs_e3.sh",
            "```", "", "As linhas reprovadas de cada teste ficam gravadas no schema `auditoria` do `ceap.duckdb`.", ""]
    SAIDA.write_text("\n".join(out), encoding="utf-8")
    print(f"{SAIDA}: {total} testes em {len(por_categoria)} categorias")


def _ancora(texto):
    t = texto.lower()
    t = re.sub(r"[^\w\s-]", "", t, flags=re.UNICODE)
    return re.sub(r"\s+", "-", t.strip())


if __name__ == "__main__":
    main()
