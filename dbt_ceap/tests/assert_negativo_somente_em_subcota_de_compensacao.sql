-- Valor negativo onde não cabe: só as subcotas marcadas em seeds/regra_subcota.csv
-- (créditos de bilhete aéreo e devolução de auxílio-moradia) podem ter valor_liquido < 0.
-- Um negativo em combustível, escritório etc. é erro de carga ou de publicação.
select f.id_lancamento, f.num_subcota, c.descricao_subcota, f.valor_liquido, f.arquivo_origem
from {{ ref('fct_lancamento_ceap') }} f
join {{ ref('dim_categoria_despesa') }} c using (num_subcota)
where f.valor_liquido < 0 and not c.permite_valor_negativo
