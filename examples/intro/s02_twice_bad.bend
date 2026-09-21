import Base
def double(x: U32) -> U32:
  U32.add(x, x)

def main() -> IO(Unit):
  IO.print(U32.show(double(21)))
