-- Mesma pergunta, lendo o gasto mensal pré-agregado (mv_gasto_mensal_deputado, migração 004).
WITH gasto_mes AS (
    SELECT id_deputado, sigla_uf, ano_competencia, mes_competencia, gasto
    FROM mv_gasto_mensal_deputado
    WHERE codigo_legislatura = 57
),
media_uf AS (
    SELECT sigla_uf, ano_competencia, mes_competencia, AVG(gasto) AS media
    FROM gasto_mes
    GROUP BY sigla_uf, ano_competencia, mes_competencia
)
SELECT g.id_deputado,
       SUM(g.gasto - m.media)                       AS desvio_acumulado,
       COUNT(*) FILTER (WHERE g.gasto > m.media)    AS meses_acima_da_media
FROM gasto_mes g
JOIN media_uf m USING (sigla_uf, ano_competencia, mes_competencia)
GROUP BY g.id_deputado
ORDER BY desvio_acumulado DESC
LIMIT 15;
