import Base
import ./common.bend as B
import ./sat-core.bend as S
import ./sat-input.bend as G
# Independent CNFs. Each DPLL tree is sequential and short-circuits on SAT.
# Generation, allocation and witness checking are included in the timing.

def dep() -> Nat:
  12n

def size() -> Nat:
  24n

def result(+i: U32, +cnf: S.CNF, answer: S.Answer) -> B.R:
  match answer:
    case S.Sat{+model, nodes}:
      B.R{U32.mul(U32.add(model, 2654435761), U32.inc(i)), nodes, Bool.to_u32(Bool.not(S.holds(cnf, model)))}
    case S.Unsat{nodes}: B.R{0, nodes, 0}
    case S.Unknown{nodes}: B.R{0, nodes, 1}

def job(+i: U32) -> B.R:
  +n = U32.from_nat(size())
  +cnf = G.generate(U32.to_nat(U32.div(U32.mul(n, 17), 4)), n, B.seed(i))
  result(i, cnf, S.solve(cnf, 0, 0))

def batch(+d: Nat, +i: U32) -> B.R:
  match d:
    case 0n: job(i)
    case 1n+p:
      a b = batch(p, i) batch(p, U32.add(i, U32.shln(1, p)))
      B.R.add(a, b)

def main() -> IO(Unit):
  IO.print(B.R.show(batch(dep(), 0)))
