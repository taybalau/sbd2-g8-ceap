# Diário de Bordo — Semana 10

- **Data:** 29/10/2026 a 03/11/2026 (fechamento da Entrega E3 em 03/11)
- **Participantes:** Filipe Carvalho, Taynara Vitorino, Gabriel Esteves, Maria Clara Alves, Kaio Macedo, Amanda Gonçalves (Squad G8)

## O que foi medido
- **Decisões de arquitetura (29/10):** [`ADR-0004`](../adr/0004-avaliacao-etl-relacional-postgres-vs-lakehouse-direto.md) (E3 direto no Lakehouse, com dbt-duckdb) e [`ADR-0005`](../adr/0005-modelagem-dimensional-granularidade-scd-ceap.md) (esquema estrela, grão do lançamento e histórico partidário).
- **Implementação da E3** em `dbt_ceap/`, `orquestracao/`, `ingestao/` e `painel/`: Bronze com 785.929 linhas, 186 deputados com troca de partido no histórico oficial (contra 92 visíveis no CSV) e 173.413 lançamentos (22%) com partido sobrescrito pela fonte. Detalhes em [E3](../e3.md) e [Erros tratados](../e3-erros-tratados.md).
- **Falhas provocadas de propósito** (`orquestracao/demo_falhas.py`): retry absorvendo duas falhas transitórias, fonte da Câmara fora com Bronze e Gold intactas, API de histórico fora com dbt impedido de iniciar e dado sujo reprovando os testes e pulando os quatro modelos Gold.
- **Backfill pelo Dagster** (`orquestracao/backfill_dagster.py`): as partições 2023 e 2024 foram executadas uma por vez; o sensor disparou a transformação após cada ingestão bem-sucedida, as contagens por ano permaneceram iguais e o hash da Gold não mudou. Evidência em `orquestracao/evidencias/backfill_dagster.json`.
- **Consulta otimizada no PostgreSQL** ([`docs/explain/`](../explain/README.md)): o desvio da pergunta de gestão caiu de ~209 ms para ~33 ms e de 21.428 para 206 páginas lidas com o gasto mensal pré-agregado. Um índice de cobertura reduziu páginas em 82%, mas não alterou o tempo.
- **Freshness e SLA:** Gold publicada até 26 h após a ingestão; `assert_gold_dentro_do_sla` reprovou quando o SLA foi forçado a 0 h.
- **Subida do zero** em cópia limpa do repositório: a plataforma completa sobe com `docker compose up --build`.

## O que surpreendeu
- O CSV da Câmara reescreve o partido dos lançamentos com o partido atual do deputado. Por isso, o SCD usa o histórico oficial da API.
- Os dados mudaram entre downloads: em 03/11 surgiu a subcota 996 (passagem aérea em missão oficial, apenas créditos), e o teste de classificação barrou a Gold até seu registro. Também foi observada a queda da subcota de divulgação em jun/2026 (12% da mediana), provavelmente associada à vedação de divulgação em ano eleitoral.
- Os 175 lançamentos de diferença entre a E1 e a E3 não eram perda na carga: o CSV anual muda conforme a data do download.
- A primeira revisão mostrou que o `docker compose` terminava com sucesso mesmo sem Gold e que a E3 não esperava o download dos CSVs. A subida do zero em cópia limpa revelou ambos os problemas.

## O que foi decidido
- Manter o painel em Streamlit, com justificativa e medições no [`ADR-0007`](../adr/0007-ferramenta-do-painel-analitico.md).
- Registrar no seed `ruptura_publicacao.csv` cada quebra investigada; uma nova quebra reprova o build até ser analisada.
- Aprovar os ADRs 0005 (revisão), 0006 e 0007 após revisar as evidências e a implementação.
- Registrar a revisão entre pares, concluir a subida reproduzível e gerar a tag `e3` no repositório público da Squad.
