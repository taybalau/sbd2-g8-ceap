-- GRÃO DECLARADO: uma linha por deputado × versão SCD (partido vigente) × competência.
-- Escopo: só deputados (sem lideranças), só a 57ª Legislatura (jan/2023 é da 56ª),
-- todas as competências (a coluna is_competencia_fechada marca o que já maturou).
--
-- Métrica de referência: média do gasto mensal entre os deputados DA MESMA UF que tiveram
-- gasto naquela competência. Compara-se com a UF porque o teto da CEAP varia por estado
-- (o deslocamento até Brasília pesa de forma diferente).
--
-- Cuidado com dupla agregação: a média é calculada sobre o total do DEPUTADO no mês
-- (soma das versões), nunca sobre as linhas de versão. Num mês de troca de partido o
-- desvio do deputado é rateado entre as versões na proporção do gasto (desvio_alocado);
-- assert_desvio_alocado_reconcilia garante que o rateio soma exatamente o desvio do mês.
with base as (
    select
        f.id_deputado,
        f.sk_parlamentar,
        p.nome_parlamentar,
        p.sigla_partido,
        p.sigla_uf,
        f.competencia,
        bool_and(f.is_competencia_fechada) as is_competencia_fechada,
        bool_and(f.is_competencia_comparavel) as is_competencia_comparavel,
        count(*)                           as qtd_lancamentos,
        sum(f.valor_liquido)               as gasto_versao
    from {{ ref('fct_lancamento_ceap') }} f
    join {{ ref('dim_parlamentar_scd') }} p using (sk_parlamentar)
    where f.is_legislatura_alvo and not f.is_lideranca
    group by all
),
deputado_mes as (
    select
        *,
        sum(gasto_versao) over (partition by id_deputado, competencia) as gasto_deputado_mes,
        count(*)          over (partition by id_deputado, competencia) as versoes_no_mes
    from base
),
referencia_uf as (
    select
        sigla_uf,
        competencia,
        -- DECIMAL, não double: soma em ponto flutuante depende da ordem (threads) e fazia a
        -- Gold variar na 10ª casa entre execuções idênticas. Com DECIMAL, a Gold é bit a bit reprodutível.
        round(avg(gasto_deputado_mes), 4)::decimal(18, 4) as media_uf_mes,
        stddev_samp(gasto_deputado_mes)            as desvio_padrao_uf_mes,
        count(*)                                   as qtd_deputados_uf_mes
    from (select distinct id_deputado, sigla_uf, competencia, gasto_deputado_mes from deputado_mes)
    group by all
)
select
    d.id_deputado,
    d.sk_parlamentar,
    d.nome_parlamentar,
    d.sigla_partido,
    d.sigla_uf,
    d.competencia,
    d.is_competencia_fechada,
    d.is_competencia_comparavel,
    d.qtd_lancamentos,
    d.gasto_versao,
    d.gasto_deputado_mes,
    r.media_uf_mes,
    r.qtd_deputados_uf_mes,
    d.gasto_deputado_mes - r.media_uf_mes                                   as desvio_deputado_mes,
    (d.gasto_deputado_mes - r.media_uf_mes) / nullif(r.desvio_padrao_uf_mes, 0) as z_deputado_mes,
    -- gasto líquido zero no mês (débitos anulados por créditos): rateio igual entre versões
    round(case when d.gasto_deputado_mes = 0
         then (d.gasto_deputado_mes - r.media_uf_mes) / d.versoes_no_mes
         else (d.gasto_deputado_mes - r.media_uf_mes) * d.gasto_versao / d.gasto_deputado_mes
    end, 4)::decimal(18, 4)                                                  as desvio_alocado
from deputado_mes d
join referencia_uf r using (sigla_uf, competencia)
