# Entregáveis

O que cada entrega do Projeto Integrado pede e onde está a evidência de cada item no repositório.
O texto dos itens resume o enunciado oficial da disciplina, que fica em
[unb-bd2.github.io/PlanoEnsino/projeto](https://unb-bd2.github.io/PlanoEnsino/projeto/). Em caso de
dúvida, vale o enunciado.

**Situação dos itens:** **atendido** quando a evidência está no repositório e foi conferida numa
subida do zero; **parcial** quando parte do item ainda falta, com o que falta escrito ao lado.

## As quatro entregas

| Entrega | Tema | Prazo | Peso | Tag | Checklist |
| :--- | :--- | :--- | ---: | :--- | :--- |
| [E1](e1.md) | Fonte transacional modelada e populada | 22/09/2026 | 10% | `e1` | 8 de 8 |
| [E2](e2.md) | Ingestão em lote e captura de mudanças | 13/10/2026 | 12% | `e2` | 8 de 8 |
| [E3](e3.md) | Camada analítica transformada, testada e orquestrada | 03/11/2026 | 14% | `e3` | 8 de 8 |
| [E4](e4.md) | Plataforma completa, governada e defendida | 24/11/2026 | 14% | `e4` | 7 atendidos, 1 parcial |

O Projeto Integrado vale 55% da nota. O portfólio dos ADRs é avaliado à parte (15% da nota final).

## Como cada entrega é avaliada

Os mesmos cinco critérios valem para as quatro entregas:

| Critério | Peso | Onde a Squad mostra |
| :--- | ---: | :--- |
| Funcionamento e reprodutibilidade | 30% | [Como executar](../como-executar.md): a plataforma sobe do zero com `docker compose up --build` |
| Adequação técnica | 25% | Documento técnico de cada entrega e os [ADRs](../adr/README.md) |
| Qualidade e testes de dados | 20% | [Testes de dados](../testes.md): 51 testes no `dbt build`, mais os testes de aceite da E2 |
| Documentação e ADRs | 15% | Este site, o [catálogo](../catalogo.md), a [linhagem](../linhagem.md) e o [portfólio de ADRs](../adr/README.md) |
| Processo da Squad | 10% | [Diário de bordo](../diario/index.md), issues, PRs revisados e o histórico do git |

O enunciado aponta como motivo de reprovação mais comum a plataforma que não sobe do zero, em
máquina limpa, a partir de um `git clone` num diretório novo.

## Estrutura obrigatória do repositório

| Exigência | Onde está | Situação |
| :--- | :--- | :--- |
| `docker-compose.yml` que sobe tudo | raiz do repositório | atendido |
| `docs/adr/` com os 5 ADRs | 8 ADRs, de [0001](../adr/0001-modelagem-transacional-insert-only-ceap.md) a [0008](../adr/0008-disponibilizacao-camada-semantica-etl-reverso.md) | atendido |
| `docs/diario/` com o registro semanal (medido, surpreendeu, decidido) | [Diário de bordo](../diario/index.md), semanas 01 a 13 e retrospectiva | atendido |
| `AI-USAGE.md` com o registro de uso de IA | raiz do repositório | atendido |
| `README.md` que permite a um terceiro subir e entender a plataforma | raiz do repositório | atendido |

## Requisitos mínimos do produto final

| Requisito | Entrega | Situação |
| :--- | :---: | :--- |
| OLTP modelado e populado | E1 | atendido |
| Ingestão em lote e fluxo de mudanças (CDC ou streaming) | E2 | atendido |
| Armazenamento analítico em formato aberto | E2 | atendido |
| Transformações versionadas com testes e orquestração agendada | E3 | atendido |
| Consumo duplo (painel e camada semântica) com caminho de ETL reverso | E4 | atendido |
| Catálogo, linhagem e análise de LGPD | E4 | atendido (implementação da LGPD parcial, ver [E4](e4.md)) |
| 5 ADRs | E1 a E4 | atendido (8 ADRs) |
