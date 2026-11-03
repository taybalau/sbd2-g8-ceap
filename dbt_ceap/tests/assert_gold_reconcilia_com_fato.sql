-- O mart mensal precisa somar exatamente o fato no mesmo recorte (57ª, sem lideranças).
with fato as (
    select sum(valor_liquido) as soma from {{ ref('fct_lancamento_ceap') }}
    where is_legislatura_alvo and not is_lideranca
),
mart as (
    select sum(gasto_versao) as soma from {{ ref('fct_gasto_mensal_parlamentar') }}
)
select * from fato, mart where fato.soma <> mart.soma
