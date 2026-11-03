-- Salto de série POR SUBCOTA. O teste do total não basta: em ago/2025 a subcota 998
-- (SIGEPA, ~18% do gasto) sumiu e o total caiu só 21% — dentro da variação normal.
-- Regra: subcota relevante (mediana >= R$ 300 mil/mês) não pode ficar abaixo de 25% da
-- mediana dos 6 meses anteriores numa competência fechada. Calibração (2026-11-03): fora
-- da ruptura registrada, a menor razão observada foi 0,53 (jan/2024, recesso).
with m as (
    select num_subcota, competencia, sum(valor_liquido) as gasto
    from {{ ref('fct_lancamento_ceap') }}
    where is_legislatura_alvo and is_competencia_fechada
    group by 1, 2
),
relevante as (select num_subcota from m group by 1 having median(gasto) >= 300000),
grade as (
    select r.num_subcota, c.competencia
    from relevante r cross join (select distinct competencia from m) c
),
serie as (
    select g.*, coalesce(m.gasto, 0) as gasto
    from grade g left join m using (num_subcota, competencia)
),
com_ref as (
    select *, median(gasto) over w as gasto_ref, count(*) over w as meses_ref
    from serie
    window w as (partition by num_subcota order by competencia rows between 6 preceding and 1 preceding)
)
select c.num_subcota, c.competencia, c.gasto, c.gasto_ref, c.gasto / c.gasto_ref as razao
from com_ref c
left join {{ ref('ruptura_publicacao') }} r
    on r.num_subcota = c.num_subcota and c.competencia >= r.competencia_inicio
where c.meses_ref >= 3
  and c.gasto_ref > 0
  and c.gasto / c.gasto_ref < 0.25
  and r.num_subcota is null
