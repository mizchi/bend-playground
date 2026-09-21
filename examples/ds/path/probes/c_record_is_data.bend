import Base
# The same wall one level up: a record holding Arrays cannot be Data
# either, so the BFS state can never be duplicated for a fork. This
# is why p1.bend and p2.bend both declare `type St is Type`.
#   Error: expected : Data
#          observed : Type
type St is Data:
  St{q: Array<U32>, d: Array<U32>, +head: U32, +tail: U32}

def main() -> IO(Unit):
  IO.print("x")
