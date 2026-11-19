"""
Comparativo média × mediana como referência do desvio (ADR-0005, seção 9.5).

Recalcula, sobre os MESMOS dados, o ranking de parlamentares e o de partidos com as duas
referências: a média e a mediana do gasto mensal dos deputados da mesma UF no mês. Lê só o
gasto de cada deputado por mês (gold.fct_gasto_mensal_parlamentar, competências comparáveis),
que não depende da referência escolhida, então o resultado é o mesmo antes e depois da troca.

Uso (com o lakehouse gerado, por exemplo dentro do container da E3):
    python scripts/comparar_media_mediana.py > /tmp/comparativo.md
"""
import os
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[1]
BANCO = Path(os.getenv("LAKEHOUSE_PATH", RAIZ / "lakehouse")) / "ceap.duckdb"
TOP = 15
MIN_DEPUTADOS_PARTIDO = 5  # o mesmo corte do painel

con = duckdb.connect(str(BANCO), read_only=True)
con.execute("""
create temp table versao as
select id_deputado, sigla_partido, sigla_uf, competencia, nome_parlamentar,
       gasto_versao::double as gasto_versao, gasto_deputado_mes::double as gasto_mes
from gold.fct_gasto_mensal_parlamentar where is_competencia_comparavel;

create temp table ref as
select sigla_uf, competencia, avg(gasto_mes) as media, median(gasto_mes) as mediana,
       count(*) as n, min(gasto_mes) as menor, max(gasto_mes) as maior
from (select distinct id_deputado, sigla_uf, competencia, gasto_mes from versao)
group by all;

create temp table dep as
select id_deputado, any_value(sigla_uf) as uf,
       sum(gasto_mes - media)   as desvio_media,
       sum(gasto_mes - mediana) as desvio_mediana
from (select distinct id_deputado, sigla_uf, competencia, gasto_mes from versao)
join ref using (sigla_uf, competencia)
group by 1;

create temp table dep_rank as
select d.*, n.nome, n.partido,
       rank() over (order by desvio_media desc)   as pos_media,
       rank() over (order by desvio_mediana desc) as pos_mediana
from dep d
join (select id_deputado, arg_max(nome_parlamentar, competencia) as nome,
             arg_max(sigla_partido, competencia) as partido
      from versao group by 1) n using (id_deputado);

-- partido da data do gasto: o desvio do mês é rateado entre as versões pelo gasto
create temp table par as
select sigla_partido, count(distinct id_deputado) as deputados,
       count(distinct (id_deputado, competencia)) as dep_meses,
       sum(case when gasto_mes = 0 then 0 else (gasto_mes - media) * gasto_versao / gasto_mes end) as desvio_media,
       sum(case when gasto_mes = 0 then 0 else (gasto_mes - mediana) * gasto_versao / gasto_mes end) as desvio_mediana
from versao join ref using (sigla_uf, competencia)
group by 1;
""")


def brl(v):
    return ("R$ " + f"{v:,.0f}".replace(",", ".")) if v >= 0 else ("−R$ " + f"{-v:,.0f}".replace(",", "."))


def pct(v):
    return f"{v:+.1%}".replace(".", ",").replace("-", "−")


def seta(antes, depois):
    d = antes - depois
    return "=" if d == 0 else (f"▲ {d}" if d > 0 else f"▼ {-d}")


ini, fim, meses = con.execute("select min(competencia), max(competencia), count(distinct competencia) from ref").fetchone()
g = con.execute("""
    select sum(media * n) / sum(n), sum(mediana * n) / sum(n),
           count(*) filter (where media > mediana), count(*)
    from ref""").fetchone()
top_media = {r[0] for r in con.execute(f"select id_deputado from dep_rank where pos_media <= {TOP}").fetchall()}
top_mediana = {r[0] for r in con.execute(f"select id_deputado from dep_rank where pos_mediana <= {TOP}").fetchall()}
spearman = con.execute("select corr(pos_media, pos_mediana) from dep_rank").fetchone()[0]

out = [
    f"Janela comparável: {ini:%m/%Y} a {fim:%m/%Y} ({meses} meses), {con.execute('select count(*) from dep').fetchone()[0]} deputados.",
    "",
    "| Indicador | Média | Mediana |", "| :--- | ---: | ---: |",
    f"| Referência mensal típica da UF (ponderada pelo nº de deputados) | {brl(g[0])} | {brl(g[1])} |",
    f"| UF × mês em que a média fica acima da mediana | {g[2]} de {g[3]} | |",
    f"| Deputados do top {TOP} que continuam no top {TOP} | {len(top_media & top_mediana)} de {TOP} | |",
    f"| Correlação de postos entre os dois rankings (Spearman) | {str(round(spearman, 3)).replace('.', ',')} | |",
    "",
    f"**Top {TOP} pela mediana** (posição na média ao lado; ▲ subiu com a mediana, ▼ caiu):", "",
    "| # mediana | Deputado | Desvio acumulado (mediana) | # média | Desvio acumulado (média) | Variação |",
    "| ---: | :--- | ---: | ---: | ---: | :---: |",
]
for r in con.execute(f"""select pos_mediana, nome, partido, uf, desvio_mediana, pos_media, desvio_media
                         from dep_rank where pos_mediana <= {TOP} order by pos_mediana""").fetchall():
    out.append(f"| {r[0]} | {r[1]} ({r[2]}-{r[3]}) | {brl(r[4])} | {r[5]} | {brl(r[6])} | {seta(r[5], r[0])} |")
saiu = con.execute(f"""select pos_media, nome, partido, uf, pos_mediana from dep_rank
                       where pos_media <= {TOP} and pos_mediana > {TOP} order by pos_media""").fetchall()
if saiu:
    out += ["", f"Saíram do top {TOP}: " + "; ".join(f"{r[1]} ({r[2]}-{r[3]}), de {r[0]}º para {r[4]}º" for r in saiu) + "."]

out += ["", f"**Partidos** com pelo menos {MIN_DEPUTADOS_PARTIDO} deputados, por desvio por deputado-mês:", "",
        "| Partido | Deputados | Desvio por deputado-mês (mediana) | # mediana | Desvio por deputado-mês (média) | # média |",
        "| :--- | ---: | ---: | ---: | ---: | ---: |"]
for r in con.execute(f"""
        select sigla_partido, deputados, desvio_mediana / dep_meses, desvio_media / dep_meses,
               rank() over (order by desvio_mediana / dep_meses desc), rank() over (order by desvio_media / dep_meses desc)
        from par where deputados >= {MIN_DEPUTADOS_PARTIDO} order by 3 desc""").fetchall():
    out.append(f"| {r[0]} | {r[1]} | {brl(r[2])} | {r[4]} | {brl(r[3])} | {r[5]} |")

out += ["", "**UFs em que a média mais se afasta da mediana** (afastamento médio nos meses da janela;"
        " positivo: a média fica acima, puxada por gastos altos; negativo: fica abaixo, puxada por gastos baixos):", "",
        "| UF | Deputados/mês | Média mensal | Mediana mensal | Média vs mediana | Menor gasto num mês | Maior gasto num mês |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: |"]
for r in con.execute("""
        with u as (select sigla_uf, round(avg(n)) as n, avg(media) as media, avg(mediana) as mediana,
                          avg(media / mediana - 1) as gap, min(menor) as menor, max(maior) as maior
                   from ref group by 1)
        (select * from u order by gap desc limit 3) union all (select * from u order by gap limit 3)
        order by gap desc""").fetchall():
    out.append(f"| {r[0]} | {r[1]:.0f} | {brl(r[2])} | {brl(r[3])} | {pct(r[4])} | {brl(r[5])} | {brl(r[6])} |")

print("\n".join(out))
