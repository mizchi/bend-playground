import Base
import ./common.bend as B
import ./sat-core.bend as S
# Deterministic random 3-SAT, no planted model. Each clause has 3 distinct
# variables, and there are floor(4.25 * n) clauses. Contract: 3 <= n <= 32.

def avoid(+c: U32, +a: U32, +b: U32, +n: U32) -> U32:
  Bool.pick(U32, Bool.or(U32.is_eq(c, a), U32.is_eq(c, b)), U32.mod(U32.inc(c), n), c)

def generate(f: Nat, +n: U32, +s: U32) -> S.CNF:
  match f:
    case 0n: S.End{}
    case 1n+p:
      +a = U32.mod(s, n)
      +b = U32.mod(U32.add(a, U32.inc(U32.mod((s >> 8n : U32), U32.sub(n, 1)))), n)
      +c = avoid(avoid(U32.mod((s >> 16n : U32), n), a, b, n), a, b, n)
      +ba = U32.shln(1, U32.to_nat(a))
      +bb = U32.shln(1, U32.to_nat(b))
      +bc = U32.shln(1, U32.to_nat(c))
      +pos = (Bool.pick(U32, U32.is_ne((s .&. 16777216 : U32), 0), ba, 0)
          .|. Bool.pick(U32, U32.is_ne((s .&. 33554432 : U32), 0), bb, 0)
          .|. Bool.pick(U32, U32.is_ne((s .&. 67108864 : U32), 0), bc, 0) : U32)
      S.Clause{pos, U32.xor((ba .|. bb .|. bc : U32), pos), generate(p, n, B.prng(s))}
