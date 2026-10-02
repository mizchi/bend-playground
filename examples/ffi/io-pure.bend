import Base
import ./common.bend as B
# Same bind/continuation structure as the FFI loop, with no foreign request.

def loop(f: Nat, +rounds: Nat, x: U32) -> IO(U32):
  match f:
    case 0n: IO.pure(U32, x)
    case 1n+p:
      IO.bind(U32, U32, IO.pure(U32, B.kernel(rounds, x)), y => loop(p, rounds, y))

def main() -> IO(Unit):
  IO.bind(U32, Unit, loop(B.calls(), B.rounds(), B.seed()), x => IO.print(B.show(x)))
