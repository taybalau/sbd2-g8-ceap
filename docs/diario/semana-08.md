# Diário de Bordo — Semanas 08 a 10

- **Data:** 14/10/2026 a 03/11/2026 (Entrega E3 em 03/11/2026)
- **Participantes:** Filipe Carvalho, Taynara Vitorino, Gabriel Esteves, Maria Clara Alves, Kaio Macedo, Amanda Gonçalves (Squad G8)

## O que foi medido
- **Decisões de arquitetura (29/10):** [`ADR-0004`](../adr/0004-avaliacao-etl-relacional-postgres-vs-lakehouse-direto.md) (a E3 roda direto sobre o Lakehouse, com dbt-duckdb) e [`ADR-0005`](../adr/0005-modelagem-dimensional-granularidade-scd-ceap.md) (esquema estrela, fato atômico e SCD tipo 2).
- **Implementação da E3** em `dbt_ceap/`, `orquestracao/`, `ingestao/` e `painel/`: Bronze com 785.929 linhas, 186 deputados com troca de partido no histórico oficial (contra 92 visíveis no CSV) e 173.413 lançamentos (22%) com partido sobrescrito pela fonte. Detalhes em [E3](../e3.md) e [Erros tratados](../e3-erros-tratados.md).
- **Falhas provocadas de propósito** (`orquestracao/demo_falhas.py`): retry absorvendo 2 falhas transitórias, fonte da Câmara fora (3 retries, Bronze e Gold intactas), API de histórico fora (dbt nem inicia) e dado sujo (teste reprova e os 4 modelos Gold são pulados).
- **Backfill real pelo Dagster** (`orquestracao/backfill_dagster.py`): o daemon executou as partições 2023 e 2024 uma de cada vez, o sensor disparou a transformação sozinho depois de cada ingestão bem-sucedida, as contagens por ano não mudaram e o hash da Gold ficou idêntico. Evidência em `orquestracao/evidencias/backfill_dagster.json`.
- **Consulta otimizada no PostgreSQL** ([`docs/explain/`](../explain/README.md)): desvio da pergunta de gestão caiu de ~209 ms para ~33 ms e de 21.428 para 206 páginas lidas, com o gasto mensal pré-agregado. Um índice de cobertura testado antes reduziu as páginas em 82%, mas não mudou o tempo.
- **Freshness e SLA:** Gold publicada até 26 h após a ingestão; o teste `assert_gold_dentro_do_sla` reprovou quando o SLA foi forçado a 0 h.
- **Subida do zero em cópia limpa do repositório** (03/11): a plataforma inteira sobe com `docker compose up --build`.

## O que surpreendeu
- **O CSV da Câmara reescreve o partido** de todos os lançamentos com o partido atual do deputado. Um SCD montado a partir do CSV reproduziria a sobrescrita da fonte; por isso o SCD usa o histórico oficial da API.
- **Os dados mudaram entre dois downloads.** No download de 03/11 apareceu a subcota 996 (passagem aérea em missão oficial, só créditos), e o teste de classificação barrou a Gold até ela ser registrada. A queda da subcota de divulgação em jun/2026 (12% da mediana) também apareceu, provavelmente pela vedação de divulgação em ano eleitoral.
- **Os 175 lançamentos de diferença** entre a E1 e a E3 não eram perda na carga: o mesmo CSV anual muda conforme a data do download.
- **Na revisão, o `docker compose` terminava com sucesso mesmo sem Gold,** e a E3 não esperava o download dos CSVs. Só uma subida do zero em cópia limpa mostrou isso.

## O que foi decidido
- Manter o painel em Streamlit, com a justificativa e as medições no [`ADR-0007`](../adr/0007-ferramenta-do-painel-analitico.md).
- Registrar no seed `ruptura_publicacao.csv` toda quebra de série investigada. Uma quebra nova reprova o build até alguém investigar.
- Revisão entre pares: a implementação foi revisada e testada do zero antes do merge (PR #2), e os complementos da E3 entraram por uma branch própria.
- Geração da tag `e3` no repositório público da Squad.
