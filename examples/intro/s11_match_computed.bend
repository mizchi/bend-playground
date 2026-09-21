import Base
def sign(+i: U32, +s: U32) -> U32:
  match U32.is_lt(i, s):
    case True{}:
      1
    case False{}:
      0

def main() -> IO(Unit):
  IO.print(U32.show(sign(1, 2)))
