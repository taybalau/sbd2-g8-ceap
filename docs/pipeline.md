# E1 · Carga no OLTP

Esta página descreve como os CSVs da Câmara chegam ao banco transacional. O que acontece depois, na camada analítica, está em [Lakehouse e CDC](lakehouse.md).

Os scripts ficam em [`scripts/`](https://github.com/taybalau/sbd2-g8-ceap/tree/main/scripts) e são executados pelo container `ceap_ingestion` a partir de `main.py`.

## Fluxo

```mermaid
sequenceDiagram
    autonumber
    participant M as main.py
    participant PG as PostgreSQL
    participant R as run_migrations.py
    participant D as download_data.py
    participant C as Câmara / cache
    participant I as ingest_ceap.py

    M->>PG: conectar (até 15 tentativas, 2 s)
    M->>R: apply_migrations()
    R->>PG: cria schema_migrations
    R->>PG: aplica 001, 002 (pula as já aplicadas)
    M->>D: ensure_data_available(ANOS)
    D->>C: usa base-dados/Ano-AAAA.csv ou baixa o .zip
    M->>I: ingest_csv_files(csv_files)
    I->>PG: SELECT count(*) FROM despesa_ceap
    Note over I,PG: 785.754 → pula a carga · mais que isso → TRUNCATE e recarrega
    loop para cada ano
        I->>PG: TRUNCATE stg_ceap_raw
        I->>PG: COPY CSV → stg_ceap_raw
        I->>PG: INSERT parlamentar, mandato
        I->>PG: INSERT categoria, especificação
        I->>PG: INSERT fornecedor
        I->>PG: INSERT despesa_ceap
        I->>PG: TRUNCATE staging + COMMIT
    end
    M->>PG: painel de validação (6 consultas)
```

## Scripts

### `main.py` — orquestrador

1. Lê `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` e conecta com *retry*.
2. Chama `apply_migrations(conn, "migrations")`.
3. Lê `ANOS` (padrão `2023,2024,2025,2026`) e garante os CSVs com `ensure_data_available`.
4. Executa a carga com `ingest_csv_files`.
5. Roda o [painel de validação](consultas.md) com as seis perguntas.
6. Segue para as etapas da E2: carga em lote no lakehouse, enriquecimento societário, consultas de auditoria e testes de aceite (ver [Arquitetura](arquitetura.md#etapas-do-mainpy)).

### `run_migrations.py` — migrações versionadas

- Cria `schema_migrations` se não existir.
- Lista os `.sql` de `migrations/` em **ordem alfanumérica**.
- Executa só os que ainda não estão registrados, e registra cada um após o sucesso.
- Se uma migração falhar, faz `ROLLBACK` e interrompe a execução.

Resultado: **as migrações são idempotentes**. Rodar duas vezes não recria nada. A migração `003` (E2) também verifica se a publicação já existe antes de criá-la.

### `download_data.py` — download com cache

- URL oficial: `http://www.camara.leg.br/cotas/Ano-{ano}.csv.zip`.
- Se `base-dados/Ano-AAAA.csv` já existir (com mais de 1 KB), usa o cache.
- Caso contrário, baixa o `.zip`, **extrai em memória** e grava o CSV.
- Pode ser executado sozinho: `python scripts/download_data.py`.

### `ingest_ceap.py` — carga em dois estágios

**Verificação prévia (adicionada na E2).** Antes de carregar, o script conta as linhas de `despesa_ceap`:

- **exatamente 785.754:** considera o banco já populado e pula a carga;
- **mais de 785.754:** entende que houve execuções repetidas, faz `TRUNCATE ... RESTART IDENTITY CASCADE` e recarrega;
- **menos que isso:** segue com a carga normalmente.

O número 785.754 está fixo no código. Uma carga parcial (só alguns anos em `ANOS`) ou novos dados de 2026 publicados pela Câmara mudam a contagem, e nesse caso a verificação não protege contra duplicação.

**Estágio 1: staging bruto.** O CSV (separador `;`) é carregado com `COPY ... FROM STDIN` na tabela `stg_ceap_raw`, que é `UNLOGGED` (não escreve no WAL) e tem só colunas `TEXT`. Esse é o caminho mais rápido possível para trazer os dados ao banco.

**Estágio 2: normalização em SQL.** A partir do staging, comandos `INSERT ... SELECT` populam as tabelas na ordem das dependências:

| Ordem | Tabela | Estratégia de conflito |
| :---: | :--- | :--- |
| 1 | `parlamentar` | `ON CONFLICT DO UPDATE` (mantém CPF/carteira já conhecidos via `COALESCE`) |
| 2 | `mandato_parlamentar` | `ON CONFLICT DO NOTHING` |
| 3 | `categoria_despesa` | `ON CONFLICT DO UPDATE` da descrição |
| 4 | `especificacao_despesa` | `ON CONFLICT DO NOTHING` |
| 5 | `fornecedor` | `ON CONFLICT DO NOTHING` (com `NULLS NOT DISTINCT`) |
| 6 | `despesa_ceap` | Insert puro (*insert-only*) |

Durante a conversão:

- strings vazias viram `NULL` (`NULLIF(..., '')`) e textos são aparados com `TRIM`;
- datas só são convertidas se casarem com `^\d{4}-\d{2}-\d{2}`;
- valores ausentes recebem padrões explícitos (ex.: `'FORNECEDOR NÃO INFORMADO'`, `'SEM PARTIDO'`, legislatura `57`);
- linhas sem `nuDeputadoId` não entram em `despesa_ceap`.

!!! warning "Competência ausente"
    Se o mês ou o ano de competência vierem vazios no CSV, a carga assume **mês 1** e **ano 2023** (`COALESCE(..., 1)` e `COALESCE(..., 2023)`). Linhas nessa situação seriam contadas em janeiro de 2023, o que pode afetar as médias mensais.

Cada ano é processado e confirmado em **uma transação** (`COMMIT` ao final do ano). No fim, o script imprime um resumo com as contagens de cada tabela e o volume total pago.

## Desempenho medido (ambiente da Squad)

| Etapa | Resultado |
| :--- | :--- |
| Carga completa dos 4 anos (785.754 linhas, ~265 MB) | **~97,4 s** |
| Consulta analítica principal (com índices) | **~112 ms** |

Para comparação com as alternativas (tabela flat e CRUD), veja a seção de medição do [ADR-0001](adr/0001-modelagem-transacional-insert-only-ceap.md#medição).

## Correção relevante: duplicação de fornecedores

Na primeira versão, fornecedores sem CNPJ eram inseridos de novo a cada ano, porque `NULL <> NULL` impedia o `ON CONFLICT` de reconhecê-los. Como o `JOIN` da carga de despesas usa `razao_social` + `cnpj_cpf`, as duplicatas multiplicavam as despesas. A troca para `UNIQUE NULLS NOT DISTINCT` resolveu o problema e restabeleceu a contagem exata de **785.754** registros.
