# Testes de dados

> Página gerada por `scripts/gerar_doc_testes.py` a partir do `manifest.json` e do
> `run_results.json` do dbt. Não edite à mão: rode o script depois de um `dbt build`.

**Última execução:** 17/11/2026 13:25 UTC, numa subida do zero (`docker compose up --build`) com os CSVs da Câmara baixados no mesmo dia.

| Resultado | Testes |
| :--- | ---: |
| ⚠️ aviso | 3 |
| ✅ passou | 39 |
| **Total** | **42** |

## Cobertura do checklist da E3

| Categoria | Testes | O que garante |
| :--- | ---: | :--- |
| [Esquema](#esquema) | 8 | colunas obrigatórias preenchidas; o contrato das tabelas de consumo (abaixo) fixa colunas e tipos |
| [Volume](#volume) | 5 | nenhuma linha perdida ou duplicada entre Bronze, fato e Gold; nenhum ano ou mês faltando |
| [Unicidade](#unicidade) | 14 | o grão declarado de cada modelo vale (uma linha por chave) |
| [Integridade referencial](#integridade-referencial) | 4 | toda chave do fato aponta para uma linha existente da dimensão |
| [Distribuição](#distribuição) | 3 | o total e cada subcota não saltam fora da faixa calibrada com os dados reais (erro silencioso) |
| [Domínio (dado sujo)](#domínio-dado-sujo) | 4 | valor negativo onde não cabe, subcota ou deputado que some, sobrescrita da fonte |
| [SCD tipo 2](#scd-tipo-2) | 3 | o partido usado é o da data do gasto, sem buracos nem sobreposição de versões |
| [Freshness e SLA](#freshness-e-sla) | 1 | a Gold não é publicada sobre uma Bronze mais velha que o SLA de 26 h |

### Contratos de esquema

Estas tabelas têm `contract: enforced`: o `dbt build` reprova se uma coluna sumir, mudar
de nome ou mudar de tipo em relação ao declarado. As colunas e os tipos estão no
[dicionário de dados](dicionario-de-dados.md).

| Tabela | Colunas sob contrato |
| :--- | ---: |
| `gold.fct_gasto_mensal_parlamentar` | 16 |
| `silver.fct_lancamento_ceap` | 30 |
| `gold.mart_concentracao_parlamentar` | 14 |
| `gold.mart_desvio_parlamentar` | 16 |
| `gold.mart_desvio_partido` | 9 |
| `gold.mart_freshness_gold` | 9 |

Contrato violado de propósito em `mart_desvio_parlamentar` (2026-11-17): primeiro declarando
um tipo errado, depois tirando uma coluna do SQL. Nos dois casos a tabela não é criada:

```text
This model has an enforced contract that failed.
| column_name      | definition_type | contract_type | mismatch_reason       |
| posicao_ranking  | BIGINT          | VARCHAR       | data type mismatch    |
| hhi_fornecedores |                 | DOUBLE        | missing in definition |
```

## Esquema

| Teste | Tabela | O que verifica | Severidade | Última execução |
| :--- | :--- | :--- | :--- | :--- |
| `not_null` | `bronze.ceap_lancamento` | `_hash_lancamento` nunca é nulo | erro | ✅ passou |
| `not_null` | `dim_categoria_despesa` | `grupo_despesa` nunca é nulo | erro | ✅ passou |
| `not_null` | `dim_parlamentar_scd` | `sk_parlamentar` nunca é nulo | erro | ✅ passou |
| `not_null` | `fct_lancamento_ceap` | `id_lancamento` nunca é nulo | erro | ✅ passou |
| `not_null` | `fct_lancamento_ceap` | `sk_parlamentar` nunca é nulo | erro | ✅ passou |
| `not_null` | `fct_lancamento_ceap` | `sk_fornecedor` nunca é nulo | erro | ✅ passou |
| `not_null` | `regra_subcota` | `num_subcota` nunca é nulo | erro | ✅ passou |
| `not_null` | `ruptura_publicacao` | `num_subcota` nunca é nulo | erro | ✅ passou |

## Volume

| Teste | Tabela | O que verifica | Severidade | Última execução |
| :--- | :--- | :--- | :--- | :--- |
| `assert_fato_reconcilia_com_bronze` (singular) | `bronze.ceap_lancamento`, `fct_lancamento_ceap` | o fato tem a mesma contagem e a mesma soma da Bronze (nenhuma junção duplicou ou perdeu linha) | erro | ✅ passou |
| `assert_todos_os_anos_presentes` (singular) | `bronze.ceap_lancamento`, `fct_lancamento_ceap` | cada ano esperado (2023 a 2026) está na Bronze e no fato | erro | ✅ passou |
| `assert_desvio_alocado_reconcilia` (singular) | `fct_gasto_mensal_parlamentar` | o desvio rateado entre as versões de um mês de troca de partido soma o desvio do mês | erro | ✅ passou |
| `assert_gold_reconcilia_com_fato` (singular) | `fct_gasto_mensal_parlamentar`, `fct_lancamento_ceap` | o fato mensal soma exatamente o fato no mesmo recorte (57ª, sem lideranças) | erro | ✅ passou |
| `assert_serie_mensal_sem_lacuna` (singular) | `fct_lancamento_ceap` | nenhum mês sem lançamentos entre a primeira e a última competência | erro | ✅ passou |

## Unicidade

| Teste | Tabela | O que verifica | Severidade | Última execução |
| :--- | :--- | :--- | :--- | :--- |
| `unique` | `bronze.ceap_lancamento` | `_hash_lancamento` não se repete | erro | ✅ passou |
| `grao_unico` | `dim_calendario` | uma linha por (`data`) | erro | ✅ passou |
| `grao_unico` | `dim_categoria_despesa` | uma linha por (`num_subcota`) | erro | ✅ passou |
| `grao_unico` | `dim_fornecedor` | uma linha por (`sk_fornecedor`) | erro | ✅ passou |
| `grao_unico` | `dim_parlamentar_scd` | uma linha por (`sk_parlamentar`) | erro | ✅ passou |
| `grao_unico` | `dim_parlamentar_scd` | uma linha por (`id_deputado`, `numero_versao`) | erro | ✅ passou |
| `grao_unico` | `dim_parlamentar_scd` | uma linha por (`id_cadastro_camara`, `numero_versao`) | erro | ✅ passou |
| `grao_unico` | `fct_gasto_mensal_parlamentar` | uma linha por (`sk_parlamentar`, `competencia`) | erro | ✅ passou |
| `grao_unico` | `fct_lancamento_ceap` | uma linha por (`id_lancamento`) | erro | ✅ passou |
| `grao_unico` | `mart_concentracao_parlamentar` | uma linha por (`id_deputado`, `num_subcota`, `sk_fornecedor`) | erro | ✅ passou |
| `grao_unico` | `mart_desvio_parlamentar` | uma linha por (`id_deputado`) | erro | ✅ passou |
| `grao_unico` | `mart_desvio_partido` | uma linha por (`sigla_partido`) | erro | ✅ passou |
| `grao_unico` | `mart_freshness_gold` | uma linha por (`tabela_consumo`) | erro | ✅ passou |
| `unique` | `regra_subcota` | `num_subcota` não se repete | erro | ✅ passou |

## Integridade referencial

| Teste | Tabela | O que verifica | Severidade | Última execução |
| :--- | :--- | :--- | :--- | :--- |
| `relationships` | `fct_lancamento_ceap` | todo `sk_parlamentar` existe em `dim_parlamentar_scd.sk_parlamentar` | erro | ✅ passou |
| `relationships` | `fct_lancamento_ceap` | todo `sk_fornecedor` existe em `dim_fornecedor.sk_fornecedor` | erro | ✅ passou |
| `relationships` | `fct_lancamento_ceap` | todo `num_subcota` existe em `dim_categoria_despesa.num_subcota` | erro | ✅ passou |
| `relationships` | `fct_lancamento_ceap` | todo `data_emissao` existe em `dim_calendario.data` | aviso | ⚠️ aviso (1 linha) |

## Distribuição

| Teste | Tabela | O que verifica | Severidade | Última execução |
| :--- | :--- | :--- | :--- | :--- |
| `assert_valor_inconsistente_sob_controle` (singular) | `fct_lancamento_ceap` | lançamentos com líquido ≠ documento − glosa ficam abaixo de 0,3% do total | erro | ✅ passou |
| `assert_serie_mensal_sem_salto` (singular) | `fct_lancamento_ceap`, `ruptura_publicacao` | o gasto total e o nº de deputados de cada mês fechado ficam entre 0,60 e 1,70 da mediana dos 6 meses anteriores | erro | ✅ passou |
| `assert_subcota_sem_salto` (singular) | `fct_lancamento_ceap`, `ruptura_publicacao` | nenhuma subcota relevante cai abaixo de 25% da sua mediana dos 6 meses anteriores | erro | ✅ passou |

## Domínio (dado sujo)

| Teste | Tabela | O que verifica | Severidade | Última execução |
| :--- | :--- | :--- | :--- | :--- |
| `assert_negativo_somente_em_subcota_de_compensacao` (singular) | `dim_categoria_despesa`, `fct_lancamento_ceap` | valor negativo só nas subcotas de compensação (40, 996, 998, 999) | erro | ✅ passou |
| `assert_divergencia_csv_vs_historico` (singular) | `dim_parlamentar_scd`, `fct_lancamento_ceap` | mede quantos lançamentos têm no CSV um partido diferente do vigente na data do gasto | aviso | ⚠️ aviso (173475 linhas) |
| `assert_deputado_ativo_nao_some_no_meio` (singular) | `fct_lancamento_ceap` | deputado sem gasto por 3+ meses no meio do mandato (lista para conferência) | aviso | ⚠️ aviso (143 linhas) |
| `assert_subcota_nao_some_entre_anos` (singular) | `fct_lancamento_ceap`, `ruptura_publicacao` | subcota com 100+ lançamentos num ano não desaparece no ano seguinte | erro | ✅ passou |

## SCD tipo 2

| Teste | Tabela | O que verifica | Severidade | Última execução |
| :--- | :--- | :--- | :--- | :--- |
| `assert_scd_janelas_contiguas` (singular) | `dim_parlamentar_scd` | as versões de cada deputado não se sobrepõem, não têm buraco e há uma única versão atual | erro | ✅ passou |
| `assert_scd_caso_conhecido_204494` (singular) | `dim_parlamentar_scd`, `fct_lancamento_ceap` | regressão com caso real: o deputado 204494 é PATRIOTA até 07/02/2024 e PRD depois | erro | ✅ passou |
| `assert_scd_preserva_partido_da_epoca` (singular) | `dim_parlamentar_scd`, `fct_lancamento_ceap` | cada lançamento aponta para a versão vigente na data do gasto, e não para a atual | erro | ✅ passou |

## Freshness e SLA

| Teste | Tabela | O que verifica | Severidade | Última execução |
| :--- | :--- | :--- | :--- | :--- |
| `assert_gold_dentro_do_sla` (singular) | `mart_freshness_gold` | a Gold foi construída até 26 h depois da ingestão mais recente | erro | ✅ passou |

## Freshness das fontes (`dbt source freshness`)

| Fonte | Carregada em (UTC) | Idade | Limites | Resultado |
| :--- | :--- | ---: | :--- | :--- |
| `bronze.camara_deputado_historico` | 2026-11-17 13:23 | 0.0 h | aviso 7 dias · erro 30 dias | ✅ passou |
| `bronze.ceap_lancamento` | 2026-11-17 13:15 | 0.0 h | aviso 26 h · erro 48 h | ✅ passou |

## Outros testes da plataforma

Além dos testes de dados do dbt, a plataforma tem testes de comportamento, com evidência versionada:

| Teste | O que verifica | Onde |
| :--- | :--- | :--- |
| Falha transitória (`retry`) | 2 leituras do CSV falham e o retry absorve | `orquestracao/evidencias/retry.json` |
| Fonte fora (`fonte_fora`) | CSV indisponível: 3 retries, Bronze e Gold intactas | `orquestracao/evidencias/fonte_fora.json` |
| API fora (`api_fora`) | histórico indisponível: o dbt nem inicia | `orquestracao/evidencias/api_fora.json` |
| Dado sujo (`dado_sujo`) | negativo injetado: teste reprova e a Gold não é publicada | `orquestracao/evidencias/dado_sujo.json` |
| Backfill (`backfill`, `backfill_dagster`) | reprocessar 2023 e 2024 não muda a Gold (hash idêntico) | `orquestracao/evidencias/backfill*.json` |
| SLA violado de propósito | `--vars '{sla_horas_gold: 0}'` reprova `assert_gold_dentro_do_sla` | [E3, seção 7](e3.md#7-freshness-e-sla) |
| Consulta otimizada | antes e depois devolvem o mesmo resultado | `scripts/explain_desvio.sh`, [EXPLAIN](explain/README.md) |
| Aceite da E2 | idempotência do lote, CDC, dado atrasado, deduplicação, UBO | `scripts/test_e2_pipeline.py`, [Lakehouse e CDC](lakehouse.md#testes-de-aceite) |

## Como rodar

Todos os testes de dados rodam sozinhos no `docker compose up --build` (container `e3-pipeline`).
Para rodar de novo com a plataforma no ar e regerar esta página e o dicionário de dados:

```bash
docker compose run --build --rm --no-deps -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
    -v ./docs:/app/docs -v ./scripts:/app/scripts e3-pipeline bash scripts/gerar_docs_e3.sh
```

As linhas reprovadas de cada teste ficam gravadas no schema `auditoria` do `ceap.duckdb`.
