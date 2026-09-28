# Plataforma de Dados da Cota Parlamentar (CEAP) — 57ª Legislatura
## Sistemas de Banco de Dados 2 (2026/2) — Universidade de Brasília (UnB)
### Squad G8

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

---

### 2. Arquitetura da Entrega E1: Fonte Transacional (OLTP)

A primeira etapa do ciclo de vida dos dados estabelece um banco transacional relacional robusto, normalizado e estritamente tipado:

- **SGBD:** PostgreSQL 16 (executado via Docker Compose).
- **Volume Real de Dados:** **785.754 registros de despesas** consolidados dos anos completos de 2023 a 2026 (~265 MB descompactados, R$ 869,4 milhões transacionados).
- **Tratamento de Histórico:** Padrão **Insert-Only (Livro-Razão Contábil)**. As despesas são fatos fiscais imutáveis. Restituições e glosas são registradas em campos de controle financeiro, sem mutabilidade destrutiva via `UPDATE`.
- **Três Carimbos de Tempo:**
  1. `data_emissao`: Momento do evento no mundo real (emissão da nota pelo fornecedor).
  2. `data_pagamento_restituicao`: Momento do evento de compensação aos cofres públicos.
  3. `data_ingestao`: Momento do registro e auditoria pelo sistema de banco de dados (`TIMESTAMP DEFAULT CURRENT_TIMESTAMP`).

---

### 3. Como Subir a Plataforma do Zero (Execução Reprodutível)

A plataforma foi projetada para subir **do zero em máquina limpa** a partir do repositório, sem nenhum passo manual de download de arquivos ou configuração prévia de banco:

#### Pré-requisitos
- [Docker](https://docs.docker.com/get-docker/) instalado e ativo.
- [Docker Compose](https://docs.docker.com/compose/) v2+.

#### Comando Único de Execução
No diretório raiz do projeto clonado, execute:

```bash
docker compose up --build
```

#### O que o comando faz automaticamente:
1. Sobe o container do **PostgreSQL 16** e aguarda o healthcheck (`pg_isready`).
2. Dispara o container de **ingestão**, que:
   - Executa as migrações em ordem sequencial a partir de `migrations/` (`001_create_tables.sql` e `002_create_indexes.sql`), registrando versões na tabela `schema_migrations`.
   - Verifica se os arquivos CSV já existem localmente em `base-dados/`; se não existirem, **faz o download automatizado** dos arquivos oficiais compactados (`.zip`) diretamente do portal da Câmara dos Deputados (`http://www.camara.leg.br/cotas/`).
   - Carrega os dados via PostgreSQL `COPY` em tabela de staging unlogged e executa a carga relacional com integridade referencial em segundos.
   - Executa uma query de validação no terminal demonstrando os resultados da pergunta de gestão.

---

### 4. Como Conectar e Consultar o Banco

Você pode conectar ao banco usando qualquer cliente SQL (DBeaver, pgAdmin, VSCode ou `psql`):

- **Host:** `localhost` (ou `127.0.0.1`)
- **Porta:** `5432`
- **Banco de Dados:** `ceap_oltp`
- **Usuário:** `postgres`
- **Senha:** `postgres`

#### Exemplo de Consulta Via Terminal (Container Docker)
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

---

### 5. Documentos e Governança

- **ADR-0001 (Decisão Arquitetural):** [docs/adr/0001-modelagem-transacional-insert-only-ceap.md](docs/adr/0001-modelagem-transacional-insert-only-ceap.md) — Aplica os 6 passos do Método de Decisão para a modelagem relacional insert-only e carimbos de tempo.
- **Diários de Bordo da Squad:** [docs/diario/](docs/diario/) — Registros semanais da concepção e execução da Squad G8 (Semanas 01 a 05: 24/08 a 28/09/2026).
- **Política de IA:** [AI-USAGE.md](AI-USAGE.md) — Registro transparente do uso de inteligência artificial.
