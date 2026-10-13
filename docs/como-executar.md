# Como executar

A plataforma sobe **do zero, em máquina limpa**. Não é preciso baixar arquivos nem criar o banco manualmente.

## Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/) instalado e em execução
- [Docker Compose](https://docs.docker.com/compose/) v2+
- Git
- Acesso à internet na primeira execução (download dos CSVs da Câmara)
- ~1 GB livre em disco (CSVs, volume do banco e lakehouse)
- Porta **5432** livre

## 1. Clonar o repositório

```bash
git clone https://github.com/taybalau/sbd2-g8-ceap.git
cd sbd2-g8-ceap

# Opcional: voltar exatamente à versão da Entrega E1
git checkout e1
```

## 2. Subir tudo com um único comando

```bash
docker compose up --build
```

O comando executa, em ordem:

1. Constrói a imagem de ingestão.
2. Sobe o PostgreSQL 16 com replicação lógica (`wal_level=logical`) e aguarda o `healthcheck` (`pg_isready`).
3. Dispara o container `ceap_ingestion`, que aplica as migrações `001`, `002` e `003`.
4. Baixa os CSVs de 2023–2026 para `./base-dados/` (ou reaproveita os que já existirem).
5. Carrega os dados no OLTP via `COPY` e normaliza ano a ano (ou pula essa etapa se o banco já estiver populado).
6. Imprime o resumo do banco e o [painel de validação](consultas.md).
7. Grava a tabela analítica em `./lakehouse/delta/despesa_ceap` ([carga em lote](lakehouse.md#caminho-1--ingestão-em-lote)).
8. Grava as tabelas de [enriquecimento societário](enriquecimento.md) e imprime as consultas de auditoria.
9. Roda os [5 testes de aceite da E2](lakehouse.md#testes-de-aceite).

!!! tip "Rodar em segundo plano"
    ```bash
    docker compose up --build -d
    docker compose logs -f ingestion
    ```

## 3. Confirmar que terminou com sucesso

No final do log, procure por:

```text
Total de Registros de Despesa:      785754
Volume Total Pago na Legislatura:   R$ 869,398,245.27
...
[FINALIZADO COM SUCESSO] PLATAFORMA INTEGRADA DA ENTREGA E2 EM OPERAÇÃO PLENA!
```

As linhas de resumo do OLTP só aparecem quando a carga é feita; numa execução em que o banco já estava populado, o log mostra `Banco OLTP já está perfeitamente populado com 785.754 despesas. Pulando recarga.`

O container `ceap_ingestion` encerra sozinho no final; o `ceap_postgres` continua rodando.

## 4. Conectar ao banco

| Parâmetro | Valor |
| :--- | :--- |
| Host | `localhost` |
| Porta | `5432` |
| Banco | `ceap_oltp` |
| Usuário | `postgres` |
| Senha | `postgres` |

Funciona com DBeaver, pgAdmin, VS Code ou `psql`. Para abrir um `psql` direto no container:

```bash
docker exec -it ceap_postgres psql -U postgres -d ceap_oltp
```

## 5. Primeira consulta

Top 10 parlamentares por gasto total:

```bash
docker exec -it ceap_postgres psql -U postgres -d ceap_oltp -c "
SELECT
    p.nome_parlamentar,
    d.sigla_partido_emissao AS partido,
    d.sigla_uf_emissao AS uf,
    COUNT(d.id_despesa) AS total_notas,
    ROUND(SUM(d.valor_liquido), 2) AS total_gasto
FROM despesa_ceap d
JOIN parlamentar p ON p.id_deputado = d.id_deputado
GROUP BY p.nome_parlamentar, d.sigla_partido_emissao, d.sigla_uf_emissao
ORDER BY total_gasto DESC
LIMIT 10;
"
```

Mais consultas em [Perguntas de gestão](consultas.md).

### Consultar o lakehouse (E2)

```bash
docker exec -it ceap_ingestion python -c "
import duckdb
con = duckdb.connect()
print(con.execute('''
    SELECT ano_competencia, COUNT(*) AS total_notas, ROUND(SUM(valor_liquido), 2) AS total_gasto
    FROM delta_scan('lakehouse/delta/despesa_ceap')
    GROUP BY ano_competencia ORDER BY ano_competencia;
''').fetchdf())
"
```

Como o `ceap_ingestion` encerra após a execução, use `docker compose run --rm ingestion python ...` se o container não estiver ativo.

## 6. (Opcional) Reproduzir a medição do ADR

```bash
docker exec -it ceap_postgres psql -U postgres -d ceap_oltp -c "EXPLAIN ANALYZE SELECT p.nome_parlamentar, d.sigla_partido_emissao, COUNT(*), SUM(d.valor_liquido) FROM despesa_ceap d JOIN parlamentar p ON p.id_deputado = d.id_deputado GROUP BY p.nome_parlamentar, d.sigla_partido_emissao ORDER BY SUM(d.valor_liquido) DESC LIMIT 10;"
```

No ambiente da Squad, essa consulta levou cerca de **112 ms**; o tempo na sua máquina pode variar (ver [ADR-0001](adr/0001-modelagem-transacional-insert-only-ceap.md#medição)).

## 7. Rodar só os testes de aceite da E2

```bash
docker compose run --rm ingestion python scripts/test_e2_pipeline.py
```

## 8. Parar ou recriar o ambiente

```bash
# Parar mantendo os dados
docker compose down

# Apagar tudo (containers + volume do banco) e recomeçar do zero
docker compose down -v
```

!!! info "Rodar de novo sobre o mesmo volume"
    - As migrações são registradas em `schema_migrations` e não são reaplicadas.
    - A carga no OLTP verifica a contagem de `despesa_ceap` antes de começar: se já houver **785.754** linhas, ela é pulada; se houver mais, a tabela é esvaziada e recarregada. Esse número está fixo no código, então uma carga parcial (por exemplo, com `ANOS: "2023"`) ou novos dados de 2026 publicados pela Câmara mudam a contagem e a verificação deixa de valer. Em caso de dúvida, use `docker compose down -v`.
    - A carga em lote do lakehouse sempre recria a tabela Delta do zero.

`./base-dados/` (CSVs) e `./lakehouse/` (tabelas Delta) ficam no host e continuam lá mesmo após `down -v`. Apague essas pastas para forçar um novo download ou uma nova camada analítica.

## Variações

=== "Carregar só alguns anos"

    Edite `ANOS` no serviço `ingestion` do `docker-compose.yml`:

    ```yaml
    ANOS: "2023"
    ```

    `ANOS` controla o download e a carga no OLTP. A carga em lote do lakehouse sempre percorre 2023 a 2026 e grava o que existir no banco.

=== "Rodar fora do Docker"

    Com um PostgreSQL 15+ rodando com `wal_level=logical` e o banco `ceap_oltp` criado:

    ```bash
    pip install -r docker/ingestion/requirements.txt

    export DB_HOST=localhost DB_PORT=5432 DB_NAME=ceap_oltp \
           DB_USER=postgres DB_PASSWORD=postgres ANOS="2023,2024,2025,2026" \
           LAKEHOUSE_PATH=./lakehouse

    # Execute a partir da raiz do projeto (migrations/ e base-dados/ são relativos)
    python scripts/main.py
    ```

    No Windows (PowerShell), use `$env:DB_HOST="localhost"` em vez de `export`.

=== "Baixar só os CSVs"

    ```bash
    python scripts/download_data.py
    ```

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
| :--- | :--- | :--- |
| `port is already allocated` na 5432 | Outro PostgreSQL local usando a porta | Pare o outro serviço ou troque o mapeamento para `"5433:5432"` no `docker-compose.yml` |
| `[ERRO] Falha ao baixar dados do ano ...` | Sem internet ou portal da Câmara indisponível | Tente mais tarde, ou coloque `Ano-AAAA.csv` manualmente em `base-dados/` |
| `Banco ainda não disponível (n/15)` repetido | Banco demorando a iniciar | O script tenta 15 vezes a cada 2 s; veja `docker compose logs db` |
| Contagens diferentes de 785.754 no OLTP | Carga parcial ou interrompida, ou novos dados publicados pela Câmara | Rode `docker compose down -v` e suba de novo |
| Volume do PostgreSQL crescendo sem parar | O slot de replicação `ceap_cdc_slot` retém o WAL porque não é consumido | Veja [Lakehouse e CDC](lakehouse.md#como-o-consumidor-funciona) |
| Erro ao criar a publicação ou o slot de replicação | PostgreSQL sem `wal_level=logical` | Use o `docker-compose.yml` do projeto, que já passa essa configuração |
| Erro em `UNIQUE NULLS NOT DISTINCT` | PostgreSQL anterior à versão 15 | Use PostgreSQL 15+ (o Compose usa a 16) |
