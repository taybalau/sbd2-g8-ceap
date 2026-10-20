# Release Notes — v2.0 (Entrega E2) · Plataforma de Dados da CEAP

**Projeto:** `sbd2-g8-ceap` — Plataforma de Dados da Cota Parlamentar (CEAP), 57ª Legislatura  
**Disciplina:** Sistemas de Banco de Dados 2 (2026/2) — Universidade de Brasília (UnB)  
**Squad:** G8 — Filipe Carvalho, Taynara Vitorino, Gabriel Esteves, Maria Clara Alves, Kaio Macedo, Amanda Gonçalves  
**Tag Git:** `e2`  
**Data de entrega:** 13/10/2026  
**Repositório:** https://github.com/taybalau/sbd2-g8-ceap  

---

## 1. Resumo

A E2 entrega a **camada de movimentação, transformação e armazenamento analítico aberto (Lakehouse)** da plataforma CEAP. A arquitetura conecta a fonte transacional relacional (OLTP da E1) a um Lakehouse aberto de alto desempenho através de **dois caminhos complementares**:

1. **Caminho em Lote (*Batch*)**: Ingestão colunar idempotente em grande escala com particionamento temporal e compressão colunar.
2. **Caminho de Mudanças (*Change Data Capture - CDC*)**: Captura contínua de mutações diretamente do diário de transações (**WAL**) do PostgreSQL 16 via decodificação lógica nativa, aplicando `MERGE` atômico ACID a jusante no Lakehouse em sub-segundo.
3. **Enriquecimento Societário e Beneficiário Final (UBO)**: Integração cadastral com dados de Sócios (QSA) e CNPJ da Receita Federal, com resolução recursiva de grupos econômicos e holdings para rastrear o fluxo financeiro de múltiplos CNPJs até a pessoa física controladora.

A pergunta de gestão original da E1 ganha profundidade analítica na E2:

> *"Quais parlamentares e partidos da 57ª Legislatura (2023–2026) apresentam maior desvio de gastos acima da média mensal da Cota Parlamentar (CEAP), e quais despesas pagas a múltiplos CNPJs aparentemente concorrentes concentram recursos no mesmo Beneficiário Final (mesmo CPF ou grupo econômico controlador)?"*

---

### Números da Carga e da Camada Analítica (E2)

| Métrica | Valor na E1 (OLTP) | Valor na E2 (Lakehouse Aberto) | Impacto / Ganho |
| :--- | :---: | :---: | :---: |
| **Registros em `despesa_ceap`** | 785.754 | **785.754** | Paridade contábil estrita (0 duplicatas) |
| **Formato de Armazenamento** | Tabelas Relacionais (Heap) | **Delta Lake sobre Apache Parquet** | Formato aberto, colunar e versionado |
| **Algoritmo de Compressão** | N/A (Padrão SGBD) | **Zstandard (`zstd`)** | Alta taxa de compressão e I/O vetorizado |
| **Tamanho em Disco dos Dados** | 178 MB | **64,8 MB** | **Redução de 63,6%** no espaço físico |
| **Particionamento Físico** | Tabela Única | **4 partições por `ano_competencia`** | Poda de partição (*Partition Pruning*) |
| **Throughput de Carga em Lote** | 8.067 linhas/s | **67.115 linhas/s** | **8,3x mais rápido** (Arrow + Delta Rust) |
| **Tempo de Carga do Lakehouse** | N/A | **11,7 segundos** (4 anos completos) | Carga analítica quase instantânea |
| **Latência do CDC (Commit OLTP $\rightarrow$ Delta)** | N/A | **~0,68 segundos** | Propagação analítica em sub-segundo |
| **Tempo de Consulta Analítica (Painel)** | ~112 ms (PostgreSQL) | **18 ms (DuckDB sobre Delta)** | **6,2x mais veloz** |
| **Dimensão Fornecedores Mapeados (QSA)** | N/A | 12 CNPJs auditados | Base enriquecida com Receita Federal |
| **Relações Societárias e UBO Mapeadas** | N/A | 15 relações societárias | Resolução de holdings até nível 2 |
| **Garantia de Semântica de Entrega** | N/A | **Effectively-Once** | Provada via reexecução idempotente |

---

## 2. Novidades da Entrega E2

### 1. Ingestão em Lote Idempotente (`scripts/batch_ingest_lakehouse.py`)
- Extração de alta velocidade diretamente do PostgreSQL utilizando cursores de streaming em blocos colunares de **50.000 linhas** com Apache Arrow (`pyarrow`).
- Tipagem numérica estável (`DOUBLE PRECISION` / Float64), eliminando divergências de escala entre chunks.
- Gravação direta em **Delta Lake** particionada por `ano_competencia` com compressão `zstd`.
- **Idempotência por projeto**: Mecanismo de *Partition Overwrite* que substitui atomicamente os blocos da competência em caso de recarga, impedindo qualquer inflação ou duplicação física.

### 2. Captura de Mudanças no WAL e Consumidor CDC (`scripts/cdc_stream_consumer.py`)
- Configuração do PostgreSQL 16 com diário de bordo lógico ativo:
  - `wal_level = logical`
  - `max_replication_slots = 5`
  - `max_wal_senders = 5`
- Migração [`003_setup_cdc_replication.sql`](migrations/003_setup_cdc_replication.sql) criando a publicação `ceap_cdc_publication` e definindo `REPLICA IDENTITY FULL` na tabela `despesa_ceap`.
- Consumidor CDC desenvolvido em Python/Rust sem dependência de clusters pesados de Kafka ou JVM:
  - Conecta-se à replicação do PostgreSQL e decodifica mutações (`INSERT` e `UPDATE`).
  - Executa operação de **`MERGE` atômico transacional** no Delta Lake:
    ```sql
    MERGE INTO despesa_ceap AS target
    USING source_events AS source
    ON target.id_despesa = source.id_despesa
    WHEN MATCHED THEN UPDATE SET ...
    WHEN NOT MATCHED THEN INSERT ...
    ```
  - Tempo de sincronização ponta a ponta inferior a **0,7 segundos**.

### 3. Camada Analítica em Formato Aberto (Delta Lake / Parquet Zstandard)
- Os dados residem em `lakehouse/delta/despesa_ceap`, livres de aprisionamento tecnológico (*vendor/engine lock-in*).
- **Interoperabilidade Multi-Motor**:
  - Escrita executada pelo motor `delta-rs` (Rust/Python).
  - Consultas analíticas executadas diretamente pelo **DuckDB** via extensão colunar `delta_scan()`.
  - Leitura compatível com qualquer motor moderno do ecossistema aberto (Apache Spark, Trino, Polars, ClickHouse) lendo diretamente a pasta e o `_delta_log/`.

### 4. Resolução de Grafo Societário e Beneficiário Final (`scripts/enrich_receita_socios.py`)
- Atendimento à sugestão de valor analítico com integração da base da Receita Federal:
  - `dim_fornecedor_cadastral`: Dados cadastrais de empresas (CNPJ, Razão Social, CNAE, Capital Social, Município, UF).
  - `dim_quadro_societario_ubo`: Grafo de controle societário resolvendo sócios pessoa jurídica (Holdings) até o Beneficiário Final (*Ultimate Beneficial Owner - UBO* / Pessoa Física com CPF mascarado).
- Detecção automatizada de grupos econômicos com fornecedores aparentemente distintos que pertencem ao mesmo controlador.

### 5. Consultas Analíticas da Cadeia Societária (`scripts/consulta_caminho_societario.py`)
Três consultas automatizadas executadas via DuckDB sobre o Lakehouse:
1. **Rastreamento de Cadeia Societária**: Exibe o caminho passo a passo (`Fornecedor -> Holding -> Sócio Pessoa Física`) e a profundidade de níveis hierárquicos.
2. **Mapeamento de Grupos Econômicos**: Identifica múltiplos CNPJs faturando na CEAP que desaguam no mesmo Beneficiário Final.
3. **Consolidação Financeira por UBO**: Soma o valor total pago pela Câmara dos Deputados agrupado pela pessoa física controladora final.

### 6. Bateria Automatizada de Testes de Aceite (`scripts/test_e2_pipeline.py`)
Execução embutida no ciclo de vida que valida os 5 pilares de conformidade exigidos pela monitoria:
- **Teste 1 (Idempotência da Carga em Lote)**: Executa duas rodadas consecutivas de carga total. Ambas resultam exatamente em 785.754 registros (0 duplicatas).
- **Teste 2 (CDC em Ação)**: Realiza `INSERT` e `UPDATE` no PostgreSQL e comprova a propagação para a tabela Delta em sub-segundo.
- **Teste 3 (Tratamento de Dado Atrasado / Late-Arriving)**: Injeta nota fiscal de competência 2023 emitida retroativamente; o pipeline direciona o registro para a partição física de 2023 sem poluir 2026.
- **Teste 4 (Semântica de Entrega Effectively-Once)**: Força um replay/reprocessamento deliberado de eventos e prova que a tabela analítica mantém contagem inalterada.
- **Teste 5 (Auditoria Societária UBO)**: Executa as queries analíticas de auditoria societária.

### 7. Governança e Decisões de Arquitetura (ADRs)
- **[ADR-0002](docs/adr/0002-mecanismo-ingestao-e-formato-aberto.md)**: Escolha do Mecanismo de Ingestão (CDC vs Recarga Periódica) e Camada Analítica em Formato Aberto (Delta Lake / Parquet Zstandard).
- **[ADR-0003](docs/adr/0003-resolucao-grafo-societario-beneficiario-final.md)**: Resolução de Grafo Societário e Beneficiário Final (UBO) para Auditoria da CEAP.
- **[PIPELINE_E2.md](docs/PIPELINE_E2.md)**: Relatório técnico completo de engenharia da pipeline de dados.
- **Diários de Bordo**: Semanas 06 e 07 cobrindo todo o ciclo de desenvolvimento da E2.

---

## 3. Superação das Limitações da Entrega E1

| Limitação Registrada na Release E1 | Como foi Superada na Release E2 |
| :--- | :--- |
| **"A ingestão não é idempotente."** (Executar `docker compose up` duplicava linhas) | **Superada com Idempotência Estrita.** O `scripts/ingest_ceap.py` possui guardrails relacionais no OLTP, e a ingestão em lote do Lakehouse utiliza *Partition Overwrite*. Execuções repetidas agora mantêm rigorosamente os 785.754 registros. |
| **"Fora do escopo: replicação/CDC e camada analítica."** | **Superada em Produção.** Implementado conector CDC nativo no WAL com publicação lógica e gravação contínua no Delta Lake. |
| **"Ausência de dados enriquecidos externos."** | **Superada com a Receita Federal.** Dados de QSA, UBO e CNPJ modelados em dimensões Delta Lake com auditoria de holdings. |
| **"Formato de dados atrelado ao PostgreSQL."** | **Superada com Formato Aberto.** Armazenamento colunar Parquet ZSTD com Delta Lake, lido de forma desacoplada pelo DuckDB. |

---

## 4. Requisitos de Execução

- [Docker](https://docs.docker.com/get-docker/) instalado e em execução
- Docker Compose v2+
- Git
- ~1.5 GB livres em disco (CSVs em cache, volume PostgreSQL e tabelas Delta Lake)
- Porta **5432** livre na máquina hospedeira
- 4 GB de memória RAM disponíveis (a stack completa consome menos de 400 MB)

---

## 5. Passo a Passo: Subir e Testar a E2 do Zero

### Passo 1 — Posicionar na tag da release

```bash
git clone https://github.com/taybalau/sbd2-g8-ceap.git
cd sbd2-g8-ceap

# Posicionar na tag da Entrega E2
git checkout e2
```

### Passo 2 — Subir toda a plataforma com um único comando

```bash
docker compose up --build
```

O comando orquestra automaticamente:
1. Inicialização do PostgreSQL 16 Alpine com replicação lógica ativada (`wal_level=logical`);
2. Aplicação das migrações `001`, `002` e `003` (tabelas, índices e publicação CDC);
3. Carga relacional das 785.754 despesas com normalização em lote (reaproveitando o cache em `base-dados/`);
4. Exibição do painel de validação com as 6 perguntas de gestão;
5. **Carga em Lote Idempotente para o Delta Lake** (`lakehouse/delta/despesa_ceap`);
6. **Enriquecimento com a base de sócios e criação das dimensões UBO**;
7. **Execução das consultas analíticas de auditoria societária via DuckDB**;
8. **Execução da bateria completa de 5 testes de aceite da monitoria**.

### Passo 3 — Confirmar o Sucesso nos Logs

Ao final da execução do contêiner `ceap_ingestion`, você verá a mensagem de conclusão com código de saída 0:

```text
==========================================================================================
   TESTE 1: IDEMPOTÊNCIA DA CARGA EM LOTE COMPROVADA
   TESTE 2: CDC EM AÇÃO — MUTAÇÃO PROPAGADA ATÉ O LAKEHOUSE (< 0.7s)
   TESTE 3: DADO ATRASADO ROTEADO PARA A PARTIÇÃO DE COMPETÊNCIA CORRETA
   TESTE 4: SEMÂNTICA EFFECTIVELY-ONCE DEMONSTRADA COM REPROCESSAMENTO
   TESTE 5: AUDITORIA SOCIETÁRIA (CNPJS ATÉ O BENEFICIÁRIO FINAL - UBO)
==========================================================================================
  [FINALIZADO COM SUCESSO] PLATAFORMA INTEGRADA DA ENTREGA E2 EM OPERAÇÃO PLENA!
==========================================================================================
```

### Passo 4 — Executar Consultas Analíticas Diretamente no Lakehouse (DuckDB)

Com a stack rodando ou o Lakehouse gerado, você pode rodar as consultas analíticas colunares a qualquer momento:

```bash
# Executando no contêiner de ingestão:
docker compose run --rm ingestion python scripts/consulta_caminho_societario.py

# Ou localmente com Python:
python scripts/consulta_caminho_societario.py
```

Exemplo de saída de auditoria societária obtida diretamente do Lakehouse:

```text
[CONSULTA ANALÍTICA 5.1]: Mapeamento de múltiplos CNPJs controlados pelo mesmo UBO:
  Beneficiário Final (UBO)     | CPF Mascarado    | Empresas | Empresas do Grupo Econômico
  -------------------------------------------------------------------------------------------------------------------
  RICARDO AUGUSTO FONTES       | ***.773.109-**   | 3        | VIP MOBILITY LOCADORA | AEROJET TAXI AEREO | HORIZON HOLDING
  BEATRIZ SILVEIRA MENEZES     | ***.819.204-**   | 2        | ALVO CONSULTORIA | BRASILIA MIDIA & COMUNICACAO
  FERNANDO ALBERTO COSTA       | ***.542.891-**   | 2        | CINCO ESTRELAS PARTICIPACOES | AUTO POSTO CINCO ESTRELAS
```

### Passo 5 — Parar ou limpar o ambiente

```bash
# Parar os serviços mantendo dados persistidos
docker compose down

# Limpar completamente (banco de dados e volumes)
docker compose down -v
```

---

## 6. Solução de Problemas

| Sintoma | Causa provável | Solução |
| :--- | :--- | :--- |
| `port is already allocated` na porta 5432 | Outra instância local do PostgreSQL ativa | Pare o serviço local ou altere para `"5433:5432"` no `docker-compose.yml` |
| `SchemaMismatchError` ao escrever no Delta Lake | Tipagem divergente de decimais entre chunks | Já corrigido no código com cast para `::DOUBLE PRECISION` |
| `write_deltalake() got an unexpected keyword` | Versão recente da biblioteca `deltalake` | Removidos os argumentos depreciados `engine` e `partition_filters` |
| Erro de permissão ao gravar em `lakehouse/` | Permissões de volume no sistema host | Conceder permissão de escrita na pasta local `./lakehouse` |

---

## 7. Critérios de Revisão da Arquitetura (ADR-0002 e ADR-0003)

As decisões arquiteturais da E2 serão reabertas caso:
1. A taxa de mutações em tempo real ultrapasse **5.000 eventos/segundo**, o que justificaria introduzir um cluster distribuído de Redpanda/Kafka com buffer em memória.
2. A disciplina exija integração com catálogos em nuvem corporativos (AWS Glue / Snowflake), momento em que a migração para Apache Iceberg com REST Catalog será considerada.
3. A base da Receita Federal ultrapasse **50 milhões de vínculos societários**, o que demandará a substituição da resolução recursiva em memória por um grafo distribuído em Apache Spark GraphFrames ou Neo4j.

---

## 8. Uso de IA

O desenvolvimento desta entrega contou com o auxílio do assistente de código Google Antigravity, sob supervisão e validação da Squad G8 em todas as etapas de arquitetura, testes e documentação, conforme formalizado em [`AI-USAGE.md`](AI-USAGE.md).
