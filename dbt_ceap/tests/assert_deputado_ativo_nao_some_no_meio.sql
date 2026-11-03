{{ config(severity='warn') }}
-- Deputado com gasto em todos os meses e que some 3+ meses seguidos no meio do mandato,
-- voltando depois. Pode ser licença legítima (por isso warn), mas também lote perdido de
-- um gabinete. A lista vai para auditoria.<tabela> para conferência humana.
with m as (
    select distinct id_deputado, competencia
    from {{ ref('fct_lancamento_ceap') }}
    where is_legislatura_alvo and not is_lideranca and is_competencia_fechada
),
g as (
    select id_deputado, competencia,
           datediff('month', lag(competencia) over (partition by id_deputado order by competencia), competencia) - 1 as meses_sem_gasto
    from m
)
select * from g where meses_sem_gasto >= 3
