"""
Gera docs/dicionario-de-dados.md: cada tabela da Bronze, da Silver e da Gold com as colunas, os
tipos reais (lidos do ceap.duckdb e das tabelas Delta) e as descrições declaradas no dbt
(models/**/_*.yml e seeds/_seeds.yml). Coluna sem descrição faz o script falhar.

Uso (com o lakehouse gerado, por exemplo dentro do container da E3):
    python scripts/gerar_dicionario.py [pasta_target_do_dbt] [arquivo_de_saida]
"""
import json
import os
import sys
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[1]
TARGET = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "dbt_ceap" / "target"
SAIDA = Path(sys.argv[2]) if len(sys.argv) > 2 else RAIZ / "docs" / "dicionario-de-dados.md"
LAKE = Path(os.getenv("LAKEHOUSE_PATH", RAIZ / "lakehouse"))

# Colunas com dado pessoal (LGPD). O CPF do parlamentar nem chega à Bronze.
PESSOAL = {"txtPassageiro": "dado pessoal de terceiro: fica só na Bronze",
           "txtCNPJCPF": "pode ser CPF de pessoa física (fornecedor)",
           "documento_fornecedor": "pode ser CPF de pessoa física (fornecedor)",
           "chave_fornecedor": "pode conter CPF de pessoa física (fornecedor)"}
CAMADAS = [
    ("Bronze", "Cópia fiel dos dados públicos, em Delta Lake (`lakehouse/bronze/`), tudo como texto."),
    ("Silver", "Dados tipados, dimensões e o fato atômico (schema `silver` do `ceap.duckdb`)."),
    ("Gold", "Tabelas analíticas com grão declarado (schema `gold` do `ceap.duckdb`)."),
    ("Semântica", "Camada semântica de métricas da E4 (views do schema `semantico`): a única fonte do "
                  "painel e do ETL reverso."),
]


def _primeira_frase(texto):
    return " ".join((texto or "").split())


def main():
    manifest = json.loads((TARGET / "manifest.json").read_text())
    con = duckdb.connect(str(LAKE / "ceap.duckdb"), read_only=True)
    con.execute("LOAD delta")

    # Glossário: a mesma coluna em vários modelos herda a descrição de onde ela foi escrita.
    glossario = {}
    # Ordem fixa (por unique_id) para a página sair igual em toda execução.
    for _, no in sorted(list(manifest["nodes"].items()) + list(manifest["sources"].items())):
        for c, info in no.get("columns", {}).items():
            if info.get("description"):
                glossario.setdefault(c, info["description"])

    tabelas = {"Bronze": [], "Silver": [], "Gold": [], "Semântica": []}
    for s in manifest["sources"].values():
        if s["source_name"] == "auditoria":  # tabela de controle gravada pelo próprio dbt (selo do painel)
            tabelas["Semântica"].append({
                "nome": f"auditoria.{s['name']}", "descricao": s.get("description"), "grao": None,
                "colunas": s.get("columns", {}), "contrato": False,
                "tipos": dict(con.execute(
                    "select column_name, data_type from information_schema.columns "
                    "where table_schema = 'auditoria' and table_name = ? order by ordinal_position",
                    [s["name"]]).fetchall())})
            continue
        tabelas["Bronze"].append({
            "nome": f"bronze/{s['name']}", "descricao": s.get("description"), "grao": None,
            "colunas": s.get("columns", {}), "contrato": False,
            "tipos": {r[0]: r[1] for r in con.execute(
                f"DESCRIBE SELECT * FROM delta_scan('{LAKE}/bronze/{s['name']}')").fetchall()}})
    for no in manifest["nodes"].values():
        if no["resource_type"] not in ("model", "seed") or no["package_name"] != "ceap":
            continue
        camada = {"gold": "Gold", "semantico": "Semântica"}.get(no["schema"], "Silver")
        tipos = dict(con.execute(
            "select column_name, data_type from information_schema.columns "
            "where table_schema = ? and table_name = ? order by ordinal_position",
            [no["schema"], no["name"]]).fetchall())
        tabelas[camada].append({
            "nome": f"{no['schema']}.{no['name']}", "descricao": no.get("description"),
            "grao": no.get("meta", {}).get("grao") or no["config"].get("meta", {}).get("grao"),
            "colunas": no.get("columns", {}), "tipos": tipos,
            "contrato": no["config"].get("contract", {}).get("enforced", False),
            "seed": no["resource_type"] == "seed"})
    con.close()

    sem_descricao = []
    out = ["# Dicionário de dados", "",
           "> Página gerada por `scripts/gerar_dicionario.py`: os tipos vêm do banco gerado pelo pipeline e",
           "> as descrições, dos arquivos `.yml` do dbt (`dbt_ceap/models/**/_*.yml`). Para mudar uma",
           "> descrição, edite o `.yml` e rode o script de novo.", "",
           "O banco transacional da E1 (PostgreSQL) está descrito em [Modelo de dados](modelo-de-dados.md).",
           "A camada analítica tem quatro camadas (Bronze, Silver e Gold da E3; Semântica da E4):", "",
           "| Camada | Conteúdo | Tabelas |", "| :--- | :--- | ---: |"]
    out += [f"| [{c}](#{c.lower()}) | {d} | {len(tabelas[c])} |" for c, d in CAMADAS]
    out += ["", "Legenda: 🔒 contrato de esquema (`contract: enforced`): o build reprova se a coluna "
            "sumir ou mudar de tipo · 👤 dado pessoal (LGPD).", ""]

    for camada, _ in CAMADAS:
        out += [f"## {camada}", ""]
        for t in sorted(tabelas[camada], key=lambda x: (x.get("seed", False), x["nome"])):
            titulo = f"### `{t['nome']}`" + (" 🔒" if t["contrato"] else "") + (" (seed)" if t.get("seed") else "")
            out += [titulo, ""]
            if t["descricao"]:
                out += [_primeira_frase(t["descricao"]), ""]
            if t["grao"] and "Grão" not in (t["descricao"] or ""):
                out += [f"**Grão:** {t['grao']}", ""]
            out += ["| Coluna | Tipo | Descrição |", "| :--- | :--- | :--- |"]
            for col, tipo in t["tipos"].items():
                desc = (t["colunas"].get(col, {}) or {}).get("description") or glossario.get(col)
                if not desc:
                    sem_descricao.append(f"{t['nome']}.{col}")
                    desc = "—"
                marca = " 👤" if col in PESSOAL else ""
                obs = f" *({PESSOAL[col]})*" if col in PESSOAL else ""
                if camada == "Semântica" and col in ("documento_fornecedor", "nome_fornecedor"):
                    marca, obs = " 👤", " *(CPF de pessoa física mascarado: `***.456.789-**`)*"
                out.append(f"| `{col}`{marca} | `{tipo}` | {' '.join(desc.split())}{obs} |")
            out.append("")

    if sem_descricao:
        print("Colunas sem descrição:", *sem_descricao, sep="\n  ")
        sys.exit(1)
    SAIDA.write_text("\n".join(out), encoding="utf-8")
    total = sum(len(t["tipos"]) for v in tabelas.values() for t in v)
    print(f"{SAIDA}: {sum(len(v) for v in tabelas.values())} tabelas, {total} colunas, todas descritas")


if __name__ == "__main__":
    main()
