-- Grão: uma linha por lançamento publicado nos CSVs da CEAP (mesmo grão da Bronze).
-- Aqui só há tipagem e renomeação; nenhuma linha é filtrada ou agregada.
with fonte as (
    select * from {{ source('bronze', 'ceap_lancamento') }}
)

select
    _hash_lancamento                                         as id_lancamento,
    nullif(nuDeputadoId, '')::integer                        as id_deputado,
    nullif(ideCadastro, '')::integer                         as id_cadastro_camara,
    -- Lideranças partidárias e de governo também gastam CEAP, mas não são parlamentares
    (nullif(ideCadastro, '') is null)                        as is_lideranca,
    trim(txNomeParlamentar)                                  as nome_parlamentar,
    nullif(trim(sgPartido), '')                              as sigla_partido_publicada,
    nullif(nullif(trim(sgUF), ''), 'NA')                     as sigla_uf_publicada,
    codLegislatura::integer                                  as codigo_legislatura,

    numSubCota::integer                                      as num_subcota,
    trim(txtDescricao)                                       as descricao_subcota,
    nullif(numEspecificacaoSubCota, '0')::integer            as num_especificacao,
    nullif(trim(txtDescricaoEspecificacao), '')              as descricao_especificacao,

    nullif(trim(txtFornecedor), '')                          as nome_fornecedor_publicado,
    nullif(regexp_replace(txtCNPJCPF, '[^0-9]', '', 'g'), '') as documento_fornecedor,

    nullif(trim(ideDocumento), '0')::bigint                  as id_documento_camara,
    nullif(trim(txtNumero), '')                              as numero_documento,
    indTipoDocumento::integer                                as tipo_documento,
    try_cast(datEmissao as timestamp)::date                  as data_emissao,

    vlrDocumento::decimal(14, 2)                             as valor_documento,
    coalesce(nullif(vlrGlosa, '')::decimal(14, 2), 0)        as valor_glosa,
    vlrLiquido::decimal(14, 2)                               as valor_liquido,
    nullif(vlrRestituicao, '')::decimal(14, 2)               as valor_restituicao,
    try_cast(datPagamentoRestituicao as timestamp)::date     as data_pagamento_restituicao,

    make_date(numAno::integer, numMes::integer, 1)           as competencia,
    numAno::integer                                          as ano_competencia,
    numMes::integer                                          as mes_competencia,
    nullif(numParcela, '0')::integer                         as parcela,
    nullif(trim(txtTrecho), '')                              as trecho,
    nullif(urlDocumento, '')                                 as url_documento,

    _arquivo_origem                                          as arquivo_origem,
    _ingerido_em::timestamptz                                as ingerido_em
from fonte
