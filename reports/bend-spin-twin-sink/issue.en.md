# A variable lent to a spin inside a jump's argument is never sunk, so RSS grows every turn of the loop

### What you did

bend twin.bend -o twin && ./twin --threads 1 --gpu off

### What happened

```text
4000010
```

The answer is right, but every turn of `go` leaves the old list's cells allocated: max RSS grows with the turn count, 64 MB for 10^6 turns of a 4-cell list (measured with Python's `resource.getrusage`). Passing `X0{}` as the second argument keeps it at 10 MB.

In the C (`bend twin.bend -o twin.c`), `go` calls `spin_0(e, _o_0, _xs_0, _xs_0, ...)`. `spin_0` takes both arguments as borrowed: it reads the first through `term_peek` and passes the second along unread. `go` then jumps back with no `term_sink` of `_xs_0`. Binding the result with a `let` first keeps RSS flat, since the `let` runs `bind_dead`.

`emit_fuse` (bend2/comp.ts @ 7d24b8d0) runs `bind_dead` only for a tail call, and a jump runs no `bind_dead`, so a spin called inside a jump's argument leaves the variable it was lent unsunk. Passing the value twice is not required: one variable lent to a parameter that is borrowed because another call site lends it leaks the same way (`go2` in the PR's test). The call can also sit deeper in the argument, as in `go(p, Xs.rev(Xs.walk(xs, xs, X0{}), X0{}))`. I checked self-jumps only; a jump to another def goes through the same path, untested.

2.0.23 (75cb8f3e) gives the same 64 MB. No open PR head from #1000 on changes this branch of `emit_fuse`. A fix with a regression test is in #<PR>. Reproduction and measurement: <gist URL>

### The file

```python
import Base

type Xs is Data:
  X0{}
  X1{v: U32, rest: Xs}

# walks xs, never reads all
def Xs.walk(xs: Xs, +all: Xs, acc: Xs) -> Xs:
  match xs:
    case X0{}:
      acc
    case X1{v, rest}:
      Xs.walk(rest, all, X1{(v + 1 : U32), acc})

def Xs.sum(xs: Xs, acc: U32) -> U32:
  match xs:
    case X0{}:
      acc
    case X1{v, rest}:
      Xs.sum(rest, (acc + v : U32))

def go(k: Nat, +xs: Xs) -> Xs:
  match k:
    case 0n:
      xs
    case 1n+p:
      go(p, Xs.walk(xs, xs, X0{}))

def main() -> IO(Unit):
  IO.print(U32.show(Xs.sum(go(U32.to_nat(1000000), X1{1, X1{2, X1{3, X1{4, X0{}}}}}), 0)))
```

### bend --version

bend 2.0.34 (from `bend version`; on main `bend --version` is an unknown option)

### uname -sm

Linux x86_64

### clang --version (the first line)

Ubuntu clang version 18.1.3 (1ubuntu1)
