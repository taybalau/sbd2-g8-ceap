-- Salto de série (lacuna): toda competência entre a primeira e a última da 57ª Legislatura
-- precisa ter lançamentos. Um mês ausente é lote perdido na ingestão.
with meses as (
    select distinct competencia from {{ ref('fct_lancamento_ceap') }} where is_legislatura_alvo
),
esperado as (
    select unnest(generate_series(min(competencia), max(competencia), interval 1 month))::date as competencia
    from meses
)
select e.competencia from esperado e left join meses m using (competencia)
where m.competencia is null
