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

if command -v node >/dev/null 2>&1; then
  while IFS= read -r js_file; do
    node --check "$js_file"
  done < <(find browser-cli-extension -type f -name '*.js' | sort)
fi

"$PYTHON_BIN" -m pytest -q
