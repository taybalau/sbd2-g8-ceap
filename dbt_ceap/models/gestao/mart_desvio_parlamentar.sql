-- RESPOSTA À 1ª PARTE DA PERGUNTA: quais parlamentares têm maior desvio acima da média mensal.
-- GRÃO DECLARADO: uma linha por deputado (57ª Legislatura, só competências comparáveis (fechadas e antes da ruptura de publicação)).
-- desvio_acumulado = soma, mês a mês, de (gasto do deputado − média da UF no mês).
with mensal as (
    -- sem nome/partido aqui: eles variam entre versões e quebrariam o grão (1 linha por deputado)
    select distinct
        id_deputado, competencia,
        gasto_deputado_mes, media_uf_mes, desvio_deputado_mes, z_deputado_mes
    from {{ ref('fct_gasto_mensal_parlamentar') }}
    where is_competencia_comparavel
),
partidos as (
    select
        id_deputado,
        arg_max(nome_parlamentar, numero_versao)                  as nome_parlamentar,
        arg_max(sigla_uf, numero_versao)                          as sigla_uf,
        string_agg(sigla_partido, ' → ' order by numero_versao)   as trajetoria_partidaria,
        arg_max(sigla_partido, numero_versao)                     as partido_atual,
        count(*) > 1                                              as trocou_de_partido
    from {{ ref('dim_parlamentar_scd') }}
    -- só versões vigentes em algum momento da 57ª Legislatura (exclui PSL/DEM etc. da 56ª)
    where not is_lideranca and valido_ate > timestamp '2023-02-01'
    group by 1
),
concentracao as (
    -- HHI dos fornecedores do deputado (0–1): perto de 1 = gasto concentrado em poucos CNPJs
    select id_deputado, sum(participacao * participacao) as hhi_fornecedores
    from (
        select id_deputado, sk_fornecedor,
               sum(valor_liquido) / sum(sum(valor_liquido)) over (partition by id_deputado) as participacao
        from {{ ref('fct_lancamento_ceap') }}
        where is_legislatura_alvo and not is_lideranca and is_competencia_comparavel
        group by 1, 2
    )
    group by 1
)
select
    m.id_deputado,
    p.nome_parlamentar,
    p.sigla_uf,
    p.partido_atual,
    p.trajetoria_partidaria,
    p.trocou_de_partido,
    count(*)                                            as meses_com_gasto,
    sum(m.gasto_deputado_mes)                           as gasto_total,
    round(avg(m.gasto_deputado_mes), 2)                 as gasto_medio_mensal,
    round(avg(m.media_uf_mes), 2)                       as media_uf_mensal,
    sum(m.desvio_deputado_mes)                          as desvio_acumulado,
    sum(m.desvio_deputado_mes) / nullif(sum(m.media_uf_mes), 0) as desvio_relativo,
    count(*) filter (where m.desvio_deputado_mes > 0)   as meses_acima_media,
    round(avg(m.z_deputado_mes), 6)                     as z_medio,
    round(c.hhi_fornecedores, 6)                        as hhi_fornecedores,
    rank() over (order by sum(m.desvio_deputado_mes) desc) as posicao_ranking
from mensal m
join partidos p using (id_deputado)
left join concentracao c using (id_deputado)
group by all
