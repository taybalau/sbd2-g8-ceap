# Release Notes — v4.0 (Entrega E4) · Plataforma de Dados da CEAP

**Projeto:** `sbd2-g8-ceap` — Plataforma de Dados da Cota Parlamentar (CEAP), 57ª Legislatura  
**Disciplina:** Sistemas de Banco de Dados 2 (2026/2) — Universidade de Brasília (UnB)  
**Squad:** G8 — Filipe Carvalho, Taynara Vitorino, Gabriel Esteves, Maria Clara Alves, Kaio Macedo, Amanda Gonçalves  
**Tag Git:** `e4`  
**Data de entrega:** 24/11/2026  
**Repositório:** [https://github.com/taybalau/sbd2-g8-ceap](https://github.com/taybalau/sbd2-g8-ceap)

---

## 1. Resumo

A E4 entrega a **disponibilização do dado**: como as métricas da Gold chegam a quem as usa, com um número só para cada métrica, e como o resultado da análise volta para o sistema operacional. Sobre o modelo analítico da E3, a Squad construiu:

1. **Camada semântica de métricas no dbt** (schema `semantico`): 5 views com contrato de esquema e 32 métricas definidas uma vez, com fórmula, unidade e grão versionados. O painel passou a ler só dela e não calcula mais nada.
2. **ETL reverso para a fila do auditor**: o top 15 do desvio é publicado diariamente, por push, no PostgreSQL da E1 (schema `alerta`), onde o auditor registra o que decidiu sobre cada parlamentar.
3. **Análise de LGPD**: inventário de cada dado pessoal por coluna e camada, com base legal, retenção, descarte e o risco de reidentificação do cruzamento CEAP × QSA.
4. **Controle de acesso com privilégio mínimo no PostgreSQL** (migration 005): três papéis, recorte de colunas e view de fornecedores com CPF mascarado.
5. **Catálogo e linhagem**: todas as tabelas da fonte ao consumo, com dono e grão, e o caminho de cada número do painel até a coluna do CSV público.
6. **ADR-0008** e a **conferência dos gatilhos** dos ADRs 0001 a 0007.

A pergunta de gestão continua a mesma da E1:

> *"Quais parlamentares e partidos da 57ª Legislatura (2023–2026) apresentam maior desvio de gastos acima da média mensal da CEAP, e quais categorias e fornecedores concentram esses recursos?"*

Desde 19/11/2026, a "média mensal" da pergunta é medida pela **mediana** do gasto mensal dos deputados da mesma UF, porque poucos gastos extremos distorciam a média ([ADR-0005, seção 9.5](adr/0005-modelagem-dimensional-granularidade-scd-ceap.md#95-mediana-no-lugar-da-média-como-referência-do-desvio)). Todas as métricas da camada semântica já usam a mediana.

---

### Números da Entrega (E4)

Medidos numa subida do zero em 24/11/2026.

| Métrica | Valor na E3 | Valor na E4 | Impacto / Ganho |
|:--|:--:|:--:|:--:|
| **Lançamentos** (Bronze na E3, fato na E4; a reconciliação garante que são iguais) | 785.929 | **802.861** | A Câmara regera os CSVs; a reconciliação Bronze × fato continua obrigatória |
| **Onde a métrica é calculada** | Gold + 4 contas no `painel/app.py` | **Só no schema `semantico`** | Nenhuma soma, média ou agrupamento no painel |
| **Métricas com definição versionada** | N/A | **32** em 5 views | Fórmula, unidade e grão no `_semantic.yml`; catálogo gerado dele |
| **Números do painel conferidos contra a camada** | N/A | **12** (`verificar_consumo_duplo.py`) | Trocar a fonte do painel não mudou nenhum número |
| **Testes no `dbt build`** | 42 | **48** | Inclui `assert_semantico_gasto_consistente` (tolerância de R$ 0,01) e `assert_semantico_desvio_consistente` (R$ 1, pelo arredondamento do rateio) |
| **Leitura do painel (5 consultas)** | N/A | **217 ms** (mediana) · 251 ms (p90) | ~130 ms a mais que tabelas, sem cópia nem defasagem |
| **Consumidores do dado** | 1 (painel) | **2** (painel + auditor) | Os dois mostram os mesmos 15 parlamentares |
| **Publicação da fila do auditor** | N/A | **38 ms** por dia (mediana) | Idempotente: republicar os mesmos dados grava 0 linhas |
| **Destino fora do ar** | N/A | 3 tentativas (2, 4 e 8 s) | Gold com o mesmo hash; fila com as 15 linhas anteriores |
| **Papéis no PostgreSQL** | superusuário `postgres` | **3 papéis de grupo + login de serviço** | 12 asserções permitidas e 34 operações negadas na validação |
| **Catálogo de dados** | N/A | **39 tabelas e views** + 3 fontes públicas | Dono, origem, grão e colunas principais de cada uma |

---

## 2. Novidades da Entrega E4

### 1. Camada Semântica de Métricas (`dbt_ceap/models/semantic/`, issue #6)

- 5 views no schema `semantico` de `lakehouse/ceap.duckdb`: `met_parlamentar`, `met_partido`, `met_categoria_parlamentar`, `met_fornecedor_parlamentar` e `met_contexto`.
- Cada métrica tem nome, descrição, fórmula e unidade no `meta` da coluna; grão, dimensões e consumidores no `meta` do modelo, em `_semantic.yml`. O [catálogo de métricas](e4.md#12-catálogo-de-métricas) é gerado desse arquivo por `scripts/gerar_catalogo_metricas.py`.
- **Contrato de esquema** (`contract: enforced`) em todas as views: coluna que some ou muda de tipo reprova o build antes de o consumidor quebrar.
- Regras de negócio que estavam no painel passaram para a camada: o top 15 (`em_alerta`, var `alerta_top_n`), o corte de 5 deputados por partido (`entra_no_ranking`, var `min_deputados_partido`) e o erro total da sobrescrita dividido por dois (`met_contexto.erro_total_sobrescrita`).
- **Views, e não tabelas:** a camada nunca fica defasada em relação à Gold, e a idade dos dados (`met_contexto.idade_horas`) é calculada na hora da leitura.

### 2. Painel que Só Lê a Camada Semântica (`painel/app.py`)

- O painel lê apenas `semantico.*`. Ele ordena, escolhe o top 15 e formata; nenhuma conta ficou nele.
- `scripts/verificar_consumo_duplo.py` reprova se o código do painel ler a Gold ou a Silver, ou se um dos 12 números exibidos (líder, partido do topo, erro da sobrescrita, categoria, fornecedores…) diferir da camada.
- O painel novo e o da E3, abertos sobre os mesmos dados, produziram textos e tabelas **idênticos**.

### 3. ETL Reverso para a Fila de Auditoria (`etl_reverso/`, issue #7)

- O asset Dagster `alerta/desvio_parlamentar_postgres` roda no fim do job `transformacao`, logo depois do dbt, e publica os parlamentares em alerta em `alerta.desvio_parlamentar` no PostgreSQL da E1.
- **Push diário**, preso à ingestão: agenda das 06:00 → ingestão → sensor → dbt → ETL reverso. Um retrato novo por ingestão nova.
- Tudo é gravado numa transação só. Com o destino fora do ar, o run fica vermelho no Dagster, a fila continua com o último retrato e o job `etl_reverso` republica sem refazer o dbt.
- O asset check `alerta_igual_a_camada_semantica` confere, a cada publicação, se a fila tem os mesmos parlamentares da camada.
- O auditor abre `alerta.vw_fila_auditoria` e registra a decisão em `alerta.tratamento` (`em_analise`, `sem_irregularidade` ou `encaminhado`). A decisão continua valendo nas publicações seguintes.
- As tabelas do schema `alerta` são *insert-only* (ADR-0001): um gatilho recusa `UPDATE` e `DELETE`. A autoria (`registrado_por`) e a hora (`registrado_em`) são gravadas pelo banco, inclusive para o superusuário.
- O ETL reverso conecta com o login de serviço `ceap_etl_reverso`, membro só de `ceap_pipeline`, e não com o superusuário.

### 4. Opção Nula Medida: o CSV Agendado Bastaria?

`etl_reverso/comparar_opcao_nula.py` publicou os mesmos 15 parlamentares pelos dois caminhos (20 repetições). O CSV é mais rápido por milissegundos (26 ms contra 38 ms), mas perde a decisão do auditor na exportação seguinte, não guarda histórico, não protege o registro contra alteração e não separa quem lê de quem edita. A tabela no PostgreSQL se justifica porque o auditor precisa **registrar** o que decidiu, e não só ler a lista.

### 5. Análise de LGPD (`docs/lgpd.md`)

- Inventário por titular (deputados, fornecedores pessoa física, sócios do QSA e passageiros), com coluna, tabela e camada de cada dado pessoal.
- Base legal por dado: art. 7º, IV (estudo por órgão de pesquisa) como base principal, art. 7º, §3º e §7º para o reuso de dado público e o cruzamento, e **art. 11, II, "c" para o partido**, que é dado sensível.
- Política de retenção e seis tarefas de descarte (T1 a T6), incluindo o `VACUUM` do Delta, sem o qual o descarte seria só lógico.
- **Reidentificação por cruzamento:** o cruzamento CEAP × QSA cria dado pessoal novo. Sete riscos (R1 a R7) com o controle de cada um e uma lista fechada de cruzamentos permitidos.
- **Achados que corrigem a E3:** o painel exibe o CPF completo de fornecedores pessoa física (314 na Gold); `sk_fornecedor` é o md5 do CPF; o OLTP guarda `parlamentar.cpf`; `txtPassageiro` está em quatro lugares, e não só na Bronze.

### 6. Controle de Acesso com Privilégio Mínimo (`migrations/005_controle_acesso.sql`, issue #10)

- Papéis de grupo `NOLOGIN`: `ceap_pipeline` (carga), `ceap_auditor` (leitura, inclusive de dados restritos) e `ceap_consulta` (só colunas públicas).
- Para `ceap_consulta` ficam bloqueados `parlamentar.cpf`, `nu_carteira_parlamentar`, `despesa_ceap.passageiro`, a tabela original de fornecedores e a staging. Fornecedores só pela view `v_fornecedor_publico`, que mascara o CPF (`12345678901` → `***.456.789-**`) e preserva o CNPJ.
- A 005 remove concessões excessivas de `PUBLIC` e dos grupos antes de aplicar a matriz; colunas novas não entram automaticamente no acesso de consulta. É reaplicável antes ou depois da 006.
- Validada com PostgreSQL 16.14 e logins reais por TCP: 12 asserções permitidas e 34 operações negadas (`SQLSTATE 42501`).

### 7. Catálogo e Linhagem (`docs/catalogo.md`, `docs/linhagem.md`)

- **Catálogo:** todas as tabelas, do OLTP ao schema `alerta`, com dono (a frente da Squad que escreve nela), descrição, origem, grão e colunas principais. Marcações de contrato de esquema e de dado pessoal.
- **Linhagem:** o caminho de ponta a ponta em 12 trechos, cada um com mecanismo, momento em que roda e como se confere. Dois exemplos seguem um número até a fonte: o desvio acumulado do painel até o CSV, e o partido do gráfico de partidos até a API.
- Registro do que o `dbt docs` cobre (Bronze → `semantico`) e do que fica fora dele (download, OLTP, painel e ETL reverso).

### 8. Governança e Decisões de Arquitetura (ADRs)

- [**ADR-0008**](adr/0008-disponibilizacao-camada-semantica-etl-reverso.md): camada semântica no dbt, leitura direto do warehouse e ETL reverso por push para o PostgreSQL. Compara cópia em CSV, cópia em Parquet, tabelas, views e federação (DuckDB com `ATTACH` do PostgreSQL), com medições.
- [**Conferência dos gatilhos**](adr/README.md) dos ADRs 0001 a 0007, feita no fechamento da E4.
- [**E4_DISPONIBILIZACAO.md**](E4_DISPONIBILIZACAO.md): documento técnico completo da E4.
- [**e4.md**](e4.md), [**lgpd.md**](lgpd.md) e [**controle-de-acesso.md**](controle-de-acesso.md): documentos de entrega.

---

## 3. Superação das Limitações da Entrega E3

| Ponto de partida | Como foi tratado na Release E4 |
|:--|:--|
| **Painel terminava contas por conta própria** (somas por categoria, top 10 de fornecedores, erro da sobrescrita ÷ 2, corte de 5 deputados) | Contas movidas para a **camada semântica**; o painel só lê, ordena e formata, e um script confere 12 números exibidos contra a camada. |
| **Um único consumidor**, sem garantia de que um segundo veria o mesmo número | Testes de consistência entre as views no `dbt build` e o asset check `alerta_igual_a_camada_semantica` na fila do auditor. |
| **Resultado da análise não voltava para nenhum sistema** | **ETL reverso** diário para `alerta.desvio_parlamentar`, com decisões do auditor protegidas e histórico de quem entrou no alerta. |
| **Serviços usavam o superusuário `postgres`** e não havia papéis | **Migration 005** com três papéis e recorte de colunas; o ETL reverso conecta com um login de serviço. |
| **LGPD tratada em dois itens** (CPF do parlamentar e passageiro) | **Análise completa** por dado, com base legal, retenção, descarte e risco de reidentificação; a análise corrigiu o que a E3 afirmava. |
| **Sem catálogo nem linhagem fora do `dbt docs`** | Catálogo de todas as tabelas e linhagem da fonte ao consumo, incluindo os trechos que o dbt não enxerga. |

---

## 4. Requisitos de Execução

- [Docker](https://docs.docker.com/get-docker/) instalado e em execução
- Docker Compose v2+
- Git
- Máquina com **7 a 8 GB de RAM**
- Portas **8501** (painel) e **3000** (Dagster, quando exposta) livres
- Para execução local sem Docker: Python 3.12 e `requirements-e3.txt`

---

## 5. Passo a Passo: Subir e Testar a E4 do Zero

### Passo 1 — Posicionar na tag da release

```
git clone https://github.com/taybalau/sbd2-g8-ceap.git
cd sbd2-g8-ceap

# Posicionar na tag da Entrega E4
git checkout e4
```

### Passo 2 — Subir toda a plataforma

```
docker compose up --build -d
docker compose wait e3-pipeline
```

O serviço `ingestion` aplica as migrations, incluindo a 005 e a 006. Depois, o `e3-pipeline` roda o dbt (incluindo a camada semântica) e publica a fila do auditor conectado como `ceap_etl_reverso`.

### Passo 3 — Abrir o painel e a fila do auditor

- Painel: `http://localhost:8501`, lendo só `semantico.*`.
- Fila do auditor:

```
docker compose exec -T db psql -U postgres -d ceap_oltp < etl_reverso/exemplo_auditor.sql
```

### Passo 4 — Reproduzir a camada semântica e as medições

```
# build, páginas de testes e dicionário, catálogo de métricas e conferência do painel
docker compose run --build --rm --no-deps -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
    -v ./docs:/app/docs -v ./scripts:/app/scripts e3-pipeline bash scripts/gerar_docs_e3.sh

# leitura do warehouse e das cópias -> docs/evidencias/e4_leitura_semantica.json
docker compose run --rm --no-deps -v ./docs:/app/docs -v ./scripts:/app/scripts \
    e3-pipeline python scripts/medir_leitura_semantica.py 20
```

### Passo 5 — Reproduzir o ETL reverso

```
# destino fora do ar -> orquestracao/evidencias/destino_fora.json
docker compose run --rm --no-deps -v ./orquestracao/evidencias:/app/orquestracao/evidencias \
    e3-pipeline python orquestracao/demo_falhas.py destino_fora

# opção nula (CSV agendado) -> docs/evidencias/e4_etl_reverso_opcao_nula.json
docker compose run --rm --no-deps -e DB_USER=postgres -e DB_PASSWORD=postgres \
    -v ./docs:/app/docs -v ./etl_reverso:/app/etl_reverso \
    e3-pipeline bash -c "cd etl_reverso && python comparar_opcao_nula.py 20"
```

### Passo 6 — Validar o controle de acesso

O roteiro em [Controle de acesso](controle-de-acesso.md#demonstrar-acesso-permitido-e-negado) cria dois usuários de teste, confere os acessos permitidos e negados e desfaz tudo com `ROLLBACK`. Ao final aparece `VALIDACAO E4 CONCLUIDA`.

### Passo 7 — Parar ou limpar o ambiente

```
docker compose down       # mantém os dados
docker compose down -v    # apaga banco e volumes
```

---

## 6. Solução de Problemas

| Sintoma | Causa provável | Solução |
|:--|:--|:--|
| `dbt build` reprova `assert_semantico_gasto_consistente` | Uma view da camada passou a somar diferente das outras ou do fato | Conferir a view alterada; as cinco precisam fechar com o fato em R$ 0,01 |
| `verificar_consumo_duplo.py` reprova | O painel voltou a ler a Gold/Silver ou a agregar dados | Mover a conta para a camada semântica e ler a view |
| Run `etl_reverso` vermelho no Dagster | PostgreSQL fora do ar ou credenciais do `ceap_etl_reverso` erradas | Com o banco de volta, rodar o job `etl_reverso`; ele republica sem refazer o dbt |
| `permission denied` ao consultar `alerta.*` como `ceap_consulta` | Esperado: o papel de consulta não acessa a fila | Usar um login membro de `ceap_auditor` |
| Fila do auditor com data antiga | Nenhuma ingestão nova desde a última publicação | Esperado: republicar os mesmos dados grava 0 linhas (ver `alerta.execucao`) |
| `UPDATE` recusado em `alerta.tratamento` | Tabelas *insert-only* | Registrar uma decisão nova; vale a mais recente |

---

## 7. Pendências e Limitações Conhecidas

- **LGPD:** os controles marcados como "alvo" na [análise](lgpd.md#8-lacunas-encontradas-e-plano-de-implementação) ainda não estão no código. O mais urgente é o **CPF completo de fornecedores pessoa física exibido no painel** (L1) e o `sk_fornecedor` reversível (L2). A zona de consumo separada (`ceap_painel.duckdb`), o pseudônimo com HMAC e o job de descarte estão só como esboço no apêndice da análise.
- **Remoção de colunas:** a migration 005 **bloqueia** `parlamentar.cpf` e `despesa_ceap.passageiro` para o papel de consulta, mas não os remove do OLTP (tarefa T5 da análise).
- **ADR-0007:** o gatilho de "acesso restrito por perfil" disparou com a análise de LGPD e ficou em aberto. O registro está na [conferência dos gatilhos](adr/README.md#adr-0007-o-gatilho-de-acesso-por-perfil-disparou).
- **Serviços da E1/E2** (ingestão e CDC) ainda conectam com o superusuário; só o ETL reverso usa login de serviço.
- **`dbt docs`** é gerado localmente; o site ainda não o publica.

---

## 8. Critérios de Revisão da Arquitetura (ADR-0008)

A decisão da E4 será reaberta se qualquer uma destas condições ocorrer:

1. A leitura do painel pela camada semântica passar de **1 s no p90** (hoje 251 ms): materializar as views como tabelas.
2. Surgir **um consumidor fora da rede do DuckDB** (hoje nenhum): publicar uma cópia em Parquet a cada build.
3. O auditor precisar de **frescor menor que diário**: publicar a cada ingestão intradiária ou avaliar federação.
4. O ETL reverso passar a ter **mais de 2 destinos** (hoje 1): trocar o script por uma ferramenta de ETL reverso.
5. A publicação falhar **3 dias seguidos** (hoje 0): rever retry, alerta e a dependência do destino.
6. A camada passar de **50 métricas** (hoje 32): prototipar o dbt Semantic Layer.

---

## 9. Uso de IA

O uso de IA no desenvolvimento desta entrega está formalizado em [`AI-USAGE.md`](https://github.com/taybalau/sbd2-g8-ceap/blob/main/AI-USAGE.md) e em [Uso de IA](https://taybalau.github.io/sbd2-g8-ceap/ia/).