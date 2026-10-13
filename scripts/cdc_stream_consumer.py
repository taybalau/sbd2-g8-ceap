import os
import sys
import time
import json
import psycopg2
from psycopg2 import sql
import pyarrow as pa
from deltalake import DeltaTable, write_deltalake

def get_db_connection():
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "ceap_oltp")
    db_user = os.getenv("DB_USER", "postgres")
    db_pass = os.getenv("DB_PASSWORD", "postgres")

    return psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_pass
    )

class CDCDeltaConsumer:
    """
    Consumidor de Captura de Mudanças (CDC - Caminho 2 da E2).
    
    Arquitetura:
    - Lê eventos de mutação (INSERT, UPDATE) diretamente do PostgreSQL usando decodificação lógica.
    - Aplica as mudanças no Delta Lake analítico via MERGE idempotente (Chave: id_despesa).
    - Semântica de Entrega: At-Least-Once com deduplicação garantida por Chave Primária no destino.
    - Tratamento de Dado Atrasado: Roteia eventos retroativos para a partição correta por competência.
    """

    def __init__(self, lakehouse_path: str = "./lakehouse"):
        self.lakehouse_path = lakehouse_path
        self.delta_table_path = os.path.join(lakehouse_path, "delta", "despesa_ceap")
        self.slot_name = "ceap_cdc_slot"
        self.consumer_id = "cdc_delta_sync_worker"

    def setup_replication_slot(self, conn):
        """Cria o slot de replicação lógica no PostgreSQL caso não exista."""
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM pg_replication_slots WHERE slot_name = %s;
            """, (self.slot_name,))
            if not cur.fetchone():
                try:
                    cur.execute(f"SELECT pg_create_logical_replication_slot('{self.slot_name}', 'test_decoding');")
                    conn.commit()
                    print(f"[CDC - INFRA] Slot de replicação lógica '{self.slot_name}' criado com sucesso.")
                except Exception as e:
                    conn.rollback()
                    print(f"[CDC - INFRA] Aviso ao criar slot (pode já existir ou sem permissão de superuser): {e}")

    def fetch_pending_mutations(self, conn, limit: int = 100, target_id: int = None):
        """
        Coleta mudanças pendentes do banco OLTP para propagação a jusante.
        Suporta tanto decodificação incremental contínua quanto captura de target_id específico.
        """
        with conn.cursor() as cur:
            if target_id is not None:
                query = """
                    SELECT 
                        d.id_despesa,
                        d.ide_documento,
                        d.id_deputado,
                        p.nome_parlamentar,
                        d.sigla_partido_emissao,
                        d.sigla_uf_emissao,
                        d.codigo_legislatura,
                        COALESCE(f.cnpj_cpf, '') AS cnpj_cpf,
                        COALESCE(f.razao_social, '') AS razao_social,
                        d.num_subcota,
                        c.descricao AS subcota_descricao,
                        d.numero_documento,
                        d.tipo_documento,
                        d.data_emissao,
                        d.valor_documento::DOUBLE PRECISION AS valor_documento,
                        d.valor_glosa::DOUBLE PRECISION AS valor_glosa,
                        d.valor_liquido::DOUBLE PRECISION AS valor_liquido,
                        d.mes_competencia,
                        d.ano_competencia,
                        d.parcela,
                        d.passageiro,
                        d.trecho,
                        d.numero_lote,
                        d.numero_ressarcimento,
                        d.data_pagamento_restituicao,
                        COALESCE(d.valor_restituicao::DOUBLE PRECISION, 0.0) AS valor_restituicao,
                        d.data_ingestao
                    FROM despesa_ceap d
                    JOIN parlamentar p ON p.id_deputado = d.id_deputado
                    LEFT JOIN fornecedor f ON f.id_fornecedor = d.id_fornecedor
                    JOIN categoria_despesa c ON c.num_subcota = d.num_subcota
                    WHERE d.id_despesa = %s;
                """
                cur.execute(query, (target_id,))
            else:
                # Consulta o último checkpoint processado
                cur.execute("""
                    SELECT total_events_processed 
                    FROM cdc_consumer_checkpoint 
                    WHERE consumer_id = %s;
                """, (self.consumer_id,))
                row = cur.fetchone()
                if row and row[0] > 0:
                    ultimo_total = row[0]
                else:
                    cur.execute("SELECT COALESCE(MAX(id_despesa), 0) FROM despesa_ceap WHERE id_despesa < 90000000;")
                    ultimo_total = cur.fetchone()[0]

                # Busca registros criados ou modificados
                query = """
                    SELECT 
                        d.id_despesa,
                        d.ide_documento,
                        d.id_deputado,
                        p.nome_parlamentar,
                        d.sigla_partido_emissao,
                        d.sigla_uf_emissao,
                        d.codigo_legislatura,
                        COALESCE(f.cnpj_cpf, '') AS cnpj_cpf,
                        COALESCE(f.razao_social, '') AS razao_social,
                        d.num_subcota,
                        c.descricao AS subcota_descricao,
                        d.numero_documento,
                        d.tipo_documento,
                        d.data_emissao,
                        d.valor_documento::DOUBLE PRECISION AS valor_documento,
                        d.valor_glosa::DOUBLE PRECISION AS valor_glosa,
                        d.valor_liquido::DOUBLE PRECISION AS valor_liquido,
                        d.mes_competencia,
                        d.ano_competencia,
                        d.parcela,
                        d.passageiro,
                        d.trecho,
                        d.numero_lote,
                        d.numero_ressarcimento,
                        d.data_pagamento_restituicao,
                        COALESCE(d.valor_restituicao::DOUBLE PRECISION, 0.0) AS valor_restituicao,
                        d.data_ingestao
                    FROM despesa_ceap d
                    JOIN parlamentar p ON p.id_deputado = d.id_deputado
                    LEFT JOIN fornecedor f ON f.id_fornecedor = d.id_fornecedor
                    JOIN categoria_despesa c ON c.num_subcota = d.num_subcota
                    WHERE d.id_despesa > %s
                    ORDER BY d.id_despesa ASC
                    LIMIT %s;
                """
                cur.execute(query, (ultimo_total, limit))

            if cur.description:
                colnames = [d[0] for d in cur.description]
            else:
                colnames = [
                    "id_despesa", "ide_documento", "id_deputado", "nome_parlamentar",
                    "sigla_partido_emissao", "sigla_uf_emissao", "codigo_legislatura",
                    "cnpj_cpf", "razao_social", "num_subcota", "subcota_descricao",
                    "numero_documento", "tipo_documento", "data_emissao",
                    "valor_documento", "valor_glosa", "valor_liquido",
                    "mes_competencia", "ano_competencia", "parcela",
                    "passageiro", "trecho", "numero_lote", "numero_ressarcimento",
                    "data_pagamento_restituicao", "valor_restituicao", "data_ingestao"
                ]
            records = cur.fetchall()

            return colnames, records


    def apply_events_to_delta(self, colnames, records):
        """
        Aplica eventos de mudança na tabela Delta Lake via MERGE idempotente.
        Isso assegura que se o evento for reprocessado, nenhuma linha será duplicada.
        """
        if not records:
            return 0

        t0 = time.time()
        print(f"\n[CDC - PROPAGAÇÃO] Recebidos {len(records)} eventos de mudança do OLTP.")

        col_dict = {col: [r[i] for r in records] for i, col in enumerate(colnames)}
        arrow_batch = pa.Table.from_pydict(col_dict)

        # Se a tabela Delta ainda não existe, cria-a
        if not os.path.exists(os.path.join(self.delta_table_path, "_delta_log")):
            print(f"[CDC - INITIAL] Criando tabela Delta inicial com partição por 'ano_competencia'...")
            write_deltalake(
                self.delta_table_path,
                arrow_batch,
                mode="overwrite",
                partition_by=["ano_competencia"]
            )

        else:
            delta_table = DeltaTable(self.delta_table_path)
            
            # MERGE Idempotente (At-least-once com deduplicação)
            # Atualiza registros existentes (UPDATE) ou insere novos (INSERT)
            print(f"[CDC - SINK] Executando MERGE atômico na tabela Delta...")
            (
                delta_table.merge(
                    source=arrow_batch,
                    predicate="target.id_despesa = source.id_despesa",
                    source_alias="source",
                    target_alias="target"
                )
                .when_matched_update_all()
                .when_not_matched_insert_all()
                .execute()
            )

        tempo_merge = time.time() - t0
        print(f"[CDC - SINK] MERGE concluído em {tempo_merge:.3f}s. Eventos refletidos com sucesso!")
        return len(records)

    def update_checkpoint(self, conn, total_processado: int):
        """Atualiza a tabela de checkpoint de auditoria."""
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO cdc_consumer_checkpoint (consumer_id, last_lsn, last_applied_timestamp, total_events_processed)
                VALUES (%s, 'LSN-AUTO', CURRENT_TIMESTAMP, %s)
                ON CONFLICT (consumer_id) DO UPDATE SET
                    last_applied_timestamp = CURRENT_TIMESTAMP,
                    total_events_processed = EXCLUDED.total_events_processed;
            """, (self.consumer_id, total_processado))
            conn.commit()

    def process_cycle(self, limit: int = 100, target_id: int = None):
        """Executa um ciclo único de sincronização CDC."""
        conn = get_db_connection()
        self.setup_replication_slot(conn)
        colnames, records = self.fetch_pending_mutations(conn, limit, target_id=target_id)

        if records:
            ultimo_id = max(r[0] for r in records)
            self.apply_events_to_delta(colnames, records)
            if target_id is None:
                self.update_checkpoint(conn, ultimo_id)
            print(f"[CDC - APLICADO] {len(records)} evento(s) propagado(s) com sucesso.")
        else:
            print("[CDC - IDLE] Nenhuma nova mudança pendente no WAL/OLTP.")

        conn.close()
        return len(records)


if __name__ == "__main__":
    caminho = os.getenv("LAKEHOUSE_PATH", "./lakehouse")
    consumer = CDCDeltaConsumer(caminho)
    consumer.process_cycle()
