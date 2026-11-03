-- GRÃO DECLARADO: uma linha por lançamento publicado pela Câmara nos CSVs da CEAP —
-- um documento fiscal, OU um trecho de bilhete aéreo (SIGEPA repete o mesmo ideDocumento
-- para vários trechos e meses), OU um crédito/compensação (valor negativo).
-- Chave: id_lancamento (hash de todos os campos de origem). NÃO use id_documento_camara
-- como chave: ele é 0/nulo em 30.357 linhas e se repete em até 9 linhas.
--
-- Este modelo não pode mudar a contagem nem a soma em relação à Bronze; o teste
-- assert_fato_reconcilia_com_bronze garante que nenhuma junção duplicou linhas.
with l as (
    select * from {{ ref('stg_ceap__lancamento') }}
),
p as (
    select * from {{ ref('dim_parlamentar_scd') }}
),
cal as (
    select data, is_competencia_fechada, is_competencia_comparavel from {{ ref('dim_calendario') }}
)
select
    l.id_lancamento,
    case when l.is_lideranca then md5('lid|' || l.id_deputado) else p.sk_parlamentar end
                                                                     as sk_parlamentar,
    md5(coalesce(l.documento_fornecedor, 'SEM-DOC:' || upper(l.nome_fornecedor_publicado))) as sk_fornecedor,
    l.num_subcota,
    l.id_deputado,
    l.data_emissao,
    coalesce(l.data_emissao, l.competencia)                          as data_referencia_scd,
    l.competencia,
    l.ano_competencia,
    l.mes_competencia,
    l.codigo_legislatura,
    -- Partido como publicado no CSV (já sobrescrito pela Câmara). Mantido só para auditoria:
    -- NÃO use para agrupar por partido; use dim_parlamentar_scd.sigla_partido.
    l.sigla_partido_publicada,
    l.sigla_uf_publicada,
    l.id_documento_camara,
    l.numero_documento,
    l.tipo_documento,
    l.trecho,
    l.url_documento,

    l.valor_documento,
    l.valor_glosa,
    l.valor_liquido,
    l.valor_restituicao,

    l.is_lideranca,
    l.codigo_legislatura = {{ var('codigo_legislatura') }}         as is_legislatura_alvo,
    coalesce(cal.is_competencia_fechada, false)                      as is_competencia_fechada,
    coalesce(cal.is_competencia_comparavel, false)                   as is_competencia_comparavel,
    l.valor_liquido < 0                                              as is_credito,
    -- Sujeira real da fonte: liquido <> documento - glosa. Excluem-se os créditos das subcotas
    -- de compensação (auxílio-moradia, bilhetes), que seguem outra regra de lançamento.
    abs(l.valor_documento - l.valor_glosa - l.valor_liquido) > 0.01
        and not (l.valor_liquido < 0 and coalesce(cat.permite_valor_negativo, false))
                                                                     as is_valor_inconsistente,
    l.arquivo_origem,
    l.ingerido_em
from l
-- SCD2: versão vigente na DATA DO GASTO (emissão; sem emissão, o 1º dia da competência).
-- Nunca juntar só por id: isso pegaria o partido atual (sobrescrita).
left join p
    on  not l.is_lideranca
    and p.id_cadastro_camara = l.id_cadastro_camara
    and coalesce(l.data_emissao, l.competencia)::timestamp >= p.valido_de
    and coalesce(l.data_emissao, l.competencia)::timestamp <  p.valido_ate
left join cal
    on cal.data = l.competencia
left join {{ ref('dim_categoria_despesa') }} cat
    on cat.num_subcota = l.num_subcota
