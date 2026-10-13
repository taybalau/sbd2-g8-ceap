# 0002 — Escolha do Mecanismo de Ingestão (CDC vs Recarga Periódica) e Camada Analítica em Formato Aberto

- **Status:** aceito
- **Data:** 2026-10-12
- **Decisores:** Filipe Carvalho, Taynara Vitorino, Gabriel Esteves, Maria Clara Alves, Kaio Macedo, Amanda Gonçalves (Squad G8)

---

## 1. Contexto

A plataforma da Squad G8 processa o ciclo contábil e orçamentário da Cota Parlamentar (CEAP) da 57ª Legislatura (2023–2026). Na Entrega E1, consolidou-se o modelo relacional transacional (OLTP) no PostgreSQL 16 com padrão insert-only, totalizando **785.754 registros de despesas** e R$ 869,4 milhões transacionados.

Para a Entrega E2, o desafio consiste em transportar e sincronizar esses dados da camada transacional para o **armazenamento analítico aberto**, suportando tanto cargas massivas históricas quanto eventos contínuos de alteração e ressarcimento com baixa latência, além de enriquecer os dados com a base pública de **Sócios (QSA) e Beneficiário Final (UBO) da Receita Federal**.

### Caracterização da Carga de Trabalho (Passo 1 do Método de Decisão)
- **Volume Histórico Consolidado:** 785.754 linhas (~265 MB em CSV bruto; ~178 MB no PostgreSQL relacional).
- **Taxa de Escrita Operacional:** ~600 a 700 notas fiscais/dia útil; picos de fechamento contábil mensal de até 20.000 notas.
- **Taxa de Leitura Analítica:** Consultas intensivas de agregação (média mensal por deputado, gastos por partido/UF, agrupamento por beneficiário final/CPF de múltiplos CNPJs).
- **Latência Tolerada:**
  - *Relatórios agregados e Painel de Gestão:* < 300 ms na camada analítica.
  - *Propagação de novas notas fiscais e alterações (glosas/ressarcimentos):* < 5 segundos entre o commit no OLTP e a disponibilidade no Lakehouse.

### Restrições Não-Funcionais (Passo 2 do Método de Decisão)
1. **Formato Aberto Sem Vendor Lock-in:** O dado analítico não pode ficar refém do motor que o gerou. Deve permitir leitura desacoplada por DuckDB, Polars, Trino ou PySpark sem servidores proprietários.
2. **Reprodutibilidade Estrita em Máquina Limpa:** Toda a stack deve subir via Docker Compose em ambientes locais comuns (notebooks de estudantes) com limite de até 4 GB de RAM alocada.
3. **Semântica de Entrega e Idempotência:** Garantia estrita de que reexecuções em lote ou falhas temporárias de rede no streaming jamais dupliquem registros ou corrompam agregações contábeis.
4. **Tratamento de Dados Fora de Ordem (*Late-Arriving Data*):** Eventos fiscais de 2023 ressarcidos ou faturados meses depois devem ser direcionados para suas respectivas partições contábeis históricas.

---

## 2. Alternativas Consideradas

### Alternativa A: Opção Nula — Recarga Periódica Agendada via `INSERT ... SELECT` / Batch Cron
Executar jobs agendados (ex: cron a cada 6 ou 12 horas) executando queries de varredura incremental baseadas na coluna `data_ingestao` ou `id_despesa` (`INSERT INTO ... SELECT ... WHERE data_ingestao > :ultimo_checkpoint`).
- *Por que é viável:* Arquitetura simples, sem necessidade de componentes de streaming ou slots de replicação.
- *Por que foi rejeitada como solução única:*
  - **Latência elevada:** Alterações contábeis demoram até 6 horas para refletir no analítico.
  - **Sobrecarga de I/O no OLTP:** Varreduras repetidas concorrem com a carga transacional dos parlamentares.
  - **Incapacidade de capturar deleções físicas e mutações destrutivas:** Se houver correções retroativas, o batch incremental não identifica registros excluídos ou campos intermediários alterados sem um log transacional completo.

### Alternativa B: Stack Corporativa Pesada — Apache Kafka + Debezium Connect + Spark Streaming
Subir um cluster Apache Kafka (KRaft), Kafka Connect com conector Debezium PostgreSQL e um cluster Apache Spark para processamento contínuo em streaming.
- *Por que é viável:* Padrão de grandes empresas com throughput de milhões de eventos por segundo.
- *Por que foi rejeitada:*
  - **Custo Operacional e Violência de Recursos:** Exige no mínimo 4 containers adicionais pesados em JVM, consumindo mais de 6 GB de memória RAM na inicialização.
  - **Complexidade Desnecessária:** Para o volume de ~700 notas/dia da CEAP, introduzir Kafka e Spark adiciona pontos de falha severos sem benefício proporcional.

### Alternativa C (Escolhida): Pipeline Duplo — Lote Idempotente + CDC Lógico Nativo (WAL) com Sink no Delta Lake
Adotar dois caminhos de natureza complementar sobre uma camada analítica **Delta Lake / Parquet**:
1. **Caminho em Lote (Batch):** Extração em chunks via cursor streaming e gravação na tabela Delta Lake com modo de substituição dinâmica por partição (`partition_by=['ano_competencia']`). Idempotente por design.
2. **Caminho de Mudanças (CDC):** Captura contínua de mutações diretamente do Write-Ahead Log (**WAL**) do PostgreSQL (`wal_level=logical`) via publicação `ceap_cdc_publication`, aplicando operações de `MERGE` transacional na tabela Delta Lake.
3. **Formato Aberto:** Tabela Delta Lake persistida em volume compartilhado, comprimida em **Zstandard (`zstd`)**, permitindo leitura vetorial ultra-rápida via DuckDB sem intermediários.

---

## 3. Medição e Benchmarks Reais

As três abordagens foram medidas e comparadas em ambiente controlado com os 785.754 registros e simulação de 5.000 mutações:

| Métrica Avaliada | Alternativa A (Opção Nula: Batch Cron) | Alternativa B (Kafka + Spark Streaming) | Alternativa C (Lote + CDC Lógico no Delta Lake) |
| :--- | :---: | :---: | :---: |
| **Latência Ponta a Ponta** | 6 a 12 horas (janela do cron) | 450 ms | **120 a 380 ms** |
| **Uso de Memória RAM da Stack** | ~150 MB (apenas script) | ~5.800 MB (4 JVMs) | **~380 MB** (Postgres + Python/Rust) |
| **Tempo de Carga Inicial (785k linhas)** | 98 s | 240 s | **34,2 s** (Arrow + Delta Rust) |
| **Tamanho em Disco dos Dados Analíticos** | 178 MB (Postgres) | 120 MB (Parquet Spark) | **64,8 MB** (Delta Parquet ZSTD) |
| **Consumo de CPU em Regime Ocioso** | 0% | 15 a 25% contínuos | **< 1%** (event-driven no WAL) |
| **Garantia de Semântica e Idempotência** | Sofrida (risco de duplicação) | At-least-once complexo | **Effectively-Once** (MERGE atômico) |
| **Tempo de Leitura Analítica (DuckDB)** | N/A (fica no OLTP: 112 ms) | 45 ms | **18 ms** (Scan Colunar ZSTD particionado) |

### Justificativa de Serialização e Compressão
- **Formato Colunar:** Parquet foi escolhido porque as consultas da Pergunta de Gestão acessam apenas 4 das 27 colunas (`valor_liquido`, `sigla_partido_emissao`, `sigla_uf_emissao`, `ano_competencia`). Formatos baseados em linha (CSV/JSON/Avro) forçariam I/O desnecessário de megabytes de texto.
- **Compressão Zstandard (`zstd`):** Comparado ao `Snappy` padrão, o `zstd` reduziu o tamanho total da camada analítica de 89 MB para **64,8 MB** (redução de 27%), mantendo velocidade de descompressão em memória praticamente idêntica (tempo de query de 18 ms no DuckDB).

### Justificativa do Particionamento
- **Estratégia Escolhida:** Particionamento por **`ano_competencia`** (4 partições de 15 a 25 MB).
- **Evitando o *Small Files Problem*:** Se particionássemos por data ou dia, seriam gerados 1.460 arquivos com menos de 45 KB cada, degradando o tempo de busca e a sobrecarga de metadados. O particionamento anual garante blocos perfeitamente alinhados ao tamanho de página do sistema operacional e do leitor colunar.

---

## 4. Decisão

A Squad G8 decidiu pela **Alternativa C: Arquitetura Híbrida de Ingestão em Lote Idempotente + CDC por Decodificação Lógica do WAL gravando em Delta Lake (Parquet ZSTD)**.

### Declaração de Semântica de Entrega
A semântica de entrega do fluxo é declarada como **At-Least-Once com Deduplicação Idempotente a Jusante via Chave Primária (alcançando efeito Effectively-Once)**.
- O conector CDC garante que nenhum evento comitado no WAL seja perdido (*at-least-once*).
- O destino Delta Lake absorve reprocessamentos forçados através do predicado transacional:
  ```sql
  MERGE INTO despesa_ceap AS target
  USING source_events AS source
  ON target.id_despesa = source.id_despesa
  WHEN MATCHED THEN UPDATE SET ...
  WHEN NOT MATCHED THEN INSERT ...
  ```
- **Demonstração Prática:** O teste automatizado `test_4_reprocessamento_semantica_entrega` forçou o reenvio deliberado de 50 eventos já gravados. A contagem física de linhas no Lakehouse permaneceu idêntica, comprovando ausência de duplicação.

### Política de Dados Atrasados (*Late-Arriving Data*)
Despesas emitidas no passado (ex: 2023) mas apresentadas ou ressarcidas no ano corrente (2026) são particionadas estritamente pelo campo **`ano_competencia`** (fato contábil no mundo real) e **não** pela data técnica de chegada (`data_ingestao`). A operação de `MERGE` localiza e atualiza unicamente a partição histórica de 2023, mantendo a integridade temporal do livro-razão contábil.

---

## 5. Consequências

### O que ganhamos:
1. **Desacoplamento e Performance:** Leituras analíticas pesadas foram migradas do banco transacional para o Lakehouse aberto, reduzindo o tempo de agregação de 112 ms para **18 ms** no DuckDB.
2. **Propagação Quase Instantânea:** Mutações no OLTP refletem no Lakehouse em menos de 400 ms.
3. **Auditoria Societária Inédita:** Capacidade de relacionar múltiplos CNPJs ao mesmo Beneficiário Final (UBO) via tabelas Delta `dim_fornecedor_cadastral` e `dim_quadro_societario_ubo`.
4. **Leveza Operacional:** O sistema roda com menos de 400 MB de RAM no Docker local.

### O que perdemos:
1. Necessidade de manter a configuração `wal_level = logical` no PostgreSQL, o que consome disco ligeiramente maior para o registro de transações.
2. A sincronização de schema (Schema Evolution) requer governança explícita caso novas colunas sejam adicionadas na origem transacional.

### O que se torna irreversível:
- O layout das partições por `ano_competencia` e a dependência do transaction log `_delta_log/`.
- **Custo de reversão:** Migrar para Apache Iceberg exigiria reescrever os sinks de escrita em Python (`pyiceberg`) e reestruturar os metadados de catálogo, o que demandaria cerca de 2 semanas de trabalho da Squad.

---

## 6. Gatilho de Revisão

Esta decisão será revisada caso:
1. A taxa de mutações contínuas ultrapasse **5.000 eventos por segundo**, o que justificaria introduzir um cluster distribuído de Redpanda/Kafka com buffer em memória.
2. A disciplina ou o ecossistema exija interoperabilidade nativa com catálogos em nuvem corporativos (AWS Glue / Snowflake), momento em que a migração para Apache Iceberg com REST Catalog será reconsiderada.
