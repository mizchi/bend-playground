import Base
# M1: an associative array as a binary search tree, affine style.
#
# K = 2^LGK independent maps; each takes N = 2^LGN inserts and then N
# lookups. Key j of map g is a bijection of j (odd multiply, xor with the
# map's seed, xorshift), so the N keys of a map are distinct and the tree
# is a random BST. The lookup probes the same N keys in the same order,
# so every probe hits; the checksum is a position-weighted fold of the
# values found, summed over the maps.
#
# LGK is the only parallelism knob: LGK = 0 is one map updated in
# sequence (an insert列 that cannot be split), and raising LGK trades
# depth for independent maps at a fixed total op count.
#
# Bend spelling notes. A match may only scrutinize a parameter or a
# field, so "which child do I descend into" cannot be a local Bool, and
# a helper def that took the Bool would be mutually recursive with ins.
# The decision rides in as an `act` column instead: both children are
# always called, one with act = True (descend) and one with act = False
# (hand the subtree straight back untouched). find threads the tree back
# out as a pair, so no node is ever duplicated and the tree stays
# uniquely owned.

type Tr is Data:
  Leaf{}
  Node{k: U32, v: U32, l: Tr, r: Tr}

def lgk() -> Nat:
  0n

def lgn() -> Nat:
  22n

# xorshift: x ^= x<<13; x ^= x>>17; x ^= x<<5  (a bijection on u32)
def prng(+x: U32) -> U32:
  +b = U32.xor(x, U32.shln(x, 13n))
  +d = U32.xor(b, U32.shrn(b, 17n))
  U32.xor(d, U32.shln(d, 5n))

# key j of map seed s; injective in j for a fixed s
def key(+s: U32, +j: U32) -> U32:
  prng(U32.xor(U32.mul(U32.inc(j), 2654435761), U32.mul(s, 340573321)))

# insert: descend into one child, hand the other back untouched
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

# rejoin the two halves of a lookup
def find.join(k2: U32, v2: U32, hit: U32, pl: Tr & U32, pr: Tr & U32) -> Tr & U32:
  (l, a) = pl
  (r, b) = pr
  (Node{k2, v2, l, r}, U32.add(hit, U32.add(a, b)))

# lookup: the same act column; the tree rides back out with the value
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

# fold one lookup's (tree, value) pair into the running (tree, acc)
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

def one.fin(r: Tr & U32) -> U32:
  (t, acc) = r
  acc

def one(+g: U32, +n: Nat) -> U32:
  +s = U32.mul(U32.inc(g), 2654435761)
  one.fin(look(n, s, 0, (fill(n, s, 0, Leaf{}), 0)))

# the fork tree over the K maps: map checksums sum up
def batch(+p: Nat, +g: U32, +n: Nat) -> U32:
  match p:
    case 0n:
      one(g, n)
    case 1n+q:
      a b = batch(q, g, n) batch(q, U32.add(g, U32.shln(1, q)), n)
      U32.add(a, b)

def main() -> IO(Unit):
  IO.print(U32.show(batch!(lgk(), 0, U32.to_nat(U32.shln(1, lgn())))))
