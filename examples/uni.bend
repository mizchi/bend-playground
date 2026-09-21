import Base
# D-twin: the uniform control for div.bend. 32 hash rounds on EVERY
# sample, no data-dependent branch. Same mean work as div.bend.

def lcg(s: U32) -> U32:
  U32.add(U32.mul(s, 1664525), 1013904223)

def rounds(n: Nat, s: U32) -> U32:
  match n:
    case 0n:
      s
    case 1n+p:
      +v = s
      rounds(p, U32.xor(U32.mul(v, 2654435761), U32.shrn(v, 13n)))

def pick(heavy: Bool, s: U32) -> U32:
  match heavy:
    case True{}:
      rounds(32n, s)
    case False{}:
      rounds(32n, s)

def draw(k: Nat, s: U32, acc: U32) -> U32:
  match k:
    case 0n:
      acc
    case 1n+p:
      +s1 = lcg(s)
      +h = pick(U32.is_zero(U32.and(s1, 1)), s1)
      draw(p, h, U32.add(acc, U32.and(h, 1)))

def seed(+i: U32) -> U32:
  U32.xor(U32.mul(U32.inc(i), 2654435761), 1013904223)

def tree(+d: Nat, +i: U32, +k: Nat) -> U32:
  match d:
    case 0n:
      draw(k, seed(i), 0)
    case 1n+p:
      a b = tree(p, i, k) tree(p, U32.add(i, U32.shln(1, p)), k)
      U32.add(a, b)

def main() -> IO(Unit):
  IO.print(U32.show(tree!(20n, 0, 16n)))
