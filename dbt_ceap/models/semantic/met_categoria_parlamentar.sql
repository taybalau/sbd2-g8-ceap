-- CAMADA SEMÂNTICA (E4) — métricas de categoria por parlamentar. GRÃO: deputado × subcota.
-- Antes o painel somava os fornecedores de cada categoria; agora a soma é feita uma vez, aqui.
select
    id_deputado,
    num_subcota,
    any_value(descricao_subcota)                                   as descricao_subcota,
    sum(gasto_fornecedor)                                          as gasto_categoria,
    any_value(excesso_categoria_vs_uf)                             as excesso_categoria_vs_uf,
    any_value(participacao_categoria_no_deputado)                  as participacao_categoria_no_deputado,
    rank() over (partition by id_deputado order by any_value(excesso_categoria_vs_uf) desc) as posicao_excesso
from {{ ref('mart_concentracao_parlamentar') }}
group by id_deputado, num_subcota
