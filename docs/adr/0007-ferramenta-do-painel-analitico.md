# 0007 — Ferramenta do painel analítico: Streamlit versionado em vez de Metabase ou Superset

- **Status:** proposto (aguarda revisão de um integrante que não o redigiu)
- **Data:** 2026-11-03
- **Decisores:** Squad G8

## 1. Contexto e caracterização da carga

O painel da E3 tem um único objetivo: responder à pergunta de gestão da E1 (*quais parlamentares
e partidos apresentam maior desvio acima da média mensal da CEAP, e quais categorias e
fornecedores concentram esses recursos*). Ele lê só a camada Gold, num arquivo DuckDB gerado
pelo dbt:

| Tabela Gold | Linhas |
| :--- | ---: |
| `mart_desvio_parlamentar` | 622 |
| `mart_desvio_partido` | 26 |
| `mart_concentracao_parlamentar` | 86.485 |
| `fct_gasto_mensal_parlamentar` | 23.458 |
| `mart_freshness_gold` | 4 |

O arquivo `ceap.duckdb` tem 128 MB. Há três visões fixas (parlamentares, partidos e
categorias/fornecedores de um parlamentar escolhido), sem consultas livres. Os leitores são a
Squad e a monitoria, não analistas que montam relatórios próprios.

A stack da disciplina lista **Metabase** e **Apache Superset** para o painel. Fugir da lista
exige justificativa, e este ADR é essa justificativa.

## 2. Restrições não funcionais

1. **Subir do zero com um comando, com o mesmo resultado** (30% da nota): o painel tem de
   aparecer pronto depois do `docker compose up`, sem cliques de configuração.
2. **Versionado no git:** mudar um gráfico tem de ser um diff revisável no PR.
3. **Uma máquina de 7 a 8 GB de RAM** roda Postgres, a ingestão da E1/E2, o dbt, o Dagster e o painel.
4. **Não travar o pipeline:** o DuckDB aceita um único processo escritor. O painel não pode
   segurar o arquivo enquanto o dbt reconstrói a Gold.

## 3. Candidatos

| Critério | Opção nula: consultas SQL salvas | Metabase | Apache Superset | **Streamlit (escolhido)** |
| :--- | :--- | :--- | :--- | :--- |
| Painel pronto depois do `docker compose up` | não há painel | só com script na API para criar perguntas e dashboard | só com `superset db upgrade`, criação de admin, `superset init` e importação do dashboard | **sim**: o painel é o código |
| Definição versionada no git | sim (SQL) | não: fica no banco de aplicação do Metabase | parcial: exportação em ZIP/YAML | **sim**: `painel/app.py` (202 linhas) |
| Leitura do DuckDB | — | driver da comunidade (`.jar` da MotherDuck), fora da distribuição oficial | via `duckdb-engine` (SQLAlchemy) | **nativa** (`duckdb.connect(read_only=True)`) |
| Imagem e memória | — | 1.218 MB · ~961 MB em repouso | não medido (precisa de um banco de metadados e, em produção, Redis) | **mesma imagem do pipeline** · 56 MB em repouso · 259 MB com o painel carregado |
| Tempo até responder | — | 40 s | não medido | 6 s |
| Exploração livre por usuário de negócio | não | **sim** | **sim** | não |
| Na stack oficial da disciplina | — | **sim** | **sim** | não |

O Superset não foi medido. A documentação oficial exige os passos de inicialização listados na
tabela, e ele não tem nenhuma vantagem sobre o Metabase que interesse a esta pergunta.

## 4. Medição

Os números da tabela foram medidos em 2026-11-03, na máquina da Squad (7,6 GB de RAM), com a
Gold real da E3. Para repetir:

```bash
bash scripts/medir_painel_metabase.sh                # Metabase vazio: tempo até /api/health e memória
bash scripts/medir_painel_streamlit.sh lakehouse     # painel da E3: tempo até /_stcore/health e memória
```

A memória do Metabase é de uma instância **vazia**, sem driver DuckDB, sem perguntas e sem
dashboard. A memória do Streamlit com o painel carregado (259 MB) é o pico do processo depois de
ler as cinco tabelas e montar os três gráficos.

## 5. Decisão e consequências

Mantemos o painel em **Streamlit** (`painel/app.py`), servido pelo container `e3-painel` na porta
8501, lendo a Gold em modo somente leitura.

**O que se ganha**
- O painel sobe pronto e igual em qualquer máquina, porque o código é o painel. Não existe um
  passo manual que possa ser esquecido.
- Cada mudança de gráfico passa por revisão no PR, como o resto do pipeline.
- Cerca de 700 MB a menos de RAM do que o Metabase em repouso, numa máquina que já roda o resto
  da plataforma.
- O painel mostra as limitações da análise junto com a resposta: janela comparável, rupturas de
  publicação e freshness contra o SLA (alerta quando passa de 26 h).

**O que se perde**
- **Ninguém fora da Squad monta uma consulta nova sem programar.** No Metabase, um usuário de
  negócio criaria uma pergunta em minutos.
- **Não há controle de acesso** por usuário nem compartilhamento de visões salvas.
- **Fica fora da stack oficial,** o que depende de esta justificativa ser aceita.
- **Cada gráfico novo é código Python,** com plotly e streamlit como dependências a manter.

**O que fica irreversível**
- Nada de forma relevante. A Gold é uma tabela DuckDB comum, então um Metabase ou um Superset
  pode ser ligado a ela depois sem mudar o pipeline. O que se perde numa migração são as
  ~200 linhas do painel, que teriam de ser refeitas como perguntas na ferramenta.

## 6. Gatilho de revisão

Migrar para o Metabase, lendo a Gold, se **qualquer** uma destas condições ocorrer:

- **mais de 3 pedidos por mês de visões novas** vindos de pessoas fora da Squad (hoje: zero);
- o painel passar a ter **mais de 8 visões**, o que tornaria o código mais caro de manter do que
  a configuração (hoje: 3);
- surgir a necessidade de **acesso restrito por perfil**, por exemplo dados não públicos de
  fornecedores.
