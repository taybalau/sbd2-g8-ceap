# Diário de Bordo — Semana 11

- **Data:** 04/11/2026 a 17/11/2026 (duas semanas num registro, depois da entrega da E3)
- **Participantes:** Filipe Carvalho, Taynara Vitorino, Gabriel Esteves, Maria Clara Alves, Kaio Macedo, Amanda Gonçalves (Squad G8)

> Entre 04/11 e 16/11 não houve commit no repositório, por isso as duas semanas ficam num registro
> só. O trabalho registrado é o de 17/11 (PR #4), que fechou pontos abertos da E3.

## O que foi medido
- **Contratos de esquema** (`contract: enforced`) nas tabelas de consumo da Gold e no fato: o
  `dbt build` passa a reprovar se uma coluna sumir ou mudar de tipo. Todas as colunas ganharam
  descrição no YAML.
- **Teste de ano faltando** (`assert_todos_os_anos_presentes`): reprova se um ano da janela some da
  Bronze, o que os testes de volume por mês não pegavam.
- **Páginas geradas de uma subida do zero:** [Testes de dados](../testes.md) com o resultado de cada
  teste na última execução e [Dicionário de dados](../dicionario-de-dados.md) com todas as colunas,
  as duas geradas por script a partir do projeto dbt.

## O que surpreendeu
- O teste do total mensal reprovava meses que já estavam registrados como ruptura de publicação no
  seed `ruptura_publicacao.csv`. O teste passou a respeitar as rupturas registradas, e uma ruptura
  nova continua reprovando.
- O site tinha links quebrados nas release notes e no menu do diário.

## O que foi decidido
- Gerar testes e dicionário por script, e não escrever à mão, para que a documentação não fique
  diferente do que o build executa.
- Incluir a arquitetura da E3 em [Arquitetura](../arquitetura.md).
