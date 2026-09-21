import Base
# S2: bitonic sort over a balanced 2^D-leaf tree, same keys as msort.bend.
#
# warp / warp_zip / warp_node / flow / bsort are taken from
# bench/runtime/tree-bitonic/main.bend: that network is already verified
# against Bend3 on the cluster, so reusing it keeps S2 an honest bitonic sort
# rather than my re-derivation of one.  What is mine here is the size (a 2^D
# run chosen to match S1), the leaf index mapping (left 2x, right 2x+1, same
# as msort.bend) and the scan: a COMBINABLE (cnt, lo, hi, ok, sum, isum, msum)
# so that the verification pass is itself a parallel tree fold and not a
# sequential walk.  tree-bitonic's own Stat carries min/max/sorted/mix and is
# not comparable with S1's numbers; this one is.
#
# Position-weighted isum combines because
#   isum(l ++ r) = isum(l) + isum(r) + cnt(l) * sum(r)
#
# Output: "ok cnt sum isum msum", identical to msort.bend and sort.c.

type Tree is Data:
  Leaf{v: U32}
  Node{l: Tree, r: Tree}

type Sc is Data:
  Sc{cnt: U32, lo: U32, hi: U32, ok: U32, sum: U32, isum: U32, msum: U32}

# xorshift: x ^= x<<13; x ^= x>>17; x ^= x<<5
def prng(+x: U32) -> U32:
  +b = U32.xor(x, U32.shln(x, 13n))
  +d = U32.xor(b, U32.shrn(b, 17n))
  U32.xor(d, U32.shln(d, 5n))

def key(i: U32) -> U32:
  prng(U32.mul(U32.inc(i), 2654435761))

def warp_leaf.go(x: U32, y: U32, t: Bool) -> Tree:
  match t:
    case False{}:
      Node{Leaf{x}, Leaf{y}}
    case True{}:
      Node{Leaf{y}, Leaf{x}}

def warp_leaf(+x: U32, +y: U32, s: Bool) -> Tree:
  warp_leaf.go(x, y, Bool.xor(s, U32.is_gt(x, y)))

def warp_zip(wa: Tree, wb: Tree) -> Tree:
  match wa wb:
    case Node{a0, a1} Node{b0, b1}:
      Node{Node{a0, b0}, Node{a1, b1}}
    case Node{a0, a1} Leaf{bv}:
      Leaf{0}
    case Leaf{av} Node{b0, b1}:
      Leaf{0}
    case Leaf{av} Leaf{bv}:
      Leaf{0}

def warp(a: Tree, b: Tree, +s: Bool) -> Tree:
  match a b:
    case Leaf{av} Leaf{bv}:
      warp_leaf(av, bv, s)
    case Leaf{av} Node{ba, bb}:
      Leaf{0}
    case Node{aa, ab} Leaf{bv}:
      Leaf{0}
    case Node{aa, ab} Node{ba, bb}:
      wa wb = warp(aa, ba, s) warp(ab, bb, s)
      warp_zip(wa, wb)

def warp_node(t: Tree, +s: Bool) -> Tree:
  match t:
    case Leaf{v}:
      Leaf{v}
    case Node{a, b}:
      warp(a, b, s)

def flow(+d: Nat, +s: Bool, w: Tree) -> Tree:
  match d w:
    case 0n Leaf{v}:
      Leaf{v}
    case 0n Node{wa, wb}:
      Node{wa, wb}
    case 1n+p Leaf{v}:
      Leaf{v}
    case 1n+p Node{wa, wb}:
      fa fb = flow(p, s, warp_node(wa, s)) flow(p, s, warp_node(wb, s))
      Node{fa, fb}

def bsort(+d: Nat, +s: Bool, +x: U32) -> Tree:
  match d:
    case 0n:
      Leaf{key(x)}
    case 1n+p:
      sa sb = bsort(p, False{}, U32.shl(x)) bsort(p, True{}, U32.inc(U32.shl(x)))
      flow(p, s, warp(sa, sb, s))

def sc_join.go(cnt: U32, llo: U32, rhi: U32, lok: U32, rok: U32, sum: U32,
               isum: U32, msum: U32, t: Bool) -> Sc:
  match t:
    case False{}:
      Sc{cnt, llo, rhi, 0, sum, isum, msum}
    case True{}:
      Sc{cnt, llo, rhi, U32.and(lok, rok), sum, isum, msum}

def sc_join(a: Sc, b: Sc) -> Sc:
  match a b:
    case Sc{+lcnt, llo, lhi, lok, lsum, lisum, lmsum}
         Sc{rcnt, rlo, rhi, rok, +rsum, risum, rmsum}:
      sc_join.go(U32.add(lcnt, rcnt), llo, rhi, lok, rok,
        U32.add(lsum, rsum),
        U32.add(U32.add(lisum, risum), U32.mul(lcnt, rsum)),
        U32.add(lmsum, rmsum),
        U32.is_le(lhi, rlo))

def scan(t: Tree) -> Sc:
  match t:
    case Leaf{+v}:
      Sc{1, v, v, 1, v, 0, prng(v)}
    case Node{a, b}:
      l r = scan(a) scan(b)
      sc_join(l, r)

def size() -> Nat:
  25n

def show(c: Sc) -> String:
  match c:
    case Sc{cnt, lo, hi, ok, sum, isum, msum}:
      String.append(String.append(U32.show(ok), " "),
        String.append(String.append(U32.show(cnt), " "),
          String.append(String.append(U32.show(sum), " "),
            String.append(String.append(U32.show(isum), " "),
              U32.show(msum)))))

def main() -> IO(Unit):
  t = bsort!(size(), False{}, 0)
  IO.print(show(scan!(t)))
