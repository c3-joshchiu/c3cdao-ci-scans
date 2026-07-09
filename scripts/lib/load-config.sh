#!/usr/bin/env bash
# Load repo onboarding YAML config as JSON on stdout (schema-validated).
set -euo pipefail
if [[ $# -lt 1 ]]; then
  echo "usage: load-config.sh <config.yaml>" >&2
  exit 1
fi
command -v uv >/dev/null 2>&1 || { echo "error: missing required command: uv (brew install uv)" >&2; exit 1; }
exec uv run --quiet "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/config.py" "$1"
