#!/usr/bin/env bash
# Medição do ADR-0007: tempo até o painel Streamlit da E3 responder /_stcore/health e memória
# em repouso, com a imagem da E3 e o lakehouse já gerado (depois do docker compose up).
# Uso: bash scripts/medir_painel_streamlit.sh [caminho_do_lakehouse]
set -euo pipefail
LAKE=$(realpath "${1:-lakehouse}")
IMG=ceap-e3-medicao
docker build -q -f docker/e3/Dockerfile -t "$IMG" . > /dev/null
docker rm -f adr7_streamlit > /dev/null 2>&1 || true
inicio=$(date +%s)
docker run -d --name adr7_streamlit -p 3902:8501 -v "$LAKE":/app/lakehouse "$IMG" \
    streamlit run painel/app.py --server.address 0.0.0.0 --server.port 8501 > /dev/null
until curl -sf localhost:3902/_stcore/health > /dev/null; do sleep 1; done
fim=$(date +%s)
sleep 30
echo "imagem:            $IMG ($(docker image inspect "$IMG" --format '{{.Size}}' | awk '{printf "%.0f MB", $1/1e6}'), a mesma do pipeline e do Dagster)"
echo "tempo até /health: $((fim - inicio)) s"
echo "memória em repouso: $(docker stats --no-stream --format '{{.MemUsage}}' adr7_streamlit)"
docker rm -f adr7_streamlit > /dev/null
