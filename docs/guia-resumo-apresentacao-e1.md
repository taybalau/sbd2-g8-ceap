# Guia Resumido de Estudos e Apresentação — Entrega E1 (SBD2)
**Projeto:** Plataforma de Engenharia de Dados para Auditoria da CEAP (57ª Legislatura: 2023–2026)  
**Squad G8:** Taynara Vitorino, Kaio Macedo, Maria Clara Alves, Amanda Abreu, Filipe Carvalho, Gabriel Esteves  
**Instituição:** Universidade de Brasília (UnB / FCTE) — 2026/2  

---

## 1. O Domínio e a Pergunta de Gestão

* **O Domínio (CEAP):** Cota pública mensal que custeia a atividade parlamentar dos 513 deputados federais (passagens aéreas, escritórios, consultorias, divulgação, combustíveis).
* **Escopo Temporal:** 57ª Legislatura completa (4 anos: 2023 a 2026).
* **Por que a CEAP venceu as outras 4 bases (Sinesp, Procon, ANS, Sinarm):** Apresentou o maior volume transacional (~800k notas), identificadores explícitos (CNPJ, CPF, deputados) e interesse de auditoria contábil pública.
* **A Pergunta de Gestão em Uma Frase:**
  > *"Quais parlamentares e partidos da 57ª Legislatura (2023–2026) apresentam maior desvio de gastos acima da média mensal da Cota Parlamentar (CEAP), e quais categorias e fornecedores concentram esses recursos?"*

---

## 2. Modelagem Relacional (3FN) e Livro-Razão (Insert-Only)

* **Decomposição 3FN (Adeus "Flat Table"):**
  1. `parlamentar`: Cadastro fixo do indivíduo (nome, CPF, `id_deputado`).
  2. `mandato_parlamentar`: Condição política transitória (partido, UF, legislatura).
  3. `fornecedor`: Estabelecimentos únicos (CNPJ/CPF e Razão Social).
  4. `categoria_despesa` e `especificacao_despesa`: Catálogo orçamentário oficial das 21 subcotas.
  5. `despesa_ceap`: Fatos transacionais conectados via Foreign Keys com `ON DELETE RESTRICT`.
* **Padrão Livro-Razão (Insert-Only):**
  * **Zero `UPDATE` e `DELETE`:** Em auditoria contábil, comandos `UPDATE` são "mutabilidade destrutiva" (destroem a linha do tempo do fluxo de caixa).
  * **Tratamento de Glosas e Estornos:** Uma devolução ou corte contábil entra como um **novo lançamento aditivo com valor negativo** (`vlr_liquido < 0`) amarrado ao mesmo documento.
* **Três Carimbos de Tempo:**
  1. `data_emissao`: Fato gerador no mundo real (emissão da nota pela empresa).
  2. `data_pagamento_restituicao`: Fluxo financeiro (quando a Câmara ressarciu ou recebeu devolução).
  3. `data_ingestao`: Auditoria interna do sistema (`DEFAULT CURRENT_TIMESTAMP`).
* **Tipagem Defensiva:** Valores monetários em `NUMERIC(12, 2)` (evita o erro do padrão IEEE 754 de ponto flutuante), datas em `DATE`/`TIMESTAMP` e restrições `CHECK` para competências válidas (mês 1-12, ano >= 2000).

---

## 3. Engenharia de Ingestão: O Casamento Python + PostgreSQL

* **A Filosofia:** O Python é o maestro de rede/orquestração; o PostgreSQL processa 100% dos dados via SQL nativo em C.
* **Módulos Python:**
  * `download_data.py`: Verifica cache local em `base-dados/`; se não existir, baixa os `.zip` oficiais da Câmara via HTTP e descompacta sem intervenção humana.
  * `run_migrations.py`: Migrador sequencial e idempotente com controle na tabela `schema_migrations`.
  * `ingest_ceap.py`: Utiliza o método nativo `psycopg2.copy_expert()` em streaming direto.
  * `main.py`: Loop de tolerância a falhas na inicialização do banco (`retry`) e emissão do dashboard analítico.
* **Tabelas UNLOGGED para Staging:**
  * A tabela `stg_ceap_raw` é criada como `UNLOGGED` (não grava no Write-Ahead Log do Postgres).
  * Ingestão bruta ultrarrápida via `COPY` (>20.000 linhas/s) sem gerar I/O de WAL, seguida de normalização relacional ACID.

---

## 4. O Desafio Técnico: A Resolução com `UNIQUE NULLS NOT DISTINCT`

* **O Problema (ANSI SQL):** Por padrão, no SQL `NULL != NULL`. Na carga ano a ano, fornecedores sem CNPJ (como bilhetes aéreos da TAM/GOL) não disparavam conflito no `ON CONFLICT`, sendo inseridos repetidamente a cada ano.
* **O Efeito Colateral:** O `LEFT JOIN` casava cada nota fiscal com múltiplas cópias do mesmo fornecedor, gerando um produto cartesiano que inflou a base de 785k para 921k linhas.
* **A Solução:** Aplicação da cláusula do padrão **SQL:2023** suportada no **PostgreSQL 16**:
  ```sql
  CONSTRAINT uk_fornecedor_doc_nome UNIQUE NULLS NOT DISTINCT (cnpj_cpf, razao_social);
  ```
* **O Resultado:** O PostgreSQL passou a considerar nulos como equivalentes para unicidade. Eliminou 100% das 135 mil duplicatas, fixando a base em exatas **785.754 despesas** e **R$ 869,4 milhões**.

---

## 5. ADR-0001 e Benchmarks Empíricos Consolidados

| Métrica Avaliada | Alternativa A (Opção Nula: Flat) | Alternativa B (Relacional CRUD) | Alternativa C (Insert-Only — Escolhida) |
| :--- | :---: | :---: | :---: |
| **Tempo de Carga (785k linhas)** | **6,8 s** | 118,2 s | **97,4 s** (Staging COPY + Transformação) |
| **Armazenamento em Disco** | 285 MB | 195 MB | **178 MB** (dimensões deduplicadas) |
| **Integridade ACID** | Nula (tudo TEXT) | Total | **Total (com NULLS NOT DISTINCT)** |
| **Auditoria e Histórico** | Nula | Sofrida (UPDATE destrói) | **Nativa (Livro-Razão Contábil)** |
| **Latência da Pergunta de Gestão** | 790 ms (Seq Scan) | 118 ms | **112 ms (Index Scan B-Tree)** |

---

## 6. Resultados do Painel Analítico (As 6 Perguntas de Gestão)

| # | Pergunta Analítica | Resposta Auditada no Banco |
| :-: | :--- | :--- |
| **0** | **Estatísticas Gerais** | **785.754 despesas** \| **R$ 869.398.245,27** \| **874 parlamentares** \| **55.882 fornecedores** |
| **1** | Custo médio mensal por deputado | **R$ 36.887,36 / mês** por parlamentar ativo |
| **2** | Top 3 parlamentares que mais gastam | 1º Pompeo de Mattos (PDT/RS - R$ 2,27M)<br>2º Albuquerque (REP/RR - R$ 2,26M)<br>3º Carlos Veras (PT/PE - R$ 2,17M) |
| **3** | Top 3 empresas recebedoras | 1º TAM Linhas Aéreas (R$ 66,2M)<br>2º GOL Linhas Aéreas (R$ 24,5M)<br>3º AZUL Linhas Aéreas (R$ 20,0M) |
| **4** | Categoria mais representativa | 1º **Divulgação da Atividade Parlamentar (R$ 349,5M - ~40%)**<br>2º Locação de Veículos (R$ 154,6M)<br>3º Escritório de Apoio (R$ 118,9M) |
| **5** | Top 3 partidos que mais consomem | 1º PL (R$ 160,4M - 155k notas)<br>2º PT (R$ 116,3M - 138k notas)<br>3º UNIÃO (R$ 95,8M - 72k notas) |
| **6** | Gastos em Fins de Semana vs Dias Úteis | **Dias Úteis:** 86,40% das notas (R$ 813,6M)<br>**Fins de Semana:** 13,60% das notas (R$ 59,9M) |

---

## 7. Roteiro da Apresentação da Squad G8 (10 a 12 min)

* **1. Taynara Vitorino (Slides 1 e 2 - 2 min):** Abertura da squad, contexto da CEAP e apresentação da Pergunta de Gestão estrita.
* **2. Kaio Macedo (Slide 3 - 1.5 min):** O processo de governança das Semanas 01 a 04 e a matriz de decisão entre as 5 bases.
* **3. Maria Clara Alves (Slide 4 - 2 min):** Modelagem conceitual e física 3FN, padrão Livro-Razão (sem UPDATE destrutivo) e os 3 carimbos de tempo.
* **4. Amanda Abreu (Slide 5 - 2 min):** Engenharia de ingestão em 2 estágios, tabelas UNLOGGED e a resolução do caso `UNIQUE NULLS NOT DISTINCT`.
* **5. Filipe Carvalho (Slide 6 - 1.5 min):** O ADR-0001, o método de decisão e a tabela comparativa de benchmarks (Opção Nula vs Insert-Only).
* **6. Gabriel Esteves (Slides 7 e 8 - 2.5 min):** Demonstração ao vivo do console Docker, apresentação dos insights das 6 perguntas e transição para o Data Warehouse na E2.

---

## 8. Pitch Rápido para a Banca (Memorize para responder perguntas)

> *"Nosso projeto transformou quase 800 mil notas brutas da CEAP (57ª Legislatura) em um banco relacional em PostgreSQL 16 normalizado em 3FN e operado como Livro-Razão (Insert-Only). Eliminamos mutabilidade destrutiva com campos dedicados para glosas e estornos, garantimos três carimbos temporais auditáveis e resolvemos o problema do ANSI SQL de `NULL != NULL` com a cláusula `UNIQUE NULLS NOT DISTINCT`. A solução sobe do zero via Docker em comando único, carrega 4 anos em apenas 97 segundos, economiza 100 MB em disco e responde consultas agregadas em 112 milissegundos."*
