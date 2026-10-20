# Diário de Bordo — Semana 07

- **Data:** 06/10/2026 a 13/10/2026 (2ª Semana e Fechamento da Entrega E2 em 13/10/2026)
- **Participantes:** Filipe Carvalho, Taynara Vitorino, Gabriel Esteves, Maria Clara Alves, Kaio Macedo, Amanda Gonçalves (Squad G8)

## O que foi medido
- Configuração do PostgreSQL para CDC e decodificação lógica do WAL:
  - Adição de `command: postgres -c wal_level=logical -c max_replication_slots=5 -c max_wal_senders=5` no `docker-compose.yml`.
  - Migração DDL `migrations/003_setup_cdc_replication.sql` com publicação `ceap_cdc_publication` e `REPLICA IDENTITY FULL`.
- Implementação e validação do **Caminho 2: Captura de Mudanças (CDC)** (`scripts/cdc_stream_consumer.py`):
  - Latência ponta a ponta medida entre mutação no OLTP e disponibilidade no Delta Lake: **380 ms**.
  - Operação transacional de reconciliação via `MERGE` atômico na chave primária `id_despesa`.
- Execução da bateria completa de testes de aceite da monitoria (`scripts/test_e2_pipeline.py`):
  1. *Idempotência do Lote:* Execução duplicada com 785.754 registros e 0 duplicatas.
  2. *CDC em Ação:* Inserção de nota fiscal teste no OLTP propagada ao Delta Lake em subsegundo, com atualização (`UPDATE`) refletida com precisão.
  3. *Tratamento de Dado Atrasado:* Evento retroativo de 2023 inserido no fluxo atual e roteado com exatidão para a partição de 2023 sem contaminar 2026.
  4. *Semântica de Entrega:* Reenvio forçado de mensagens duplicadas absorvido sem inflar contagens físicas (*Effectively-Once*).
  5. *Auditoria Societária (QSA/UBO):* Consultas via DuckDB evidenciando múltiplos CNPJs sob o controle da mesma pessoa física.
- Elaboração e consolidação de duas Decisões Arquiteturais da E2:
  - [`ADR-0002`](../adr/0002-mecanismo-ingestao-e-formato-aberto.md): Mecanismo de Ingestão (CDC vs Recarga Periódica agendada como opção nula) e Formato Aberto Delta Lake.
  - [`ADR-0003`](../adr/0003-resolucao-grafo-societario-beneficiario-final.md): Modelagem e Resolução em Grafo da Cadeia Societária para Identificação de Beneficiário Final (UBO).

## O que surpreendeu
- A consulta analítica sobre a Pergunta de Gestão executada pelo DuckDB sobre a tabela Delta particionada demorou apenas **18 ms** (contra 112 ms no PostgreSQL OLTP indexado), provando na prática a superioridade do armazenamento colunar aberto.
- O poder da decodificação lógica sem triggers: o banco transacional não sofreu nenhuma degradação de throughput de escrita.

## O que foi decidido
- Fechamento formal da Entrega E2 da Squad G8 cumprindo 100% do checklist de aceite no prazo de 13/10/2026.
- Consolidação do documento técnico explicativo em [`docs/PIPELINE_E2.md`](../PIPELINE_E2.md), atualização do [`README.md`](https://github.com/taybalau/sbd2-g8-ceap/blob/main/README.md) e do [`AI-USAGE.md`](https://github.com/taybalau/sbd2-g8-ceap/blob/main/AI-USAGE.md).
- Geração da tag `e2` no repositório público da Squad.
