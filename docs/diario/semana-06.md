# Diário de Bordo — Semana 06

- **Data:** 29/09/2026 a 05/10/2026 (1ª Semana da Entrega E2)
- **Participantes:** Filipe Carvalho, Taynara Vitorino, Gabriel Esteves, Maria Clara Alves, Kaio Macedo, Amanda Gonçalves (Squad G8)

## O que foi medido
- Planejamento e desenho da arquitetura da Entrega E2 (Ingestão em Lote e Captura de Mudanças):
  - Avaliação de viabilidade de formatos abertos: comparação entre Delta Lake e Apache Iceberg em ambiente local de contêiner.
  - Avaliação de compressão: comparação entre Snappy e Zstandard (`zstd`) sobre arquivos Parquet.
- Acolhimento e modelagem da sugestão da professora:
  - Enriquecimento da base da CEAP com dados públicos do Cadastro de CNPJs e Quadro de Sócios e Administradores (QSA) da Receita Federal.
  - Modelagem do algoritmo de resolução de grafo societário para rastreamento de Beneficiário Final (UBO - *Ultimate Beneficial Owner*).
- Implementação inicial da **Ingestão em Lote Idempotente** (`scripts/batch_ingest_lakehouse.py`) e do **Enriquecimento Societário** (`scripts/enrich_receita_socios.py`):
  - Tempo de carga em lote dos 785.754 registros para o Delta Lake: **34,2 segundos** (~23.000 linhas/s).
  - Volume em disco reduzido de 178 MB (Postgres) para **64,8 MB** (Delta Parquet ZSTD).
  - Prova de conceito de idempotência em lote: duas execuções consecutivas gerando rigorosamente os mesmos 785.754 registros sem duplicatas.

## O que surpreendeu
- A eficiência extrema da biblioteca `deltalake` em Rust/Python integrada ao Apache Arrow: grava tabelas com versionamento ACID e log de transações sem precisar de um cluster distribuído ou JVM pesada.
- A clareza do ganho analítico com o QSA: mais de 55.000 fornecedores na CEAP, mas muitos grupos de mídia e fretamento compartilham os mesmos sócios e holdings controladoras.

## O que foi decidido
- Adotar **Delta Lake** particionado por `ano_competencia` com compressão **Zstandard (`zstd`)** para a camada analítica aberta, mitigando o *Small Files Problem*.
- Separar o enriquecimento da Receita Federal em duas tabelas dimensionais no Lakehouse: `dim_fornecedor_cadastral` e `dim_quadro_societario_ubo`.
- Preparar a segunda semana para a configuração do WAL lógico no PostgreSQL e implementação do conector CDC.
