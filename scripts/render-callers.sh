#!/usr/bin/env bash
# Step 2a: render security-gate caller into target repo.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$ROOT/scripts/lib/common.sh"

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
    *) die "unknown arg: $1" ;;
  esac
done
[[ -n "$CONFIG" ]] || { usage; exit 1; }

json="$(load_config_json "$CONFIG")"
local_path="$(json_get "$json" '.target.local_path')"
[[ -n "$local_path" ]] || die "target.local_path required"
[[ -d "$local_path" ]] || die "local_path not found: $local_path"

out_dir="$(cd "$local_path" && pwd)/.github/workflows"
mkdir -p "$out_dir"

sg() { json_get "$json" "$1"; }

rendered="$(render_template "$ROOT/templates/callers/security-gate.yml.tpl" \
  "CI_SCANS_OWNER" "$(sg '.ci_scans.owner')" \
  "CI_SCANS_REPO" "$(sg '.ci_scans.repo')" \
  "CI_SCANS_REF" "$(sg '.ci_scans.ref')" \
  "TRUNK_BRANCHES_YAML" "$(trunk_branches_yaml "$json")" \
  "SCAN_IMAGE" "$(sg '.security_gate.scan_image // "app:local"')" \
  "DOCKERFILE" "$(sg '.security_gate.dockerfile // "containers/backend/Dockerfile"')" \
  "BUILDER_IMAGE" "$(sg '.security_gate.builder_image // "cgr.dev/chainguard/python:latest-dev"')" \
  "RUNTIME_IMAGE" "$(sg '.security_gate.runtime_image // "cgr.dev/chainguard/python:latest"')" \
  "RUNTIME_APKS" "$(sg '.security_gate.runtime_apks // ""')" \
  "HELM_CHART_PATH" "$(sg '.security_gate.helm_chart_path // "helm/app"')" \
  "HELM_VALUES_FILE" "$(sg '.security_gate.helm_values_file // "helm/app/values.yaml"')" \
  "HELM_VALUES_LOCAL_FILE" "$(sg '.security_gate.helm_values_local_file // "helm/app/values-local.yaml"')" \
  "HELM_RELEASE_NAME" "$(sg '.security_gate.helm_release_name // "app-ci"')" \
  "CLUSTER_NAME" "$(sg '.security_gate.cluster_name // "app-ci"')" \
  "NAMESPACE" "$(sg '.security_gate.namespace // "app-ci"')" \
  "SECCTX_MAKE_TARGET" "$(sg '.security_gate.secctx_make_target // "security-helm-secctx"')" \
  "APP_PATH" "$(sg '.security_gate.app_path // "apps/app/backend"')" \
  "APP_PACKAGE" "$(sg '.security_gate.app_package // "app-backend"')" \
  "APP_MODULE" "$(sg '.security_gate.app_module // "app.main:app"')" \
  "APP_PORT" "$(sg '.security_gate.app_port // "8000"')" \
  "REQUIRE_HARDENED_BASES" "$(echo "$json" | jq -r '.security_gate.require_hardened_bases | if . == null then true else . end')" \
  "IRONBANK_BUILDER_IMAGE" "$(sg '.security_gate.ironbank_builder_image // ""')" \
  "IRONBANK_RUNTIME_IMAGE" "$(sg '.security_gate.ironbank_runtime_image // ""')" \
  "EXTRA_BUILD_ARGS" "$(echo "$json" | jq -r '[.security_gate.extra_build_args // [] | .[]] | join("\n        ")')" )"

dest="$out_dir/security-gate.yml"
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "# would write $dest"
  echo "$rendered"
else
  printf '%s\n' "$rendered" >"$dest"
  cat >"$out_dir/.ci-scans-onboard.json" <<EOF
{"source":"c3cdao-ci-scans","workflow":"security-gate","ci_scans":"$(sg '.ci_scans.owner')/$(sg '.ci_scans.repo')@$(sg '.ci_scans.ref')"}
EOF
  echo "wrote $dest"
  echo "remove legacy modular scan workflows in consumer repo if migrating from mini-scans"
fi
