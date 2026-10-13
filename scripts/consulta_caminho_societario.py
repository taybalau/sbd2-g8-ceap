import os
import duckdb

def executar_consultas_caminho_societario(lakehouse_path: str = "./lakehouse"):
    """
    Executa e exibe no terminal as consultas analíticas que rastreiam o caminho societário
    desde o CNPJ emitente da nota fiscal até as holdings intermediárias e a Pessoa Física (CPF/UBO).
    """
    tabela_fato = os.path.join(lakehouse_path, "delta", "despesa_ceap").replace("\\", "/")
    tabela_empresas = os.path.join(lakehouse_path, "delta", "dim_fornecedor_cadastral").replace("\\", "/")
    tabela_cadeia = os.path.join(lakehouse_path, "delta", "dim_quadro_societario_ubo").replace("\\", "/")

    con = duckdb.connect()

    print("\n" + "=" * 115)
    print("      PAINEL DE AUDITORIA SOCIETÁRIA: RASTREAMENTO DE CNPJs ATÉ O BENEFICIÁRIO FINAL (UBO)")
    print("          (Atendimento à sugestão da docência — Cruzamento CEAP + Receita Federal do Brasil)")
    print("=" * 115)

    # -------------------------------------------------------------------------------------------------
    # CONSULTA 1: O CAMINHO EXPLICATIVO COMPLETO (Passo a Passo: CNPJ -> Holdings -> Sócio PF)
    # -------------------------------------------------------------------------------------------------
    print("\n[CONSULTA 1] RASTREAMENTO DO CAMINHO SOCIETÁRIO COMPLETO (HOLDINGS E GRAU DE PROFUNDIDADE)")
    print("Objetivo: Demonstrar a cadeia societária de cada empresa fornecedora até o controlador final.")
    print("-" * 115)

    query_caminho = f"""
        SELECT 
            c.cnpj_fornecedor_ceap AS "CNPJ Fornecedor",
            c.razao_social_fornecedor AS "Razão Social Fornecedor",
            c.grau_profundidade AS "Nível",
            c.tipo_socio AS "Tipo Sócio",
            c.doc_socio AS "Doc Sócio (CNPJ/CPF)",
            c.nome_socio AS "Nome do Sócio / Holding",
            c.caminho_societario AS "Caminho da Cadeia Societária"
        FROM delta_scan('{tabela_cadeia}') c
        ORDER BY c.cnpj_fornecedor_ceap, c.grau_profundidade;
    """
    try:
        df_caminho = con.execute(query_caminho).fetchall()
        print(f"{'CNPJ Fornecedor':<16} | {'Nível':<7} | {'Tipo':<15} | {'Doc Sócio':<16} | {'Caminho Societário'}")
        print("-" * 115)
        for r in df_caminho:
            print(f"{r[0]:<16} | Nível {r[2]} | {r[3]:<15} | {r[4]:<16} | {r[6]}")
    except Exception as e:
        print(f"Nota: Tabela Delta ainda não gerada ou vazia ({e}). Execute a ingestão primeiro.")

    # -------------------------------------------------------------------------------------------------
    # CONSULTA 2: O AGRUPAMENTO POR BENEFICIÁRIO FINAL (Vários CNPJs que pertencem à mesma pessoa física)
    # -------------------------------------------------------------------------------------------------
    print("\n\n" + "=" * 115)
    print("[CONSULTA 2] CONCENTRAÇÃO DE FORNECEDORES POR BENEFICIÁRIO FINAL (PESSOA FÍSICA)")
    print("Objetivo: Responder à pergunta da professora — múltiplos CNPJs que pertencem à mesma pessoa.")
    print("-" * 115)

    query_concentracao = f"""
        SELECT 
            c.nome_socio AS "Beneficiário Final (Pessoa Física)",
            c.doc_socio AS "CPF Mascarado",
            COUNT(DISTINCT c.cnpj_fornecedor_ceap) AS "Qtd CNPJs Controlados",
            STRING_AGG(DISTINCT c.razao_social_fornecedor, ' | ') AS "Empresas Fornecedoras do Grupo"
        FROM delta_scan('{tabela_cadeia}') c
        WHERE c.is_beneficiario_final = true
        GROUP BY c.nome_socio, c.doc_socio
        HAVING COUNT(DISTINCT c.cnpj_fornecedor_ceap) > 1
        ORDER BY "Qtd CNPJs Controlados" DESC;
    """
    try:
        df_conc = con.execute(query_concentracao).fetchall()
        print(f"{'Beneficiário Final (PF)':<26} | {'CPF Mascarado':<16} | {'CNPJs':<5} | {'Empresas Fornecedoras do Grupo'}")
        print("-" * 115)
        for r in df_conc:
            print(f"{r[0]:<26} | {r[1]:<16} | {r[2]:<5} | {r[3]}")
    except Exception as e:
        print(f"Erro ao executar Consulta 2: {e}")

    # -------------------------------------------------------------------------------------------------
    # CONSULTA 3: CRUZAMENTO DA CADEIA SOCIETÁRIA COM OS GASTOS REAIS DA CEAP (2023 a 2026)
    # -------------------------------------------------------------------------------------------------
    print("\n\n" + "=" * 115)
    print("[CONSULTA 3] GASTOS REAIS DA CÂMARA (CEAP) RASTREADOS ATÉ A PESSOA FÍSICA CONTROLADORA")
    print("Objetivo: Totalizar os recursos públicos recebidos por pessoa física através de todos os seus CNPJs.")
    print("-" * 115)

    query_gastos_ubo = f"""
        SELECT 
            c.nome_socio AS "Controlador Final (UBO)",
            c.doc_socio AS "CPF Mascarado",
            COUNT(DISTINCT d.id_despesa) AS "Total Notas CEAP",
            ROUND(SUM(d.valor_liquido), 2) AS "Total Pago pela Câmara (R$)"
        FROM delta_scan('{tabela_fato}') d
        JOIN delta_scan('{tabela_cadeia}') c 
          ON SUBSTR(regexp_replace(d.cnpj_cpf, '[^0-9]', '', 'g'), 1, 8) = SUBSTR(regexp_replace(c.cnpj_fornecedor_ceap, '[^0-9]', '', 'g'), 1, 8)
        WHERE c.is_beneficiario_final = true
        GROUP BY c.nome_socio, c.doc_socio
        ORDER BY "Total Pago pela Câmara (R$)" DESC;
    """
    try:
        df_gastos = con.execute(query_gastos_ubo).fetchall()
        print(f"{'Controlador Final (UBO)':<28} | {'CPF Mascarado':<16} | {'Notas':<8} | {'Total Acumulado Pago (R$)'}")
        print("-" * 115)
        for r in df_gastos:
            print(f"{r[0]:<28} | {r[1]:<16} | {r[2]:<8} | R$ {r[3]:,.2f}")
    except Exception as e:
        print(f"Nota: Tabela fato despesa_ceap no Delta Lake ainda não carregada ({e}).")

    print("=" * 115 + "\n")

if __name__ == "__main__":
    lakehouse_path = os.getenv("LAKEHOUSE_PATH", "./lakehouse")
    executar_consultas_caminho_societario(lakehouse_path)
