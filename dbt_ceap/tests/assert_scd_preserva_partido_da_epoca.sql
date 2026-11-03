-- O erro que este teste pega: dimensão tratada como sobrescrita, ou junção do fato com a
-- dimensão só por id (que casa a versão atual). Recalcula, independentemente do modelo,
-- qual versão estava vigente na data do gasto e exige que o fato aponte para ela.
-- Para o caso ideCadastro 204494, um gasto de mar/2023 TEM de cair em PATRIOTA, não em PRD.
with esperado as (
    select f.id_lancamento, p.sk_parlamentar as sk_esperado, p.sigla_partido as partido_esperado
    from {{ ref('fct_lancamento_ceap') }} f
    join {{ ref('dim_parlamentar_scd') }} p
      on p.id_deputado = f.id_deputado
     and not p.is_lideranca
     and f.data_referencia_scd::timestamp >= p.valido_de
     and f.data_referencia_scd::timestamp <  p.valido_ate
    where not f.is_lideranca
)
select f.id_lancamento, f.id_deputado, f.data_referencia_scd,
       e.partido_esperado, d.sigla_partido as partido_no_fato
from {{ ref('fct_lancamento_ceap') }} f
join esperado e using (id_lancamento)
left join {{ ref('dim_parlamentar_scd') }} d on d.sk_parlamentar = f.sk_parlamentar
where f.sk_parlamentar is distinct from e.sk_esperado
