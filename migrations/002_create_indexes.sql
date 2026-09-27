-- Migração 002: Criação de índices estratégicos para suportar consultas analíticas e de gestão
-- Justificados pela caracterização da carga de trabalho (Passo 1 do Método de Decisão)

-- 1. Índice para agregações e filtros por parlamentar e competência temporal
CREATE INDEX IF NOT EXISTS idx_despesa_deputado_periodo 
ON despesa_ceap (id_deputado, ano_competencia, mes_competencia);

-- 2. Índice para consultas agrupadas por partido e ano
CREATE INDEX IF NOT EXISTS idx_despesa_partido_ano 
ON despesa_ceap (sigla_partido_emissao, ano_competencia);

-- 3. Índice para análise de categorias de despesa mais representativas
CREATE INDEX IF NOT EXISTS idx_despesa_subcota_ano 
ON despesa_ceap (num_subcota, ano_competencia);

-- 4. Índice para identificação dos maiores fornecedores e seus valores
CREATE INDEX IF NOT EXISTS idx_despesa_fornecedor_valor 
ON despesa_ceap (id_fornecedor, valor_liquido);

-- 5. Índice para consultas sobre carimbo de emissão (ex: despesas em fins de semana e feriados)
CREATE INDEX IF NOT EXISTS idx_despesa_data_emissao 
ON despesa_ceap (data_emissao);

-- 6. Índice parcial para consultas pontuais de notas fiscais com identificador
CREATE INDEX IF NOT EXISTS idx_despesa_ide_documento 
ON despesa_ceap (ide_documento) 
WHERE ide_documento IS NOT NULL;
