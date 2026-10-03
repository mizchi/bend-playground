# Known-callback specialization submitted on Bend 2.0.35

[Upstream PR #1288](https://github.com/bendlang/bend/pull/1288) follows the Feature template and describes the GPUI binding work that exposed the callback bottleneck.

The application code is available as a [reusable Bend/GPUI library and English usage guide](https://github.com/mizchi/bend-playground/blob/6c21544c51228c88e5ff1559236231a0b88727f7/packages/bend-gpui/README.en.md), a [minimal Bend application](https://github.com/mizchi/bend-playground/blob/6c21544c51228c88e5ff1559236231a0b88727f7/examples/gpui/minimal.bend), and a [particle rendering example](https://github.com/mizchi/bend-playground/tree/6c21544c51228c88e5ff1559236231a0b88727f7/examples/particles).

This branch applies the compiler optimization to upstream main [5a0b523f](https://github.com/bendlang/bend/commit/5a0b523f7759335164f1dead0e0815234a5fd9dc), preserving its latest ownership fix. It has two commits:

1. [1e250850](https://github.com/mizchi/bend/commit/1e250850): simplify type/import notation and comments, 63,980 → 63,129 ttok. Fourteen existing programs emit byte-identical C/JS before and after this commit.
2. [83d497e5](https://github.com/mizchi/bend/commit/83d497e52610c42dcc5bddf5ad21fb0285e12e88): known-callback specialization (+69/-15 compiler lines) and two regression fixtures, 63,956 ttok. `gates/repo.ts` passes 49/49.

The initial [size-reduction proposal](../size-reduction/README.md) and [measured comparison](../README.en.md) remain pinned to their original revisions. No timing records were replaced. The latest baseline and this branch produce the same eight instrumented particle C files as the respective measured revisions. The published timing table therefore describes those emitted programs; no new timing run was performed.

[Validation](validation-macos-m5.json) records the revisions, source hash, token counts, 28 compaction C/JS comparisons, eight particle comparisons, and 64 executions of sixteen programs across interpreter, JS and C with 1/4 threads. These include the two new callback fixtures and main's `spin_lent_sink` and `fork_spin_hold` witnesses. Thirteen downstream callback contracts also pass. TypeScript reports the same two existing `bend.ts` errors. Full cluster test/perf/safe gates and CUDA hardware remain unrun.

## Reproduce the branch checks

```sh
git clone https://github.com/mizchi/bend.git build/bend-callback-pr
git -C build/bend-callback-pr checkout 83d497e52610c42dcc5bddf5ad21fb0285e12e88
git clone https://github.com/bendlang/bend.git build/bend-callback-base
git -C build/bend-callback-base checkout 5a0b523f7759335164f1dead0e0815234a5fd9dc
BEND_REPO="$PWD/build/bend-callback-pr" BEND_BASE_REPO="$PWD/build/bend-callback-base" BEND_PARTICLE_CID=Tick python3 tests/bend_step02_refactor.py
BEND_REPO="$PWD/build/bend-callback-pr" just check-bend-step02-upstream
(cd build/bend-callback-pr && bun gates/repo.ts)
```

Run from the playground root. Bun, Python, clang and `ttok` on PATH are required. The first test command covers thirteen callback contracts; the `just` task runs the twelve original upstream programs in four lanes. The two added callback files and two recent ownership witnesses can also be run directly with `./scripts/bend.sh`, emitted as JS, and emitted/compiled as C with `--gpu off --threads 1` and `--threads 4`; their expected outputs are the trailing `#|` lines.
