# Diário de Bordo — Semana 09

- **Data:** 21/10/2026 a 28/10/2026
- **Foco:** avaliação do desenho de dados e preparação da arquitetura analítica da E3.

## O que foi medido
- A investigação da E3 caracterizou a CEAP como carga analítica de dados públicos, sem necessidade de transações de usuários na aplicação. A comparação de alternativas considerou a preservação do dado bruto, a capacidade de auditar exceções e a manutenção de esquemas duplicados.
- A análise de granularidade e histórico partidário identificou que a chave técnica `id_despesa` da E1 não representa uma chave de negócio, e que o CSV não preserva necessariamente o partido vigente na data do gasto. Os números e exemplos consolidados dessa investigação estão detalhados na revisão do ADR-0005.

## O que surpreendeu
- Reutilizar o modelo relacional da E1 como estágio obrigatório poderia rejeitar exceções relevantes para auditoria pública e manter dois contratos de dados para a mesma camada analítica.
- Um SCD2 construído diretamente com o partido atual do CSV reproduziria a sobrescrita publicada pela fonte, em vez de recuperar a filiação histórica.

## O que foi decidido
- Preparar a migração do fluxo analítico para Direct-to-Lakehouse ELT, preservando os dados de origem na Bronze e aplicando tipagem e regras nas camadas seguintes.
- Declarar no ADR-0005 o grão real do lançamento e a necessidade de buscar histórico partidário em fonte temporal própria; a decisão foi formalizada em 29/10, junto ao ADR-0004.
