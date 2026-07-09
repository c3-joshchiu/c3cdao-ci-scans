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

json_get_array() {
  local json="$1" query="$2"
  echo "$json" | jq -r "$query // [] | .[]?"
}

die() {
  echo "error: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1 (brew install $1)"
}

trunk_branches_yaml() {
  local json="$1"
  echo "$json" | jq -c '[.target.trunk_branches[]]'
}

render_template() {
  local tpl="$1"
  shift
  local content
  content="$(<"$tpl")"
  while [[ $# -ge 2 ]]; do
    local key="$1" val="$2"
    content="${content//\{\{${key}\}\}/${val}}"
    shift 2
  done
  printf '%s\n' "$content"
}

profile_required_checks() {
  local profile="$1"
  ruby -ryaml -e '
    p = YAML.load_file(ARGV[0])
    checks = p["required_checks"] || []
    overrides = p["check_overrides"] || {}
    checks.each { |c| puts overrides.fetch(c, c) }
  ' "$ROOT/config/profiles/${profile}.yaml"
}

apply_check_overrides() {
  local config_json="$1"
  local profile
  profile="$(json_get "$config_json" '.ruleset.profile')"
  # config-level overrides: ruleset.check_overrides in future
  profile_required_checks "$profile"
}
