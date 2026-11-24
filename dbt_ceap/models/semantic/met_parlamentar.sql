-- CAMADA SEMÂNTICA (E4) — métricas por parlamentar. GRÃO: um deputado (57ª Legislatura).
-- Fonte única das métricas de parlamentar para o painel e para o ETL reverso: quem consome lê daqui,
-- nunca da Gold diretamente, e não recalcula nada. As fórmulas estão em _semantic.yml (meta.formula).
select
    id_deputado,
    nome_parlamentar,
    sigla_uf,
    partido_atual,
    nome_parlamentar || ' (' || coalesce(partido_atual, '—') || '-' || sigla_uf || ')' as rotulo,
    trajetoria_partidaria,
    trocou_de_partido,
    meses_com_gasto,
    gasto_total,
    gasto_medio_mensal,
    mediana_uf_mensal,
    desvio_acumulado,
    desvio_relativo,
    meses_acima_mediana,
    z_medio,
    hhi_fornecedores,
    posicao_ranking,
    posicao_ranking <= {{ var('alerta_top_n') }} as em_alerta
from {{ ref('mart_desvio_parlamentar') }}
