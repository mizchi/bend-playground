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

# Verify portability, introductory samples, simulations and exact CPU algorithms.
test:
    python3 tests/smoke.py
    python3 tests/benchmark.py
    python3 tests/algorithms.py
    python3 tests/sat.py
    python3 tests/ffi.py

# Verify native FFI and its pure controls against an independent scalar oracle.
check-ffi:
    python3 tests/ffi.py

# Measure per-call native FFI overhead and optional batching.
bench-ffi *args="":
    python3 scripts/ffi_bench.py {{args}}

# Verify irregular CPU algorithms against C twins and independent oracles.
check-algorithms:
    python3 tests/algorithms.py

# Compare C and Bend on 1/all CPU threads; program names select a subset.
bench-algorithms *programs="nqueens rho astfold sat":
    python3 scripts/algorithm_bench.py {{programs}}

# Verify DPLL and SAT witnesses against exhaustive truth tables.
check-sat:
    python3 tests/sat.py

# Solve a DIMACS CNF (0..32 variables); append --split-depth/--threads/--backend.
sat +args:
    python3 scripts/sat.py "$@"

# Compare sequential DPLL with prefix partitions of one repeated CNF.
bench-sat +args:
    python3 scripts/sat_bench.py "$@"

# Check the physics and Monte Carlo samples against their C twins (no GPU).
check-sim:
    ./examples/sim/check.sh

# Time the physics and Monte Carlo samples against their C twins (quiet machine).
bench-sim *programs="galton anneal balls balls_flat fmc mcts c4":
    ./examples/sim/bench.sh {{programs}}

# Time sequential-loop forks versus a broad fork tree (WS overrides work sizes).
bench-fork:
    ./examples/sim/probes/fork_cost.sh

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
