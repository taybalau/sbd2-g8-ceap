"""
Consumo duplo (E4): verifica que o painel mostra os mesmos números da camada semântica.

1. O código do painel não lê a Gold nem a Silver e não agrega nada (só a camada `semantico`).
2. Abre o painel sem navegador (streamlit AppTest) e confere, um a um, os números exibidos contra
   as views da camada: líder do ranking, partido do topo, erro da sobrescrita, categoria que mais
   explica o desvio e participação dos maiores fornecedores do parlamentar selecionado.
3. Confere os elementos que mostram o levantamento: selo de qualidade (último build), tabela dos 15
   em alerta, série mensal do parlamentar, maiores lançamentos com o link do documento, nenhum CPF
   completo em nenhuma tabela da tela, e o filtro por UF (posição nacional preservada).

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


def brl(v):  # mesmo formato do painel, com o cifrão escapado como no markdown da tela
    return ("R\\$ " + f"{v:,.0f}").replace(",", "X").replace(".", ",").replace("X", ".")


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
qual = con.execute("select testes_total, testes_aprovados, testes_reprovados from semantico.met_qualidade_build").fetchone()
alerta = {r[0] for r in con.execute("select id_deputado from semantico.met_parlamentar where em_alerta").fetchall()}
num_cat = con.execute("select num_subcota from semantico.met_categoria_parlamentar where id_deputado = ? "
                      "order by posicao_excesso limit 1", [id_lider]).fetchone()[0]
lanc1 = con.execute("select valor_liquido, url_documento from semantico.met_lancamento_parlamentar "
                    "where id_deputado = ? and num_subcota = ? and posicao_valor = 1", [id_lider, num_cat]).fetchone()
uf_teste, rotulo_uf, pos_uf = con.execute(
    "select sigla_uf, arg_min(rotulo, posicao_ranking), min(posicao_ranking) from semantico.met_parlamentar "
    "where sigla_uf = 'DF' group by 1").fetchone()
con.close()

at = AppTest.from_file(str(APP), default_timeout=120).run()
if at.exception:
    print("o painel levantou exceção:", [e.value for e in at.exception])
    sys.exit(1)
tela = "\n".join([m.value for m in at.markdown] + [e.label for e in at.expander]
                 + [m.value for m in at.success] + [m.value for m in at.error])

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

# ---------------------------------------------------------------- elementos do levantamento
if qual:
    conferir("selo de qualidade", f"**{qual[0]} testes de dados** no build", tela)
    conferir("testes aprovados no selo", f"{qual[1]} aprovados", tela)
else:
    falhas.append("selo de qualidade: met_qualidade_build vazia (nenhum build registrado)")
conferir("série mensal do líder", f"Acima da mediana em **{lider[4]} de ", tela)
detalhe = at.dataframe[0].value
(ok if set(detalhe["posicao_ranking"]) == set(range(1, len(alerta) + 1)) and len(detalhe) == len(alerta)
 else falhas).append(f"tabela de detalhe: os {len(alerta)} em alerta, mesmas posições da camada")
lanc = next(df.value for df in at.dataframe if "url_documento" in df.value.columns)
link_tela = lanc["url_documento"].iloc[0]
mesmo_link = (link_tela is None or link_tela != link_tela) if lanc1[1] is None else link_tela == lanc1[1]
(ok if abs(float(lanc["valor_liquido"].iloc[0]) - float(lanc1[0])) < 0.01 and mesmo_link
 else falhas).append(f"maior lançamento da categoria do líder: R$ {lanc1[0]} com o mesmo link ({lanc1[1] or 'sem link'})")
pf_com_link = lanc[lanc["documento_fornecedor"].astype(str).str.startswith("***") & lanc["url_documento"].notna()]
(falhas if len(pf_com_link) else ok).append("nenhum link de documento de pessoa física na tela")
cpf = re.compile(r"(^|[^0-9])[0-9]{3}[.]?[0-9]{3}[.]?[0-9]{3}-?[0-9]{2}([^0-9]|$)")
expostos = [v for df in at.dataframe for v in df.value.astype(str).to_numpy().ravel() if cpf.search(v)]
(falhas if expostos else ok).append(f"nenhum CPF completo nas tabelas da tela: {expostos[:3] or 'ok'}")

at.multiselect[0].select(uf_teste).run()
tela_uf = "\n".join(m.value for m in at.markdown)
conferir(f"filtro por UF ({uf_teste}): líder da UF com a posição nacional",
         f"**{rotulo_uf}** lidera com esses filtros (posição {pos_uf} no país)", tela_uf)
(falhas if at.exception else ok).append("painel filtrado sem exceção")

for linha in ok:
    print("✅", linha)
for linha in falhas:
    print("❌", linha)
print(f"{len(ok)} conferências iguais, {len(falhas)} divergentes")
sys.exit(1 if falhas else 0)
