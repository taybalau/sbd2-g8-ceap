-- Grão: uma linha por dia civil. Datas de emissão fora do intervalo ficam sem par
-- e são capturadas pelo teste de relacionamento (severidade warn).
-- is_competencia_comparavel: fechada E anterior à primeira ruptura de publicação registrada
-- em seeds/ruptura_publicacao.csv. É a janela usada nos rankings da Gold.
with limites as (
    select
        (select max(competencia) from {{ ref('stg_ceap__lancamento') }}) as ultima_competencia_publicada,
        (select min(competencia_inicio) from {{ ref('ruptura_publicacao') }}) as primeira_ruptura
),
dias as (
    select unnest(generate_series(date '2022-01-01', date '2026-12-31', interval 1 day))::date as data
)
select
    d.data,
    year(d.data)                              as ano,
    month(d.data)                             as mes,
    date_trunc('month', d.data)::date         as competencia,
    isodow(d.data)                            as dia_semana_iso,
    isodow(d.data) in (6, 7)                  as is_fim_de_semana,
    date_trunc('month', d.data)::date
        <= (l.ultima_competencia_publicada - to_months({{ var('meses_maturacao') }}))::date
                                              as is_competencia_fechada,
    date_trunc('month', d.data)::date
        <= (l.ultima_competencia_publicada - to_months({{ var('meses_maturacao') }}))::date
    and date_trunc('month', d.data)::date < coalesce(l.primeira_ruptura, date '9999-12-31')
                                              as is_competencia_comparavel
from dias d
cross join limites l
