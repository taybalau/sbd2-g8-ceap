-- Sujeira conhecida da fonte: vlrLiquido <> vlrDocumento - vlrGlosa em 974 lançamentos
-- (0,12% em 2026-11-03, já excluídos os créditos de compensação). Não descartamos (a Bronze
-- é fiel e a linha fica sinalizada), mas se a proporção passar de 0,3% algo mudou na
-- publicação ou no parsing de decimais.
select count(*) filter (where is_valor_inconsistente) as inconsistentes,
       count(*) as total,
       count(*) filter (where is_valor_inconsistente) / count(*) as proporcao
from {{ ref('fct_lancamento_ceap') }}
having count(*) filter (where is_valor_inconsistente) / count(*) > 0.003
