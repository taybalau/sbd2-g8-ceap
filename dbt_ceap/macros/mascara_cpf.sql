{#
  LGPD (docs/lgpd.md, achados L1 e R7; apêndice A.5): fornecedor pessoa física não aparece com o CPF
  completo nas camadas de consumo. Formato igual ao da migration 005 (***.456.789-**): sobram os 6
  dígitos do meio, que o auditor usa para conferir na Receita, e somem os que identificam sozinhos.

  mascara_cpf(col): documento com 11 dígitos (CPF) vira ***.456.789-**; CNPJ (14) passa inteiro.
  mascara_cpf_no_texto(col): qualquer CPF isolado dentro de um texto, com ou sem pontuação (razão
  social de MEI, que costuma terminar no CPF do dono), vira ***.456.789-**. Uma sequência de 11
  dígitos dentro de um CNPJ (14 dígitos) não casa, porque o padrão exige não-dígito nas pontas.
#}
{% macro mascara_cpf(col) -%}
    case when length({{ col }}) = 11
         then '***.' || substr({{ col }}, 4, 3) || '.' || substr({{ col }}, 7, 3) || '-**'
         else {{ col }} end
{%- endmacro %}

{% macro mascara_cpf_no_texto(col) -%}
    regexp_replace({{ col }}, '(^|[^0-9])[0-9]{3}[.]?([0-9]{3})[.]?([0-9]{3})-?[0-9]{2}([^0-9]|$)',
                   '\1***.\2.\3-**\4', 'g')
{%- endmacro %}
