import Base
# M2: a priority queue as a skew heap (a mergeable heap: push and pop are
# both one merge). K = 2^LGK independent heaps; each takes N = 2^LGN
# pushes and then N pops. Keys are a bijection of the draw index, so the
# N keys of a heap are distinct and the pop order is unique.
#
# The pop loop carries an `ok` column that stays 1 only while every popped
# key is >= the one before it, so the program prints two lines,
# (checksum, ok), and ok = 1 is the proof that the pops came out ascending.
#
# Bend spelling notes, both forced by "a match may only scrutinize a
# parameter or a field":
#   * the smaller-root test cannot be a local Bool, and a helper that took
#     the Bool would be mutually recursive with merge. So `order` does the
#     comparison and hands the two heaps back already sorted, packed into
#     one HNode{0, smaller, other} node; merge then only unpacks fields.
#   * merge descends into the right spine of *either* argument, so no
#     argument column shrinks on both self-calls and the structural
#     recursion check refuses it. A fuel Nat rides in as the first column;
#     the bound is the heap size, which bounds any skew heap's right spine.

type H is Data:
  HNil{}
  HNode{k: U32, l: H, r: H}

def lgk() -> Nat:
  0n

def lgn() -> Nat:
  22n

# the right spine of a heap of 2^LGN keys is at most 2^LGN long
def fuel() -> Nat:
  Nat.add(1n, U32.to_nat(U32.shln(1, lgn())))

# xorshift: x ^= x<<13; x ^= x>>17; x ^= x<<5  (a bijection on u32)
def prng(+x: U32) -> U32:
  +b = U32.xor(x, U32.shln(x, 13n))
  +d = U32.xor(b, U32.shrn(b, 17n))
  U32.xor(d, U32.shln(d, 5n))

def key(+s: U32, +j: U32) -> U32:
  prng(U32.xor(U32.mul(U32.inc(j), 2654435761), U32.mul(s, 340573321)))

# the comparison, in its own def so the Bool is a parameter
def order.go(c: Bool, ka: U32, la: H, ra: H, kb: U32, lb: H, rb: H) -> H:
  match c:
    case True{}:
      HNode{0, HNode{ka, la, ra}, HNode{kb, lb, rb}}
    case False{}:
      HNode{0, HNode{kb, lb, rb}, HNode{ka, la, ra}}

# pack two heaps into HNode{0, smaller-rooted, other}
def order(x: H, y: H) -> H:
  match x y:
    case HNil{} HNil{}:
      HNode{0, HNil{}, HNil{}}
    case HNil{} HNode{k, l, r}:
      HNode{0, HNode{k, l, r}, HNil{}}
    case HNode{k, l, r} HNil{}:
      HNode{0, HNode{k, l, r}, HNil{}}
    case HNode{+ka, la, ra} HNode{+kb, lb, rb}:
      order.go(U32.is_le(ka, kb), ka, la, ra, kb, lb, rb)

# skew merge of an ordered pair: take the smaller root, merge its right
# child with the other heap, then swap the children
def merge(f: Nat, p: H) -> H:
  match f p:
    case 0n x:
      x
    case 1n+q HNil{}:
      HNil{}
    case 1n+q HNode{z, m, o}:
      match m:
        case HNil{}:
          o
        case HNode{km, lm, rm}:
          HNode{km, merge(q, order(rm, o)), lm}

def mrg(f: Nat, a: H, b: H) -> H:
  merge(f, order(a, b))

def push(+s: U32, +j: U32, h: H) -> H:
  mrg(fuel(), h, HNode{key(s, j), HNil{}, HNil{}})

def pushn(n: Nat, +s: U32, +j: U32, h: H) -> H:
  match n:
    case 0n:
      h
    case 1n+p:
      pushn(p, s, U32.inc(j), push(s, j, h))

# one pop: mix the key in position-weighted, and keep `ok` only while the
# keys come out ascending
def popstep(+i: U32, prev: U32, acc: U32, ok: U32, h: H) -> H & U32 & U32 & U32:
  match h:
    case HNil{}:
      (HNil{}, prev, acc, ok)
    case HNode{+k, l, r}:
      (mrg(fuel(), l, r), k,
       U32.add(acc, U32.mul(k, U32.inc(U32.mul(i, 2654435761)))),
       U32.mul(ok, Bool.to_u32(U32.is_le(prev, k))))

def popn(n: Nat, +i: U32, r: H & U32 & U32 & U32) -> H & U32 & U32 & U32:
  match n:
    case 0n:
      r
    case 1n+p:
      (h, prev, acc, ok) = r
      popn(p, U32.inc(i), popstep(i, prev, acc, ok, h))

def one.fin(r: H & U32 & U32 & U32) -> U32 & U32:
  (h, prev, acc, ok) = r
  (acc, ok)

def one(+g: U32, +n: Nat) -> U32 & U32:
  +s = U32.mul(U32.inc(g), 2654435761)
  one.fin(popn(n, 0, (pushn(n, s, 0, HNil{}), 0, 0, 1)))

def comb(pa: U32 & U32, pb: U32 & U32) -> U32 & U32:
  (a1, o1) = pa
  (a2, o2) = pb
  (U32.add(a1, a2), U32.mul(o1, o2))

def batch(+p: Nat, +g: U32, +n: Nat) -> U32 & U32:
  match p:
    case 0n:
      one(g, n)
    case 1n+q:
      a b = batch(q, g, n) batch(q, U32.add(g, U32.shln(1, q)), n)
      comb(a, b)

def main.go(r: U32 & U32) -> IO(Unit):
  (acc, ok) = r
  IO.bind(Unit, Unit, IO.print(U32.show(acc)), u => IO.print(U32.show(ok)))

def main() -> IO(Unit):
  main.go(batch!(lgk(), 0, U32.to_nat(U32.shln(1, lgn()))))
