-- CAMADA SEMÂNTICA — lançamentos do parlamentar com o link para o documento na Câmara.
-- GRÃO: um lançamento publicado (id_lancamento), no mesmo recorte do ranking: 57ª Legislatura, sem
-- lideranças, só competências comparáveis. É o fim da linhagem: do desvio do painel até a nota.
--
-- LGPD (docs/lgpd.md): CPF de fornecedor pessoa física mascarado no documento e no nome (MEI);
-- nome do passageiro e trecho do bilhete ficam de fora (o passageiro pode não ser o deputado).
-- O link do documento também fica de fora quando o fornecedor é pessoa física: o recibo digitalizado
-- traz o CPF completo, e o link desfaria a máscara com um clique (link_omitido_lgpd marca esses casos).
-- O consumidor deve filtrar por id_deputado (e num_subcota): a view tem centenas de milhares de linhas e o DuckDB
-- empurra esse filtro para antes da janela de posicao_valor, que é particionada pelas mesmas colunas.
select
    f.id_lancamento,
    f.id_deputado,
    f.num_subcota,
    cat.descricao_subcota,
    f.competencia,
    f.data_emissao,
    f.sk_fornecedor,
    {{ mascara_cpf_no_texto('forn.nome_fornecedor') }}              as nome_fornecedor,
    {{ mascara_cpf('forn.documento_fornecedor') }}                  as documento_fornecedor,
    case f.tipo_documento
        when 0 then 'nota fiscal'
        when 4 then 'nota fiscal eletrônica'
        when 1 then 'recibo'
        when 2 then 'despesa no exterior'
        else 'outro'
    end                                                             as tipo_documento,
    f.valor_liquido,
    case when length(forn.documento_fornecedor) = 11 then null else f.url_documento end as url_documento,
    f.url_documento is not null                                     as tem_documento_publicado,
    f.url_documento is not null and length(forn.documento_fornecedor) = 11 as link_omitido_lgpd,
    row_number() over (partition by f.id_deputado, f.num_subcota
                       order by f.valor_liquido desc, f.id_lancamento) as posicao_valor
from {{ ref('fct_lancamento_ceap') }} f
join {{ ref('dim_categoria_despesa') }} cat using (num_subcota)
join {{ ref('dim_fornecedor') }} forn using (sk_fornecedor)
where f.is_legislatura_alvo and not f.is_lideranca and f.is_competencia_comparavel
