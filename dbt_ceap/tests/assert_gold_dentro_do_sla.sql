-- SLA da Gold: no máximo var('sla_horas_gold') horas entre a ingestão mais recente dos CSVs e a
-- Gold publicada. Reprova se a transformação rodar sobre uma Bronze velha (ingestão parada).
select tabela_consumo, ingerido_em_mais_recente, gold_construida_em, idade_horas_no_build, sla_horas
from {{ ref('mart_freshness_gold') }}
where not dentro_do_sla
