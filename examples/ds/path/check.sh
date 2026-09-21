#!/bin/bash
# The correctness gate, no timing. Three things:
#   1  p1.bend and p2.bend are the same program at the same grain
#   2  p2 reproduces the value bench/runtime/bfs/main.bend documents
#   3  SEQ, PAR, GPU and the C twin agree, and the distance map
#      satisfies the graph-distance invariants
# It rebuilds small variants in a temp dir and leaves the main
# binaries alone.
set -e
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BEND="$D/../../../scripts/bend.sh"
T="$D/.check"
mkdir -p "$T"

echo "== 1. same grain: P1 at 32x32 == P2 with one maze =="
sed -e 's/^  28n$/  10n/' -e 's/^  14n$/  5n/g' "$D/p1.bend" > "$T/p1_small.bend"
sed -e 's/^  18n$/  0n/' "$D/p2.bend" > "$T/p2_k0.bend"
"$BEND" "$T/p1_small.bend" -o "$T/p1_small"
"$BEND" "$T/p2_k0.bend" -o "$T/p2_k0"
echo -n "  P1 32x32 one maze : "; "$T/p1_small" --threads 1 --gpu off
echo -n "  P2 32x32 one maze : "; "$T/p2_k0" --threads 1 --gpu off

echo "== 2. the repo's own bfs bench value, 512822161 =="
sed -e 's/^  18n$/  4n/' "$D/p2.bend" > "$T/p2_d4.bend"
"$BEND" "$T/p2_d4.bend" -o "$T/p2_d4"
cc -std=c11 -O3 -DWB=5 -DHB=5 -DDEPTH=4 "$D/p2.c" -o "$T/p2_c_d4"
echo -n "  C   : "; "$T/p2_c_d4"
echo -n "  SEQ : "; "$T/p2_d4" --threads 1 --gpu off
echo -n "  PAR : "; "$T/p2_d4" --gpu off
echo -n "  GPU : "; "$T/p2_d4"

echo "== 3. four-way agreement, P1 at 2^24 (fits the default GPU span) =="
sed -e 's/^  28n$/  24n/' -e 's/^  14n$/  12n/g' "$D/p1.bend" > "$T/p1_24.bend"
"$BEND" "$T/p1_24.bend" -o "$T/p1_24"
cc -std=c11 -O3 -DWB=12 -DHB=12 "$D/p1.c" -o "$T/p1_24_c"
cc -std=c11 -O3 -DWB=12 -DHB=12 -DDEPTH=0 "$D/verify.c" -o "$T/verify_24"
echo -n "  C   : "; "$T/p1_24_c"
echo -n "  SEQ : "; "$T/p1_24" --threads 1 --gpu off
echo -n "  PAR : "; "$T/p1_24" --gpu off
echo -n "  GPU : "; "$T/p1_24" --gpu 4GB
echo -n "  inv : "; "$T/verify_24"
