-- Migração 003: Configuração de Publicação Lógica para CDC (Change Data Capture)
-- Domínio: Cota para o Exercício da Atividade Parlamentar (CEAP) - Câmara dos Deputados
-- Entrega E2: Captura de mudanças a partir do Write-Ahead Log (WAL)

-- Cria a publicação lógica para a tabela transacional despesa_ceap
-- Essa publicação permite que o conector lógico receba o fluxo de eventos INSERT, UPDATE e DELETE.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication WHERE pubname = 'ceap_cdc_publication'
    ) THEN
        CREATE PUBLICATION ceap_cdc_publication FOR TABLE despesa_ceap;
        RAISE NOTICE 'Publicação lógica ceap_cdc_publication criada com sucesso para a tabela despesa_ceap.';
    ELSE
        RAISE NOTICE 'Publicação lógica ceap_cdc_publication já existe.';
    END IF;
END $$;

-- Configura a identidade de réplica como FULL na tabela despesa_ceap
-- Isso garante que eventos UPDATE e DELETE contenham tanto o estado anterior (before) quanto o novo (after)
ALTER TABLE despesa_ceap REPLICA IDENTITY FULL;

-- Tabela de auditoria para checkpoints e controle de offset do consumidor CDC
CREATE TABLE IF NOT EXISTS cdc_consumer_checkpoint (
    consumer_id VARCHAR(100) PRIMARY KEY,
    last_lsn VARCHAR(50) NOT NULL,
    last_applied_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    total_events_processed BIGINT DEFAULT 0
);
