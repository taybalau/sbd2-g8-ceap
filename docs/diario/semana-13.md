# Diário de Bordo — Semana 13

- **Data:** 25/11/2026 a 26/11/2026 (tag `e4` e preparação da defesa)
- **Participantes:** Filipe Carvalho, Taynara Vitorino, Gabriel Esteves, Maria Clara Alves, Kaio Macedo, Amanda Gonçalves (Squad G8)

## O que foi medido
- **Integração da E4 (25/11):** PRs #18 a #23 revisados e integrados; `mkdocs build --strict` sem
  links quebrados (22 links da retrospectiva estavam quebrados antes da revisão do PR #22); tag `e4`
  criada sobre a `main`.
- **Material da defesa** (issue #13): roteiro de 20 minutos em 7 partes, os 4 passos da demo
  validados numa subida do zero e as perguntas prováveis da banca, em `docs/defesa/`.
- **Painel depois da E4 (26/11, PR #24):** 3 views novas na camada semântica (série mensal,
  lançamentos com o link do documento na Câmara e o resultado do último build), 50 métricas em 8
  views e 51 testes. Leitura ao abrir com 254 ms de p90; lançamentos de um parlamentar com 38 ms.
- **Cobertura do documento:** a Câmara publicou o documento de 94% dos lançamentos da janela (100%
  das notas eletrônicas e dos recibos, 87% das notas em papel).
- **CPF fora da tela:** mascarado no documento e no nome do fornecedor (426 nomes com 11 dígitos
  seguidos e 29 com CPF pontuado) e link do recibo omitido para pessoa física (4.676 lançamentos,
  cerca de 1%). O teste `assert_semantico_sem_cpf_completo` barra o build se um CPF completo
  aparecer na camada.

## O que surpreendeu
- **A `main` deixou de subir do zero.** A ingestão em lote da E2 falhou com
  `Cannot cast field trecho from Utf8 to Null`: num bloco do CSV em que `trecho` vinha todo vazio, o
  tipo da coluna era deduzido como nulo. Depende do arquivo baixado no dia, por isso não apareceu
  antes. A correção (esquema fixo no lote e no CDC) está no PR #24.
- **A fonte mudou no mesmo dia:** os CSVs regerados em 26/11 têm 647.072 lançamentos, contra 802.861
  na subida de 24/11, e o líder do ranking passou a ser Zé Trovão (PL-SC). Os testes de volume e de
  reconciliação passaram: a diferença está na fonte.
- A API da Câmara respondeu HTTP 429 (limite de requisições) três vezes no mesmo dia; a pipeline
  falhou de forma segura e o plano B com cache funcionou.
- Duas vezes "R$" na mesma frase do painel era lido como fórmula LaTeX e embaralhava o texto.

## O que foi decidido
- Contar visão do ADR-0007 como bloco do painel (3 blocos, gatilho de 8 visões não disparou) e manter
  o limite de 50 métricas do ADR-0008 ([portfólio](../adr/README.md)).
- Não mostrar o link do documento quando o fornecedor é pessoa física, porque o recibo traz o CPF
  completo.
- Integrar o PR #24 antes da defesa, por causa da correção da subida do zero.
- Reunir o enunciado e o checklist de aceite de cada entrega numa seção
  [Entregáveis](../entregaveis/index.md) do site, com a evidência de cada item.
