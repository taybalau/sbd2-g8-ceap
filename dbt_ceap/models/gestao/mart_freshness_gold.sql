-- FRESHNESS E SLA DAS TABELAS DE CONSUMO. GRÃO DECLARADO: uma linha por tabela de consumo da Gold.
-- idade_horas_no_build = horas entre a ingestão mais recente da Bronze e a construção desta Gold.
-- O teste assert_gold_dentro_do_sla reprova o build quando essa idade passa do SLA.
-- Freshness do negócio (dado atrasado na fonte) fica à parte: última competência publicada e
-- última competência fechada (ver var meses_maturacao).
with fato as (
    select max(ingerido_em) as ingerido_em_mais_recente,
           min(ingerido_em) as ingerido_em_mais_antigo,
           max(competencia) as ultima_competencia_publicada
    from {{ ref('fct_lancamento_ceap') }}
),
fechada as (
    select max(competencia) as ultima_competencia_fechada
    from {{ ref('dim_calendario') }} where is_competencia_fechada
),
tabelas as (
    select unnest(['mart_desvio_parlamentar', 'mart_desvio_partido',
                   'mart_concentracao_parlamentar', 'fct_gasto_mensal_parlamentar']) as tabela_consumo
)
select
    t.tabela_consumo,
    f.ingerido_em_mais_recente,
    f.ingerido_em_mais_antigo,
    current_timestamp                                                         as gold_construida_em,
    round(date_diff('second', f.ingerido_em_mais_recente, current_timestamp) / 3600.0, 2)
                                                                              as idade_horas_no_build,
    {{ var('sla_horas_gold') }}                                               as sla_horas,
    date_diff('second', f.ingerido_em_mais_recente, current_timestamp) / 3600.0
        <= {{ var('sla_horas_gold') }}                                        as dentro_do_sla,
    f.ultima_competencia_publicada,
    c.ultima_competencia_fechada
from tabelas t
cross join fato f
cross join fechada c
