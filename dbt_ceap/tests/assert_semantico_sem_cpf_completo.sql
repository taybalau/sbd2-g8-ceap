-- LGPD (docs/lgpd.md, achados L1 e R7; apêndice A.5): nenhuma view da camada semântica entrega CPF
-- completo de fornecedor pessoa física, nem no documento, nem dentro do nome (razão social de MEI),
-- nem pelo link do documento digitalizado (o recibo de pessoa física traz o CPF completo).
-- Devolve as linhas que violam; uma linha basta para reprovar o build.
{% set cpf_no_texto = "'(^|[^0-9])[0-9]{3}[.]?[0-9]{3}[.]?[0-9]{3}-?[0-9]{2}([^0-9]|$)'" %}
with fornecedores as (
    select 'met_fornecedor_parlamentar' as visao, nome_fornecedor, documento_fornecedor
    from {{ ref('met_fornecedor_parlamentar') }}
    union all
    select distinct 'met_lancamento_parlamentar', nome_fornecedor, documento_fornecedor
    from {{ ref('met_lancamento_parlamentar') }}
)
select visao, nome_fornecedor, documento_fornecedor, 'CPF no documento ou no nome' as motivo
from fornecedores
where regexp_matches(documento_fornecedor, '^[0-9]{11}$')
   or regexp_matches(nome_fornecedor, {{ cpf_no_texto }})
union all
select 'met_lancamento_parlamentar', nome_fornecedor, documento_fornecedor, 'link de documento de pessoa física'
from {{ ref('met_lancamento_parlamentar') }}
where url_documento is not null and documento_fornecedor like '***.%'
