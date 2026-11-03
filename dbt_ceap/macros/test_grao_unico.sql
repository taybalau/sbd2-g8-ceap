{#
  Teste genérico de GRÃO: falha se existir mais de uma linha para a combinação de colunas
  que define o grão declarado do modelo. Uso:
    tests:
      - grao_unico: {colunas: [id_deputado, sk_parlamentar, competencia]}
#}
{% test grao_unico(model, colunas) %}
select {{ colunas | join(', ') }}, count(*) as linhas
from {{ model }}
group by {{ colunas | join(', ') }}
having count(*) > 1
{% endtest %}
