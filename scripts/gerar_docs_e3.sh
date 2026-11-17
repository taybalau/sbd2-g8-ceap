#!/usr/bin/env bash
# Regera docs/testes.md e docs/dicionario-de-dados.md a partir de uma execução real do dbt.
# Roda dentro do container da E3, com a plataforma já no ar (lakehouse gerado):
#
#   docker compose run --build --rm --no-deps -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
#       -v ./docs:/app/docs -v ./scripts:/app/scripts e3-pipeline bash scripts/gerar_docs_e3.sh
#
# Sai com erro se algum teste reprovar, mas gera as páginas mesmo assim (a reprovação aparece nelas).
set -uo pipefail
cd /app/dbt_ceap
export DBT_PROFILES_DIR=.

dbt build
status=$?
# `dbt source freshness` regrava o run_results.json; o do build é o que vai para a página.
cp target/run_results.json /tmp/run_results_build.json
dbt source freshness || status=$?
cp /tmp/run_results_build.json target/run_results.json

cd /app
python scripts/gerar_doc_testes.py || status=$?
python scripts/gerar_dicionario.py || status=$?
chown "${HOST_UID:-0}:${HOST_GID:-0}" docs/testes.md docs/dicionario-de-dados.md 2>/dev/null || true
exit $status
