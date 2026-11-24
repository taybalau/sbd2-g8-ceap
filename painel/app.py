"""
Painel da E3 — responde à pergunta de gestão definida na E1, e só a ela:

  "Quais parlamentares e partidos da 57ª Legislatura (2023–2026) apresentam maior desvio
   de gastos acima da média mensal da CEAP, e quais categorias e fornecedores concentram
   esses recursos?"

"Média mensal" é medida pela MEDIANA do gasto mensal dos deputados da mesma UF (ADR-0005, 9.5):
poucos gastos individuais muito altos distorciam a média.

Três blocos, um por parte da pergunta. Lê somente a camada semântica (schema `semantico` do
lakehouse/ceap.duckdb, definida em dbt_ceap/models/semantic/) e não calcula nenhuma métrica: só
ordena, escolhe o que mostrar e formata. Consumo duplo (E4): o ETL reverso lê as mesmas views.
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

st.set_page_config(page_title="CEAP — Desvio de gastos", layout="wide")


@st.cache_data(ttl=300)
def carregar():
    con = duckdb.connect(str(BANCO), read_only=True)
    try:
        # só a camada semântica; cada view já traz as métricas prontas (ver _semantic.yml)
        dados = {
            "dep": con.execute("select * from semantico.met_parlamentar").df(),
            "par": con.execute("select * from semantico.met_partido").df(),
            "cat": con.execute("select * from semantico.met_categoria_parlamentar").df(),
            "forn": con.execute("select * from semantico.met_fornecedor_parlamentar").df(),
            "ctx": con.execute("select * from semantico.met_contexto").df().iloc[0],
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
    st.error(f"Não foi possível ler a camada semântica em {BANCO}. Rode o pipeline primeiro. ({e})")
    st.stop()

ctx = d["ctx"]
st.title("Quem gasta acima da mediana da CEAP — 57ª Legislatura")
st.caption(
    f"Comparação mês a mês com a **mediana** dos deputados da **mesma UF** (o teto da cota varia por estado). "
    f"A mediana é o valor do meio: metade dos deputados da UF gastou menos e metade gastou mais, então "
    f"poucos gastos muito altos não a distorcem. "
    f"Janela comparável: **{mes(ctx.janela_inicio)} a {mes(ctx.janela_fim)}** ({ctx.meses_janela} meses). "
    f"Dados da Câmara ingeridos em {pd.Timestamp(ctx.atualizado_em).strftime('%d/%m/%Y %H:%M')}.")
if not ctx.dentro_do_sla:
    st.warning(f"Dados com {ctx.idade_horas:.0f} h desde a última ingestão: acima do SLA de {ctx.sla_horas} h. "
               "A ingestão diária pode ter falhado; confira o Dagster.")
else:
    st.caption(f"Freshness: {ctx.idade_horas:.1f} h desde a última ingestão (SLA: até {ctx.sla_horas} h).")

with st.expander("Por que a janela termina antes de 2026?", expanded=False):
    st.markdown(
        f"- Os meses mais recentes ainda estão recebendo notas (dado atrasado). Só entram competências com "
        f"pelo menos 4 meses de maturação; a última publicada é {mes(ctx.ultima_competencia_publicada)}.\n"
        + (f"- **Ruptura de publicação:** a partir de {mes(ctx.ruptura_inicio)} a subcota "
           f"{int(ctx.ruptura_num_subcota)} — {ctx.ruptura_descricao}. {ctx.ruptura_evidencia} Incluir esses "
           f"meses compararia períodos com e sem passagens aéreas, então eles ficam fora do ranking até a "
           f"fonte ser corrigida." if pd.notna(ctx.ruptura_inicio) else ""))

# ------------------------------------------------------------ 1. parlamentares
dep = d["dep"].sort_values("posicao_ranking")
lider = dep.iloc[0]
st.header("1. Parlamentares com maior desvio acima da mediana")
st.markdown(
    f"**{lider.nome_parlamentar} ({lider.partido_atual}-{lider.sigla_uf})** lidera: gastou em média "
    f"**{brl(lider.gasto_medio_mensal)}/mês**, contra {brl(lider.mediana_uf_mensal)} da mediana da UF — "
    f"{lider.desvio_relativo:+.0%}, acumulando **{brl(lider.desvio_acumulado)}** acima da mediana "
    f"em {lider.meses_com_gasto} meses ({lider.meses_acima_mediana} deles acima).")
top = dep.head(15).assign(
    gm=lambda x: x.gasto_medio_mensal.map(brl), mu=lambda x: x.mediana_uf_mensal.map(brl),
    rel=lambda x: x.desvio_relativo.map(lambda v: f"{v:+.0%}"))
st.plotly_chart(barras_h(top, "desvio_acumulado", "rotulo", AZUL, {
    "cols": ["gm", "mu", "rel", "trajetoria_partidaria", "meses_acima_mediana"],
    "tpl": "<b>%{y}</b><br>Desvio acumulado: R$ %{x:,.0f}<br>Gasto médio: %{customdata[0]}/mês"
           "<br>Mediana da UF: %{customdata[1]}/mês (%{customdata[2]})"
           "<br>Partidos no período: %{customdata[3]}<br>Meses acima da mediana: %{customdata[4]}"},
    "Desvio acumulado acima da mediana da UF (R$)"), use_container_width=True)

# ------------------------------------------------------------ 2. partidos
st.header("2. Partidos com maior desvio")
par = d["par"].query("entra_no_ranking").sort_values("posicao_ranking")
p1 = par.iloc[0]
st.markdown(
    f"Por deputado-mês, **{p1.sigla_partido}** tem o maior desvio médio: "
    f"**{brl(p1.desvio_medio_por_deputado_mes)}** acima da mediana da UF "
    f"({int(p1.qtd_deputados)} deputados). O partido é o **da data do gasto** (histórico oficial da Câmara), "
    f"não o atual. Partidos com menos de {ctx.min_deputados_partido} deputados ficam fora do gráfico.")
par = par.assign(
    cor=lambda x: x.desvio_medio_por_deputado_mes.map(lambda v: LARANJA if v > 0 else AZUL),
    gt=lambda x: x.gasto_total.map(brl), da=lambda x: x.desvio_acumulado.map(brl))
fig = barras_h(par, "desvio_medio_por_deputado_mes", "sigla_partido", par["cor"], {
    "cols": ["qtd_deputados", "deputado_meses", "gt", "da"],
    "tpl": "<b>%{y}</b><br>Desvio médio: R$ %{x:,.0f} por deputado-mês<br>Deputados: %{customdata[0]}"
           " · deputado-meses: %{customdata[1]}<br>Gasto total: %{customdata[2]}<br>Desvio acumulado: %{customdata[3]}"},
    "Desvio médio por deputado-mês (R$) — laranja: acima da mediana · azul: abaixo")
st.plotly_chart(fig, use_container_width=True)

erro = d["par"].assign(erro_abs=lambda x: x.erro_gasto_se_sobrescrito.abs())  # só para ordenar
with st.expander(f"Quanto erraria quem usasse o partido atual: {brl(ctx.erro_total_sobrescrita)} "
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
cat = (d["cat"].query("id_deputado == @escolha[0]").sort_values("posicao_excesso")
       .rename(columns={"gasto_categoria": "gasto", "excesso_categoria_vs_uf": "excesso",
                        "participacao_categoria_no_deputado": "part"}))
c1 = cat.iloc[0]
st.markdown(
    f"A categoria que mais explica o desvio é **{c1.descricao_subcota.rstrip('.').capitalize()}**: "
    f"**{brl(c1.excesso)}** acima da mediana dos deputados da mesma UF nessa categoria "
    f"({c1.part:.0%} do gasto do parlamentar).")
col1, col2 = st.columns([3, 2])
with col1:
    cat = cat.assign(cor=lambda x: x.excesso.map(lambda v: LARANJA if v > 0 else AZUL),
                     g=lambda x: x.gasto.map(brl), p=lambda x: x.part.map(lambda v: f"{v:.0%}"))
    st.plotly_chart(barras_h(cat.head(10), "excesso", "descricao_subcota", cat.head(10)["cor"], {
        "cols": ["g", "p"],
        "tpl": "<b>%{y}</b><br>Acima da mediana da UF: R$ %{x:,.0f}<br>Gasto na categoria: %{customdata[0]}"
               " (%{customdata[1]} do total)"},
        "Gasto na categoria acima da mediana da UF (R$)"), use_container_width=True)
with col2:
    forn = (d["forn"].query("id_deputado == @escolha[0] and posicao_gasto <= 10").sort_values("posicao_gasto")
            .rename(columns={"gasto_fornecedor": "gasto", "participacao_no_deputado": "part",
                             "qtd_lancamentos": "notas"}))
    st.markdown(f"**{len(forn)} maiores fornecedores** — somam {forn.participacao_acumulada.iloc[-1]:.0%} do gasto")
    st.dataframe(
        forn[["nome_fornecedor", "documento_fornecedor", "gasto", "part", "notas"]].rename(columns={"nome_fornecedor": "Fornecedor", "documento_fornecedor": "CNPJ/CPF",
                             "gasto": "Gasto (R$)", "part": "Participação", "notas": "Lançamentos"}),
        hide_index=True, use_container_width=True,
        column_config={"Gasto (R$)": st.column_config.NumberColumn(format="%.0f"),
                       "Participação": st.column_config.NumberColumn(format="percent")})

with st.expander("Tabela completa do ranking"):
    st.dataframe(dep[["posicao_ranking", "nome_parlamentar", "sigla_uf", "trajetoria_partidaria",
                      "meses_com_gasto", "gasto_medio_mensal", "mediana_uf_mensal", "desvio_acumulado",
                      "desvio_relativo", "hhi_fornecedores"]],
                 hide_index=True, use_container_width=True)

st.caption("Camada semântica: semantico.met_parlamentar, met_partido, met_categoria_parlamentar, "
           "met_fornecedor_parlamentar e met_contexto. Definição de cada métrica: "
           "dbt_ceap/models/semantic/_semantic.yml. "
           "Desvio não é irregularidade: indica onde olhar primeiro.")
