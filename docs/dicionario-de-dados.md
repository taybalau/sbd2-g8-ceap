# Dicionário de dados

> Página gerada por `scripts/gerar_dicionario.py`: os tipos vêm do banco gerado pelo pipeline e
> as descrições, dos arquivos `.yml` do dbt (`dbt_ceap/models/**/_*.yml`). Para mudar uma
> descrição, edite o `.yml` e rode o script de novo.

O banco transacional da E1 (PostgreSQL) está descrito em [Modelo de dados](modelo-de-dados.md).
A camada analítica tem quatro camadas (Bronze, Silver e Gold da E3; Semântica da E4):

| Camada | Conteúdo | Tabelas |
| :--- | :--- | ---: |
| [Bronze](#bronze) | Cópia fiel dos dados públicos, em Delta Lake (`lakehouse/bronze/`), tudo como texto. | 2 |
| [Silver](#silver) | Dados tipados, dimensões e o fato atômico (schema `silver` do `ceap.duckdb`). | 10 |
| [Gold](#gold) | Tabelas analíticas com grão declarado (schema `gold` do `ceap.duckdb`). | 5 |
| [Semântica](#semântica) | Camada semântica de métricas da E4 (views do schema `semantico`): a única fonte do painel e do ETL reverso. | 9 |

Legenda: 🔒 contrato de esquema (`contract: enforced`): o build reprova se a coluna sumir ou mudar de tipo · 👤 dado pessoal (LGPD).

## Bronze

### `bronze/camara_deputado_historico`

Uma linha por evento do histórico do deputado (GET /deputados/{id}/historico). É a fonte do SCD tipo 2: o sgPartido do CSV da CEAP é regravado com o partido atual.

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `id` | `VARCHAR` | ideCadastro do deputado (id da API). |
| `nome` | `VARCHAR` | Nome civil do deputado. |
| `nomeEleitoral` | `VARCHAR` | Nome eleitoral do deputado. |
| `siglaPartido` | `VARCHAR` | Partido do deputado a partir deste evento. |
| `siglaUf` | `VARCHAR` | UF do deputado a partir deste evento. |
| `idLegislatura` | `VARCHAR` | Legislatura do evento. |
| `dataHora` | `VARCHAR` | Data e hora do evento (posse, licença, alteração de partido...). |
| `situacao` | `VARCHAR` | Situação do mandato após o evento (Exercício, Licença...). |
| `condicaoEleitoral` | `VARCHAR` | Titular ou suplente. |
| `descricaoStatus` | `VARCHAR` | Descrição do evento (ex.: Alteração de partido). |
| `_id_consultado` | `VARCHAR` | ideCadastro usado na chamada à API. |
| `_ordem_evento` | `VARCHAR` | Posição do evento na resposta da API; desempata eventos no mesmo instante. |
| `_extraido_em` | `VARCHAR` | Momento (UTC) da extração. Base da freshness do histórico. |
| `_origem` | `VARCHAR` | api ou cache (modo degradado CEAP_USAR_CACHE=1). |

### `bronze/ceap_lancamento`

Uma linha por linha dos CSVs anuais da CEAP publicados pela Câmara. Coluna cpf descartada (LGPD).

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `txNomeParlamentar` | `VARCHAR` | Nome parlamentar do deputado, ou nome da liderança (ex.: LIDERANÇA DO PT). |
| `ideCadastro` | `VARCHAR` | Identificador do deputado no cadastro da Câmara; é o id da API de dados abertos. Vazio para lideranças. |
| `nuCarteiraParlamentar` | `VARCHAR` | Número da carteira parlamentar. Vazio para lideranças. |
| `nuLegislatura` | `VARCHAR` | Ano de início da legislatura (2023 para a 57ª). |
| `sgUF` | `VARCHAR` | UF do deputado, como publicada (NA para lideranças). |
| `sgPartido` | `VARCHAR` | Partido do deputado, como publicado. A Câmara regrava com o partido ATUAL; não serve para histórico. |
| `codLegislatura` | `VARCHAR` | Número da legislatura (56 ou 57 no período). |
| `numSubCota` | `VARCHAR` | Código da subcota (categoria de despesa da CEAP). |
| `txtDescricao` | `VARCHAR` | Descrição da subcota. |
| `numEspecificacaoSubCota` | `VARCHAR` | Código da especificação dentro da subcota (0 quando não há). |
| `txtDescricaoEspecificacao` | `VARCHAR` | Descrição da especificação (ex.: combustível para veículos ou aeronaves). |
| `txtFornecedor` | `VARCHAR` | Nome do fornecedor ou prestador, como digitado no documento. |
| `txtCNPJCPF` 👤 | `VARCHAR` | CNPJ ou CPF do fornecedor, com ou sem máscara. Vazio em passagens do SIGEPA e auxílio-moradia. *(pode ser CPF de pessoa física (fornecedor))* |
| `txtNumero` | `VARCHAR` | Número do documento fiscal. |
| `indTipoDocumento` | `VARCHAR` | Tipo do documento: 0 nota fiscal, 1 recibo, 2 despesa no exterior, 4 nota fiscal eletrônica. |
| `datEmissao` | `VARCHAR` | Data e hora de emissão do documento. Vazia em 28.496 lançamentos (telefonia, SIGEPA). |
| `vlrDocumento` | `VARCHAR` | Valor total do documento, em reais. |
| `vlrGlosa` | `VARCHAR` | Valor glosado (não reembolsado), em reais. |
| `vlrLiquido` | `VARCHAR` | Valor efetivamente debitado da cota, em reais. Negativo em créditos e compensações. |
| `numMes` | `VARCHAR` | Mês de competência do lançamento. |
| `numAno` | `VARCHAR` | Ano de competência do lançamento. |
| `numParcela` | `VARCHAR` | Número da parcela, em despesas parceladas (0 quando não há). |
| `txtPassageiro` 👤 | `VARCHAR` | Nome do passageiro em passagens aéreas. Dado pessoal: fica só na Bronze. *(dado pessoal de terceiro: fica só na Bronze)* |
| `txtTrecho` | `VARCHAR` | Trecho da viagem em passagens aéreas (ex.: BSB/GRU). |
| `numLote` | `VARCHAR` | Número do lote de processamento na Câmara. |
| `numRessarcimento` | `VARCHAR` | Número do ressarcimento na Câmara. |
| `datPagamentoRestituicao` | `VARCHAR` | Data em que o valor foi restituído aos cofres públicos, quando houve. |
| `vlrRestituicao` | `VARCHAR` | Valor restituído, em reais. |
| `nuDeputadoId` | `VARCHAR` | Identificador numérico do deputado nos arquivos da CEAP (difere do ideCadastro). |
| `ideDocumento` | `VARCHAR` | Identificador do documento na Câmara. NÃO é chave: vale 0 em 30.357 linhas e se repete em até 9. |
| `urlDocumento` | `VARCHAR` | Link para a imagem do documento no portal da Câmara. |
| `_hash_lancamento` | `VARCHAR` | md5 de todos os campos de origem; identifica a linha publicada. |
| `_arquivo_origem` | `VARCHAR` | Nome do CSV de onde a linha veio (ex.: Ano-2025.csv). |
| `_ingerido_em` | `VARCHAR` | Momento (UTC) em que a partição foi gravada na Bronze. Base da freshness. |
| `ano_arquivo` | `VARCHAR` | Ano do arquivo; é a partição Delta (reprocessar um ano substitui só ela). |

## Silver

### `silver.dim_calendario`

**Grão:** um dia civil.

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `data` | `DATE` | Dia civil (2022-01-01 a 2026-12-31). |
| `ano` | `BIGINT` | Ano do dia. |
| `mes` | `BIGINT` | Mês do dia (1 a 12). |
| `competencia` | `DATE` | Primeiro dia do mês do dia. |
| `dia_semana_iso` | `BIGINT` | Dia da semana ISO (1 = segunda, 7 = domingo). |
| `is_fim_de_semana` | `BOOLEAN` | Verdadeiro aos sábados e domingos. |
| `is_competencia_fechada` | `BOOLEAN` | Verdadeiro se o mês já tem 4 meses de maturação em relação à última competência publicada. |
| `is_competencia_comparavel` | `BOOLEAN` | Fechado e anterior à primeira ruptura de publicação: é a janela dos rankings. |

### `silver.dim_categoria_despesa`

**Grão:** uma linha por subcota da CEAP.

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `num_subcota` | `INTEGER` | Código da subcota da CEAP. |
| `descricao_subcota` | `VARCHAR` | Descrição da subcota, como publicada. |
| `grupo_despesa` | `VARCHAR` | Grupo da subcota (seed regra_subcota). Nulo = subcota nova que ninguém classificou. |
| `permite_valor_negativo` | `BOOLEAN` | Verdadeiro nas subcotas de compensação (40, 996, 998, 999), onde valor negativo é legítimo. |
| `justificativa_negativo` | `VARCHAR` | Por que a subcota pode ter valor negativo, com a evidência. |

### `silver.dim_fornecedor`

**Grão:** uma linha por fornecedor (CNPJ/CPF; sem documento, pelo nome). SCD tipo 1 no nome, justificado no modelo.

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `sk_fornecedor` | `VARCHAR` | Chave do fornecedor: md5 de chave_fornecedor. |
| `chave_fornecedor` 👤 | `VARCHAR` | Documento (só dígitos) ou, sem documento, 'SEM-DOC:' + nome em maiúsculas. *(pode conter CPF de pessoa física (fornecedor))* |
| `documento_fornecedor` 👤 | `VARCHAR` | CNPJ (14 dígitos) ou CPF (11) do fornecedor, só dígitos. Nulo quando não informado. *(pode ser CPF de pessoa física (fornecedor))* |
| `tipo_documento_fornecedor` | `VARCHAR` | CNPJ, CPF, OUTRO ou SEM DOCUMENTO. |
| `nome_fornecedor` | `VARCHAR` | Grafia mais frequente do nome (SCD tipo 1: o nome é sobrescrito, as séries usam o documento). |
| `qtd_grafias_nome` | `BIGINT` | Quantas grafias diferentes do nome foram publicadas para o mesmo documento. |
| `primeira_competencia` | `DATE` | Primeira competência com gasto no fornecedor. |
| `ultima_competencia` | `DATE` | Última competência com gasto no fornecedor. |

### `silver.dim_parlamentar_scd`

**Grão:** uma linha por versão do parlamentar (trecho contínuo com o mesmo partido e UF). SCD tipo 2 construído do histórico oficial de eventos da Câmara (não do CSV, que é regravado com o partido atual).

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `sk_parlamentar` | `VARCHAR` | Chave substituta da versão do parlamentar. |
| `id_deputado` | `INTEGER` | nuDeputadoId do deputado ou da liderança. |
| `id_cadastro_camara` | `INTEGER` | ideCadastro do deputado (nulo para lideranças). |
| `numero_versao` | `HUGEINT` | Ordem da versão do deputado (1 = a mais antiga). |
| `nome_parlamentar` | `VARCHAR` | Nome do deputado na versão (ou da liderança). |
| `sigla_partido` | `VARCHAR` | Partido vigente na versão, segundo o histórico oficial (nulo para lideranças). |
| `sigla_uf` | `VARCHAR` | UF vigente na versão (nula para lideranças). |
| `is_lideranca` | `BOOLEAN` | Verdadeiro para contas de liderança, que têm uma versão única sem partido. |
| `data_inicio_real` | `TIMESTAMP` | Data do evento que abriu a versão (a primeira versão é estendida para trás em valido_de). |
| `evento_de_abertura` | `VARCHAR` | Evento que abriu a versão (ex.: Posse, Alteração de partido). |
| `valido_de` | `TIMESTAMP` | Início da vigência da versão (inclusive). A primeira versão começa em 1900-01-01. |
| `valido_ate` | `TIMESTAMP` | Fim da vigência (exclusive). A versão atual vai até 9999-12-31. |
| `is_atual` | `BOOLEAN` | Verdadeiro na versão vigente hoje. |
| `total_versoes` | `BIGINT` | Quantidade de versões do deputado. |

### `silver.fct_lancamento_ceap` 🔒

**Grão:** uma linha por lançamento publicado pela Câmara nos CSVs da CEAP (documento fiscal, trecho de bilhete aéreo ou crédito/compensação). **Não** é "uma linha por documento": ideDocumento se repete (até 9×) e vale 0 em 30.357 linhas.

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `id_lancamento` | `VARCHAR` | Chave do lançamento: md5 de todos os campos de origem. |
| `sk_parlamentar` | `VARCHAR` | Versão SCD2 do parlamentar vigente na data do gasto (emissão; sem emissão, o 1º dia da competência). |
| `sk_fornecedor` | `VARCHAR` | Chave do fornecedor em dim_fornecedor (md5 do documento ou, sem documento, do nome). |
| `num_subcota` | `INTEGER` | Subcota da despesa; liga com dim_categoria_despesa. |
| `id_deputado` | `INTEGER` | nuDeputadoId do deputado ou da liderança. |
| `data_emissao` | `DATE` | Nula em 28.496 lançamentos (telefonia, SIGEPA). Por isso a junção com o SCD usa coalesce(data_emissao, competencia). |
| `data_referencia_scd` | `DATE` | Data usada para escolher a versão do SCD: a emissão ou, sem ela, o 1º dia da competência. |
| `competencia` | `DATE` | Primeiro dia do mês de competência (mês a que a despesa se refere). |
| `ano_competencia` | `INTEGER` | Ano de competência. |
| `mes_competencia` | `INTEGER` | Mês de competência (1 a 12). |
| `codigo_legislatura` | `INTEGER` | Número da legislatura do lançamento (56 ou 57). |
| `sigla_partido_publicada` | `VARCHAR` | Partido como publicado no CSV (já sobrescrito pela Câmara com o atual). Só para auditoria. |
| `sigla_uf_publicada` | `VARCHAR` | UF como publicada no CSV (NA vira nulo). |
| `id_documento_camara` | `BIGINT` | ideDocumento (0 vira nulo). Não é chave: repete-se em bilhetes SIGEPA. |
| `numero_documento` | `VARCHAR` | Número do documento fiscal. |
| `tipo_documento` | `INTEGER` | 0 nota fiscal, 1 recibo, 2 despesa no exterior, 4 nota fiscal eletrônica. |
| `trecho` | `VARCHAR` | Trecho da viagem, em passagens aéreas. |
| `url_documento` | `VARCHAR` | Link para a imagem do documento no portal da Câmara. |
| `valor_documento` | `DECIMAL(14,2)` | Valor total do documento (R$). |
| `valor_glosa` | `DECIMAL(14,2)` | Valor glosado, não reembolsado (R$). Vazio vira 0. |
| `valor_liquido` | `DECIMAL(14,2)` | Valor debitado da cota (R$). Negativo em créditos e compensações. É a medida somada em toda a Gold. |
| `valor_restituicao` | `DECIMAL(14,2)` | Valor restituído aos cofres públicos (R$), quando houve. |
| `is_lideranca` | `BOOLEAN` | Verdadeiro para contas de liderança partidária ou de governo (sem ideCadastro). |
| `is_legislatura_alvo` | `BOOLEAN` | Verdadeiro para lançamentos da 57ª Legislatura (jan/2023 é da 56ª). |
| `is_competencia_fechada` | `BOOLEAN` | Verdadeiro se a competência já tem 4 meses de maturação (notas atrasadas já chegaram). |
| `is_competencia_comparavel` | `BOOLEAN` | Fechada e anterior à primeira ruptura de publicação registrada: é a janela dos rankings. |
| `is_credito` | `BOOLEAN` | Verdadeiro quando valor_liquido < 0 (crédito ou compensação). |
| `is_valor_inconsistente` | `BOOLEAN` | Verdadeiro quando líquido ≠ documento − glosa (fora dos créditos de compensação). Sinalizado, não descartado. |
| `arquivo_origem` | `VARCHAR` | CSV de onde a linha veio (linhagem até a fonte pública). |
| `ingerido_em` | `TIMESTAMP WITH TIME ZONE` | Momento (UTC) em que a linha foi gravada na Bronze. |

### `silver.int_parlamentar__versoes`

**Grão:** uma versão do deputado: trecho contínuo no tempo com o mesmo partido e a mesma UF, segundo o histórico oficial de eventos da Câmara. Base do SCD tipo 2.

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `id_cadastro_camara` | `INTEGER` | ideCadastro do deputado (id da API da Câmara). |
| `numero_versao` | `HUGEINT` | Ordem da versão do deputado (1 = a mais antiga). |
| `nome_parlamentar` | `VARCHAR` | Nome civil do deputado no evento que abriu a versão. |
| `sigla_partido` | `VARCHAR` | Partido do deputado durante a versão, segundo o histórico oficial. |
| `sigla_uf` | `VARCHAR` | UF do deputado durante a versão. |
| `inicio_versao` | `TIMESTAMP` | Data e hora do evento que abriu a versão. |
| `evento_de_abertura` | `VARCHAR` | Descrição do evento que abriu a versão (ex.: Posse, Alteração de partido). |

### `silver.stg_camara__deputado_evento`

**Grão:** um evento do histórico oficial de um deputado (posse, licença, alteração de partido), só das legislaturas 56 e 57 e com partido preenchido.

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `id_cadastro_camara` | `INTEGER` | ideCadastro do deputado (id da API da Câmara). |
| `nome_parlamentar` | `VARCHAR` | Nome civil do deputado, como na API. |
| `sigla_partido` | `VARCHAR` | Partido do deputado a partir do evento. |
| `sigla_uf` | `VARCHAR` | UF do deputado a partir do evento. |
| `id_legislatura` | `INTEGER` | Legislatura do evento (56 ou 57). |
| `data_hora_evento` | `TIMESTAMP` | Data e hora do evento. |
| `ordem_evento` | `INTEGER` | Posição do evento na resposta da API; desempata eventos no mesmo instante. |
| `situacao` | `VARCHAR` | Situação do mandato após o evento (Exercício, Licença...). |
| `descricao_status` | `VARCHAR` | Descrição do evento (ex.: Alteração de partido). |
| `extraido_em` | `TIMESTAMP WITH TIME ZONE` | Momento (UTC) em que o histórico foi extraído da API. |

### `silver.stg_ceap__lancamento`

**Grão:** uma linha por lançamento publicado nos CSVs da CEAP (o mesmo da Bronze). Só tipagem e renomeação; nenhuma linha é filtrada ou agregada.

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `id_lancamento` | `VARCHAR` | Chave do lançamento: md5 de todos os campos de origem (o _hash_lancamento da Bronze). |
| `id_deputado` | `INTEGER` | nuDeputadoId: identificador do deputado nos arquivos da CEAP. |
| `id_cadastro_camara` | `INTEGER` | ideCadastro: identificador do deputado na API da Câmara. Nulo para lideranças. |
| `is_lideranca` | `BOOLEAN` | Verdadeiro para contas de liderança partidária ou de governo (sem ideCadastro). |
| `nome_parlamentar` | `VARCHAR` | Nome parlamentar do deputado ou nome da liderança. |
| `sigla_partido_publicada` | `VARCHAR` | Partido como publicado no CSV (já sobrescrito pela Câmara com o atual). Só para auditoria. |
| `sigla_uf_publicada` | `VARCHAR` | UF como publicada no CSV (NA vira nulo). |
| `codigo_legislatura` | `INTEGER` | Número da legislatura do lançamento (56 ou 57). |
| `num_subcota` | `INTEGER` | Código da subcota (categoria de despesa). |
| `descricao_subcota` | `VARCHAR` | Descrição da subcota. |
| `num_especificacao` | `INTEGER` | Código da especificação dentro da subcota (nulo quando não há). |
| `descricao_especificacao` | `VARCHAR` | Descrição da especificação da subcota. |
| `nome_fornecedor_publicado` | `VARCHAR` | Nome do fornecedor como digitado no documento. |
| `documento_fornecedor` 👤 | `VARCHAR` | CNPJ (14 dígitos) ou CPF (11) do fornecedor, só dígitos. Nulo quando não informado. *(pode ser CPF de pessoa física (fornecedor))* |
| `id_documento_camara` | `BIGINT` | ideDocumento (0 vira nulo). Não é chave: repete-se em bilhetes SIGEPA. |
| `numero_documento` | `VARCHAR` | Número do documento fiscal. |
| `tipo_documento` | `INTEGER` | 0 nota fiscal, 1 recibo, 2 despesa no exterior, 4 nota fiscal eletrônica. |
| `data_emissao` | `DATE` | Data de emissão do documento. Nula em 28.496 lançamentos. |
| `valor_documento` | `DECIMAL(14,2)` | Valor total do documento (R$). |
| `valor_glosa` | `DECIMAL(14,2)` | Valor glosado, não reembolsado (R$). Vazio vira 0. |
| `valor_liquido` | `DECIMAL(14,2)` | Valor debitado da cota (R$). Negativo em créditos e compensações. É a medida somada em toda a Gold. |
| `valor_restituicao` | `DECIMAL(14,2)` | Valor restituído aos cofres públicos (R$), quando houve. |
| `data_pagamento_restituicao` | `DATE` | Data da restituição, quando houve. |
| `competencia` | `DATE` | Primeiro dia do mês de competência (mês a que a despesa se refere). |
| `ano_competencia` | `INTEGER` | Ano de competência. |
| `mes_competencia` | `INTEGER` | Mês de competência (1 a 12). |
| `parcela` | `INTEGER` | Número da parcela, em despesas parceladas (nulo quando não há). |
| `trecho` | `VARCHAR` | Trecho da viagem, em passagens aéreas. |
| `url_documento` | `VARCHAR` | Link para a imagem do documento no portal da Câmara. |
| `arquivo_origem` | `VARCHAR` | CSV de onde a linha veio (linhagem até a fonte pública). |
| `ingerido_em` | `TIMESTAMP WITH TIME ZONE` | Momento (UTC) em que a linha foi gravada na Bronze. |

### `silver.regra_subcota` (seed)

Regras de domínio por subcota. `permite_valor_negativo` foi derivado do perfil dos dados (2026-11-03): só as subcotas 40, 998 e 999 têm vlrLiquido < 0. A 996 (missão oficial, só créditos) apareceu num download posterior do mesmo dia e foi classificada igual. Qualquer negativo novo em outra subcota quebra o teste assert_negativo_somente_em_subcota_de_compensacao e exige análise.

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `num_subcota` | `INTEGER` | Código da subcota da CEAP. |
| `grupo_despesa` | `VARCHAR` | Grupo da subcota usado nas análises (ex.: Passagens aéreas). |
| `permite_valor_negativo` | `BOOLEAN` | Verdadeiro nas subcotas de compensação, onde valor negativo é legítimo. |
| `justificativa_negativo` | `VARCHAR` | Por que a subcota pode ter valor negativo, com a evidência. |

### `silver.ruptura_publicacao` (seed)

Rupturas de publicação CONHECIDAS e investigadas. Os testes de salto e de subcota que some ignoram só o que está aqui; qualquer ruptura nova quebra o build até alguém investigar e registrar. A primeira ruptura encerra a janela "comparável" usada nos rankings.

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `num_subcota` | `INTEGER` | Subcota em que a ruptura foi observada. |
| `competencia_inicio` | `DATE` | Primeira competência afetada. A partir dela, os testes de salto ignoram a subcota. |
| `descricao` | `VARCHAR` | O que mudou na publicação. |
| `evidencia` | `VARCHAR` | Números que mostram a ruptura e a causa provável (ou a indicação de que não foi verificada). |

## Gold

### `gold.fct_gasto_mensal_parlamentar` 🔒

**Grão:** deputado × versão SCD (partido da época) × competência. 57ª Legislatura, sem lideranças. gasto_versao é aditivo; gasto_deputado_mes, mediana_uf_mes e desvio_deputado_mes se REPETEM nas versões de um mesmo mês — não some essas colunas sem antes fazer DISTINCT por (id_deputado, competencia). Para somar desvio por partido use desvio_alocado.

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `id_deputado` | `INTEGER` | nuDeputadoId do deputado (sem lideranças). |
| `sk_parlamentar` | `VARCHAR` | Versão SCD2 do deputado (partido da época). |
| `nome_parlamentar` | `VARCHAR` | Nome do deputado na versão. |
| `sigla_partido` | `VARCHAR` | Partido vigente na versão (na data do gasto). |
| `sigla_uf` | `VARCHAR` | UF vigente na versão. |
| `competencia` | `DATE` | Mês de competência (1º dia). |
| `is_competencia_fechada` | `BOOLEAN` | Mês com 4 meses de maturação. |
| `is_competencia_comparavel` | `BOOLEAN` | Mês dentro da janela dos rankings. |
| `qtd_lancamentos` | `BIGINT` | Lançamentos da versão no mês. |
| `gasto_versao` | `DECIMAL(38,2)` | Gasto da versão no mês (R$). Aditivo: pode ser somado. |
| `gasto_deputado_mes` | `DECIMAL(38,2)` | Gasto total do deputado no mês (R$). Repete-se entre versões do mesmo mês: NÃO somar. |
| `mediana_uf_mes` | `DECIMAL(18,4)` | Mediana do gasto mensal dos deputados da mesma UF no mês (R$): a referência do desvio. NÃO somar. |
| `qtd_deputados_uf_mes` | `BIGINT` | Deputados da UF com gasto no mês (base da mediana). |
| `desvio_deputado_mes` | `DECIMAL(38,4)` | gasto_deputado_mes − mediana_uf_mes (R$). Repete-se entre versões: NÃO somar. |
| `z_deputado_mes` | `DOUBLE` | Z-score robusto: (gasto − mediana da UF) ÷ (1,4826 × MAD da UF no mês). Nulo se o MAD for 0. |
| `desvio_alocado` | `DECIMAL(18,4)` | Desvio do mês rateado entre as versões pelo gasto (R$). Aditivo: é o que se soma por partido. |

### `gold.mart_concentracao_parlamentar` 🔒

**Grão:** deputado × subcota × fornecedor (competências fechadas).

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `id_deputado` | `INTEGER` | nuDeputadoId do deputado. |
| `num_subcota` | `INTEGER` | Subcota. |
| `descricao_subcota` | `VARCHAR` | Descrição da subcota. |
| `sk_fornecedor` | `VARCHAR` | Fornecedor (dim_fornecedor). |
| `nome_fornecedor` | `VARCHAR` | Nome do fornecedor. |
| `documento_fornecedor` 👤 | `VARCHAR` | CNPJ ou CPF do fornecedor. *(pode ser CPF de pessoa física (fornecedor))* |
| `qtd_lancamentos` | `BIGINT` | Lançamentos do deputado no fornecedor e na subcota. |
| `gasto_fornecedor` | `DECIMAL(38,2)` | Gasto do deputado no fornecedor e na subcota (R$). |
| `gasto_categoria` | `DECIMAL(38,2)` | Gasto do deputado na subcota (R$). |
| `gasto_deputado` | `DECIMAL(38,2)` | Gasto total do deputado na janela (R$). |
| `participacao_na_categoria` | `DOUBLE` | gasto_fornecedor ÷ gasto_categoria. |
| `participacao_no_deputado` | `DOUBLE` | gasto_fornecedor ÷ gasto_deputado. |
| `participacao_categoria_no_deputado` | `DOUBLE` | gasto_categoria ÷ gasto_deputado. |
| `excesso_categoria_vs_uf` | `DECIMAL(38,2)` | Gasto na subcota menos a mediana dos deputados da UF na mesma subcota, contando com zero quem não gastou nela (R$). |

### `gold.mart_desvio_parlamentar` 🔒

**Grão:** um deputado. Ranking do desvio acumulado acima da mediana mensal da UF (competências comparáveis).

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `id_deputado` | `INTEGER` | nuDeputadoId do deputado. |
| `nome_parlamentar` | `VARCHAR` | Nome do deputado (versão mais recente). |
| `sigla_uf` | `VARCHAR` | UF do deputado (versão mais recente). |
| `partido_atual` | `VARCHAR` | Partido da versão mais recente. |
| `trajetoria_partidaria` | `VARCHAR` | Partidos do deputado na 57ª Legislatura, em ordem (ex.: PATRIOTA → PRD). |
| `trocou_de_partido` | `BOOLEAN` | Verdadeiro se teve mais de uma versão na 57ª. |
| `meses_com_gasto` | `BIGINT` | Competências comparáveis com gasto. |
| `gasto_total` | `DECIMAL(38,2)` | Gasto nas competências comparáveis (R$). |
| `gasto_medio_mensal` | `DOUBLE` | Gasto médio por mês com gasto (R$). |
| `mediana_uf_mensal` | `DOUBLE` | Média, nos mesmos meses, da mediana mensal da UF (R$). |
| `desvio_acumulado` | `DECIMAL(38,4)` | Soma mês a mês de (gasto − mediana da UF) (R$). É a medida do ranking. |
| `desvio_relativo` | `DOUBLE` | desvio_acumulado ÷ soma das medianas da UF (ex.: 0,33 = 33% acima). |
| `meses_acima_mediana` | `BIGINT` | Meses em que o gasto passou da mediana da UF. |
| `z_medio` | `DOUBLE` | Média dos z-scores robustos mensais. |
| `hhi_fornecedores` | `DOUBLE` | Concentração em fornecedores (0 a 1; perto de 1 = poucos fornecedores). |
| `posicao_ranking` | `BIGINT` | Posição pelo desvio acumulado (1 = maior desvio). |

### `gold.mart_desvio_partido` 🔒

**Grão:** um partido, pela sigla vigente na data do gasto (SCD2). Inclui o comparativo com o resultado errado da sobrescrita.

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `sigla_partido` | `VARCHAR` | Partido na data do gasto (SCD tipo 2). |
| `qtd_deputados` | `BIGINT` | Deputados com gasto pelo partido na janela. |
| `deputado_meses` | `BIGINT` | Pares deputado × mês com gasto pelo partido. |
| `gasto_total` | `DECIMAL(38,2)` | Gasto pelo partido na janela (R$). |
| `desvio_acumulado` | `DECIMAL(38,4)` | Soma do desvio_alocado (R$). |
| `desvio_medio_por_deputado_mes` | `DOUBLE` | desvio_acumulado ÷ deputado_meses (R$). É a medida do gráfico de partidos. |
| `gasto_total_se_sobrescrito` | `DECIMAL(38,2)` | Gasto que o partido teria se o partido fosse sobrescrito pelo atual (SCD tipo 1) (R$). |
| `desvio_acumulado_se_sobrescrito` | `DECIMAL(38,4)` | Desvio que o partido teria com a sobrescrita (R$). |
| `erro_gasto_se_sobrescrito` | `DECIMAL(38,2)` | Diferença entre o gasto com sobrescrita e o correto (R$): o erro que o SCD2 evita. |

### `gold.mart_freshness_gold` 🔒

**Grão:** uma linha por tabela de consumo da Gold. Freshness medida no build: horas entre a ingestão mais recente dos CSVs e a construção da Gold, comparadas com o SLA declarado (var sla_horas_gold). O painel recalcula a idade no momento da leitura.

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `tabela_consumo` | `VARCHAR` | Tabela de consumo da Gold a que a medida se refere. |
| `ingerido_em_mais_recente` | `TIMESTAMP WITH TIME ZONE` | Ingestão mais recente da Bronze usada no build. |
| `ingerido_em_mais_antigo` | `TIMESTAMP WITH TIME ZONE` | Ingestão mais antiga entre as partições usadas. |
| `gold_construida_em` | `TIMESTAMP WITH TIME ZONE` | Momento em que a Gold foi construída. |
| `idade_horas_no_build` | `DOUBLE` | Horas entre a ingestão mais recente e a construção da Gold. |
| `sla_horas` | `INTEGER` | SLA declarado (26 h). |
| `dentro_do_sla` | `BOOLEAN` | Verdadeiro se idade_horas_no_build ≤ sla_horas. |
| `ultima_competencia_publicada` | `DATE` | Competência mais recente nos CSVs. |
| `ultima_competencia_fechada` | `DATE` | Competência mais recente com 4 meses de maturação. |

## Semântica

### `auditoria.resultado_build`

Uma linha por `dbt build` ou `dbt test`, com a contagem dos testes por resultado. Criada no on-run-start e preenchida no on-run-end (macros/registra_build.sql).

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `invocation_id` | `VARCHAR` | Identificador da execução do dbt. |
| `comando` | `VARCHAR` | Comando do dbt (build ou test). |
| `executado_em` | `TIMESTAMP WITH TIME ZONE` | Fim da execução. |
| `testes_total` | `INTEGER` | Testes executados. |
| `testes_aprovados` | `INTEGER` | Testes aprovados. |
| `testes_aviso` | `INTEGER` | Testes com severidade warn que acusaram algo. |
| `testes_reprovados` | `INTEGER` | Testes reprovados ou com erro. |
| `modelos_com_erro` | `INTEGER` | Modelos ou seeds que falharam. |

### `semantico.met_categoria_parlamentar` 🔒

**Grão:** deputado × subcota. Métricas da categoria que gera o desvio (3ª parte da pergunta).

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `id_deputado` | `INTEGER` | nuDeputadoId do deputado. |
| `num_subcota` | `INTEGER` | Código da subcota (categoria de despesa). |
| `descricao_subcota` | `VARCHAR` | Descrição da subcota. |
| `gasto_categoria` | `DECIMAL(38,2)` | Gasto do deputado na subcota, na janela comparável. |
| `excesso_categoria_vs_uf` | `DECIMAL(38,2)` | Quanto o deputado gastou na subcota acima da mediana dos deputados da UF nela. |
| `participacao_categoria_no_deputado` | `DOUBLE` | Peso da subcota no gasto total do deputado. |
| `posicao_excesso` | `BIGINT` | Posição da subcota pelo excesso, dentro do deputado (1 = a que mais explica o desvio). |

### `semantico.met_contexto` 🔒

**Grão:** uma linha. Contexto das métricas: janela comparável, atualização, freshness e a ruptura que encerra a janela. View: a idade dos dados é calculada na hora da leitura.

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `janela_inicio` | `DATE` | Primeira competência comparável. |
| `janela_fim` | `DATE` | Última competência comparável. |
| `meses_janela` | `BIGINT` | Meses na janela comparável. |
| `ultima_competencia_publicada` | `DATE` | Competência mais recente nos CSVs. |
| `atualizado_em` | `TIMESTAMP WITH TIME ZONE` | Ingestão mais recente dos CSVs no fato. |
| `sla_horas` | `INTEGER` | SLA declarado da Gold (26 h). |
| `idade_horas` | `DOUBLE` | Horas desde a ingestão mais recente, medidas na leitura. |
| `dentro_do_sla` | `BOOLEAN` | Verdadeiro se idade_horas ≤ sla_horas. |
| `erro_total_sobrescrita` | `DECIMAL(38,2)` | Gasto que iria para o partido errado se o partido fosse sobrescrito pelo atual. |
| `min_deputados_partido` | `INTEGER` | Mínimo de deputados para o partido entrar no ranking (var min_deputados_partido). |
| `ruptura_num_subcota` | `INTEGER` | Subcota da ruptura que encerra a janela. |
| `ruptura_inicio` | `DATE` | Primeira competência afetada pela ruptura. |
| `ruptura_descricao` | `VARCHAR` | O que mudou na publicação. |
| `ruptura_evidencia` | `VARCHAR` | Evidência medida da ruptura. |

### `semantico.met_fornecedor_parlamentar` 🔒

**Grão:** deputado × fornecedor (todas as subcotas somadas). Métricas de concentração em fornecedores (3ª parte da pergunta).

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `id_deputado` | `INTEGER` | nuDeputadoId do deputado. |
| `sk_fornecedor` | `VARCHAR` | Fornecedor (dim_fornecedor). |
| `nome_fornecedor` 👤 | `VARCHAR` | Nome do fornecedor; CPF dentro do nome (razão social de MEI) mascarado. *(CPF de pessoa física mascarado: `***.456.789-**`)* |
| `documento_fornecedor` 👤 | `VARCHAR` | CNPJ completo, ou CPF mascarado (***.456.789-**) para pessoa física (LGPD). *(CPF de pessoa física mascarado: `***.456.789-**`)* |
| `gasto_fornecedor` | `DECIMAL(38,2)` | Gasto do deputado no fornecedor, na janela comparável. |
| `participacao_no_deputado` | `DOUBLE` | Peso do fornecedor no gasto total do deputado. |
| `qtd_lancamentos` | `BIGINT` | Lançamentos do deputado no fornecedor. |
| `posicao_gasto` | `BIGINT` | Posição do fornecedor pelo gasto, dentro do deputado (1 = o maior). |
| `participacao_acumulada` | `DOUBLE` | Quanto este fornecedor e os maiores que ele somam do gasto do deputado (na posição 10, os 10 maiores). |

### `semantico.met_lancamento_parlamentar` 🔒

**Grão:** um lançamento publicado, no recorte do ranking. Liga o desvio do painel ao documento na Câmara (3ª parte da pergunta, até a fonte). CPF de pessoa física mascarado; sem passageiro e sem trecho.

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `id_lancamento` | `VARCHAR` | Lançamento (fct_lancamento_ceap). |
| `id_deputado` | `INTEGER` | nuDeputadoId do deputado. |
| `num_subcota` | `INTEGER` | Código da subcota (categoria de despesa). |
| `descricao_subcota` | `VARCHAR` | Descrição da subcota. |
| `competencia` | `DATE` | Mês de competência. |
| `data_emissao` | `DATE` | Data de emissão do documento (vazia em telefonia e bilhetes). |
| `sk_fornecedor` | `VARCHAR` | Fornecedor (dim_fornecedor). |
| `nome_fornecedor` 👤 | `VARCHAR` | Nome do fornecedor; CPF dentro do nome mascarado. *(CPF de pessoa física mascarado: `***.456.789-**`)* |
| `documento_fornecedor` 👤 | `VARCHAR` | CNPJ completo, ou CPF mascarado (***.456.789-**). *(CPF de pessoa física mascarado: `***.456.789-**`)* |
| `tipo_documento` | `VARCHAR` | Tipo do documento: nota fiscal, nota fiscal eletrônica, recibo, despesa no exterior ou outro. |
| `valor_liquido` | `DECIMAL(14,2)` | Valor debitado da cota no lançamento (negativo em créditos). |
| `url_documento` | `VARCHAR` | Link para o documento digitalizado no site da Câmara. Vazio quando a Câmara não publicou ou quando o fornecedor é pessoa física (o documento traz o CPF completo). |
| `tem_documento_publicado` | `BOOLEAN` | Verdadeiro se a Câmara publicou o link do documento (mesmo que ele não seja exibido). |
| `link_omitido_lgpd` | `BOOLEAN` | Verdadeiro se a Câmara publicou o documento, mas o link não é exibido porque o fornecedor é pessoa física. |
| `posicao_valor` | `BIGINT` | Posição do lançamento pelo valor, dentro do deputado e da subcota (1 = o maior). |

### `semantico.met_parlamentar` 🔒

**Grão:** um deputado da 57ª Legislatura (sem lideranças), nas competências comparáveis. Métricas do ranking de desvio acima da mediana mensal da UF (1ª parte da pergunta de gestão).

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `id_deputado` | `INTEGER` | nuDeputadoId do deputado. |
| `nome_parlamentar` | `VARCHAR` | Nome do deputado (versão mais recente). |
| `sigla_uf` | `VARCHAR` | UF do deputado (versão mais recente). |
| `partido_atual` | `VARCHAR` | Partido da versão mais recente. |
| `rotulo` | `VARCHAR` | Rótulo de exibição: Nome (PARTIDO-UF). |
| `trajetoria_partidaria` | `VARCHAR` | Partidos do deputado na 57ª, em ordem (ex.: PATRIOTA → PRD). |
| `trocou_de_partido` | `BOOLEAN` | Verdadeiro se teve mais de uma versão na 57ª. |
| `meses_com_gasto` | `BIGINT` | Competências comparáveis em que o deputado teve gasto. |
| `gasto_total` | `DECIMAL(38,2)` | Gasto líquido do deputado na janela comparável. |
| `gasto_medio_mensal` | `DOUBLE` | Gasto médio do deputado por mês com gasto. |
| `mediana_uf_mensal` | `DOUBLE` | Referência da comparação. Média, nos meses do deputado, da mediana mensal da UF. |
| `desvio_acumulado` | `DECIMAL(38,4)` | Quanto o deputado gastou acima da mediana da UF, somado mês a mês. É a medida do ranking. |
| `desvio_relativo` | `DOUBLE` | Desvio acumulado em proporção da referência (0,33 = 33% acima da mediana da UF). |
| `meses_acima_mediana` | `BIGINT` | Meses em que o gasto do deputado passou da mediana da UF. |
| `proporcao_meses_acima` | `DOUBLE` | Fração dos meses com gasto em que o deputado ficou acima da mediana da UF. Perto de 1, o desvio é constante; baixa com desvio alto, ele vem de poucos meses fora da curva. |
| `z_medio` | `DOUBLE` | O quanto o deputado foge do padrão da UF, independentemente do tamanho da UF. |
| `hhi_fornecedores` | `DOUBLE` | Concentração do gasto em fornecedores (0 a 1; perto de 1 = poucos fornecedores). |
| `posicao_ranking` | `BIGINT` | Posição pelo desvio acumulado (1 = maior desvio). |
| `em_alerta` | `BOOLEAN` | Verdadeiro para o topo do ranking (var alerta_top_n = 15). É o top 15 do painel e o que o ETL reverso publica na fila de auditoria. |

### `semantico.met_parlamentar_mes` 🔒

**Grão:** deputado × competência comparável. Série mensal do parlamentar contra a mediana da UF: mostra se o desvio é constante ou vem de poucos meses (1ª parte da pergunta, no tempo).

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `id_deputado` | `INTEGER` | nuDeputadoId do deputado. |
| `competencia` | `DATE` | Mês de competência (primeiro dia). |
| `sigla_uf` | `VARCHAR` | UF do deputado no mês. |
| `partidos_no_mes` | `VARCHAR` | Partido no mês, pela data do gasto; dois em mês de troca (ex.: PATRIOTA → PRD). |
| `gasto_mes` | `DECIMAL(38,2)` | Gasto líquido do deputado no mês. |
| `mediana_uf_mes` | `DECIMAL(18,4)` | Mediana do gasto mensal dos deputados da mesma UF com gasto no mês. |
| `qtd_deputados_uf_mes` | `BIGINT` | Deputados da UF com gasto no mês (base da mediana). |
| `desvio_mes` | `DECIMAL(38,4)` | Quanto o deputado gastou acima (ou abaixo) da mediana da UF no mês. Somado, dá desvio_acumulado. |
| `z_mes` | `DOUBLE` | Desvio do mês em z robusto, comparável entre UFs. |
| `acima_mediana` | `BOOLEAN` | Verdadeiro se o gasto do mês passou da mediana da UF. |
| `trocou_de_partido_no_mes` | `BOOLEAN` | Verdadeiro no mês em que o partido muda (dentro do mês ou em relação ao mês anterior com gasto). |

### `semantico.met_partido` 🔒

**Grão:** um partido, pela sigla vigente na data do gasto (SCD tipo 2). Métricas do ranking de partidos (2ª parte da pergunta) e do erro que a sobrescrita do partido causaria.

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `sigla_partido` | `VARCHAR` | Partido na data do gasto (SCD tipo 2). |
| `qtd_deputados` | `BIGINT` | Deputados com gasto pelo partido na janela. |
| `deputado_meses` | `BIGINT` | Pares deputado × mês com gasto pelo partido. |
| `gasto_total` | `DECIMAL(38,2)` | Gasto pelo partido na janela comparável. |
| `desvio_acumulado` | `DECIMAL(38,4)` | Desvio acima da mediana da UF atribuído ao partido. |
| `desvio_medio_por_deputado_mes` | `DOUBLE` | Desvio médio por deputado-mês. É a medida do ranking de partidos. |
| `entra_no_ranking` | `BOOLEAN` | Verdadeiro se o partido tem deputados suficientes para o ranking (var min_deputados_partido = 5). |
| `posicao_ranking` | `BIGINT` | Posição pelo desvio por deputado-mês entre os partidos que entram no ranking (nulo para os demais). |
| `gasto_total_se_sobrescrito` | `DECIMAL(38,2)` | Gasto que o partido teria se todo o histórico do deputado fosse do partido atual (SCD tipo 1). |
| `erro_gasto_se_sobrescrito` | `DECIMAL(38,2)` | Erro que o SCD tipo 2 evita no partido. |

### `semantico.met_qualidade_build` 🔒

**Grão:** uma linha, o build mais recente. Resultado dos testes do dbt que produziu os dados em consumo; é o selo de qualidade do painel.

| Coluna | Tipo | Descrição |
| :--- | :--- | :--- |
| `executado_em` | `TIMESTAMP WITH TIME ZONE` | Fim do build. |
| `comando` | `VARCHAR` | Comando do dbt (build ou test). |
| `testes_total` | `INTEGER` | Testes executados no build. |
| `testes_aprovados` | `INTEGER` | Testes aprovados. |
| `testes_aviso` | `INTEGER` | Testes com severidade warn que acusaram algo (não barram o build). |
| `testes_reprovados` | `INTEGER` | Testes reprovados ou com erro. |
| `modelos_com_erro` | `INTEGER` | Modelos ou seeds que falharam no build. |
| `build_sem_falhas` | `BOOLEAN` | Verdadeiro se nenhum teste reprovou e nenhum modelo falhou. |
