# Release Notes — v3.0 (Entrega E3) · Plataforma de Dados da CEAP

**Projeto:** `sbd2-g8-ceap` — Plataforma de Dados da Cota Parlamentar (CEAP), 57ª Legislatura  
**Disciplina:** Sistemas de Banco de Dados 2 (2026/2) — Universidade de Brasília (UnB)  
**Squad:** G8 — Filipe Carvalho, Taynara Vitorino, Gabriel Esteves, Maria Clara Alves, Kaio Macedo, Amanda Gonçalves  
**Tag Git:** `e3`  
**Data de entrega:** DD/MM/2026 *(preencher)*  
**Repositório:** [https://github.com/taybalau/sbd2-g8-ceap](https://github.com/taybalau/sbd2-g8-ceap)

---

## 1. Resumo

A E3 entrega a **camada de transformação, qualidade, orquestração e consumo analítico** da plataforma CEAP. Sobre o Lakehouse da E2, a Squad construiu um pipeline Bronze → Silver → Gold em dbt, com **modelo dimensional (estrela) de grão declarado**, **testes que verificam a sujeira real do domínio**, **orquestração com Dagster que falha de forma controlada** e um **painel em Streamlit** que responde à pergunta de gestão da E1:

> *"Quais parlamentares e partidos da 57ª Legislatura (2023–2026) apresentam maior desvio de gastos acima da média mensal da CEAP, e quais categorias e fornecedores concentram esses recursos?"*

Os pilares da entrega são:

1. **Modelagem dimensional com SCD tipo 2**: fatos e dimensões com grão declarado e testado, e `dim_parlamentar_scd` construída do histórico oficial da API da Câmara, porque o CSV regrava o partido com o valor atual do deputado.
2. **Testes de domínio no `dbt build`**: reconciliação com a Bronze, saltos de série por subcota, valores negativos fora das subcotas de compensação, janelas do SCD contíguas, entre outros. Falhas ficam gravadas no schema `auditoria`.
3. **Orquestração que falha**: retry com espera crescente, falha de fonte sem alterar a Gold publicada, teste reprovado que bloqueia a publicação e backfill por partição anual com Gold de hash idêntico.
4. **Painel e governança de consumo**: três blocos (parlamentares, partidos, categorias e fornecedores), SLA de 26 h para a Gold, freshness medido e tratamento de LGPD.

---

### Números da Entrega (E3)

Medidos sobre os CSVs da Câmara baixados em 2026-09-28 e o histórico da API extraído em 2026-11-03.

| Métrica | Valor na E2 | Valor na E3 | Impacto / Ganho |
|:--|:--:|:--:|:--:|
| **Lançamentos na Bronze** | 785.754 (Delta `despesa_ceap`) | **785.929** (`bronze/ceap_lancamento`) | Diferença de 175 linhas explicada: a Câmara regera os CSVs; reconciliação com o fato é obrigatória |
| **Chave do fato** | `id_despesa` (`BIGSERIAL` da E1) | **`id_lancamento`** (hash de todos os campos de origem) | `ideDocumento` vale 0 em 30.357 linhas e se repete em até 9 |
| **Camadas** | Delta Lake (fato + dimensões de QSA) | **Bronze, Silver e Gold** (dbt) | Linhagem completa até o painel |
| **Partido do deputado** | Partido do CSV | **SCD tipo 2** pela data do gasto | Evita enviar **R$ 33,4 mi** ao partido errado; o CSV diverge do histórico em **173.413 lançamentos (22%)** |
| **Testes de domínio** | 5 testes de aceite | **11 testes de domínio** + reconciliações e testes de SLA | 2 em severidade de aviso; os demais barram o build |
| **Consulta de desvio no PostgreSQL** | N/A | **~209 ms → ~33 ms** | **6,3x mais rápida**; páginas lidas **21.428 → 206**; resultado idêntico |
| **Gold publicada** | N/A | 5 tabelas: **622**, **26**, **86.485**, **23.458** e **4** linhas | Arquivo `ceap.duckdb` com 128 MB |
| **SLA da Gold** | N/A | **26 h** após a ingestão do CSV | Ingestão às 06:00, 2 h de margem para retry |
| **Painel (memória)** | N/A | 56 MB em repouso · 259 MB carregado | ~700 MB a menos que o Metabase em repouso (~961 MB) |
| **Painel (tempo até responder)** | N/A | 6 s | Metabase: 40 s |
| **Backfill 2023 e 2024** | N/A | Hash da Gold **idêntico** | Só as partições pedidas ganham novo `_ingerido_em` |
| **Erros tratados e documentados** | N/A | **29 itens** | 6 da orientação, 14 da fonte, 7 do pipeline e 2 de LGPD |

---

## 2. Novidades da Entrega E3

### 1. Modelo Dimensional com Grão Declarado (`dbt_ceap/models/`)

- Cada modelo declara o grão na descrição e em `meta.grao`, e o teste `grao_unico` verifica a declaração.
- Fatos: `fct_lancamento_ceap` (lançamento publicado) e `fct_gasto_mensal_parlamentar` (deputado × versão × competência).
- Dimensões: `dim_parlamentar_scd` (tipo 2), `dim_fornecedor` (tipo 1, decisão justificada), `dim_categoria_despesa` e `dim_calendario`.
- Marts: `mart_desvio_parlamentar`, `mart_desvio_partido`, `mart_concentracao_parlamentar` e `mart_freshness_gold`.
- **Prevenção de dupla agregação:** colunas repetidas entre versões do mesmo mês estão marcadas como `meta.soma_proibida`; para somar por partido existe `desvio_alocado`, cujo rateio é verificado por teste.
- Média de referência calculada **por UF e mês**, porque o teto da cota varia por UF.

### 2. Dimensão de Variação Lenta (SCD Tipo 2)

- Construída do histórico de eventos da API `GET /deputados/{id}/historico` (`bronze/camara_deputado_historico`).
- Junção do fato pela data do gasto contra `[valido_de, valido_ate)`.
- `mart_desvio_partido` traz o resultado correto e o que se obteria com a sobrescrita (`*_se_sobrescrito`).
- Caso de regressão verificado na API: ideCadastro **204494** (PRD no CSV desde fev/2023; PATRIOTA até 07/02/2024 no histórico oficial).

### 3. Testes que Verificam o que o Domínio Tem de Sujo

Todos rodam no `dbt build`, com falhas em `auditoria` (`store_failures`).

- **Reconciliação:** `assert_fato_reconcilia_com_bronze`, `assert_gold_reconcilia_com_fato`, `assert_desvio_alocado_reconcilia`.
- **Valores:** `assert_negativo_somente_em_subcota_de_compensacao` e `assert_valor_inconsistente_sob_controle` (limite de 0,3%; hoje 0,12%).
- **Séries:** `assert_subcota_sem_salto`, `assert_serie_mensal_sem_salto`, `assert_serie_mensal_sem_lacuna` e `assert_subcota_nao_some_entre_anos`.
- **SCD:** `assert_scd_preserva_partido_da_epoca`, `assert_scd_caso_conhecido_204494` e `assert_scd_janelas_contiguas`.
- **Avisos:** `assert_divergencia_csv_vs_historico` (173.413 lançamentos) e `assert_deputado_ativo_nao_some_no_meio` (136 casos).
- **SLA:** `assert_gold_dentro_do_sla`.
- **Achado principal:** em **ago/2025 a subcota 998 (SIGEPA, mediana de R$ 3,5 mi/mês) deixa de ter débitos**. O teste do total não pegou, porque o total caiu só 21%; o teste por subcota pegou. A ruptura fica registrada em `seeds/ruptura_publicacao.csv`, e os testes ignoram só o que está registrado ali.

### 4. Orquestração com Dagster (`orquestracao/`)

- Assets Bronze com `RetryPolicy(max_retries=3, backoff=EXPONENTIAL)`; `bronze/ceap_lancamento` particionado por ano com `replaceWhere`.
- A coleta do histórico faz uma sondagem antes das ~860 requisições e **não grava nada** se mais de 1% dos deputados ficar sem histórico.
- Dois jobs: `ingestao_ceap` (particionado) e `transformacao`. O sensor `transforma_apos_ingestao` só dispara após ingestão bem-sucedida.
- Schedule `diario_ano_corrente` às 06:00; anos fechados por backfill sob demanda.
- Cada teste do dbt é um asset check; teste reprovado pula os modelos a jusante e a Gold anterior permanece.

### 5. Falhas Provocadas e Backfill (`orquestracao/demo_falhas.py`)

Cinco cenários, com evidências em `orquestracao/evidencias/*.json`:

- **`retry`:** duas leituras de `Ano-2025.csv` falham e o run conclui com sucesso.
- **`fonte_fora`:** falha após 3 retries; Bronze e Gold inalteradas.
- **`api_fora`:** falha após 3 retries; o dbt nem inicia; SCD e Gold iguais.
- **`dado_sujo`:** `vlrLiquido = -999.99` injetado reprova o teste; os 4 modelos Gold são pulados.
- **`backfill`:** 2023 e 2024 reprocessados; contagens por ano iguais e Gold com hash idêntico.

Além disso, `orquestracao/backfill_dagster.py` executou o **backfill real pelo daemon do Dagster**, com o sensor disparando a transformação após cada partição.

### 6. Painel Analítico (`painel/app.py`)

- Três blocos, um por parte da pergunta, cada um abrindo com a resposta em uma frase e um único gráfico: **parlamentares** (top 15 por desvio acumulado), **partidos** (pelo partido na data do gasto, com a tabela do erro da sobrescrita) e **categorias e fornecedores** (de um parlamentar escolhido, com os 10 maiores fornecedores).
- Limitações exibidas no próprio painel: janela comparável (fev/2023 a jul/2025), ruptura do SIGEPA e meses em maturação. **Desvio não é irregularidade.**
- Leitura da Gold em modo somente leitura (`duckdb.connect(read_only=True)`), para não travar o dbt.

### 7. Freshness, SLA e LGPD

- **SLA:** Gold publicada em até **26 h** após a ingestão do CSV (`gold.mart_freshness_gold`, `assert_gold_dentro_do_sla`, `dbt source freshness` e alerta no painel).
- **Maturação:** o ranking usa só competências fechadas (`meses_maturacao: 4`), porque freshness não é o mesmo que dado atrasado.
- **LGPD:** a coluna `cpf` do parlamentar não é gravada nem na Bronze; `txtPassageiro` fica só na Bronze e não passa para Silver e Gold. O CPF entra no md5 de `_hash_lancamento` e é recuperável por força bruta, risco registrado (o dado já é publicado pela Câmara).

### 8. Consulta Otimizada (`docs/explain/`)

`EXPLAIN (ANALYZE, BUFFERS)` antes e depois da consulta de desvio, usando o gasto mensal pré-agregado da migração 004: **~209 ms → ~33 ms** e **21.428 → 206 páginas**, com resultado idêntico.

### 9. Governança e Decisões de Arquitetura (ADRs)

- [**ADR-0005**](https://github.com/taybalau/sbd2-g8-ceap/blob/main/docs/adr/0005-modelagem-dimensional-granularidade-scd-ceap.md): Modelagem dimensional, granularidade e SCD.
- [**ADR-0006**](https://github.com/taybalau/sbd2-g8-ceap/blob/main/docs/adr/0006-orquestracao-falha-controlada-e-backfill.md): Orquestração com Dagster (retry, falha controlada e backfill por partição), em comparação com cron e Airflow.
- [**ADR-0007**](https://github.com/taybalau/sbd2-g8-ceap/blob/main/docs/adr/0007-ferramenta-do-painel-analitico.md): Streamlit versionado em vez de Metabase ou Superset, com medições de memória e tempo.
- [**PIPELINE_E3.md**](https://github.com/taybalau/sbd2-g8-ceap/blob/main/docs/PIPELINE_E3.md): Documento técnico completo da E3.
- [**e3.md**](https://github.com/taybalau/sbd2-g8-ceap/blob/main/docs/e3.md) e [**e3-erros-tratados.md**](https://github.com/taybalau/sbd2-g8-ceap/blob/main/docs/e3-erros-tratados.md): documento de entrega e catálogo dos 29 erros tratados.

---

## 3. Superação das Limitações da Entrega E2

| Ponto de partida | Como foi tratado na Release E3 |
|:--|:--|
| **Fato com chave herdada da E1** (`BIGSERIAL`, que conta linhas carregadas e não identifica o lançamento) | **Grão redefinido** para "lançamento publicado" com chave `id_lancamento` (hash de todos os campos de origem), testada e reconciliada com a Bronze. |
| **Partido do deputado vindo do CSV**, que regrava o valor atual | **SCD tipo 2** a partir do histórico oficial, com teste de regressão sobre o caso 204494 e medição do erro evitado (R$ 33,4 mi). |
| **Pipeline sem orquestração que falhe** | **Dagster** com retry, sensor, schedule e cinco cenários de falha provocados, mais backfill real. |
| **Dados sem camada de consumo** | **Gold** com marts e **painel** que responde à pergunta de gestão, com SLA e freshness declarados. |
| **Qualidade dependente de inspeção manual** | **Testes de domínio** no `dbt build` que barram a publicação e gravam as falhas em `auditoria`. |

---

## 4. Requisitos de Execução

- [Docker](https://docs.docker.com/get-docker/) instalado e em execução
- Docker Compose v2+
- Git
- Máquina com **7 a 8 GB de RAM** (a stack roda Postgres, ingestão E1/E2, dbt, Dagster e painel)
- Porta **8501** livre para o painel (e **3000** para a interface do Dagster, quando exposta)
- Para execução local sem Docker: Python 3.12 e `requirements-e3.txt`

---

## 5. Passo a Passo: Subir e Testar a E3 do Zero

### Passo 1 — Posicionar na tag da release

```
git clone https://github.com/taybalau/sbd2-g8-ceap.git
cd sbd2-g8-ceap

# Posicionar na tag da Entrega E3
git checkout e3
```

### Passo 2 — Subir toda a plataforma com um único comando

```
docker compose up --build
```

O comando sobe a E1/E2 e, depois que o serviço `ingestion` conclui, o pipeline da E3 (`e3-pipeline`), o Dagster e o painel (`e3-painel`). O `demo_falhas.py base` sai com erro se algum job falhar, então uma transformação reprovada não termina "com sucesso".

### Passo 3 — Abrir o painel

Acesse `http://localhost:8501`. O painel sobe pronto, sem configuração manual, e exibe os três blocos, as limitações da análise e o alerta de freshness contra o SLA de 26 h.

### Passo 4 — Reproduzir as evidências de falha e backfill

```
python orquestracao/demo_falhas.py            # retry, fonte_fora, api_fora, dado_sujo e backfill
python orquestracao/backfill_dagster.py       # backfill real de 2023 e 2024 pelo daemon do Dagster
```

Para explorar o grafo, as execuções e o backfill pela interface:

```
.venv/bin/dagster dev -f orquestracao/definitions.py   # http://localhost:3000
```

### Passo 5 — Reproduzir as medições do painel (ADR-0007)

```
bash scripts/medir_painel_metabase.sh                # Metabase vazio: tempo até /api/health e memória
bash scripts/medir_painel_streamlit.sh lakehouse     # painel da E3: tempo até /_stcore/health e memória
```

### Passo 6 — Parar ou limpar o ambiente

```
# Parar os serviços mantendo dados persistidos
docker compose down

# Limpar completamente (banco de dados e volumes)
docker compose down -v
```

---

## 6. Solução de Problemas

| Sintoma | Causa provável | Solução |
|:--|:--|:--|
| `dbt build` reprova `assert_subcota_sem_salto` ou `assert_negativo_somente_em_subcota_de_compensacao` | A Câmara publicou algo novo (ex.: a subcota 996 surgiu num download de 2026-11-03; a queda da subcota 5 em jun/2026) | Investigar a evidência em `auditoria`; se for ruptura ou subcota legítima, registrar em `seeds/ruptura_publicacao.csv` ou `seeds/regra_subcota.csv` |
| Contagens diferentes de 785.929 na Bronze | A Câmara regera os CSVs; o download traz contagens um pouco diferentes por data | Esperado. Conferir apenas a reconciliação Bronze × fato, que deve passar |
| `assert_gold_dentro_do_sla` reprova | Gold construída sobre Bronze mais velha que 26 h | Reexecutar a ingestão do ano corrente e a transformação |
| Falha de escrita ou travamento no `ceap.duckdb` | O DuckDB aceita um único processo escritor | Não executar dois jobs simultâneos (o `dagster.yaml` já limita a uma execução); o painel abre a Gold só para leitura |
| SCD defasado | Modo `CEAP_USAR_CACHE=1` ativo | Desativar o cache; a freshness do histórico avisa após 7 dias e falha após 30 |
| `port is already allocated` na porta 8501 | Outro processo usando a porta do painel | Parar o processo ou alterar o mapeamento da porta no `docker-compose.yml` |

---

## 7. Critérios de Revisão da Arquitetura (ADR-0006 e ADR-0007)

As decisões arquiteturais da E3 serão reabertas caso:

1. A Câmara passe a publicar a CEAP com **partição mensal** (pediria partições mensais no Dagster), ou o pipeline passe a ter **mais de uma fonte** que exija execução em tempo real.
2. O painel receba **mais de 3 pedidos por mês** de visões novas vindos de fora da Squad (hoje: zero), passe a ter **mais de 8 visões** (hoje: 3) ou precise de **acesso restrito por perfil**. Nesses casos, a migração para o Metabase, lendo a mesma Gold, será considerada.

---

## 8. Uso de IA

O uso de IA no desenvolvimento desta entrega está formalizado em [`AI-USAGE.md`](https://github.com/taybalau/sbd2-g8-ceap/blob/main/docs/AI-USAGE.md) e em [Uso de IA](https://taybalau.github.io/sbd2-g8-ceap/ia/). 
