-- Dupla agregação / fan-out: o fato tem que ter exatamente as mesmas linhas e a mesma soma
-- que a Bronze. Se a junção temporal com o SCD casar 2 versões, a contagem sobe e isto falha.
with bronze as (
    select count(*) as linhas, sum(vlrLiquido::decimal(14,2)) as soma
    from {{ source('bronze', 'ceap_lancamento') }}
),
fato as (
    select count(*) as linhas, count(distinct id_lancamento) as distintas, sum(valor_liquido) as soma
    from {{ ref('fct_lancamento_ceap') }}
)
select * from bronze, fato
where bronze.linhas <> fato.linhas
   or fato.linhas <> fato.distintas
   or bronze.soma <> fato.soma
