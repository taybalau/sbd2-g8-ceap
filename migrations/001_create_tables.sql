-- Migração 001: Criação da estrutura de tabelas transacionais (OLTP)
-- Domínio: Cota para o Exercício da Atividade Parlamentar (CEAP) - Câmara dos Deputados

-- Tabela de controle de versão das migrações
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(255) PRIMARY KEY,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 1. Tabela: parlamentar (contempla deputados federais e lideranças partidárias)
CREATE TABLE IF NOT EXISTS parlamentar (
    id_deputado INTEGER PRIMARY KEY,           -- nuDeputadoId oficial da Câmara
    nome_parlamentar VARCHAR(255) NOT NULL,     -- txNomeParlamentar
    cpf VARCHAR(14) NULL,                       -- cpf (nulo para lideranças)
    ide_cadastro VARCHAR(30) NULL,              -- ideCadastro
    nu_carteira_parlamentar VARCHAR(30) NULL,   -- nuCarteiraParlamentar
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabela: mandato_parlamentar (acompanha histórico de partido, UF e legislatura)
CREATE TABLE IF NOT EXISTS mandato_parlamentar (
    id_mandato SERIAL PRIMARY KEY,
    id_deputado INTEGER NOT NULL REFERENCES parlamentar(id_deputado) ON DELETE RESTRICT,
    sigla_partido VARCHAR(20) NOT NULL,
    sigla_uf VARCHAR(5) NOT NULL,
    codigo_legislatura INTEGER NOT NULL,        -- codLegislatura (ex: 56, 57)
    ano_legislatura INTEGER NULL,               -- nuLegislatura
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_mandato UNIQUE (id_deputado, sigla_partido, sigla_uf, codigo_legislatura)
);

-- 3. Tabela: fornecedor (estabelecimentos e prestadores de serviço)
CREATE TABLE IF NOT EXISTS fornecedor (
    id_fornecedor SERIAL PRIMARY KEY,
    cnpj_cpf VARCHAR(30) NULL,                  -- txtCNPJCPF (pode ser nulo ou genérico para cia aérea)
    razao_social VARCHAR(255) NOT NULL,         -- txtFornecedor
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_fornecedor_doc_nome UNIQUE (cnpj_cpf, razao_social)
);

-- 4. Tabela: categoria_despesa (subcotas orçamentárias da CEAP)
CREATE TABLE IF NOT EXISTS categoria_despesa (
    num_subcota INTEGER PRIMARY KEY,            -- numSubCota
    descricao VARCHAR(255) NOT NULL             -- txtDescricao
);

-- 5. Tabela: especificacao_despesa (detalhamento da subcota, ex: Veículos / Aeronaves)
CREATE TABLE IF NOT EXISTS especificacao_despesa (
    id_especificacao SERIAL PRIMARY KEY,
    num_subcota INTEGER NOT NULL REFERENCES categoria_despesa(num_subcota) ON DELETE RESTRICT,
    num_especificacao INTEGER NOT NULL,         -- numEspecificacaoSubCota
    descricao VARCHAR(255) NOT NULL,            -- txtDescricaoEspecificacao
    CONSTRAINT uk_especificacao UNIQUE (num_subcota, num_especificacao, descricao)
);

-- 6. Tabela: despesa_ceap (Livro-Razão Transacional / Insert-Only Ledger)
CREATE TABLE IF NOT EXISTS despesa_ceap (
    id_despesa BIGSERIAL PRIMARY KEY,
    ide_documento BIGINT NULL,                  -- ideDocumento (nulo ou 0 em passagens aéreas e telefonia)
    id_deputado INTEGER NOT NULL REFERENCES parlamentar(id_deputado) ON DELETE RESTRICT,
    id_fornecedor INTEGER NULL REFERENCES fornecedor(id_fornecedor) ON DELETE RESTRICT,
    num_subcota INTEGER NOT NULL REFERENCES categoria_despesa(num_subcota) ON DELETE RESTRICT,
    id_especificacao INTEGER NULL REFERENCES especificacao_despesa(id_especificacao) ON DELETE RESTRICT,
    
    -- Contexto da emissão
    sigla_partido_emissao VARCHAR(20) NULL,
    sigla_uf_emissao VARCHAR(5) NULL,
    codigo_legislatura INTEGER NOT NULL,
    
    -- Documento fiscal / comprobatório
    numero_documento VARCHAR(150) NULL,         -- txtNumero
    tipo_documento INTEGER NULL,                -- indTipoDocumento (0=NF, 1=Recibo, 2=Exterior, 4=NF-e)
    data_emissao TIMESTAMP NULL,                -- datEmissao (pode ser nula em telefonia ramal)
    
    -- Valores contábeis
    valor_documento NUMERIC(12, 2) NOT NULL,    -- vlrDocumento (pode ser negativo em reembolsos/cancelamentos)
    valor_glosa NUMERIC(12, 2) DEFAULT 0.00,    -- vlrGlosa (descontos e glosas)
    valor_liquido NUMERIC(12, 2) NOT NULL,      -- vlrLiquido (valor pago/reembolsado)
    
    -- Competência e controle
    mes_competencia SMALLINT NOT NULL CHECK (mes_competencia BETWEEN 1 AND 12),
    ano_competencia SMALLINT NOT NULL CHECK (ano_competencia >= 2000),
    parcela INTEGER DEFAULT 0,
    
    -- Detalhes adicionais
    passageiro VARCHAR(255) NULL,
    trecho VARCHAR(150) NULL,
    numero_lote INTEGER NULL,
    numero_ressarcimento VARCHAR(50) NULL,
    data_pagamento_restituicao DATE NULL,
    valor_restituicao NUMERIC(12, 2) NULL,
    url_documento TEXT NULL,
    
    -- Carimbo de auditoria do sistema de banco de dados
    data_ingestao TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. Tabela de Staging Temporária (UNLOGGED para máxima performance de ingestão COPY)
CREATE UNLOGGED TABLE IF NOT EXISTS stg_ceap_raw (
    txNomeParlamentar TEXT,
    cpf TEXT,
    ideCadastro TEXT,
    nuCarteiraParlamentar TEXT,
    nuLegislatura TEXT,
    sgUF TEXT,
    sgPartido TEXT,
    codLegislatura TEXT,
    numSubCota TEXT,
    txtDescricao TEXT,
    numEspecificacaoSubCota TEXT,
    txtDescricaoEspecificacao TEXT,
    txtFornecedor TEXT,
    txtCNPJCPF TEXT,
    txtNumero TEXT,
    indTipoDocumento TEXT,
    datEmissao TEXT,
    vlrDocumento TEXT,
    vlrGlosa TEXT,
    vlrLiquido TEXT,
    numMes TEXT,
    numAno TEXT,
    numParcela TEXT,
    txtPassageiro TEXT,
    txtTrecho TEXT,
    numLote TEXT,
    numRessarcimento TEXT,
    datPagamentoRestituicao TEXT,
    vlrRestituicao TEXT,
    nuDeputadoId TEXT,
    ideDocumento TEXT,
    urlDocumento TEXT
);

