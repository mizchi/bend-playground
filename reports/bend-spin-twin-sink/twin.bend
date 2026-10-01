import Base

type Xs is Data:
  X0{}
  X1{v: U32, rest: Xs}

# consumes xs, never reads all
def Xs.walk(xs: Xs, +all: Xs, acc: Xs) -> Xs:
  match xs:
    case X0{}:
      acc
    case X1{v, rest}:
      Xs.walk(rest, all, X1{(v + 1 : U32), acc})

def Xs.sum(xs: Xs, acc: U32) -> U32:
  match xs:
    case X0{}:
      acc
    case X1{v, rest}:
      Xs.sum(rest, (acc + v : U32))

def go(k: Nat, +xs: Xs) -> Xs:
  match k:
    case 0n:
      xs
    case 1n+p:
      go(p, Xs.walk(xs, xs, X0{}))

def main() -> IO(Unit):
  IO.print(U32.show(Xs.sum(go(U32.to_nat(1000000), X1{1, X1{2, X1{3, X1{4, X0{}}}}}), 0)))
