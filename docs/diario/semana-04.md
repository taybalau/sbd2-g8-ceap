# Diário de Bordo — Semana 04

- **Data:** 14/09/2026
- **Participantes:** Filipe Carvalho, Taynara Vitorino, Gabriel Esteves, Maria Clara Alves, Kaio Macedo, Amanda Gonçalves (Squad G8)

## O que foi medido
- Análise comparativa teórica entre um modelo relacional CRUD com sobrescrita (`UPDATE`) versus um modelo de livro-razão contábil (*insert-only*).
- Análise de impacto das trocas partidárias: deputados mudam de legenda ou estado durante a legislatura, demonstrando que o partido não pode ser atributo fixo da tabela `parlamentar`.
- Avaliação conceitual das opções de carga: projeção teórica de que inserções individuais via ORM/drivers seriam inviáveis para quase 1 milhão de linhas, enquanto uma tabela de staging unlogged com utilitário nativo `COPY` do PostgreSQL permitiria carga rápida.

## O que surpreendeu
- A constatação de que um esquema CRUD comum destrói o histórico de quando uma despesa foi efetuada, glosada ou restituída ao sobrescrever registros com `UPDATE`, inviabilizando auditorias retrospectivas e dificultando a captura de mudanças (CDC) na Entrega E2.

## O que foi decidido
- Decisão arquitetural de adotar o padrão **insert-only** para a tabela de fatos/transações `despesa_ceap`.
- Planejamento da distinção formal entre três carimbos de tempo essenciais:
  1. Hora do evento no mundo real (`data_emissao`);
  2. Hora da compensação financeira (`data_pagamento_restituicao`);
  3. Hora do registro no sistema de banco de dados (`data_ingestao`).
- Planejamento da normalização com a entidade associativa `mandato_parlamentar` (rastreando histórico de partido e legislatura) e do pipeline de ingestão em dois estágios (staging `UNLOGGED` + `COPY` seguido de transformações relacionais ACID).
- Planejamento da orquestração via Docker Compose com PostgreSQL 16 para atender ao requisito de subida com comando único a partir de máquina limpa.
