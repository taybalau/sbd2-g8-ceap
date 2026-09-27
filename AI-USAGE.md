# Registro de Uso de Inteligência Artificial (AI-USAGE)

Em conformidade com as diretrizes e a Política de Uso de Inteligência Artificial da disciplina de **Sistemas de Banco de Dados 2 (2026/2) — Universidade de Brasília (UnB)**, a **Squad G8** declara o uso transparente de assistentes de inteligência artificial durante o desenvolvimento da Entrega E1.

---

### 1. Ferramentas e Modelos Utilizados
- **Google Antigravity (com modelo Gemini 3.8 Flash)**: Utilizado como assistente de engenharia e pair programming no ambiente de desenvolvimento.

---

### 2. Escopo e Propósito do Uso

| Atividade / Artefato | Como a IA foi utilizada |
| :--- | :--- |
| **Modelagem Relacional (DDL)** | Apoio na estruturação inicial dos scripts SQL (`migrations/001_create_tables.sql` e `002_create_indexes.sql`), sugerindo tipos de dados nativos para PostgreSQL e mapeamento das colunas da CEAP. |
| **Pipeline de Ingestão Python** | Auxílio na codificação do script de download concorrente e extração de arquivos `.zip` oficiais (`scripts/download_data.py`) e do mecanismo de carga em massa via `COPY` (`scripts/ingest_ceap.py`). |
| **Orquestração Docker** | Suporte na elaboração do `docker-compose.yml` com definição de `healthcheck` para evitar condições de corrida entre o banco de dados e a rotina de carga. |
| **Documentação e ADR** | Auxílio na formatação do ADR-0001 segundo o padrão Nygard em 6 etapas exigido pelo método de decisão da disciplina. |

---

### 3. Validação Humana e Responsabilidade Técnica

Todo o código, esquema e documentação gerados com o apoio do assistente foram rigorosamente inspecionados, revisados e testados pelos integrantes da Squad G8:
- **Análise dos Dados Reais:** A equipe identificou as inconsistências do dataset público da Câmara (valores negativos em estornos de passagens aéreas pelo SIGEPA, telefonia com datas vazias e lideranças sem CPF), ajustando os tipos de dados e constraints para que o banco aceitasse a realidade dos dados abertos sem corrupção.
- **Validação de Performance:** A decisão pelo uso de tabelas de staging unlogged e comandos `COPY` foi medida e comprovada empiricamente no ambiente local.
- **Autoria:** A Squad G8 assume integral responsabilidade técnica pelo funcionamento, integridade dos dados e defesa conceitual das decisões registradas.
