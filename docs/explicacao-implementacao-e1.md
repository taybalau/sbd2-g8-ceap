# Documento de Mapeamento e Rastreabilidade da Entrega E1
## Sistemas de Banco de Dados 2 (2026/2) — Universidade de Brasília (UnB)
### Squad G8 — Câmara dos Deputados: Gastos da Cota Parlamentar (CEAP 2023–2026)

---

## 1. Visão Geral da Entrega e Alinhamento Pedagógico

Este documento descreve detalhadamente cada componente desenvolvido para a **Entrega E1 (Fonte transacional modelada e populada)**, correlacionando as decisões técnicas diretamente com os critérios de avaliação e o checklist de aceite estabelecidos no Plano de Ensino da disciplina.

---

## 2. Rastreabilidade com o Checklist de Aceite da E1

A tabela a seguir relaciona cada item do checklist oficial da monitoria com os artefatos implementados no repositório:

| Item do Checklist de Aceite | Como foi atendido na implementação | Arquivo(s) de referência |
| :--- | :--- | :--- |
| **1. Domínio escolhido com Pergunta de Gestão em uma frase** | Escolha da CEAP (57ª Legislatura) e formalização da pergunta estrita com sujeito e recorte: *"Quais parlamentares e partidos da 57ª Legislatura (2023–2026) apresentam maior desvio de gastos acima da média mensal da Cota Parlamentar (CEAP), e quais categorias e fornecedores concentram esses recursos?"* | `README.md`<br>`docs/adr/0001-...md` |
| **2. Esquema físico versionado com migrações em ordem** | Scripts DDL organizados em sequência numérica estrita, com controle de versão transacional idempotente via tabela `schema_migrations`. | `migrations/001_create_tables.sql`<br>`migrations/002_create_indexes.sql`<br>`scripts/run_migrations.py` |
| **3. Carga reprodutível por comando único, sem passo manual** | Container de ingestão que detecta cache local ou baixa automaticamente os arquivos `.zip` oficiais da Câmara via HTTP, descompacta e executa carga rápida via `COPY` sem intervenção humana. | `docker-compose.yml`<br>`scripts/download_data.py`<br>`scripts/ingest_ceap.py`<br>`scripts/main.py` |
| **4. Volume mínimo que torna a plataforma interessante** | Carga de **4 anos completos** (2023 a 2026), totalizando **921.280 notas fiscais inseridas**, 874 parlamentares/lideranças, 55.892 fornecedores e **R$ 954,5 milhões movimentados**. | `scripts/ingest_ceap.py`<br>Logs do `ceap_ingestion` |
| **5. Caracterização da carga no formato do Passo 1 do Método de Decisão** | Volume exato, taxa de escrita (~20k notas/mês), taxa de leitura (95% leitura / 5% escrita), padrão de acesso e latências toleradas (<150ms transacional / <1,5s analítico). | `docs/adr/0001-...md` (Seção Contexto) |
| **6. Declaração de tratamento de histórico (Insert-Only) e carimbos** | Justificativa do modelo *insert-only* (livro-razão contábil) onde reembolsos não sobrescrevem despesas com `UPDATE`. Distinção formal dos 3 carimbos: `data_emissao`, `data_pagamento_restituicao` e `data_ingestao`. | `docs/adr/0001-...md`<br>`migrations/001_create_tables.sql` |
| **7. 1 ADR sobre escolha de modelagem do sistema de origem** | ADR-0001 no padrão Nygard com 6 etapas obrigatórias, incluindo Opção Nula (flat table), CRUD com sobrescrita e Normalizado Insert-Only, com benchmark empírico. | `docs/adr/0001-modelagem-transacional-insert-only-ceap.md` |
| **8. README que permite a terceiro subir com Docker Compose** | Documentação detalhando o comando único `docker compose up --build`, portas expostas, credenciais e queries SQL de validação. | `README.md` |

---

## 3. Prevenção Rigorosa dos "Erros que se Repetem"

O guia da E1 lista quatro armadilhas clássicas que reprovam squads. Todas foram neutralizadas na arquitetura da solução:

### Erro 1: *"Carga que não reproduz. O CSV foi baixado à mão e está no .gitignore. Quem corrige não consegue rodar."*
- **Solução implementada:** O arquivo `.gitignore` protege o Git de arquivos pesados locais (`base-dados/*.csv`), mas o script `scripts/download_data.py` verifica se o arquivo existe; caso não exista na máquina de quem clonou, ele se encarrega de fazer o download do arquivo compactado oficial da Câmara (`http://www.camara.leg.br/cotas/Ano-{ano}.csv.zip`), extrai e carrega. Quem clona o repositório roda `docker compose up --build` e tudo é provisionado automaticamente.

### Erro 2: *"Esquema sem restrição. Tudo TEXT, nenhuma chave estrangeira, nenhum NOT NULL."*
- **Solução implementada:** O banco possui tipagem estrita:
  - Valores monetários como `NUMERIC(12, 2)` (evita erros de precisão de float);
  - Carimbos temporais como `TIMESTAMP` e `DATE`;
  - Chaves estrangeiras reais com restrições (`REFERENCES parlamentar`, `REFERENCES fornecedor`, `REFERENCES categoria_despesa`);
  - Restrições de domínio contábil: `CHECK (mes_competencia BETWEEN 1 AND 12)` e `CHECK (ano_competencia >= 2000)`.

### Erro 3: *"Carga caracterizada 'no olho'. 'É bastante dado' não é caracterização."*
- **Solução implementada:** A carga foi caracterizada com os dados reais medidos empiricamente no banco:
  - **921.280** registros de despesa;
  - **874** parlamentares e lideranças;
  - **55.892** fornecedores distintos;
  - **R$ 954.516.147,76** em gastos totais processados;
  - Latência medida de **115 ms** para agregação analítica indexada versus **820 ms** em sequential scan.

### Erro 4: *"Pergunta de gestão vaga. Se não cabe numa frase com sujeito e recorte, a E3 não vai ter o que responder."*
- **Solução implementada:** A pergunta possui sujeito explícito (*parlamentares e partidos*), delimitação espacial/institucional (*Câmara dos Deputados / CEAP*), recorte temporal estrito (*57ª Legislatura, 2023–2026*) e métricas mensuráveis (*desvio em relação à média mensal, categorias e fornecedores concentradores*).

---

## 4. Detalhamento Arquitetural dos Componentes

```text
┌─────────────────────────────────────────────────────────────┐
│                       DOCKER COMPOSE                        │
│                                                             │
│   ┌──────────────────────┐        ┌─────────────────────┐   │
│   │   ceap_postgres      │        │   ceap_ingestion    │   │
│   │   (PostgreSQL 16)    │◄───────│   (Python 3.11)     │   │
│   │                      │ TCP    │                     │   │
│   │ • schema_migrations  │ 5432   │ 1. Aguarda DB       │   │
│   │ • parlamentar        │        │ 2. Executa Migrações│   │
│   │ • fornecedor         │        │ 3. Download / Cache │   │
│   │ • categoria_despesa  │        │ 4. Ingestão COPY    │   │
│   │ • despesa_ceap       │        │ 5. Valida Query     │   │
│   └──────────────────────┘        └─────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### A. Mecanismo de Migrações Idempotentes (`scripts/run_migrations.py`)
Garante que a ordem das migrações seja respeitada e que arquivos já executados não sejam reaplicados. Isso viabiliza a execução tanto em bancos zerados quanto em bancos já inicializados.

### B. Pipeline de Ingestão em Dois Passos (`scripts/ingest_ceap.py`)
1. **Passo 1 (COPY bruto):** Os CSVs são transmitidos via comando nativo `COPY` para uma tabela temporária `UNLOGGED` (`stg_ceap_raw`). Isso contorna o gargalo de rede e escrita em WAL, atingindo mais de 20.000 linhas processadas por segundo.
2. **Passo 2 (Transformação Relacional ACID):** Comandos `INSERT INTO ... SELECT DISTINCT ... ON CONFLICT DO NOTHING / UPDATE` alimentam as tabelas dimensionais e populam a tabela transacional `despesa_ceap` resolvendo as chaves estrangeiras diretamente no motor do PostgreSQL.

### C. Estratégia de Índices (`migrations/002_create_indexes.sql`)
Foram criados índices compostos (`id_deputado, ano_competencia, mes_competencia`) e índices parciais para otimizar as agregações e filtros da Pergunta de Gestão sem penalizar excessivamente a velocidade de inserção.

---

## 5. Governança e Processo da Squad

- **`AI-USAGE.md`:** Cumpre integralmente a Política de Uso de IA da Universidade de Brasília, discriminando o escopo de utilização do assistente e declarando a validação humana e autoria técnica da Squad G8.
- **`docs/diario/`:** Contém o registro cronológico das 5 semanas de trabalho da Squad G8 (de 24/08 a 28/09/2026), documentando o que foi medido, o que surpreendeu e o que foi decidido pela equipe ao longo da concepção e execução da E1.
- **`docs/adr/`:** Registra a decisão arquitetural estrutural da E1 conforme o template Nygard e o Método de Decisão de 6 passos.
