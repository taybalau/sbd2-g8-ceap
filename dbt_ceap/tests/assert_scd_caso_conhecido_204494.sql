-- Teste de regressão com caso real verificado na API (2026-11-03): ideCadastro 204494 era
-- PATRIOTA até 07/02/2024 e PRD depois. O CSV traz PRD desde fev/2023 (sobrescrita na fonte).
-- Falha se algum gasto anterior a 07/02/2024 desse deputado for atribuído a outro partido
-- que não PATRIOTA, ou se algum posterior não for PRD.
select f.id_lancamento, f.data_referencia_scd, d.sigla_partido
from {{ ref('fct_lancamento_ceap') }} f
join {{ ref('dim_parlamentar_scd') }} d using (sk_parlamentar)
where d.id_cadastro_camara = 204494
  and f.codigo_legislatura = 57
  and (   (f.data_referencia_scd <  date '2024-02-07' and d.sigla_partido <> 'PATRIOTA')
       or (f.data_referencia_scd >= date '2024-02-07' and d.sigla_partido <> 'PRD'))
