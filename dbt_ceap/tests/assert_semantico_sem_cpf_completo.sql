-- LGPD (docs/lgpd.md, achados L1 e R7; apêndice A.5): nenhuma view da camada semântica entrega CPF
-- completo de fornecedor pessoa física, nem no documento nem dentro do nome (razão social de MEI).
-- Devolve as linhas que violam; uma linha basta para reprovar o build.
{% set cpf_no_texto = "'(^|[^0-9])[0-9]{3}[.]?[0-9]{3}[.]?[0-9]{3}-?[0-9]{2}([^0-9]|$)'" %}
with fornecedores as (
    select 'met_fornecedor_parlamentar' as visao, nome_fornecedor, documento_fornecedor
    from {{ ref('met_fornecedor_parlamentar') }}
    union all
    select distinct 'met_lancamento_parlamentar', nome_fornecedor, documento_fornecedor
    from {{ ref('met_lancamento_parlamentar') }}
)
select *
from fornecedores
where regexp_matches(documento_fornecedor, '^[0-9]{11}$')
   or regexp_matches(nome_fornecedor, {{ cpf_no_texto }})
