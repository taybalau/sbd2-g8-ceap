# Registro de Uso de Inteligência Artificial (AI-USAGE)

Em conformidade com as diretrizes e a Política de Uso de Inteligência Artificial da disciplina de **Sistemas de Banco de Dados 2 (2026/2) — Universidade de Brasília (UnB)**, a **Squad G8** declara o uso transparente de assistentes de inteligência artificial durante o desenvolvimento das Entregas E1 e E2.

---

### 1. Ferramentas e Modelos Utilizados
- **Google Antigravity (com modelo Gemini 3.8 Flash)**: Utilizado como assistente de engenharia de dados, design de arquitetura e pair programming no ambiente de desenvolvimento.

---

### 2. Escopo e Propósito do Uso nas Entregas

| Atividade / Artefato | Como a IA foi utilizada |
| :--- | :--- |
| **Modelagem Relacional Transacional (E1)** | Apoio na estruturação inicial dos scripts SQL (`migrations/001_create_tables.sql` e `002_create_indexes.sql`), sugerindo tipos de dados nativos para PostgreSQL e mapeamento das colunas da CEAP. |
| **Pipeline de Ingestão e Carga OLTP (E1)** | Auxílio na codificação do script de download concorrente (`scripts/download_data.py`) e do mecanismo de carga em massa via `COPY` (`scripts/ingest_ceap.py`). |
| **Camada Analítica Delta Lake (E2)** | Suporte no design e codificação da ingestão em lote idempotente com PyArrow e Delta Lake (`scripts/batch_ingest_lakehouse.py`), particionamento por competência e compressão Zstandard. |
| **Captura de Mudanças - CDC (E2)** | Auxílio na arquitetura de decodificação lógica do WAL do PostgreSQL (`scripts/cdc_stream_consumer.py` e `migrations/003_setup_cdc_replication.sql`) e implementação de `MERGE` transacional com semântica *at-least-once com deduplicação idempotente*. |
| **Enriquecimento Societário da Receita (E2)** | Auxílio na estruturação do algoritmo recursivo de identificação do Beneficiário Final (UBO) e grupos econômicos (`scripts/enrich_receita_socios.py`). |
| **Roteiro de Testes de Aceite (E2)** | Apoio na construção da suíte automatizada de validação de idempotência, dados atrasados e mutação OLTP (`scripts/test_e2_pipeline.py`). |
| **Documentação Técnica e ADRs (E1 e E2)** | Auxílio na formatação e consolidação das decisões de engenharia segundo o método de 6 etapas de Nygard (`ADR-0001` e `ADR-0002`), além do guia técnico `docs/PIPELINE_E2.md`. |

---

### 3. Validação Humana e Responsabilidade Técnica

Todo o código, esquema e documentação elaborados com o apoio do assistente foram rigorosamente inspecionados, revisados e testados pelos integrantes da Squad G8:
- **Análise dos Dados Reais:** A equipe identificou as peculiaridades dos dados públicos da Câmara e da Receita Federal, garantindo consistência contábil, integridade referencial e precisão analítica.
- **Validação de Performance e Métricas:** As medições comparativas da ADR-0002 (latência de CDC de subsegundo vs horas do cron da opção nula, compressão Zstandard e testes de idempotência) foram verificadas e defendidas pela equipe.
- **Autoria:** A Squad G8 assume integral responsabilidade técnica pelo funcionamento, integridade dos dados e defesa conceitual das decisões registradas.
