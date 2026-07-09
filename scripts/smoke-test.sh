#!/usr/bin/env bash
# Step 4: smoke test before enabling ruleset enforcement.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

usage() {
  cat <<'EOF'
usage: smoke-test.sh --config <yaml> [--pr <number>]

Validates:
  - gh auth + repo admin
  - caller workflow files exist locally
  - reusable workflow ref resolves (ci_scans repo reachable)
  - profile checks appear on PR (or warns if missing)
  - ruleset exists (if ruleset_id set)
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

require_cmd gh
require_cmd jq

json="$(load_config_json "$CONFIG")"
owner="$(json_get "$json" '.target.owner')"
target_repo="$(json_get "$json" '.target.repo')"
local_path="$(json_get "$json" '.target.local_path')"
ci_owner="$(json_get "$json" '.ci_scans.owner')"
ci_repo="$(json_get "$json" '.ci_scans.repo')"
ci_ref="$(json_get "$json" '.ci_scans.ref')"
ruleset_id="$(json_get "$json" '.ruleset.ruleset_id')"
profile="$(json_get "$json" '.ruleset.profile')"

fail=0
pass() { echo "PASS: $*"; }
warn() { echo "WARN: $*"; }
fail_msg() { echo "FAIL: $*"; fail=1; }

echo "== smoke test: ${owner}/${target_repo} profile=${profile} =="

if gh api "repos/${owner}/${target_repo}" --jq '.permissions.admin' 2>/dev/null | grep -q true; then
  pass "repo admin via gh"
else
  fail_msg "need repo admin on ${owner}/${target_repo}"
fi

if gh repo view "${ci_owner}/${ci_repo}" --json name -q .name >/dev/null 2>&1; then
  pass "ci_scans repo reachable (${ci_owner}/${ci_repo}@${ci_ref})"
else
  fail_msg "cannot reach ${ci_owner}/${ci_repo}"
fi

enabled=()
while IFS= read -r line; do
  [[ -n "$line" ]] && enabled+=("$line")
done < <(json_get_array "$json" '.workflows.enabled')
if [[ -n "$local_path" && -d "$local_path" ]]; then
  for wf in "${enabled[@]}"; do
    f="${local_path}/.github/workflows/${wf}.yml"
    if [[ -f "$f" ]]; then pass "caller exists: ${wf}.yml"; else fail_msg "missing caller: $f"; fi
  done
else
  warn "target.local_path not set — skipping caller file checks"
fi

expected=()
while IFS= read -r line; do
  [[ -n "$line" ]] && expected+=("$line")
done < <(apply_check_overrides "$json")
if [[ -z "$PR" ]]; then
  PR="$(gh pr list --repo "${owner}/${target_repo}" --state open --limit 1 --json number -q '.[0].number' 2>/dev/null || true)"
fi
if [[ -n "$PR" && "$PR" != "null" ]]; then
  sha="$(gh pr view "$PR" --repo "${owner}/${target_repo}" --json headRefOid -q .headRefOid)"
  live=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && live+=("$line")
  done < <(gh api "repos/${owner}/${target_repo}/commits/${sha}/check-runs" --paginate \
    --jq '[.check_runs[] | select(.app.slug=="github-actions") | .name] | unique | .[]')
  for check in "${expected[@]}"; do
    if printf '%s\n' "${live[@]}" | grep -Fxq "$check"; then
      pass "PR #${PR} has check: ${check}"
    else
      warn "PR #${PR} missing check (may be path-filtered or not run yet): ${check}"
    fi
  done
else
  warn "no open PR — skipping live check-name verification"
fi

if [[ -n "$ruleset_id" && "$ruleset_id" != "null" ]]; then
  if gh api "repos/${owner}/${target_repo}/rulesets/${ruleset_id}" --jq .name >/dev/null 2>&1; then
    pass "ruleset id ${ruleset_id} exists"
  else
    fail_msg "ruleset id ${ruleset_id} not found"
  fi
else
  warn "ruleset.ruleset_id not set — run setup-ruleset.sh first"
fi

if [[ "$fail" -eq 0 ]]; then
  echo "== smoke test OK =="
  exit 0
fi
echo "== smoke test FAILED =="
exit 1
