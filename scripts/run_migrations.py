import os
import psycopg2

def apply_migrations(conn, migrations_dir: str = "migrations"):
    """
    Aplica todas as migrações SQL da pasta 'migrations' em ordem sequencial alfanumérica.
    Garante idempotência registrando as versões aplicadas na tabela 'schema_migrations'.
    """
    print(f"[MIGRATIONS] Verificando migrações em '{migrations_dir}'...")

    with conn.cursor() as cur:
        # Garante tabela de controle
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

        cur.execute("SELECT version FROM schema_migrations;")
        applied = {row[0] for row in cur.fetchall()}

        migration_files = sorted([f for f in os.listdir(migrations_dir) if f.endswith(".sql")])

        for filename in migration_files:
            if filename in applied:
                print(f"[MIGRATIONS] Ignorando (já aplicada): {filename}")
                continue

            filepath = os.path.join(migrations_dir, filename)
            print(f"[MIGRATIONS] Executando migração: {filename}...")

            with open(filepath, "r", encoding="utf-8") as f:
                sql_content = f.read()

            try:
                cur.execute(sql_content)
                cur.execute("INSERT INTO schema_migrations (version) VALUES (%s);", (filename,))
                conn.commit()
                print(f"[MIGRATIONS] Migração {filename} aplicada com sucesso!")
            except Exception as e:
                conn.rollback()
                print(f"[ERRO] Falha crítica ao executar {filename}: {e}")
                raise

if __name__ == "__main__":
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ceap_oltp")
    with psycopg2.connect(db_url) as conn:
        apply_migrations(conn)
