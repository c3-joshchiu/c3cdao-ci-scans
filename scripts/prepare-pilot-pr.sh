#!/usr/bin/env bash
# Render caller on a clean branch from default_branch and open a pilot PR.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

usage() {
  cat <<'EOF'
usage: prepare-pilot-pr.sh --config <yaml> [options]

Avoids conflicted long-lived branches by branching from default_branch, rendering
the caller workflow, committing, pushing, and opening a PR.

Options:
  --branch <name>     Pilot branch (default: ci-scans/pilot)
  --title <text>      PR title
  --dry-run           Print git/gh commands only
  --skip-pr           Commit + push only

Example:
  ./scripts/prepare-pilot-pr.sh --config configs/my-repo.yaml
EOF
}

CONFIG=""
BRANCH="ci-scans/pilot"
TITLE=""
DRY_RUN=0
SKIP_PR=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --title) TITLE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --skip-pr) SKIP_PR=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown arg: $1" ;;
  esac
done
[[ -n "$CONFIG" ]] || { usage; exit 1; }

require_cmd gh
require_cmd git

json="$(load_config_json "$CONFIG")"
owner="$(json_get "$json" '.target.owner')"
repo="$(json_get "$json" '.target.repo')"
default_branch="$(json_get "$json" '.target.default_branch')"
local_path="$(json_get "$json" '.target.local_path')"
[[ -n "$local_path" && -d "$local_path" ]] || die "target.local_path not found: $local_path"

[[ -n "$TITLE" ]] || TITLE="ci-scans pilot: Security Scan reusable gate"

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY-RUN: $*"
  else
    "$@"
  fi
}

"$ROOT/scripts/render-callers.sh" --config "$CONFIG"
[[ "$DRY_RUN" -eq 1 ]] && "$ROOT/scripts/render-callers.sh" --config "$CONFIG" --dry-run >/dev/null

(
  cd "$local_path"
  run git fetch origin "$default_branch"
  run git checkout -B "$BRANCH" "origin/${default_branch}"
  run git add .github/workflows/security-gate.yml .github/workflows/.ci-scans-onboard.json
  if git diff --cached --quiet; then
    echo "no caller changes to commit"
  else
    run git commit -m "ci-scans: add Security Scan reusable gate caller"
  fi
  run git push -u origin "$BRANCH" --force-with-lease
)

if [[ "$SKIP_PR" -eq 0 ]]; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY-RUN: gh pr create --repo ${owner}/${repo} --base ${default_branch} --head ${BRANCH}"
  else
    url="$(gh pr create --repo "${owner}/${repo}" --base "$default_branch" --head "$BRANCH" \
      --title "$TITLE" \
      --body "Pilot PR for c3cdao-ci-scans security gate onboarding.")"
    echo "PR: $url"
  fi
fi

echo "Done. Wait for Security Scan run, then:"
echo "  ./scripts/discover-check-names.sh --config $CONFIG --pr <N>"
echo "  ./scripts/smoke-test.sh --config $CONFIG --pr <N>"
