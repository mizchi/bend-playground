#!/bin/bash
# The four columns, for both programs. P1 needs a bigger GPU span:
# its three 2^28-cell arrays are 3.2 GB, over the 2 GB default.
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "# P1  one 16384 x 16384 maze, 2^28 cells   expect 1635505109"
"$D/p1_c"                                 # C, 1 core
"$D/p1_bend" --threads 1 --gpu off        # Bend SEQ
"$D/p1_bend" --gpu off                    # Bend PAR (10 core)
"$D/p1_bend" --gpu 8GB                    # Bend GPU
echo "# P2  2^18 mazes of 32 x 32, 2^28 cells    expect 3112990347"
"$D/p2_c"                                 # C, 1 core
"$D/p2_bend" --threads 1 --gpu off        # Bend SEQ
"$D/p2_bend" --gpu off                    # Bend PAR (10 core)
"$D/p2_bend"                              # Bend GPU
