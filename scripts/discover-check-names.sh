#!/usr/bin/env bash
# Step 1: discover live GHA check context names from an open PR (optional).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

usage() {
  cat <<'EOF'
usage: discover-check-names.sh --config <yaml> [--pr <number>]

Prints check names from a live PR, or falls back to profile required_checks.
EOF
}

CONFIG=""
PR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2 ;;
    --pr) PR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown arg: $1" ;;
  esac
done
[[ -n "$CONFIG" ]] || { usage; exit 1; }

json="$(load_config_json "$CONFIG")"
owner="$(json_get "$json" '.target.owner')"
repo="$(json_get "$json" '.target.repo')"
profile="$(json_get "$json" '.ruleset.profile')"

if [[ -n "$PR" ]]; then
  sha="$(gh pr view "$PR" --repo "$owner/$repo" --json headRefOid -q .headRefOid)"
  gh api "repos/${owner}/${repo}/commits/${sha}/check-runs" --paginate \
    --jq '[.check_runs[] | select(.app.slug=="github-actions") | .name] | unique | sort | .[]'
  exit 0
fi

if [[ -z "$PR" ]]; then
  PR="$(gh pr list --repo "$owner/$repo" --state open --limit 1 --json number -q '.[0].number' 2>/dev/null || true)"
fi
if [[ -n "$PR" && "$PR" != "null" ]]; then
  sha="$(gh pr view "$PR" --repo "$owner/$repo" --json headRefOid -q .headRefOid)"
  echo "# Live checks from PR #${PR}" >&2
  gh api "repos/${owner}/${repo}/commits/${sha}/check-runs" --paginate \
    --jq '[.check_runs[] | select(.app.slug=="github-actions") | .name] | unique | sort | .[]'
  exit 0
fi

echo "# No open PR — using profile ${profile}" >&2
ruby -ryaml -e '
  p = YAML.load_file(ARGV[0])
  (p["required_checks"] || []).each { |c| puts c }
' "$ROOT/config/profiles/${profile}.yaml"
