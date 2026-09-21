import Base
def go(f: Nat, +acc: U32) -> U32:
  match f:
    case 0n:
      acc
    case 1n+p:
      go(p, U32.inc(acc))

def main() -> IO(Unit):
  IO.print(U32.show(go(10n, 0)))
