import Base
# B: FWHT -- MERGE-heavy divide and conquer. Same fork shape as A, but
# the combine step costs O(subtree), not O(1). Verified against the
# involution law FWHT(FWHT(x)) == 2^d * x in fwht_check.bend.

type T is Data:
  L{v: U32}
  N{a: T, b: T}

type P is Data:
  Pr{p: T, m: T}

def bfly.join(ra: P, rb: P) -> P:
  match ra rb:
    case Pr{pa, ma} Pr{pb, mb}:
      Pr{N{pa, pb}, N{ma, mb}}

def fwht.comb(r: P) -> T:
  match r:
    case Pr{p, m}:
      N{p, m}

def bfly(x: T, y: T) -> P:
  match x y:
    case L{+u} L{+v}:
      Pr{L{U32.add(u, v)}, L{U32.sub(u, v)}}
    case N{xa, xb} N{ya, yb}:
      ra rb = bfly(xa, ya) bfly(xb, yb)
      bfly.join(ra, rb)
    case L{u} N{ya, yb}:
      Pr{L{0}, L{0}}
    case N{xa, xb} L{v}:
      Pr{L{0}, L{0}}

def fwht(t: T) -> T:
  match t:
    case L{v}:
      L{v}
    case N{a, b}:
      a2 b2 = fwht(a) fwht(b)
      fwht.comb(bfly(a2, b2))

def hash(+i: U32) -> U32:
  U32.xor(U32.mul(U32.inc(i), 2654435761), U32.shrn(i, 3n))

def mk(+d: Nat, +i: U32) -> T:
  match d:
    case 0n:
      L{hash(i)}
    case 1n+p:
      a b = mk(p, i) mk(p, U32.add(i, U32.shln(1, p)))
      N{a, b}

# position-weighted checksum: stride halves on the way down, so a leaf
# sees its own array index. Order-sensitive, so a permutation bug shows.
def mix(t: T, +i: U32, +s: U32) -> U32:
  match t:
    case L{v}:
      U32.mul(v, U32.inc(U32.mul(i, 2654435761)))
    case N{a, b}:
      +h = U32.shrn(s, 1n)
      x y = mix(a, i, h) mix(b, U32.add(i, s), h)
      U32.add(x, y)

def dep() -> Nat:
  20n

def run(+d: Nat) -> U32:
  mix(fwht(mk(d, 0)), 0, U32.shrn(U32.shln(1, d), 1n))

def main() -> IO(Unit):
  IO.print(U32.show(run!(dep())))
