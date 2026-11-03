"""
Painel da E3 — responde à pergunta de gestão definida na E1, e só a ela:

  "Quais parlamentares e partidos da 57ª Legislatura (2023–2026) apresentam maior desvio
   de gastos acima da média mensal da CEAP, e quais categorias e fornecedores concentram
   esses recursos?"

Três blocos, um por parte da pergunta. Lê somente a camada Gold (lakehouse/ceap.duckdb).
Execução:  streamlit run painel/app.py
"""
import os
from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
BANCO = Path(os.getenv("LAKEHOUSE_PATH", RAIZ / "lakehouse")) / "ceap.duckdb"
AZUL, LARANJA = "#2a78d6", "#eb6834"          # paleta de referência (slots 1 e 2), validada
MIN_DEPUTADOS_PARTIDO = 5

st.set_page_config(page_title="CEAP — Desvio de gastos", layout="wide")


@st.cache_data(ttl=300)
def carregar():
    con = duckdb.connect(str(BANCO), read_only=True)
    try:
        dados = {
            "dep": con.execute("select * from gold.mart_desvio_parlamentar").df(),
            "par": con.execute("select * from gold.mart_desvio_partido").df(),
            "con": con.execute("select * from gold.mart_concentracao_parlamentar").df(),
            "janela": con.execute("""
                select min(competencia), max(competencia), count(distinct competencia)
                from gold.fct_gasto_mensal_parlamentar where is_competencia_comparavel""").fetchone(),
            "ultima_pub": con.execute("select max(competencia) from silver.fct_lancamento_ceap").fetchone()[0],
            # a primeira ruptura é a que encerra a janela comparável (ver dim_calendario)
            "ruptura": con.execute(
                "select * from silver.ruptura_publicacao order by competencia_inicio").df(),
            "atualizado": con.execute("select max(ingerido_em) from silver.fct_lancamento_ceap").fetchone()[0],
        }
    finally:
        con.close()
    return dados


def brl(v: float) -> str:
    return ("R$ " + f"{v:,.0f}").replace(",", "X").replace(".", ",").replace("X", ".")


def mes(d) -> str:
    return pd.Timestamp(d).strftime("%m/%Y")


def barras_h(df, x, y, cor, hover, titulo_x):
    fig = go.Figure(go.Bar(
        x=df[x], y=df[y], orientation="h", marker_color=cor, marker_line_width=0,
        customdata=df[hover["cols"]], hovertemplate=hover["tpl"] + "<extra></extra>"))
    fig.update_layout(
        height=max(260, 28 * len(df) + 60), margin=dict(l=8, r=8, t=8, b=36),
        bargap=0.25, xaxis_title=titulo_x, yaxis=dict(autorange="reversed"),
        xaxis=dict(zeroline=True, zerolinewidth=1, gridcolor="rgba(128,128,128,0.15)"))
    return fig


try:
    d = carregar()
except duckdb.Error as e:
    st.error(f"Não foi possível ler a camada Gold em {BANCO}. Rode o pipeline primeiro. ({e})")
    st.stop()

ini, fim, n_meses = d["janela"]
st.title("Quem gasta acima da média da CEAP — 57ª Legislatura")
st.caption(
    f"Comparação mês a mês com a média dos deputados da **mesma UF** (o teto da cota varia por estado). "
    f"Janela comparável: **{mes(ini)} a {mes(fim)}** ({n_meses} meses). "
    f"Dados da Câmara ingeridos em {pd.Timestamp(d['atualizado']).strftime('%d/%m/%Y %H:%M')}.")

with st.expander("Por que a janela termina antes de 2026?", expanded=False):
    rup = d["ruptura"].iloc[0] if len(d["ruptura"]) else None
    st.markdown(
        f"- Os meses mais recentes ainda estão recebendo notas (dado atrasado). Só entram competências com "
        f"pelo menos 4 meses de maturação; a última publicada é {mes(d['ultima_pub'])}.\n"
        + (f"- **Ruptura de publicação:** a partir de {mes(rup.competencia_inicio)} a subcota {rup.num_subcota} "
           f"— {rup.descricao}. {rup.evidencia} Incluir esses meses compararia períodos com e sem passagens "
           f"aéreas, então eles ficam fora do ranking até a fonte ser corrigida." if rup is not None else ""))

# ------------------------------------------------------------ 1. parlamentares
dep = d["dep"].sort_values("posicao_ranking")
lider = dep.iloc[0]
st.header("1. Parlamentares com maior desvio acima da média")
st.markdown(
    f"**{lider.nome_parlamentar} ({lider.partido_atual}-{lider.sigla_uf})** lidera: gastou em média "
    f"**{brl(lider.gasto_medio_mensal)}/mês**, contra {brl(lider.media_uf_mensal)} da média da UF — "
    f"{lider.desvio_relativo:+.0%}, acumulando **{brl(lider.desvio_acumulado)}** acima da média "
    f"em {lider.meses_com_gasto} meses ({lider.meses_acima_media} deles acima).")
top = dep.head(15).assign(
    rotulo=lambda x: x.nome_parlamentar + " (" + x.partido_atual.fillna("—") + "-" + x.sigla_uf + ")",
    gm=lambda x: x.gasto_medio_mensal.map(brl), mu=lambda x: x.media_uf_mensal.map(brl),
    rel=lambda x: x.desvio_relativo.map(lambda v: f"{v:+.0%}"))
st.plotly_chart(barras_h(top, "desvio_acumulado", "rotulo", AZUL, {
    "cols": ["gm", "mu", "rel", "trajetoria_partidaria", "meses_acima_media"],
    "tpl": "<b>%{y}</b><br>Desvio acumulado: R$ %{x:,.0f}<br>Gasto médio: %{customdata[0]}/mês"
           "<br>Média da UF: %{customdata[1]}/mês (%{customdata[2]})"
           "<br>Partidos no período: %{customdata[3]}<br>Meses acima da média: %{customdata[4]}"},
    "Desvio acumulado acima da média da UF (R$)"), use_container_width=True)

# ------------------------------------------------------------ 2. partidos
st.header("2. Partidos com maior desvio")
par = d["par"].query("qtd_deputados >= @MIN_DEPUTADOS_PARTIDO").sort_values(
    "desvio_medio_por_deputado_mes", ascending=False)
p1 = par.iloc[0]
st.markdown(
    f"Por deputado-mês, **{p1.sigla_partido}** tem o maior desvio médio: "
    f"**{brl(p1.desvio_medio_por_deputado_mes)}** acima da média da UF "
    f"({int(p1.qtd_deputados)} deputados). O partido é o **da data do gasto** (histórico oficial da Câmara), "
    f"não o atual. Partidos com menos de {MIN_DEPUTADOS_PARTIDO} deputados ficam fora do gráfico.")
par = par.assign(
    cor=lambda x: x.desvio_medio_por_deputado_mes.map(lambda v: LARANJA if v > 0 else AZUL),
    gt=lambda x: x.gasto_total.map(brl), da=lambda x: x.desvio_acumulado.map(brl))
fig = barras_h(par, "desvio_medio_por_deputado_mes", "sigla_partido", par["cor"], {
    "cols": ["qtd_deputados", "deputado_meses", "gt", "da"],
    "tpl": "<b>%{y}</b><br>Desvio médio: R$ %{x:,.0f} por deputado-mês<br>Deputados: %{customdata[0]}"
           " · deputado-meses: %{customdata[1]}<br>Gasto total: %{customdata[2]}<br>Desvio acumulado: %{customdata[3]}"},
    "Desvio médio por deputado-mês (R$) — laranja: acima da média · azul: abaixo")
st.plotly_chart(fig, use_container_width=True)

erro = d["par"].assign(erro_abs=lambda x: x.erro_gasto_se_sobrescrito.abs())
with st.expander(f"Quanto erraria quem usasse o partido atual: {brl(erro.erro_abs.sum() / 2)} "
                 "de gasto no partido errado"):
    st.markdown(
        "O CSV da CEAP regrava o partido de todos os lançamentos com o partido **atual** do deputado. "
        "Esta tabela mostra, por partido, a diferença entre o gasto correto (partido na data do gasto) "
        "e o que se obteria com a sobrescrita.")
    st.dataframe(
        erro.sort_values("erro_abs", ascending=False)[
            ["sigla_partido", "gasto_total", "gasto_total_se_sobrescrito", "erro_gasto_se_sobrescrito"]
        ].rename(columns={"sigla_partido": "Partido", "gasto_total": "Gasto correto (R$)",
                          "gasto_total_se_sobrescrito": "Se sobrescrito (R$)",
                          "erro_gasto_se_sobrescrito": "Erro (R$)"}),
        hide_index=True, use_container_width=True,
        column_config={c: st.column_config.NumberColumn(format="%.0f")
                       for c in ["Gasto correto (R$)", "Se sobrescrito (R$)", "Erro (R$)"]})

# ------------------------------------------------------------ 3. concentração
st.header("3. Onde está o dinheiro: categorias e fornecedores")
opcoes = top[["id_deputado", "rotulo"]].values.tolist()
escolha = st.selectbox("Parlamentar (top 15 do ranking)", opcoes, format_func=lambda o: o[1])
conc = d["con"].query("id_deputado == @escolha[0]")

cat = (conc.groupby(["descricao_subcota"], as_index=False)
       .agg(gasto=("gasto_fornecedor", "sum"), excesso=("excesso_categoria_vs_uf", "first"),
            part=("participacao_categoria_no_deputado", "first"))
       .sort_values("excesso", ascending=False))
c1 = cat.iloc[0]
st.markdown(
    f"A categoria que mais explica o desvio é **{c1.descricao_subcota.rstrip('.').capitalize()}**: "
    f"**{brl(c1.excesso)}** acima do que gastou, em média, um deputado da mesma UF "
    f"({c1.part:.0%} do gasto do parlamentar).")
col1, col2 = st.columns([3, 2])
with col1:
    cat = cat.assign(cor=lambda x: x.excesso.map(lambda v: LARANJA if v > 0 else AZUL),
                     g=lambda x: x.gasto.map(brl), p=lambda x: x.part.map(lambda v: f"{v:.0%}"))
    st.plotly_chart(barras_h(cat.head(10), "excesso", "descricao_subcota", cat.head(10)["cor"], {
        "cols": ["g", "p"],
        "tpl": "<b>%{y}</b><br>Acima da média da UF: R$ %{x:,.0f}<br>Gasto na categoria: %{customdata[0]}"
               " (%{customdata[1]} do total)"},
        "Gasto na categoria acima da média da UF (R$)"), use_container_width=True)
with col2:
    forn = (conc.groupby(["nome_fornecedor", "documento_fornecedor"], as_index=False, dropna=False)
            .agg(gasto=("gasto_fornecedor", "sum"), part=("participacao_no_deputado", "sum"),
                 notas=("qtd_lancamentos", "sum"))
            .sort_values("gasto", ascending=False).head(10))
    st.markdown(f"**10 maiores fornecedores** — somam {forn.part.sum():.0%} do gasto")
    st.dataframe(
        forn.rename(columns={"nome_fornecedor": "Fornecedor", "documento_fornecedor": "CNPJ/CPF",
                             "gasto": "Gasto (R$)", "part": "Participação", "notas": "Lançamentos"}),
        hide_index=True, use_container_width=True,
        column_config={"Gasto (R$)": st.column_config.NumberColumn(format="%.0f"),
                       "Participação": st.column_config.NumberColumn(format="percent")})

with st.expander("Tabela completa do ranking"):
    st.dataframe(dep[["posicao_ranking", "nome_parlamentar", "sigla_uf", "trajetoria_partidaria",
                      "meses_com_gasto", "gasto_medio_mensal", "media_uf_mensal", "desvio_acumulado",
                      "desvio_relativo", "hhi_fornecedores"]],
                 hide_index=True, use_container_width=True)

st.caption("Gold: gold.mart_desvio_parlamentar, gold.mart_desvio_partido, gold.mart_concentracao_parlamentar. "
           "Grão e testes de cada tabela: dbt_ceap/models/gestao/_gestao.yml. "
           "Desvio não é irregularidade: indica onde olhar primeiro.")
