#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKIP_MODELS=0
SKIP_INDEX=0

for argument in "$@"; do
  case "$argument" in
    --skip-models) SKIP_MODELS=1 ;;
    --skip-index) SKIP_INDEX=1 ;;
    *)
      echo "Неизвестный аргумент: $argument"
      echo "Допустимо: --skip-models --skip-index"
      exit 2
      ;;
  esac
done

choose_python() {
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      "$candidate" -c 'import sys; raise SystemExit(not ((3, 11) <= sys.version_info[:2] < (3, 15)))' \
        >/dev/null 2>&1 && {
          command -v "$candidate"
          return 0
        }
    fi
  done
  return 1
}

PYTHON_BIN="$(choose_python || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "Нужен Python 3.11–3.14. Установите, например: brew install python@3.13"
  exit 1
fi

cd "$PROJECT_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "→ Создаю локальное Python-окружение…"
  "$PYTHON_BIN" -m venv .venv
fi

echo "→ Устанавливаю небольшой backend…"
.venv/bin/python -m pip install --disable-pip-version-check -e ".[dev]"

if [[ "$SKIP_MODELS" -eq 0 ]]; then
  if ! command -v ollama >/dev/null 2>&1; then
    echo
    echo "Ollama не найдена. Установите её и повторите setup:"
    echo "  brew install --cask ollama"
    echo "  или https://ollama.com/download"
    exit 1
  fi

  mkdir -p data
  if ! curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "→ Запускаю Ollama…"
    nohup ollama serve >data/ollama.log 2>&1 &
    for _ in {1..30}; do
      curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break
      sleep 1
    done
  fi

  for model in "qwen3:8b" "qwen3-embedding:0.6b"; do
    if ollama show "$model" >/dev/null 2>&1; then
      echo "✓ $model уже установлена"
    else
      echo "→ Загружаю $model (один раз)…"
      ollama pull "$model"
    fi
  done
fi

if [[ "$SKIP_INDEX" -eq 0 ]]; then
  if .venv/bin/python -c \
    'from app.config import load_settings; raise SystemExit(0 if load_settings().vault_path else 1)'; then
    echo "→ Строю read-only индекс Obsidian…"
    .venv/bin/python -m app.cli reindex
  else
    echo "→ Vault пока не выбран. Укажите папку в web-интерфейсе после запуска."
  fi
fi

echo
echo "Готово. Запуск:"
echo "  ./run.sh"
echo
echo "Затем откройте http://127.0.0.1:8787"
