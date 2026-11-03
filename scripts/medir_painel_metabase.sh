#!/usr/bin/env bash
# Medição do ADR-0007: tempo até o Metabase responder /api/health e memória em repouso,
# numa instância vazia (sem banco de aplicação externo, sem dashboards).
# Uso: bash scripts/medir_painel_metabase.sh
set -euo pipefail
IMG=metabase/metabase:v0.50.36
docker pull -q "$IMG" > /dev/null
docker rm -f adr7_metabase > /dev/null 2>&1 || true
inicio=$(date +%s)
docker run -d --name adr7_metabase -p 3901:3000 "$IMG" > /dev/null
until curl -sf localhost:3901/api/health > /dev/null; do sleep 2; done
fim=$(date +%s)
sleep 30
echo "imagem:            $IMG ($(docker image inspect "$IMG" --format '{{.Size}}' | awk '{printf "%.0f MB", $1/1e6}'))"
echo "tempo até /health: $((fim - inicio)) s"
echo "memória em repouso: $(docker stats --no-stream --format '{{.MemUsage}}' adr7_metabase)"
docker rm -f adr7_metabase > /dev/null
