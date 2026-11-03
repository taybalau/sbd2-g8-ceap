-- Grão: uma linha por fornecedor, identificado pelo CNPJ/CPF (só dígitos).
-- Sem documento (ex.: companhias aéreas no SIGEPA, auxílio-moradia), a chave é o nome publicado.
--
-- Decisão SCD: tipo 1 para o nome. 7.870 documentos aparecem com mais de uma grafia de nome
-- (medido em 2026-11-03), quase sempre variação de digitação. Todas as agregações são por
-- documento (sk_fornecedor), nunca por nome, então sobrescrever o nome não altera nenhuma
-- série histórica. A quantidade de grafias fica registrada em qtd_grafias_nome.
with base as (
    select
        coalesce(documento_fornecedor, 'SEM-DOC:' || upper(nome_fornecedor_publicado)) as chave_fornecedor,
        documento_fornecedor,
        nome_fornecedor_publicado,
        data_emissao,
        competencia
    from {{ ref('stg_ceap__lancamento') }}
)
select
    md5(chave_fornecedor)                          as sk_fornecedor,
    chave_fornecedor,
    any_value(documento_fornecedor)                as documento_fornecedor,
    case
        when any_value(documento_fornecedor) is null        then 'SEM DOCUMENTO'
        when length(any_value(documento_fornecedor)) = 14   then 'CNPJ'
        when length(any_value(documento_fornecedor)) = 11   then 'CPF'
        else 'OUTRO'
    end                                            as tipo_documento_fornecedor,
    mode(nome_fornecedor_publicado)                as nome_fornecedor,
    count(distinct nome_fornecedor_publicado)      as qtd_grafias_nome,
    min(competencia)                               as primeira_competencia,
    max(competencia)                               as ultima_competencia
from base
group by chave_fornecedor
