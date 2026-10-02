import Base

def step(+x: U32) -> U32:
  +a = U32.xor(x, U32.shln(x, 13n))
  +b = U32.xor(a, U32.shrn(a, 17n))
  U32.xor(b, U32.shln(b, 5n))

def work(rounds: Nat, x: U32) -> U32:
  match rounds:
    case 0n: x
    case 1n+p: work(p, step(x))

# Every global job runs exactly once, independently of the batch partition.
def batch(+depth: Nat, +rounds: Nat, +seed: U32, +offset: U32) -> U32:
  match depth:
    case 0n: work(rounds, U32.add(seed, offset))
    case 1n+p:
      a b = batch(p, rounds, seed, offset)
        batch(p, rounds, seed, U32.add(offset, U32.shln(1, p)))
      U32.add(a, b)
