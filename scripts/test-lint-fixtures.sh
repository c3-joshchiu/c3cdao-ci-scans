#!/usr/bin/env bash
# Assert every caller-lint fixture's verdict by filename convention:
#   clean-*.yml  -> lint must PASS (exit 0)
#   bad-*.yml    -> lint must FAIL (exit 1)
# Gates all lint rules: a rule that silently stops firing flips its bad-* fixture
# to exit 0 and this check goes red. Always runs with --consumer-root so the
# image-values rule is exercised (two fixtures depend on it). Run locally or in CI.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTRACT="$ROOT/contract/security-gate.schema.json"
CONSUMER="$ROOT/tests/fixtures/consumer"
FIXTURES="$ROOT/tests/fixtures/callers"

fail=0
count=0
for f in "$FIXTURES"/*.yml; do
  [ -e "$f" ] || continue
  count=$((count + 1))
  base="$(basename "$f")"
  out="$(uv run --quiet "$ROOT/scripts/lib/lint_caller.py" "$f" \
    --contract "$CONTRACT" --consumer-root "$CONSUMER" 2>/dev/null)"
  rc=$?
  case "$base" in
    clean-*)
      if [ "$rc" -eq 0 ]; then
        echo "PASS $base (clean)"
      else
        echo "FAIL $base: expected exit 0, got $rc"; echo "$out"; fail=1
      fi
      ;;
    bad-*)
      if [ "$rc" -eq 1 ]; then
        echo "PASS $base (rejected)"
      else
        echo "FAIL $base: expected exit 1, got $rc"; fail=1
      fi
      ;;
    *)
      echo "FAIL $base: fixture name must start with 'clean-' or 'bad-'"; fail=1
      ;;
  esac
done

if [ "$count" -eq 0 ]; then
  echo "FAIL: no fixtures found under $FIXTURES"
  exit 1
fi
echo "checked $count fixture(s)"
[ "$fail" -eq 0 ] || { echo "== lint-fixture check FAILED =="; exit 1; }
echo "== lint-fixture check OK =="
