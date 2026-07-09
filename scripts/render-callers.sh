#!/usr/bin/env bash
# Step 2a: render security-gate caller into target repo.
# Thin wrapper — the actual rendering lives in scripts/lib/render_caller.py
# (schema-validated config, schema defaults, exact booleans, indent-safe
# multiline substitution).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  echo "usage: render-callers.sh --config <yaml> [--dry-run]"
}

CONFIG=""
DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown arg: $1" >&2; usage; exit 1 ;;
  esac
done
[[ -n "$CONFIG" ]] || { usage; exit 1; }

command -v uv >/dev/null 2>&1 || { echo "error: missing required command: uv (brew install uv)" >&2; exit 1; }

args=(--config "$CONFIG")
[[ "$DRY_RUN" -eq 1 ]] && args+=(--dry-run)
exec uv run --quiet "$ROOT/scripts/lib/render_caller.py" "${args[@]}"
