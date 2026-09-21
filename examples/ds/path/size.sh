#!/bin/bash
# Rewrite the pair at a chosen total-cell exponent, so P1 and P2 keep
# walking the same number of cells, then rebuild and re-verify.
#   usage: ./size.sh 28
# P1 becomes one 2^ceil(E/2) x 2^floor(E/2) grid; P2 becomes 2^(E-10)
# mazes of 32 x 32. E must be at least 11. Note that P1 needs
# 3 * 2^E * 4 bytes of GPU span: 2^28 wants --gpu 8GB.
set -e
E=${1:-28}
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BEND="$D/../../../scripts/bend.sh"
WB=$(( (E + 1) / 2 )); HB=$(( E - WB )); K=$(( E - 10 ))

python3 - "$D" "$E" "$WB" "$HB" "$K" <<'PY'
import re, sys
d = sys.argv[1]
e, wb, hb, k = map(int, sys.argv[2:])
s = open(f"{d}/p1.bend").read()
s = re.sub(r"(def db\(\) -> Nat:\n  )\d+n", rf"\g<1>{e}n", s)
s = re.sub(r"(def wb\(\) -> Nat:\n  )\d+n", rf"\g<1>{wb}n", s)
s = re.sub(r"(def hb\(\) -> Nat:\n  )\d+n", rf"\g<1>{hb}n", s)
open(f"{d}/p1.bend", "w").write(s)
s = open(f"{d}/p2.bend").read()
s = re.sub(r"(def kb\(\) -> Nat:\n  )\d+n", rf"\g<1>{k}n", s)
open(f"{d}/p2.bend", "w").write(s)
PY

"$BEND" "$D/p1.bend" -o "$D/p1_bend"
"$BEND" "$D/p2.bend" -o "$D/p2_bend"
cc -std=c11 -O3 -DWB=$WB -DHB=$HB           "$D/p1.c" -o "$D/p1_c"
cc -std=c11 -O3 -DWB=5 -DHB=5 -DDEPTH=$K    "$D/p2.c" -o "$D/p2_c"
cc -std=c11 -O3 -DWB=$WB -DHB=$HB -DDEPTH=0 "$D/verify.c" -o "$D/verify_p1"
cc -std=c11 -O3 -DWB=5 -DHB=5 -DDEPTH=$K    "$D/verify.c" -o "$D/verify_p2"
echo "E=$E   P1 = one 2^$WB x 2^$HB maze   P2 = 2^$K mazes of 32x32   (2^$E cells each)"
echo -n "P1 "; "$D/verify_p1"
echo -n "P2 "; "$D/verify_p2"
