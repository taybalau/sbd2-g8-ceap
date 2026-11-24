-- CAMADA SEMÂNTICA (E4) — métricas por partido. GRÃO: um partido, pela sigla vigente NA DATA DO GASTO
-- (SCD tipo 2). A regra de corte do ranking (mínimo de deputados) mora aqui, não no painel.
select
    sigla_partido,
    qtd_deputados,
    deputado_meses,
    gasto_total,
    desvio_acumulado,
    desvio_medio_por_deputado_mes,
    qtd_deputados >= {{ var('min_deputados_partido') }}                as entra_no_ranking,
    case when qtd_deputados >= {{ var('min_deputados_partido') }}
         then rank() over (partition by qtd_deputados >= {{ var('min_deputados_partido') }}
                           order by desvio_medio_por_deputado_mes desc)
    end                                                                as posicao_ranking,
    gasto_total_se_sobrescrito,
    erro_gasto_se_sobrescrito
from {{ ref('mart_desvio_partido') }}
