# E3 — Erros tratados

> Documento da Entrega E3. Precisa ser revisado e aprovado por um integrante que não o redigiu.
> Números medidos sobre os CSVs da CEAP baixados em 2026-09-28 e o histórico da API da
> Câmara extraído em 2026-11-03. A Câmara regera os CSVs, então um download em outra data
> traz contagens um pouco diferentes. Detalhes técnicos em [e3.md](e3.md).

## 1. Erros apontados na orientação da disciplina

| # | Erro | Como foi tratado | Onde |
| :-- | :--- | :--- | :--- |
| 1 | **Fato sem grão declarado** | Cada modelo declara o grão na descrição e em `meta.grao`, e um teste `grao_unico` verifica a declaração. O fato principal tem grão "uma linha por lançamento publicado pela Câmara" e chave `id_lancamento` (hash de todos os campos de origem). Colunas que não podem ser somadas estão marcadas como `soma_proibida`. | `dbt_ceap/models/*/_*.yml`, `fct_lancamento_ceap.sql` |
| 2 | **Dupla agregação passando despercebida** | O fato precisa ter a mesma contagem e a mesma soma da Bronze. A Gold precisa somar exatamente o fato. O rateio do desvio por partido precisa fechar com o desvio do mês. | `assert_fato_reconcilia_com_bronze`, `assert_gold_reconcilia_com_fato`, `assert_desvio_alocado_reconcilia` |
| 3 | **Testes que só verificam o que não quebra** | Os testes cobrem a sujeira do domínio: valor negativo fora das subcotas de compensação, salto de série no total e por subcota, mês ausente, subcota que some entre anos, deputado que some no meio do mandato e inconsistência de valores acima de um limite. Os limites foram calibrados com os dados reais. | `dbt_ceap/tests/` |
| 4 | **Dimensão de variação lenta tratada como sobrescrita** | `dim_parlamentar_scd` é SCD tipo 2, construída a partir do histórico oficial de eventos da Câmara. O fato se liga à versão vigente na data do gasto. Há teste de janelas contíguas, teste que recalcula a versão esperada e teste de regressão com um caso real verificado. | `int_parlamentar__versoes.sql`, `dim_parlamentar_scd.sql`, `assert_scd_*` |
| 5 | **Orquestração que nunca falhou** | Dagster com retry e espera crescente, Bronze particionada por ano e transformação disparada só após ingestão bem-sucedida. Quatro falhas foram provocadas de propósito, e um backfill foi executado (abaixo). | `orquestracao/definitions.py`, `orquestracao/demo_falhas.py`, `orquestracao/evidencias/` |
| 6 | **Painel que não responde à pergunta** | Três blocos, um por parte da pergunta da E1 (parlamentares, partidos, categorias e fornecedores). Cada bloco abre com a resposta em uma frase e tem um único gráfico. As limitações da janela de análise aparecem no próprio painel. | `painel/app.py` |

### Cenários executados

| Cenário | Resultado |
| :--- | :--- |
| Falha transitória na leitura do CSV (2 tentativas) | Retry absorveu as falhas; run concluído com sucesso |
| Fonte da Câmara indisponível | Falha após 3 retries; Bronze e Gold inalteradas. A transformação não roda porque o sensor só reage a ingestão bem-sucedida (configurado no Dagster; o script de demonstração não executa sensores) |
| API de histórico indisponível | Falha após 3 retries; dbt não iniciou; SCD e Gold inalterados |
| Dado sujo injetado (combustível negativo) | Teste reprovado; os 4 modelos Gold foram pulados e mantiveram o estado anterior |
| Backfill de 2023 e 2024 | Só essas partições foram reprocessadas; contagem total igual; Gold com hash idêntico |

## 2. Problemas encontrados nos dados da fonte

| # | Problema | Evidência | Tratamento |
| :-- | :--- | :--- | :--- |
| 7 | **O CSV da Câmara sobrescreve o partido** com o partido atual do deputado | ideCadastro 204494: PRD no CSV desde fev/2023; PATRIOTA até 07/02/2024 no histórico oficial. 173.413 lançamentos (22%) divergem. | SCD2 construído da API `/deputados/{id}/historico`. A divergência é medida em teste de aviso. Com a sobrescrita, R$ 33,4 mi iriam para o partido errado. |
| 8 | **`ideDocumento` não é chave** | Vale 0 em 30.357 linhas e se repete em até 9 linhas nos bilhetes SIGEPA | Grão redefinido para "lançamento publicado"; chave por hash de todos os campos |
| 9 | **Ruptura de publicação do SIGEPA** | Subcota 998 (mediana de R$ 3,5 mi/mês) sem débitos a partir de ago/2025; o total mensal caiu só 21% e passou despercebido | Teste de salto por subcota; ruptura registrada em `seeds/ruptura_publicacao.csv`; ranking limitado a fev/2023–jul/2025. Causa não verificada. |
| 10 | **Meses recentes incompletos** (dado atrasado) | jun/2026 com 54% do gasto típico; set/2026 com 7% | Só entram competências com 4 meses de maturação |
| 11 | **Jan/2023 pertence à 56ª Legislatura** | `codLegislatura = 56` em 13.349 lançamentos | Excluído dos rankings da 57ª |
| 12 | **Valores negativos** | Só nas subcotas 40 (auxílio-moradia), 996, 998 e 999 (créditos de passagem aérea). A 996 (missão oficial, 6 créditos) surgiu num download de 2026-11-03 e foi barrada pelo teste de `grupo_despesa` não nulo até ser classificada | Regra registrada em `seeds/regra_subcota.csv`; negativo em qualquer outra subcota, ou subcota sem classificação, reprova o build |
| 13 | **Líquido ≠ documento − glosa** | 974 lançamentos (0,12%), já excluídos os créditos de compensação | Linha sinalizada (`is_valor_inconsistente`), não descartada; teste reprova se passar de 0,3% |
| 14 | **Data de emissão ausente** | Nula em 28.496 lançamentos | O SCD usa `coalesce(data_emissao, competencia)` |
| 15 | **Data de emissão fora do intervalo** | 1 lançamento com emissão em 2002 | Teste de relacionamento com o calendário, severidade aviso |
| 16 | **Lideranças misturadas com deputados** | Linhas sem `ideCadastro` (ex.: LID.GOV-CD) | Versão própria na dimensão; excluídas dos rankings de parlamentares |
| 17 | **Grafias diferentes de fornecedor** | 7.870 documentos (CNPJ ou CPF) com mais de um nome | `dim_fornecedor` agrega por documento (SCD tipo 1 justificado); quantidade de grafias registrada |
| 18 | **Gabinetes sem gasto por 3+ meses** | 136 casos | Teste de aviso; lista guardada para conferência humana |
| 19 | **Teto da cota varia por UF** | Comparar com a média nacional distorce o desvio | Média de referência calculada entre deputados da mesma UF no mesmo mês |

## 3. Erros do próprio pipeline pegos durante o desenvolvimento

| # | Erro | Como foi detectado | Correção |
| :-- | :--- | :--- | :--- |
| 20 | Diferença de 175 lançamentos entre a E1 (785.754) e a Bronze da E3 (785.929) | Comparação com a Bronze | Não é perda na carga da E1 (o INSERT de despesas não usa `DISTINCT`): os CSVs da Câmara mudam conforme a data do download. Em 2023, a E1 tinha 232.747 linhas, a Bronze 232.745 e um download de 2026-11-03 trouxe 232.754. A Bronze grava todas as linhas, e a reconciliação com o fato é obrigatória |
| 21 | Vaivém falso de partido (A→B→A) no mês de transição | `assert_scd_janelas_contiguas` | Ordenação dentro do mês por continuidade (depois substituída pelo histórico oficial) |
| 22 | Desvio não rateado em meses com gasto líquido zero | `assert_desvio_alocado_reconcilia` | Rateio igual entre versões quando o gasto do mês é zero |
| 23 | Linha duplicada no ranking por variação de nome entre versões | `grao_unico` do `mart_desvio_parlamentar` | Nome e UF passam a vir da versão mais recente |
| 24 | Gold não determinística entre execuções idênticas | Comparação de hash no backfill | Média e desvio em `DECIMAL` no lugar de ponto flutuante |
| 25 | Partidos da 56ª (PSL, DEM) na trajetória partidária da 57ª | Revisão manual do resultado | Trajetória restrita às versões vigentes a partir de 01/02/2023 |
| 26 | `docker compose` terminava "com sucesso" mesmo com a transformação reprovada, e a E3 não esperava o download dos CSVs | Teste de subida do zero em cópia limpa do repositório | `demo_falhas.py base` sai com erro se algum job falhar; `e3-pipeline` espera o serviço `ingestion` concluir |

## 4. LGPD

| # | Ponto | Tratamento |
| :-- | :--- | :--- |
| 27 | CPF do parlamentar no CSV | A coluna não é gravada, nem na Bronze. Ela entra no md5 de `_hash_lancamento`, e com os demais campos da Bronze o CPF pode ser recuperado por força bruta (~10⁹ valores possíveis). O dado já é publicado pela Câmara |
| 28 | Nome de passageiro (assessores, pessoas físicas) | Mantido só na Bronze (cópia do dado público); não passa para Silver e Gold |
