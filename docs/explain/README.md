# Consulta otimizada a partir do plano de execução (E3)

A consulta escolhida é a da pergunta de gestão da E1, executada no PostgreSQL (OLTP): o
**desvio acumulado de cada deputado da 57ª Legislatura em relação à média mensal dos
deputados da mesma UF** (top 15).

| Arquivo | Conteúdo |
| :--- | :--- |
| [`consulta_desvio.sql`](consulta_desvio.sql) | Consulta original, direto sobre `despesa_ceap` |
| [`antes.txt`](antes.txt) | `EXPLAIN (ANALYZE, BUFFERS)` da consulta original |
| [`consulta_desvio_otimizada.sql`](consulta_desvio_otimizada.sql) | Mesma consulta lendo o gasto mensal pré-agregado |
| [`depois.txt`](depois.txt) | `EXPLAIN (ANALYZE, BUFFERS)` da consulta otimizada |

Para gerar os dois planos de novo (com a plataforma no ar):

```bash
bash scripts/explain_desvio.sh
```

O script aquece o cache antes de medir, grava `antes.txt` e `depois.txt` e confere se as duas
consultas devolvem **o mesmo resultado**.

## O que o plano "antes" mostrou

- `Parallel Seq Scan on despesa_ceap`: a tabela inteira (167 MB) é lida a cada execução,
  cerca de **21,4 mil páginas** de 8 kB.
- O nó `GroupAggregate` do gasto mensal consome **~190 dos ~210 ms**: são ~780 mil
  lançamentos agregados em ~24 mil linhas (deputado × UF × mês) toda vez que a pergunta é feita.
- O restante (média da UF, junção e ranking) trabalha sobre essas ~24 mil linhas e é barato.

## Primeira tentativa: índice de cobertura (descartada)

Um índice `(codigo_legislatura, id_deputado, sigla_uf_emissao, ano_competencia,
mes_competencia) INCLUDE (valor_liquido)` trocou a varredura da tabela por um
`Index Only Scan` e reduziu as páginas lidas de 21,4 mil para 3,9 mil (−82%). **O tempo não
mudou** (~210 ms): o gargalo é agregar as ~780 mil linhas, não lê-las. Além disso, o índice
ocupa 31 MB e encarece cada inserção. Por isso ele não foi mantido.

## Otimização adotada: gasto mensal pré-agregado

A migração [`004_create_mv_gasto_mensal.sql`](https://github.com/taybalau/sbd2-g8-ceap/blob/main/migrations/004_create_mv_gasto_mensal.sql)
cria a view materializada `mv_gasto_mensal_deputado` (deputado × UF × competência ×
legislatura, ~24 mil linhas), e o `scripts/main.py` a recalcula logo após a carga.

| Medida (cache quente) | Antes | Depois |
| :--- | ---: | ---: |
| Tempo de execução | ~209 ms | **~33 ms** (6,3× mais rápido) |
| Páginas lidas (`shared hit + read`) | 21.428 | **206** (−99%) |
| Nó mais caro | `GroupAggregate` sobre ~780 mil linhas | `Seq Scan` sobre ~24 mil linhas |
| Resultado | top 15 | **idêntico** |

## O que se perde

- **A view envelhece.** Lançamentos inseridos depois da carga, por exemplo pelo teste de CDC
  da E2, só aparecem no `REFRESH MATERIALIZED VIEW`, que leva ~0,5 s.
- **Mais um objeto para manter.** Uma mudança na definição do gasto exige nova migração.
- **Recálculo integral.** O `REFRESH` refaz a agregação inteira, sem modo incremental. Se a
  carga passar a ser contínua, o caminho é o mart incremental no dbt (camada Gold), não esta view.
