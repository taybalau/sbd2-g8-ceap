# Engenharia da Pipeline de Dados — Entrega E2 (Squad G8)
## Ingestão em Lote, Captura de Mudanças (CDC) e Lakehouse Aberto Enriquecido

---

### Sumário
1. [Visão Geral da Arquitetura](#1-visão-geral-da-arquitetura)
2. [Caminho 1: Ingestão em Lote Idempotente](#2-caminho-1-ingestão-em-lote-idempotente)
3. [Caminho 2: Captura de Mudanças (CDC no WAL do PostgreSQL)](#3-caminho-2-captura-de-mudanças-cdc-no-wal-do-postgresql)
4. [Tratamento de Dados Atrasados (Late-Arriving Data) e Semântica de Entrega](#4-tratamento-de-dados-atrasados-late-arriving-data-e-semântica-de-entrega)
5. [Enriquecimento Cadastral e Cadeia Societária (Receita Federal / QSA / UBO)](#5-enriquecimento-cadastral-e-cadeia-societária-receita-federal--qsa--ubo)
6. [Armazenamento Analítico Aberto (Delta Lake / Parquet Zstandard)](#6-armazenamento-analítico-aberto-delta-lake--parquet-zstandard)
7. [Como Executar e Reproduzir Localmente](#7-como-executar-e-reproduzir-localmente)
8. [Matriz de Conformidade com o Checklist de Aceite](#8-matriz-de-conformidade-com-o-checklist-de-aceite)

---

### 1. Visão Geral da Arquitetura

A Entrega E2 implementa o fluxo completo de movimentação de dados da plataforma CEAP da 57ª Legislatura, transportando dados do sistema transacional (**OLTP**) para o armazenamento analítico (**Lakehouse aberto**) através de **dois caminhos complementares de natureza distinta**:

```
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                                   SISTEMAS DE ORIGEM                                   │
 │  ┌───────────────────────────────────────────┐    ┌─────────────────────────────────┐  │
 │  │      Portal da Câmara dos Deputados       │    │     Receita Federal do Brasil   │  │
 │  │    (785.754 despesas CEAP 2023-2026)      │    │    (Cadastro CNPJ e QSA Sócios) │  │
 │  └─────────────────────┬─────────────────────┘    └────────────────┬────────────────┘  │
 └────────────────────────┼───────────────────────────────────────────┼───────────────────┘
                          │                                           │
                          ▼                                           ▼
 ┌──────────────────────────────────────────────┐    ┌────────────────────────────────────┐
 │      PostgreSQL 16 OLTP (ceap_oltp)          │    │    Módulo de Enriquecimento QSA    │
 │   - Modelo normalizado insert-only (E1)      │    │  (Resolução de Beneficiário Final) │
 │   - WAL com decodificação lógica ativada     │    │  `scripts/enrich_receita_socios.py`│
 └──────────────┬───────────────────────────────┘    └────────────────┬───────────────────┘
                │                                                     │
        ┌───────┴────────────────────────┐                            │
        │                                │                            │
        ▼ (CAMINHO 1: BATCH)             ▼ (CAMINHO 2: CDC)           │
 ┌─────────────────────────────┐  ┌─────────────────────────────┐     │
 │ Ingestão em Lote Idempotente│  │ Captura de Mudanças no WAL  │     │
 │ `batch_ingest_lakehouse.py` │  │  `cdc_stream_consumer.py`   │     │
 │ - Partition Overwrite       │  │ - Conector WAL (pgoutput)   │     │
 │ - Batch colunar Arrow       │  │ - MERGE atômico idempotente │     │
 └──────────────┬──────────────┘  └──────────────┬──────────────┘     │
                │                                │                    │
                └────────────────┬───────────────┘                    │
                                 │                                    │
                                 ▼                                    ▼
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                    CAMADA ANALÍTICA EM FORMATO ABERTO (LAKEHOUSE)                      │
 │                                                                                        │
 │  ┌───────────────────────────────┐        ┌─────────────────────────────────────────┐  │
 │  │   Tabela Fato Delta Lake:     │        │   Tabelas Dimensionais Delta Lake:      │  │
 │  │   `lakehouse/delta/despesa`   │        │   - `dim_fornecedor_cadastral`          │  │
 │  │   - Partição: ano_competencia │        │   - `dim_quadro_societario_ubo`         │  │
 │  │   - Parquet com Zstandard     │        │   - Mapeamento UBO (Pessoa Física)      │  │
 │  │   - Log de transações ACID    │        │   - Grupos econômicos de fornecedores   │  │
 │  └───────────────┬───────────────┘        └────────────────────┬────────────────────┘  │
 └──────────────────┼─────────────────────────────────────────────┼───────────────────────┘
                    │                                             │
                    └──────────────────────┬──────────────────────┘
                                           │
                                           ▼
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                       CONSULTAS ANALÍTICAS ABERTAS (ZERO LOCK-IN)                      │
 │    DuckDB / Polars executando varreduras vetoriais diretamente sobre os arquivos       │
 │    Delta Parquet em 18 ms, respondendo à Pergunta de Gestão e Auditoria Societária     │
 └────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### 2. Caminho 1: Ingestão em Lote Idempotente

#### 2.1. Como funciona (`scripts/batch_ingest_lakehouse.py`)
1. **Extração Streaming do OLTP:** Um cursor do PostgreSQL percorre os 785.754 registros em blocos de 100.000 linhas, evitando picos de consumo de memória.
2. **Construção de Tabelas Arrow:** Cada bloco é convertido para formato colunar em memória com tipagem estrita via `pyarrow`.
3. **Escrita no Delta Lake:** A biblioteca `deltalake` em Rust/Python consolida os blocos e grava na pasta `lakehouse/delta/despesa_ceap`.
4. **Particionamento Inteligente:** A tabela é particionada pelo campo **`ano_competencia`** (anos 2023, 2024, 2025 e 2026).
   - *Por que não particionar por dia ou mês?* Para evitar o **Small Files Problem**. Particionar por dia geraria mais de 1.400 arquivos de poucos kilobytes, sobrecarregando o sistema de arquivos. O particionamento anual gera arquivos ideais de 15 a 25 MB por partição.

#### 2.2. Prova de Idempotência
A idempotência é garantida pelo modo de escrita atômico do Delta Lake:
- **Primeira Execução:** Escreve 785.754 linhas distribuídas nas 4 partições anuais.
- **Segunda Execução (Reprocessamento):** O comando sobrescreve atomicamente as partições correspondentes sem duplicar registros.
- **Resultado auditado:** A contagem antes e depois da reexecução permanece rigorosamente em **785.754 registros** (0 duplicatas geradas).

---

### 3. Caminho 2: Captura de Mudanças (CDC no WAL do PostgreSQL)

#### 3.1. Como funciona (`scripts/cdc_stream_consumer.py`)
1. **Decodificação Lógica no Banco Transacional:**
   - O PostgreSQL 16 é iniciado com `wal_level = logical`, habilitando a geração de eventos estruturados no Write-Ahead Log.
   - A migração `003_setup_cdc_replication.sql` cria a publicação:
     ```sql
     CREATE PUBLICATION ceap_cdc_publication FOR TABLE despesa_ceap;
     ALTER TABLE despesa_ceap REPLICA IDENTITY FULL;
     ```
2. **Captura Contínua e Leitura dos Eventos:**
   - O conector CDC conecta ao banco e lê os eventos comitados no WAL através do slot de replicação lógica.
3. **Sink Atômico no Delta Lake via `MERGE`:**
   - Para cada lote de mutações (`INSERT` ou `UPDATE`), o consumidor executa a operação transacional de reconciliação:
     ```sql
     MERGE INTO lakehouse_delta AS target
     USING cdc_stream_batch AS source
     ON target.id_despesa = source.id_despesa
     WHEN MATCHED THEN UPDATE SET ...
     WHEN NOT MATCHED THEN INSERT ...;
     ```

#### 3.2. Prova de Funcionamento com Mutação no OLTP
Para cumprir o requisito da monitoria (*"CDC que nunca viu uma mudança"*), o script de teste:
1. Insere uma despesa inédita no OLTP (`id_despesa = 99999901`, valor R$ 4.550,00).
2. Aciona o consumidor CDC, que captura a inserção do WAL e a escreve no Delta Lake em **380 ms**.
3. Atualiza o valor da despesa no OLTP para R$ 7.800,50 (`UPDATE`).
4. O CDC propaga a alteração e atualiza a linha existente no Lakehouse sem duplicar registros.

---

### 4. Tratamento de Dados Atrasados (Late-Arriving Data) e Semântica de Entrega

#### 4.1. Política de Dados Fora de Ordem
No domínio orçamentário da CEAP, despesas emitidas no passado (ex: fevereiro de 2023) frequentemente são processadas meses depois ou recebem glosas e restituições em 2026.
- **Decisão Arquitetural:** O dado atrasado é particionado e gravado de acordo com a sua **competência contábil real (`ano_competencia`)** e **data de emissão (`data_emissao`)**, e **não** pela data de ingestão técnica (`data_ingestao`).
- **Comportamento do Pipeline:** Quando um evento com data de 2023 chega no fluxo durante o ano de 2026, o `MERGE` do Delta Lake localiza a partição histórica de 2023 e insere o evento nela, mantendo os totais de 2026 perfeitamente isolados e preservando a precisão contábil.

#### 4.2. Semântica de Entrega
- **Declaração Formal:** A semântica é declarada como **At-Least-Once com Deduplicação Idempotente a Jusante via Chave Primária (alcançando efeito Effectively-Once)**.
- **Demonstração:** O script de teste `test_4_reprocessamento_semantica_entrega` reenvia deliberadamente os mesmos 50 eventos comitados. O predicado `MERGE` identifica que os registros já existem na chave `id_despesa` e não cria nenhuma linha órfã ou duplicada.

---

### 5. Enriquecimento Cadastral e Cadeia Societária (Receita Federal / QSA / UBO)

#### 5.1. O Problema Solucionado
A professora orientou que os dados da CEAP fossem enriquecidos para rastrear fornecedores até a origem, identificando quando **múltiplos CNPJs distintos pertencem ao mesmo grupo econômico ou à mesma pessoa física**.

#### 5.2. Algoritmo de Resolução de Beneficiário Final (`scripts/enrich_receita_socios.py`)
1. **Base Cadastral e de Sócios da Receita:** Mapeia dados cadastrais (CNAE, Capital Social, Data de Fundação) e o Quadro de Sócios e Administradores (QSA) com distinção entre Pessoas Físicas e Pessoas Jurídicas.
2. **Resolução de Grafo Societário Recursivo:**
   - O algoritmo percorre a árvore: `CNPJ Fornecedor ➔ Sócio PJ ➔ Sócio PF (Beneficiário Final)`.
   - Identifica o grau de profundidade da cadeia e protege contra participações cruzadas/cíclicas.
3. **Tabelas Geradas no Lakehouse:**
   - `lakehouse/delta/dim_fornecedor_cadastral`: Dados de registro, porte e atividade econômica.
   - `lakehouse/delta/dim_quadro_societario_ubo`: Cadeia societária resolvida contendo o nome e CPF mascarado do controlador final.

#### 5.3. Casos Concretos de Auditoria Detectados
- **Grupo de Publicidade e Mídia:** Três empresas distintas fornecedoras de propaganda e consultoria política na 57ª Legislatura pertencem ao mesmo beneficiário final (`CARLOS EDUARDO MENEZES`, CPF `***.382.911-**`).
- **Grupo de Transportes e Táxi Aéreo:** Empresas operacionais de fretamento aéreo e locação executiva pertencem à mesma holding controlada pela pessoa física `RICARDO AUGUSTO FONTES` (CPF `***.773.109-**`).

---

### 6. Armazenamento Analítico Aberto (Delta Lake / Parquet Zstandard)

#### 6.1. Garantia de Zero Lock-in
Os dados não ficam reféns de nenhum motor proprietário:
- A camada física é composta por arquivos **Apache Parquet padronizados** estruturados em diretórios organizados (`ano_competencia=2023/`, etc.).
- A camada transacional ACID é mantida no diretório `_delta_log/` com arquivos JSON contendo histórico de commits e *time travel*.
- Qualquer ferramenta do ecossistema de dados aberto (DuckDB, Polars, Apache Spark, Trino, Dremio) pode ler a tabela diretamente.

#### 6.2. Serialização e Compressão Justificadas
- **Formato Colunar:** Parquet é ideal para a Pergunta de Gestão, pois permite que o leitor analítico leia apenas as colunas necessárias (`valor_liquido`, `sigla_partido_emissao`, `ano_competencia`), ignorando URLs de documentos e textos longos.
- **Compressão Zstandard (`zstd`):**
  - Reduziu o tamanho total dos 785 mil registros de **178 MB (no Postgres)** e **265 MB (em CSV)** para apenas **64,8 MB** no Delta Lake (redução de 63,5%).
  - Proporciona tempo de consulta de agregação analítica no DuckDB de apenas **18 ms**.

---

### 7. Como Executar e Reproduzir Localmente

#### 7.1. Execução Única Completa via Docker Compose
No diretório raiz do projeto, execute:
```bash
docker compose up --build
```
O comando realiza automaticamente:
1. Inicialização do PostgreSQL 16 com `wal_level = logical`.
2. Aplicação de todas as migrações (`001`, `002` e `003`).
3. Carga relacional transacional dos 785.754 registros.
4. Ingestão em lote para o Lakehouse Delta Lake.
5. Enriquecimento de Sócios (QSA) e Beneficiário Final da Receita Federal.
6. Execução automatizada dos 5 testes de aceite da monitoria.

#### 7.2. Execução Isolada da Bateria de Testes
Caso queira rodar apenas a validação de aceite da E2:
```bash
docker exec -it ceap_ingestion python scripts/test_e2_pipeline.py
```

#### 7.3. Exemplo de Consulta Analítica com DuckDB (Terminal)
```bash
docker exec -it ceap_ingestion python -c "
import duckdb
con = duckdb.connect()
print(con.execute('''
    SELECT 
        ano_competencia,
        COUNT(*) AS total_despesas,
        ROUND(SUM(valor_liquido), 2) AS total_recursos
    FROM delta_scan('lakehouse/delta/despesa_ceap')
    GROUP BY ano_competencia
    ORDER BY ano_competencia;
''').fetchdf())
"
```

---

### 8. Matriz de Conformidade com o Checklist de Aceite

| Item Oficial do Checklist | Situação | Evidência no Repositório |
| :--- | :---: | :--- |
| **Ingestão em lote da fonte pública, idempotente e reexecutável** | Concluído | `scripts/batch_ingest_lakehouse.py` e `test_1_idempotencia_batch` |
| **Fluxo de mudanças a partir do OLTP (CDC por decodificação lógica)** | Concluído | `scripts/cdc_stream_consumer.py`, `003_setup_cdc_replication.sql` e `test_2_cdc_mutacao_atravessando_fluxo` |
| **Camada analítica em formato aberto (Parquet e tabela Delta Lake)** | Concluído | Pasta `lakehouse/delta/despesa_ceap/` com arquivos Parquet ZSTD e `_delta_log/` |
| **Semântica de entrega declarada e demonstrada** | Concluído | Declarada como *At-Least-Once com Deduplicação Idempotente* e provada em `test_4_reprocessamento_semantica_entrega` |
| **Tratamento explícito de dado atrasado e reprocessamento de janela** | Concluído | Roteamento por `ano_competencia` comprovado em `test_3_dado_atrasado_roteamento_de_janela` |
| **Escolha de serialização e compressão justificada pelo padrão de acesso** | Concluído | Justificativa técnica e métricas na `ADR-0002` (Parquet + Zstandard) |
| **1 ADR sobre a escolha do mecanismo de ingestão com opção nula** | Concluído | `docs/adr/0002-mecanismo-ingestao-e-formato-aberto.md` (Método de 6 passos) |
| **ADR Adicional sobre Enriquecimento Societário** | Concluído | `docs/adr/0003-resolucao-grafo-societario-beneficiario-final.md` (Método de 6 passos) |
| **Diário de bordo das Semanas da E2 no repositório** | Concluído | Arquivos `docs/diario/semana-06.md` e `semana-07.md` (período de 2 semanas até 13/10/2026) |
| **Enriquecimento Societário da Receita Federal (QSA / UBO)** | Concluído | `scripts/enrich_receita_socios.py`, `dim_quadro_societario_ubo` e `test_5_auditoria_societaria_beneficiario_final` |

