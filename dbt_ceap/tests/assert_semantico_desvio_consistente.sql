-- CONSUMO DUPLO (E4): o desvio acima da mediana é o mesmo número por parlamentar e por partido,
-- e o erro total da sobrescrita no contexto bate com o dos partidos.
-- O desvio por partido vem do rateio entre versões (desvio_alocado, arredondado a 4 casas por
-- linha); a tolerância de R$ 1 cobre esse arredondamento em ~24 mil linhas e nada além disso.
with par as (
    select 'desvio por partido vs por parlamentar' as verificacao,
           (select sum(desvio_acumulado) from {{ ref('met_partido') }})     as valor_a,
           (select sum(desvio_acumulado) from {{ ref('met_parlamentar') }}) as valor_b,
           1.0 as tolerancia
    union all
    select 'erro total da sobrescrita: contexto vs partidos',
           (select erro_total_sobrescrita from {{ ref('met_contexto') }}),
           (select sum(abs(erro_gasto_se_sobrescrito)) / 2 from {{ ref('met_partido') }}),
           0.01
    union all
    select 'linhas do contexto (deve ser 1)',
           (select count(*) from {{ ref('met_contexto') }}), 1, 0
)
select * from par where abs(valor_a - valor_b) > tolerancia
