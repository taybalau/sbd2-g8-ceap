# Release Notes · Plataforma de Dados da CEAP

Este documento consolida o histórico de entregas e versões da plataforma de dados da CEAP (57ª Legislatura), desenvolvida pela **Squad G8** na disciplina de Sistemas de Banco de Dados 2 (UnB - 2026/2).

### Sumário de Versões
- [Release Notes — v2.0 (Entrega E2) · Ingestão em Lote, CDC WAL, Lakehouse Aberto e Enriquecimento Societário](#release-notes--v20-entrega-e2--plataforma-de-dados-da-ceap)
- [Release Notes — v1.0 (Entrega E1) · Fonte Transacional (OLTP) Modelada e Populada](#release-notes--v10-entrega-e1--plataforma-de-dados-da-ceap)

---

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

---

# Release Notes — v1.0 (Entrega E1) · Plataforma de Dados da CEAP

**Projeto:** `sbd2-g8-ceap` — Plataforma de Dados da Cota Parlamentar (CEAP), 57ª Legislatura  
**Disciplina:** Sistemas de Banco de Dados 2 (2026/2) — Universidade de Brasília (UnB)  
**Squad:** G8 — Filipe Carvalho, Taynara Vitorino, Gabriel Esteves, Maria Clara Alves, Kaio Macedo, Amanda Gonçalves  
**Tag Git:** `e1`  
**Data de entrega:** 28/09/2026  
**Repositório:** https://github.com/taybalau/sbd2-g8-ceap  

---

## 1. Resumo

A E1 entrega a **fonte transacional (OLTP)** da plataforma: um banco PostgreSQL 16 normalizado, populado com os dados reais da CEAP de 2023 a 2026 e subido com **um único comando** a partir de uma máquina limpa.

A plataforma existe para responder à pergunta de gestão:

> *"Quais parlamentares e partidos da 57ª Legislatura (2023–2026) apresentam maior desvio de gastos acima da média mensal da Cota Parlamentar (CEAP), e quais categorias e fornecedores concentram esses recursos?"*

### Números da carga

| Métrica | Valor |
| :--- | ---: |
| Registros em `despesa_ceap` | **785.754** |
| Parlamentares e lideranças | 874 |
| Fornecedores distintos | 55.882 |
| Categorias de despesa (subcotas) | 21 |
| Volume financeiro (soma de `valor_liquido`) | R$ 869.398.245,27 |
| Volume bruto dos CSVs | ~265 MB |
| Tempo de carga completa (4 anos) | ~97,4 s |
| Latência da consulta analítica principal | ~112 ms |

Linhas por ano de origem: 2023 → 232.747 · 2024 → 232.918 · 2025 → 209.080 · 2026 → 111.009 (**2026 é um ano parcial**, com os dados disponíveis até a data da carga).

---

## 2. Novidades

### Modelo de dados relacional (migração `001_create_tables.sql`)
- Seis tabelas de domínio: `parlamentar`, `mandato_parlamentar`, `fornecedor`, `categoria_despesa`, `especificacao_despesa` e `despesa_ceap`, com chaves estrangeiras `ON DELETE RESTRICT`.
- Tabela de controle `schema_migrations` para versionar as migrações aplicadas.
- Tabela `stg_ceap_raw` do tipo `UNLOGGED`, com as 32 colunas originais do CSV como `TEXT`, usada como área de staging.
- Valores monetários em `NUMERIC(12, 2)` (sem erro de ponto flutuante) e `CHECK` nas competências (`mes_competencia` 1–12, `ano_competencia` ≥ 2000).
- `mandato_parlamentar` separa partido/UF/legislatura do parlamentar, porque deputados trocam de legenda durante a legislatura.
- `fornecedor` usa `UNIQUE NULLS NOT DISTINCT (cnpj_cpf, razao_social)` (exige PostgreSQL 15+).

### Padrão insert-only (livro-razão contábil)
- `despesa_ceap` é tratada como fato fiscal imutável: não há `UPDATE` destrutivo.
- Glosas e restituições têm campos próprios (`valor_glosa`, `valor_restituicao`, `data_pagamento_restituicao`).
- **Três carimbos de tempo** distintos:
  1. `data_emissao` — quando o documento fiscal foi emitido (evento no mundo real);
  2. `data_pagamento_restituicao` — quando houve a compensação financeira;
  3. `data_ingestao` — quando o banco registrou a linha (`DEFAULT CURRENT_TIMESTAMP`).

### Índices analíticos (migração `002_create_indexes.sql`)
Seis índices alinhados às perguntas de gestão:
- `(id_deputado, ano_competencia, mes_competencia)`
- `(sigla_partido_emissao, ano_competencia)`
- `(num_subcota, ano_competencia)`
- `(id_fornecedor, valor_liquido)`
- `(data_emissao)`
- `(ide_documento)` — índice parcial, `WHERE ide_documento IS NOT NULL`

### Pipeline de ingestão reprodutível (`scripts/`)
- `main.py` — orquestra tudo: espera o banco, migra, baixa, carrega e valida.
- `run_migrations.py` — aplica os `.sql` em ordem alfanumérica e registra cada um em `schema_migrations`, de modo que uma migração já aplicada é ignorada.
- `download_data.py` — usa cache local em `base-dados/` e, se o CSV não existir, baixa o `.zip` oficial de `camara.leg.br/cotas/` e extrai em memória.
- `ingest_ceap.py` — carrega o CSV com `COPY` na tabela de staging e popula dimensões e fatos via SQL, ano a ano, em transação.

### Orquestração com Docker
- `docker-compose.yml` com dois serviços: `db` (PostgreSQL 16 Alpine, com `healthcheck` via `pg_isready`) e `ingestion` (Python 3.11 slim, que só inicia quando o banco está saudável).
- Anos a carregar configuráveis pela variável `ANOS` (padrão: `2023,2024,2025,2026`).
- Dados persistidos no volume nomeado `postgres_data`.

### Painel de validação no terminal
Ao final da carga, `main.py` imprime seis consultas que cobrem a pergunta de gestão e as perguntas complementares:
1. custo médio mensal por deputado;
2. ranking dos parlamentares que mais usam a cota;
3. maiores fornecedores;
4. categorias mais representativas;
5. consumo por partido;
6. proporção de gastos em fins de semana vs. dias úteis.

### Governança e documentação
- **ADR-0001** (`docs/adr/`) — decisão por modelagem normalizada insert-only, no formato Nygard em 6 passos, comparando três alternativas (tabela flat, CRUD com `UPDATE` e insert-only) com medições.
- **Diários de bordo** (`docs/diario/`) — semanas 01 a 05 (24/08 a 28/09/2026).
- **AI-USAGE.md** — registro do uso de IA e da validação humana.
- **Planilha de acompanhamento** do G8 em `docs/`.

---

## 3. Correções

- **Duplicação de fornecedores na carga.** Fornecedores sem CNPJ (como bilhetes aéreos) geravam duplicatas porque, no SQL padrão, `NULL <> NULL` em constraints `UNIQUE`, e o `ON CONFLICT` não os reconhecia. A constraint passou a usar `UNIQUE NULLS NOT DISTINCT`, o que restabeleceu a contagem exata de **785.754** despesas. (Commit `bc7c302`, Amanda.)
- Atualização das métricas no ADR-0001, nos diários e no README com a carga já desduplicada.
- Correção do nome de um integrante no ADR e nos diários.
- Remoção de documentos de apoio e de uma planilha duplicada de `docs/`.

---

## 4. Tratamento das inconsistências dos dados abertos

O modelo foi ajustado para aceitar a realidade do dataset da Câmara, sem descartar registros:

| Inconsistência encontrada | Tratamento |
| :--- | :--- |
| Lideranças partidárias sem CPF nem carteira parlamentar | `cpf` e `nu_carteira_parlamentar` anuláveis |
| Telefonia com data de emissão vazia | `data_emissao` anulável |
| Passagens aéreas (SIGEPA) com valor líquido negativo (estornos) | Sem `CHECK` de positividade nos valores |
| Passagens e telefonia sem `ideDocumento` ou com valor 0 | `ide_documento` anulável; índice parcial |
| Fornecedor sem CNPJ/CPF | `cnpj_cpf` anulável + `NULLS NOT DISTINCT` |

---

## 5. Requisitos

- [Docker](https://docs.docker.com/get-docker/) instalado e em execução
- Docker Compose v2+
- Git
- Acesso à internet na primeira execução (download dos CSVs da Câmara)
- ~1 GB livres em disco (CSVs + volume do banco)
- Porta **5432** livre na máquina

---

## 6. Passo a passo: subir a plataforma do zero

### Passo 1 — Clonar o repositório e posicionar na versão

```bash
git clone https://github.com/taybalau/sbd2-g8-ceap.git
cd sbd2-g8-ceap

# Opcional: fixar exatamente a versão desta release
git checkout e1
```

### Passo 2 — Subir tudo com um único comando

```bash
docker compose up --build
```

Não é preciso baixar arquivos nem criar o banco manualmente. O comando executa, em ordem:

1. Constrói a imagem de ingestão.
2. Sobe o PostgreSQL 16 e aguarda o `healthcheck`.
3. Dispara o container `ceap_ingestion`, que aplica as migrações `001` e `002`.
4. Baixa os CSVs de 2023–2026 para `./base-dados/` (ou reaproveita os que já existirem).
5. Carrega os dados via `COPY` e normaliza ano a ano.
6. Imprime o resumo do banco e o painel de validação.

> Para rodar em segundo plano: `docker compose up --build -d` e acompanhar com `docker compose logs -f ingestion`.

### Passo 3 — Confirmar que terminou com sucesso

Ao final do log, procure por:

```
Total de Registros de Despesa:      785754
Volume Total Pago na Legislatura:   R$ 869,398,245.27
[FINALIZADO] Plataforma transacional (E1) pronta e operando com sucesso!
```

O container `ceap_ingestion` encerra sozinho após a carga; o `ceap_postgres` continua rodando.

### Passo 4 — Conectar ao banco

| Parâmetro | Valor |
| :--- | :--- |
| Host | `localhost` |
| Porta | `5432` |
| Banco | `ceap_oltp` |
| Usuário | `postgres` |
| Senha | `postgres` |

Funciona com DBeaver, pgAdmin, VS Code ou `psql`. Para abrir um `psql` direto no container:

```bash
docker exec -it ceap_postgres psql -U postgres -d ceap_oltp
```

### Passo 5 — Fazer uma primeira consulta

Top 10 parlamentares por gasto total:

```bash
docker exec -it ceap_postgres psql -U postgres -d ceap_oltp -c "
SELECT
    p.nome_parlamentar,
    d.sigla_partido_emissao AS partido,
    d.sigla_uf_emissao AS uf,
    COUNT(d.id_despesa) AS total_notas,
    ROUND(SUM(d.valor_liquido), 2) AS total_gasto
FROM despesa_ceap d
JOIN parlamentar p ON p.id_deputado = d.id_deputado
GROUP BY p.nome_parlamentar, d.sigla_partido_emissao, d.sigla_uf_emissao
ORDER BY total_gasto DESC
LIMIT 10;
"
```

### Passo 6 — (Opcional) Reproduzir a medição de desempenho do ADR

```bash
docker exec -it ceap_postgres psql -U postgres -d ceap_oltp -c "EXPLAIN ANALYZE SELECT p.nome_parlamentar, d.sigla_partido_emissao, COUNT(*), SUM(d.valor_liquido) FROM despesa_ceap d JOIN parlamentar p ON p.id_deputado = d.id_deputado GROUP BY p.nome_parlamentar, d.sigla_partido_emissao ORDER BY SUM(d.valor_liquido) DESC LIMIT 10;"
```

### Passo 7 — Parar ou recriar o ambiente

```bash
# Parar mantendo os dados
docker compose down

# Apagar tudo (containers + volume do banco) e recomeçar do zero
docker compose down -v
```

> Os CSVs ficam em `./base-dados/` e continuam como cache local mesmo após `down -v`. Apague essa pasta se quiser forçar um novo download.

---

## 7. Variações úteis

### Carregar apenas alguns anos (teste rápido)

Edite `ANOS` no serviço `ingestion` do `docker-compose.yml`:

```yaml
ANOS: "2023"
```

### Rodar a ingestão fora do Docker

Com um PostgreSQL 15+ já rodando e o banco `ceap_oltp` criado:

```bash
pip install -r docker/ingestion/requirements.txt

export DB_HOST=localhost DB_PORT=5432 DB_NAME=ceap_oltp \
       DB_USER=postgres DB_PASSWORD=postgres ANOS="2023,2024,2025,2026"

# Execute a partir da raiz do projeto (os caminhos migrations/ e base-dados/ são relativos)
python scripts/main.py
```

> No Windows (PowerShell), use `$env:DB_HOST="localhost"` em vez de `export`.

### Baixar apenas os CSVs

```bash
python scripts/download_data.py
```

---

## 8. Solução de problemas

| Sintoma | Causa provável | O que fazer |
| :--- | :--- | :--- |
| `port is already allocated` na 5432 | Outro PostgreSQL local usando a porta | Pare o outro serviço ou troque o mapeamento para `"5433:5432"` no `docker-compose.yml` |
| `[ERRO] Falha ao baixar dados do ano ...` | Sem internet ou portal da Câmara indisponível | Tente novamente mais tarde, ou coloque manualmente `Ano-AAAA.csv` em `base-dados/` |
| `Banco ainda não disponível (n/15)` repetido | Banco demorando a iniciar | O script tenta 15 vezes a cada 2 s; veja `docker compose logs db` |
| Contagens maiores que 785.754 | Ingestão executada mais de uma vez sobre o mesmo volume | Veja a limitação nº 1 abaixo e rode `docker compose down -v` |
| Erro em `UNIQUE NULLS NOT DISTINCT` | PostgreSQL anterior à versão 15 | Use PostgreSQL 15+ (o Compose usa a 16) |

---

## 9. Limitações conhecidas

1. **A ingestão não é idempotente.** As migrações são idempotentes, mas a carga em `despesa_ceap` não tem `ON CONFLICT`. Executar `docker compose up` novamente sobre um volume já populado duplica as despesas. Para recarregar, use `docker compose down -v` antes.
2. **2026 é um ano parcial.** Os dados refletem o que a Câmara havia publicado até a carga; uma nova execução mais tarde trará mais linhas.
3. **Credenciais fixas** (`postgres`/`postgres`) e porta exposta, adequadas apenas para ambiente local acadêmico.
4. **O download é sequencial**, ano a ano, sem verificação de integridade além do tamanho mínimo do cache local.
5. **Fora do escopo desta entrega:** replicação/CDC, camada analítica e transformações, previstas para as entregas E2 a E4.

---

## 10. Critérios de revisão da arquitetura (ADR-0001)

A decisão será reaberta se:
- o volume mensal ultrapassar **200.000 notas fiscais/mês**, o que justificaria particionamento declarativo por ano/mês de competência; ou
- a latência p95 de agregação analítica no OLTP passar de **2,0 s**, o que justificaria uma réplica colunar dedicada.

---

## 11. Uso de IA

O desenvolvimento contou com o assistente Google Antigravity (conforme declarado em [`AI-USAGE.md`](https://github.com/taybalau/sbd2-g8-ceap/blob/main/AI-USAGE.md)), com revisão e validação humana de todo o código, esquema e documentação pela Squad G8.
