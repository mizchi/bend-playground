import Base

type R is Data:
  R{checksum: U32, detail: U32, errors: U32}

def R.add(a: R, b: R) -> R:
  match a b:
    case R{ac, ad, ae} R{bc, bd, be}:
      R{U32.add(ac, bc), U32.add(ad, bd), U32.add(ae, be)}

def R.show(r: R) -> String:
  match r:
    case R{c, d, e}:
      "checksum=" ++ U32.show(c) ++ " detail=" ++ U32.show(d) ++ " errors=" ++ U32.show(e)

def prng(+x: U32) -> U32:
  +b = U32.xor(x, U32.shln(x, 13n))
  +d = U32.xor(b, U32.shrn(b, 17n))
  U32.xor(d, U32.shln(d, 5n))

def seed(+i: U32) -> U32:
  U32.xor(U32.mul(U32.inc(i), 2654435761), 1013904223)
