#!/usr/bin/env bash
# Bit-exact check: each examples/sim/*.bend against its C twin at a small size.
# Needs a C compiler (CC, default cc); no GPU. Prints PASS/FAIL per program.
set -euo pipefail
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BEND="$D/../../scripts/bend.sh"
CC="${CC:-cc}"
export BEND_NO_TELEMETRY=1
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# rewrite the bodies of `def dep()` and `def steps()` to the given sizes
resize() {
  awk -v dep="$2" -v steps="$3" '
    prev == "def dep() -> Nat:"   { $0 = "  " dep "n" }
    prev == "def steps() -> Nat:" { $0 = "  " steps "n" }
    { print; prev = $0 }' "$1"
}

passed=0
failed=0
check() {
  local name="$1" dep="$2" steps="$3"
  resize "$D/$name.bend" "$dep" "$steps" > "$work/$name.bend"
  "$BEND" "$work/$name.bend" -o "$work/$name" > /dev/null
  "$CC" -std=c11 -O3 -ffp-contract=off -DDEP="$dep" -DSTEPS="$steps" \
    "$D/$name.c" -lm -o "$work/${name}_c"
  local got want
  got="$("$work/$name" --gpu off)"
  want="$("$work/${name}_c" | head -n 1)"
  if [[ -n "$got" && "$got" == "$want" ]]; then
    printf 'PASS %s dep=%s steps=%s: %s\n' "$name" "$dep" "$steps" "$got"
    passed=$((passed + 1))
  else
    printf 'FAIL %s dep=%s steps=%s\n  bend: %s\n  c:    %s\n' \
      "$name" "$dep" "$steps" "$got" "$want" >&2
    failed=$((failed + 1))
  fi
}

check galton 10 2048
check anneal 8 4096
check balls 4 512
printf 'PASS: %s / %s\n' "$passed" "$((passed + failed))"
[[ "$failed" -eq 0 ]]
