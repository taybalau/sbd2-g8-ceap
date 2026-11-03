-- Grão: uma linha por subcota da CEAP.
select
    s.num_subcota,
    any_value(s.descricao_subcota)          as descricao_subcota,
    r.grupo_despesa,
    coalesce(r.permite_valor_negativo, false) as permite_valor_negativo,
    r.justificativa_negativo
from {{ ref('stg_ceap__lancamento') }} s
left join {{ ref('regra_subcota') }} r using (num_subcota)
group by s.num_subcota, r.grupo_despesa, r.permite_valor_negativo, r.justificativa_negativo
