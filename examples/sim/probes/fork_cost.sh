#!/usr/bin/env bash
# Wall clock (best of 3) of fork_cost.bend's three modes at work sizes w,
# on 1 thread and on every core. Run on a quiet machine.
set -euo pipefail
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BEND="$D/../../../scripts/bend.sh"
export BEND_NO_TELEMETRY=1
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

best() {
  python3 - "$@" <<'PY'
import subprocess, sys, time
b = float("inf")
for _ in range(3):
    t = time.perf_counter()
    subprocess.run(sys.argv[1:], stdout=subprocess.DEVNULL, check=True)
    b = min(b, time.perf_counter() - t)
print(f"{b:.3f}s")
PY
}

printf '# %s, %s threads, Bend %s\n' "$(uname -sm)" "$(nproc)" "$("$BEND" version | awk '{print $2}')"
printf '%-6s %-6s %-10s %-10s %s\n' w mode 1-thread all-cores output
for w in ${WS:-16 64 256 1024}; do
  for mode in 0 1 2; do
    awk -v w="$w" -v m="$mode" '
      prev == "def w() -> Nat:"    { $0 = "  " w "n" }
      prev == "def mode() -> U32:" { $0 = "  " m }
      { print; prev = $0 }' "$D/fork_cost.bend" > "$work/f.bend"
    "$BEND" "$work/f.bend" -o "$work/f" > /dev/null
    name=$(case $mode in 0) echo plain ;; 1) echo fork ;; 2) echo tree ;; esac)
    printf '%-6s %-6s %-10s %-10s %s\n' "$w" "$name" \
      "$(best "$work/f" --threads 1 --gpu off)" "$(best "$work/f" --gpu off)" "$("$work/f" --gpu off)"
  done
done
