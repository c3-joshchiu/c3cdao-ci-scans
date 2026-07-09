#!/usr/bin/env bash
# Load repo onboarding YAML config as JSON on stdout.
set -euo pipefail
if [[ $# -lt 1 ]]; then
  echo "usage: load-config.sh <config.yaml>" >&2
  exit 1
fi
ruby -ryaml -rjson -e 'puts JSON.generate(YAML.load_file(ARGV[0]))' "$1"
