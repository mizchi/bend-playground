# A spin called in a self-jump's argument sinks the twin it was lent, so the loop no longer keeps the old list's cells (#<issue>)

In `go(p, Xs.walk(xs, xs, X0{}))`, `go` keeps `xs` once and lends it to `Xs.walk`'s second parameter, which a spin never reads. The lent copy dies at the call, but `emit_fuse` ran `bind_dead` only for a tail call, and the self-jump runs none, so nothing sank it: the answer was right and every turn left the old list's cells (#<issue>).

`emit_fuse` now runs `bind_dead(fl, fl.rest)` after a non-tail call too, sinking the bindings the rest no longer uses; a tail call is unchanged. In the C, the spin call is followed by one `term_sink(e, _xs_0);`.

Test: `tests/reg/spin_twin_sink.bend` (10^6 turns of a 4-cell list, the answer pinned). test.ts does not check RSS, so the header states it, as `closure_value_owns.bend` does: 64 MB before, 10 MB after, at `--threads 1` and `--threads 4`.

<details>
<summary>Checked locally</summary>

- gates/repo.ts: PASS: 49 / 49
- every tests/ file with `#|` lines, built and run on the C lane (`-o t`, `./t --gpu off`) and the JS lane (`-o t.js`, `bun t.js`), before and after: the same results on both lanes except the new test (C pass 670 -> 671, JS 692 -> 693); the rest are tests whose expected output is a check error, and io/ tests that fail on this machine before and after
- bench/runtime: the emitted C is byte-identical for 15 of 16; in hashmap an existing `term_sink` moves up to right after its spin call
- not run: gates/test.ts and gates/perf.ts (they need the cluster); no GPU here
- Linux x86_64 (Intel Xeon, 4 threads), Ubuntu clang 18.1.3, bend 2.0.34 (7d24b8d0)

</details>
