-- E4 / issue #10: privilegio minimo e recorte de colunas no PostgreSQL 16.
-- Executar como administrador, em transacao (scripts/run_migrations.py ou psql -1).
-- Reaplicavel antes ou depois da 006; os GRANT do schema alerta pertencem a 006.
-- CPF e passageiro continuam na origem: remove-los exige adaptar a ingestao.

DO $$
DECLARE
    papel text;
BEGIN
    FOREACH papel IN ARRAY ARRAY['ceap_pipeline', 'ceap_auditor', 'ceap_consulta'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = papel) THEN
            EXECUTE format('CREATE ROLE %I NOLOGIN', papel);
        END IF;
        -- As roles sao grupos, nunca credenciais nem administradores.
        EXECUTE format('ALTER ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
                       'INHERIT NOREPLICATION NOBYPASSRLS', papel);
        -- Uma heranca preexistente pode contornar todos os REVOKE abaixo.
        -- Nao removemos silenciosamente memberships administradas fora desta migration.
        IF EXISTS (
            SELECT 1 FROM pg_auth_members m
            JOIN pg_roles r ON r.oid = m.member WHERE r.rolname = papel
        ) THEN
            RAISE EXCEPTION 'A role % herda outro papel; revise a associacao antes de aplicar a 005', papel;
        END IF;
    END LOOP;

    EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC, ceap_pipeline, ceap_auditor, ceap_consulta',
                   current_database());
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO ceap_pipeline, ceap_auditor, ceap_consulta',
                   current_database());
END $$;

-- PUBLIC soma privilegios a todos os usuarios. Sem CREATE, os perfis tambem nao
-- podem substituir objetos no search_path. Administracao continua com o dono.
REVOKE ALL ON SCHEMA public FROM PUBLIC, ceap_pipeline, ceap_auditor, ceap_consulta;
GRANT USAGE ON SCHEMA public TO ceap_pipeline, ceap_auditor, ceap_consulta;

CREATE OR REPLACE VIEW public.v_fornecedor_publico
WITH (security_barrier = true, security_invoker = false) AS
SELECT
    id_fornecedor,
    -- MEI pode trazer CPF no nome: cobrir tanto 00000000000 como 000.000.000-00.
    -- Os limites numericos preservam CNPJ de 14 digitos.
    regexp_replace(razao_social,
        '(?<![0-9])[0-9]{3}[.[:space:]]*[0-9]{3}[.[:space:]]*[0-9]{3}[-[:space:]]*[0-9]{2}(?![0-9])',
        '***', 'g') AS razao_social,
    CASE
        WHEN cnpj_cpf IS NULL OR btrim(cnpj_cpf) = '' THEN NULL
        WHEN length(regexp_replace(cnpj_cpf, '[^0-9]', '', 'g')) = 11
            THEN '***.' || substr(regexp_replace(cnpj_cpf, '[^0-9]', '', 'g'), 4, 3)
                 || '.' || substr(regexp_replace(cnpj_cpf, '[^0-9]', '', 'g'), 7, 3) || '-**'
        WHEN cnpj_cpf ~ '^[0-9./[:space:]-]+$'
             AND length(regexp_replace(cnpj_cpf, '[^0-9]', '', 'g')) = 14
            THEN cnpj_cpf
        -- Valores desconhecidos nao sao devolvidos crus ao consumidor.
        ELSE '[documento restrito]'
    END AS cnpj_cpf_exibicao
FROM public.fornecedor;

COMMENT ON VIEW public.v_fornecedor_publico IS
    'Consumo CEAP: CPF mascarado no documento e na razao social; CNPJ preservado. Nao anonimiza o titular.';

-- Refazer a matriz tambem corrige GRANTs amplos anteriores em public.
-- Um REVOKE na tabela NAO remove privilegios concedidos diretamente por coluna.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC, ceap_pipeline, ceap_auditor, ceap_consulta;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, ceap_pipeline, ceap_auditor, ceap_consulta;
DO $$
DECLARE
    objeto record;
BEGIN
    FOR objeto IN
        SELECT c.relname, string_agg(format('%I', a.attname), ', ' ORDER BY a.attnum) AS colunas
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
          AND a.attnum > 0 AND NOT a.attisdropped
        GROUP BY c.oid, c.relname
    LOOP
        EXECUTE format('REVOKE ALL (%s) ON TABLE public.%I '
                       'FROM PUBLIC, ceap_pipeline, ceap_auditor, ceap_consulta',
                       objeto.colunas, objeto.relname);
    END LOOP;
END $$;

-- Sem concessoes automaticas: uma tabela nova exige revisao explicita.
-- Estes defaults pertencem ao administrador que executa as migrations.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON TABLES FROM PUBLIC, ceap_pipeline, ceap_auditor, ceap_consulta;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON SEQUENCES FROM PUBLIC, ceap_pipeline, ceap_auditor, ceap_consulta;

-- Servicos: somente as operacoes usadas na carga normal e no checkpoint.
-- Migracoes, REFRESH da MV, reset de carga e replicacao logica sao administrativos.
GRANT SELECT, INSERT ON public.parlamentar, public.mandato_parlamentar,
    public.fornecedor, public.categoria_despesa, public.especificacao_despesa,
    public.despesa_ceap, public.cdc_consumer_checkpoint TO ceap_pipeline;
GRANT UPDATE ON public.parlamentar, public.categoria_despesa,
    public.cdc_consumer_checkpoint TO ceap_pipeline;
GRANT SELECT, INSERT, TRUNCATE ON public.stg_ceap_raw TO ceap_pipeline;
GRANT SELECT ON public.mv_gasto_mensal_deputado, public.v_fornecedor_publico TO ceap_pipeline;
GRANT USAGE ON SEQUENCE public.mandato_parlamentar_id_mandato_seq,
    public.fornecedor_id_fornecedor_seq, public.especificacao_despesa_id_especificacao_seq,
    public.despesa_ceap_id_despesa_seq TO ceap_pipeline;

-- Auditor: leitura das tabelas de negocio, inclusive identificadores restritos.
-- Nao le staging bruta, controle de migrations nem checkpoint; nao escreve no OLTP.
GRANT SELECT ON public.parlamentar, public.mandato_parlamentar, public.fornecedor,
    public.categoria_despesa, public.especificacao_despesa, public.despesa_ceap,
    public.mv_gasto_mensal_deputado, public.v_fornecedor_publico TO ceap_auditor;

-- Consulta: lista positiva de colunas. Nunca conceder SELECT na tabela inteira.
-- SELECT * em parlamentar/despesa_ceap falha, mesmo que as tabelas estejam vazias.
GRANT SELECT (id_deputado, nome_parlamentar, ide_cadastro, created_at)
    ON public.parlamentar TO ceap_consulta;
GRANT SELECT (id_mandato, id_deputado, sigla_partido, sigla_uf,
    codigo_legislatura, ano_legislatura, created_at)
    ON public.mandato_parlamentar TO ceap_consulta;
GRANT SELECT (num_subcota, descricao) ON public.categoria_despesa TO ceap_consulta;
GRANT SELECT (id_especificacao, num_subcota, num_especificacao, descricao)
    ON public.especificacao_despesa TO ceap_consulta;
GRANT SELECT (id_despesa, ide_documento, id_deputado, id_fornecedor, num_subcota,
    id_especificacao, sigla_partido_emissao, sigla_uf_emissao, codigo_legislatura,
    numero_documento, tipo_documento, data_emissao, valor_documento, valor_glosa,
    valor_liquido, mes_competencia, ano_competencia, parcela, trecho, numero_lote,
    numero_ressarcimento, data_pagamento_restituicao, valor_restituicao,
    url_documento, data_ingestao)
    ON public.despesa_ceap TO ceap_consulta;
GRANT SELECT (id_deputado, sigla_uf, ano_competencia, mes_competencia,
    codigo_legislatura, gasto, qtd_lancamentos)
    ON public.mv_gasto_mensal_deputado TO ceap_consulta;
GRANT SELECT ON public.v_fornecedor_publico TO ceap_consulta;

-- Nenhum GRANT em alerta: a migration 006 define publicacao e decisoes.
-- Nenhum GRANT OPTION, DDL, DELETE, REPLICATION ou privilegio de superusuario.
