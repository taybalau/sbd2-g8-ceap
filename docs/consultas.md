# Perguntas de gestão

## Pergunta central

!!! question ""
    **Quais parlamentares e partidos da 57ª Legislatura (2023–2026) apresentam maior desvio de gastos acima da média mensal da Cota Parlamentar (CEAP), e quais categorias e fornecedores concentram esses recursos?**

A pergunta foi formalizada na [Semana 02](diario/semana-02.md), quando a Squad percebeu que perguntas genéricas ("como os deputados gastam a cota?") não dão critério técnico para a modelagem. Ela tem sujeito claro (parlamentares e partidos), recorte delimitado (57ª Legislatura) e métrica explícita (desvio sobre a média mensal).

## Perguntas complementares

Ao final da carga, `main.py` imprime um **painel de validação** com as seis consultas abaixo. Todas podem ser executadas em qualquer cliente SQL conectado a `ceap_oltp` (veja [Como executar](como-executar.md#4-conectar-ao-banco)).

### 1. Custo médio mensal por deputado

```sql
SELECT ROUND(AVG(gasto_mensal), 2)
FROM (
    SELECT id_deputado, ano_competencia, mes_competencia,
           SUM(valor_liquido) AS gasto_mensal
    FROM despesa_ceap
    GROUP BY id_deputado, ano_competencia, mes_competencia
) sub;
```

### 2. Parlamentares que mais usam a cota (Top 5)

```sql
SELECT
    p.nome_parlamentar,
    d.sigla_partido_emissao,
    d.sigla_uf_emissao,
    COUNT(d.id_despesa)            AS notas,
    ROUND(AVG(d.valor_liquido), 2) AS ticket_medio,
    ROUND(SUM(d.valor_liquido), 2) AS total_gasto
FROM despesa_ceap d
JOIN parlamentar p ON p.id_deputado = d.id_deputado
GROUP BY p.nome_parlamentar, d.sigla_partido_emissao, d.sigla_uf_emissao
ORDER BY SUM(d.valor_liquido) DESC
LIMIT 5;
```

### 3. Maiores fornecedores (Top 3)

```sql
SELECT f.razao_social, COUNT(d.id_despesa), ROUND(SUM(d.valor_liquido), 2)
FROM despesa_ceap d
JOIN fornecedor f ON f.id_fornecedor = d.id_fornecedor
GROUP BY f.razao_social
ORDER BY SUM(d.valor_liquido) DESC
LIMIT 3;
```

### 4. Categorias de despesa mais representativas (Top 3)

```sql
SELECT c.descricao, COUNT(d.id_despesa), ROUND(SUM(d.valor_liquido), 2)
FROM despesa_ceap d
JOIN categoria_despesa c ON c.num_subcota = d.num_subcota
GROUP BY c.descricao
ORDER BY SUM(d.valor_liquido) DESC
LIMIT 3;
```

### 5. Consumo por partido político (Top 3)

```sql
SELECT d.sigla_partido_emissao, COUNT(d.id_despesa), ROUND(SUM(d.valor_liquido), 2)
FROM despesa_ceap d
WHERE d.sigla_partido_emissao IS NOT NULL AND d.sigla_partido_emissao != ''
GROUP BY d.sigla_partido_emissao
ORDER BY SUM(d.valor_liquido) DESC
LIMIT 3;
```

### 6. Fins de semana vs. dias úteis

```sql
SELECT
    CASE WHEN EXTRACT(ISODOW FROM data_emissao) IN (6, 7)
         THEN 'Fim de Semana' ELSE 'Dia Útil' END     AS tipo_dia,
    COUNT(*)                                          AS notas,
    ROUND(SUM(valor_liquido), 2)                      AS total,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct_notas
FROM despesa_ceap
WHERE data_emissao IS NOT NULL
GROUP BY tipo_dia
ORDER BY tipo_dia DESC;
```

## Índices que sustentam as consultas

Cada pergunta tem um índice dedicado em `despesa_ceap`. A relação completa está em [Modelo de dados → Índices](modelo-de-dados.md#índices-002_create_indexessql).

## Na camada analítica (E2)

A partir da E2, as mesmas análises podem ser feitas sobre a tabela Delta `despesa_ceap`, que já vem desnormalizada (com nome do parlamentar, fornecedor e descrição da subcota) e dispensa junções. Segundo o [ADR-0002](adr/0002-mecanismo-ingestao-e-formato-aberto.md), a agregação no DuckDB leva cerca de **18 ms**, contra 112 ms no OLTP.

Exemplo, equivalente à pergunta 5 (consumo por partido):

```sql
SELECT sigla_partido_emissao,
       COUNT(*)                     AS notas,
       ROUND(SUM(valor_liquido), 2) AS total
FROM delta_scan('lakehouse/delta/despesa_ceap')
WHERE sigla_partido_emissao IS NOT NULL AND sigla_partido_emissao != ''
GROUP BY sigla_partido_emissao
ORDER BY total DESC
LIMIT 3;
```

As consultas da pergunta ampliada (beneficiário final) estão em [Enriquecimento societário](enriquecimento.md#consultas-de-auditoria).
