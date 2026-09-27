import os
import time
import psycopg2

SQL_POPULATE_PARLAMENTAR = """
INSERT INTO parlamentar (id_deputado, nome_parlamentar, cpf, ide_cadastro, nu_carteira_parlamentar)
SELECT DISTINCT ON (NULLIF(nuDeputadoId, '')::INTEGER)
    NULLIF(nuDeputadoId, '')::INTEGER AS id_deputado,
    COALESCE(NULLIF(TRIM(txNomeParlamentar), ''), 'PARLAMENTAR NÃO IDENTIFICADO') AS nome_parlamentar,
    NULLIF(TRIM(cpf), '') AS cpf,
    NULLIF(TRIM(ideCadastro), '') AS ide_cadastro,
    NULLIF(TRIM(nuCarteiraParlamentar), '') AS nu_carteira_parlamentar
FROM stg_ceap_raw
WHERE NULLIF(nuDeputadoId, '') IS NOT NULL
ON CONFLICT (id_deputado) DO UPDATE SET
    nome_parlamentar = EXCLUDED.nome_parlamentar,
    cpf = COALESCE(EXCLUDED.cpf, parlamentar.cpf),
    ide_cadastro = COALESCE(EXCLUDED.ide_cadastro, parlamentar.ide_cadastro),
    nu_carteira_parlamentar = COALESCE(EXCLUDED.nu_carteira_parlamentar, parlamentar.nu_carteira_parlamentar);
"""

SQL_POPULATE_MANDATO = """
INSERT INTO mandato_parlamentar (id_deputado, sigla_partido, sigla_uf, codigo_legislatura, ano_legislatura)
SELECT DISTINCT
    NULLIF(nuDeputadoId, '')::INTEGER AS id_deputado,
    COALESCE(NULLIF(TRIM(sgPartido), ''), 'SEM PARTIDO') AS sigla_partido,
    COALESCE(NULLIF(TRIM(sgUF), ''), 'NA') AS sigla_uf,
    COALESCE(NULLIF(codLegislatura, '')::INTEGER, 57) AS codigo_legislatura,
    NULLIF(nuLegislatura, '')::INTEGER AS ano_legislatura
FROM stg_ceap_raw
WHERE NULLIF(nuDeputadoId, '') IS NOT NULL
ON CONFLICT (id_deputado, sigla_partido, sigla_uf, codigo_legislatura) DO NOTHING;
"""

SQL_POPULATE_CATEGORIA = """
INSERT INTO categoria_despesa (num_subcota, descricao)
SELECT DISTINCT ON (NULLIF(numSubCota, '')::INTEGER)
    NULLIF(numSubCota, '')::INTEGER AS num_subcota,
    COALESCE(NULLIF(TRIM(txtDescricao), ''), 'OUTRAS DESPESAS') AS descricao
FROM stg_ceap_raw
WHERE NULLIF(numSubCota, '') IS NOT NULL
ON CONFLICT (num_subcota) DO UPDATE SET
    descricao = EXCLUDED.descricao;
"""

SQL_POPULATE_ESPECIFICACAO = """
INSERT INTO especificacao_despesa (num_subcota, num_especificacao, descricao)
SELECT DISTINCT
    NULLIF(numSubCota, '')::INTEGER AS num_subcota,
    COALESCE(NULLIF(numEspecificacaoSubCota, '')::INTEGER, 0) AS num_especificacao,
    COALESCE(NULLIF(TRIM(txtDescricaoEspecificacao), ''), 'Não especificado') AS descricao
FROM stg_ceap_raw
WHERE NULLIF(numSubCota, '') IS NOT NULL
ON CONFLICT (num_subcota, num_especificacao, descricao) DO NOTHING;
"""

SQL_POPULATE_FORNECEDOR = """
INSERT INTO fornecedor (cnpj_cpf, razao_social)
SELECT DISTINCT
    NULLIF(TRIM(txtCNPJCPF), '') AS cnpj_cpf,
    COALESCE(NULLIF(TRIM(txtFornecedor), ''), 'FORNECEDOR NÃO INFORMADO') AS razao_social
FROM stg_ceap_raw
ON CONFLICT (cnpj_cpf, razao_social) DO NOTHING;
"""

SQL_POPULATE_DESPESA = """
INSERT INTO despesa_ceap (
    ide_documento,
    id_deputado,
    id_fornecedor,
    num_subcota,
    id_especificacao,
    sigla_partido_emissao,
    sigla_uf_emissao,
    codigo_legislatura,
    numero_documento,
    tipo_documento,
    data_emissao,
    valor_documento,
    valor_glosa,
    valor_liquido,
    mes_competencia,
    ano_competencia,
    parcela,
    passageiro,
    trecho,
    numero_lote,
    numero_ressarcimento,
    data_pagamento_restituicao,
    valor_restituicao,
    url_documento
)
SELECT
    NULLIF(s.ideDocumento, '')::BIGINT AS ide_documento,
    NULLIF(s.nuDeputadoId, '')::INTEGER AS id_deputado,
    f.id_fornecedor,
    NULLIF(s.numSubCota, '')::INTEGER AS num_subcota,
    e.id_especificacao,
    NULLIF(TRIM(s.sgPartido), '') AS sigla_partido_emissao,
    NULLIF(TRIM(s.sgUF), '') AS sigla_uf_emissao,
    COALESCE(NULLIF(s.codLegislatura, '')::INTEGER, 57) AS codigo_legislatura,
    NULLIF(TRIM(s.txtNumero), '') AS numero_documento,
    NULLIF(s.indTipoDocumento, '')::INTEGER AS tipo_documento,
    CASE 
        WHEN NULLIF(s.datEmissao, '') IS NOT NULL AND s.datEmissao ~ '^\d{4}-\d{2}-\d{2}' 
        THEN s.datEmissao::TIMESTAMP 
        ELSE NULL 
    END AS data_emissao,
    COALESCE(NULLIF(s.vlrDocumento, '')::NUMERIC(12, 2), 0.00) AS valor_documento,
    COALESCE(NULLIF(s.vlrGlosa, '')::NUMERIC(12, 2), 0.00) AS valor_glosa,
    COALESCE(NULLIF(s.vlrLiquido, '')::NUMERIC(12, 2), 0.00) AS valor_liquido,
    COALESCE(NULLIF(s.numMes, '')::SMALLINT, 1) AS mes_competencia,
    COALESCE(NULLIF(s.numAno, '')::SMALLINT, 2023) AS ano_competencia,
    COALESCE(NULLIF(s.numParcela, '')::INTEGER, 0) AS parcela,
    NULLIF(TRIM(s.txtPassageiro), '') AS passageiro,
    NULLIF(TRIM(s.txtTrecho), '') AS trecho,
    NULLIF(s.numLote, '')::INTEGER AS numero_lote,
    NULLIF(TRIM(s.numRessarcimento), '') AS numero_ressarcimento,
    CASE 
        WHEN NULLIF(s.datPagamentoRestituicao, '') IS NOT NULL AND s.datPagamentoRestituicao ~ '^\d{4}-\d{2}-\d{2}' 
        THEN s.datPagamentoRestituicao::DATE 
        ELSE NULL 
    END AS data_pagamento_restituicao,
    NULLIF(s.vlrRestituicao, '')::NUMERIC(12, 2) AS valor_restituicao,
    NULLIF(TRIM(s.urlDocumento), '') AS url_documento
FROM stg_ceap_raw s
LEFT JOIN fornecedor f 
    ON f.razao_social = COALESCE(NULLIF(TRIM(s.txtFornecedor), ''), 'FORNECEDOR NÃO INFORMADO')
   AND (f.cnpj_cpf = NULLIF(TRIM(s.txtCNPJCPF), '') OR (f.cnpj_cpf IS NULL AND NULLIF(TRIM(s.txtCNPJCPF), '') IS NULL))
LEFT JOIN especificacao_despesa e 
    ON e.num_subcota = NULLIF(s.numSubCota, '')::INTEGER
   AND e.num_especificacao = COALESCE(NULLIF(s.numEspecificacaoSubCota, '')::INTEGER, 0)
   AND e.descricao = COALESCE(NULLIF(TRIM(s.txtDescricaoEspecificacao), ''), 'Não especificado')
WHERE NULLIF(s.nuDeputadoId, '') IS NOT NULL;
"""

def ingest_csv_files(conn, csv_files: dict[int, str]):
    """
    Realiza a ingestão de múltiplos arquivos CSV de forma eficiente usando
    PostgreSQL COPY em tabela de staging unlogged, seguida de transformações relacionais ACID.
    """
    total_start = time.time()
    print("[INGESTAO] Iniciando processamento dos dados da CEAP...")

    with conn.cursor() as cur:
        for year, filepath in sorted(csv_files.items()):
            year_start = time.time()
            print(f"\n[INGESTAO] Processando {filepath} (Ano {year})...")

            # 1. Limpa tabela de staging
            cur.execute("TRUNCATE TABLE stg_ceap_raw;")

            # 2. Carrega CSV via PostgreSQL COPY (extremamente rápido)
            print(f"[INGESTAO] Executando COPY para staging do arquivo do ano {year}...")
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                cur.copy_expert(
                    sql="COPY stg_ceap_raw FROM STDIN WITH (FORMAT csv, HEADER true, DELIMITER ';', QUOTE '\"');",
                    file=f
                )

            cur.execute("SELECT count(*) FROM stg_ceap_raw;")
            staging_count = cur.fetchone()[0]
            print(f"[INGESTAO] Linhas carregadas no staging: {staging_count}")

            # 3. Popula dimensões e fatos via SQL
            print("[INGESTAO] Populando parlamentares e mandatos...")
            cur.execute(SQL_POPULATE_PARLAMENTAR)
            cur.execute(SQL_POPULATE_MANDATO)

            print("[INGESTAO] Populando categorias e especificações...")
            cur.execute(SQL_POPULATE_CATEGORIA)
            cur.execute(SQL_POPULATE_ESPECIFICACAO)

            print("[INGESTAO] Populando fornecedores...")
            cur.execute(SQL_POPULATE_FORNECEDOR)

            print("[INGESTAO] Populando tabela transacional despesa_ceap...")
            cur.execute(SQL_POPULATE_DESPESA)

            # 4. Limpa staging após concluir o ano
            cur.execute("TRUNCATE TABLE stg_ceap_raw;")
            conn.commit()

            year_elapsed = time.time() - year_start
            print(f"[INGESTAO] Ano {year} concluído com sucesso em {year_elapsed:.2f}s!")

        # Relatório de contagem final
        print("\n================ RESUMO DO BANCO RELACIONAL ================")
        cur.execute("SELECT count(*) FROM parlamentar;")
        print(f"Total de Parlamentares cadastrados: {cur.fetchone()[0]}")

        cur.execute("SELECT count(*) FROM fornecedor;")
        print(f"Total de Fornecedores cadastrados:  {cur.fetchone()[0]}")

        cur.execute("SELECT count(*) FROM categoria_despesa;")
        print(f"Total de Categorias de Despesa:    {cur.fetchone()[0]}")

        cur.execute("SELECT count(*) FROM despesa_ceap;")
        print(f"Total de Registros de Despesa:      {cur.fetchone()[0]}")

        cur.execute("SELECT sum(valor_liquido) FROM despesa_ceap;")
        total_pago = cur.fetchone()[0] or 0.00
        print(f"Volume Total Pago na Legislatura:   R$ {total_pago:,.2f}")
        print("============================================================\n")

    total_elapsed = time.time() - total_start
    print(f"[INGESTAO] Carga completa de todos os anos finalizada em {total_elapsed:.2f}s!")

if __name__ == "__main__":
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ceap_oltp")
    with psycopg2.connect(db_url) as conn:
        sample_files = {2023: "base-dados/Ano-2023.csv"}
        ingest_csv_files(conn, sample_files)
