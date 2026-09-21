import Base
# A: Monte Carlo pi -- REDUCE-heavy, balanced, branchless.
# The reference "ideal" shape for Bend's GPU: a perfect fork tree whose
# leaves each do a fixed amount of arithmetic and whose combine is one
# add. No divergence: the hit test is a branchless mask, as in the
# mandelbrot bench.
#
# LCG: s = s*1664525 + 1013904223 (mod 2^32); a sample takes the top 15
# bits of two successive states, so x,y in [0,32768) and x*x+y*y fits a
# u32. hit = [x*x + y*y < 2^30].

def b2u(b: Bool) -> U32:
  match b:
    case False{}:
      0
    case True{}:
      1

def lcg(s: U32) -> U32:
  U32.add(U32.mul(s, 1664525), 1013904223)

# K branchless samples from one seed
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

def leaf(+i: U32, +k: Nat) -> U32:
  draw(k, seed(i), 0)

def tree(+d: Nat, +i: U32, +k: Nat) -> U32:
  match d:
    case 0n:
      leaf(i, k)
    case 1n+p:
      a b = tree(p, i, k) tree(p, U32.add(i, U32.shln(1, p)), k)
      U32.add(a, b)

def dep() -> Nat:
  20n

def per() -> Nat:
  64n

def main() -> IO(Unit):
  IO.print(U32.show(tree!(dep(), 0, per())))
