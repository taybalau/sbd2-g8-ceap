# E4 · Controle de acesso com privilégio mínimo

A [migration 005](../migrations/005_controle_acesso.sql) atende à issue #10 por **recorte de colunas e view mascarada no PostgreSQL**, conforme os papéis da [análise de LGPD](lgpd.md#62-papéis).

## Papéis e recorte

| Papel | Permissões |
| --- | --- |
| `ceap_pipeline` | Leitura e escrita necessárias à carga, upserts, staging e sequências. Sem administração ou exclusão de despesas. |
| `ceap_auditor` | Leitura das tabelas de negócio, incluindo dados restritos. Sem escrita no OLTP nem leitura da staging. |
| `ceap_consulta` | Somente colunas públicas; fornecedores pela view `v_fornecedor_publico`. |

Os grupos são `NOLOGIN`, sem privilégios administrativos. Cada login recebe um único perfil. A 005 remove concessões excessivas de `PUBLIC` e dos grupos antes de aplicar a matriz; novas colunas não entram automaticamente no acesso de consulta.

Para `ceap_consulta`, ficam bloqueados `parlamentar.cpf`, `nu_carteira_parlamentar`, `despesa_ceap.passageiro` e a tabela original de fornecedores. A view mascara CPF no documento (`12345678901` → `***.456.789-**`) e na razão social, preservando CNPJ. Isso reduz exposição, sem anonimizar o titular.

As permissões de `alerta` pertencem exclusivamente à **006**: pipeline publica, auditor lê e registra decisões, consulta não acessa. O login `ceap_etl_reverso`, membro de `ceap_pipeline`, já é usado pelo Dagster/ETL reverso no Compose.

## Aplicar

Na raiz do projeto, com Docker ativo:

```powershell
docker compose up -d db
docker compose build ingestion
docker compose exec -T db pg_isready -U postgres -d ceap_oltp
docker compose run --rm --no-deps -e DATABASE_URL=postgresql://postgres:postgres@db:5432/ceap_oltp ingestion python scripts/run_migrations.py
```

Execute o runner quando o banco aceitar conexões. Ele registra as migrations pendentes e aplica a 005 mesmo se a 006 já estiver registrada.

## Demonstrar acesso permitido e negado

Com as migrations aplicadas, execute em banco de desenvolvimento. O roteiro cria dois usuários e dados sintéticos, verifica as permissões e desfaz tudo com `ROLLBACK`. `SET SESSION AUTHORIZATION` assume a identidade do usuário, sem privilégios de superusuário; os nomes `e4_demo_*` devem estar livres.

Este comando PowerShell extrai e executa o SQL abaixo:

```powershell
$docAcesso = Get-Content -Raw -Encoding UTF8 docs/controle-de-acesso.md
$sqlAcesso = [regex]::Match($docAcesso, '(?s)<!-- inicio-validacao-sql -->\s*```sql\s*(.*?)\s*```').Groups[1].Value
if (-not $sqlAcesso) { throw 'Bloco de validacao nao encontrado' }
$sqlAcesso | docker compose exec -T db psql -X -v ON_ERROR_STOP=1 -U postgres -d ceap_oltp
if ($LASTEXITCODE -ne 0) { throw 'Validacao de acesso falhou' }
```

<!-- inicio-validacao-sql -->
```sql
\set ON_ERROR_STOP on
BEGIN;
CREATE ROLE e4_demo_auditor LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE e4_demo_consulta LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT ceap_auditor TO e4_demo_auditor;
GRANT ceap_consulta TO e4_demo_consulta;

INSERT INTO public.parlamentar (id_deputado, nome_parlamentar, cpf)
VALUES (-100010, 'PARLAMENTAR TESTE E4', '12345678901');
INSERT INTO public.fornecedor (id_fornecedor, cnpj_cpf, razao_social)
VALUES (-100010, '12345678901', 'PESSOA TESTE 123.456.789-01');

SET SESSION AUTHORIZATION e4_demo_auditor;
SELECT session_user, cpf FROM public.parlamentar WHERE id_deputado = -100010;
RESET SESSION AUTHORIZATION;

SET SESSION AUTHORIZATION e4_demo_consulta;
SELECT session_user, nome_parlamentar FROM public.parlamentar WHERE id_deputado = -100010;
SELECT * FROM public.v_fornecedor_publico WHERE id_fornecedor = -100010;
DO $$
DECLARE comando text;
BEGIN
    IF (SELECT cnpj_cpf_exibicao = '***.456.789-**' AND razao_social = 'PESSOA TESTE ***'
        FROM public.v_fornecedor_publico WHERE id_fornecedor = -100010) IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'FALHOU: mascaramento do fornecedor';
    END IF;
    FOREACH comando IN ARRAY ARRAY[
        'SELECT cpf FROM public.parlamentar',
        'SELECT nu_carteira_parlamentar FROM public.parlamentar',
        'SELECT passageiro FROM public.despesa_ceap',
        'SELECT * FROM public.fornecedor',
        'SELECT * FROM public.stg_ceap_raw',
        'SELECT * FROM alerta.vw_fila_auditoria',
        'UPDATE public.parlamentar SET nome_parlamentar = nome_parlamentar WHERE false',
        'SET ROLE ceap_auditor'
    ] LOOP
        BEGIN
            EXECUTE comando;
        EXCEPTION WHEN insufficient_privilege THEN
            RAISE NOTICE 'NEGADO (42501): %', comando;
            CONTINUE;
        END;
        RAISE EXCEPTION 'ACESSO INDEVIDO: %', comando;
    END LOOP;
END $$;
RESET SESSION AUTHORIZATION;
ROLLBACK;
\echo VALIDACAO E4 CONCLUIDA: acessos permitidos e negados conforme a matriz.
```
<!-- fim-validacao-sql -->

**Esperado:** auditor lê `12345678901`; consulta lê o nome público e o fornecedor mascarado; as oito operações proibidas geram `NEGADO (42501)`. Uma permissão indevida interrompe o teste com erro. Ao final, aparece `VALIDACAO E4 CONCLUIDA`.

## Evidências da implementação

Validação realizada em **24/11/2026**, com **PostgreSQL 16.14** em container isolado e dados sintéticos. A bateria completa da implementação passou com **12 asserções positivas e 34 operações negadas**; o roteiro acima é uma demonstração resumida.

Também foram validados: instalação nova, reaplicação da 005, atualização depois da 006, remoção de permissões excessivas, bloqueio de novas colunas e execução dos SQLs reais de carga como pipeline. As permissões de `alerta` permaneceram intactas.

Evidência obtida com logins reais por TCP, cada um associado a seu perfil:

| Usuário | Consulta | Resultado |
| --- | --- | --- |
| `e4_tcp_auditor` | `SELECT cpf FROM public.parlamentar` | Permitido: `12345678901` |
| `e4_tcp_consulta` | Mesma consulta | Negado: SQLSTATE `42501` |
| `e4_tcp_consulta` | View de fornecedores | `***.456.789-**` e `PESSOA TESTE ***` |

