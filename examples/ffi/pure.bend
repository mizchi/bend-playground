import Base
import ./common.bend as B

def loop(f: Nat, +rounds: Nat, x: U32) -> U32:
  match f:
    case 0n: x
    case 1n+p: loop(p, rounds, B.kernel(rounds, x))

def main() -> IO(Unit):
  IO.print(B.show(loop(B.calls(), B.rounds(), B.seed())))
