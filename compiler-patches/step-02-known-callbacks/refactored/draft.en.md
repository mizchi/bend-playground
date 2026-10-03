# The C compiler specializes calls with a known callback

Status: experimental, before submission. Reproduced locally against main `947db722`. Functional checks pass; `comp.ts` is 64,777 ttok, so simplification is still needed to meet the 64,000-token gate.

## What Bend should do

Avoid allocating a closure and applying it dynamically when a call passes a known callback. The compiler specializes supported calls while keeping the source API and function types.

```python
def apply(x: U32, callback: U32 -> U32) -> U32:
  callback(x)

def run(+bias: U32, x: U32) -> U32:
  a = apply(x, y => U32.add(y, bias))
  apply(a, y => U32.add(y, bias))
```

## Why

Element processing and continuation chains can pay for closure allocation and dynamic application on every small computation. This change aims to reduce that cost without rewriting the program as separate functions with explicit arguments. It applies to the C generation shared by the CPU and GPU runtimes.

## Change

Specialize saturated ordinary definitions passed one literal lambda with unboxed captures. Reuse function fusion and argument binding, preserving typed lambdas and constructor patterns. Keep the caller's captures alive and cache admission decisions across calls rebuilt by ANF, including fuel exhaustion.

Dynamic functions, multiple lambda arguments, foreign/bang calls, and callees with direct self-reference or parallel bindings retain the existing path. Non-tail expansion also excludes non-flat calls. Calls that exhaust the optimization budget retain the closure path. Generated JS and the interpreter provide result comparisons.

## Verification

Start with `tests/run/known_callback.bend` (expected stdout: `42`):

```sh
bun bend2/main.ts tests/run/known_callback.bend -o /tmp/known_callback.c
clang -O3 -std=c11 -pthread /tmp/known_callback.c -lm -o /tmp/known_callback
/tmp/known_callback --gpu off --threads 1
/tmp/known_callback --gpu off --threads 4
```

- Scalar capture reuse, tuple matching, linear arrays, fuel exhaustion, non-flat calls and generic fallback checked on C with 1/4 threads, JS and the interpreter.
- Twelve existing closure, array and mutual-recursion probes checked across those four execution modes. The full upstream cluster test/perf/safe gates have not run.
- A downstream GPUI particle update provides an application example: unchanged Bend sources produce zero update closure segments instead of fourteen. Generated C for the flat control is identical to the baseline.

GPUI bindings, rendering code and handwritten Metal kernels are outside this patch. GPUI supplies a use case for a general compiler optimization. CPU/Metal execution is checked on Apple M5/macOS; CUDA hardware has not been tested.

Reference implementation and CPU/Metal comparisons: [bend-playground](https://github.com/mizchi/bend-playground/tree/main/compiler-patches/step-02-known-callbacks/refactored). Compiler commits: [upstream main](https://github.com/bendlang/bend/commit/947db722640c86247849343657bf2f7ef01cb7f1), [mizchi fork](https://github.com/mizchi/bend/commit/b59588e2a9c63092b542739bb6908c3329d2e353).
