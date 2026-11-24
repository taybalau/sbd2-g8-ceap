# E4 · Controle de acesso com privilégio mínimo

Implementação da issue #10 em [`migrations/005_controle_acesso.sql`](../migrations/005_controle_acesso.sql), alinhada aos nomes de papéis de [LGPD, seção 6.2](lgpd.md#62-papéis). O requisito é atendido por **recorte de coluna**, usando `GRANT SELECT (colunas)` e a view `public.v_fornecedor_publico`. Não há política RLS: todos os registros podem ser consultados nas colunas autorizadas.

## 1. Papéis e permissões

Os três papéis são grupos `NOLOGIN`, sem senha, superusuário, criação de banco/papéis, replicação, `BYPASSRLS` ou autorização para repassar privilégios. Cada usuário recebe apenas o grupo de seu perfil.

| Recurso/operação | `ceap_pipeline` | `ceap_auditor` | `ceap_consulta` |
| --- | --- | --- | --- |
| Conectar ao banco / usar `public` | Sim | Sim | Sim |
| Ler tabelas de negócio do OLTP | Todas as colunas | Todas as colunas | Lista explícita de colunas públicas |
| `parlamentar.cpf`, `nu_carteira_parlamentar`, `despesa_ceap.passageiro` | Sim | Sim | **Negado** |
| `fornecedor` original | Ler e inserir | Ler | **Negado**, inclusive razão social original |
| `v_fornecedor_publico` | Ler | Ler | Ler, com CPF mascarado |
| Inserir dimensões e despesas | Sim | Não | Não |
| Atualizar `parlamentar`, `categoria_despesa` e checkpoint | Sim, usados no upsert | Não | Não |
| Alterar/apagar despesas e demais dimensões | Não | Não | Não |
| `stg_ceap_raw` | Ler, inserir/COPY e truncar | **Negado** | **Negado** |
| `cdc_consumer_checkpoint` | Ler, inserir e atualizar | Não | Não |
| Sequências de identidade da carga | `USAGE` | Não | Não |
| `schema_migrations` | Não | Não | Não |
| View materializada de gastos mensais | Ler | Ler | Ler colunas autorizadas |
| Criar tabelas/schemas/temporárias, mudar estrutura, conceder acesso | Não | Não | Não |
| `alerta` (permissões **da 006**) | Publicar retratos e execuções | Ler fila e inserir decisões | **Negado** |

A staging não faz parte da leitura do auditor porque contém o CSV bruto; a própria análise de LGPD restringe essa tabela ao pipeline. O auditor lê os identificadores nas tabelas de negócio enquanto a minimização definitiva da origem não for implementada.

O pipeline recebe operações específicas, em vez de `GRANT ALL`: não é dono das tabelas, não pode apagar o livro-razão, editar migrations nem conceder permissões. Carga normal e upserts estão contemplados. `REFRESH MATERIALIZED VIEW` no PostgreSQL 16, migrations, reset de carga com `RESTART IDENTITY` e captura de replicação continuam sendo tarefas administrativas, separadas dessas credenciais.

## 2. Como o recorte funciona

Exemplo do controle nativo de colunas:

```sql
GRANT SELECT (id_deputado, nome_parlamentar, ide_cadastro, created_at)
    ON public.parlamentar TO ceap_consulta;
```

`ceap_consulta` pode selecionar `nome_parlamentar`, mas `SELECT cpf`, `SELECT *` e filtros sobre `cpf` são recusados pelo banco. Isso vale mesmo com a tabela vazia. Acrescentar uma coluna à tabela não a torna automaticamente acessível. A consulta deve declarar as colunas públicas.

Para fornecedores, o perfil de consulta não recebe acesso à tabela original. A view devolve somente `id_fornecedor`, `razao_social` tratada e `cnpj_cpf_exibicao`:

| Entrada sintética | Saída da view |
| --- | --- |
| CPF `12345678901` ou `123.456.789-01` | `***.456.789-**` |
| Razão social `PESSOA TESTE 12345678901` | `PESSOA TESTE ***` |
| Razão social `PESSOA TESTE 123.456.789-01` | `PESSOA TESTE ***` |
| CNPJ `12.345.678/0001-90` | `12.345.678/0001-90` |
| Documento nulo ou vazio | `NULL` |
| Documento em formato desconhecido | `[documento restrito]` |

A view usa as permissões de seu proprietário (`security_invoker = false`) para ler a origem e tem `security_barrier = true`. O consumidor só recebe `SELECT` na view. Mascaramento reduz exposição; não torna a pessoa anônima, pois nome e identificador de fornecedor continuam disponíveis.

A migration revoga privilégios anteriores de `PUBLIC` e dos três grupos em `public`, incluindo concessões **por coluna**, antes de reconstruir a matriz. Também retira `CREATE`/`TEMPORARY` no banco e `CREATE` no schema. Não altera permissões em `alerta`. Objetos novos não recebem concessões automáticas para esses grupos. Os `ALTER DEFAULT PRIVILEGES` são específicos do schema `public` e do administrador que aplica a migration; se outro proprietário criar objetos, seus defaults também devem ser administrados.

Papéis preexistentes são reutilizados e seus atributos normalizados. Se um dos três grupos já herdar outro papel, a migration falha para exigir a revisão dessa herança, que poderia conceder acessos além da matriz. Logins não devem ser donos dos objetos, superusuários, membros de vários perfis nem receber `GRANT` direto além do grupo. Privilégios adicionais concedidos por outro administrador se somam aos do perfil.

Referências do mecanismo: [GRANT no PostgreSQL 16](https://www.postgresql.org/docs/16/sql-grant.html) e [CREATE VIEW no PostgreSQL 16](https://www.postgresql.org/docs/16/sql-createview.html).

## 3. Aplicar a migration

Execute na raiz do repositório. Basta subir o banco; não é necessário baixar os CSVs nem executar o dbt para demonstrar as permissões.

```powershell
docker compose up -d db
docker compose exec -T db pg_isready -U postgres -d ceap_oltp
```

Quando `pg_isready` informar que aceita conexões, aplique pelo executor existente. Ele aplica as migrations pendentes em ordem e registra cada uma em `schema_migrations`:

```powershell
docker compose run --rm --no-deps -e DATABASE_URL=postgresql://postgres:postgres@db:5432/ceap_oltp ingestion python scripts/run_migrations.py
```

Na primeira execução, se a imagem de ingestão ainda não estiver construída, execute antes `docker compose build ingestion`. Se a 006 já estiver registrada, o executor ainda aplica a 005 pendente; as permissões existentes em `alerta` continuam intactas. Em instalação nova, a 005 cria os grupos e a 006 os reutiliza.

Alternativa para um banco que **já tem 001 a 004**, inclusive com a 006 aplicada: executar somente a 005 em uma transação. Esse comando não registra a execução em `schema_migrations`; uma execução posterior do runner a reaplicará com segurança.

```powershell
Get-Content -Raw -Encoding UTF8 migrations/005_controle_acesso.sql | docker compose exec -T db psql -X -v ON_ERROR_STOP=1 --single-transaction -U postgres -d ceap_oltp
if ($LASTEXITCODE -ne 0) { throw 'Falha ao aplicar a migration 005' }
```

No Bash, o equivalente é:

```bash
docker compose exec -T db psql -X -v ON_ERROR_STOP=1 --single-transaction -U postgres -d ceap_oltp < migrations/005_controle_acesso.sql
```

### Associar usuários reais

O administrador cria logins individuais e associa cada um a um único perfil. A migration não cria usuários de demonstração nem senhas. Exemplo em uma sessão administrativa do `psql`:

```sql
CREATE ROLE investigador LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT ceap_auditor TO investigador;
CREATE ROLE leitor_bi LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT ceap_consulta TO leitor_bi;
-- No psql, definir as senhas interativamente, sem inclui-las no script:
\password investigador
\password leitor_bi
```

Para testar autenticação real no ambiente Docker, use TCP e informe a senha quando solicitado:

```powershell
docker compose exec db psql -X -h 127.0.0.1 -U investigador -d ceap_oltp -W
docker compose exec db psql -X -h 127.0.0.1 -U leitor_bi -d ceap_oltp -W
```

No primeiro usuário, `SELECT cpf FROM public.parlamentar LIMIT 1;` é permitido. No segundo, a mesma consulta deve retornar `permission denied for table parlamentar` (SQLSTATE `42501`), enquanto `SELECT * FROM public.v_fornecedor_publico LIMIT 5;` funciona. O login de serviço `ceap_etl_reverso` já é criado pela 006 como membro de `ceap_pipeline`.

## 4. Demonstração automatizada e reproduzível

O script abaixo usa dados sintéticos e três identidades `LOGIN` sem privilégios administrativos. `SET SESSION AUTHORIZATION` muda **tanto `session_user` quanto `current_user`**; assim, a consulta é verificada com as permissões do usuário demonstrado. Somente o administrador inicial pode alternar essas identidades. Isso testa autorização; o teste de senha/TCP é o da seção anterior.

Pré-requisitos: migrations 001 a 006 aplicadas, conexão administrativa e nomes `e4_demo_*` ainda não usados. Execute preferencialmente em banco descartável. Tudo é feito dentro de `BEGIN`/`ROLLBACK`, inclusive usuários, funções de teste e dados; os testes de `nextval` avançam sequências, pois contadores não são transacionais. Se houver uma falha inesperada, `ON_ERROR_STOP` encerra o `psql` com código diferente de zero e a desconexão desfaz a transação.

Salve o bloco a seguir como `validar_acesso.sql` em uma pasta temporária e execute:

```powershell
Get-Content -Raw -Encoding UTF8 "$env:TEMP/validar_acesso.sql" | docker compose exec -T db psql -X -v ON_ERROR_STOP=1 -U postgres -d ceap_oltp
if ($LASTEXITCODE -ne 0) { throw 'Validacao de acesso falhou' }
```

Ou extraia automaticamente o bloco marcado deste documento, sem criar um terceiro arquivo versionado:

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
\pset pager off
BEGIN;

CREATE ROLE e4_demo_auditor LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE e4_demo_consulta LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE e4_demo_pipeline LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT ceap_auditor TO e4_demo_auditor;
GRANT ceap_consulta TO e4_demo_consulta;
GRANT ceap_pipeline TO e4_demo_pipeline;

-- Funcoes de teste SECURITY INVOKER: executam com os privilegios do chamador.
-- Criadas apenas nesta transacao; nao fazem parte da migration.
CREATE FUNCTION public.e4_exigir(ok boolean, caso text) RETURNS void
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog AS $$
BEGIN
    IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'FALHOU: %', caso; END IF;
    RAISE NOTICE 'OK: %', caso;
END $$;
CREATE FUNCTION public.e4_negar(comando text) RETURNS void
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog AS $$
BEGIN
    BEGIN
        EXECUTE comando;
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'NEGADO (42501): %', comando;
        RETURN;
    END;
    RAISE EXCEPTION 'ACESSO INDEVIDO: %', comando;
END $$;
GRANT EXECUTE ON FUNCTION public.e4_exigir(boolean, text), public.e4_negar(text)
    TO ceap_pipeline, ceap_auditor, ceap_consulta;

INSERT INTO public.parlamentar (id_deputado, nome_parlamentar, cpf, nu_carteira_parlamentar)
VALUES (-100010, 'PARLAMENTAR TESTE E4', '12345678901', 'CARTEIRA TESTE');
INSERT INTO public.categoria_despesa (num_subcota, descricao) VALUES (-100010, 'TESTE E4');
INSERT INTO public.fornecedor (id_fornecedor, cnpj_cpf, razao_social) VALUES
    (-100010, '12345678901', 'PESSOA TESTE 12345678901'),
    (-100011, '123.456.789-01', 'PESSOA TESTE 123.456.789-01'),
    (-100012, '12.345.678/0001-90', 'EMPRESA TESTE 12345678000190'),
    (-100013, NULL, 'SEM DOCUMENTO'),
    (-100014, 'desconhecido', 'DOCUMENTO INVALIDO');
INSERT INTO public.despesa_ceap (id_despesa, id_deputado, id_fornecedor, num_subcota,
    codigo_legislatura, valor_documento, valor_liquido, mes_competencia, ano_competencia, passageiro)
VALUES (-100010, -100010, -100010, -100010, 57, 100, 100, 1, 2026, 'PASSAGEIRO TESTE');
CREATE TABLE public.e4_demo_tabela_futura (segredo text);
ALTER TABLE public.parlamentar ADD COLUMN e4_demo_coluna_futura text;

SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
FROM pg_roles WHERE rolname IN ('ceap_pipeline', 'ceap_auditor', 'ceap_consulta') ORDER BY rolname;
SELECT public.e4_exigir(NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname IN ('ceap_pipeline', 'ceap_auditor', 'ceap_consulta')
    AND (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
), 'grupos sem login ou atributos administrativos');

-- A mesma coluna, com um usuario autorizado e outro sem acesso.
SET SESSION AUTHORIZATION e4_demo_auditor;
SELECT session_user, current_user, cpf FROM public.parlamentar WHERE id_deputado = -100010;
SELECT public.e4_exigir((SELECT cpf = '12345678901' FROM public.parlamentar
    WHERE id_deputado = -100010), 'auditor le CPF completo');
SELECT public.e4_exigir((SELECT passageiro = 'PASSAGEIRO TESTE' FROM public.despesa_ceap
    WHERE id_despesa = -100010), 'auditor le passageiro');
SELECT public.e4_exigir((SELECT cnpj_cpf = '12345678901' FROM public.fornecedor
    WHERE id_fornecedor = -100010), 'auditor le fornecedor original');
SELECT public.e4_negar('SELECT * FROM public.stg_ceap_raw');
SELECT public.e4_negar('UPDATE public.parlamentar SET nome_parlamentar = nome_parlamentar WHERE false');
SELECT public.e4_negar('DELETE FROM public.despesa_ceap WHERE false');
RESET SESSION AUTHORIZATION;

SET SESSION AUTHORIZATION e4_demo_consulta;
SELECT session_user, current_user, nome_parlamentar FROM public.parlamentar WHERE id_deputado = -100010;
SELECT public.e4_exigir((SELECT nome_parlamentar = 'PARLAMENTAR TESTE E4' FROM public.parlamentar
    WHERE id_deputado = -100010), 'consulta le coluna publica');
SELECT * FROM public.v_fornecedor_publico WHERE id_fornecedor BETWEEN -100014 AND -100010
ORDER BY id_fornecedor DESC;
SELECT public.e4_exigir((SELECT count(*) = 2 FROM public.v_fornecedor_publico
    WHERE id_fornecedor IN (-100010, -100011)
    AND cnpj_cpf_exibicao = '***.456.789-**' AND razao_social = 'PESSOA TESTE ***'),
    'CPF cru e formatado mascarados no documento e no nome');
SELECT public.e4_exigir((SELECT cnpj_cpf_exibicao = '12.345.678/0001-90'
    AND razao_social = 'EMPRESA TESTE 12345678000190' FROM public.v_fornecedor_publico
    WHERE id_fornecedor = -100012), 'CNPJ preservado');
SELECT public.e4_exigir((SELECT cnpj_cpf_exibicao IS NULL FROM public.v_fornecedor_publico
    WHERE id_fornecedor = -100013), 'documento nulo preservado');
SELECT public.e4_exigir((SELECT cnpj_cpf_exibicao = '[documento restrito]' FROM public.v_fornecedor_publico
    WHERE id_fornecedor = -100014), 'documento desconhecido nao vaza');
SELECT public.e4_exigir((SELECT sum(d.valor_liquido) = 100 FROM public.despesa_ceap d
    JOIN public.parlamentar p USING (id_deputado)
    JOIN public.v_fornecedor_publico f USING (id_fornecedor)
    WHERE d.id_despesa = -100010), 'join e agregacao de BI funcionam');
SELECT public.e4_negar('SELECT cpf FROM public.parlamentar');
SELECT public.e4_negar('SELECT nu_carteira_parlamentar FROM public.parlamentar');
SELECT public.e4_negar('SELECT passageiro FROM public.despesa_ceap');
SELECT public.e4_negar('SELECT * FROM public.parlamentar');
SELECT public.e4_negar('SELECT * FROM public.despesa_ceap');
SELECT public.e4_negar('SELECT nome_parlamentar FROM public.parlamentar WHERE cpf IS NOT NULL');
SELECT public.e4_negar('SELECT cnpj_cpf FROM public.fornecedor');
SELECT public.e4_negar('SELECT razao_social FROM public.fornecedor');
SELECT public.e4_negar('SELECT * FROM public.stg_ceap_raw');
SELECT public.e4_negar('SELECT * FROM public.schema_migrations');
SELECT public.e4_negar('SELECT * FROM public.cdc_consumer_checkpoint');
SELECT public.e4_negar('SELECT e4_demo_coluna_futura FROM public.parlamentar');
SELECT public.e4_negar('SELECT * FROM public.e4_demo_tabela_futura');
SELECT public.e4_negar('INSERT INTO public.categoria_despesa VALUES (-100011, ''INDEVIDO'')');
SELECT public.e4_negar('UPDATE public.v_fornecedor_publico SET id_fornecedor = id_fornecedor WHERE false');
SELECT public.e4_negar('DELETE FROM public.despesa_ceap WHERE false');
SELECT public.e4_negar('TRUNCATE public.stg_ceap_raw');
SELECT public.e4_negar('SELECT nextval(''public.fornecedor_id_fornecedor_seq'')');
SELECT public.e4_negar('CREATE TABLE public.e4_demo_indevida (id integer)');
SELECT public.e4_negar('CREATE TEMP TABLE e4_demo_temp (id integer)');
SELECT public.e4_negar('SET ROLE ceap_auditor');
SELECT public.e4_negar('SET ROLE ceap_pipeline');
SELECT public.e4_negar('SELECT * FROM alerta.vw_fila_auditoria');
RESET SESSION AUTHORIZATION;

SET SESSION AUTHORIZATION e4_demo_pipeline;
INSERT INTO public.parlamentar (id_deputado, nome_parlamentar) VALUES (-100011, 'CARGA TESTE');
UPDATE public.parlamentar SET nome_parlamentar = 'CARGA ATUALIZADA' WHERE id_deputado = -100011;
INSERT INTO public.fornecedor (cnpj_cpf, razao_social) VALUES (NULL, 'CARGA TESTE E4');
INSERT INTO public.stg_ceap_raw (txNomeParlamentar) VALUES ('STAGING TESTE E4');
SELECT public.e4_exigir(EXISTS (SELECT 1 FROM public.stg_ceap_raw
    WHERE txNomeParlamentar = 'STAGING TESTE E4'), 'pipeline escreve e le staging');
TRUNCATE public.stg_ceap_raw;
INSERT INTO public.cdc_consumer_checkpoint (consumer_id, last_lsn) VALUES ('e4_demo', '0/0')
ON CONFLICT (consumer_id) DO UPDATE SET last_lsn = EXCLUDED.last_lsn;
SELECT public.e4_negar('DELETE FROM public.despesa_ceap WHERE false');
SELECT public.e4_negar('UPDATE public.despesa_ceap SET valor_liquido = 0 WHERE false');
SELECT public.e4_negar('SELECT * FROM public.schema_migrations');
SELECT public.e4_negar('CREATE TABLE public.e4_demo_indevida (id integer)');
SELECT public.e4_negar('SELECT setval(''public.fornecedor_id_fornecedor_seq'', 1)');

-- Integração: os GRANT abaixo foram aplicados exclusivamente pela migration 006.
INSERT INTO alerta.desvio_parlamentar (referencia_dados, id_deputado, nome_parlamentar,
    sigla_uf, posicao_ranking, desvio_acumulado, desvio_relativo, meses_acima_mediana,
    meses_com_gasto, janela_inicio, janela_fim)
VALUES ('2026-01-01Z', -100010, 'PARLAMENTAR TESTE E4', 'DF', 1, 100, 0.5, 1, 1,
    '2026-01-01', '2026-01-31');
INSERT INTO alerta.execucao (referencia_dados, linhas_recebidas, linhas_novas, origem)
VALUES ('2026-01-01Z', 1, 1, 'e4_demo');
SELECT public.e4_negar('SELECT * FROM alerta.tratamento');
RESET SESSION AUTHORIZATION;

SET SESSION AUTHORIZATION e4_demo_auditor;
SELECT count(*) AS itens_na_fila FROM alerta.vw_fila_auditoria;
INSERT INTO alerta.tratamento (id_deputado, referencia_dados, situacao, observacao)
VALUES (-100010, '2026-01-01Z', 'em_analise', 'TESTE E4');
SELECT public.e4_exigir(EXISTS (SELECT 1 FROM alerta.tratamento
    WHERE id_deputado = -100010 AND registrado_por = 'e4_demo_auditor'),
    '006 preservada: auditor registra decisao com autoria da sessao');
SELECT public.e4_negar('UPDATE alerta.tratamento SET observacao = ''INDEVIDO'' WHERE false');
SELECT public.e4_negar('INSERT INTO alerta.tratamento (id_deputado, referencia_dados, situacao, registrado_por) VALUES (-100010, ''2026-01-01Z'', ''em_analise'', ''outro_usuario'')');
RESET SESSION AUTHORIZATION;

ROLLBACK;
\echo VALIDACAO E4 CONCLUIDA: acessos permitidos e negados conforme a matriz.
```
<!-- fim-validacao-sql -->

## 5. Evidências e resultado da validação

Validação executada em **24/11/2026**, com **PostgreSQL 16.14**, imagem `postgres:16-alpine`, em container descartável, separado do volume da plataforma. Foram usados apenas dados sintéticos. O bloco da seção 4 passou pelo `psql` com `ON_ERROR_STOP=1`, código de saída **0**, **12 asserções positivas** e **34 operações recusadas com SQLSTATE `42501`**, além dos INSERT/UPDATE/TRUNCATE autorizados. A transação terminou em `ROLLBACK`.

Trechos da saída efetivamente obtida:

```text
  session_user   |  current_user   |     cpf
-----------------+-----------------+-------------
 e4_demo_auditor | e4_demo_auditor | 12345678901

   session_user   |   current_user   |   nome_parlamentar
------------------+------------------+----------------------
 e4_demo_consulta | e4_demo_consulta | PARLAMENTAR TESTE E4

 id_fornecedor |         razao_social         |  cnpj_cpf_exibicao
---------------+------------------------------+----------------------
       -100010 | PESSOA TESTE ***             | ***.456.789-**
       -100011 | PESSOA TESTE ***             | ***.456.789-**
       -100012 | EMPRESA TESTE 12345678000190 | 12.345.678/0001-90
       -100013 | SEM DOCUMENTO                |
       -100014 | DOCUMENTO INVALIDO           | [documento restrito]

NOTICE:  NEGADO (42501): SELECT cpf FROM public.parlamentar
NOTICE:  NEGADO (42501): SELECT nu_carteira_parlamentar FROM public.parlamentar
NOTICE:  NEGADO (42501): SELECT passageiro FROM public.despesa_ceap
NOTICE:  NEGADO (42501): SELECT * FROM public.stg_ceap_raw
NOTICE:  NEGADO (42501): SELECT e4_demo_coluna_futura FROM public.parlamentar
NOTICE:  NEGADO (42501): SET ROLE ceap_auditor
NOTICE:  NEGADO (42501): SELECT * FROM alerta.vw_fila_auditoria
NOTICE:  OK: 006 preservada: auditor registra decisao com autoria da sessao
ROLLBACK
VALIDACAO E4 CONCLUIDA: acessos permitidos e negados conforme a matriz.
```

Também foram abertas conexões **reais por TCP**, com logins de teste, senhas aleatórias e associação a um único grupo. As senhas não foram registradas. Resultado:

```text
TCP auditor:  session_user=e4_tcp_auditor, current_user=e4_tcp_auditor,
              cpf=12345678901
TCP consulta: session_user=e4_tcp_consulta, current_user=e4_tcp_consulta,
              cnpj_cpf_exibicao=***.456.789-**, razao_social=PESSOA TESTE ***
NEGADO e4_tcp_consulta SQLSTATE=42501: SELECT cpf FROM public.parlamentar
NEGADO e4_tcp_consulta SQLSTATE=42501: SET ROLE ceap_auditor
NEGADO e4_tcp_consulta SQLSTATE=42501: SELECT * FROM alerta.vw_fila_auditoria
NEGADO e4_tcp_auditor SQLSTATE=42501: UPDATE public.parlamentar SET nome_parlamentar=nome_parlamentar WHERE false
```

Verificações adicionais executadas:

| Cenário | Resultado |
| --- | --- |
| Banco vazio: runner aplica 001 → 006 | Seis migrations registradas, sem erro |
| Segunda execução do runner | Seis migrations ignoradas por já estarem aplicadas |
| Reexecutar o SQL da 005 duas vezes, com a 006 presente | Demonstração completa continua passando |
| Conceder previamente SELECT em tabela/CPF a `PUBLIC` e consulta, staging ao auditor e UPDATE de despesas ao pipeline; reaplicar 005 | Concessões excessivas removidas, demonstração completa passa |
| Outro banco com 001–004 e 006 registradas; executar o runner | 005 aplicada apesar da numeração anterior; ACLs de `alerta` idênticas antes/depois |
| Grupo consulta herdando auditor | 005 recusa a configuração; transação desfeita |
| Seis transformações SQL reais de `scripts/ingest_ceap.py`, executadas duas vezes como login de pipeline | Inserts, upserts e uso das sequências permitidos; limpeza da staging permitida |
| Nova tabela e nova coluna criadas pelo administrador | Consulta sem acesso automático |
| Rollback da demonstração | Dados, funções auxiliares, coluna extra e usuários de teste removidos |

Para conferir as concessões sem criar dados, execute esta consulta administrativa:

```sql
SELECT r AS papel,
    has_column_privilege(r, 'public.parlamentar', 'cpf', 'SELECT') AS le_cpf,
    has_column_privilege(r, 'public.parlamentar', 'nome_parlamentar', 'SELECT') AS le_nome,
    has_table_privilege(r, 'public.fornecedor', 'SELECT') AS fornecedor_original,
    has_table_privilege(r, 'public.v_fornecedor_publico', 'SELECT') AS fornecedor_mascarado,
    has_table_privilege(r, 'public.stg_ceap_raw', 'SELECT') AS le_staging
FROM unnest(ARRAY['ceap_pipeline', 'ceap_auditor', 'ceap_consulta']) AS r;
```

Resultado observado (`t` = permitido, `f` = negado):

```text
     papel     | le_cpf | le_nome | fornecedor_original | fornecedor_mascarado | le_staging
---------------+--------+---------+---------------------+----------------------+-----------
 ceap_pipeline | t      | t       | t                   | t                    | t
 ceap_auditor  | t      | t       | t                   | t                    | f
 ceap_consulta | f      | t       | f                   | t                    | f
```

Para colunas, use `has_column_privilege`: `has_table_privilege(..., 'SELECT')` sozinho não representa uma concessão parcial. As funções de catálogo complementam a evidência; o teste principal executa as consultas como cada usuário.

## 6. Limites e integração com as demais issues

- Esta entrega controla o **PostgreSQL**. Roles SQL não protegem arquivos DuckDB, Delta, CSV ou volumes do painel. A separação de arquivos restritos/consumo continua sendo a implementação prevista em LGPD.
- O apêndice A.1 de LGPD propõe remover CPF e passageiro **depois** de adaptar os scripts de ingestão. Como eles ainda referenciam essas colunas, a 005 os mantém na zona restrita. Não se deve afirmar que houve eliminação física desses dados.
- A ingestão do `docker-compose.yml` ainda conecta como `postgres` para aplicar migrations, fazer manutenção e executar testes de CDC. A 005 não troca credenciais do Compose. O ETL reverso já usa `ceap_etl_reverso`, membro de `ceap_pipeline`. Superusuários e donos dos objetos continuam sendo administradores e não servem como prova do recorte.
- Só a migration 006 concede permissões em `alerta`. A 005 pode ser aplicada depois dela sem retirar o acesso à fila, a publicação ou o registro de decisões.
- Arquivos desta issue: `migrations/005_controle_acesso.sql` e `docs/controle-de-acesso.md`. Título para o menu da documentação: **Controle de acesso com privilégio mínimo**. A integração em README/MkDocs pertence à issue #14; a demonstração da seção 4 pode ser usada na defesa da issue #13.
