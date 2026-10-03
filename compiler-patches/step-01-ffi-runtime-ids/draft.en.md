# Fix C emission when a native effect invokes a Bend callback

A native C effect should be able to call a callback received from Bend. This can currently fail at compile time because the compiler resolves the runtime helper's ID before registering it.

### What you did

Saved the two files below and compiled on upstream `main` @ `947db722`, still the latest HEAD when checked on 2026-10-03:

```sh
bend main.bend -o main.c
```

The C effect calls the Bend callback with `40`; the callback adds `2`.

### What happened

C emission fails before clang runs:

```text
Error: FID(Clo~apply) names no constructor or def
```

Expected: compilation succeeds and the native program prints `42`.

### The file

`main.bend`:

```python
import Base

def native.apply(step: U32 -> U32, value: U32) -> IO(Unit):
  import "./native.c"

def main() -> IO(Unit):
  native.apply(x => (x + 2 : U32), 40)
```

`native.c`:

```c
static Term native_apply_run(Env e, Term* f, IoWork* w) {
  (void)w;
  u64 at = task_node(e, FID(Clo~apply), TERM_HOLE, 0, 0);
  e.mem[at] = f[0];
  e.mem[at + 1] = f[1];
  Term result = corpus_eval(e.mem, term_tsk(FID(Clo~apply), at));
  if (err_seen(e.mem)) err_fail("foreign closure application failed");
  printf("%u\n", (u32)result);
  return term_pak(CID(Unit), 0);
}

static void __attribute__((constructor)) native_apply_use(void) {
  io_eff(CID(native.apply), native_apply_run, 0);
}
```

### Why

`Clo~apply` is the runtime code that applies a closure, and `IO~emit` wraps an IO result. They are implemented in the generated runtime, rather than declared in the Bend book.

`compile_book` reads foreign C sources through `effect_srcs` before creating these runtime segments. `c_ids` accepts a name only if it is in the book or the ID table. When no emitted Bend call has registered the helper yet, it rejects the valid runtime name.

### Change

Register `IO_EMIT` and `CLO_APPLY` with `seg_fid` immediately after `file_book` resets the ID table. Their names are then available when foreign sources are read. Runtime entries and numeric IDs are still generated at the same place.

Adds two C/JS regression tests: calling the Bend callback from C and extracting an `IO~emit` payload. Both print `42`.

### Verification

- The two-file reproducer fails on upstream main and prints `42` with this patch (C, 1/4 threads, GPU off).
- Both new tests and six existing controls match their expected output in the interpreter, JS and C.
- Nine local checks pass; four codegen controls produce byte-identical C before/after.
- `gates/repo.ts`: PASS 49/49. `comp.ts`: 63,933 → 63,961 ttok (cap 64,000).

Full cluster test/perf gates and CUDA were not run locally.

### bend --version

Output of `bend version`:

```text
bend 2.0.34
```

Base: `947db722640c86247849343657bf2f7ef01cb7f1`; PR head: `f5fadf405df89f339d33582e4f4b937acb603d10`.

### uname -sm

```text
Darwin arm64
```

Apple M5, macOS 26.6.2.

### clang --version (the first line)

```text
Apple clang version 21.0.0 (clang-2100.0.123.102)
```

Created with AI assistance (Codex).
