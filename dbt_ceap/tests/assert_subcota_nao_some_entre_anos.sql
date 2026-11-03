-- "Município que some entre dois anos", versão CEAP: uma subcota com volume relevante
-- (>= 100 lançamentos) num ano fechado não pode desaparecer no ano seguinte. Isso costuma
-- ser mudança de código na fonte (a Câmara renumerar a subcota) ou arquivo truncado.
with anual as (
    select ano_competencia, num_subcota, count(*) as n
    from {{ ref('fct_lancamento_ceap') }}
    where is_legislatura_alvo
    group by 1, 2
),
anos as (select distinct ano_competencia from anual)
select a.ano_competencia, a.num_subcota, a.n as lancamentos_no_ano, a.ano_competencia + 1 as ano_em_que_sumiu
from anual a
join anos prox on prox.ano_competencia = a.ano_competencia + 1
left join anual b on b.num_subcota = a.num_subcota and b.ano_competencia = a.ano_competencia + 1
left join {{ ref('ruptura_publicacao') }} r
    on r.num_subcota = a.num_subcota and year(r.competencia_inicio) <= a.ano_competencia + 1
where a.n >= 100 and b.num_subcota is null
  and r.num_subcota is null   -- ruptura já investigada e registrada
