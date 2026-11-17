-- Salto de série (degrau): em competência FECHADA, o gasto total e o nº de deputados com
-- gasto não podem cair abaixo de 60% nem passar de 170% da mediana dos 6 meses anteriores.
-- Calibração (download de 2026-11-17, meses fechados de mai/2023 a jul/2026): a razão do gasto
-- ficou entre 0,74 e 1,21 e a do nº de deputados entre 0,98 e 1,03.
-- Meses ainda em maturação ficam fora (ver var meses_maturacao) — não são erro, são atraso.
-- O gasto soma só as subcotas SEM ruptura registrada em seeds/ruptura_publicacao.csv: essas são
-- vigiadas uma a uma por assert_subcota_sem_salto. Sem isso, uma ruptura já investigada derruba
-- o total (jul/2026: a divulgação, ~R$ 10 mi/mês, cai a R$ 0,25 mi no período eleitoral e o
-- total vai a 0,58 da mediana; sem as subcotas com ruptura, o mês fica normal).
with mensal as (
    select competencia,
           sum(valor_liquido) filter (
               where num_subcota not in (select num_subcota from {{ ref('ruptura_publicacao') }})
           )                             as gasto,
           count(distinct id_deputado)   as deputados
    from {{ ref('fct_lancamento_ceap') }}
    where is_legislatura_alvo and not is_lideranca and is_competencia_fechada
    group by 1
),
com_ref as (
    select *,
        median(gasto)     over w as gasto_ref,
        median(deputados) over w as deputados_ref,
        count(*)          over w as meses_ref
    from mensal
    window w as (order by competencia rows between 6 preceding and 1 preceding)
)
select competencia, gasto, gasto_ref, gasto / gasto_ref as razao_gasto,
       deputados, deputados_ref, deputados / deputados_ref as razao_deputados
from com_ref
where meses_ref >= 3
  and (gasto / gasto_ref not between 0.60 and 1.70
       or deputados / deputados_ref not between 0.60 and 1.70)
