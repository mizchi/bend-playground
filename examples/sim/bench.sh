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

# best-of-3 wall clock and the largest max RSS, as "seconds MB"
measure() {
  python3 - "$@" <<'PY'
import resource, subprocess, sys, time
best = float("inf")
for _ in range(3):
    t = time.perf_counter()
    subprocess.run(sys.argv[1:], stdout=subprocess.DEVNULL, check=True)
    best = min(best, time.perf_counter() - t)
rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
print(f"{best:.3f}s {rss:.0f}MB")
PY
}

printf '# %s, %s threads, %s\n' "$(uname -sm)" "$(nproc)" "$("$CC" --version | head -n 1)"
printf '# Bend %s (%s)\n' "$("$BEND" version | awk '{print $2}')" \
  "$(git -C "${BEND_REPO:-$ROOT/upstream/bend}" rev-parse --short=8 HEAD)"
printf '%-8s %-16s %-16s %-16s %s\n' program c bend-1core bend-allcores output
for name in "$@"; do
  "$BEND" "$D/$name.bend" -o "$OUT/$name" > /dev/null
  "$CC" -std=c11 -O3 -ffp-contract=off "$D/$name.c" -lm -o "$OUT/${name}_c"
  printf '%-8s %-16s %-16s %-16s %s\n' "$name" \
    "$(measure "$OUT/${name}_c")" \
    "$(measure "$OUT/$name" --threads 1 --gpu off)" \
    "$(measure "$OUT/$name" --gpu off)" \
    "$("$OUT/$name" --gpu off)"
done
