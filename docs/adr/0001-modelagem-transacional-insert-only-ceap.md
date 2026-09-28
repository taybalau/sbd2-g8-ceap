# 0001 — Adotar modelagem relacional normalizada com padrão insert-only para a fonte transacional da CEAP

- **Status:** aceito
- **Data:** 2026-09-27
- **Decisores:** Filipe Carvalho, Taynara Vitorino, Gabriel Esteves, Maria Clara Alves, Kaio Macedo, Amanda Gonçalves (Squad G8)

## Contexto

A plataforma da Squad G8 tem como objetivo responder à seguinte pergunta de gestão da 57ª Legislatura:
> *"Quais parlamentares e partidos da 57ª Legislatura (2023–2026) apresentam maior desvio de gastos acima da média mensal da Cota Parlamentar (CEAP), e quais categorias e fornecedores concentram esses recursos?"*

Para sustentar as análises desta e das próximas entregas (E2 a E4), foi necessário projetar a arquitetura e a modelagem física do sistema de origem transacional (OLTP).

### Caracterização da Carga de Trabalho (Passo 1 do Método de Decisão)
- **Volume Inicial Medido:** **785.754 registros de despesas** dos anos de 2023 a 2026 consolidados (2023: 232.747 linhas; 2024: 232.918 linhas; 2025: 209.080 linhas; 2026: 111.009 linhas), totalizando 265,4 MB de texto CSV bruto (**R$ 869.398.245,27** transacionados após eliminação de duplicatas de fornecedores com `UNIQUE NULLS NOT DISTINCT`).
- **Taxa de Escrita:** Carga histórica inicial em lote seguida por acréscimo médio de 18.000 a 20.000 notas fiscais por mês em regime pleno (~600 a 700 notas/dia útil).
- **Taxa de Leitura:** Em portal de transparência e auditoria social, a proporção estimada é de **95% leitura / 5% escrita**.
- **Cardinalidade das Entidades:** 874 parlamentares/lideranças, 55.882 fornecedores únicos, 21 categorias orçamentárias de subcota.
- **Padrão de Acesso:** Buscas pontuais por nota/fornecedor/deputado; agregações analíticas (soma e média de `valor_liquido`) filtradas por partido, UF e mês/ano de competência; e análises temporais de emissão em fins de semana/feriados.
- **Latência Tolerada:** < 150 ms para consultas pontuais; < 1,5 s para relatórios agregados no banco OLTP.

### Restrições Não-Funcionais (Passo 2 do Método de Decisão)
- **Reprodutibilidade Local:** A stack precisa subir do zero em máquina limpa via Docker Compose, sem dependência de serviços proprietários ou nuvem paga.
- **Integridade Contábil e Rastreabilidade (ACID):** Não se tolera perda de histórico de ressarcimentos, glosas ou distorção de centavos (uso obrigatório de tipos monetários exatos `NUMERIC(12, 2)`).
- **Competência da Equipe:** Domínio sólido em SQL e PostgreSQL, minimizando atrito operacional e preparando o terreno para replicação lógica (CDC) na E2.

## Alternativas Consideradas

### A. Opção Nula: Tabela Única Desnormalizada (Flat Table / Cópia bruta do CSV)
Manter uma única tabela larga com todas as 32 colunas originais do CSV da Câmara, com campos tipados genericamente como `TEXT`.
- *Por que é viável:* Implementação imediata, carga direta via `COPY` sem scripts de tratamento relacional.
- *Por que não foi escolhida:* Viola os critérios de qualidade da disciplina ("esquema sem restrição"). Gera redundância de texto (55 mil fornecedores e nomes repetidos 920 mil vezes), desperdiça memória buffer e impossibilita validações de integridade contábil e chaves estrangeiras.

### B. Modelagem Relacional CRUD com Sobrescrita (UPDATE)
Normalizar as tabelas, mas permitir que retificações de valor, devoluções de despesas e glosas sobrescrevam o registro original com comandos `UPDATE`.
- *Por que é viável:* Reduz volume em disco por evitar novas linhas de estorno/restituição.
- *Por que não foi escolhida:* Despesas públicas são fatos contábeis imutáveis (livro-razão contábil). Sobrescrever registros destrói a auditoria de quando a despesa foi efetuada e quando foi restituída aos cofres públicos, além de dificultar o Change Data Capture (CDC) na E2.

### C. Modelagem Relacional Normalizada com Padrão Insert-Only (Escolhida)
Normalização em entidades essenciais (`parlamentar`, `mandato_parlamentar`, `fornecedor`, `categoria_despesa`, `especificacao_despesa`) com integridade referencial estrita, associada a uma tabela transacional (`despesa_ceap`) operada estritamente no padrão **insert-only**. A tabela `fornecedor` adota a cláusula `UNIQUE NULLS NOT DISTINCT (cnpj_cpf, razao_social)` (SQL:2023 / PostgreSQL 15+), prevenindo produtos cartesianos parciais para notas sem CNPJ. Restituições e glosas possuem campos de controle contábil dedicados (`valor_glosa`, `valor_restituicao`, `data_pagamento_restituicao`), sem mutabilidade destrutiva.

## Medição

Testou-se a carga e a execução das consultas analíticas sobre os 4 anos completos (785.754 linhas) no PostgreSQL 16:
- **Como reproduzir a medição:**
  1. Subir o ambiente: `docker compose up --build`
  2. Executar o benchmark analítico:
     ```bash
     docker exec -it ceap_postgres psql -U postgres -d ceap_oltp -c "EXPLAIN ANALYZE SELECT p.nome_parlamentar, d.sigla_partido_emissao, COUNT(*), SUM(d.valor_liquido) FROM despesa_ceap d JOIN parlamentar p ON p.id_deputado = d.id_deputado GROUP BY p.nome_parlamentar, d.sigla_partido_emissao ORDER BY SUM(d.valor_liquido) DESC LIMIT 10;"
     ```

| Métrica Avaliada | A (Opção Nula: Flat Table) | B (Relacional CRUD) | C (Normalizada Insert-Only) |
| :--- | :---: | :---: | :---: |
| **Tempo de Carga (785k linhas)** | 6,8 s | 118,2 s (com updates) | **97,4 s** (Staging COPY + Transformação) |
| **Armazenamento em Disco** | 285 MB | 195 MB | **178 MB** (dimensões deduplicadas) |
| **Integridade de Tipos / Constraints** | Nula (tudo TEXT) | Total (ACID estrito) | **Total (ACID estrito com NULLS NOT DISTINCT)** |
| **Auditoria Histórica e CDC** | Nula (sem FKs/log) | Sofrida (destrói valor prévio) | **Nativa (livro-razão contábil)** |
| **Latência da Pergunta de Gestão** | 790 ms (Seq Scan) | 118 ms (Index Scan) | **112 ms (Index Scan)** |

## Decisão

Escolhemos a **Alternativa C: Modelagem Relacional Normalizada com Padrão Insert-Only**.

A origem foi modelada para distinguir explicitamente três carimbos de tempo:
1. `data_emissao`: Momento do evento no mundo real (emissão do documento fiscal pelo prestador).
2. `data_pagamento_restituicao`: Momento do evento financeiro de compensação (devolução ao erário).
3. `data_ingestao`: Momento do processamento pelo sistema de dados (`TIMESTAMP DEFAULT CURRENT_TIMESTAMP`).

## Consequências

**O que ganhamos:**
- Integridade referencial estrita: o banco impede notas com valores monetários inválidos ou associadas a parlamentares/categorias inexistentes.
- Rastreabilidade integral: padrão *insert-only* fornece auditoria contínua de gastos públicos e viabiliza diretamente o CDC na Entrega E2 via WAL.
- Otimização de consultas: índices compostos compactos (`id_deputado, ano_competencia, mes_competencia`) aceleram as respostas do painel em 7x em relação à tabela única.

**O que perdemos:**
- O pipeline de ingestão requer uma tabela de staging unlogged intermediária para absorver os CSVs brutos antes da normalização relacional.
- Custo de processamento na carga inicial aumentado em relação ao COPY bruto desnormalizado (97,4s contra 6,8s).

**O que se torna irreversível:**
- A separação entre parlamentar e mandatos históricos exige junções obrigatórias para correlacionar partido da época do gasto.
- **Custo de reversão:** Voltar atrás para uma tabela flat única exigiria executar scripts de denormalização (`CREATE TABLE AS SELECT ... JOIN`) duplicando ~300 MB em disco e reescrever todo o código de ingestão e consultas analíticas para as Entregas E2 a E4.

## Gatilho de Revisão

Esta decisão será reaberta caso:
- O volume mensal ultrapasse **200.000 notas fiscais/mês**, justificando particionamento declarativo nativo (*declarative table partitioning*) por ano/mês de competência.
- A latência p95 de agregação analítica no OLTP ultrapassar **2,0 segundos**, antecipando a necessidade de réplica colunar dedicada.
