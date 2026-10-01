# Bend: a variable lent to a spin inside a jump argument is never sunk

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

In the generated C (`bend twin.bend -o twin.c`), `go` calls
`spin_0(e, _o_0, _xs_0, _xs_0, ...)`, `spin_0` reads both arguments as
borrowed (`term_peek`), and `go` jumps back with no `term_sink` of `_xs_0`.
Binding the result with a `let` first keeps RSS flat, because the `let`
runs `bind_dead`. Passing the value twice is not required: a variable lent
once to a parameter that is borrowed (because another call site lends it)
leaks the same way, as `go2` in the PR's test shows.

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
