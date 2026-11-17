-- Dado faltante no nível do arquivo: cada ano esperado (var anos_esperados, o mesmo ANOS da
-- ingestão) precisa estar na Bronze e no fato. Os testes de série não pegam isso: se o
-- Ano-2026.csv nunca for ingerido, a série termina em dez/2025 sem lacuna e a Gold sai sem 2026.
with esperados as (
    select unnest({{ var('anos_esperados') }}) as ano
),
bronze as (
    select distinct ano_arquivo::integer as ano from {{ source('bronze', 'ceap_lancamento') }}
),
fato as (
    select distinct regexp_extract(arquivo_origem, '(\d{4})', 1)::integer as ano
    from {{ ref('fct_lancamento_ceap') }}
)
select e.ano, b.ano is not null as presente_na_bronze, f.ano is not null as presente_no_fato
from esperados e
left join bronze b using (ano)
left join fato f using (ano)
where b.ano is null or f.ano is null
