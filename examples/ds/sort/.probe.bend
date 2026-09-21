import Base
# S1: merge sort over 2^D keys, tree-shaped recursion, list-shaped merges.
#
# The keys are the xorshift hash of the leaf index, exactly as
# bench/runtime/tree-bitonic/main.bend spells it, so this file, bsort.bend,
# nosort.bend and sort.c all sort the same multiset.
#
# msort forks the two halves (a b = msort(..) msort(..)) and merges them; the
# merge is the affine one-pass fold of two runs into one, so every cons cell of
# both inputs is consumed exactly once.  The ROOT merge does not build a list:
# it folds straight into the Ck accumulator, so the O(n) verification pass
# rides inside the O(n) merge that has to run anyway.
#
# A merge has to branch on a comparison, and Bend cannot match a computed value
# ("a match cannot scrutinize a computed value") nor call a helper that calls
# back ("expected: a defined name"), so the comparison rides in as a Bool
# PARAMETER: each self-call computes the next decision for its successor.
#
# Output: "ok cnt sum isum msum", all U32.
#   ok    1 iff the emitted sequence is ascending      (order property)
#   cnt   number of elements emitted
#   sum   sum of the values                            (order-INdependent)
#   isum  sum of i*v                                   (order-sensitive)
#   msum  sum of prng(v)                               (order-INdependent hash)

type Lst is Data:
  Lnil{}
  Lcons{h: U32, t: Lst}

type Ck is Data:
  Ck{i: U32, ok: U32, sum: U32, isum: U32, msum: U32, prev: U32}

# xorshift: x ^= x<<13; x ^= x>>17; x ^= x<<5
def prng(+x: U32) -> U32:
  +b = U32.xor(x, U32.shln(x, 13n))
  +d = U32.xor(b, U32.shrn(b, 17n))
  U32.xor(d, U32.shln(d, 5n))

def key(i: U32) -> U32:
  prng(U32.mul(U32.inc(i), 2654435761))

# a merge emits at most n elements; 2^26 covers the 2^25 run
def fuel() -> Nat:
  67108864n

def ck0() -> Ck:
  Ck{0, 1, 0, 0, 0, 0}

# one emitted element: bump the index, AND the ascending test into ok, add the
# value to the order-independent sum, to the position-weighted isum, and to
# msum -- a commutative hash of the multiset, which unlike sum notices a pair
# of values swapped for two others with the same total
def push(c: Ck, +v: U32) -> Ck:
  match c:
    case Ck{+i, ok, sum, isum, msum, prev}:
      Ck{U32.inc(i), U32.and(ok, Bool.to_u32(U32.is_le(prev, v))),
        U32.add(sum, v), U32.add(isum, U32.mul(i, v)),
        U32.add(msum, prng(v)), v}

# fold the leftover tail of whichever run outlived the other
def drain(f: Nat, xs: Lst, acc: Ck) -> Ck:
  match f:
    case 0n:
      acc
    case 1n+p:
      match xs:
        case Lnil{}:
          acc
        case Lcons{v, t}:
          drain(p, t, push(acc, v))

# the root merge: folds instead of consing.  t is is_le(ah, bh), decided by
# the caller.
def mchk(f: Nat, t: Bool, +ah: U32, +bh: U32, at: Lst, bt: Lst,
         acc: Ck) -> Ck:
  match f:
    case 0n:
      acc
    case 1n+p:
      match t:
        case True{}:
          match at:
            case Lnil{}:
              drain(p, Lcons{bh, bt}, push(acc, ah))
            case Lcons{+a2, at2}:
              mchk(p, U32.is_le(a2, bh), a2, bh, at2, bt, push(acc, ah))
        case False{}:
          match bt:
            case Lnil{}:
              drain(p, Lcons{ah, at}, push(acc, bh))
            case Lcons{+b2, bt2}:
              mchk(p, U32.is_le(ah, b2), ah, b2, at, bt2, push(acc, bh))

# the inner merges: two sorted runs into one, one pass, both consumed
def merge(f: Nat, t: Bool, +ah: U32, +bh: U32, at: Lst, bt: Lst) -> Lst:
  match f:
    case 0n:
      Lnil{}
    case 1n+p:
      match t:
        case True{}:
          match at:
            case Lnil{}:
              Lcons{ah, Lcons{bh, bt}}
            case Lcons{+a2, at2}:
              Lcons{ah, merge(p, U32.is_le(a2, bh), a2, bh, at2, bt)}
        case False{}:
          match bt:
            case Lnil{}:
              Lcons{bh, Lcons{ah, at}}
            case Lcons{+b2, bt2}:
              Lcons{bh, merge(p, U32.is_le(ah, b2), ah, b2, at, bt2)}

def mrg(a: Lst, b: Lst) -> Lst:
  match a b:
    case Lnil{} Lnil{}:
      Lnil{}
    case Lnil{} Lcons{bh, bt}:
      Lcons{bh, bt}
    case Lcons{ah, at} Lnil{}:
      Lcons{ah, at}
    case Lcons{+ah, at} Lcons{+bh, bt}:
      merge(fuel(), U32.is_le(ah, bh), ah, bh, at, bt)

def mrg_chk(a: Lst, b: Lst) -> Ck:
  match a b:
    case Lnil{} Lnil{}:
      ck0()
    case Lnil{} Lcons{bh, bt}:
      drain(fuel(), Lcons{bh, bt}, ck0())
    case Lcons{ah, at} Lnil{}:
      drain(fuel(), Lcons{ah, at}, ck0())
    case Lcons{+ah, at} Lcons{+bh, bt}:
      mchk(fuel(), U32.is_le(ah, bh), ah, bh, at, bt, ck0())

# 2^d keys under path x, sorted ascending
def msort(+d: Nat, +x: U32) -> Lst:
  match d:
    case 0n:
      Lcons{key(x), Lnil{}}
    case 1n+p:
      a b = msort(p, U32.shl(x)) msort(p, U32.inc(U32.shl(x)))
      mrg(a, b)

def size() -> Nat:
  25n

def run(+d: Nat) -> Ck:
  match d:
    case 0n:
      drain(fuel(), msort(0n, 0), ck0())
    case 1n+p:
      a b = msort(p, 0) msort(p, 1)
      mrg_chk(a, b)

def show(c: Ck) -> String:
  match c:
    case Ck{i, ok, sum, isum, msum, prev}:
      String.append(String.append(U32.show(ok), " "),
        String.append(String.append(U32.show(i), " "),
          String.append(String.append(U32.show(sum), " "),
            String.append(String.append(U32.show(isum), " "),
              U32.show(msum)))))

def main() -> IO(Unit):
  c = run!(size())
  IO.print(show(c))
