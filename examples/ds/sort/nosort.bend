import Base
# NEGATIVE CONTROL for S1 / S2: the same 2^D keys in index order, folded by the
# same combinable (cnt, lo, hi, ok, sum, isum, msum) scan as bsort.bend.
# Nothing is sorted, so ok must come out 0 and isum must differ, while cnt,
# sum and msum stay bit-identical to the sorted runs.  That is what makes the
# two checks mean something: ok really discriminates order, and sum / msum
# really are order-independent multiset hashes.

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

def gen(+d: Nat, +x: U32) -> Tree:
  match d:
    case 0n:
      Leaf{key(x)}
    case 1n+p:
      a b = gen(p, U32.shl(x)) gen(p, U32.inc(U32.shl(x)))
      Node{a, b}

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
  t = gen!(size(), 0)
  IO.print(show(scan!(t)))
