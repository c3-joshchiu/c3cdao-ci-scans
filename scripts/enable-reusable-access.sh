#!/usr/bin/env bash
# Enable private consumer repo to use reusable workflows from user-owned repos.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

usage() {
  cat <<'EOF'
usage: enable-reusable-access.sh --config <yaml> [--level user|organization|none]

Sets repos/{owner}/{repo}/actions/permissions/access on the **ci_scans** repo
(the one holding reusable-security-gate.yml). This is a callee-side policy —
it controls which outside workflows may call *into* ci_scans, so it must be
set on ci_scans, not on the consumer/target repo.

Public ci-scans repo does not need this (access policy only applies to
internal/private repos) — the script is a no-op in that case.

Default level: user
EOF
}

CONFIG=""
LEVEL="user"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2 ;;
    --level) LEVEL="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown arg: $1" ;;
  esac
done
[[ -n "$CONFIG" ]] || { usage; exit 1; }

require_cmd gh
require_cmd jq

json="$(load_config_json "$CONFIG")"
owner="$(json_get "$json" '.ci_scans.owner')"
repo="$(json_get "$json" '.ci_scans.repo')"
target="${owner}/${repo}"

visibility="$(gh repo view "$target" --json visibility -q .visibility)"
if [[ "$visibility" == "PUBLIC" ]]; then
  echo "NOTE: ${target} is public — access policy usually unnecessary"
fi

before="$(gh api "repos/${owner}/${repo}/actions/permissions/access" --jq .access_level 2>/dev/null || echo unknown)"
gh api -X PUT "repos/${owner}/${repo}/actions/permissions/access" \
  -f "access_level=${LEVEL}" >/dev/null
after="$(gh api "repos/${owner}/${repo}/actions/permissions/access" --jq .access_level)"

echo "PASS: ${target} reusable access ${before} → ${after}"
