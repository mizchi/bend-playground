# Bend: a lent twin is never sunk after a spin call in a self-jump argument

`go(p, Xs.walk(xs, xs, X0{}))` passes one list twice. `Xs.walk` is a flat
loop (emitted as a `spin_N` C function) that consumes its first parameter and
never reads its second. The compiled program prints the right answer, but
every turn of `go` leaves the old list's cells allocated, so RSS grows
linearly with the turn count.

```sh
bend twin.bend -o twin
python3 -c 'import resource, subprocess, sys
subprocess.run(sys.argv[1:])
print(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss // 1024, "MB")' ./twin --threads 1 --gpu off
# 4000010
# 64 MB          (10^6 turns of a 4-cell list; Linux reports ru_maxrss in KB)
```

Expected: about 10 MB, flat in the turn count. Any of these keeps it flat:

- pass `X0{}` instead of the second `xs`;
- build the result with a non-tail cons, so `Xs.walk` is not a spin;
- the patch below (comp.ts @ 7d24b8d0).

In the generated C (`bend twin.bend -o twin.c`), `go` does
`_xs_0 = term_keep(e, _xs_0, 1)`, calls `spin_0(e, _o_0, _xs_0, _xs_0, ...)`,
and jumps back without a `term_sink` of `_xs_0`. When `Xs.walk` is not fused,
the continuation after the call sinks it.

```diff
--- a/bend2/comp.ts
+++ b/bend2/comp.ts
@@ function emit_fuse
   out.ws.forEach((v, j) => file_push(fl, `${v} = ${o}[${j}];`));
-  if (tail) {
-    bind_dead(fl, []);
-  }
+  bind_dead(fl, tail ? [] : fl.rest);
   emit_put(fl, dst, out);
```

Measured on Linux x86_64 (Intel Xeon, 4 threads), Ubuntu clang 18.1.3,
bend 2.0.34 (7d24b8d0); the same 64 MB on bend 2.0.23 (75cb8f3e).
