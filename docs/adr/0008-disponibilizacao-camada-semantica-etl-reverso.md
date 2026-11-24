# 0008 — Disponibilizar o dado por uma camada semântica no dbt lida direto do warehouse, com ETL reverso por push para a fila do auditor no PostgreSQL

- **Status:** aceito
- **Data:** 2026-11-24
- **Decisores:** Squad G8
- **Detalhes de implementação:** [Entrega E4 — Disponibilização do dado](../e4.md) (issues #6 e #7)

## 1. Contexto

Na E3 a Gold respondia à pergunta de gestão, mas o painel terminava contas por conta própria (somas
por categoria, top 10 de fornecedores, o erro da sobrescrita dividido por dois, o corte de 5 deputados
por partido). A E4 traz um **segundo consumidor**, e a mesma métrica não pode sair com dois valores.

**Carga, com os números do domínio** (subida do zero em 2026-11-24):

| Item | Valor |
| :--- | ---: |
| Lançamentos no fato | 802.861 |
| Linhas lidas pelo painel por abertura (5 consultas) | 91.227 (84.936 de fornecedor × deputado) |
| Arquivo do warehouse (`lakehouse/ceap.duckdb`) | 129 MiB |
| Atualização da fonte | diária (agenda às 06:00, SLA de 26 h) |

| Consumidor | O que precisa | Escreve? |
| :--- | :--- | :---: |
| **Painel** (Streamlit, Squad e monitoria) | as 5 visões da pergunta de gestão, lidas a cada abertura (cache de 5 min) | não |
| **Auditor** (sistema operacional, PostgreSQL da E1) | os 15 parlamentares em alerta, uma vez por dia, e **registrar a decisão** sobre cada um | **sim** |

**Restrições não funcionais:** subir do zero com um comando; uma métrica com **uma definição só**; o
DuckDB aceita **um processo escritor** por vez (o dbt reconstrói o arquivo a cada build); privilégio
mínimo e nenhum dado pessoal desnecessário fora da zona restrita (análise de LGPD); máquina de 7 a 8 GB.

## 2. Alternativas consideradas

A disponibilização tem três escolhas. Em cada uma, a opção nula é a primeira.

**2.1 Onde a métrica é definida**

- **A. Opção nula — cada consumidor calcula** a partir da Gold (o que a E3 fazia).
- **B. Views escritas à mão** no banco, fora do dbt: uma definição só, mas sem contrato de esquema,
  sem teste e sem documentação ligada ao código.
- **C. Camada semântica no dbt (escolhida):** 5 views no schema `semantico`, com fórmula, unidade,
  grão e consumidores no `meta` do `_semantic.yml`, contrato de esquema (`contract: enforced`) e
  testes de consistência entre as views.
- **D. dbt Semantic Layer (MetricFlow):** métricas declaradas e SQL gerado pela ferramenta. Não foi
  prototipada (ver 3.1).

**2.2 De onde o consumidor lê**

- **A. Opção nula — cópia em arquivo** (CSV exportado a cada build).
- **B. Cópia em Parquet** exportada a cada build.
- **C. Warehouse, com as métricas materializadas como tabelas.**
- **D. Warehouse, views (escolhida para o painel).**
- **E. Federação de consultas:** o consumidor junta, na hora, o warehouse e o PostgreSQL numa consulta
  só, sem cópia (DuckDB com `ATTACH` do PostgreSQL).

**2.3 Como o alerta chega ao auditor**

- **A. Opção nula — CSV agendado** com os 15 nomes.
- **B. Pull / federação:** o auditor consulta o warehouse e as suas decisões na hora (2.2-E).
- **C. Push diário para uma tabela no PostgreSQL (escolhida)**, logo depois do dbt, com retry.

## 3. Medição

Todas as medições usam o volume real, 20 repetições e conexão nova a cada leitura.

**3.1 Definição da métrica.** A opção A já existiu: na E3 o painel fazia 4 contas que ninguém mais
conferia. Na C, os testes `assert_semantico_gasto_consistente` e `assert_semantico_desvio_consistente`
reprovam o `dbt build` se o gasto ou o desvio divergirem em mais de R$ 0,01 entre as views, e
`scripts/verificar_consumo_duplo.py` confere os 12 números exibidos no painel contra a camada. Trocar a
fonte do painel para a camada não mudou nenhum número. A B tem o mesmo SQL que a C, mas perderia
esses testes e o contrato. A D não foi prototipada: as métricas centrais (desvio contra a **mediana
mensal da UF**, z robusto com MAD, HHI, `rank()` por deputado) são janelas e agregações aninhadas
que o MetricFlow não expressa como métrica simples. Além disso, a API que serve as métricas para
outras ferramentas só existe no dbt Cloud. Isso é argumento, não medição, e fica como ponto fraco
deste ADR.

**3.2 De onde o consumidor lê** (painel: as 5 consultas que ele faz).

| Caminho | Leitura (mediana · p90) | Custo de manter | Espaço extra | Defasagem | Acoplamento |
| :--- | ---: | ---: | ---: | :--- | :--- |
| A. Cópia em CSV (nula) | 148 · 162 ms | 0,17 s por exportação | 11,7 MiB | até a próxima exportação | segundo lugar onde a métrica mora; precisa de agenda e monitoramento |
| B. Cópia em Parquet | 71 · 77 ms | 0,25 s por exportação | 6,5 MiB | até a próxima exportação | idem |
| C. Warehouse, tabelas | 83 · 86 ms | 3,0 s por build | 6,3 MiB | até o próximo build | nenhum além do warehouse |
| **D. Warehouse, views** | **217 · 251 ms** | **nenhum** | **nenhum** | **nenhuma** | nenhum além do warehouse |
| E. Federação (fila do auditor) | 135 · 143 ms (conexão nova) | nenhum | nenhum | nenhuma | precisa do warehouse **e** do PostgreSQL no ar ao mesmo tempo; não lê durante o build (3.3) |

**3.3 Como o alerta chega ao auditor** (os mesmos 15 parlamentares pelos três caminhos).

| | A. CSV agendado (nula) | B. Federação | **C. Push para o PostgreSQL** |
| :--- | :--- | :--- | :--- |
| Publicar | 26 ms | — (não publica) | **38 ms**, uma vez por dia |
| Auditor ler a fila (mediana, conexão nova) | 1 ms | 135 ms (4 ms com a conexão mantida aberta, o que trava o dbt) | **13 a 21 ms** (duas medições) |
| Mesmos 15 parlamentares que a camada semântica | sim | sim | **sim** |
| Decisão do auditor sobrevive à publicação seguinte | **não**: o arquivo é reescrito | sim (as decisões ficam no PostgreSQL) | **sim** |
| Histórico de quem entrou no alerta e quando | não | **não**: a fila é recalculada, o retrato de ontem some | **sim**: um retrato por publicação |
| Leitura enquanto um processo escreve no warehouse (o dbt, a cada build) | sim | **não**: `Could not set lock on file`; o auditor fica sem fila | **sim**: leu as 15 linhas |
| Acesso que o auditor precisa | o arquivo | **o warehouse inteiro** (129 MiB): `silver`, `gold`, `semantico` e `auditoria`, com 6 colunas de documento de fornecedor, inclusive CPF completo | **só o schema `alerta`** (`GRANT` por role) |
| Registro protegido contra alteração | não | parcial | **sim**: *insert-only*, `UPDATE` recusado |

**Destino fora do ar (push):** com o PostgreSQL derrubado, a publicação falhou depois de 3 tentativas
(espera de 2, 4 e 8 s); a Gold manteve o mesmo hash e a fila ficou com as 15 linhas anteriores, nenhuma
pela metade. Com o destino de volta, a republicação gravou 0 linhas novas (idempotente) e o asset check
confirmou fila igual à camada.

**Como reproduzir** (com `docker compose up --build -d` e `docker compose wait e3-pipeline`):

```bash
# 3.2 A a D: leitura do warehouse e das cópias -> docs/evidencias/e4_leitura_semantica.json
docker compose run --rm --no-deps -v ./docs:/app/docs -v ./scripts:/app/scripts \
    e3-pipeline python scripts/medir_leitura_semantica.py 20

# 3.3 A e C: CSV agendado x push -> docs/evidencias/e4_etl_reverso_opcao_nula.json
docker compose run --rm --no-deps -e DB_USER=postgres -e DB_PASSWORD=postgres \
    -v ./docs:/app/docs -v ./etl_reverso:/app/etl_reverso \
    e3-pipeline bash -c "cd etl_reverso && python comparar_opcao_nula.py 20"

# destino fora do ar -> orquestracao/evidencias/destino_fora.json
docker compose run --rm --no-deps -v ./orquestracao/evidencias:/app/orquestracao/evidencias \
    e3-pipeline python orquestracao/demo_falhas.py destino_fora
```

**Federação (3.2-E e 3.3-B):** medida em 2026-11-24 com DuckDB 1.3.2 e a extensão `postgres`. O
script não fica no repositório de código: salve o bloco abaixo como `medir_federacao.py` e rode

```bash
docker compose run --rm --no-deps -T -e DB_USER=postgres -e DB_PASSWORD=postgres \
    e3-pipeline python - 20 < medir_federacao.py
```

Ele mede as duas leituras da fila, confere se os 15 parlamentares são os mesmos, lista o que o
consumidor federado enxerga no warehouse e tenta ler a fila enquanto outro processo segura o
arquivo para escrita, como o dbt faz a cada build.

<details markdown>
<summary><code>medir_federacao.py</code></summary>

```python
"""ADR-0008: fila do auditor por push (tabela no PostgreSQL) x federação (DuckDB lê lakehouse + PostgreSQL na hora)."""
import json, os, statistics, subprocess, sys, time
import duckdb, psycopg

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
LAKE = "/app/lakehouse/ceap.duckdb"
PG = dict(host=os.environ["DB_HOST"], port=os.environ["DB_PORT"], dbname=os.environ["DB_NAME"],
          user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"])
PG_DSN = " ".join(f"{k}={v}" for k, v in PG.items())

FILA_FEDERADA = """
with ultima as (
    select id_deputado, situacao, observacao, registrado_por, registrado_em,
           row_number() over (partition by id_deputado order by registrado_em desc, id_tratamento desc) as rn
    from pg.alerta.tratamento)
select p.posicao_ranking, p.id_deputado, p.nome_parlamentar, p.partido_atual, p.sigla_uf,
       p.desvio_acumulado, p.desvio_relativo, p.meses_acima_mediana, p.meses_com_gasto,
       coalesce(u.situacao, 'pendente') as situacao, u.observacao, u.registrado_por, u.registrado_em
from semantico.met_parlamentar p
left join ultima u on u.id_deputado = p.id_deputado and u.rn = 1
where p.em_alerta
order by p.posicao_ranking, p.id_deputado"""


def cronometrar(f):
    f()  # aquecimento
    t = []
    for _ in range(N):
        i = time.perf_counter(); f(); t.append((time.perf_counter() - i) * 1000)
    t.sort()
    return {"mediana_ms": round(statistics.median(t), 1), "p90_ms": round(t[int(0.9 * (len(t) - 1))], 1)}


def abrir_federado():
    con = duckdb.connect(LAKE, read_only=True)
    con.execute("LOAD postgres")
    con.execute(f"ATTACH '{PG_DSN}' AS pg (TYPE postgres, READ_ONLY)")
    return con


def ler_push():
    with psycopg.connect(**PG) as c:
        return c.execute("select * from alerta.vw_fila_auditoria").fetchall()


def ler_federado():
    con = abrir_federado()
    try:
        return con.execute(FILA_FEDERADA).fetchall()
    finally:
        con.execute("DETACH pg")
        con.close()


def main():
    duckdb.connect().execute("INSTALL postgres")
    push, fed = ler_push(), ler_federado()

    lat_push = cronometrar(ler_push)
    lat_fed_nova = cronometrar(ler_federado)
    quente = abrir_federado()
    lat_fed_aberta = cronometrar(lambda: quente.execute(FILA_FEDERADA).fetchall())
    quente.execute("DETACH pg")
    quente.close()
    resultado = {
        "medido_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "repeticoes": N,
        "ambiente": f"DuckDB {duckdb.__version__}, extensão postgres; PostgreSQL 16",
        "mesmos_parlamentares": [r[1] for r in push] == [r[1] for r in fed],
        "linhas": {"push": len(push), "federado": len(fed)},
        "latencia": {
            "push_tabela_postgres": lat_push,
            "federado_conexao_nova": lat_fed_nova,
            "federado_conexao_aberta": lat_fed_aberta,
        },
    }

    # Acoplamento 1: o que o consumidor federado enxerga ao abrir o arquivo do lakehouse
    con = duckdb.connect(LAKE, read_only=True)
    resultado["acesso_exigido"] = {
        "arquivo_mb": round(os.path.getsize(LAKE) / 2**20, 1),
        "schemas_visiveis": [r[0] for r in con.execute(
            "select schema_name from duckdb_tables() where not internal union "
            "select schema_name from duckdb_views() where not internal order by 1").fetchall()],
        "colunas_com_documento": [f"{r[0]}.{r[1]}.{r[2]}" for r in con.execute(
            "select schema_name, table_name, column_name from duckdb_columns() "
            "where column_name in ('documento_fornecedor', 'chave_fornecedor', 'cnpj_cpf', 'txtCNPJCPF', 'doc_socio') "
            "order by 1, 2, 3").fetchall()],
    }
    con.close()

    # Acoplamento 2: um processo escritor no lakehouse (é o que o dbt faz a cada build)
    escritor = subprocess.Popen([sys.executable, "-c",
        f"import duckdb, time; c = duckdb.connect('{LAKE}'); print('ok', flush=True); time.sleep(30)"],
        stdout=subprocess.PIPE, text=True)
    assert escritor.stdout.readline().strip() == "ok"
    try:
        try:
            ler_federado(); fed_durante = "leu"
        except Exception as e:
            fed_durante = f"falhou: {type(e).__name__}: {str(e).splitlines()[0][:160]}"
        try:
            push_durante = f"leu {len(ler_push())} linhas"
        except Exception as e:
            push_durante = f"falhou: {e}"
    finally:
        escritor.kill(); escritor.wait()
    resultado["durante_escrita_no_lakehouse"] = {"push": push_durante, "federado": fed_durante}

    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

</details>

## 4. Decisão

1. **As métricas são definidas uma vez, na camada semântica do dbt** (`semantico.*`, views com contrato
   e testes). Nenhum consumidor recalcula.
2. **O painel lê o warehouse direto, pelas views.** É o caminho mais lento medido (~130 ms a mais que as
   tabelas), mas o único sem cópia para manter e sem defasagem. Com cache de 5 minutos, 0,25 s não
   muda a experiência.
3. **O alerta chega ao auditor por push diário** para `alerta.desvio_parlamentar` no PostgreSQL, no fim
   do job `transformacao`, com 3 tentativas. Se o destino estiver fora do ar, o run falha visível no
   Dagster, a fila fica com o retrato anterior e o job `etl_reverso` republica sem refazer o dbt.

O CSV agendado bastaria se o auditor só **lesse** a lista. Ele precisa **registrar o que decidiu**, com
histórico e sem que o registro possa ser alterado; isso exige um banco transacional. A federação evita
a cópia e foi rápida o bastante (135 ms), mas foi descartada pelo acoplamento medido: o auditor
ficaria sem fila enquanto o dbt reconstrói o warehouse, precisaria ler o arquivo inteiro, com CPF de
pessoas físicas que ele não precisa ver, e perderia o histórico de quem entrou no alerta e quando.

## 5. Consequências

**O que ganhamos**
- O mesmo número em todos os consumidores, garantido por teste, e não por convenção.
- Uma métrica nova ou alterada é um diff no `.sql` e no `.yml`, e o catálogo da [E4](../e4.md) é
  gerado desse arquivo.
- O auditor tem uma fila com decisões, histórico e autoria gravada pelo banco, e acessa só o schema
  `alerta`, sem tocar no lakehouse.

**O que perdemos**
- Cada leitura do painel custa ~130 ms a mais que tabelas, porque as views refazem os agrupamentos.
- **O PostgreSQL voltou ao fluxo de dados**, como destino. Isso acrescenta uma migration (006), roles
  e um asset ao grafo, e torna menos absoluta a decisão do ADR-0004.
- A fila do auditor tem até um dia de defasagem em relação à camada semântica.
- A definição das métricas depende do dbt e do DuckDB. Um consumidor fora da rede do DuckDB não
  consegue ler a camada sem uma cópia.

**O que se torna irreversível**
- Os retratos e as decisões em `alerta.*` são *insert-only*: o que foi publicado ou decidido não é
  apagado. Abandonar o push não apaga esse histórico; ele teria de ser migrado.
- A interface pública do dado passa a ser o schema `semantico`, com contrato. Mudar ou remover uma
  coluna quebra o build de propósito e exige mudar os consumidores juntos.

## 6. Gatilho de revisão

Revisar esta decisão se **qualquer** uma destas condições ocorrer:

| Condição | Limiar | Hoje | O que fazer |
| :--- | ---: | ---: | :--- |
| Leitura do painel pela camada semântica (p90) | > 1 s | 251 ms | materializar as views como tabelas (3.2-C) |
| Consumidor fora da rede do DuckDB (outra equipe, outra nuvem) | 1 | 0 | publicar uma cópia em Parquet (3.2-B) a cada build |
| Frescor exigido pelo auditor | menor que diário | diário | publicar a cada ingestão intradiária ou avaliar federação (3.3-B) |
| Destinos do ETL reverso | > 2 sistemas | 1 | trocar o script por uma ferramenta de ETL reverso |
| Falhas seguidas da publicação | 3 dias | 0 | rever retry, alerta e a dependência do destino |
| Métricas na camada semântica | > 50 | 32 | prototipar o dbt Semantic Layer (2.1-D) |
