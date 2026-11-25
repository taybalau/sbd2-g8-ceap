# Defesa da E4 — roteiro de 20 minutos

> Material de ensaio da Squad (issue #13). Fica no repositório, fora do menu do site.
> Os slides ficam fora do repositório e seguem a ordem deste roteiro.
> Comandos da demo: [demo.md](demo.md) · Perguntas prováveis da banca: [perguntas.md](perguntas.md).

**Banca:** público técnico **e** de gestão. Regra do roteiro: cada parte técnica termina dizendo que
decisão aquilo permite tomar. Uma apresentação que serve só a uma das metades perde nota.

**Divisão das falas:** cada parte fica com quem fez a issue do assunto. As partes marcadas como
*sugestão* tratam de issues sem dono entre os apresentadores (#6, #7 e #11); a Squad confirma antes
do ensaio.

## Visão geral

| Tempo | Parte | Público | Quem fala | Issue de origem |
| :--- | :--- | :--- | :--- | :--- |
| 0:00–2:30 | 1. A pergunta e a decisão | gestão | Gabriel | #13 |
| 2:30–5:30 | 2. De onde vem cada número | misto | Amanda | #8 |
| 5:30–9:00 | 3. Como cada métrica é calculada | técnico | Filipe *(sugestão)* | #6 |
| 9:00–11:30 | 4. O resultado volta para quem age | misto | Taynara *(sugestão)* | #7 e #11 |
| 11:30–16:00 | 5. Demo ao vivo | misto | Gabriel | #13 e #10 |
| 16:00–18:00 | 6. Privacidade e riscos | gestão e técnico | Clara | #9 |
| 18:00–20:00 | 7. O que aprendemos e o que fica | gestão | Amanda | #12 |
| depois | Arguição | — | quem tratou do assunto | — |

---

## 1. A pergunta e a decisão (0:00–2:30) — Gabriel

**Slide:** a pergunta da E1 e uma frase sobre a decisão.

- A pergunta: *quais parlamentares e partidos da 57ª Legislatura gastam acima do padrão mensal da
  CEAP, e em quais categorias e fornecedores esse dinheiro se concentra?*
- **O que a plataforma permite decidir que antes não se decidia:** um auditor com tempo para olhar
  poucos casos sabe **quem investigar primeiro**. Recebe todo dia uma fila com os 15 parlamentares
  mais acima do padrão da própria UF, com a categoria que explica o desvio, e registra o que decidiu.
- Antes: dados públicos espalhados em CSVs anuais, com o partido sobrescrito pelo atual e sem
  comparação justa entre estados (o teto da cota muda por UF).
- **Desvio não é irregularidade:** é onde olhar primeiro.

## 2. De onde vem cada número (2:30–5:30) — Amanda

**Slide:** o diagrama de ponta a ponta da [linhagem](../linhagem.md#visão-de-ponta-a-ponta).

- Fonte pública (CSV anual da Câmara e API de histórico dos deputados) → Bronze → Silver → Gold →
  camada semântica → painel e fila do auditor no PostgreSQL.
- O [catálogo](../catalogo.md) tem as 39 tabelas da plataforma, com dono, origem e grão.
- Exemplo seguido até a fonte: o **desvio acumulado** da barra do painel volta, coluna por coluna,
  até o `vlrLiquido` do CSV da Câmara ([linhagem, exemplo 1](../linhagem.md#exemplo-1-o-desvio-acumulado-do-painel-até-o-csv)).
- **Para a gestão:** qualquer número do painel pode ser conferido até o documento público.

## 3. Como cada métrica é calculada (5:30–9:00) — Filipe *(sugestão)*

**Slide:** a fórmula do desvio e a tabela de granularidade.

- **Grão:** o fato é um lançamento publicado; a comparação é **deputado × mês contra a mediana dos
  deputados da mesma UF no mesmo mês**. Por UF porque o teto da cota varia por estado.
- **Mediana, e não média** ([ADR-0005, 9.5](../adr/0005-modelagem-dimensional-granularidade-scd-ceap.md#95-mediana-no-lugar-da-média-como-referência-do-desvio)):
  poucos meses extremos deslocavam a referência da UF inteira. O comparativo mostrou o ranking estável
  (14 de 15 mantidos), com mais mudança entre partidos.
- **Partido da data do gasto** (SCD tipo 2): o CSV regrava o partido com o atual em 22% dos
  lançamentos; sem isso, R$ 33 milhões iriam para o partido errado.
- **Uma definição por métrica:** 32 métricas em 5 views da camada `semantico`, com fórmula, unidade e
  grão versionados. O painel não calcula nada.
- **Mesmo número garantido por teste:** o gasto bate entre parlamentar, partido, categoria,
  fornecedor e o fato (R$ 0,01); 48 testes no `dbt build`.

## 4. O resultado volta para quem age (9:00–11:30) — Taynara *(sugestão)*

**Slide:** fila do auditor e a tabela "CSV × tabela".

- **ETL reverso:** o top 15 vai todo dia, por **push**, para a fila `alerta` no PostgreSQL, logo
  depois do dbt. É o mesmo top 15 do painel.
- **Destino fora do ar:** 3 tentativas; se falhar, o run fica vermelho, a Gold e o painel não mudam e
  a próxima execução publica sem duplicar.
- **Opção nula medida:** um CSV agendado é mais rápido por milissegundos, mas perde a decisão do
  auditor na exportação seguinte, não guarda histórico e qualquer um altera. Bastaria se o auditor só
  lesse; ele precisa **registrar** o que decidiu.
- **Decisão registrada** no [ADR-0008](../adr/0008-disponibilizacao-camada-semantica-etl-reverso.md),
  com gatilhos medidos (p90 de 251 ms contra limiar de 1 s, por exemplo).

## 5. Demo ao vivo (11:30–16:00) — Gabriel

Seguir [demo.md](demo.md). Quatro passos, cerca de 1 minuto cada:

1. Painel: o líder do ranking e o partido do topo.
2. Fila do auditor: **os mesmos 15 nomes**, na mesma ordem, e o registro de uma decisão.
3. Linhagem: o número do líder em cada camada até a Bronze.
4. Recorte de acesso: o auditor vê o CPF; a consulta pública vê o dado mascarado; o resto é negado.

Se a demo falhar, usar o plano B de [demo.md](demo.md#plano-b) (evidências já gravadas).

## 6. Privacidade e riscos (16:00–18:00) — Clara

**Slide:** os titulares e os achados que corrigem a E3.

- [Análise de LGPD](../lgpd.md): inventário por titular (deputados, fornecedores pessoa física, sócios
  do QSA e passageiros), com base legal, retenção, descarte e risco de reidentificação.
- **Achado mais grave, ainda aberto:** o painel mostra o **CPF completo** de 314 fornecedores pessoa
  física. Disparou o gatilho do ADR-0007, e a decisão não foi revista.
- **Já feito:** papéis com privilégio mínimo no PostgreSQL (migration 005) e o ETL reverso conectando
  com usuário de serviço, não com o superusuário.
- **Para a gestão:** o risco é conhecido, medido e tem plano; não foi escondido.

## 7. O que aprendemos e o que fica (18:00–20:00) — Amanda

**Slide:** três lições e as pendências.

- **Testar o dado em vez de confiar nele:** os testes barraram problemas reais da fonte (subcota nova,
  queda da divulgação em ano eleitoral, ruptura do SIGEPA).
- **A fonte não era estável:** o CSV é regerado e sobrescreve o partido.
- **Os gatilhos de ADR quase não ajudaram:** só um disparou e ficou sem dono; o ADR-0008 já saiu com
  limiar, valor atual e ação.
- Pendências: CPF no painel, zona de consumo separada e serviços da E1/E2 ainda como superusuário
  ([retrospectiva](../diario/retrospectiva.md)).

---

## Checklist do ensaio

- [ ] Confirmar a divisão das falas (partes 3 e 4 são sugestão).
- [ ] Subir a plataforma **antes** da defesa (a subida leva ~8 minutos; não fazer ao vivo).
- [ ] Ensaiar a demo inteira pelo [demo.md](demo.md) na máquina que vai ser usada.
- [ ] Conferir os números da parte 5 no dia: eles mudam com a data do download da Câmara.
- [ ] Cronometrar: cada parte dentro do tempo, com 30 s de folga para a troca de quem fala.
- [ ] Cada apresentador ler as perguntas do seu assunto em [perguntas.md](perguntas.md).
