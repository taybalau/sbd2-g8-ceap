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

O desenvolvimento contou com o assistente Google Antigravity (conforme declarado em [`AI-USAGE.md`](AI-USAGE.md)), com revisão e validação humana de todo o código, esquema e documentação pela Squad G8.
