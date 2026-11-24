-- E4 (issue #7): destino operacional do ETL reverso — a FILA DE AUDITORIA de parlamentares em alerta.
--
-- Quem consome: o auditor (role `auditor`, quando existir). Ele abre a fila do dia
-- (alerta.vw_fila_auditoria), escolhe quem investigar, abre as notas no portal da Câmara e registra
-- o que decidiu em alerta.tratamento. Consultas de exemplo: etl_reverso/exemplo_auditor.sql.
--
-- Quem escreve: etl_reverso/publicar_alertas.py, agendado no Dagster (push, diário, depois do dbt).
-- A métrica vem pronta da camada semântica (semantico.met_parlamentar, coluna em_alerta): nada é
-- recalculado aqui.
--
-- Insert-only, como o resto do banco (ADR-0001): cada publicação é um retrato novo e cada decisão do
-- auditor é um evento novo. Nada é alterado ou apagado; um gatilho impede UPDATE e DELETE.
CREATE SCHEMA IF NOT EXISTS alerta;

-- Um retrato do top do ranking a cada publicação. A chave (referencia_dados, id_deputado) torna a
-- carga idempotente: republicar os mesmos dados não cria linha nova.
CREATE TABLE IF NOT EXISTS alerta.desvio_parlamentar (
    referencia_dados     TIMESTAMPTZ   NOT NULL,  -- ingestão mais recente dos CSVs usada (met_contexto.atualizado_em)
    id_deputado          INTEGER       NOT NULL,
    nome_parlamentar     VARCHAR(255)  NOT NULL,
    partido_atual        VARCHAR(50),
    sigla_uf             VARCHAR(2)    NOT NULL,
    posicao_ranking      INTEGER       NOT NULL,
    desvio_acumulado     NUMERIC(18,2) NOT NULL,  -- R$ acima da mediana da UF, somado mês a mês
    desvio_relativo      NUMERIC(10,4) NOT NULL,  -- 0,34 = 34% acima da mediana da UF
    meses_acima_mediana  INTEGER       NOT NULL,
    meses_com_gasto      INTEGER       NOT NULL,
    janela_inicio        DATE          NOT NULL,
    janela_fim           DATE          NOT NULL,
    publicado_em         TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (referencia_dados, id_deputado)
);

-- O que o auditor fez com cada alerta. Um evento por decisão; o último vale.
CREATE TABLE IF NOT EXISTS alerta.tratamento (
    id_tratamento     BIGSERIAL    PRIMARY KEY,
    id_deputado       INTEGER      NOT NULL,
    referencia_dados  TIMESTAMPTZ  NOT NULL,
    situacao          VARCHAR(30)  NOT NULL
        CHECK (situacao IN ('em_analise', 'sem_irregularidade', 'encaminhado')),
    observacao        TEXT,
    registrado_por    VARCHAR(100) NOT NULL DEFAULT current_user,
    registrado_em     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    FOREIGN KEY (referencia_dados, id_deputado)
        REFERENCES alerta.desvio_parlamentar (referencia_dados, id_deputado)
);

-- Registro de cada publicação do ETL reverso (quantas linhas vieram e quantas eram novas).
CREATE TABLE IF NOT EXISTS alerta.execucao (
    id_execucao       BIGSERIAL    PRIMARY KEY,
    referencia_dados  TIMESTAMPTZ  NOT NULL,
    linhas_recebidas  INTEGER      NOT NULL,
    linhas_novas      INTEGER      NOT NULL,
    origem            VARCHAR(100) NOT NULL,
    executado_em      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- A fila do dia: o retrato mais recente, com a última decisão do auditor sobre cada parlamentar
-- (decisões de retratos anteriores continuam valendo: o auditor não reabre o mesmo caso a cada dia).
CREATE OR REPLACE VIEW alerta.vw_fila_auditoria AS
WITH atual AS (
    SELECT * FROM alerta.desvio_parlamentar
    WHERE referencia_dados = (SELECT max(referencia_dados) FROM alerta.desvio_parlamentar)
),
ultima_decisao AS (
    SELECT DISTINCT ON (id_deputado) id_deputado, situacao, observacao, registrado_por, registrado_em
    FROM alerta.tratamento
    ORDER BY id_deputado, registrado_em DESC, id_tratamento DESC
)
SELECT a.posicao_ranking, a.id_deputado, a.nome_parlamentar, a.partido_atual, a.sigla_uf,
       a.desvio_acumulado, a.desvio_relativo, a.meses_acima_mediana, a.meses_com_gasto,
       a.janela_inicio, a.janela_fim, a.referencia_dados,
       COALESCE(d.situacao, 'pendente') AS situacao,
       d.observacao, d.registrado_por, d.registrado_em
FROM atual a
LEFT JOIN ultima_decisao d USING (id_deputado)
ORDER BY a.posicao_ranking;

-- Insert-only garantido pelo banco, não só pela convenção.
CREATE OR REPLACE FUNCTION alerta.impede_alteracao() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'alerta.% é insert-only (ADR-0001): registre um evento novo em vez de %',
        TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['desvio_parlamentar', 'tratamento', 'execucao'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS insert_only ON alerta.%I', t);
        EXECUTE format('CREATE TRIGGER insert_only BEFORE UPDATE OR DELETE ON alerta.%I '
                       'FOR EACH ROW EXECUTE FUNCTION alerta.impede_alteracao()', t);
    END LOOP;
END $$;

-- Privilégio mínimo, se as roles da migration 005 (controle de acesso, issue #10) existirem:
--   etl     só publica (lê e insere nos retratos e no registro de execução);
--   auditor lê a fila e registra decisões, sem poder mexer nos retratos.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'etl') THEN
        GRANT USAGE ON SCHEMA alerta TO etl;
        GRANT SELECT, INSERT ON alerta.desvio_parlamentar, alerta.execucao TO etl;
        GRANT USAGE ON SEQUENCE alerta.execucao_id_execucao_seq TO etl;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'auditor') THEN
        GRANT USAGE ON SCHEMA alerta TO auditor;
        GRANT SELECT ON alerta.desvio_parlamentar, alerta.execucao, alerta.vw_fila_auditoria TO auditor;
        GRANT SELECT, INSERT ON alerta.tratamento TO auditor;
        GRANT USAGE ON SEQUENCE alerta.tratamento_id_tratamento_seq TO auditor;
    END IF;
END $$;
