-- Num mês de troca de partido o desvio é rateado entre as versões; o rateio deve somar o desvio do mês.
select id_deputado, competencia, sum(desvio_alocado) as rateado, any_value(desvio_deputado_mes) as desvio
from {{ ref('fct_gasto_mensal_parlamentar') }}
group by 1, 2
having abs(sum(desvio_alocado) - any_value(desvio_deputado_mes)) > 0.01
