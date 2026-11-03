#!/usr/bin/env bash
# Gera docs/explain/antes.txt e depois.txt com EXPLAIN (ANALYZE, BUFFERS) da consulta de
# desvio da pergunta de gestão, no PostgreSQL do docker compose (container ceap_postgres).
# Uso (com a plataforma no ar):  bash scripts/explain_desvio.sh
set -euo pipefail
cd "$(dirname "$0")/.."
DIR=docs/explain
PSQL=(docker exec -i ceap_postgres psql -U postgres -d ceap_oltp -X -q)

"${PSQL[@]}" -c "VACUUM ANALYZE despesa_ceap" -c "ANALYZE mv_gasto_mensal_deputado"

plano() {  # $1 = consulta, $2 = saída. Uma execução de aquecimento e a medida com cache quente.
    "${PSQL[@]}" -At < "$1" > /dev/null
    { echo "-- gerado em $(date -u +%Y-%m-%dT%H:%M:%SZ) a partir de $1"
      "${PSQL[@]}" -c "SELECT version();" -At
      echo
      { echo "EXPLAIN (ANALYZE, BUFFERS)"; cat "$1"; } | "${PSQL[@]}"
    } > "$2"
    grep -E "Execution Time" "$2"
}

plano "$DIR/consulta_desvio.sql" "$DIR/antes.txt"
plano "$DIR/consulta_desvio_otimizada.sql" "$DIR/depois.txt"

if diff <("${PSQL[@]}" -At < "$DIR/consulta_desvio.sql") \
        <("${PSQL[@]}" -At < "$DIR/consulta_desvio_otimizada.sql") > /dev/null; then
    echo "resultado idêntico nas duas consultas"
else
    echo "ATENÇÃO: as duas consultas devolvem resultados diferentes" >&2; exit 1
fi
