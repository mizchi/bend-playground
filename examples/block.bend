import Base
# C2: same fork tree and the SAME TOTAL WORK as mc.bend, but the work is
# a linear ramp across the leaves: leaf i draws 2*K*i/n samples instead
# of K. sum(2*K*i/n) ~= K*n, so a work-stealing runtime should not care.
# Bend deals tasks round-robin and never moves them, so the busiest lane
# does ~2x the mean.

def b2u(b: Bool) -> U32:
  match b:
    case False{}:
      0
    case True{}:
      1

def lcg(s: U32) -> U32:
  U32.add(U32.mul(s, 1664525), 1013904223)

def draw(k: Nat, s: U32, acc: U32) -> U32:
  match k:
    case 0n:
      acc
    case 1n+p:
      +s1 = lcg(s)
      +s2 = lcg(s1)
      +x = U32.shrn(s1, 17n)
      +y = U32.shrn(s2, 17n)
      q = U32.add(U32.mul(x, x), U32.mul(y, y))
      draw(p, s2, U32.add(acc, b2u(U32.is_lt(q, 1073741824))))

def seed(+i: U32) -> U32:
  U32.xor(U32.mul(U32.inc(i), 2654435761), 1013904223)

# block: the first 1/64 of the index RANGE draws 64*K samples, the rest
# draw none. Identical total work to uniform; the load now correlates
# with the high bits of the index, i.e. with one contiguous subtree.
def leaf(+i: U32, +d: Nat, +k: Nat) -> U32:
  n = U32.to_nat(U32.mul(U32.mul(64, U32.from_nat(k)),
        Bool.to_u32(U32.is_lt(i, 16384))))
  draw(n, seed(i), 0)

def tree(+t: Nat, +d: Nat, +i: U32, +k: Nat) -> U32:
  match t:
    case 0n:
      leaf(i, d, k)
    case 1n+p:
      a b = tree(p, d, i, k) tree(p, d, U32.add(i, U32.shln(1, p)), k)
      U32.add(a, b)

def dep() -> Nat:
  20n

def per() -> Nat:
  4096n

def main() -> IO(Unit):
  IO.print(U32.show(tree!(dep(), dep(), 0, per())))
