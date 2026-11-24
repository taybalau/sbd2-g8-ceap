"""
Consumo duplo (E4): verifica que o painel mostra os mesmos números da camada semântica.

1. O código do painel não lê a Gold nem a Silver e não agrega nada (só a camada `semantico`).
2. Abre o painel sem navegador (streamlit AppTest) e confere, um a um, os números exibidos contra
   as views da camada: líder do ranking, partido do topo, erro da sobrescrita, categoria que mais
   explica o desvio e participação dos maiores fornecedores do parlamentar selecionado.

Sai com erro se algum número divergir. Uso (com o lakehouse gerado, dentro do container da E3):
    python scripts/verificar_consumo_duplo.py
"""
import os
import re
import sys
from pathlib import Path

import duckdb
from streamlit.testing.v1 import AppTest

RAIZ = Path(__file__).resolve().parents[1]
APP = RAIZ / "painel" / "app.py"
BANCO = Path(os.getenv("LAKEHOUSE_PATH", RAIZ / "lakehouse")) / "ceap.duckdb"


def brl(v):  # mesmo formato do painel
    return ("R$ " + f"{v:,.0f}").replace(",", "X").replace(".", ",").replace("X", ".")


falhas, ok = [], []


def conferir(nome, esperado, texto):
    (ok if esperado in texto else falhas).append(f"{nome}: esperado {esperado!r}")


codigo = APP.read_text()
proibidos = [p for p in (r"\bgold\.", r"\bsilver\.", r"\.groupby\(", r"\.agg\(", r"\.sum\(", r"\.mean\(")
             if re.search(p, codigo)]
(falhas if proibidos else ok).append(f"painel sem leitura da Gold/Silver e sem agregação: {proibidos or 'ok'}")

con = duckdb.connect(str(BANCO), read_only=True)
lider = con.execute("select rotulo, gasto_medio_mensal, mediana_uf_mensal, desvio_acumulado, meses_acima_mediana "
                    "from semantico.met_parlamentar where posicao_ranking = 1").fetchone()
partido = con.execute("select sigla_partido, desvio_medio_por_deputado_mes, qtd_deputados "
                      "from semantico.met_partido where posicao_ranking = 1").fetchone()
ctx = con.execute("select erro_total_sobrescrita, meses_janela from semantico.met_contexto").fetchone()
id_lider = con.execute("select id_deputado from semantico.met_parlamentar where posicao_ranking = 1").fetchone()[0]
cat = con.execute("select excesso_categoria_vs_uf, participacao_categoria_no_deputado from "
                  "semantico.met_categoria_parlamentar where id_deputado = ? order by posicao_excesso limit 1",
                  [id_lider]).fetchone()
forn = con.execute("select max(posicao_gasto), max(participacao_acumulada) from semantico.met_fornecedor_parlamentar "
                   "where id_deputado = ? and posicao_gasto <= 10", [id_lider]).fetchone()
con.close()

at = AppTest.from_file(str(APP), default_timeout=120).run()
if at.exception:
    print("o painel levantou exceção:", [e.value for e in at.exception])
    sys.exit(1)
tela = "\n".join([m.value for m in at.markdown] + [e.label for e in at.expander])

conferir("líder do ranking", f"**{lider[0]}** lidera", tela)
conferir("gasto médio do líder", f"**{brl(lider[1])}/mês**", tela)
conferir("mediana da UF do líder", f"contra {brl(lider[2])} da mediana", tela)
conferir("desvio acumulado do líder", f"**{brl(lider[3])}** acima da mediana", tela)
conferir("meses acima da mediana", f"({lider[4]} deles acima)", tela)
conferir("partido do topo", f"**{partido[0]}** tem o maior desvio médio: **{brl(partido[1])}**", tela)
conferir("deputados do partido do topo", f"({partido[2]} deputados)", tela)
conferir("erro total da sobrescrita", f"partido atual: {brl(ctx[0])} de gasto", tela)
conferir("categoria que explica o desvio", f"**{brl(cat[0])}** acima da mediana", tela)
conferir("peso da categoria", f"({cat[1]:.0%} do gasto do parlamentar)", tela)
conferir("maiores fornecedores", f"**{forn[0]} maiores fornecedores** — somam {forn[1]:.0%} do gasto", tela)

for linha in ok:
    print("✅", linha)
for linha in falhas:
    print("❌", linha)
print(f"{len(ok)} conferências iguais, {len(falhas)} divergentes")
sys.exit(1 if falhas else 0)
