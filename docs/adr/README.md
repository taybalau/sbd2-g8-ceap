# Portfólio de decisões (ADRs)

Cada decisão de arquitetura da plataforma está registrada num ADR (*Architecture Decision Record*)
no formato de Nygard: contexto, alternativas (com a opção nula), medição, decisão, consequências e
**gatilho de revisão**. O gatilho é a condição medível que obriga a reabrir a decisão.

Esta página reúne os ADRs e mostra, para cada um, se o gatilho **disparou** ao longo do semestre.
A conferência foi feita em **2026-11-24**, no fechamento da E4, com a plataforma subida do zero.
Os ADRs ficam como foram aceitos; o que mudou desde então está registrado aqui.

## Visão geral

| ADR | Entrega | Decisão | Status | Gatilho disparou? |
| :--- | :---: | :--- | :--- | :--- |
| [0001](0001-modelagem-transacional-insert-only-ceap.md) | E1 | OLTP relacional normalizado e *insert-only* no PostgreSQL | aceito | não |
| [0002](0002-mecanismo-ingestao-e-formato-aberto.md) | E2 | Lote idempotente + CDC pelo WAL, gravando em Delta Lake | aceito | não |
| [0003](0003-resolucao-grafo-societario-beneficiario-final.md) | E2 | Beneficiário final (UBO) resolvido em lote sobre o Delta Lake | aceito | não |
| [0004](0004-avaliacao-etl-relacional-postgres-vs-lakehouse-direto.md) | E3 | Transformação direto no lakehouse, sem staging no PostgreSQL | aceito | não, mas a E4 mudou o papel do PostgreSQL ([ver abaixo](#adr-0004-o-postgresql-voltou-ao-fluxo-como-destino)) |
| [0005](0005-modelagem-dimensional-granularidade-scd-ceap.md) | E3 | Esquema estrela, fato atômico e SCD tipo 2 | aceito, revisto em 2026-11-03 | não (a revisão veio da implementação, não do gatilho) |
| [0006](0006-orquestracao-falha-controlada-e-backfill.md) | E3 | Dagster com retry, falha controlada e backfill por ano | aceito | não |
| [0007](0007-ferramenta-do-painel-analitico.md) | E3 | Painel em Streamlit em vez de Metabase ou Superset | aceito | **sim, e a decisão não foi revista** ([ver abaixo](#adr-0007-o-gatilho-de-acesso-por-perfil-disparou)) |
| [0008](0008-disponibilizacao-camada-semantica-etl-reverso.md) | E4 | Camada semântica no dbt, leitura no warehouse e ETL reverso por push para o PostgreSQL | aceito | — (novo) |

## Gatilhos, um por um

Para cada ADR: o gatilho como foi escrito, o valor medido hoje e a conclusão.

### ADR-0001 · OLTP *insert-only*

| Gatilho | Limiar | Hoje | Disparou? |
| :--- | ---: | ---: | :---: |
| Volume mensal de notas fiscais | 200.000 notas/mês | máximo de 23.430 (média de 17.465 em 45 meses) | não |
| Latência p95 da agregação analítica no OLTP | 2,0 s | 378 ms (mediana de 262 ms) | não |

Medido com a consulta de referência do próprio ADR, 20 execuções sobre 785.929 despesas, com o
pipeline da E3 rodando ao mesmo tempo. O mês mais cheio está a cerca de 12% do limiar de volume.

### ADR-0002 · Lote + CDC em Delta Lake

| Gatilho | Limiar | Hoje | Disparou? |
| :--- | ---: | ---: | :---: |
| Taxa de mutações contínuas | 5.000 eventos/s | a fonte é um CSV anual regerado; a carga diária é de um ano por vez, não um fluxo contínuo | não |
| Exigência de catálogo em nuvem (AWS Glue, Snowflake) | ocorrer | não ocorreu: tudo roda local em Docker | não |

O segundo gatilho não tem métrica. Uma versão medível seria: *"revisar se um consumidor externo
precisar ler o lakehouse por um catálogo (Glue, Unity, Polaris) em vez do arquivo"*.

### ADR-0003 · Resolução de UBO

| Gatilho | Limiar | Hoje | Disparou? |
| :--- | ---: | ---: | :---: |
| Fornecedores monitorados com cadeias profundas | 500.000 entidades com mais de 6 níveis | 55.894 fornecedores distintos | não |
| Mudança de layout dos Dados Abertos do CNPJ | ocorrer | não ocorreu no semestre | não |

### ADR-0004 · Lakehouse direto, sem staging no PostgreSQL

| Gatilho | Limiar | Hoje | Disparou? |
| :--- | ---: | ---: | :---: |
| Aplicação CRUD multiusuário com bloqueio por linha | < 50 ms com concorrência pessimista | a fila do auditor (E4) tem escrita de usuários, mas é *insert-only*: não há `UPDATE` nem bloqueio por linha | não |
| Catálogo distribuído externo | ocorrer | não ocorreu | não |

Os dois gatilhos são qualitativos. Uma versão medível do primeiro: *"revisar se mais de um
usuário precisar alterar o mesmo registro, ou se a escrita do usuário exigir latência p95 abaixo
de 50 ms"*.

#### ADR-0004: o PostgreSQL voltou ao fluxo como destino

O gatilho não disparou, mas a seção "Papel do PostgreSQL a partir da E3" do ADR-0004 ficou
incompleta. Na E3 o PostgreSQL deixou de ser **intermediário** da transformação, e isso continua
valendo. Na E4 ele voltou como **destino**: o ETL reverso publica a fila de auditoria em
`alerta.desvio_parlamentar` e o auditor grava as decisões em `alerta.tratamento`. A justificativa
está no [ADR-0008](0008-disponibilizacao-camada-semantica-etl-reverso.md): o auditor precisa
escrever, e o lakehouse não é lugar para escrita de usuário.

### ADR-0005 · Esquema estrela, fato atômico e SCD tipo 2

| Gatilho | Limiar | Hoje | Disparou? |
| :--- | ---: | ---: | :---: |
| Fim da exigência de nota fiscal individual na CEAP | ocorrer | não ocorreu | não |
| Fontes externas integradas com esquema instável | 15 bases | 3 fontes: CSV da CEAP, API de histórico dos deputados e CNPJ da Receita | não |

A decisão foi **revista em 2026-11-03** (seção 9 do ADR) e em 2026-11-19 (média trocada pela
mediana), mas por evidência da implementação, não por gatilho. Isso mostra uma limitação dos
gatilhos originais: nenhum deles cobria "a premissa sobre os dados estar errada", que foi o que
de fato aconteceu (o grão e a fonte do SCD).

### ADR-0006 · Dagster com retry e backfill por ano

| Gatilho | Limiar | Hoje | Disparou? |
| :--- | ---: | ---: | :---: |
| A Câmara publicar a CEAP por mês | ocorrer | continua publicando um arquivo por ano | não |
| Mais de uma fonte com execução em tempo real | 2 fontes | nenhuma: todas as execuções são diárias ou sob demanda | não |

O gatilho não tem limiar numérico de operação. Uma versão medível: *"revisar se um run do job
`transformacao` passar de 30 minutos, ou se for preciso atualizar a Gold mais de uma vez por
dia"*. A E4 acrescentou um terceiro job (`etl_reverso`) e um asset no fim da `transformacao`,
dentro do mesmo desenho do ADR.

### ADR-0007 · Painel em Streamlit

| Gatilho | Limiar | Hoje | Disparou? |
| :--- | ---: | ---: | :---: |
| Pedidos de visões novas de fora da Squad | mais de 3 por mês | zero | não |
| Número de visões do painel | mais de 8 | 3 | não |
| Necessidade de **acesso restrito por perfil**, "por exemplo dados não públicos de fornecedores" | ocorrer | **ocorreu**: a [análise de LGPD](../lgpd.md) mostrou que o painel exibe o CPF completo de fornecedores pessoa física | **sim** |

#### ADR-0007: o gatilho de acesso por perfil disparou

**O que aconteceu.** A análise de LGPD da E4 encontrou dois fatos que são exatamente a condição do
terceiro gatilho:

1. a tabela dos 10 maiores fornecedores do painel mostra `documento_fornecedor`, que para pessoa
   física é o **CPF completo**. Na Gold que o painel lê há **314 CPFs completos** de fornecedores
   pessoa física (conferido em 2026-11-24; comando no fim desta página);
2. o painel monta o `./lakehouse` inteiro. Ler só a Gold é convenção do `painel/app.py`, não
   restrição, e o Streamlit não tem controle de acesso por usuário.

Ou seja, surgiu dado que não deve ser visto por todos os leitores, e o ADR dizia que isso
levaria à migração para o Metabase.

**O que foi feito.** A decisão **não foi revista**. O painel continua em Streamlit e o ADR-0007
continua "aceito". O registro honesto é este: o gatilho disparou na E4, perto do prazo final, e
ninguém reabriu o ADR-0007 quando a análise de LGPD apontou o problema. O ADR previa a troca de
ferramenta, e essa troca não foi feita nem descartada formalmente.

**O que a análise de LGPD propõe no lugar.** Em vez de dar acesso por perfil no painel, tirar o
dado pessoal do que o painel lê: uma zona de consumo (`ceap_painel.duckdb`) já recortada, com CPF
mascarado e pseudônimo, e o lakehouse completo só na zona restrita. Se isso for implementado, a
condição do gatilho deixa de existir (não haverá mais dado restrito no painel) e o Streamlit volta
a se justificar. Até lá, o gatilho está disparado e em aberto.

**Próximo passo.** Revisar o ADR-0007 quando a zona de consumo for implementada: ou registrar que
o recorte dos dados resolveu a condição, ou abrir um ADR que o substitua.

Este caso vai para a retrospectiva da E4 no diário de bordo (issue #12).

**Atualização de 26/11/2026.** A primeira metade da condição foi tratada na exibição: o painel lê a
camada semântica, que agora entrega o CPF mascarado (`***.456.789-**`), e um teste barra o build se
um CPF completo voltar. A segunda metade continua: o painel monta o lakehouse inteiro, e o arquivo
ainda tem o CPF completo na Gold. Sem a zona de consumo, o gatilho segue disparado e a decisão segue
sem revisão.

### ADR-0008 · Disponibilização do dado

ADR novo da E4. Os gatilhos estão na [seção 6 do ADR](0008-disponibilizacao-camada-semantica-etl-reverso.md#6-gatilho-de-revisão).

## Reconferência de 26/11/2026: o painel depois da E4

O painel ganhou visões e a camada semântica ganhou 3 views ([E4, seção 1.6](../e4.md#16-depois-da-entrega-o-painel-mostra-o-levantamento)).
Dois gatilhos mudaram de valor:

| ADR | Gatilho | Limiar | Na E4 | Hoje | Disparou? |
| :--- | :--- | ---: | ---: | ---: | :---: |
| 0007 | Número de visões do painel (visão = bloco da pergunta) | mais de 8 | 3 | **3** (11 gráficos e tabelas) | não |
| 0008 | Métricas na camada semântica | mais de 50 | 32 | **50** | não, mas está no limite |
| 0008 | Leitura do painel pela camada semântica (p90) | mais de 1 s | 251 ms | 254 ms (7 views; [evidência](../evidencias/painel_leitura_semantica.json)) | não |

**ADR-0007, visões.** O ADR chama de visões os três blocos fixos (parlamentares, partidos e
concentração) e diz que o gatilho existe porque, acima de 8, "o código ficaria mais caro de manter do
que a configuração". Por bloco, continuam 3. Por gráfico ou tabela, são 11: barras do ranking, tabela
dos 15 em alerta, dispersão "constante ou pontual", barras de partidos, tabela do erro da sobrescrita,
linha mês a mês, posição na UF, barras de categorias, fornecedores, lançamentos e a tabela completa do
ranking. O código do painel passou de 193 para 420 linhas.

**Decisão (26/11/2026):** visão é um **bloco do painel**, ou seja, uma parte da pergunta de gestão, como
no próprio ADR ("três visões fixas"). O gatilho **não disparou**: os 11 gráficos e tabelas detalham as
mesmas 3 partes da pergunta, e o painel continua sendo código simples, sem a configuração por
pergunta que justificaria o Metabase. Um bloco novo (uma 4ª parte da pergunta, ou visões pedidas de
fora da Squad) conta para o limite. O que continua disparado no ADR-0007 é o gatilho de acesso por
perfil ([acima](#adr-0007-o-gatilho-de-acesso-por-perfil-disparou)).

**ADR-0008, métricas.** O limite de 50 fica como está. Mudá-lo justamente quando ele está para ser
atingido tiraria o sentido do gatilho. A próxima métrica passa do limiar, e aí a Squad prototipa o dbt
Semantic Layer, como prevê a alternativa 2.1-D do ADR.

## Como reconferir

Com a plataforma no ar (`docker compose up --build -d` e `docker compose wait e3-pipeline`):

```bash
# ADR-0001: notas por mês (máximo e média)
docker compose exec -T db psql -U postgres -d ceap_oltp -c "
  select max(n) as maximo_mes, round(avg(n)) as media_mes, count(*) as meses
  from (select ano_competencia, mes_competencia, count(*) n from despesa_ceap group by 1, 2) t"

# ADR-0001: p95 da consulta de referência do ADR (rodar 20 vezes e tomar o 19º menor tempo)
for i in $(seq 1 20); do
  docker compose exec -T db psql -U postgres -d ceap_oltp -Atc "EXPLAIN (ANALYZE, FORMAT JSON)
    SELECT p.nome_parlamentar, d.sigla_partido_emissao, COUNT(*), SUM(d.valor_liquido)
    FROM despesa_ceap d JOIN parlamentar p ON p.id_deputado = d.id_deputado
    GROUP BY p.nome_parlamentar, d.sigla_partido_emissao ORDER BY SUM(d.valor_liquido) DESC LIMIT 10" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['Execution Time'])"
done | sort -n

# ADR-0003: fornecedores distintos
docker compose exec -T db psql -U postgres -d ceap_oltp -c "select count(*) from fornecedor"

# ADR-0007: CPF completo de fornecedor pessoa física na Gold que o painel lê
docker compose run --rm --no-deps e3-pipeline python -c "
import duckdb; c = duckdb.connect('lakehouse/ceap.duckdb', read_only=True)
print(c.execute('''select count(distinct documento_fornecedor) from gold.mart_concentracao_parlamentar
                   where length(regexp_replace(documento_fornecedor, '[^0-9]', '', 'g')) = 11''').fetchone()[0])"
```
