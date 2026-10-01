import Base
# Memory probe (Bend 2.0.34, 7d24b8d0): a shared list passed twice to one
# def, walk(xs, xs, Nil{}), where the first copy is matched cell by cell into
# an accumulator and the second rides along unread. Every iteration leaves
# the old list's cells unfreed: --threads 1 grows to ~94 MB of RSS over 10^6
# iterations of a 4-cell list (~24 bytes a cell). Passing Nil{} as the second
# argument, or building the result with a non-tail cons (h <> walk(t, all,
# acc)), keeps RSS flat. balls.bend first hit this as a 6 GB RSS and a 17 s
# run dominated by page faults; see ../../../08-physics-and-monte-carlo.md.
# Measure with examples/sim/check.sh (or: ./twin_leak --threads 1 --gpu off
# under a tool that reports max RSS).

def walk(xs: +List<U32>, +all: +List<U32>, acc: +List<U32>) -> +List<U32>:
  match xs:
    case Nil{}:
      acc
    case Con{h, t}:
      walk(t, all, h <> acc)

def len(xs: +List<U32>, n: U32) -> U32:
  match xs:
    case Nil{}:
      n
    case Con{h, t}:
      len(t, U32.inc(n))

def go(k: Nat, +xs: +List<U32>) -> +List<U32>:
  match k:
    case 0n:
      xs
    case 1n+p:
      go(p, walk(xs, xs, Nil{}))

def main() -> IO(Unit):
  IO.print(U32.show(len(go(1000000n, [7, 7, 7, 7]), 0)))
