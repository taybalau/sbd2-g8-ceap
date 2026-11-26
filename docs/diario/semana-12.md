# Diário de Bordo — Semana 12

- **Data:** 18/11/2026 a 24/11/2026 (entrega da E4 em 24/11)
- **Participantes:** Filipe Carvalho, Taynara Vitorino, Gabriel Esteves, Maria Clara Alves, Kaio Macedo, Amanda Gonçalves (Squad G8)

## O que foi medido
- **Mediana no lugar da média (19/11, PR #5):** a referência do desvio passou a ser a mediana do gasto
  mensal dos deputados da mesma UF no mês, com z-score robusto (MAD). O comparativo sobre os mesmos
  dados manteve 14 dos 15 nomes do ranking, com mais mudança entre partidos
  ([ADR-0005, seção 9.5](../adr/0005-modelagem-dimensional-granularidade-scd-ceap.md#95-mediana-no-lugar-da-média-como-referência-do-desvio)).
- **Camada semântica (24/11, issue #6):** 5 views no schema `semantico` com 32 métricas, cada uma
  com fórmula, unidade e grão no `_semantic.yml`. O painel passou a ler só dessas views, e testes no
  `dbt build` conferem que o gasto é o mesmo número em todas elas e no fato (48 testes no total).
- **Leitura da camada:** 251 ms de p90 para tudo o que o painel lê ao abrir, contra limiar de 1 s no
  [ADR-0008](../adr/0008-disponibilizacao-camada-semantica-etl-reverso.md).
- **ETL reverso (issue #7):** o top 15 vai por push para a fila `alerta` no PostgreSQL. Com o destino
  derrubado de propósito, a publicação falhou após 3 tentativas sem mudar a Gold nem a fila; com o
  destino de volta, republicou sem duplicar. O CSV agendado (opção nula) foi medido nos mesmos
  cenários.
- **Controle de acesso (issue #10):** migration 005 com papéis de privilégio mínimo e recorte de
  colunas; o roteiro de validação confere os acessos permitidos e as operações negadas
  ([Controle de acesso](../controle-de-acesso.md)).
- **Conferência dos gatilhos dos ADRs 0001 a 0007** com a plataforma subida do zero
  ([portfólio](../adr/README.md)): só o gatilho de acesso por perfil do ADR-0007 disparou.

## O que surpreendeu
- A [análise de LGPD](../lgpd.md) (issue #9) achou o **CPF completo** de fornecedores pessoa física
  na tabela de fornecedores do painel.
- A revisão do PR #17 mostrou que o ETL reverso conectava como superusuário, porque o
  `docker-compose.yml` passava `postgres` aos serviços, e que o auditor podia gravar uma decisão em
  nome de outra pessoa. Os dois foram corrigidos antes do merge: usuário de serviço
  `ceap_etl_reverso` e autoria gravada pelo banco (`session_user`).
- As 9 issues da E4 foram abertas em 24/11, o dia do prazo, e fechadas em 24 e 25/11. O enunciado
  avisa contra deixar a E4 para as duas últimas semanas, e a Squad deixou para o último dia.

## O que foi decidido
- Camada semântica no dbt lida direto do warehouse, e ETL reverso por push, registrados no
  [ADR-0008](../adr/0008-disponibilizacao-camada-semantica-etl-reverso.md) com limiar, valor atual e
  ação para cada gatilho.
- Uma regra só para o alerta (`em_alerta`, top 15) usada pelo painel e pela fila do auditor.
- Registrar o gatilho disparado do ADR-0007 em aberto, sem rever a decisão nesta entrega.
- Catálogo e linhagem da fonte ao consumo ([catálogo](../catalogo.md), [linhagem](../linhagem.md),
  issue #8) e a [retrospectiva](retrospectiva.md) do ciclo de vida (issue #12).
