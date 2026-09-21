import Base
type Lst is Data:
  Lnil{}
  Lcons{h: U32, t: Lst}

type Ck is Data:
  Ck{i: U32, ok: U32, sum: U32, isum: U32, msum: U32, prev: U32}

def prng(+x: U32) -> U32:
  +b = U32.xor(x, U32.shln(x, 13n))
  +d = U32.xor(b, U32.shrn(b, 17n))
  U32.xor(d, U32.shln(d, 5n))

def key(i: U32) -> U32:
  prng(U32.mul(U32.inc(i), 2654435761))

def fuel() -> Nat:
  67108864n

def ck0() -> Ck:
  Ck{0, 1, 0, 0, 0, 0}

def push(c: Ck, +v: U32) -> Ck:
  match c:
    case Ck{+i, ok, sum, isum, msum, prev}:
      Ck{U32.inc(i), U32.and(ok, Bool.to_u32(U32.is_le(prev, v))),
        U32.add(sum, v), U32.add(isum, U32.mul(i, v)),
        U32.add(msum, prng(v)), v}

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

# tail-recursive list build: O(1) depth
def build(+f: Nat, +x: U32, acc: Lst) -> Lst:
  match f:
    case 0n:
      acc
    case 1n+p:
      build(p, U32.inc(x), Lcons{key(x), acc})

def go(+d: Nat) -> Ck:
  drain(fuel(), build(d, 0, Lnil{}), ck0())

def cnt(c: Ck) -> U32:
  match c:
    case Ck{i, ok, sum, isum, msum, prev}:
      i

def main() -> IO(Unit):
  c = go!(65536n)
  IO.print(U32.show(cnt(c)))
