"""
Gera o catálogo de métricas da camada semântica (E4) em docs/e4.md, entre os marcadores
<!-- catalogo-metricas:inicio --> e <!-- catalogo-metricas:fim -->.

A fonte é a definição versionada em dbt_ceap/models/semantic/_semantic.yml, lida do manifest.json
do dbt: toda coluna com meta.metrica entra, com descrição, fórmula e unidade; o grão, as dimensões
e os consumidores vêm do meta do modelo. Métrica sem fórmula ou sem descrição faz o script falhar.

Uso (depois de um `dbt build` ou `dbt parse`):
    python scripts/gerar_catalogo_metricas.py [pasta_target_do_dbt] [arquivo_e4]
"""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
TARGET = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "dbt_ceap" / "target"
SAIDA = Path(sys.argv[2]) if len(sys.argv) > 2 else RAIZ / "docs" / "e4.md"
INICIO, FIM = "<!-- catalogo-metricas:inicio -->", "<!-- catalogo-metricas:fim -->"


def main():
    manifest = json.loads((TARGET / "manifest.json").read_text())
    modelos = sorted((n for n in manifest["nodes"].values()
                      if n["resource_type"] == "model" and n["schema"] == "semantico"),
                     key=lambda n: n["original_file_path"])
    # ordem de leitura do painel: quem (parlamentar, mês a mês), partido, onde (categoria, fornecedor,
    # lançamento) e o contexto (janela, qualidade)
    ordem = ["met_parlamentar", "met_parlamentar_mes", "met_partido", "met_categoria_parlamentar",
             "met_fornecedor_parlamentar", "met_lancamento_parlamentar", "met_contexto", "met_qualidade_build"]
    modelos.sort(key=lambda n: ordem.index(n["name"]) if n["name"] in ordem else len(ordem))

    out, faltando, total = [INICIO, "",
                            "> Tabela gerada por `scripts/gerar_catalogo_metricas.py` a partir de",
                            "> `dbt_ceap/models/semantic/_semantic.yml`. Para mudar uma métrica, edite o `.yml`",
                            "> (e o `.sql` da view) e rode o script de novo.", ""], [], 0
    for n in modelos:
        meta = {**n["config"].get("meta", {}), **n.get("meta", {})}
        out += [f"#### `semantico.{n['name']}`", "",
                f"- **Grão:** {meta.get('grao', '—')}",
                f"- **Dimensões:** {', '.join(meta.get('dimensoes') or []) or '—'}",
                f"- **Quem consome:** {', '.join(meta.get('consumidores') or []) or '—'}",
                f"- **Definição:** [`{n['original_file_path'].split('/')[-1]}`]"
                f"(https://github.com/taybalau/sbd2-g8-ceap/blob/main/dbt_ceap/{n['original_file_path']})", "",
                "| Métrica | Descrição | Fórmula | Unidade |", "| :--- | :--- | :--- | :--- |"]
        for col, info in n["columns"].items():
            m = {**info.get("config", {}).get("meta", {}), **info.get("meta", {})}
            if not m.get("metrica"):
                continue
            if not m.get("formula") or not info.get("description"):
                faltando.append(f"{n['name']}.{col}")
            total += 1
            formula = m.get("formula", "—").replace("|", "\\|")
            out.append(f"| `{col}` | {' '.join(info.get('description', '').split())} | `{formula}` | "
                       f"{m.get('unidade', '—')} |")
        out.append("")
    out.append(FIM)

    if faltando:
        print("Métricas sem fórmula ou sem descrição:", *faltando, sep="\n  ")
        sys.exit(1)
    texto = SAIDA.read_text(encoding="utf-8")
    if INICIO not in texto or FIM not in texto:
        print(f"{SAIDA} não tem os marcadores {INICIO} / {FIM}")
        sys.exit(1)
    antes, resto = texto.split(INICIO, 1)
    depois = resto.split(FIM, 1)[1]
    SAIDA.write_text(antes + "\n".join(out) + depois, encoding="utf-8")
    print(f"{SAIDA}: {total} métricas em {len(modelos)} views da camada semântica")


if __name__ == "__main__":
    main()
