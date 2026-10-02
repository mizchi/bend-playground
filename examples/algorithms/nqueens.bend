import Base
import ./common.bend as B
# Exact bitboard DFS for one board, partitioned by the first two columns.
# The 256 possible prefixes are independent; recursion below them is sequential.
# Contract: dep=8 and 4 <= size <= 16. No symmetry shortcuts or approximations.

def dep() -> Nat:
  8n

def size() -> Nat:
  15n

# A path has at most 16 choices at each of 16 rows. 512 bounds the two
# recursive calls per choice; fuel is a termination witness, not a work budget.
def search(+f: Nat, +mask: U32, +cols: U32, +left: U32, +right: U32, +available: U32,
           finished: Bool, more: Bool) -> U32:
  match f finished more:
    case 0n _ _:
      0
    case 1n+p True{} _:
      1
    case 1n+p False{} False{}:
      0
    case 1n+p False{} True{}:
      +bit = (available .&. (0 - available) : U32)
      +cols2 = (cols .|. bit : U32)
      +left2 = (((left .|. bit) << 1n) .&. mask : U32)
      +right2 = ((right .|. bit) >> 1n : U32)
      +av2 = (mask .&. U32.not((cols2 .|. left2 .|. right2 : U32)) : U32)
      +rest = U32.xor(available, bit)
      a = search(p, mask, cols2, left2, right2, av2, U32.is_eq(cols2, mask), U32.is_ne(av2, 0))
      b = search(p, mask, cols, left, right, rest, False{}, U32.is_ne(rest, 0))
      U32.add(a, b)

def prefix(+mask: U32, +a: U32, +b: U32, valid: Bool) -> B.R:
  match valid:
    case False{}:
      B.R{0, 0, 0}
    case True{}:
      +cols = (a .|. b : U32)
      +left = ((((a << 1n) .|. b) << 1n) .&. mask : U32)
      +right = (((a >> 1n) .|. b) >> 1n : U32)
      +av = (mask .&. U32.not((cols .|. left .|. right : U32)) : U32)
      B.R{search(512n, mask, cols, left, right, av, False{}, U32.is_ne(av, 0)), 0, 0}

def job(+i: U32) -> B.R:
  +c0 = (i .&. 15 : U32)
  +c1 = (i >> 4n : U32)
  +a = U32.shln(1, U32.to_nat(c0))
  +b = U32.shln(1, U32.to_nat(c1))
  prefix(U32.sub(U32.shln(1, size()), 1), a, b,
    Bool.and(Bool.and(U32.is_lt(c0, U32.from_nat(size())), U32.is_lt(c1, U32.from_nat(size()))),
      U32.is_zero((b .&. (a .|. (a << 1n) .|. (a >> 1n)) : U32))))

def batch(+d: Nat, +i: U32) -> B.R:
  match d:
    case 0n:
      job(i)
    case 1n+p:
      a b = batch(p, i) batch(p, U32.add(i, U32.shln(1, p)))
      B.R.add(a, b)

def main() -> IO(Unit):
  IO.print(B.R.show(batch(dep(), 0)))
