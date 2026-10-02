#!/usr/bin/env bash
# Wall clock (best of 3) and max RSS of each examples/sim program at the size
# written in its source: the C twin, Bend on one core, Bend on every core.
# Run serially on a quiet machine. Needs clang (Bend's own C compiler, so the
# twins compete on the same backend); no GPU. Writes binaries to build/sim.
set -euo pipefail
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$D/../.."
BEND="$ROOT/scripts/bend.sh"
OUT="$ROOT/build/sim"
CC="${CC:-clang}"
export BEND_NO_TELEMETRY=1
mkdir -p "$OUT"

# the C twin of a program: balls_flat shares balls.c
twin_of() {
  case "$1" in
    balls_flat) echo balls ;;
    *) echo "$1" ;;
  esac
}

# best-of-3 wall clock and the largest max RSS, as "seconds MB"
measure() {
  python3 "$ROOT/scripts/benchmark.py" --rss "$@"
}

printf '# %s, %s threads, %s\n' "$(uname -sm)" "$(getconf _NPROCESSORS_ONLN)" "$("$CC" --version | head -n 1)"
printf '# Bend %s (%s)\n' "$("$BEND" version | awk '{print $2}')" \
  "$(git -C "${BEND_REPO:-$ROOT/upstream/bend}" rev-parse --short=8 HEAD)"
printf '%-8s %-16s %-16s %-16s %s\n' program c bend-1core bend-allcores output
for name in "$@"; do
  "$BEND" "$D/$name.bend" -o "$OUT/$name" > /dev/null
  "$CC" -std=c11 -O3 -ffp-contract=off "$D/$(twin_of "$name").c" -lm -o "$OUT/${name}_c"
  c_time="$(measure "$OUT/${name}_c")"
  bend_one="$(measure "$OUT/$name" --threads 1 --gpu off)"
  bend_all="$(measure "$OUT/$name" --gpu off)"
  output="$("$OUT/$name" --gpu off)"
  printf '%-8s %-16s %-16s %-16s %s\n' "$name" \
    "$c_time" "$bend_one" "$bend_all" "$output"
done
