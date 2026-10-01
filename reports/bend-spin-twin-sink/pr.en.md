# A spin called in a jump's argument sinks the variable it was lent, so a loop no longer keeps the old list's cells (#<issue>)

When a spin is called inside a jump's argument, as in `go(p, Xs.walk(xs, xs, X0{}))`, and lent a variable that dies at the call, nothing sank that variable: `emit_fuse` ran `bind_dead` only for a tail call, and the jump runs none. The answer was right, and every turn left the old list's cells (#<issue>).

`emit_fuse` now runs `bind_dead(fl, fl.rest)` after a non-tail call too, sinking the bindings the rest no longer uses; a tail call is unchanged. Outside jump arguments this sinks a dead binding right after its spin call instead of later, so a continuation's frame can lose a word (in the hashmap bench an existing `term_sink` moves up to right after its spin call).

Test: `tests/reg/spin_lent_sink.bend`, with one value passed twice (`go`) and one variable lent once to a parameter another call site made borrowed (`go2`). test.ts does not check RSS, so the header states it, as `closure_value_owns.bend` does: 79 MB before, 10 MB after, at `--threads 1` and `--threads 4`. The C differs only by a `term_sink` after each of the two spin calls.

Not settled: `emit_fork`'s sequential path evaluates a call's arguments with `rest: [chain[i]]`. If a spin inside those arguments were lent a binding that only `hold` keeps alive, the sequential and parallel paths could disagree on what is live. I could not build such a program, and the fork programs I tried emit the same C before and after.

<details>
<summary>Checked locally</summary>

- gates/repo.ts: PASS: 49 / 49
- every tests/ file with `#|` lines, built and run on the C lane (`-o t`, `./t --gpu off`) and the JS lane (`-o t.js`, `bun t.js`), before and after: the same results on both lanes except the new test (C pass 670 -> 671, JS 692 -> 693); the rest are tests whose expected output is a check error, and io/ tests that fail on this machine before and after
- bench/runtime: the emitted C is byte-identical for 15 of 16; hashmap has the one moved line above
- not run: gates/test.ts and gates/perf.ts (they need the cluster); no GPU here
- Linux x86_64 (Intel Xeon, 4 threads), Ubuntu clang 18.1.3, bend 2.0.34 (7d24b8d0)

</details>
