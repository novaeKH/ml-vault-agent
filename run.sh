#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [[ ! -x ".venv/bin/uvicorn" ]]; then
  echo "Сначала выполните: ./setup.sh"
  exit 1
fi

mkdir -p data
if command -v ollama >/dev/null 2>&1 \
  && ! curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  nohup ollama serve >data/ollama.log 2>&1 &
  for _ in {1..30}; do
    curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break
    sleep 1
  done
fi

echo "ML Vault Agent: http://127.0.0.1:8787"
echo "Остановить: Ctrl+C"
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8787
