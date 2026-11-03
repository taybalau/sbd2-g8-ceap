-- E3: gasto mensal por deputado pré-agregado, para a consulta de desvio da pergunta de gestão.
-- O plano da consulta original (docs/explain/antes.txt) gasta ~85% do tempo agregando
-- ~780 mil lançamentos a cada execução; esta view guarda o resultado (~24 mil linhas).
-- É recalculada por scripts/main.py logo após a carga (REFRESH MATERIALIZED VIEW).
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_gasto_mensal_deputado AS
SELECT
    id_deputado,
    sigla_uf_emissao   AS sigla_uf,
    ano_competencia,
    mes_competencia,
    codigo_legislatura,
    SUM(valor_liquido) AS gasto,
    COUNT(*)           AS qtd_lancamentos
FROM despesa_ceap
GROUP BY id_deputado, sigla_uf_emissao, ano_competencia, mes_competencia, codigo_legislatura;

CREATE INDEX IF NOT EXISTS idx_mv_gasto_mensal_uf_periodo
    ON mv_gasto_mensal_deputado (codigo_legislatura, sigla_uf, ano_competencia, mes_competencia);
