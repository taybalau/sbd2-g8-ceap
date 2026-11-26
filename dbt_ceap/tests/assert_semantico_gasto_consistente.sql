-- CONSUMO DUPLO (E4): o gasto total é o mesmo número em todas as visões da camada semântica e no fato.
-- Se duas telas mostram a mesma métrica com valores diferentes, a plataforma perdeu autoridade.
-- Compara o gasto da janela comparável somado por parlamentar, por partido, por categoria, por
-- fornecedor, mês a mês e lançamento a lançamento com o fato atômico no mesmo recorte (57ª, sem lideranças, competências comparáveis).
-- Reprova se qualquer visão divergir em mais de R$ 0,01.
with visoes as (
    select 'met_parlamentar' as visao, sum(gasto_total) as gasto from {{ ref('met_parlamentar') }}
    union all
    select 'met_partido', sum(gasto_total) from {{ ref('met_partido') }}
    union all
    select 'met_categoria_parlamentar', sum(gasto_categoria) from {{ ref('met_categoria_parlamentar') }}
    union all
    select 'met_fornecedor_parlamentar', sum(gasto_fornecedor) from {{ ref('met_fornecedor_parlamentar') }}
    union all
    select 'met_parlamentar_mes', sum(gasto_mes) from {{ ref('met_parlamentar_mes') }}
    union all
    select 'met_lancamento_parlamentar', sum(valor_liquido) from {{ ref('met_lancamento_parlamentar') }}
),
fato as (
    select sum(valor_liquido) as gasto
    from {{ ref('fct_lancamento_ceap') }}
    where is_legislatura_alvo and not is_lideranca and is_competencia_comparavel
)
select v.visao, v.gasto as gasto_na_visao, f.gasto as gasto_no_fato, v.gasto - f.gasto as diferenca
from visoes v cross join fato f
where abs(v.gasto - f.gasto) > 0.01
