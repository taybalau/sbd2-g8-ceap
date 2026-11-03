-- RESPOSTA À 2ª PARTE DA PERGUNTA: quais partidos apresentam maior desvio.
-- GRÃO DECLARADO: uma linha por partido (sigla vigente NA DATA DO GASTO, via SCD tipo 2).
-- Só competências comparáveis (fechadas e antes da ruptura de publicação) da 57ª Legislatura.
--
-- As colunas *_se_sobrescrito mostram o resultado ERRADO que se obteria tratando o partido
-- como SCD tipo 1 (todo o histórico do deputado atribuído ao partido atual). A diferença é
-- o tamanho do erro que o SCD tipo 2 evita.
with mensal as (
    select * from {{ ref('fct_gasto_mensal_parlamentar') }} where is_competencia_comparavel
),
atual as (
    select id_deputado, sigla_partido as partido_atual
    from {{ ref('dim_parlamentar_scd') }} where is_atual
),
correto as (
    select
        sigla_partido,
        count(distinct id_deputado)                         as qtd_deputados,
        count(distinct (id_deputado, competencia))          as deputado_meses,
        sum(gasto_versao)                                   as gasto_total,
        sum(desvio_alocado)                                 as desvio_acumulado
    from mensal group by 1
),
sobrescrito as (
    select
        a.partido_atual                                     as sigla_partido,
        sum(m.gasto_versao)                                 as gasto_total_se_sobrescrito,
        sum(m.desvio_alocado)                               as desvio_acumulado_se_sobrescrito
    from mensal m join atual a using (id_deputado)
    group by 1
)
select
    coalesce(c.sigla_partido, s.sigla_partido)              as sigla_partido,
    coalesce(c.qtd_deputados, 0)                            as qtd_deputados,
    coalesce(c.deputado_meses, 0)                           as deputado_meses,
    coalesce(c.gasto_total, 0)                              as gasto_total,
    coalesce(c.desvio_acumulado, 0)                         as desvio_acumulado,
    coalesce(c.desvio_acumulado, 0) / nullif(c.deputado_meses, 0) as desvio_medio_por_deputado_mes,
    coalesce(s.gasto_total_se_sobrescrito, 0)               as gasto_total_se_sobrescrito,
    coalesce(s.desvio_acumulado_se_sobrescrito, 0)          as desvio_acumulado_se_sobrescrito,
    coalesce(s.gasto_total_se_sobrescrito, 0) - coalesce(c.gasto_total, 0) as erro_gasto_se_sobrescrito
from correto c
full outer join sobrescrito s using (sigla_partido)
