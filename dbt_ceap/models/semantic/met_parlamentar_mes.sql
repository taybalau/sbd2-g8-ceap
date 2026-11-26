-- CAMADA SEMÂNTICA — série mensal do parlamentar. GRÃO: deputado × competência comparável.
-- Mostra QUANDO o desvio acontece: constante (acima da mediana quase todo mês) ou concentrado em
-- poucos meses. Somada mês a mês, desvio_deputado_mes dá exatamente met_parlamentar.desvio_acumulado
-- (assert_semantico_desvio_consistente). Num mês de troca de partido o deputado tem duas versões na
-- Gold; aqui elas viram uma linha e os partidos do mês aparecem em ordem (ex.: PATRIOTA → PRD).
with versoes as (
    select
        g.id_deputado,
        g.competencia,
        g.sigla_uf,
        g.sigla_partido,
        p.numero_versao,
        g.gasto_deputado_mes,
        g.mediana_uf_mes,
        g.qtd_deputados_uf_mes,
        g.desvio_deputado_mes,
        g.z_deputado_mes
    from {{ ref('fct_gasto_mensal_parlamentar') }} g
    join {{ ref('dim_parlamentar_scd') }} p using (sk_parlamentar)
    where g.is_competencia_comparavel
),
mes as (
    select
        id_deputado,
        competencia,
        any_value(sigla_uf)                                         as sigla_uf,
        string_agg(sigla_partido, ' → ' order by numero_versao)     as partidos_no_mes,
        arg_max(sigla_partido, numero_versao)                       as partido_fim_do_mes,
        arg_min(sigla_partido, numero_versao)                       as partido_inicio_do_mes,
        any_value(gasto_deputado_mes)::decimal(38, 2)               as gasto_mes,
        any_value(mediana_uf_mes)::decimal(18, 4)                   as mediana_uf_mes,
        any_value(qtd_deputados_uf_mes)::bigint                     as qtd_deputados_uf_mes,
        any_value(desvio_deputado_mes)::decimal(38, 4)              as desvio_mes,
        any_value(z_deputado_mes)::double                           as z_mes
    from versoes
    group by id_deputado, competencia
)
select
    id_deputado,
    competencia,
    sigla_uf,
    partidos_no_mes,
    gasto_mes,
    mediana_uf_mes,
    qtd_deputados_uf_mes,
    desvio_mes,
    z_mes,
    desvio_mes > 0                                                  as acima_mediana,
    -- troca de partido: dentro do mês (duas versões) ou entre o mês anterior com gasto e este
    partido_inicio_do_mes <> partido_fim_do_mes
        or partido_inicio_do_mes <> coalesce(lag(partido_fim_do_mes) over (
               partition by id_deputado order by competencia), partido_inicio_do_mes)
                                                                    as trocou_de_partido_no_mes
from mes
