#!/usr/bin/env bash
# Orchestrator: render callers → create ruleset (disabled) → smoke → optional enable.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
usage: onboard-repo.sh --config <yaml> [options]

Steps:
  0. enable-reusable-access.sh (private consumer)
  0b. set-secrets.sh (optional — from config secrets.env_files)
  1. discover-check-names (informational)
  2. render-callers.sh        → target .github/workflows/
  2b. prepare-pilot-pr.sh     → clean branch + PR (optional)
  3. setup-ruleset.sh         → GitHub ruleset (disabled by default)
  4. smoke-test.sh
  5. --enable                 → flip ruleset to active

Options:
  --dry-run       Print actions without writing
  --skip-render   Skip caller workflow generation
  --skip-ruleset  Skip ruleset create/update
  --enable-access Run enable-reusable-access.sh before render
  --set-secrets   Push gate secrets from config secrets.env_files
  --pilot-pr      Run prepare-pilot-pr.sh after render (commit + push + PR)
  --enable        Enable ruleset after smoke test passes
  --pr <n>        PR number for check discovery / smoke test

Examples:
  ./scripts/onboard-repo.sh --config configs/examples/example-monorepo.yaml --dry-run
  ./scripts/onboard-repo.sh --config configs/examples/example-monorepo.yaml
  ./scripts/onboard-repo.sh --config configs/examples/example-fork.yaml --enable

Profile swap: change \`ruleset.profile\`.
EOF
}

CONFIG=""
DRY_RUN=0
SKIP_RENDER=0
SKIP_RULESET=0
ENABLE=0
ENABLE_ACCESS=0
SET_SECRETS=0
PILOT_PR=0
PR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --skip-render) SKIP_RENDER=1; shift ;;
    --skip-ruleset) SKIP_RULESET=1; shift ;;
    --enable-access) ENABLE_ACCESS=1; shift ;;
    --set-secrets) SET_SECRETS=1; shift ;;
    --pilot-pr) PILOT_PR=1; shift ;;
    --enable) ENABLE=1; shift ;;
    --pr) PR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 1 ;;
  esac
done

[[ -n "$CONFIG" ]] || { usage; exit 1; }
[[ -f "$CONFIG" ]] || { echo "config not found: $CONFIG" >&2; exit 1; }

render_args=(--config "$CONFIG")
ruleset_args=(--config "$CONFIG")
smoke_args=(--config "$CONFIG")
discover_args=(--config "$CONFIG")
[[ -n "$PR" ]] && smoke_args+=(--pr "$PR") discover_args+=(--pr "$PR")
[[ "$DRY_RUN" -eq 1 ]] && render_args+=(--dry-run) ruleset_args+=(--dry-run)

if [[ "$ENABLE_ACCESS" -eq 1 ]]; then
  echo "=== Step 0: enable reusable workflow access ==="
  "$ROOT/scripts/enable-reusable-access.sh" --config "$CONFIG"
fi

if [[ "$SET_SECRETS" -eq 1 ]]; then
  echo "=== Step 0b: set gate secrets ==="
  secret_args=(--config "$CONFIG")
  [[ "$DRY_RUN" -eq 1 ]] && secret_args+=(--dry-run)
  "$ROOT/scripts/set-secrets.sh" "${secret_args[@]}"
fi

echo "=== Step 1: discover check names ==="
"$ROOT/scripts/discover-check-names.sh" "${discover_args[@]}" || true

if [[ "$SKIP_RENDER" -eq 0 ]]; then
  echo "=== Step 2: render caller workflows ==="
  "$ROOT/scripts/render-callers.sh" "${render_args[@]}"
else
  echo "=== Step 2: skipped (--skip-render) ==="
fi

if [[ "$PILOT_PR" -eq 1 ]]; then
  echo "=== Step 2b: prepare pilot PR ==="
  pilot_args=(--config "$CONFIG")
  [[ "$DRY_RUN" -eq 1 ]] && pilot_args+=(--dry-run)
  "$ROOT/scripts/prepare-pilot-pr.sh" "${pilot_args[@]}"
fi

if [[ "$SKIP_RULESET" -eq 0 ]]; then
  echo "=== Step 3: setup ruleset (disabled unless --enable) ==="
  if [[ "$ENABLE" -eq 1 ]]; then
    ruleset_args+=(--enable)
  fi
  "$ROOT/scripts/setup-ruleset.sh" "${ruleset_args[@]}"
else
  echo "=== Step 3: skipped (--skip-ruleset) ==="
fi

if [[ "$DRY_RUN" -eq 0 ]]; then
  echo "=== Step 4: smoke test ==="
  "$ROOT/scripts/smoke-test.sh" "${smoke_args[@]}"
else
  echo "=== Step 4: skipped (dry-run) ==="
fi

if [[ "$ENABLE" -eq 1 && "$DRY_RUN" -eq 0 && "$SKIP_RULESET" -eq 0 ]]; then
  echo "=== Step 5: ruleset enabled via setup-ruleset.sh --enable ==="
fi

echo "Done. Commit rendered workflows in target repo and push before expecting checks on PRs."
