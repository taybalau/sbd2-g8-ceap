-- CAMADA SEMÂNTICA (E4) — métricas de fornecedor por parlamentar. GRÃO: deputado × fornecedor
-- (somadas todas as subcotas). Antes o painel fazia esta soma; agora é feita uma vez, aqui.
select
    id_deputado,
    sk_fornecedor,
    any_value(nome_fornecedor)                                     as nome_fornecedor,
    any_value(documento_fornecedor)                                as documento_fornecedor,
    sum(gasto_fornecedor)                                          as gasto_fornecedor,
    sum(participacao_no_deputado)                                  as participacao_no_deputado,
    sum(qtd_lancamentos)::bigint                                   as qtd_lancamentos,
    row_number() over (partition by id_deputado
                       order by sum(gasto_fornecedor) desc, sk_fornecedor) as posicao_gasto,
    -- quanto os N maiores fornecedores somam: o painel lê a linha da posição N
    sum(sum(participacao_no_deputado)) over (partition by id_deputado
                       order by sum(gasto_fornecedor) desc, sk_fornecedor
                       rows between unbounded preceding and current row) as participacao_acumulada
from {{ ref('mart_concentracao_parlamentar') }}
group by id_deputado, sk_fornecedor
