import Base
# M1-shared: the same BST map as m1.bend, but with ONE tree of N = 2^LGN
# keys built in sequence and then the N lookups split across 2^LGP forks
# that all read the SAME tree. The tree rides into both halves of the fork
# with `+`, which is a refcount increment, not a copy -- the asymmetry
# with Array (which cannot take `+` at all) is the point.
#
# The checksum is identical to m1.bend at LGK = 0 with the same LGN: the
# lookups are the same lookups with the same position weights, only the
# summation order differs, and U32 addition is associative.

type Tr is Data:
  Leaf{}
  Node{k: U32, v: U32, l: Tr, r: Tr}

def lgn() -> Nat:
  22n

# 2^LGP forked lookup chunks over the one shared tree
def lgp() -> Nat:
  5n

def nops() -> Nat:
  U32.to_nat(U32.shln(1, lgn()))

def cnt() -> Nat:
  U32.to_nat(U32.shrn(U32.shln(1, lgn()), lgp()))

def prng(+x: U32) -> U32:
  +b = U32.xor(x, U32.shln(x, 13n))
  +d = U32.xor(b, U32.shrn(b, 17n))
  U32.xor(d, U32.shln(d, 5n))

def key(+s: U32, +j: U32) -> U32:
  prng(U32.xor(U32.mul(U32.inc(j), 2654435761), U32.mul(s, 340573321)))

def ins(t: Tr, +k: U32, +v: U32, act: Bool) -> Tr:
  match t act:
    case u False{}:
      u
    case Leaf{} True{}:
      Node{k, v, Leaf{}, Leaf{}}
    case Node{+k2, v2, l, r} True{}:
      +c = U32.is_lt(k, k2)
      a = ins(l, k, v, c)
      b = ins(r, k, v, Bool.not(c))
      Node{k2, v2, a, b}

def find.join(k2: U32, v2: U32, hit: U32, pl: Tr & U32, pr: Tr & U32) -> Tr & U32:
  (l, a) = pl
  (r, b) = pr
  (Node{k2, v2, l, r}, U32.add(hit, U32.add(a, b)))

def find(t: Tr, +k: U32, act: Bool) -> Tr & U32:
  match t act:
    case u False{}:
      (u, 0)
    case Leaf{} True{}:
      (Leaf{}, 0)
    case Node{+k2, +v2, l, r} True{}:
      +c = U32.is_lt(k, k2)
      +hit = U32.mul(v2, Bool.to_u32(U32.is_eq(k, k2)))
      find.join(k2, v2, hit, find(l, k, c), find(r, k, Bool.not(c)))

def fill(n: Nat, +s: U32, +j: U32, t: Tr) -> Tr:
  match n:
    case 0n:
      t
    case 1n+p:
      fill(p, s, U32.inc(j), ins(t, key(s, j), U32.inc(j), True{}))

def mixp(+w: U32, acc: U32, p: Tr & U32) -> Tr & U32:
  (t, v) = p
  (t, U32.add(acc, U32.mul(v, w)))

def look(n: Nat, +s: U32, +j: U32, r: Tr & U32) -> Tr & U32:
  match n:
    case 0n:
      r
    case 1n+p:
      (t, acc) = r
      look(p, s, U32.inc(j),
           mixp(U32.inc(U32.mul(j, 2654435761)), acc, find(t, key(s, j), True{})))

def fin(r: Tr & U32) -> U32:
  (t, acc) = r
  acc

# one fork's chunk: `c` lookups starting at draw index j0, on its own
# refcounted handle of the shared tree
def chunk(+c: Nat, +s: U32, +j0: U32, t: Tr) -> U32:
  fin(look(c, s, j0, (t, 0)))

# the fork tree over the lookup range; the tree goes into both halves
def lookpar(+d: Nat, +s: U32, +j0: U32, +c: Nat, +t: Tr) -> U32:
  match d:
    case 0n:
      chunk(c, s, j0, t)
    case 1n+q:
      a b = lookpar(q, s, j0, c, t)
            lookpar(q, s, U32.add(j0, U32.mul(U32.from_nat(c), U32.shln(1, q))), c, t)
      U32.add(a, b)

def run(+d: Nat, +n: Nat, +c: Nat) -> U32:
  +s: U32 = 2654435761
  lookpar(d, s, 0, c, fill(n, s, 0, Leaf{}))

def main() -> IO(Unit):
  IO.print(U32.show(run!(lgp(), nops(), cnt())))
