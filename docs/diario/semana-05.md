# Diário de Bordo — Semana 05

- **Data:** 21/09/2026 a 28/09/2026 (Fechamento e Entrega da E1 em 28/09/2026)
- **Participantes:** Filipe Carvalho, Taynara Vitorino, Gabriel Esteves, Maria Clara Alves, Kaio Macedo, Amanda Gonçalves (Squad G8)

## O que foi medido
- **Construção e Execução dos Scripts e Migrações:**
  - Implementação dos scripts SQL de migração DDL (`migrations/001_create_tables.sql` e `migrations/002_create_indexes.sql`).
  - Implementação do script de download concorrente automatizado dos arquivos `.zip` oficiais da Câmara com verificação de integridade e cache local (`scripts/download_data.py`).
  - Implementação do script de execução sequencial e idempotente de migrações (`scripts/run_migrations.py`).
  - Implementação do pipeline de carga de alta performance via `COPY` e normalização relacional em dois estágios (`scripts/ingest_ceap.py`).
  - Configuração do `docker-compose.yml` e `docker/ingestion/Dockerfile` com `healthcheck` de banco.
- **Métricas Reais Obtidas na Execução:**
  - Carga dos 4 anos completos da CEAP (2023 a 2026) finalizada em apenas **97,4 segundos**.
  - **785.754 registros de despesas inseridos** na tabela transacional `despesa_ceap` (100% íntegro com os CSVs originais).
  - **874 parlamentares e lideranças** cadastrados na tabela `parlamentar`.
  - **55.882 fornecedores distintos** cadastrados na tabela `fornecedor`.
  - **21 categorias orçamentárias** cadastradas na tabela `categoria_despesa`.
  - **Volume total pago na legislatura:** **R$ 869.398.245,27**.
  - Latência da consulta analítica da Pergunta de Gestão com índices compostos: **112 ms**.

## O que surpreendeu
- A eficiência real da tabela `UNLOGGED` associada ao comando `COPY` do PostgreSQL: todo o volume de quase 800 mil linhas (~265 MB) foi transferido, higienizado e normalizado com integridade referencial em apenas 97 segundos.
- A sutileza do padrão ANSI SQL onde `NULL != NULL` em constraints `UNIQUE`: na carga ano a ano, fornecedores sem CNPJ (como bilhetes aéreos) não batiam no `ON CONFLICT`, gerando duplicatas. A aplicação da cláusula moderna `UNIQUE NULLS NOT DISTINCT` do PostgreSQL 16 resolveu cirurgicamente o problema e restabeleceu a contagem exata de 785.754 despesas.

## O que foi decidido
- Fechamento formal de todos os artefatos da Entrega E1:
  - Código, migrações, scripts e orquestração Docker validados ponta a ponta;
  - Documento [`ADR-0001`](../adr/0001-modelagem-transacional-insert-only-ceap.md) consolidado no formato Nygard em 6 passos, integrando as métricas reais medidas;
  - Preenchimento completo da planilha oficial [`projetoengenhariadedadosbd2.xlsx`](../projetoengenhariadedadosbd2.xlsx) com 7 de 7 abas concluídas (100% OK);
  - [`AI-USAGE.md`](../../AI-USAGE.md) e [`README.md`](../../README.md) finalizados;
  - Geração da tag `e1` no repositório Git para submissão oficial da Squad G8.
