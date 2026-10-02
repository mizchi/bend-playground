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
    python3 tests/grid.py

# Lay out a supported CSS Grid JSON page with the Bend or C native engine.
grid +args:
    python3 scripts/grid.py "$@"

# Generate a standalone Bend/browser layout comparison viewer.
grid-demo:
    python3 scripts/grid_demo.py

# Install the pinned browser oracle dependencies and Chromium/Firefox.
setup-grid-browser:
    pnpm --dir examples/grid/browser install --frozen-lockfile
    pnpm --dir examples/grid/browser exec playwright install chromium firefox

# Verify Grid contracts and native correctness, then compare to real browsers.
check-grid:
    python3 tests/grid.py
    python3 scripts/check_grid.py
    pnpm --dir examples/grid/browser test

# Measure page relayout latency and independent page throughput (serial timings).
bench-grid *args="":
    python3 scripts/grid_bench.py {{args}}

# Verify full CPU/Metal rectangle handoffs and reject GPU fallback.
check-grid-gpu:
    python3 tests/grid_gpu.py

# Verify direct shared-buffer coordinates and CPU read/copy checksums.
check-grid-gpu-flat:
    python3 tests/grid_gpu_flat.py

# Measure independent page batches and full rectangle materialization on Metal.
bench-grid-gpu *args="":
    python3 scripts/grid_gpu.py {{args}}

# Compare output Trees with direct packed buffers; measure read and memcpy.
bench-grid-gpu-flat *args="":
    python3 scripts/grid_gpu_flat.py {{args}}

# Verify fixed-work CPU/Metal task-boundary checksums and real dispatch.
check-device:
    python3 tests/device_bench.py

# Measure CPU/GPU handoffs for scalar and grouped independent jobs.
bench-device *args="":
    python3 scripts/device_bench.py {{args}}

# Draw Bend Grid or procedural pixels in a native GPUI/Metal window (macOS).
gpui *args="grid":
    python3 scripts/gpui.py {{args}}

# Verify C/Rust ABI and CPU/GPU output against independent NV12 pixel oracles.
check-gpui:
    CARGO_TARGET_DIR="$PWD/build/gpui/target" MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-15.0}" cargo test --locked --manifest-path examples/gpui/Cargo.toml
    python3 tests/gpui.py

# Open actual GPUI windows, verify all output pixels, and close automatically.
check-gpui-window:
    python3 scripts/gpui.py grid --gpu off --frames 3 --verify
    python3 scripts/gpui.py shader --gpu on --frames 3 --verify

# Measure fixed-size frame preparation; excludes display/presentation latency.
bench-gpui *args="":
    python3 scripts/gpui_bench.py {{args}}

# Simulate persistent particles and draw their shared buffer through GPUI.
particles *args="":
    python3 scripts/particles.py {{args}}

# Compare every state field to independent C/Python float32 oracles.
check-particles:
    python3 tests/particles.py

# Exercise real GPUI windows for each particle backend, then close them.
check-particles-window:
    python3 scripts/particles.py --backend bend-cpu --count 10000 --frames 3 --verify
    python3 scripts/particles.py --backend bend-gpu --count 100000 --noise-rounds 64 --frames 3 --verify
    python3 scripts/particles.py --backend metal --count 100000 --noise-rounds 64 --frames 3 --verify

# Serial Bend CPU/Bend GPU/native Metal update and rendering measurements.
bench-particles *args="":
    python3 scripts/particles_bench.py {{args}}

# Compare callback and flat Bend code with the same compiler and grain.
bench-particles-code *args="":
    python3 scripts/particles_bench.py --variant callback --variant flat {{args}}

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
