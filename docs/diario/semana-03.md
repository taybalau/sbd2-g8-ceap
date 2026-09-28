# Diário de Bordo — Semana 03

- **Data:** 07/09/2026
- **Participantes:** Filipe Carvalho, Taynara Vitorino, Gabriel Esteves, Maria Clara Alves, Kaio Macedo, Amanda Gonçalves (Squad G8)

## O que foi medido
- Inspeção conceitual das 32 colunas fornecidas no layout oficial dos arquivos da CEAP pela Câmara dos Deputados.
- Análise preliminar da cardinalidade das entidades do domínio: cerca de 600 deputados e contas de liderança ativas, mais de 50.000 fornecedores e prestadores únicos, e 21 subcotas orçamentárias.

## O que surpreendeu
- Constatação de particularidades e inconsistências estruturais nos dados abertos reais:
  - Existência de despesas associadas a contas de liderança partidária ("Liderança da Minoria", "Liderança do Governo") que movimentam cota parlamentar sem CPF individual nem carteira parlamentar.
  - Registros de telefonia da Câmara com datas de emissão vazias (`""`).
  - Passagens aéreas emitidas pelo sistema central SIGEPA com valores líquidos negativos (decorrentes de estornos ou cancelamentos de voos) e sem CNPJ no campo correspondente.

## O que foi decidido
- Planejar a modelagem relacional de forma a absorver fielmente essas particularidades sem quebrar a integridade nem descartar registros reais:
  - Campos de CPF e carteira parlamentar devem ser anuláveis para comportar as lideranças institucionais.
  - O campo de data de emissão deve ser anulável para acomodar despesas de ramal telefônico interno da Câmara.
  - As constraints financeiras devem permitir valores líquidos negativos legítimos resultantes de cancelamentos e devoluções contábeis.
