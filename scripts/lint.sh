#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 127
fi

uv run python -m compileall src tests scripts
uv run python scripts/guards/python_compatibility.py
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts

if command -v node >/dev/null 2>&1; then
  while IFS= read -r js_file; do
    node --check "$js_file"
  done < <(find browser-cli-extension -type f -name '*.js' | sort)
  node --test browser-cli-extension/tests/popup_view.test.js
fi
