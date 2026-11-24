-- CAMADA SEMÂNTICA (E4) — contexto das métricas. GRÃO: uma linha.
-- Janela comparável, atualização, freshness e a ruptura que encerra a janela. É uma view: a idade
-- dos dados (idade_horas) é calculada no momento da leitura, não no build.
with janela as (
    select min(competencia) as janela_inicio, max(competencia) as janela_fim,
           count(distinct competencia) as meses_janela
    from {{ ref('fct_gasto_mensal_parlamentar') }} where is_competencia_comparavel
),
fato as (
    select max(competencia) as ultima_competencia_publicada, max(ingerido_em) as atualizado_em
    from {{ ref('fct_lancamento_ceap') }}
),
sla as (
    select sla_horas, ingerido_em_mais_recente
    from {{ ref('mart_freshness_gold') }} where tabela_consumo = 'mart_desvio_parlamentar'
),
erro as (
    -- cada real atribuído ao partido errado aparece duas vezes (sobra num, falta noutro)
    select (sum(abs(erro_gasto_se_sobrescrito)) / 2)::decimal(38, 2) as erro_total_sobrescrita
    from {{ ref('mart_desvio_partido') }}
),
ruptura as (
    -- a primeira ruptura é a que encerra a janela comparável (ver dim_calendario)
    select num_subcota, competencia_inicio, descricao, evidencia
    from {{ ref('ruptura_publicacao') }} order by competencia_inicio limit 1
)
select
    j.janela_inicio,
    j.janela_fim,
    j.meses_janela,
    f.ultima_competencia_publicada,
    f.atualizado_em,
    s.sla_horas,
    date_diff('second', s.ingerido_em_mais_recente, current_timestamp) / 3600.0 as idade_horas,
    date_diff('second', s.ingerido_em_mais_recente, current_timestamp) / 3600.0 <= s.sla_horas as dentro_do_sla,
    e.erro_total_sobrescrita,
    {{ var('min_deputados_partido') }}::integer as min_deputados_partido,
    r.num_subcota        as ruptura_num_subcota,
    r.competencia_inicio as ruptura_inicio,
    r.descricao          as ruptura_descricao,
    r.evidencia          as ruptura_evidencia
from janela j
cross join fato f
cross join sla s
cross join erro e
left join ruptura r on true
