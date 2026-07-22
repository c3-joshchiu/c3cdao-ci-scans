#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

load_config_json() {
  "$ROOT/scripts/lib/load-config.sh" "$1"
}

json_get() {
  local json="$1" query="$2"
  echo "$json" | jq -r "$query // empty"
}

die() {
  echo "error: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1 (brew install $1)"
}
