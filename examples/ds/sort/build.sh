#!/bin/bash
# Builds every binary of the sort experiment next to this file.
#   ./build.sh          # the shipped size, 2^25
#   ./build.sh 22       # a smaller run (rewrites size()/DEP for this build only)
set -e
D="$(cd "$(dirname "$0")" && pwd)"
BEND="$D/../../../scripts/bend.sh"
d="${1:-25}"
for f in msort bsort nosort; do
  awk -v d="$d" '/^def size/{p=1;print;next} p{print "  " d "n"; p=0; next} {print}' \
    "$D/$f.bend" > "$D/.sz_$f.bend"
  "$BEND" "$D/.sz_$f.bend" -o "$D/$f"
done
rm -f "$D"/.sz_*.bend
cc -std=c11 -O3 -DDEP="$d" -DMODE=0 "$D/sort.c" -o "$D/c_merge"
cc -std=c11 -O3 -DDEP="$d" -DMODE=1 "$D/sort.c" -o "$D/c_qsort"
cc -std=c11 -O3 -DDEP="$d" -DMODE=2 "$D/sort.c" -o "$D/c_nosort"
echo "built at 2^$d in $D"
