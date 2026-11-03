# Plataforma de Dados da Cota Parlamentar (CEAP) — 57ª Legislatura
## Sistemas de Banco de Dados 2 (2026/2) — Universidade de Brasília (UnB)
### Squad G8

📘 **Documentação completa:** https://taybalau.github.io/sbd2-g8-ceap/

---

### Integrantes da Squad G8
- Filipe Carvalho
- Taynara Vitorino
- Gabriel Esteves
- Maria Clara Alves
- Kaio Macedo
- Amanda Gonçalves

---

### 1. Domínio e Pergunta de Gestão

A **Cota para o Exercício da Atividade Parlamentar (CEAP)** custeia despesas ligadas ao exercício do mandato parlamentar dos deputados federais (passagens aéreas, aluguel de escritórios, combustíveis, consultorias, segurança, entre outros).

A plataforma de dados foi construída para responder com precisão à seguinte pergunta de gestão:

> **"Quais parlamentares e partidos da 57ª Legislatura (2023–2026) apresentam maior desvio de gastos acima da média mensal da Cota Parlamentar (CEAP), e quais categorias e fornecedores concentram esses recursos?"**

Com o enriquecimento da **Entrega E2**, a pergunta ganha profundidade de auditoria societária:
> *"Quais despesas da CEAP pagas a múltiplos CNPJs aparentemente concorrentes concentram recursos no mesmo Beneficiário Final (mesmo CPF ou grupo econômico controlador)?"*

---

### 2. Arquitetura da Entrega E1: Fonte Transacional (OLTP)

A primeira etapa do ciclo de vida dos dados estabeleceu um banco transacional relacional robusto, normalizado e estritamente tipado:

- **SGBD:** PostgreSQL 16 (executado via Docker Compose).
- **Volume Real de Dados:** **785.754 registros de despesas** consolidados dos anos completos de 2023 a 2026 (~265 MB descompactados, R$ 869,4 milhões transacionados).
- **Tratamento de Histórico:** Padrão **Insert-Only (Livro-Razão Contábil)**. As despesas são fatos fiscais imutáveis. Restituições e glosas são registradas em campos de controle financeiro, sem mutabilidade destrutiva via `UPDATE`.
- **Três Carimbos de Tempo:**
  1. `data_emissao`: Momento do evento no mundo real (emissão da nota pelo fornecedor).
  2. `data_pagamento_restituicao`: Momento do evento de compensação aos cofres públicos.
  3. `data_ingestao`: Momento do registro e auditoria pelo sistema de banco de dados (`TIMESTAMP DEFAULT CURRENT_TIMESTAMP`).

---

### 3. Arquitetura da Entrega E2: Ingestão em Lote, CDC e Lakehouse Aberto

A segunda etapa estabelece a movimentação analítica de dados sem lock-in, através de dois caminhos de natureza distinta e enriquecimento público:

- **Caminho 1 (Em Lote):** Pipeline em lote idempotente que grava os dados da CEAP na tabela **Delta Lake** (`lakehouse/delta/despesa_ceap`), particionada por `ano_competencia` e comprimida em **Zstandard (`zstd`)**. A reexecução é comprovadamente idempotente (0 linhas duplicadas).
- **Caminho 2 (Captura de Mudanças - CDC):** Captura contínua de mutações a partir da decodificação lógica do Write-Ahead Log (**WAL**) do PostgreSQL (`wal_level=logical`), aplicando `MERGE` atômico na tabela Delta com semântica **At-Least-Once com Deduplicação Idempotente (Effectively-Once)**.
- **Tratamento de Dado Atrasado (*Late-Arriving Data*):** Eventos fiscais com atraso de meses/anos são roteados e consolidados na partição histórica de sua competência real (`ano_competencia`), preservando o fechamento contábil.
- **Enriquecimento com a Receita Federal (QSA e Beneficiário Final):** Mapeamento do Quadro de Sócios e Administradores com algoritmo recursivo de UBO (*Ultimate Beneficial Owner*), identificando grupos econômicos reais onde múltiplos CNPJs pertencem à mesma pessoa física.

---

### 3.1 Arquitetura da Entrega E3: Esquema Estrela, Testes de Domínio, Orquestração e Painel

Documento completo: [docs/e3.md](docs/e3.md) · ADRs [0004](docs/adr/0004-avaliacao-etl-relacional-postgres-vs-lakehouse-direto.md), [0005](docs/adr/0005-modelagem-dimensional-granularidade-scd-ceap.md) (com revisão de 2026-11-03), [0006](docs/adr/0006-orquestracao-falha-controlada-e-backfill.md) e [0007](docs/adr/0007-ferramenta-do-painel-analitico.md) · Consulta otimizada (EXPLAIN antes e depois): [docs/explain/](docs/explain/README.md).

- **Direct-to-Lakehouse:** CSV da Câmara → Bronze Delta (`ingestao/bronze.py`, partição por ano, idempotente) + histórico oficial de deputados via API (`ingestao/bronze_historico.py`).
- **dbt (`dbt_ceap/`):** fato `fct_lancamento_ceap` com grão declarado (uma linha por lançamento publicado), `dim_parlamentar_scd` (SCD tipo 2 a partir do histórico oficial, porque o CSV regrava o partido atual) e marts Gold que respondem à pergunta de gestão.
- **Testes de domínio:** negativo fora de subcota de compensação, salto de série por subcota, subcota que some entre anos, reconciliação Bronze ↔ fato ↔ Gold e regressão do SCD com caso real.
- **Dagster (`orquestracao/`):** retry com backoff, falha de fonte sem propagação e backfill por ano. Tudo isso é exercitado por `orquestracao/demo_falhas.py`.
- **Painel (`painel/app.py`):** três blocos, um por parte da pergunta (Streamlit; justificativa no ADR-0007).
- **Freshness e SLA:** Gold publicada até 26 h após a ingestão (`gold.mart_freshness_gold`, teste `assert_gold_dentro_do_sla`).

```bash
docker compose up --build   # E1/E2 + pipeline da E3 + Dagster (:3000) + painel (:8501)
```

---

### 4. Como Subir a Plataforma do Zero (Execução Reprodutível)

A plataforma foi projetada para subir **do zero em máquina limpa** a partir do repositório, sem nenhum passo manual de configuração:

#### Pré-requisitos
- [Docker](https://docs.docker.com/get-docker/) instalado e ativo.
- [Docker Compose](https://docs.docker.com/compose/) v2+.

#### Comando Único de Execução
No diretório raiz do projeto clonado, execute:

```bash
docker compose up --build
```

#### O que o comando executa automaticamente:
1. Sobe o **PostgreSQL 16** com replicação lógica habilitada (`wal_level=logical`).
2. Dispara o container de **ingestão**, que:
   - Executa as migrações sequenciais em `migrations/` (`001` a `004`), criando tabelas, índices, publicação lógica de CDC e a view de gasto mensal da E3.
   - Baixa (ou valida o cache local) dos CSVs oficiais da CEAP (2023 a 2026).
   - Realiza a carga transacional OLTP via `COPY` em tabela unlogged e normalização com integridade referencial.
   - Executa a **Ingestão em Lote para o Delta Lake** (`batch_ingest_lakehouse.py`).
   - Gera o **Enriquecimento de Sócios (QSA) e Beneficiário Final** da Receita Federal (`enrich_receita_socios.py`).
   - Roda a **Bateria Completa de Testes de Aceite da E2** (`test_e2_pipeline.py`) demonstrando:
     - Idempotência do lote (execução dupla = 0 duplicatas);
     - CDC em ação com mutações no OLTP refletidas no Lakehouse em subsegundo;
     - Tratamento explícito de dados atrasados;
     - Semântica de entrega e deduplicação;
     - Auditoria analítica de grupos econômicos e sócios UBO.
3. Quando a ingestão termina, sobe a **E3**:
   - `e3-pipeline`: Bronze Delta a partir dos CSVs, histórico de deputados pela API da Câmara e `dbt build` (Silver e Gold com todos os testes), mais o `dbt source freshness`. Termina com erro se algum passo falhar.
   - `e3-dagster` em http://localhost:3000: grafo, execuções, schedule diário e backfill por ano.
   - `e3-painel` em http://localhost:8501: painel que responde à pergunta de gestão.

---

### 5. Como Consultar o Lakehouse Aberto (DuckDB / Zero Lock-in)

Você pode consultar diretamente os dados analíticos abertos usando **DuckDB** sem precisar de nenhum servidor intermediário:

```bash
docker exec -it ceap_ingestion python -c "
import duckdb
con = duckdb.connect()
print(con.execute('''
    SELECT 
        ano_competencia,
        COUNT(*) AS total_notas,
        ROUND(SUM(valor_liquido), 2) AS total_gasto
    FROM delta_scan('lakehouse/delta/despesa_ceap')
    GROUP BY ano_competencia
    ORDER BY ano_competencia;
''').fetchdf())
"
```

---

### 6. Documentos e Governança

- **Documento Explicativo da Pipeline E2:** [docs/PIPELINE_E2.md](docs/PIPELINE_E2.md) — Detalhamento técnico de ponta a ponta dos dois caminhos, do enriquecimento societário e da garantia de semântica.
- **ADR-0001 (Decisão Arquitetural OLTP):** [docs/adr/0001-modelagem-transacional-insert-only-ceap.md](docs/adr/0001-modelagem-transacional-insert-only-ceap.md) — Modelagem relacional insert-only e carimbos de tempo.
- **ADR-0002 (Decisão Arquitetural E2 - Ingestão e Lakehouse):** [docs/adr/0002-mecanismo-ingestao-e-formato-aberto.md](docs/adr/0002-mecanismo-ingestao-e-formato-aberto.md) — CDC vs Recarga Periódica (Opção Nula), Delta Lake e Compressão Zstandard.
- **ADR-0003 (Decisão Arquitetural E2 - Enriquecimento Societário):** [docs/adr/0003-resolucao-grafo-societario-beneficiario-final.md](docs/adr/0003-resolucao-grafo-societario-beneficiario-final.md) — Resolução em Grafo da Cadeia Societária e Beneficiário Final (UBO).
- **Diários de Bordo da Squad G8:** [docs/diario/](docs/diario/) — Registros semanais detalhados:
  - Semanas 01 a 05: Concepção, modelagem transacional e Entrega E1 (24/08 a 28/09/2026).
  - Semanas 06 e 07: Ingestão em lote, CDC, enriquecimento QSA da Receita e Entrega E2 (29/09 a 13/10/2026).
- **Política de IA:** [AI-USAGE.md](AI-USAGE.md) — Registro transparente do uso de inteligência artificial.

