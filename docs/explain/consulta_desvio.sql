-- Pergunta de gestão da E1, no OLTP: quais deputados da 57ª Legislatura mais gastam
-- acima da média mensal dos deputados da mesma UF (desvio acumulado, top 15).
WITH gasto_mes AS (
    SELECT id_deputado,
           sigla_uf_emissao     AS sigla_uf,
           ano_competencia,
           mes_competencia,
           SUM(valor_liquido)   AS gasto
    FROM despesa_ceap
    WHERE codigo_legislatura = 57
    GROUP BY id_deputado, sigla_uf_emissao, ano_competencia, mes_competencia
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
