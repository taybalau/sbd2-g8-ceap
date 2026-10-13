---
hide:
  - navigation
---

# Plataforma de Dados da Cota Parlamentar (CEAP)

**57ª Legislatura (2023–2026)** · Sistemas de Banco de Dados 2 (2026/2) · Universidade de Brasília (UnB) · **Squad G8**

A **Cota para o Exercício da Atividade Parlamentar (CEAP)** custeia as despesas ligadas ao mandato dos deputados federais: passagens aéreas, aluguel de escritórios, combustíveis, consultorias, segurança, entre outras. A Câmara dos Deputados publica esses gastos em arquivos abertos anuais.

Este projeto transforma esses arquivos em uma **plataforma de dados** que sobe do zero com um único comando e responde a uma pergunta de gestão bem definida:

- **E1:** banco transacional (OLTP) PostgreSQL, normalizado e populado com os dados reais;
- **E2:** camada analítica em formato aberto (Delta Lake), alimentada por carga em lote e por captura de mudanças (CDC), e enriquecida com a cadeia societária dos fornecedores.

## Pergunta de gestão

!!! question "Pergunta central"
    **Quais parlamentares e partidos da 57ª Legislatura (2023–2026) apresentam maior desvio de gastos acima da média mensal da Cota Parlamentar (CEAP), e quais categorias e fornecedores concentram esses recursos?**

Ela é apoiada por [seis perguntas complementares](consultas.md), como o custo médio mensal por deputado e o ranking de fornecedores.

Na E2, a pergunta ganhou uma dimensão de [auditoria societária](enriquecimento.md):

!!! question "Pergunta ampliada (E2)"
    **Quais despesas da CEAP pagas a múltiplos CNPJs aparentemente concorrentes concentram recursos no mesmo Beneficiário Final (mesmo CPF ou grupo econômico controlador)?**

## A plataforma em números

| Métrica | Valor |
| :--- | ---: |
| Registros de despesa (`despesa_ceap`) | **785.754** |
| Volume financeiro (soma de `valor_liquido`) | **R$ 869.398.245,27** |
| Parlamentares e lideranças | 874 |
| Fornecedores distintos | 55.882 |
| Categorias de despesa (subcotas) | 21 |
| Volume bruto dos CSVs | ~265 MB |
| Tempo de carga completa (4 anos) | ~97,4 s |
| Latência da consulta analítica principal no OLTP | ~112 ms |

Linhas por ano: 2023 → 232.747 · 2024 → 232.918 · 2025 → 209.080 · 2026 → 111.009 (*2026 é parcial*).

Na camada analítica da E2, segundo o [ADR-0002](adr/0002-mecanismo-ingestao-e-formato-aberto.md):

| Métrica | Valor |
| :--- | ---: |
| Carga em lote para o Delta Lake | 34,2 s |
| Tamanho da camada analítica (Parquet) | 64,8 MB |
| Agregação analítica no DuckDB | 18 ms |
| Latência do CDC no teste de mutação | 380 ms |

## Comece por aqui

<div class="grid cards" markdown>

-   :material-rocket-launch: **[Como executar](como-executar.md)**

    ---

    Suba o PostgreSQL e carregue os dados reais com `docker compose up --build`.

-   :material-sitemap: **[Arquitetura](arquitetura.md)**

    ---

    Containers, fluxo dos dados e decisões de infraestrutura.

-   :material-database: **[Modelo de dados](modelo-de-dados.md)**

    ---

    Diagrama ER, tabelas, índices e os três carimbos de tempo.

-   :material-pipe: **[Carga no OLTP](pipeline.md)**

    ---

    Download, migrações, staging `UNLOGGED` + `COPY` e normalização.

-   :material-lake: **[Lakehouse e CDC](lakehouse.md)**

    ---

    Delta Lake, carga em lote idempotente, `MERGE` de mudanças e testes de aceite.

-   :material-account-network: **[Enriquecimento societário](enriquecimento.md)**

    ---

    Cadeia de sócios até o beneficiário final (UBO).

-   :material-chart-bar: **[Perguntas de gestão](consultas.md)**

    ---

    As consultas SQL que respondem às perguntas do projeto.

-   :material-scale-balance: **Decisões (ADR)**

    ---

    [0001 · Modelagem *insert-only*](adr/0001-modelagem-transacional-insert-only-ceap.md) ·
    [0002 · Ingestão e formato aberto](adr/0002-mecanismo-ingestao-e-formato-aberto.md) ·
    [0003 · Beneficiário final](adr/0003-resolucao-grafo-societario-beneficiario-final.md)

</div>

## Entregas

| Entrega | Escopo | Status |
| :--- | :--- | :--- |
| **E1** | Fonte transacional (OLTP) em PostgreSQL 16, ingestão reprodutível | :material-check-circle: Entregue em 28/09/2026 (tag `e1`) |
| **E2** | Ingestão em lote, CDC, lakehouse Delta Lake e enriquecimento societário | :material-check-circle: Entregue em 13/10/2026 |
| E3 | Transformações | Planejada |
| E4 | Ainda não detalhada | Planejada |

Os detalhes da E1 estão nas [Release Notes](release-notes.md); os da E2, no [documento técnico da E2](PIPELINE_E2.md).

## Tecnologias

- **PostgreSQL 16** (Alpine), em Docker
- **Python 3.11** (`psycopg2`, `requests`) para migrações e ingestão
- **Delta Lake** (`deltalake`, `pyarrow`) com Parquet para a camada analítica
- **DuckDB** para consultas diretas sobre o lakehouse
- **Docker Compose** para subir tudo com um comando
- Dados abertos da [Câmara dos Deputados](https://www.camara.leg.br/transparencia/gastos-parlamentares)

## Squad G8

| Integrante |
| :--- |
| Filipe Carvalho |
| Taynara Vitorino |
| Gabriel Esteves |
| Maria Clara Alves |
| Kaio Macedo |
| Amanda Gonçalves |
