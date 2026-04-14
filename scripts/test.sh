#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 127
fi

uv sync --dev --reinstall-package browser-control-and-automation-cli
uv run pytest -q
