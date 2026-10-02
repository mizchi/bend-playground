import Base

def calls() -> Nat:
  1048576n

def rounds() -> Nat:
  1n

def seed() -> U32:
  305419896

def step(+x: U32) -> U32:
  +a = U32.xor(x, U32.shln(x, 13n))
  +b = U32.xor(a, U32.shrn(a, 17n))
  U32.xor(b, U32.shln(b, 5n))

def kernel(f: Nat, x: U32) -> U32:
  match f:
    case 0n: x
    case 1n+p: kernel(p, step(x))

def show(x: U32) -> String:
  "checksum=" ++ U32.show(x)
