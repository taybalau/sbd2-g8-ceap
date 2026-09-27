import os
import time
import psycopg2
from download_data import ensure_data_available
from run_migrations import apply_migrations
from ingest_ceap import ingest_csv_files

def get_connection(retries=15, delay=2):
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "ceap_oltp")
    db_user = os.getenv("DB_USER", "postgres")
    db_pass = os.getenv("DB_PASSWORD", "postgres")

    print(f"[ORQUESTRAÇÃO] Aguardando banco de dados {db_host}:{db_port}/{db_name} ficar pronto...")

    for i in range(retries):
        try:
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                dbname=db_name,
                user=db_user,
                password=db_pass
            )
            print("[ORQUESTRAÇÃO] Conexão com o PostgreSQL estabelecida com sucesso!")
            return conn
        except psycopg2.OperationalError as e:
            print(f"[ORQUESTRAÇÃO] Banco ainda não disponível ({i+1}/{retries}). Aguardando {delay}s...")
            time.sleep(delay)

    raise RuntimeError("[ORQUESTRAÇÃO] Não foi possível conectar ao banco de dados dentro do tempo limite.")

def test_management_query(conn):
    print("\n" + "=" * 90)
    print("        PAINEL DE VALIDAÇÃO DAS PERGUNTAS DE GESTÃO DA SQUAD G8 (CEAP 2023-2026)")
    print("=" * 90)

    with conn.cursor() as cur:
        # 1. Custo médio mensal por deputado
        cur.execute("""
            SELECT ROUND(AVG(gasto_mensal), 2)
            FROM (
                SELECT id_deputado, ano_competencia, mes_competencia, SUM(valor_liquido) AS gasto_mensal
                FROM despesa_ceap
                GROUP BY id_deputado, ano_competencia, mes_competencia
            ) sub;
        """)
        custo_medio = cur.fetchone()[0] or 0.00
        print(f"\n[PERGUNTA 1] Qual é o custo médio mensal da Cota Parlamentar por deputado federal?")
        print(f"  -> R$ {custo_medio:,.2f} / mês por deputado ativo\n")

        # 2. Ranking dos parlamentares que mais utilizam a cota
        print("[PERGUNTA 2] Quais são os parlamentares que mais utilizam a Cota Parlamentar? (Top 5)")
        cur.execute("""
            SELECT 
                p.nome_parlamentar,
                d.sigla_partido_emissao,
                d.sigla_uf_emissao,
                COUNT(d.id_despesa),
                ROUND(AVG(d.valor_liquido), 2),
                ROUND(SUM(d.valor_liquido), 2)
            FROM despesa_ceap d
            JOIN parlamentar p ON p.id_deputado = d.id_deputado
            GROUP BY p.nome_parlamentar, d.sigla_partido_emissao, d.sigla_uf_emissao
            ORDER BY SUM(d.valor_liquido) DESC
            LIMIT 5;
        """)
        rows_dep = cur.fetchall()
        print(f"  {'Parlamentar':<32} | {'Partido':<7} | {'UF':<3} | {'Notas':<6} | {'Ticket Médio':<12} | {'Total Gasto':<14}")
        print("  " + "-" * 86)
        for r in rows_dep:
            print(f"  {r[0]:<32} | {r[1] or 'N/A':<7} | {r[2] or 'N/A':<3} | {r[3]:<6} | R$ {r[4]:<9} | R$ {r[5]:<11}")
        print()

        # 3. Maiores fornecedores recebedores
        print("[PERGUNTA 3] Quais empresas/fornecedores são os maiores recebedores da Cota? (Top 3)")
        cur.execute("""
            SELECT f.razao_social, COUNT(d.id_despesa), ROUND(SUM(d.valor_liquido), 2)
            FROM despesa_ceap d
            JOIN fornecedor f ON f.id_fornecedor = d.id_fornecedor
            GROUP BY f.razao_social
            ORDER BY SUM(d.valor_liquido) DESC
            LIMIT 3;
        """)
        for idx, (razao, qtd, total) in enumerate(cur.fetchall(), 1):
            print(f"  {idx}. {razao:<40} - {qtd:>6} notas | Total: R$ {total:,.2f}")
        print()

        # 4. Categorias de despesa mais representativas
        print("[PERGUNTA 4] Qual é a categoria de despesa mais representativa? (Top 3)")
        cur.execute("""
            SELECT c.descricao, COUNT(d.id_despesa), ROUND(SUM(d.valor_liquido), 2)
            FROM despesa_ceap d
            JOIN categoria_despesa c ON c.num_subcota = d.num_subcota
            GROUP BY c.descricao
            ORDER BY SUM(d.valor_liquido) DESC
            LIMIT 3;
        """)
        for idx, (desc, qtd, total) in enumerate(cur.fetchall(), 1):
            print(f"  {idx}. {desc:<45} - Total: R$ {total:,.2f}")
        print()

        # 5. Consumo por partido político
        print("[PERGUNTA 5] Quanto cada partido político consome do total acumulado? (Top 3)")
        cur.execute("""
            SELECT d.sigla_partido_emissao, COUNT(d.id_despesa), ROUND(SUM(d.valor_liquido), 2)
            FROM despesa_ceap d
            WHERE d.sigla_partido_emissao IS NOT NULL AND d.sigla_partido_emissao != ''
            GROUP BY d.sigla_partido_emissao
            ORDER BY SUM(d.valor_liquido) DESC
            LIMIT 3;
        """)
        for idx, (partido, qtd, total) in enumerate(cur.fetchall(), 1):
            print(f"  {idx}. Partido {partido:<12} - {qtd:>6} notas | Total: R$ {total:,.2f}")
        print()

        # 6. Proporção de gastos em fins de semana vs dias úteis
        print("[PERGUNTA 6] Qual a proporção de gastos com nota fiscal em fins de semana vs dias úteis?")
        cur.execute("""
            SELECT 
                CASE WHEN EXTRACT(ISODOW FROM data_emissao) IN (6, 7) THEN 'Fim de Semana' ELSE 'Dia Útil' END AS tipo_dia,
                COUNT(*),
                ROUND(SUM(valor_liquido), 2),
                ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2)
            FROM despesa_ceap
            WHERE data_emissao IS NOT NULL
            GROUP BY tipo_dia
            ORDER BY tipo_dia DESC;
        """)
        for tipo, qtd, total, pct in cur.fetchall():
            print(f"  - {tipo:<15}: {pct:>5}% das notas ({qtd:>7} notas) | Total: R$ {total:,.2f}")
        print("=" * 90 + "\n")

def main():
    print("=" * 70)
    print("  PLATAFORMA CEAP — INGESTÃO REPRODUTÍVEL E MIGRAÇÕES (SBD2 - E1)")
    print("=" * 70)

    # 1. Conexão com o banco
    conn = get_connection()

    # 2. Execução das migrações
    apply_migrations(conn, migrations_dir="migrations")

    # 3. Garantir dados disponíveis (cache local ou download automatizado da Câmara)
    anos_env = os.getenv("ANOS", "2023,2024,2025,2026")
    anos = [int(a.strip()) for a in anos_env.split(",") if a.strip()]
    csv_files = ensure_data_available(anos, target_dir="base-dados")

    # 4. Ingestão e carga no modelo transacional
    ingest_csv_files(conn, csv_files)

    # 5. Validação da consulta analítica da pergunta de gestão
    test_management_query(conn)

    conn.close()
    print("[FINALIZADO] Plataforma transacional (E1) pronta e operando com sucesso!\n")

if __name__ == "__main__":
    main()
