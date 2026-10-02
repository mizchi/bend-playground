import Base
import ./common.bend as B

def native_work(x: U32, rounds: U32) -> IO(U32):
  import "./effect.c"

def loop(f: Nat, +rounds: U32, x: U32) -> IO(U32):
  match f:
    case 0n: IO.pure(U32, x)
    case 1n+p:
      IO.bind(U32, U32, native_work(x, rounds), y => loop(p, rounds, y))

def main() -> IO(Unit):
  IO.bind(U32, Unit, loop(B.calls(), U32.from_nat(B.rounds()), B.seed()), x => IO.print(B.show(x)))
