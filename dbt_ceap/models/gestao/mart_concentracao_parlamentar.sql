-- RESPOSTA À 3ª PARTE DA PERGUNTA: quais categorias e fornecedores concentram os recursos
-- de cada deputado. GRÃO DECLARADO: uma linha por deputado × subcota × fornecedor.
-- Só competências comparáveis (fechadas e antes da ruptura de publicação), 57ª Legislatura, sem lideranças.
-- excesso_categoria_vs_uf: quanto o deputado gastou na subcota acima do que gastou, em média,
-- um deputado da mesma UF na mesma subcota no mesmo período (aponta a categoria que gera o desvio).
with l as (
    select f.*, p.sigla_uf
    from {{ ref('fct_lancamento_ceap') }} f
    join {{ ref('dim_parlamentar_scd') }} p using (sk_parlamentar)
    where f.is_legislatura_alvo and not f.is_lideranca and f.is_competencia_comparavel
),
dep_cat_forn as (
    select id_deputado, sigla_uf, num_subcota, sk_fornecedor,
           count(*) as qtd_lancamentos, sum(valor_liquido) as gasto
    from l group by all
),
dep_cat as (
    select id_deputado, sigla_uf, num_subcota, sum(gasto) as gasto_categoria
    from dep_cat_forn group by all
),
dep_total as (
    select id_deputado, sum(gasto) as gasto_deputado from dep_cat_forn group by 1
),
uf_cat as (
    -- média por deputado da UF (inclui com zero quem não gastou na subcota)
    select c.sigla_uf, c.num_subcota,
           sum(c.gasto_categoria) / max(n.qtd_deputados_uf) as media_categoria_uf
    from dep_cat c
    join (select sigla_uf, count(distinct id_deputado) as qtd_deputados_uf from l group by 1) n using (sigla_uf)
    group by all
)
select
    x.id_deputado,
    x.num_subcota,
    cat.descricao_subcota,
    x.sk_fornecedor,
    forn.nome_fornecedor,
    forn.documento_fornecedor,
    x.qtd_lancamentos,
    x.gasto                                            as gasto_fornecedor,
    c.gasto_categoria,
    t.gasto_deputado,
    x.gasto / nullif(c.gasto_categoria, 0)             as participacao_na_categoria,
    x.gasto / nullif(t.gasto_deputado, 0)              as participacao_no_deputado,
    c.gasto_categoria / nullif(t.gasto_deputado, 0)    as participacao_categoria_no_deputado,
    c.gasto_categoria - u.media_categoria_uf           as excesso_categoria_vs_uf
from dep_cat_forn x
join dep_cat c using (id_deputado, sigla_uf, num_subcota)
join dep_total t using (id_deputado)
join uf_cat u using (sigla_uf, num_subcota)
join {{ ref('dim_categoria_despesa') }} cat using (num_subcota)
join {{ ref('dim_fornecedor') }} forn using (sk_fornecedor)
