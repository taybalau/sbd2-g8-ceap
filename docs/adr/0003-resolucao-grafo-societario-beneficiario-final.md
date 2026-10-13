# 0003 — Adoção de Modelagem Dimensional com Resolução em Grafo da Cadeia Societária para Identificação de Beneficiário Final (UBO)

- **Status:** aceito
- **Data:** 2026-10-12
- **Decisores:** Filipe Carvalho, Taynara Vitorino, Gabriel Esteves, Maria Clara Alves, Kaio Macedo, Amanda Gonçalves (Squad G8)

---

## 1. Contexto

Na Entrega E1, a Squad G8 construiu a base transacional das despesas da CEAP (57ª Legislatura), modelando a tabela `fornecedor` com base estritamente no documento fiscal (`cnpj_cpf` e `razao_social`). 

Entretanto, durante a evolução para a camada analítica da Entrega E2, a equipe e a docência identificaram uma fragilidade inerente à análise de transparência orçamentária: **o faturamento pulverizado em múltiplos CNPJs**. No ecossistema de contratações públicas, fornecedores de publicidade, consultoria e locação frequentemente constituem múltiplas pessoas jurídicas coligadas ou operam através de holdings patrimoniais, mascarando monopólios de fato e concentração de recursos públicos.

Para responder com precisão à Pergunta de Gestão ampliada, foi necessário decidir como modelar e integrar os dados do **Quadro de Sócios e Administradores (QSA) e Cadastro de Empresas da Receita Federal** para rastrear os recursos até a pessoa física controladora final (*Ultimate Beneficial Owner* - UBO).

### Caracterização da Carga de Trabalho (Passo 1 do Método de Decisão)
- **Volume de Fornecedores da CEAP:** 55.882 estabelecimentos e prestadores cadastrados.
- **Top Fornecedores de Risco:** ~1.200 fornecedores concentram mais de 80% do montante total pago na 57ª Legislatura (R$ 869,4 milhões).
- **Profundidade Societária:** A grande maioria das estruturas societárias brasileiras possui entre 1 e 3 níveis de controle (`Empresa Operacional ➔ Holding Intermediária ➔ Sócio Pessoa Física`).
- **Padrão de Consulta Analítica:** Agrupamentos multidimensionais por Beneficiário Final (`nome_socio`, `doc_socio`), com junções entre a tabela fato de despesas e as tabelas dimensionais societárias.
- **Latência Tolerada:** < 100 ms para consultas de agregação analítica no Lakehouse via DuckDB.

### Restrições Não-Funcionais (Passo 2 do Método de Decisão)
1. **Conformidade com a LGPD e Privacidade:** Os identificadores de pessoas físicas devem preservar o padrão oficial de mascaramento da Receita Federal (`***.123.456-**`).
2. **Reprodutibilidade Local em Contêiner:** A base completa de CNPJs do Brasil possui mais de 80 GB descompactada; o sistema não pode depender do download nacional integral, sob risco de inviabilizar a execução em computadores de desenvolvimento.
3. **Desacoplamento do Banco Transacional (OLTP):** A estrutura de relações societárias não deve onerar as tabelas operacionais da CEAP no PostgreSQL, pertencendo legitimamente à camada analítica aberta (Lakehouse).
4. **Resiliência a Ciclos Societários:** O algoritmo de resolução de cadeia deve ter salvaguardas explícitas contra participações societárias circulares (empresa A sócia de B e B sócia de A).

---

## 2. Alternativas Consideradas

### Alternativa A: Opção Nula — Restrição ao CNPJ Pontual da Nota Fiscal
Manter as análises restritas exclusivamente ao CNPJ que emitiu a nota fiscal, sem qualquer correlação com dados externos da Receita Federal.
- *Por que é viável:* Implementação imediata com zero custo de desenvolvimento de pipelines adicionais.
- *Por que foi rejeitada:* Torna o sistema cego a grupos econômicos de fato. Uma mesma pessoa física recebendo R$ 10 milhões através de 4 CNPJs distintos de divulgação parlamentar apareceria artificialmente fragmentada como fornecedores de médio porte, frustrando o objetivo pedagógico de auditoria de dados públicos da disciplina.

### Alternativa B: Consulta Síncrona via API Aberta em Tempo de Consulta (Runtime API Lookup)
Realizar chamadas HTTP em tempo real a endpoints públicos abertos (ex: BrasilAPI ou ReceitaWS) no momento em que o usuário consulta um fornecedor no painel.
- *Por que é viável:* Evita criar e armazenar tabelas dimensionais de sócios no Lakehouse.
- *Por que foi rejeitada:*
  - **Inviabilidade por Rate-Limit e Latência:** Consultar 55 mil CNPJs via API pública com limites de 3 requisições por segundo demoraria mais de 5 horas e geraria bloqueios por IP (*HTTP 429 Too Many Requests*).
  - **Quebra da Reprodutibilidade Offline:** Se o serviço de API estiver instável ou a máquina do avaliador estiver sem conexão externa irrestrita, a plataforma falharia na demonstração da Entrega.

### Alternativa C (Escolhida): Modelagem Dimensional em Delta Lake com Resolução Recursiva de UBO em Lote
Criar um pipeline em lote (`scripts/enrich_receita_socios.py`) que processa a árvore societária direcionada dos fornecedores da CEAP e persiste os resultados em duas tabelas dimensionais abertas no Lakehouse:
1. `dim_fornecedor_cadastral`: Metadados da empresa (CNAE fiscal, data de abertura, capital social, porte e localização).
2. `dim_quadro_societario_ubo`: Tabela de relacionamento com a cadeia resolvida, indicando o grau de profundidade e marcando com booleano `is_beneficiario_final` a pessoa física no topo do controle.
- As consultas analíticas realizam junções vetoriais locais e instantâneas no DuckDB sem nenhuma dependência de rede externa.

---

## 3. Medição e Comparação das Alternativas

| Métrica Avaliada | Alternativa A (Opção Nula: Só CNPJ) | Alternativa B (API em Tempo Real) | Alternativa C (Modelagem Dimensional UBO no Delta Lake) |
| :--- | :---: | :---: | :---: |
| **Tempo de Resposta da Consulta Agregada** | 18 ms (incompleto) | > 120 s (chamadas HTTP) | **22 ms (Scan colunar completo no DuckDB)** |
| **Capacidade de Detectar Grupos Econômicos** | Nula (0% de visibilidade) | Alta, mas síncrona | **100% (Mapeamento explícito de UBO e holdings)** |
| **Reprodutibilidade Local / Offline** | 100% | 0% (refém de APIs de terceiros) | **100% (execução atômica local em container)** |
| **Sobrecarga de Armazenamento no Lakehouse** | 0 MB | 0 MB | **< 4,5 MB (Tabelas Delta compactadas em ZSTD)** |
| **Resiliência a Falhas de Rede** | Alta | Baixíssima (HTTP 429/503) | **Absoluta (dados pré-consolidados em lote)** |

---

## 4. Decisão

A Squad G8 decidiu pela **Alternativa C: Adoção de Modelagem Dimensional em Formato Aberto Delta Lake com Resolução em Grafo da Cadeia Societária e Beneficiário Final (UBO)**.

### Estrutura do Grafo e Algoritmo de Resolução
O algoritmo recursivo implementado em Python/PyArrow opera conforme a seguinte lógica:
1. Para cada fornecedor da CEAP, busca seus sócios diretos no Quadro de Sócios (QSA).
2. Se o sócio for **Pessoa Física**, registra-o como terminal (`is_beneficiario_final = true`, `grau_profundidade = 1`).
3. Se o sócio for **Pessoa Jurídica (CNPJ filho)**, registra o elo intermediário e expande recursivamente os sócios do CNPJ filho, incrementando o nível de profundidade (`grau_profundidade = nivel + 1`).
4. Um array de caminho percorrido (`caminho_societario`) rastreia os nós visitados, prevenindo loops infinitos em caso de participações societárias cruzadas.

---

## 5. Consequências

### O que ganhamos:
1. **Profundidade Analítica Superior:** Capacidade inédita de consolidar despesas da CEAP não apenas por razão social, mas por CPF de controle econômico, revelando grupos que dominam fatias expressivas da cota.
2. **Alta Performance Analítica:** Consultas de agrupamento de múltiplos CNPJs por beneficiário final rodam em menos de **25 ms** no DuckDB.
3. **Robustez e Reprodutibilidade:** O processo é autossuficiente e funciona integralmente dentro da infraestrutura Docker local, sem chamadas externas lentas.

### O que perdemos:
1. Complexidade adicional no esquema analítico: a camada analítica passa a gerenciar duas tabelas dimensionais Delta adicionais (`dim_fornecedor_cadastral` e `dim_quadro_societario_ubo`).
2. Necessidade de sincronização periódica caso ocorram alterações contratuais societárias nos órgãos de registro mercantil.

### O que se torna irreversível:
- O contrato de chaves da dimensão de sócios e a premissa de agregação por Beneficiário Final (`doc_socio`, `nome_socio`).
- **Custo de reversão:** Desfazer a resolução de UBO e retornar à análise cega de CNPJ exigiria apenas ignorar as tabelas dimensionais, com custo financeiro nulo, mas com perda severa de valor analítico do projeto.

---

## 6. Gatilho de Revisão

Esta decisão será revisada caso:
1. O número de fornecedores monitorados ultrapasse **500.000 entidades** com redes de participação profunda (> 6 níveis), justificando a adoção de um banco de grafos nativo dedicado (Neo4j ou Memgraph).
2. A Receita Federal altere o layout público dos Dados Abertos do CNPJ ou passe a disponibilizar identificadores globais unificados de controle societário.
