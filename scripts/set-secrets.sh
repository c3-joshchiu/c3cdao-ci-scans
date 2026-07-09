#!/usr/bin/env bash
# Push security-gate secrets to target repo via gh (never prints values).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

usage() {
  cat <<'EOF'
usage: set-secrets.sh --config <yaml> [options]

Reads KEY=VALUE pairs from dotenv file(s) and sets GitHub Actions repo secrets
on the target consumer via `gh secret set` (values encrypted client-side).

Options:
  --env-file <path>   Dotenv file (repeatable; overrides config secrets.env_files)
  --dry-run           Show which secrets would be set; do not call gh
  --only <name>       Set a single secret (repeatable)

Default secret names (unless config secrets.names is set):
  CGR_PULL_TOKEN, CGR_PULL_USERNAME, IRONBANK_TOKEN, IRONBANK_USERNAME

Examples:
  ./scripts/set-secrets.sh --config configs/my-repo.yaml
  ./scripts/set-secrets.sh --config configs/my-repo.yaml --env-file ../other/.env
  ./scripts/set-secrets.sh --config configs/my-repo.yaml --dry-run
EOF
}

CONFIG=""
DRY_RUN=0
ENV_FILES=()
ONLY=()
DEFAULT_NAMES=(CGR_PULL_TOKEN CGR_PULL_USERNAME IRONBANK_TOKEN IRONBANK_USERNAME)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2 ;;
    --env-file) ENV_FILES+=("$2"); shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --only) ONLY+=("$2"); shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown arg: $1" ;;
  esac
done
[[ -n "$CONFIG" ]] || { usage; exit 1; }

require_cmd gh
require_cmd jq

json="$(load_config_json "$CONFIG")"
owner="$(json_get "$json" '.target.owner')"
repo="$(json_get "$json" '.target.repo')"
target="${owner}/${repo}"

if [[ ${#ENV_FILES[@]} -eq 0 ]]; then
  while IFS= read -r line; do
    [[ -n "$line" ]] && ENV_FILES+=("$line")
  done < <(json_get_array "$json" '.secrets.env_files')
fi

names=()
if [[ ${#ONLY[@]} -gt 0 ]]; then
  names=("${ONLY[@]}")
else
  while IFS= read -r line; do
    [[ -n "$line" ]] && names+=("$line")
  done < <(json_get_array "$json" '.secrets.names')
  [[ ${#names[@]} -eq 0 ]] && names=("${DEFAULT_NAMES[@]}")
fi

# Resolve env file paths relative to ci-scans repo root (same as target.local_path).
resolved_files=()
for f in "${ENV_FILES[@]}"; do
  [[ -z "$f" ]] && continue
  if [[ "$f" != /* ]]; then
    f="${ROOT}/${f}"
  fi
  [[ -f "$f" ]] || die "env file not found: $f"
  resolved_files+=("$f")
done
[[ ${#resolved_files[@]} -gt 0 ]] || die "no env files — set secrets.env_files in config or pass --env-file"

# Merge KEY=VALUE from files (later files override earlier) into a temp map file.
map_file="$(mktemp)"
trap 'rm -f "$map_file"' EXIT
for env_file in "${resolved_files[@]}"; do
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -z "$line" || "$line" != *=* ]] && continue
    key="${line%%=*}"
    printf '%s\n' "$line" >>"$map_file"
  done <"$env_file"
done

get_value() {
  local key="$1"
  { grep -E "^${key}=" "$map_file" 2>/dev/null || true; } | tail -1 | cut -d= -f2- \
    | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

if ! gh api "repos/${target}" --jq '.permissions.admin' 2>/dev/null | grep -q true; then
  die "need repo admin on ${target} (gh auth login)"
fi

set_count=0
skip_count=0
for name in "${names[@]}"; do
  val="$(get_value "$name")"
  if [[ -z "$val" ]]; then
    echo "SKIP: ${name} (not in env file(s))"
    skip_count=$((skip_count + 1))
    continue
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY-RUN: would set ${name} on ${target}"
  else
    printf '%s' "$val" | gh secret set "$name" --repo "$target"
    echo "SET: ${name} on ${target}"
  fi
  set_count=$((set_count + 1))
done

echo "== set-secrets: ${set_count} set, ${skip_count} skipped (target ${target}) =="
[[ "$set_count" -gt 0 || "$DRY_RUN" -eq 1 ]] || die "no secrets set — add keys to env file(s) or adjust secrets.names"
