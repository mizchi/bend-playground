#!/bin/bash
# Correctness matrix.  No timing: only the output line and the user/real split,
# which tells whether a GPU run really reached the device (user ~ 0).
D="$(cd "$(dirname "$0")" && pwd)"
run() {
  local label="$1"; shift
  local tmp; tmp=$(mktemp); local out
  out=$( { /usr/bin/time -p "$@" 1>&3; } 2>"$tmp" 3>&1 )
  printf "%-26s | %-46s | real=%-8s user=%s\n" "$label" "$out" \
    "$(awk '/^real/{print $2}' "$tmp")" "$(awk '/^user/{print $2}' "$tmp")"
  grep -h multiset "$tmp" 2>/dev/null | sed 's/^/                           | /'
  rm -f "$tmp"
}
echo "=== S1 merge sort (Bend) ==="
run "S1 SEQ (1 core)"       "$D/msort" --threads 1 --gpu off
run "S1 PAR (all cores)"    "$D/msort" --gpu off
run "S1 GPU"                "$D/msort"
echo "=== S2 bitonic sort (Bend) ==="
run "S2 SEQ (1 core)"       "$D/bsort" --threads 1 --gpu off
run "S2 PAR (all cores)"    "$D/bsort" --gpu off
run "S2 GPU"                "$D/bsort"
echo "=== C twins (1 core) ==="
run "C1 array merge sort"   "$D/c_merge"
run "C2 qsort(3)"           "$D/c_qsort"
echo "=== negative control: same multiset, NOT sorted ==="
run "NEG Bend SEQ"          "$D/nosort" --threads 1 --gpu off
run "NEG Bend PAR"          "$D/nosort" --gpu off
run "NEG Bend GPU"          "$D/nosort"
run "NEG C"                 "$D/c_nosort"
