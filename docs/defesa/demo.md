# Defesa da E4 — demo ao vivo (4 minutos)

> Parte 5 do [roteiro](roteiro.md). Mostra a mesma métrica em dois consumidores, o caminho dela até a
> fonte e o recorte de acesso. Todos os comandos rodam na raiz do repositório, com a plataforma no ar.

## Antes da defesa (não fazer ao vivo)

A subida leva cerca de 8 minutos. Fazer antes e deixar no ar:

```bash
git switch main && git pull
docker compose up --build -d
docker compose wait e3-pipeline     # termina com código 0
```

**Se a pipeline falhar na API da Câmara** (`ApiIndisponivel` ou HTTP 429 em `bronze__camara_deputado_historico`):
a API limita o número de requisições, e cada subida consulta o histórico de ~600 deputados. Aconteceu
num teste de 25/11/2026, depois de várias subidas seguidas. A plataforma falha sem publicar dado pela
metade. Duas saídas:

1. Esperar alguns minutos e rodar só a pipeline da E3 de novo:
   ```bash
   docker compose up -d --no-deps e3-pipeline && docker compose wait e3-pipeline
   docker compose up -d --no-deps e3-dagster e3-painel
   ```
2. Usar o histórico já baixado numa subida anterior (modo degradado explícito, ADR-0006). Por isso,
   **subir a plataforma pelo menos uma vez antes do dia da defesa**, para o cache existir:
   ```bash
   docker compose run --rm --no-deps -e CEAP_USAR_CACHE=1 e3-pipeline
   docker compose up -d --no-deps e3-dagster e3-painel
   ```

Deixar abertos:

- uma aba do navegador no painel: <http://localhost:8501>;
- uma aba no site, na [linhagem, exemplo 1](https://taybalau.github.io/sbd2-g8-ceap/linhagem/#exemplo-1-o-desvio-acumulado-do-painel-até-o-csv);
- um terminal na raiz do repositório, com fonte grande.

> Os números abaixo são da subida de 26/11/2026. A Câmara regera os CSVs (no dia 26 o líder mudou de
> Pompeo de Mattos para Zé Trovão), então conferir no dia e ajustar a fala se mudarem. O que não pode
> mudar é o **mesmo número nas duas telas**.

## Passo 1 — Painel: quem lidera e a prova (1 min)

No painel, bloco 1 ("Parlamentares com maior desvio acima da mediana"):

- O selo verde no topo: **51 testes de dados** no último build, nenhum reprovado.
- **Zé Trovão (PL-SC)** lidera: R$ 43.188/mês contra R$ 26.902 da mediana da UF (+61%), acumulando
  **R$ 488.566** acima da mediana.
- No bloco 2, **PSC** tem o maior desvio por deputado-mês (R$ 4.632), e o destaque mostra os
  **R$ 29.028.199** que iriam para o partido errado sem o SCD tipo 2.
- No bloco 3, com o líder selecionado: a linha mês a mês mostra **30 de 30 meses** acima da mediana
  (desvio constante, não um pico). Nos maiores lançamentos, o primeiro é um **recibo de pessoa física**
  (R$ 9.000, CPF mascarado) e aparece **sem link**: o recibo traz o CPF completo (LGPD).
- Trocar o parlamentar para **Pompeo de Mattos (PDT-RS)**, 3º: em Divulgação da atividade parlamentar,
  clicar em **abrir na Câmara** no primeiro lançamento. Abre a nota da **NOVOGRAF** de **R$ 46.500**
  (09/08/2024).

**Fala:** "O painel não calcula nada: lê a camada semântica, e cada lançamento de empresa leva ao
documento publicado pela Câmara. Agora o mesmo número em outro sistema."

## Passo 2 — Fila do auditor: os mesmos 15 (1 min)

```bash
docker compose exec -T db psql -U postgres -d ceap_oltp -c \
  "select posicao_ranking as pos, nome_parlamentar, partido_atual as partido, sigla_uf as uf,
          desvio_acumulado, situacao
   from alerta.vw_fila_auditoria"
```

**Esperado:** 15 linhas, de Zé Trovão (R$ 488.565,96) a Juliana Cardoso, **na mesma ordem do
painel**, todas `pendente`.

Registrar uma decisão como auditor e mostrar que ela não pode ser alterada (tudo desfeito no fim):

```bash
docker compose exec -T db psql -U postgres -d ceap_oltp <<'SQL'
BEGIN;
SET ROLE ceap_auditor;
INSERT INTO alerta.tratamento (id_deputado, referencia_dados, situacao, observacao)
SELECT id_deputado, referencia_dados, 'em_analise', 'pedido de notas ao gabinete'
FROM alerta.vw_fila_auditoria ORDER BY posicao_ranking LIMIT 1;
SELECT posicao_ranking, nome_parlamentar, situacao, registrado_em::timestamp(0)
FROM alerta.vw_fila_auditoria WHERE situacao <> 'pendente';
UPDATE alerta.tratamento SET situacao = 'sem_irregularidade';   -- recusado
ROLLBACK;
SQL
```

**Esperado:** o líder aparece `em_analise`; o `UPDATE` é recusado (`permission denied`: o auditor só
insere decisões). **Fala:** "O auditor registra o que decidiu, com autoria e hora gravadas pelo banco,
e ninguém reescreve o histórico."

## Passo 3 — Linhagem: o número em cada camada (1 min)

Na aba do site, mostrar o diagrama do exemplo 1. Depois, conferir o número do líder em cada camada:

```bash
docker compose exec -T e3-painel python -c "
import duckdb; c = duckdb.connect('lakehouse/ceap.duckdb', read_only=True)
q = lambda s: c.execute(s).fetchone()[0]
i = q('select id_deputado from semantico.met_parlamentar where posicao_ranking = 1')
print('semantico.met_parlamentar   ', q(f'select round(desvio_acumulado, 2) from semantico.met_parlamentar where id_deputado = {i}'))
print('gold.mart_desvio_parlamentar', q(f'select round(desvio_acumulado, 2) from gold.mart_desvio_parlamentar where id_deputado = {i}'))
print('soma mês a mês (gold mensal)', q(f'''select round(sum(desvio_deputado_mes), 2) from (select distinct competencia, desvio_deputado_mes
    from gold.fct_gasto_mensal_parlamentar where id_deputado = {i} and is_competencia_comparavel)'''))
"
```

**Esperado:** o mesmo valor (488.565,96) nas três linhas. **Fala:** "Daqui até o `vlrLiquido` do CSV
da Câmara, cada passo está na página de linhagem."

## Passo 4 — Recorte de acesso (1 min)

Roda o roteiro de validação do [controle de acesso](../controle-de-acesso.md#demonstrar-acesso-permitido-e-negado):
cria dois usuários de teste, confere o que cada um vê e desfaz tudo.

```bash
awk '/^<!-- inicio-validacao-sql -->/{f=1; next} /^<!-- fim-validacao-sql -->/{f=0} f' docs/controle-de-acesso.md \
  | sed '/^```/d' \
  | docker compose exec -T db psql -X -v ON_ERROR_STOP=1 -U postgres -d ceap_oltp
```

**Esperado:** o auditor lê o CPF `12345678901`; a consulta pública vê `***.456.789-**`; oito
operações aparecem como `NEGADO (42501)`, inclusive ler a fila do auditor; no fim,
`VALIDACAO E4 CONCLUIDA`. **Fala:** "Cada papel vê só o que precisa."

## Plano B

Se a plataforma não subir ou um comando falhar, mostrar as evidências já gravadas no repositório:

| Passo | Evidência |
| :--- | :--- |
| 1 e 2 | `docs/e4.md`, seção 2 (fila igual à camada, mesmos 15 nomes) |
| 2 (falha do destino) | `orquestracao/evidencias/destino_fora.json` |
| 3 | página de [linhagem](https://taybalau.github.io/sbd2-g8-ceap/linhagem/) no site |
| 4 | `docs/controle-de-acesso.md`, seção "Evidências da implementação" |

## Depois da defesa

```bash
docker compose down        # mantém os dados
```
