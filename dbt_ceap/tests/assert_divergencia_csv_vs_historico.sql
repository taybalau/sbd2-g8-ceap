{{ config(severity='warn') }}
-- Mede (e guarda em auditoria.*) os lançamentos em que o partido publicado no CSV difere do
-- partido vigente na data do gasto segundo o histórico oficial: é o tamanho da sobrescrita
-- feita pela própria fonte. warn porque é sujeira da fonte, não do pipeline.
select f.id_lancamento, f.id_deputado, f.competencia, f.valor_liquido,
       f.sigla_partido_publicada, d.sigla_partido as partido_na_data
from {{ ref('fct_lancamento_ceap') }} f
join {{ ref('dim_parlamentar_scd') }} d using (sk_parlamentar)
where not f.is_lideranca
  and f.sigla_partido_publicada is distinct from d.sigla_partido
