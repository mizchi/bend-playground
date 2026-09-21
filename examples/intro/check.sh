#!/usr/bin/env bash
# 07-bend-intro.md の全サンプル。意図した型エラーも検証する。
set -euo pipefail
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BEND="$D/../../scripts/bend.sh"
passed=0
failed=0
for f in "$D"/*.bend; do
  name="$(basename "$f")"
  expected_status=0
  expected='All terms check.'
  case "$name" in
    s02_*) expected_status=1; expected='consumed more than once' ;;
    s08_*) expected_status=1; expected='expected : Data' ;;
    s09_*) expected_status=1; expected='a decreasing self-call' ;;
    s11_*) expected_status=1; expected='a match cannot scrutinize a computed value' ;;
  esac
  status=0
  output=$("$BEND" "$f" --check-only 2>&1) || status=$?
  if [[ "$status" -eq "$expected_status" && "$output" == *"$expected"* ]]; then
    printf 'PASS %s\n' "$name"
    passed=$((passed + 1))
  else
    printf 'FAIL %s (exit=%s, expected=%s)\n%s\n' "$name" "$status" "$expected_status" "$output" >&2
    failed=$((failed + 1))
  fi
done
printf 'PASS: %s / %s\n' "$passed" "$((passed + failed))"
[[ "$failed" -eq 0 && "$passed" -eq 13 ]]
