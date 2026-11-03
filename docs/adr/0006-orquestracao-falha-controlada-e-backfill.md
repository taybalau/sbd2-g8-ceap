# 0006 — Orquestração com Dagster: retry, falha controlada e backfill por partição

- **Status:** proposto (aguarda revisão da squad)
- **Data:** 2026-11-03
- **Decisores:** Squad G8

## 1. Contexto

Na E3 o pipeline tem duas fontes externas que **podem cair** e uma cadeia de transformações
que **não pode publicar lixo**:

1. CSVs anuais da CEAP (Câmara). O arquivo do ano corrente é regerado continuamente.
2. API `GET /deputados/{id}/historico` (Câmara), fonte do SCD tipo 2. Precisamos dela porque
   o `sgPartido` do CSV é regravado com o partido atual (ver ADR-0005, revisão de 2026-11-03).
3. dbt (Silver/Gold) com testes de domínio que devem barrar a publicação de dado errado.

Um grafo que nunca falhou é decorativo. O requisito é **mostrar** o que acontece quando uma
dependência cai, que o retry funciona e que o backfill reprocessa só o que precisa.

## 2. Alternativas

| Critério | Cron + scripts (opção nula) | Airflow | **Dagster + dagster-dbt (escolhida)** |
| :--- | :--- | :--- | :--- |
| Unidade do grafo | tarefa | tarefa | **asset (tabela)** |
| Testes do dbt no grafo | não | via operador, como tarefa opaca | **cada teste vira asset check** |
| Backfill por ano | laço manual | por data de execução | **partição estática por ano** |
| Linhagem Bronze → Gold | inexistente | só entre tarefas | **um grafo só (sources do dbt = assets Bronze)** |
| Peso para rodar local | mínimo | scheduler + webserver + banco | `dagster dev` num processo |

Airflow foi descartado porque o particionamento dele é por data de execução, enquanto o
nosso dado é particionado por **ano do arquivo** da Câmara. O cron foi descartado porque não
tem como impedir que a transformação rode sobre uma ingestão que falhou.

## 3. Decisão

- `bronze/ceap_lancamento`: particionado por ano (`2023`…`2026`), `RetryPolicy(max_retries=3,
  backoff=EXPONENTIAL)`. Reprocessar um ano substitui só aquela partição Delta (`replaceWhere`).
- `bronze/camara_deputado_historico`: retry 3x. Antes de abrir ~860 requisições, faz uma
  sondagem que falha rápido, e deixa o backoff com o orquestrador. Se mais de 1% dos deputados
  ficar sem histórico, **não grava nada** e o snapshot anterior continua valendo.
- Modelos dbt carregados como assets e executados com `dbt build`: teste reprovado pula os
  modelos a jusante, e a Gold anterior permanece.
- Dois jobs: `ingestao_ceap` (particionado) e `transformacao`. O sensor
  `transforma_apos_ingestao` só dispara a transformação após ingestão **bem-sucedida**.
- Agenda diária reingere só o ano corrente. Os anos fechados são reprocessados por backfill sob
  demanda.

## 4. Evidência

`orquestracao/demo_falhas.py` derruba cada dependência de propósito. Os resultados ficam em
`orquestracao/evidencias/*.json` e são resumidos em `docs/e3.md`, seção "Orquestração que falha".

## 5. Consequências

- Ganho: falha de fonte não apaga nem corrompe a Gold, e isso foi demonstrado, não só afirmado.
- Ganho: o backfill de um ano não reescreve os demais.
- Custo: mais uma dependência (Dagster) e dois jobs em vez de um.
- Risco aceito: no modo `CEAP_USAR_CACHE=1` o SCD pode ficar defasado. O modo é explícito, e
  a `freshness` da source no dbt avisa após 7 dias e falha após 30.

## 6. Gatilho de revisão

Revisar se a Câmara passar a publicar a CEAP com partição mensal, o que pediria partições
mensais, ou se o pipeline passar a ter mais de uma fonte que precise de execução em tempo real.
