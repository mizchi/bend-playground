# Known-callback fusion: reference implementation

[Upstream PR #1288](https://github.com/bendlang/bend/pull/1288) is based on main `5a0b523f`. It describes the GPUI binding work that exposed the callback cost and the resulting general compiler optimization.

This experiment adds a general optimization to Bend's C compiler: fuse saturated calls that pass one literal lambda with unboxed captures, avoiding closure allocation and dynamic application. The GPUI particle update is a downstream example. CPU and GPU share the C emitter; the compiler patch contains no GPUI bindings or Metal kernels.

## Pinned comparison

| Compiler | Commit |
| --- | --- |
| Measured upstream main, checked on 2026-10-03 | [`947db722`](https://github.com/bendlang/bend/commit/947db722640c86247849343657bf2f7ef01cb7f1) |
| mizchi/bend, `perf/known-callback-fusion` | [`b59588e2`](https://github.com/mizchi/bend/commit/b59588e2a9c63092b542739bb6908c3329d2e353) |

[reference.json](reference.json) contains repository URLs, full revisions and compiler SHA-256 hashes. The harness fetches these commits and refuses a different HEAD, dirty checkout or mismatched compiler. Both published commits were also fetched into fresh checkouts for verification.

[compiler.patch](compiler.patch) changes only `comp.ts`. [pr.patch](pr.patch) also includes two Bend regression fixtures. The compiler has 69 added and 15 removed lines, versus 166 added lines in the earlier standalone transformation pass. It reuses function expansion, argument binding and lambda application, with separate callee capture bindings and stable admission caching across ANF rebuilding.

The measured `b59588e2` compiler is 64,777 ttok and passes 48/49 repository checks. The [submission branch](submission/README.md) is based on main `5a0b523f` (Bend 2.0.35) and separates notation/comment compaction from specialization into two commits. It is **63,956 ttok, repo gate 49/49**, with the permanent cap unchanged. All eight particle C outputs match the respective measured versions byte-for-byte; timings were not rerun. Full upstream cluster test/perf/safe gates and CUDA hardware have not been tested.

## Reproduce

Tested on Apple M5, macOS 26.6.2, Bun 1.3.5, clang 21.0.0 and Rust 1.98.0. Use Git, just, Python 3 and Bun; the application benchmark also needs Rust/Cargo and Xcode with its Metal SDK.

```sh
git clone https://github.com/mizchi/bend-playground.git
cd bend-playground
git checkout 0d2b737a2b0e020428e223e572d85e6d2c4d748e
just setup
just check-bend-step02-refactored
just bench-bend-step02-refactored --phase build
just bench-bend-step02-refactored --phase verify
just bench-bend-step02-refactored --phase bench
```

This pins the [measured playground source](https://github.com/mizchi/bend-playground/commit/0d2b737a2b0e020428e223e572d85e6d2c4d748e). Compiler checkouts and generated files live under `build/`; the recorded submodule and `bend.ts` are preserved. Only the copied native adapter changes `CID(api.Tick)` to `CID(Tick)` for the newer compiler's namespace resolution. Both lanes use identical Bend/C inputs, with hashes recorded in the results.

## Correctness and performance

The callback contracts cover capture reuse, tuple patterns, linear arrays, generic fallback, dependent types, recompilation, non-flat calls and fuel exhaustion. Thirteen compiler tests, four checkout contracts and forty playground tests pass. Twelve existing upstream programs agree across the interpreter, generated JS and C with 1/4 threads.

Eight application binaries were checked against independent float32 and image oracles, including edge counts and one million particles: 36 configurations, 144 verified frames. Update closure segments fall from fourteen to zero; two UI/IO closure segments remain. The flat control's generated C is byte-identical across compilers at both grains. TypeScript reports the same two pre-existing `bend.ts` errors on both commits.

Timing uses one million particles, 64 noise rounds, CPU grain 1,024 and GPU grain 16,384, with 960×540 offscreen output. Each process warms up five frames and measures fifteen; the table compares medians from three runs. Configurations run serially in shuffled order. Startup, builds and correctness checks are excluded.

| Callback update | Upstream main | mizchi fork | Speedup |
| --- | ---: | ---: | ---: |
| CPU update, 1 thread | 160.881 ms | 69.830 ms | 2.30× |
| CPU update, 10 threads | 24.472 ms | 12.108 ms | 2.02× |
| Metal update, including completion wait | 8.653 ms | 1.625 ms | 5.32× |
| Metal update, GPU timestamp | 7.550 ms | 1.372 ms | 5.50× |

GPU frame preparation, including update, drawing and NV12 conversion, takes 16.227 → 9.849 ms. This does not measure display/presentation latency. GPU timestamps overlap CPU completion waits and must not be added to them.

All 720 recorded frames have zero CPU readback bytes and one persistent state allocation; real GPU dispatches are checked. Verification readback is outside the timed runs. The machine was shared: CPU idle before timing was 74.60% and 60.51% in two observations. The identical flat GPU control ranged 1.543–1.841 ms on main and 1.514–1.725 ms on the fork, so small timing differences should not be attributed to the compiler.

See [raw timing data](results-macos-m5.json), [validation logs and source hashes](validation-macos-m5.json), [the specification](SPEC.md) and [the proposed PR description](draft.en.md).
