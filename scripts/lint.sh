#!/usr/bin/env bash
set -euo pipefail

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
else
  echo "python or python3 is required" >&2
  exit 127
fi

"$PYTHON_BIN" -m compileall src tests scripts
"$PYTHON_BIN" scripts/guards/python_compatibility.py
if command -v uv >/dev/null 2>&1; then
  uv run ruff check src tests scripts
  uv run ruff format --check src tests scripts
elif command -v ruff >/dev/null 2>&1; then
  ruff check src tests scripts
  ruff format --check src tests scripts
elif "$PYTHON_BIN" -c "import ruff" >/dev/null 2>&1; then
  "$PYTHON_BIN" -m ruff check src tests scripts
  "$PYTHON_BIN" -m ruff format --check src tests scripts
fi

if command -v node >/dev/null 2>&1; then
  while IFS= read -r js_file; do
    node --check "$js_file"
  done < <(find browser-cli-extension -type f -name '*.js' | sort)
  node --test browser-cli-extension/tests/popup_view.test.js
fi
