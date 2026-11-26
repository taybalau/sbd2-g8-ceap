"""
Painel da E3 — responde à pergunta de gestão definida na E1, e só a ela:

  "Quais parlamentares e partidos da 57ª Legislatura (2023–2026) apresentam maior desvio
   de gastos acima da média mensal da CEAP, e quais categorias e fornecedores concentram
   esses recursos?"

"Média mensal" é medida pela MEDIANA do gasto mensal dos deputados da mesma UF (ADR-0005, 9.5):
poucos gastos individuais muito altos distorciam a média.

Três blocos, um por parte da pergunta, em três passos: QUEM gasta acima (ranking), QUANDO (série
mensal: desvio constante ou pico) e COM QUE PROVA (o lançamento e o documento na Câmara).
Lê somente a camada semântica (schema `semantico` do lakehouse/ceap.duckdb, definida em
dbt_ceap/models/semantic/) e não calcula nenhuma métrica: só filtra, ordena, escolhe o que mostrar
e formata. Consumo duplo (E4): o ETL reverso lê as mesmas views.
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
CINZA = "rgba(128,128,128,0.45)"
SITE = "https://taybalau.github.io/sbd2-g8-ceap"
# Faixas usuais do HHI (0–1): abaixo de 0,15 pouco concentrado; acima de 0,25 muito concentrado
HHI_MODERADO, HHI_ALTO = 0.15, 0.25

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
            "mes": con.execute("select * from semantico.met_parlamentar_mes").df(),
            "ctx": con.execute("select * from semantico.met_contexto").df().iloc[0],
            "qual": con.execute("select * from semantico.met_qualidade_build").df(),
        }
    finally:
        con.close()
    return dados


@st.cache_data(ttl=300)
def lancamentos(id_deputado: int, num_subcota: int, limite: int = 15):
    """Maiores lançamentos de um parlamentar numa categoria. Filtra na consulta: a view é grande."""
    con = duckdb.connect(str(BANCO), read_only=True)
    try:
        return con.execute(
            "select * from semantico.met_lancamento_parlamentar "
            "where id_deputado = ? and num_subcota = ? and posicao_valor <= ? order by posicao_valor",
            [id_deputado, num_subcota, limite]).df()
    finally:
        con.close()


def brl(v: float) -> str:
    return ("R$ " + f"{v:,.0f}").replace(",", "X").replace(".", ",").replace("X", ".")


def md(texto: str) -> str:
    """Escapa o cifrão: no markdown do Streamlit, dois "R$" na mesma frase viram fórmula LaTeX."""
    return texto.replace("$", "\\$")


def mes(d) -> str:
    return pd.Timestamp(d).strftime("%m/%Y")


def faixa_hhi(h) -> str:
    if pd.isna(h):
        return "—"
    return "alta" if h > HHI_ALTO else "moderada" if h >= HHI_MODERADO else "baixa"


def csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")   # abre direto no Excel


def eixos(fig, altura, titulo_x=None, titulo_y=None):
    fig.update_layout(
        height=altura, margin=dict(l=8, r=8, t=8, b=36), xaxis_title=titulo_x, yaxis_title=titulo_y,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
        xaxis=dict(gridcolor="rgba(128,128,128,0.15)"), yaxis=dict(gridcolor="rgba(128,128,128,0.15)"))
    return fig


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

# ------------------------------------------------------------ selo de qualidade e freshness
if not d["qual"].empty:
    q = d["qual"].iloc[0]
    quando = pd.Timestamp(q.executado_em).tz_convert("America/Sao_Paulo").strftime("%d/%m/%Y %H:%M")
    texto = (f"**{q.testes_total} testes de dados** no build de {quando}: {q.testes_aprovados} aprovados, "
             f"{q.testes_aviso} com aviso, {q.testes_reprovados} reprovados. "
             f"[O que cada teste verifica]({SITE}/testes/)")
    if q.build_sem_falhas:
        st.success("Dados validados. " + texto, icon=":material/verified:")
    else:
        st.error(f"O último build teve falhas ({q.modelos_com_erro} modelos com erro). " + texto
                 + " Os números abaixo podem estar desatualizados.", icon=":material/error:")
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

# ------------------------------------------------------------ filtros (blocos 1 e 3)
dep = d["dep"].sort_values("posicao_ranking")
with st.sidebar:
    st.header("Filtros")
    ufs = st.multiselect("UF", sorted(dep.sigla_uf.unique()), placeholder="Todas")
    partidos = st.multiselect("Partido atual", sorted(dep.partido_atual.dropna().unique()), placeholder="Todos")
    st.caption("Valem para os blocos 1 e 3. A posição é sempre a do ranking nacional, e o alerta é o "
               f"top {len(dep.query('em_alerta'))} nacional, o mesmo da fila do auditor. "
               "O bloco 2 usa o partido da data do gasto e não é filtrado.")
filtrado = bool(ufs or partidos)
vis = dep[(dep.sigla_uf.isin(ufs) | (not ufs)) & (dep.partido_atual.isin(partidos) | (not partidos))]
if vis.empty:
    st.warning("Nenhum parlamentar com esses filtros.")
    st.stop()

# ------------------------------------------------------------ 1. parlamentares
lider = vis.iloc[0]
st.header("1. Parlamentares com maior desvio acima da mediana")
st.markdown(md(
    f"**{lider.rotulo}** "
    f"lidera{' com esses filtros (posição ' + str(lider.posicao_ranking) + ' no país)' if filtrado else ''}: "
    f"gastou em média **{brl(lider.gasto_medio_mensal)}/mês**, contra {brl(lider.mediana_uf_mensal)} da "
    f"mediana da UF — {lider.desvio_relativo:+.0%}, acumulando **{brl(lider.desvio_acumulado)}** acima da "
    f"mediana em {lider.meses_com_gasto} meses ({lider.meses_acima_mediana} deles acima)."))
# sem filtro, o topo é exatamente o conjunto em alerta (o mesmo da fila do auditor)
top = (vis.head(15) if filtrado else vis.query("em_alerta")).assign(
    gm=lambda x: x.gasto_medio_mensal.map(brl), mu=lambda x: x.mediana_uf_mensal.map(brl),
    rel=lambda x: x.desvio_relativo.map(lambda v: f"{v:+.0%}"),
    acima=lambda x: x.meses_acima_mediana.astype(str) + " de " + x.meses_com_gasto.astype(str),
    cor=lambda x: x.em_alerta.map(lambda a: AZUL if a else CINZA))
st.plotly_chart(barras_h(top, "desvio_acumulado", "rotulo", top["cor"], {
    "cols": ["gm", "mu", "rel", "trajetoria_partidaria", "acima", "posicao_ranking"],
    "tpl": "<b>%{y}</b> · %{customdata[5]}º no país<br>Desvio acumulado: R$ %{x:,.0f}"
           "<br>Gasto médio: %{customdata[0]}/mês<br>Mediana da UF: %{customdata[1]}/mês (%{customdata[2]})"
           "<br>Partidos no período: %{customdata[3]}<br>Meses acima da mediana: %{customdata[4]}"},
    "Desvio acumulado acima da mediana da UF (R$)" + (" — azul: em alerta (top 15 nacional)" if filtrado else "")),
    use_container_width=True)

# participação dos 3 maiores fornecedores: a view já traz o acumulado; o painel lê a linha da posição 3
tres = (d["forn"].query("posicao_gasto == 3")[["id_deputado", "participacao_acumulada"]]
        .rename(columns={"participacao_acumulada": "tres_maiores"}))
detalhe = top.merge(tres, on="id_deputado", how="left").assign(
    nome=lambda x: x.rotulo + x.trocou_de_partido.map(lambda t: " 🔀" if t else ""),
    hhi=lambda x: x.hhi_fornecedores.map(faixa_hhi))
st.markdown(f"**{'Os ' + str(len(detalhe)) + ' em detalhe' if filtrado else 'Os 15 em alerta, em detalhe'}** — "
            "🔀 trocou de partido na legislatura (a coluna Partidos mostra a trajetória, pela data do gasto)")
st.dataframe(
    detalhe.assign(pct_meses=lambda x: x.proporcao_meses_acima * 100, pct_tres=lambda x: x.tres_maiores * 100)[
        ["posicao_ranking", "nome", "desvio_acumulado", "pct_meses", "z_medio", "pct_tres", "hhi",
         "trajetoria_partidaria"]],
    hide_index=True, use_container_width=True, height=36 * (len(detalhe) + 1) + 3,
    column_config={
        "posicao_ranking": st.column_config.NumberColumn("Pos.", format="%dº", width="small"),
        "nome": st.column_config.TextColumn("Parlamentar", width="medium"),
        "desvio_acumulado": st.column_config.NumberColumn("Desvio (R$)", format="%.0f"),
        "pct_meses": st.column_config.ProgressColumn(
            "Meses acima", min_value=0, max_value=100, format="%.0f%%",
            help="Perto de 100%: gasta acima quase todo mês. Baixo com desvio alto: poucos meses fora da curva."),
        "z_medio": st.column_config.NumberColumn(
            "z robusto", format="%.2f", width="small",
            help="Quantos desvios típicos acima do padrão da UF, em média. Compara deputados de UFs diferentes."),
        "pct_tres": st.column_config.ProgressColumn(
            "3 maiores fornec.", min_value=0, max_value=100, format="%.0f%%",
            help="Parte do gasto do parlamentar que foi para os 3 fornecedores que mais receberam dele."),
        "hhi": st.column_config.TextColumn(
            "Concentração", width="small",
            help="Índice HHI dos fornecedores: baixa (< 0,15), moderada ou alta (> 0,25)."),
        "trajetoria_partidaria": st.column_config.TextColumn("Partidos", width="small"),
    })

st.subheader("Desvio constante ou pontual?")
st.markdown(
    "Cada ponto é um deputado. **À direita**, quem gasta acima da mediana da UF quase todo mês (desvio "
    "constante); **à esquerda com desvio alto**, quem acumulou o desvio em poucos meses fora da curva. Os dois "
    "pedem perguntas diferentes ao auditor: um padrão de gasto ou alguns meses específicos.")
fig = go.Figure()
for em_alerta, nome, cor, tam in [(False, "Demais deputados", CINZA, 6), (True, "Em alerta (top 15 nacional)", AZUL, 10)]:
    g = vis[vis.em_alerta == em_alerta]
    fig.add_trace(go.Scatter(
        x=g.proporcao_meses_acima, y=g.desvio_acumulado, mode="markers", name=nome,
        marker=dict(color=cor, size=tam, line_width=0),
        customdata=g[["rotulo", "posicao_ranking", "meses_acima_mediana", "meses_com_gasto"]],
        hovertemplate="<b>%{customdata[0]}</b> · %{customdata[1]}º<br>Desvio acumulado: R$ %{y:,.0f}"
                      "<br>Acima da mediana em %{customdata[2]} de %{customdata[3]} meses<extra></extra>"))
fig.add_vline(x=0.5, line_dash="dot", line_color="gray", annotation_text="metade dos meses",
              annotation_position="top")
fig.add_hline(y=0, line_color="gray", line_width=1)
eixos(fig, 420, "Fração dos meses acima da mediana da UF", "Desvio acumulado (R$)")
fig.update_xaxes(tickformat=".0%", range=[-0.02, 1.02])
st.plotly_chart(fig, use_container_width=True)

st.download_button(
    "Baixar o ranking (CSV)" + (" com os filtros" if filtrado else ""),
    csv(vis[["posicao_ranking", "nome_parlamentar", "partido_atual", "sigla_uf", "trajetoria_partidaria",
             "meses_com_gasto", "meses_acima_mediana", "gasto_total", "gasto_medio_mensal", "mediana_uf_mensal",
             "desvio_acumulado", "desvio_relativo", "z_medio", "hhi_fornecedores", "em_alerta"]]),
    "ranking_desvio_ceap.csv", "text/csv")

# ------------------------------------------------------------ 2. partidos
st.header("2. Partidos com maior desvio")
par = d["par"].query("entra_no_ranking").sort_values("posicao_ranking")
p1 = par.iloc[0]
st.markdown(md(
    f"Por deputado-mês, **{p1.sigla_partido}** tem o maior desvio médio: "
    f"**{brl(p1.desvio_medio_por_deputado_mes)}** acima da mediana da UF "
    f"({int(p1.qtd_deputados)} deputados). O partido é o **da data do gasto** (histórico oficial da Câmara), "
    f"não o atual. Partidos com menos de {ctx.min_deputados_partido} deputados ficam fora do gráfico."))
par = par.assign(
    cor=lambda x: x.desvio_medio_por_deputado_mes.map(lambda v: LARANJA if v > 0 else AZUL),
    gt=lambda x: x.gasto_total.map(brl), da=lambda x: x.desvio_acumulado.map(brl))
fig = barras_h(par, "desvio_medio_por_deputado_mes", "sigla_partido", par["cor"], {
    "cols": ["qtd_deputados", "deputado_meses", "gt", "da"],
    "tpl": "<b>%{y}</b><br>Desvio médio: R$ %{x:,.0f} por deputado-mês<br>Deputados: %{customdata[0]}"
           " · deputado-meses: %{customdata[1]}<br>Gasto total: %{customdata[2]}<br>Desvio acumulado: %{customdata[3]}"},
    "Desvio médio por deputado-mês (R$) — laranja: acima da mediana · azul: abaixo")
st.plotly_chart(fig, use_container_width=True)

st.subheader("Por que o partido da data do gasto importa")
col_m, col_t = st.columns([1, 2])
with col_m:
    st.metric("Gasto que iria para o partido errado", brl(ctx.erro_total_sobrescrita))
    st.markdown(md(
        f"Quanto erraria quem usasse o partido atual: {brl(ctx.erro_total_sobrescrita)} de gasto no partido "
        "errado. O CSV da CEAP regrava o partido de todos os lançamentos com o partido **atual** do deputado; "
        "o painel usa o histórico oficial da Câmara (SCD tipo 2) para atribuir cada gasto ao partido da época."))
with col_t:
    erro = d["par"].assign(erro_abs=lambda x: x.erro_gasto_se_sobrescrito.abs())  # só para ordenar
    st.dataframe(
        erro.sort_values("erro_abs", ascending=False).head(10)[
            ["sigla_partido", "gasto_total", "gasto_total_se_sobrescrito", "erro_gasto_se_sobrescrito"]
        ].rename(columns={"sigla_partido": "Partido", "gasto_total": "Gasto correto (R$)",
                          "gasto_total_se_sobrescrito": "Se sobrescrito (R$)",
                          "erro_gasto_se_sobrescrito": "Erro (R$)"}),
        hide_index=True, use_container_width=True,
        column_config={c: st.column_config.NumberColumn(format="%.0f")
                       for c in ["Gasto correto (R$)", "Se sobrescrito (R$)", "Erro (R$)"]})
    st.caption("Os 10 partidos com maior erro. Positivo: o partido ganharia gasto que não é dele; negativo: perderia.")

# ------------------------------------------------------------ 3. concentração
st.header("3. Onde está o dinheiro: categorias e fornecedores")
rotulos = dict(zip(top.id_deputado, top.rotulo))
id_sel = st.selectbox(
    f"Parlamentar ({'top ' + str(len(top)) + ' com os filtros' if filtrado else 'top ' + str(len(top)) + ' do ranking, em alerta'})",
    list(rotulos), format_func=rotulos.get)
sel = dep.query("id_deputado == @id_sel").iloc[0]

# QUANDO: a série mensal do parlamentar contra a mediana da UF
serie = d["mes"].query("id_deputado == @id_sel").sort_values("competencia")
st.subheader("Mês a mês contra a mediana da UF")
st.markdown(
    f"Acima da mediana em **{sel.meses_acima_mediana} de {sel.meses_com_gasto} meses** "
    f"({sel.proporcao_meses_acima:.0%}). "
    + ("Desvio **constante**: o gasto fica acima do padrão da UF na maior parte do período."
       if sel.proporcao_meses_acima >= 0.75 else
       "Desvio **concentrado**: poucos meses explicam boa parte do acumulado; vale olhar esses meses primeiro."
       if sel.proporcao_meses_acima < 0.5 else
       "Desvio **frequente**, mas não em todos os meses."))
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=serie.competencia, y=serie.mediana_uf_mes, name=f"Mediana dos deputados de {sel.sigla_uf}",
    mode="lines", line=dict(color=CINZA, width=2, dash="dash"),
    hovertemplate="%{x|%m/%Y}<br>Mediana da UF: R$ %{y:,.0f}<extra></extra>"))
fig.add_trace(go.Scatter(
    x=serie.competencia, y=serie.gasto_mes, name=sel.nome_parlamentar, mode="lines+markers",
    line=dict(color=AZUL, width=2),
    marker=dict(size=8, color=serie.acima_mediana.map(lambda a: LARANJA if a else AZUL), line_width=0),
    customdata=serie[["desvio_mes", "partidos_no_mes", "qtd_deputados_uf_mes"]],
    hovertemplate="%{x|%m/%Y} · %{customdata[1]}<br>Gasto: R$ %{y:,.0f}<br>Desvio: R$ %{customdata[0]:,.0f}"
                  "<br>Mediana entre %{customdata[2]} deputados da UF<extra></extra>"))
for _, t in serie[serie.trocou_de_partido_no_mes].iterrows():
    fig.add_vline(x=t.competencia, line_dash="dot", line_color="gray")
    fig.add_annotation(x=t.competencia, y=1, yref="paper", text=f"🔀 {t.partidos_no_mes}", showarrow=False,
                       yanchor="bottom", font=dict(size=11))
eixos(fig, 360, None, "Gasto no mês (R$)")
st.plotly_chart(fig, use_container_width=True)
st.caption("Pontos laranja: meses acima da mediana da UF. "
           + ("Linha pontilhada: troca de partido dentro da janela. " if serie.trocou_de_partido_no_mes.any() else "")
           + (f"A trajetória na legislatura foi {sel.trajetoria_partidaria}; a troca ficou fora da janela comparável."
              if sel.trocou_de_partido and not serie.trocou_de_partido_no_mes.any() else ""))

# onde o parlamentar fica entre os colegas da mesma UF
colegas = dep.query("sigla_uf == @sel.sigla_uf")
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=colegas.gasto_medio_mensal, y=[""] * len(colegas), mode="markers", name=f"Deputados de {sel.sigla_uf}",
    marker=dict(color=CINZA, size=11, line_width=0), customdata=colegas[["rotulo"]],
    hovertemplate="%{customdata[0]}<br>Gasto médio: R$ %{x:,.0f}/mês<extra></extra>"))
fig.add_trace(go.Scatter(
    x=[sel.gasto_medio_mensal], y=[""], mode="markers", name=sel.nome_parlamentar,
    marker=dict(color=LARANJA, size=16, line_width=0),
    hovertemplate=f"{sel.rotulo}<br>Gasto médio: R$ %{{x:,.0f}}/mês<extra></extra>"))
fig.add_vline(x=sel.mediana_uf_mensal, line_dash="dash", line_color="gray",
              annotation_text="mediana da UF", annotation_position="top")
eixos(fig, 170, f"Gasto médio mensal dos {len(colegas)} deputados de {sel.sigla_uf} (R$/mês)")
fig.update_layout(margin=dict(l=8, r=8, t=28, b=36))
st.markdown(f"**Entre os colegas de {sel.sigla_uf}:** {sel.posicao_ranking}º no ranking nacional de desvio. "
            "A linha tracejada é a mediana da UF nos meses do parlamentar; metade dos colegas fica de cada lado "
            "em cada mês, e um gasto muito alto não a desloca.")
st.plotly_chart(fig, use_container_width=True)

# ONDE: categorias e fornecedores
cat = (d["cat"].query("id_deputado == @id_sel").sort_values("posicao_excesso")
       .rename(columns={"gasto_categoria": "gasto", "excesso_categoria_vs_uf": "excesso",
                        "participacao_categoria_no_deputado": "part"}))
c1 = cat.iloc[0]
st.subheader("Categorias e fornecedores")
st.markdown(md(
    f"A categoria que mais explica o desvio é **{c1.descricao_subcota.rstrip('.').capitalize()}**: "
    f"**{brl(c1.excesso)}** acima da mediana dos deputados da mesma UF nessa categoria "
    f"({c1.part:.0%} do gasto do parlamentar)."))
cat = cat.assign(cor=lambda x: x.excesso.map(lambda v: LARANJA if v > 0 else AZUL),
                 g=lambda x: x.gasto.map(brl), p=lambda x: x.part.map(lambda v: f"{v:.0%}"))
st.plotly_chart(barras_h(cat.head(10), "excesso", "descricao_subcota", cat.head(10)["cor"], {
    "cols": ["g", "p"],
    "tpl": "<b>%{y}</b><br>Acima da mediana da UF: R$ %{x:,.0f}<br>Gasto na categoria: %{customdata[0]}"
           " (%{customdata[1]} do total)"},
    "Gasto na categoria acima da mediana da UF (R$)"), use_container_width=True)
forn = (d["forn"].query("id_deputado == @id_sel and posicao_gasto <= 10").sort_values("posicao_gasto")
        .rename(columns={"gasto_fornecedor": "gasto", "participacao_no_deputado": "part",
                         "qtd_lancamentos": "notas"}))
st.markdown(f"**{len(forn)} maiores fornecedores** — somam {forn.participacao_acumulada.iloc[-1]:.0%} do gasto")
st.dataframe(
    forn[["nome_fornecedor", "documento_fornecedor", "gasto", "part", "notas"]].rename(columns={
        "nome_fornecedor": "Fornecedor", "documento_fornecedor": "CNPJ/CPF", "gasto": "Gasto (R$)",
        "part": "Participação", "notas": "Lançamentos"}),
    hide_index=True, use_container_width=True,
    column_config={"Gasto (R$)": st.column_config.NumberColumn(format="%.0f"),
                   "Participação": st.column_config.NumberColumn(format="percent")})
st.caption("CPF de pessoa física aparece mascarado (`***.456.789-**`), conforme a análise de LGPD.")

# COM QUE PROVA: o lançamento e o documento publicado pela Câmara
st.subheader("Os maiores lançamentos, com o documento na Câmara")
nomes_cat = dict(zip(cat.num_subcota, cat.descricao_subcota.str.rstrip(".").str.capitalize()))
num_cat = st.selectbox("Categoria", list(nomes_cat), format_func=nomes_cat.get)
lanc = lancamentos(int(id_sel), int(num_cat))
st.markdown(
    f"Os {len(lanc)} maiores lançamentos de **{sel.nome_parlamentar}** nessa categoria. Cada linha é um "
    "lançamento publicado pela Câmara; o link abre o documento digitalizado no site da Câmara.")
st.dataframe(
    lanc[["posicao_valor", "data_emissao", "competencia", "nome_fornecedor", "documento_fornecedor",
          "tipo_documento", "valor_liquido", "url_documento"]],
    hide_index=True, use_container_width=True, height=36 * (len(lanc) + 1) + 3,
    column_config={
        "posicao_valor": st.column_config.NumberColumn("#", format="%d"),
        "data_emissao": st.column_config.DateColumn("Emissão", format="DD/MM/YYYY"),
        "competencia": st.column_config.DateColumn("Competência", format="MM/YYYY"),
        "nome_fornecedor": "Fornecedor", "documento_fornecedor": "CNPJ/CPF", "tipo_documento": "Tipo",
        "valor_liquido": st.column_config.NumberColumn("Valor (R$)", format="%.2f"),
        "url_documento": st.column_config.LinkColumn("Documento", display_text="abrir na Câmara"),
    })
st.caption("Documento vazio: a Câmara não publicou o arquivo digitalizado, ou o fornecedor é pessoa física. "
           "Neste caso o link não é exibido porque o recibo traz o CPF completo; o lançamento continua "
           "identificado por fornecedor, data e valor. Nome do passageiro e trecho de voo também não são "
           "exibidos (LGPD).")
cd1, cd2 = st.columns(2)
cd1.download_button("Baixar os fornecedores (CSV)", csv(forn[["nome_fornecedor", "documento_fornecedor", "gasto",
                    "part", "notas"]]), f"fornecedores_{id_sel}.csv", "text/csv")
cd2.download_button("Baixar os lançamentos (CSV)", csv(lanc.drop(columns=["sk_fornecedor"])),
                    f"lancamentos_{id_sel}_{num_cat}.csv", "text/csv")

with st.expander("Tabela completa do ranking"):
    st.dataframe(dep[["posicao_ranking", "nome_parlamentar", "sigla_uf", "trajetoria_partidaria",
                      "meses_com_gasto", "gasto_medio_mensal", "mediana_uf_mensal", "desvio_acumulado",
                      "desvio_relativo", "hhi_fornecedores"]],
                 hide_index=True, use_container_width=True)

st.caption("Camada semântica: semantico.met_parlamentar, met_parlamentar_mes, met_partido, "
           "met_categoria_parlamentar, met_fornecedor_parlamentar, met_lancamento_parlamentar, met_contexto e "
           "met_qualidade_build. Definição de cada métrica: dbt_ceap/models/semantic/_semantic.yml. "
           "Desvio não é irregularidade: indica onde olhar primeiro.")
