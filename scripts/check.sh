#!/usr/bin/env bash
set -euo pipefail

./scripts/lint.sh
./scripts/guard.sh
