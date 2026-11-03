-- Salto de série (degrau): em competência FECHADA, o gasto total e o nº de deputados com
-- gasto não podem cair abaixo de 60% nem passar de 170% da mediana dos 6 meses anteriores.
-- Calibração (2026-11-03): nos meses fechados reais a razão do gasto ficou entre 0,75 e 1,35
-- e a do nº de deputados entre 0,98 e 1,03.
-- Meses ainda em maturação ficam fora (ver var meses_maturacao) — não são erro, são atraso.
with mensal as (
    select competencia,
           sum(valor_liquido)            as gasto,
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
