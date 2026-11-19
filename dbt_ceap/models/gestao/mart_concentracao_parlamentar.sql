-- RESPOSTA À 3ª PARTE DA PERGUNTA: quais categorias e fornecedores concentram os recursos
-- de cada deputado. GRÃO DECLARADO: uma linha por deputado × subcota × fornecedor.
-- Só competências comparáveis (fechadas e antes da ruptura de publicação), 57ª Legislatura, sem lideranças.
-- excesso_categoria_vs_uf: quanto o deputado gastou na subcota acima da MEDIANA dos deputados da
-- mesma UF na mesma subcota no mesmo período (aponta a categoria que gera o desvio). Quem não gastou
-- na subcota entra com zero, então numa subcota que a maioria da UF não usa a mediana é 0.
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
deputados_uf as (
    select distinct id_deputado, sigla_uf from l
),
dep_total as (
    select id_deputado, sum(gasto) as gasto_deputado from dep_cat_forn group by 1
),
uf_cat as (
    -- mediana por deputado da UF: todo deputado da UF × toda subcota usada na UF, com zero
    -- para quem não gastou na subcota
    select d.sigla_uf, s.num_subcota,
           median(coalesce(c.gasto_categoria, 0))::decimal(38, 2) as mediana_categoria_uf
    from deputados_uf d
    join (select distinct sigla_uf, num_subcota from dep_cat) s using (sigla_uf)
    left join dep_cat c using (id_deputado, sigla_uf, num_subcota)
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
    (c.gasto_categoria - u.mediana_categoria_uf)::decimal(38, 2) as excesso_categoria_vs_uf
from dep_cat_forn x
join dep_cat c using (id_deputado, sigla_uf, num_subcota)
join dep_total t using (id_deputado)
join uf_cat u using (sigla_uf, num_subcota)
join {{ ref('dim_categoria_despesa') }} cat using (num_subcota)
join {{ ref('dim_fornecedor') }} forn using (sk_fornecedor)
