set positional-arguments

# Show available tasks.
default:
    @just --list

# Fetch the Bend revision recorded in the submodule.
setup:
    git submodule update --init --recursive

# Run Bend (append --check-only for type checking or -o PATH to compile).
bend +args:
    ./scripts/bend.sh "$@"

# Verify portability, the introductory samples, FWHT and the simulations.
test:
    python3 tests/smoke.py

# Check the physics and Monte Carlo samples against their C twins (no GPU).
check-sim:
    ./examples/sim/check.sh

# Time the physics and Monte Carlo samples against their C twins (quiet machine).
bench-sim *programs="galton anneal balls balls_flat fmc mcts":
    ./examples/sim/bench.sh {{programs}}

# Check all 13 introductory samples, including the four expected errors.
check-intro:
    ./examples/intro/check.sh

# Build the path-finding experiment at its current size.
build-path:
    ./examples/ds/path/build.sh

# Run the existing path-finding correctness matrix (requires a GPU).
check-path:
    ./examples/ds/path/check.sh

# Build the sorting experiments at 2^depth elements.
build-sort depth="25":
    ./examples/ds/sort/build.sh {{quote(depth)}}

# Run the existing sorting correctness matrix (requires a GPU).
check-sort:
    ./examples/ds/sort/verify.sh
