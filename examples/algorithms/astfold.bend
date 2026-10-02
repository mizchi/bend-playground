import Base
import ./common.bend as B
# Build independent expression trees, fold constants and algebraic identities,
# then evaluate and count the surviving nodes. Jobs share no mutable state.
# Tree generation and allocation are included in the benchmark.

def dep() -> Nat:
  14n

def size() -> Nat:
  9n

type Expr is Data:
  C{v: U32}
  V{i: U32}
  Add{a: Expr, b: Expr}
  Mul{a: Expr, b: Expr}

def leaf(+s: U32, variable: Bool) -> Expr:
  match variable:
    case True{}:
      V{((s >> 8n) .&. 3 : U32)}
    case False{}:
      C{((s >> 8n) .&. 15 : U32)}

def make(a: Expr, b: Expr, add: Bool) -> Expr:
  match add:
    case True{}:
      Add{a, b}
    case False{}:
      Mul{a, b}

def generate(+d: Nat, +s: U32) -> Expr:
  match d:
    case 0n:
      leaf(s, U32.is_zero((s .&. 3 : U32)))
    case 1n+p:
      a = generate(p, B.prng(s))
      b = generate(p, B.prng(U32.xor(s, 277803737)))
      make(a, b, U32.is_zero((s .&. 1 : U32)))

def add_left(v: U32, b: Expr, zero: Bool) -> Expr:
  match zero:
    case True{}:
      b
    case False{}:
      Add{C{v}, b}

def add_right(a: Expr, v: U32, zero: Bool) -> Expr:
  match zero:
    case True{}:
      a
    case False{}:
      Add{a, C{v}}

def fold_add(a: Expr, b: Expr) -> Expr:
  match a b:
    case C{u} C{v}:
      C{U32.add(u, v)}
    case C{+u} x:
      add_left(u, x, U32.is_zero(u))
    case x C{+v}:
      add_right(x, v, U32.is_zero(v))
    case x y:
      Add{x, y}

def mul_left(v: U32, b: Expr, zero: Bool, one: Bool) -> Expr:
  match zero one:
    case True{} _:
      C{0}
    case False{} True{}:
      b
    case False{} False{}:
      Mul{C{v}, b}

def mul_right(a: Expr, v: U32, zero: Bool, one: Bool) -> Expr:
  match zero one:
    case True{} _:
      C{0}
    case False{} True{}:
      a
    case False{} False{}:
      Mul{a, C{v}}

def fold_mul(a: Expr, b: Expr) -> Expr:
  match a b:
    case C{u} C{v}:
      C{U32.mul(u, v)}
    case C{+u} x:
      mul_left(u, x, U32.is_zero(u), U32.is_eq(u, 1))
    case x C{+v}:
      mul_right(x, v, U32.is_zero(v), U32.is_eq(v, 1))
    case x y:
      Mul{x, y}

def fold(t: Expr) -> Expr:
  match t:
    case C{v}:
      C{v}
    case V{i}:
      V{i}
    case Add{a, b}:
      a2 = fold(a)
      b2 = fold(b)
      fold_add(a2, b2)
    case Mul{a, b}:
      a2 = fold(a)
      b2 = fold(b)
      fold_mul(a2, b2)

def variable(i: U32) -> U32:
  match i:
    case 0: 2
    case 1: 3
    case 2: 5
    case k: 7

type Stats is Data:
  Stats{value: U32, nodes: U32}

def Stats.join(a: Stats, b: Stats, multiply: Bool) -> Stats:
  match a b:
    case Stats{+av, an} Stats{+bv, bn}:
      Stats{Bool.pick(U32, multiply, U32.mul(av, bv), U32.add(av, bv)), U32.inc(U32.add(an, bn))}

def inspect(t: Expr) -> Stats:
  match t:
    case C{v}:
      Stats{v, 1}
    case V{i}:
      Stats{variable(i), 1}
    case Add{a, b}:
      Stats.join(inspect(a), inspect(b), False{})
    case Mul{a, b}:
      Stats.join(inspect(a), inspect(b), True{})

def result(i: U32, stats: Stats) -> B.R:
  match stats:
    case Stats{v, n}:
      B.R{U32.mul(v, U32.inc(i)), n, 0}

def job(+i: U32) -> B.R:
  result(i, inspect(fold(generate(size(), B.seed(i)))))

def batch(+d: Nat, +i: U32) -> B.R:
  match d:
    case 0n:
      job(i)
    case 1n+p:
      a b = batch(p, i) batch(p, U32.add(i, U32.shln(1, p)))
      B.R.add(a, b)

def main() -> IO(Unit):
  IO.print(B.R.show(batch(dep(), 0)))
