#!/usr/bin/env bash
set -euo pipefail

./scripts/lint.sh
./scripts/test.sh
./scripts/guard.sh
