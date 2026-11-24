-- Como o auditor usa a fila de auditoria (consumidor do ETL reverso, issue #7).
-- Rode com:  docker compose exec -T db psql -U postgres -d ceap_oltp < etl_reverso/exemplo_auditor.sql
-- (quando a role `auditor` da migration 005 existir, conecte com ela: só lê a fila e registra decisões).

-- 1. A fila do dia: quem está em alerta e o que já foi decidido sobre cada um.
SELECT posicao_ranking, nome_parlamentar, partido_atual, sigla_uf,
       desvio_acumulado, round(desvio_relativo * 100) AS pct_acima_mediana, situacao
FROM alerta.vw_fila_auditoria;

-- 2. O auditor escolhe o 1º pendente, abre as notas no portal da Câmara e registra a decisão.
--    (dentro de uma transação desfeita no fim, para o exemplo não deixar rastro)
BEGIN;
INSERT INTO alerta.tratamento (id_deputado, referencia_dados, situacao, observacao)
SELECT id_deputado, referencia_dados, 'em_analise', 'notas de divulgação solicitadas ao gabinete'
FROM alerta.vw_fila_auditoria WHERE situacao = 'pendente' ORDER BY posicao_ranking LIMIT 1;

SELECT posicao_ranking, nome_parlamentar, situacao, observacao, registrado_por
FROM alerta.vw_fila_auditoria WHERE situacao <> 'pendente';

-- 3. Corrigir uma decisão é um evento novo; alterar a linha é bloqueado (insert-only, ADR-0001).
SAVEPOINT antes_do_update;
UPDATE alerta.tratamento SET situacao = 'sem_irregularidade';   -- ERRO esperado: insert-only
ROLLBACK TO SAVEPOINT antes_do_update;
ROLLBACK;

-- 4. Histórico: quando cada parlamentar entrou e saiu do alerta.
SELECT id_deputado, nome_parlamentar, min(referencia_dados) AS primeiro_alerta,
       max(referencia_dados) AS ultimo_alerta, count(*) AS publicacoes
FROM alerta.desvio_parlamentar GROUP BY 1, 2 ORDER BY ultimo_alerta DESC, primeiro_alerta;

-- 5. Saúde do ETL reverso: cada publicação, quantas linhas vieram e quantas eram novas.
SELECT executado_em, referencia_dados, linhas_recebidas, linhas_novas, origem
FROM alerta.execucao ORDER BY executado_em DESC LIMIT 10;
