# Como executar

A plataforma sobe **do zero, em máquina limpa**. Não é preciso baixar arquivos nem criar o banco manualmente.

## Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/) instalado e em execução
- [Docker Compose](https://docs.docker.com/compose/) v2+
- Git
- Acesso à internet na primeira execução (download dos CSVs da Câmara)
- ~1 GB livre em disco (CSVs + volume do banco)
- Porta **5432** livre

## 1. Clonar o repositório

```bash
git clone https://github.com/taybalau/sbd2-g8-ceap.git
cd sbd2-g8-ceap

# Opcional: fixar exatamente a versão da Entrega E1
git checkout e1
```

## 2. Subir tudo com um único comando

```bash
docker compose up --build
```

O comando executa, em ordem:

1. Constrói a imagem de ingestão.
2. Sobe o PostgreSQL 16 e aguarda o `healthcheck` (`pg_isready`).
3. Dispara o container `ceap_ingestion`, que aplica as migrações `001` e `002`.
4. Baixa os CSVs de 2023–2026 para `./base-dados/` (ou reaproveita os que já existirem).
5. Carrega os dados via `COPY` e normaliza ano a ano.
6. Imprime o resumo do banco e o [painel de validação](consultas.md).

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
[FINALIZADO] Plataforma transacional (E1) pronta e operando com sucesso!
```

O container `ceap_ingestion` encerra sozinho após a carga; o `ceap_postgres` continua rodando.

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

## 6. (Opcional) Reproduzir a medição do ADR

```bash
docker exec -it ceap_postgres psql -U postgres -d ceap_oltp -c "EXPLAIN ANALYZE SELECT p.nome_parlamentar, d.sigla_partido_emissao, COUNT(*), SUM(d.valor_liquido) FROM despesa_ceap d JOIN parlamentar p ON p.id_deputado = d.id_deputado GROUP BY p.nome_parlamentar, d.sigla_partido_emissao ORDER BY SUM(d.valor_liquido) DESC LIMIT 10;"
```

O resultado esperado é por volta de **112 ms** (ver [ADR-0001](adr/0001-modelagem-transacional-insert-only-ceap.md#medicao)).

## 7. Parar ou recriar o ambiente

```bash
# Parar mantendo os dados
docker compose down

# Apagar tudo (containers + volume do banco) e recomeçar do zero
docker compose down -v
```

!!! warning "A ingestão não é idempotente"
    As migrações podem rodar várias vezes, mas a carga em `despesa_ceap` não. Rodar `docker compose up` de novo sobre um volume já populado **duplica as despesas**. Para recarregar, use `docker compose down -v` antes.

Os CSVs ficam em `./base-dados/` e continuam como cache mesmo após `down -v`. Apague essa pasta para forçar um novo download.

## Variações

=== "Carregar só alguns anos"

    Edite `ANOS` no serviço `ingestion` do `docker-compose.yml`:

    ```yaml
    ANOS: "2023"
    ```

=== "Rodar fora do Docker"

    Com um PostgreSQL 15+ rodando e o banco `ceap_oltp` criado:

    ```bash
    pip install -r docker/ingestion/requirements.txt

    export DB_HOST=localhost DB_PORT=5432 DB_NAME=ceap_oltp \
           DB_USER=postgres DB_PASSWORD=postgres ANOS="2023,2024,2025,2026"

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
| Contagens maiores que 785.754 | Ingestão executada mais de uma vez no mesmo volume | Rode `docker compose down -v` e suba de novo |
| Erro em `UNIQUE NULLS NOT DISTINCT` | PostgreSQL anterior à versão 15 | Use PostgreSQL 15+ (o Compose usa a 16) |
