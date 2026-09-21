#!/bin/bash
# Build every binary for the path-finding pair, at the sizes the
# sources currently carry (P1: db=28 wb=14 hb=14; P2: db=10 kb=18).
set -e
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BEND="$D/../../../scripts/bend.sh"

# P1: one 16384 x 16384 maze, 2^28 cells            expect 1635505109
"$BEND" "$D/p1.bend" -o "$D/p1_bend"
cc -std=c11 -O3 -DWB=14 -DHB=14            "$D/p1.c" -o "$D/p1_c"

# P2: 2^18 mazes of 32 x 32, 2^28 cells in all      expect 3112990347
"$BEND" "$D/p2.bend" -o "$D/p2_bend"
cc -std=c11 -O3 -DWB=5 -DHB=5 -DDEPTH=18   "$D/p2.c" -o "$D/p2_c"

# the algorithm-independent checkers
cc -std=c11 -O3 -DWB=14 -DHB=14 -DDEPTH=0  "$D/verify.c" -o "$D/verify_p1"
cc -std=c11 -O3 -DWB=5 -DHB=5 -DDEPTH=18   "$D/verify.c" -o "$D/verify_p2"

# the tie to the repo's own bench: p2.c at DEPTH=4 must print
# 512822161, the value bench/runtime/bfs/main.bend documents
cc -std=c11 -O3 -DWB=5 -DHB=5 -DDEPTH=4    "$D/p2.c" -o "$D/p2_c_d4"
echo built
