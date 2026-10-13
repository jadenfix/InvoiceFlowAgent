#!/usr/bin/env bash
# Canonical real pipeline, preserving existing resources after the demo.
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$TASK_ROOT"
command -v docker >/dev/null || { echo 'Docker is required for the real PostgreSQL/RabbitMQ pipeline.' >&2; exit 1; }
docker compose version >/dev/null
BUILD_FLAG=(--build)
if [[ "${1:-}" == --no-build ]]; then BUILD_FLAG=(); fi
docker compose -f docker-compose.pipeline.yml up -d "${BUILD_FLAG[@]}" --wait --wait-timeout 240
python -m pip install -r services/pipeline/requirements.txt
python scripts/check_pipeline_http.py
echo 'Pipeline is running on http://127.0.0.1:8003. Data persists in named volumes.'
echo 'Stop it with: docker compose -f docker-compose.pipeline.yml down'
