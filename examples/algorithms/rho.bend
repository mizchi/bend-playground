import Base
import ./common.bend as B
# Pollard rho with Floyd cycle detection and deterministic restarts.
# Inputs are semiprimes of the 16 primes below, < 2^21. Thus x*x+c fits
# Bend's immediate Nat (< 2^48); no emulated 64-bit arithmetic is needed.

def dep() -> Nat:
  19n

def prime(i: U32) -> U32:
  match i:
    case 0: 1009
    case 1: 1013
    case 2: 1019
    case 3: 1021
    case 4: 1031
    case 5: 1033
    case 6: 1039
    case 7: 1049
    case 8: 1051
    case 9: 1061
    case 10: 1063
    case 11: 1069
    case 12: 1087
    case 13: 1091
    case 14: 1093
    case k: 1097

def gcd(f: Nat, +a: U32, +b: U32, zero: Bool) -> U32:
  match f zero:
    case 0n _:
      0
    case 1n+p True{}:
      a
    case 1n+p False{}:
      +r = U32.mod(a, b)
      gcd(p, b, r, U32.is_zero(r))

def polynomial(+x: U32, +n: U32, c: U32) -> U32:
  U32.from_nat(Nat.mod(Nat.add(Nat.mul(U32.to_nat(x), U32.to_nat(x)), U32.to_nat(c)), U32.to_nat(n)))

type S is Data:
  S{x: U32, y: U32, c: U32, g: U32, found: Bool, cycle: Bool}

def step(+n: U32, x: U32, y: U32, +c: U32) -> S:
  +x2 = polynomial(x, n, c)
  +y2 = polynomial(polynomial(y, n, c), n, c)
  +g = gcd(64n, U32.sub(U32.max(x2, y2), U32.min(x2, y2)), n, False{})
  S{x2, y2, c, g, U32.is_gt(g, 1), U32.is_eq(g, n)}

def answer(+g: U32, n: U32, count: U32) -> B.R:
  +q = U32.div(n, g)
  B.R{U32.add(U32.mul(U32.min(g, q), 2654435761), U32.max(g, q)), count, 0}

def find(f: Nat, +n: U32, state: S, +count: U32) -> B.R:
  match f state:
    case 0n s:
      B.R{0, count, 1}
    case 1n+p S{x, y, c, g, False{}, cycle}:
      find(p, n, step(n, x, y, c), U32.inc(count))
    case 1n+p S{x, y, c, g, True{}, True{}}:
      find(p, n, S{2, 2, U32.inc(c), 1, False{}, False{}}, count)
    case 1n+p S{x, y, c, g, True{}, False{}}:
      answer(g, n, count)

def weighted(i: U32, r: B.R) -> B.R:
  match r:
    case B.R{v, d, e}:
      B.R{U32.mul(v, U32.inc(i)), d, e}

def job(+i: U32) -> B.R:
  +s = B.prng(B.seed(i))
  n = U32.mul(prime((s .&. 15 : U32)), prime(((s >> 8n) .&. 15 : U32)))
  weighted(i, find(65536n, n, S{2, 2, 1, 1, False{}, False{}}, 0))

def batch(+d: Nat, +i: U32) -> B.R:
  match d:
    case 0n:
      job(i)
    case 1n+p:
      a b = batch(p, i) batch(p, U32.add(i, U32.shln(1, p)))
      B.R.add(a, b)

def main() -> IO(Unit):
  IO.print(B.R.show(batch(dep(), 0)))
