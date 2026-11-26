# Catálogo de dados

Este catálogo lista **todas as tabelas da plataforma**, da fonte pública ao consumo: o banco
transacional (OLTP), o lakehouse da E2, as camadas Bronze, Silver e Gold da E3, a camada semântica
da E4 e o destino do ETL reverso. Para cada tabela há dono, descrição, origem, grão e as colunas
principais.

- O caminho que o dado percorre entre essas tabelas, com exemplos de coluna seguida de ponta a
  ponta, está em [Linhagem](linhagem.md).
- O tipo e a descrição de **todas** as colunas da Bronze, Silver, Gold e Semântica estão no
  [Dicionário de dados](dicionario-de-dados.md), gerado do dbt. Aqui ficam só as colunas principais,
  com a coluna de onde cada uma vem.
- O OLTP está detalhado em [Modelo de dados](modelo-de-dados.md), e as métricas da camada semântica
  (fórmula e unidade) no [catálogo de métricas da E4](e4.md#12-catálogo-de-métricas).

**Legenda:** 🔒 contrato de esquema (`contract: enforced`) · 👤 dado pessoal (LGPD, ver
[análise de LGPD](lgpd.md)) · ⚠️ cuidado de uso.

## Visão geral

| Camada | Onde fica | Tabelas | Dono | Alimenta o painel? |
| :--- | :--- | ---: | :--- | :---: |
| [Fontes públicas](#fontes-públicas) | Portal e API da Câmara; base societária | 3 | — | — |
| [OLTP](#oltp-postgresql-schema-public) | PostgreSQL `ceap_oltp`, schema `public` | 10 | Ingestão OLTP | não |
| [Lakehouse E2](#lakehouse-e2-delta-lake) | `lakehouse/delta/` (Delta) | 3 | Lakehouse E2 / Enriquecimento | não |
| [Bronze](#bronze) | `lakehouse/bronze/` (Delta) | 2 | Bronze e orquestração | **sim** |
| [Silver](#silver) | `lakehouse/ceap.duckdb`, schema `silver` | 10 | Modelagem dbt | **sim** |
| [Gold](#gold) | `lakehouse/ceap.duckdb`, schema `gold` | 5 | Modelagem dbt | **sim** |
| [Semântica](#semântica) | `lakehouse/ceap.duckdb`, schemas `semantico` e `auditoria` | 9 | Camada semântica | **sim** |
| [Destino do ETL reverso](#destino-do-etl-reverso-postgresql-schema-alerta) | PostgreSQL `ceap_oltp`, schema `alerta` | 4 | ETL reverso / Auditor | — (é consumo) |

!!! warning "O OLTP não fica no caminho do painel"
    Desde o [ADR-0004](adr/0004-avaliacao-etl-relacional-postgres-vs-lakehouse-direto.md) (E3), a
    Bronze lê o CSV da Câmara **direto do cache** `base-dados/`, sem passar pelo PostgreSQL. O OLTP e
    o lakehouse da E2 continuam no ar, carregados do **mesmo arquivo**, mas são um ramo paralelo. O
    PostgreSQL volta a aparecer no fim do fluxo, como **destino** do ETL reverso (schema `alerta`).
    O desenho completo está em [Linhagem](linhagem.md#visão-de-ponta-a-ponta).

## Donos

O **dono** de uma tabela é a frente da Squad G8 que escreve nela e responde por mudanças de
esquema, qualidade e significado. O catálogo registra a frente, e não o nome de quem responde por
ela, para não ficar desatualizado quando a escala da Squad muda; quem responde por cada frente está
na planilha de acompanhamento da Squad.

| Frente (dono) | Responde por | Código que escreve |
| :--- | :--- | :--- |
| **Ingestão OLTP** (E1) | schema `public` do PostgreSQL | `scripts/download_data.py`, `scripts/ingest_ceap.py`, `migrations/001` a `004` |
| **Lakehouse E2** | `lakehouse/delta/despesa_ceap` | `scripts/batch_ingest_lakehouse.py`, `scripts/cdc_stream_consumer.py`, `migrations/003` |
| **Enriquecimento societário** (E2) | `lakehouse/delta/dim_fornecedor_cadastral`, `dim_quadro_societario_ubo` | `scripts/enrich_receita_socios.py` |
| **Bronze e orquestração** (E3) | `lakehouse/bronze/*` | `ingestao/bronze.py`, `ingestao/bronze_historico.py`, `orquestracao/definitions.py` |
| **Modelagem dbt** (E3) | schemas `silver` e `gold`, seeds | `dbt_ceap/models/{staging,intermediate,core,gestao}/`, `dbt_ceap/seeds/` |
| **Camada semântica** (E4, issue #6) | schema `semantico` | `dbt_ceap/models/semantic/` |
| **ETL reverso** (E4, issue #7) | `alerta.desvio_parlamentar`, `alerta.execucao`, `alerta.vw_fila_auditoria` | `etl_reverso/publicar_alertas.py`, `migrations/006_etl_reverso.sql` |
| **Auditor** (role `ceap_auditor`) | conteúdo de `alerta.tratamento` (as decisões) | — (registro manual, via SQL) |

## Fontes públicas

| Fonte | Publicador | Acesso | Formato | Lida por | Atualização |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CEAP — CSV anual** | Câmara dos Deputados | `http://www.camara.leg.br/cotas/Ano-AAAA.csv.zip` | CSV `;`, 32 colunas, um arquivo por ano (2023 a 2026) | `scripts/download_data.py`, que grava em `base-dados/Ano-AAAA.csv` | A Câmara regrava o arquivo do ano; a Squad reingere o ano corrente diariamente às 06:00 (Dagster) |
| **Histórico de deputados — API** | Câmara dos Deputados | `GET https://dadosabertos.camara.leg.br/api/v2/deputados/{id}/historico` | JSON, um evento por item | `ingestao/bronze_historico.py` (~860 chamadas) | Snapshot completo a cada transformação; cache em `lakehouse/_cache/historico/` |
| **QSA da Receita Federal** ⚠️ | Receita Federal (Dados Abertos do CNPJ) | — | — | `scripts/enrich_receita_socios.py` | — |

!!! note "O QSA é uma base de demonstração"
    O enriquecimento societário da E2 **não lê** os Dados Abertos do CNPJ: usa 12 empresas e 12
    relações societárias definidas no próprio código (ver
    [Enriquecimento societário](enriquecimento.md#base-de-dados-usada) e o
    [ADR-0003](adr/0003-resolucao-grafo-societario-beneficiario-final.md)). As tabelas que ele gera
    não entram na Silver, na Gold, no painel nem no ETL reverso.

## OLTP (PostgreSQL, schema `public`)

Banco `ceap_oltp`, criado pelas migrações `001` a `004`. Carregado de `base-dados/Ano-AAAA.csv` por
`scripts/ingest_ceap.py`: `COPY` para a staging e `INSERT ... SELECT` para as tabelas normalizadas.
Detalhes em [Modelo de dados](modelo-de-dados.md) e [Carga no OLTP](pipeline.md).

### public.stg_ceap_raw

| | |
| :--- | :--- |
| **Dono** | Ingestão OLTP |
| **Descrição** | Staging `UNLOGGED` com as 32 colunas do CSV, todas `TEXT`. Esvaziada no início e no fim de cada ano carregado. |
| **Origem** | `base-dados/Ano-AAAA.csv`, via `COPY` (`scripts/ingest_ceap.py`) |
| **Grão** | uma linha do CSV (só durante a carga) |
| **Colunas principais** | as 32 colunas do CSV com o nome original (`nuDeputadoId`, `vlrLiquido`, `txtCNPJCPF`…), incluindo `cpf` 👤 e `txtPassageiro` 👤 |

### public.parlamentar

| | |
| :--- | :--- |
| **Dono** | Ingestão OLTP |
| **Descrição** | Deputados e contas de liderança partidária. |
| **Origem** | `stg_ceap_raw`, uma linha por `nuDeputadoId` |
| **Grão** | um `id_deputado` |

| Coluna | Significado | Vem de |
| :--- | :--- | :--- |
| `id_deputado` (PK) | Identificador do deputado nos arquivos da CEAP | CSV `nuDeputadoId` |
| `nome_parlamentar` | Nome parlamentar ou nome da liderança | CSV `txNomeParlamentar` |
| `ide_cadastro` | Id do deputado na API da Câmara (nulo em lideranças) | CSV `ideCadastro` |
| `cpf` 👤 | CPF do deputado. Sem uso na pergunta de gestão; remoção planejada na migração 005 ([LGPD](lgpd.md)) | CSV `cpf` |

### public.mandato_parlamentar

| | |
| :--- | :--- |
| **Dono** | Ingestão OLTP |
| **Descrição** | Combinações de partido, UF e legislatura vistas no CSV para cada deputado. |
| **Origem** | `stg_ceap_raw` (`SELECT DISTINCT`) |
| **Grão** | `(id_deputado, sigla_partido, sigla_uf, codigo_legislatura)` |
| **Colunas principais** | `sigla_partido` ← CSV `sgPartido`; `sigla_uf` ← `sgUF`; `codigo_legislatura` ← `codLegislatura` |
| ⚠️ | O `sgPartido` do CSV é regravado pela Câmara com o partido **atual** do deputado. Esta tabela não guarda o partido da época; para isso use `silver.dim_parlamentar_scd`. |

### public.fornecedor

| | |
| :--- | :--- |
| **Dono** | Ingestão OLTP |
| **Descrição** | Fornecedores, por par documento × nome (`UNIQUE NULLS NOT DISTINCT`). |
| **Origem** | `stg_ceap_raw` |
| **Grão** | `(cnpj_cpf, razao_social)` |
| **Colunas principais** | `id_fornecedor` (PK); `cnpj_cpf` 👤 ← CSV `txtCNPJCPF` (como publicado, com máscara; pode ser CPF); `razao_social` ← `txtFornecedor` |

### public.categoria_despesa e public.especificacao_despesa

| | |
| :--- | :--- |
| **Dono** | Ingestão OLTP |
| **Descrição** | Subcotas da CEAP e o detalhamento de cada uma (ex.: combustível para veículos ou aeronaves). |
| **Origem** | `stg_ceap_raw` |
| **Grão** | uma subcota (`num_subcota`); uma especificação por `(num_subcota, num_especificacao, descricao)` |
| **Colunas principais** | `num_subcota` ← CSV `numSubCota`; `descricao` ← `txtDescricao`; `num_especificacao` ← `numEspecificacaoSubCota`; `especificacao_despesa.descricao` ← `txtDescricaoEspecificacao` |

### public.despesa_ceap

| | |
| :--- | :--- |
| **Dono** | Ingestão OLTP |
| **Descrição** | Fato transacional *insert-only* (livro-razão, [ADR-0001](adr/0001-modelagem-transacional-insert-only-ceap.md)). Fonte do lote e do CDC da E2 e da `mv_gasto_mensal_deputado`. |
| **Origem** | `stg_ceap_raw` + chaves de `fornecedor` e `especificacao_despesa`. Linhas sem `nuDeputadoId` ficam de fora. |
| **Grão** | uma linha do CSV com `nuDeputadoId` (785.754 linhas na carga de referência, segundo o [Modelo de dados](modelo-de-dados.md#fornecedor)) |

| Coluna | Significado | Vem de |
| :--- | :--- | :--- |
| `id_despesa` (PK) | Chave técnica gerada pelo banco (`BIGSERIAL`) | — |
| `id_deputado` | Deputado ou liderança | CSV `nuDeputadoId` |
| `valor_liquido` | Valor debitado da cota, `NUMERIC(12,2)`; vazio vira 0 | CSV `vlrLiquido` |
| `ano_competencia`, `mes_competencia` | Competência da despesa | CSV `numAno`, `numMes` |
| `sigla_partido_emissao` ⚠️ | Apesar do nome, é o partido **como publicado** (já regravado com o atual) | CSV `sgPartido` |
| `data_emissao` | Emissão do documento (nula em telefonia e SIGEPA) | CSV `datEmissao` |
| `passageiro` 👤 | Nome do passageiro em passagens aéreas | CSV `txtPassageiro` |
| `data_ingestao` | Quando o banco registrou a linha | `DEFAULT CURRENT_TIMESTAMP` |

### public.mv_gasto_mensal_deputado

| | |
| :--- | :--- |
| **Dono** | Ingestão OLTP |
| **Descrição** | Visão materializada da E3 para a [consulta otimizada com `EXPLAIN`](explain/README.md). Recalculada por `scripts/main.py` após a carga. |
| **Origem** | `despesa_ceap` (`migrations/004_create_mv_gasto_mensal.sql`) |
| **Grão** | deputado × UF publicada × ano × mês × legislatura |
| **Colunas principais** | `gasto` = `SUM(valor_liquido)`; `qtd_lancamentos`; `sigla_uf` ← `despesa_ceap.sigla_uf_emissao` |

### Tabelas de controle

| Tabela | Dono | Descrição | Origem |
| :--- | :--- | :--- | :--- |
| `public.schema_migrations` | Ingestão OLTP | Migrações aplicadas (`version`, `applied_at`) | `scripts/run_migrations.py` |
| `public.cdc_consumer_checkpoint` | Lakehouse E2 | Até onde o consumidor CDC já processou | `scripts/cdc_stream_consumer.py` |

## Lakehouse E2 (Delta Lake)

Em `lakehouse/delta/`. Ramo analítico da E2: lido com DuckDB (`delta_scan`), **não** alimenta a
Bronze, o dbt nem o painel. Detalhes em [Lakehouse e CDC](lakehouse.md) e
[Enriquecimento societário](enriquecimento.md).

### delta/despesa_ceap

| | |
| :--- | :--- |
| **Dono** | Lakehouse E2 |
| **Descrição** | Cópia desnormalizada de `despesa_ceap`, particionada por `ano_competencia`. |
| **Origem** | OLTP `despesa_ceap` ⨝ `parlamentar` ⨝ `fornecedor` ⨝ `categoria_despesa`. Lote: `scripts/batch_ingest_lakehouse.py` (recria tudo). CDC: `scripts/cdc_stream_consumer.py` (`MERGE` por `id_despesa`). |
| **Grão** | uma linha de `despesa_ceap` (`id_despesa`) |
| **Colunas principais** | `id_despesa` ← OLTP; `valor_liquido` (`DOUBLE`) ← `despesa_ceap.valor_liquido`; `cnpj_cpf` 👤, `razao_social` ← `fornecedor`; `nome_parlamentar` ← `parlamentar`; `subcota_descricao` ← `categoria_despesa.descricao`; `passageiro` 👤 ← `despesa_ceap.passageiro` |
| ⚠️ | Exclusões no OLTP não são propagadas pelo CDC ([limitações](arquitetura.md#limitações-conhecidas)). |

### delta/dim_fornecedor_cadastral e delta/dim_quadro_societario_ubo

| | |
| :--- | :--- |
| **Dono** | Enriquecimento societário |
| **Descrição** | Cadastro das empresas e cadeia societária resolvida até o beneficiário final (UBO). |
| **Origem** | Base de demonstração definida em `scripts/enrich_receita_socios.py` (ver [Fontes públicas](#fontes-públicas)). Gravadas com `overwrite`. |
| **Grão** | uma empresa (`cnpj`); um elo da cadeia (`cnpj_fornecedor_ceap` × sócio × `grau_profundidade`) |
| **Colunas principais** | `cnpj`, `cnpj_basico`, `razao_social`, `cnae_principal`; `cnpj_fornecedor_ceap`, `caminho_societario`, `doc_socio` 👤 (CPF mascarado), `nome_socio` 👤, `is_beneficiario_final` |
| **Ligação com a CEAP** | Só em consulta: `delta/despesa_ceap.cnpj_cpf` × `cnpj_fornecedor_ceap` pela raiz de 8 dígitos (`scripts/consulta_caminho_societario.py`). |

## Bronze

Em `lakehouse/bronze/` (Delta). Cópia fiel das fontes públicas, tudo como texto, mais colunas de
controle com prefixo `_`. São as `sources` do dbt (`dbt_ceap/models/staging/_sources.yml`), com
freshness declarada.

### bronze/ceap_lancamento

| | |
| :--- | :--- |
| **Dono** | Bronze e orquestração |
| **Descrição** | Uma linha por linha dos CSVs anuais da CEAP. A coluna `cpf` é descartada (minimização, LGPD). |
| **Origem** | `base-dados/Ano-AAAA.csv` lido com DuckDB `read_csv` (`ingestao/bronze.py`, asset Dagster `bronze/ceap_lancamento`). **Não passa pelo OLTP.** |
| **Grão** | uma linha publicada (`_hash_lancamento`); partição `ano_arquivo` (reprocessar um ano substitui só ela) |
| **Freshness** | aviso após 26 h, erro após 48 h (`_ingerido_em`) |

| Coluna | Significado | Vem de |
| :--- | :--- | :--- |
| 31 colunas de origem | Texto como publicado (`nuDeputadoId`, `vlrLiquido`, `sgPartido`, `txtCNPJCPF` 👤, `txtPassageiro` 👤…) | CSV, coluna de mesmo nome |
| `_hash_lancamento` | md5 de todos os campos de origem (inclusive `cpf`, antes do descarte). Chave do lançamento | calculado na ingestão |
| `_arquivo_origem` | Nome do CSV (ex.: `Ano-2025.csv`) | nome do arquivo lido |
| `_ingerido_em` | Momento (UTC) da gravação da partição | relógio da ingestão |
| `ano_arquivo` | Ano do arquivo; partição Delta | argumento da ingestão |

### bronze/camara_deputado_historico

| | |
| :--- | :--- |
| **Dono** | Bronze e orquestração |
| **Descrição** | Eventos do histórico de cada deputado (posse, licença, alteração de partido). Fonte do SCD tipo 2: o `sgPartido` do CSV é regravado com o partido atual. |
| **Origem** | API da Câmara `GET /deputados/{id}/historico`, para cada `ideCadastro` presente em `bronze/ceap_lancamento` (`ingestao/bronze_historico.py`). Nada é gravado se mais de 1% das chamadas falhar. |
| **Grão** | um evento retornado pela API |
| **Freshness** | aviso após 7 dias, erro após 30 dias (`_extraido_em`) |
| **Colunas principais** | `id` (= `ideCadastro`), `siglaPartido`, `siglaUf`, `dataHora`, `idLegislatura`, `descricaoStatus` ← campos de mesmo nome do JSON; `_ordem_evento`, `_extraido_em`, `_origem` (`api` ou `cache`) ← ingestão |

## Silver

Schema `silver` de `lakehouse/ceap.duckdb`, construído pelo dbt. Dono de todas as tabelas:
**Modelagem dbt**. Colunas completas em [Dicionário de dados › Silver](dicionario-de-dados.md#silver).

| Tabela | Descrição | Origem (dbt `ref`/`source`) | Grão | Colunas principais (← de onde vêm) |
| :--- | :--- | :--- | :--- | :--- |
| `stg_ceap__lancamento` (view) | Tipagem e renomeação da Bronze; nenhuma linha filtrada | `source('bronze','ceap_lancamento')` | lançamento publicado | `id_lancamento` ← `_hash_lancamento`; `id_deputado` ← `nuDeputadoId`; `valor_liquido` ← `vlrLiquido::decimal(14,2)`; `documento_fornecedor` 👤 ← só os dígitos de `txtCNPJCPF`; `competencia` ← `make_date(numAno, numMes, 1)`; `arquivo_origem` ← `_arquivo_origem` |
| `stg_camara__deputado_evento` (view) | Eventos tipados, só legislaturas 56 e 57 e com partido | `source('bronze','camara_deputado_historico')` | evento | `id_cadastro_camara` ← `id`; `sigla_partido` ← `siglaPartido`; `sigla_uf` ← `siglaUf`; `data_hora_evento` ← `dataHora` |
| `int_parlamentar__versoes` | Trechos contínuos com o mesmo partido e UF | `stg_camara__deputado_evento` | deputado × versão | `sigla_partido`, `sigla_uf`, `inicio_versao` |
| `dim_parlamentar_scd` | SCD tipo 2 do parlamentar (partido e UF da época), mais uma versão por liderança | `int_parlamentar__versoes`, `stg_ceap__lancamento` (mapa `ideCadastro` ↔ `nuDeputadoId`) | versão do parlamentar | `sk_parlamentar`; `id_deputado`; `sigla_partido` e `sigla_uf` ← API; `valido_de`, `valido_ate`, `is_atual` |
| `dim_fornecedor` | Fornecedor por documento (sem documento, pelo nome); SCD tipo 1 no nome | `stg_ceap__lancamento` | fornecedor | `sk_fornecedor` = md5 de `chave_fornecedor`; `documento_fornecedor` 👤; `nome_fornecedor` (grafia mais frequente) |
| `dim_categoria_despesa` | Subcotas com as regras de domínio | `stg_ceap__lancamento`, seed `regra_subcota` | subcota | `num_subcota`, `descricao_subcota`, `grupo_despesa`, `permite_valor_negativo` |
| `dim_calendario` | Calendário com as flags de maturação e de janela comparável | `stg_ceap__lancamento`, seed `ruptura_publicacao` | dia | `competencia`, `is_competencia_fechada`, `is_competencia_comparavel` |
| `fct_lancamento_ceap` 🔒 | Fato atômico; não pode mudar contagem nem soma em relação à Bronze (`assert_fato_reconcilia_com_bronze`) | `stg_ceap__lancamento` ⨝ `dim_parlamentar_scd` (pela data do gasto) ⨝ `dim_calendario` ⨝ `dim_categoria_despesa` | lançamento publicado (`id_lancamento`) | `valor_liquido` ← stg; `sk_parlamentar` ← SCD vigente em `coalesce(data_emissao, competencia)`; `sk_fornecedor`; `is_competencia_comparavel`; `arquivo_origem`, `ingerido_em` (linhagem até a fonte) |
| `regra_subcota` (seed) | Regras por subcota, revisadas pela Squad | `dbt_ceap/seeds/regra_subcota.csv` (versionado no repositório) | subcota | `permite_valor_negativo`, `justificativa_negativo` |
| `ruptura_publicacao` (seed) | Rupturas de publicação investigadas; a primeira encerra a janela comparável | `dbt_ceap/seeds/ruptura_publicacao.csv` | subcota × início | `competencia_inicio`, `descricao`, `evidencia` |

!!! note "Duas origens que não são a fonte pública"
    Os seeds `regra_subcota` e `ruptura_publicacao` são **conhecimento de domínio registrado pela
    Squad**, não dados da Câmara. Eles mudam o que entra nos rankings (a janela comparável termina
    antes da primeira ruptura), então uma mudança neles muda números do painel sem que a fonte
    tenha mudado.

## Gold

Schema `gold` de `lakehouse/ceap.duckdb`. Dono: **Modelagem dbt**. Todas com contrato de esquema 🔒.
Colunas completas em [Dicionário de dados › Gold](dicionario-de-dados.md#gold).

| Tabela | Descrição | Origem | Grão | Colunas principais |
| :--- | :--- | :--- | :--- | :--- |
| `fct_gasto_mensal_parlamentar` 🔒 | Gasto mensal e desvio em relação à mediana da UF. 57ª Legislatura, sem lideranças. ⚠️ `gasto_deputado_mes`, `mediana_uf_mes` e `desvio_deputado_mes` se repetem entre versões do mesmo mês: não somar | `fct_lancamento_ceap`, `dim_parlamentar_scd` | deputado × versão SCD × competência | `gasto_versao` = Σ `valor_liquido`; `gasto_deputado_mes`; `mediana_uf_mes` (mediana entre deputados da mesma UF no mês); `desvio_deputado_mes` = gasto − mediana; `desvio_alocado` (somável por partido) |
| `mart_desvio_parlamentar` 🔒 | Ranking de parlamentares (1ª parte da pergunta) | `fct_gasto_mensal_parlamentar`, `fct_lancamento_ceap`, `dim_parlamentar_scd` | deputado | `desvio_acumulado` = Σ meses comparáveis de `desvio_deputado_mes`; `posicao_ranking`; `hhi_fornecedores` |
| `mart_desvio_partido` 🔒 | Ranking de partidos pela sigla da data do gasto, com o erro que a sobrescrita causaria (2ª parte) | `fct_gasto_mensal_parlamentar`, `dim_parlamentar_scd` | partido | `desvio_acumulado` = Σ `desvio_alocado`; `desvio_medio_por_deputado_mes`; `erro_gasto_se_sobrescrito` |
| `mart_concentracao_parlamentar` 🔒 | Concentração em categorias e fornecedores (3ª parte) | `fct_lancamento_ceap`, `dim_fornecedor`, `dim_categoria_despesa`, `dim_parlamentar_scd` | deputado × subcota × fornecedor | `gasto_fornecedor`, `gasto_categoria`, `excesso_categoria_vs_uf`, `documento_fornecedor` 👤 |
| `mart_freshness_gold` 🔒 | Freshness medida no build contra o SLA de 26 h | `fct_lancamento_ceap`, `dim_calendario` | tabela de consumo | `ingerido_em_mais_recente`, `idade_horas_no_build`, `dentro_do_sla` |

## Semântica

Schema `semantico` de `lakehouse/ceap.duckdb`: **views** com as métricas prontas, a única fonte do
painel e do ETL reverso. Dono: **Camada semântica**. Todas com contrato de esquema 🔒. Fórmula e
unidade de cada métrica no [catálogo de métricas](e4.md#12-catálogo-de-métricas), definido em
`dbt_ceap/models/semantic/_semantic.yml`.

| View | Descrição | Origem | Grão | Quem consome |
| :--- | :--- | :--- | :--- | :--- |
| `met_parlamentar` 🔒 | Ranking de desvio por deputado, a regra de alerta (`em_alerta` = top 15) e a fração de meses acima da mediana | `gold.mart_desvio_parlamentar` | deputado | painel (bloco 1, filtros e seletor do bloco 3), ETL reverso |
| `met_parlamentar_mes` 🔒 | Série mensal do parlamentar contra a mediana da UF, com a troca de partido marcada | `gold.fct_gasto_mensal_parlamentar`, `silver.dim_parlamentar_scd` | deputado × competência | painel (bloco 3, linha mês a mês) |
| `met_partido` 🔒 | Ranking de partidos com o corte de 5 deputados | `gold.mart_desvio_partido` | partido | painel (bloco 2) |
| `met_categoria_parlamentar` 🔒 | Categoria que explica o desvio | `gold.mart_concentracao_parlamentar` | deputado × subcota | painel (bloco 3) |
| `met_fornecedor_parlamentar` 🔒 | Concentração em fornecedores. CPF de pessoa física mascarado no documento e no nome | `gold.mart_concentracao_parlamentar` | deputado × fornecedor | painel (blocos 1 e 3) |
| `met_lancamento_parlamentar` 🔒 | Lançamentos com o link do documento na Câmara (`url_documento`). CPF mascarado; sem link para documento de pessoa física (o recibo traz o CPF), sem passageiro e sem trecho | `silver.fct_lancamento_ceap`, `silver.dim_fornecedor`, `silver.dim_categoria_despesa` | lançamento | painel (bloco 3, maiores lançamentos), sempre filtrada por deputado e subcota |
| `met_contexto` 🔒 | Janela comparável, freshness lida na hora, ruptura e erro total da sobrescrita | `gold.fct_gasto_mensal_parlamentar`, `gold.mart_desvio_partido`, `gold.mart_freshness_gold`, `silver.fct_lancamento_ceap`, seed `ruptura_publicacao` | uma linha | painel (cabeçalho e bloco 2), ETL reverso (`atualizado_em`, janela) |
| `met_qualidade_build` 🔒 | Resultado dos testes do build mais recente: o selo de qualidade | `auditoria.resultado_build` | uma linha | painel (selo no cabeçalho) |
| `auditoria.resultado_build` (tabela de controle) | Uma linha por `dbt build` ou `dbt test`, com os testes por resultado. Criada no `on-run-start` e preenchida no `on-run-end` (`dbt_ceap/macros/registra_build.sql`); fonte `auditoria` no dbt | o próprio dbt (`results`) | execução do dbt | `met_qualidade_build` |

## Destino do ETL reverso (PostgreSQL, schema `alerta`)

Criado por `migrations/006_etl_reverso.sql` no mesmo banco `ceap_oltp` da E1. Tabelas *insert-only*
(gatilho recusa `UPDATE` e `DELETE`); autoria e horário carimbados pelo banco. Detalhes em
[E4 › ETL reverso](e4.md#2-etl-reverso-a-fila-de-auditoria).

| Tabela | Dono | Descrição | Origem | Grão | Colunas principais |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `alerta.desvio_parlamentar` | ETL reverso | Retrato do top 15 a cada publicação | `semantico.met_parlamentar` (`em_alerta`) × `semantico.met_contexto`, por `etl_reverso/publicar_alertas.py` (asset Dagster `alerta/desvio_parlamentar_postgres`) | `(referencia_dados, id_deputado)` | `referencia_dados` ← `met_contexto.atualizado_em`; `desvio_acumulado` ← `met_parlamentar.desvio_acumulado` arredondado a 2 casas; `posicao_ranking`; `janela_inicio`, `janela_fim` ← `met_contexto` |
| `alerta.execucao` | ETL reverso | Uma linha por publicação: linhas recebidas e novas | `etl_reverso/publicar_alertas.py` | publicação | `referencia_dados`, `linhas_recebidas`, `linhas_novas`, `origem` |
| `alerta.tratamento` | Auditor | Decisões do auditor sobre cada alerta (evento por decisão; vale a mais recente) | registro manual do auditor | decisão | `situacao` (`em_analise`, `sem_irregularidade`, `encaminhado`), `observacao`, `registrado_por` e `registrado_em` (do banco) |
| `alerta.vw_fila_auditoria` (view) | ETL reverso | A fila do dia: retrato mais recente com a última decisão de cada parlamentar | `alerta.desvio_parlamentar`, `alerta.tratamento` | parlamentar no retrato mais recente | todas as de `desvio_parlamentar` + `situacao` (`pendente` sem decisão) |

## Consumidores

| Consumidor | Lê | Não lê | Código |
| :--- | :--- | :--- | :--- |
| Painel Streamlit (`:8501`) | só `semantico.*` (8 views; `met_lancamento_parlamentar` filtrada por deputado e subcota) | Gold, Silver, Bronze, OLTP | `painel/app.py` |
| ETL reverso | `semantico.met_parlamentar`, `semantico.met_contexto` | Gold, Silver | `etl_reverso/publicar_alertas.py` |
| Auditor | `alerta.vw_fila_auditoria`; escreve em `alerta.tratamento` | lakehouse | `etl_reverso/exemplo_auditor.sql` |
| Consultas de auditoria societária (E2) | `delta/despesa_ceap`, `delta/dim_quadro_societario_ubo` | camadas da E3 | `scripts/consulta_caminho_societario.py` |

A regra "o painel só lê `semantico`" é conferida por `scripts/verificar_consumo_duplo.py`
([E4, seção 1.3](e4.md#13-como-garantimos-o-mesmo-número)).

## Como manter este catálogo

- **Tabela nova ou coluna nova na Bronze, Silver, Gold ou Semântica:** descreva no `.yml` do dbt e
  rode `scripts/gerar_docs_e3.sh` (atualiza o dicionário). Acrescente a tabela aqui com dono,
  origem e grão, e a aresta nova em [Linhagem](linhagem.md).
- **Mudança no OLTP ou no schema `alerta`:** a migração nova entra em
  [Modelo de dados](modelo-de-dados.md) e aqui.
- **Mudança de dono:** atualize a tabela [Donos](#donos).
