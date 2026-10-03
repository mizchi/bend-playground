# The C compiler specializes calls with a known callback

Based on main `5a0b523f` (Bend 2.0.35); reproduced locally on Apple M5/macOS.

## What Bend should do

Specialize calls that pass a known callback, avoiding closure allocation and dynamic application while keeping ordinary function types:

```python
def apply(x: U32, callback: U32 -> U32) -> U32:
  callback(x)

def run(+bias: U32, x: U32) -> U32:
  a = apply(x, y => U32.add(y, bias))
  apply(a, y => U32.add(y, bias))
```

## Why

I started this while building Bend bindings for [GPUI](https://gpui.rs/), connecting Bend-computed particle state to rendering without CPU readback. Small callbacks used to thread linear arrays through element reads became a bottleneck. The generated update had fourteen closure segments; rewriting those callbacks as explicit arguments made it much faster.

This lets the compiler remove that cost for supported calls while keeping the callback API. CPU and GPU share the C emitter. With unchanged Bend particle sources, update closure segments fall from fourteen to zero; two UI/IO closures remain.

One million particles on Apple M5, measured on main `947db722` vs fork `b59588e2`. Rebased particle C outputs are byte-identical:

| Update | Baseline | Optimized | Speedup |
| --- | ---: | ---: | ---: |
| CPU, 1 thread | 160.881 ms | 69.830 ms | 2.30× |
| CPU, 10 threads | 24.472 ms | 12.108 ms | 2.02× |
| Metal, including completion wait | 8.653 ms | 1.625 ms | 5.32× |

GPUI is the application example. This PR changes the general compiler; application code is available as a [reusable Bend/GPUI library](https://github.com/mizchi/bend-playground/blob/6c21544c51228c88e5ff1559236231a0b88727f7/packages/bend-gpui/README.en.md), a [minimal Bend application](https://github.com/mizchi/bend-playground/blob/6c21544c51228c88e5ff1559236231a0b88727f7/examples/gpui/minimal.bend), and a [particle rendering example](https://github.com/mizchi/bend-playground/tree/6c21544c51228c88e5ff1559236231a0b88727f7/examples/particles). The [benchmark reference implementation](https://github.com/mizchi/bend-playground/tree/09fc6e6/compiler-patches/step-02-known-callbacks/refactored) remains pinned to the measured versions.

## Change

Two commits: first shorten type/import notation and comments without changing generated output, then add specialization (+69/-15 compiler lines) and two regression fixtures. `comp.ts` is 63,956 ttok; the 64,000 cap stays unchanged.

Specialize saturated defs with one literal lambda and unboxed captures. Reuse fusion and argument binding, preserve typed lambdas/constructor patterns and caller capture lifetimes, and cache admission across ANF rebuilding and fuel exhaustion.

Dynamic callbacks, boxed captures, multiple lambdas and foreign/bang calls retain the existing path. Callees with direct self-reference or parallel bindings are excluded. Non-tail expansion also excludes non-flat calls and callbacks with parallel bindings. Budget exhaustion falls back to closures.

Separate from #1286 (foreign-callback C emission). The notation/comment commit shares the size-reduction goal of open #1281.

## Verification

Local checks on main `5a0b523f` plus this patch:

- `gates/repo.ts`: 49/49.
- Thirteen callback contracts pass, including capture reuse, linear arrays, dependent types, non-flat calls, fallback, repeated compilation and fuel exhaustion.
- Sixteen upstream programs (including the two new fixtures and main's two new ownership regressions) agree across interpreter, JS and C with 1/4 threads: 64 executions.
- The compaction alone preserves generated C/JS byte-for-byte for fourteen programs. The eight particle C outputs match the published measured versions, including both flat controls.
- TypeScript reports the same two existing `bend.ts` errors on baseline and branch. Full cluster test/perf/safe gates and CUDA hardware have not been run.

Start with `tests/run/known_callback.bend` (stdout `42`); commands below.

<details>
<summary>Reproduction and measurement details</summary>

Small regression (stdout `42`):

```sh
bun bend2/main.ts tests/run/known_callback.bend -o /tmp/known_callback.c
clang -O3 -std=c11 -pthread /tmp/known_callback.c -lm -o /tmp/known_callback
/tmp/known_callback --gpu off --threads 1
/tmp/known_callback --gpu off --threads 4
```

The table was measured on [main 947db722](https://github.com/bendlang/bend/commit/947db722640c86247849343657bf2f7ef01cb7f1) versus [fork b59588e2](https://github.com/mizchi/bend/commit/b59588e2a9c63092b542739bb6908c3329d2e353). After rebasing onto main 5a0b523f and compacting, all eight measured particle C outputs remain byte-identical in their respective lanes; timings were not rerun.

Apple M5 (10 CPU/10 GPU cores), macOS 26.6.2, Bun 1.3.5, clang 21.0.0. One million particles, 64 noise rounds, CPU grain 1,024, GPU grain 16,384, 960×540 offscreen output. Five warmup frames and fifteen measured frames per run; median of three run medians, configurations shuffled and run serially. Builds/startup/verification are excluded. Measured frames have zero CPU readback. This measures update time, not display/presentation latency.

The machine was shared. The byte-identical flat GPU control ranged 1.543–1.841 ms on main and 1.514–1.725 ms on the fork, so small timing differences should not be attributed to the compiler. Eight application binaries were checked with float32/image oracles: 36 configurations and 144 verified frames.

[Raw timings](https://github.com/mizchi/bend-playground/blob/09fc6e6/compiler-patches/step-02-known-callbacks/refactored/results-macos-m5.json) and [application validation](https://github.com/mizchi/bend-playground/blob/09fc6e6/compiler-patches/step-02-known-callbacks/refactored/validation-macos-m5.json), with pinned source/compiler revisions and reproduction commands in the reference README.

</details>

Implemented and checked with OpenAI Codex assistance.
