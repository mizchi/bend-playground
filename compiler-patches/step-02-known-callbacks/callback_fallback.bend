import Base

def apply(x: U32, callback: U32 -> U32) -> U32:
  callback(x)

def choose(b: Bool) -> U32 -> U32:
  match b:
    case False{}: x => U32.add(x, 1)
    case True{}: x => U32.add(x, 2)

# A dynamic function must stay callable through the generic runtime.
def dynamic(b: Bool, x: U32) -> U32:
  apply(x, choose(b))

# Non-scalar captures are deliberately outside this experiment's subset.
def add_value(result: Array<U32> & U32, x: U32) -> U32:
  (array, value) = result
  U32.add(x, value)

def boxed(array: Array<U32>, x: U32) -> U32:
  apply(x, y => add_value(Array.get(U32, array, 0), y))

# An already raised callback parameter, inside a recursive callee.
def recurse(n: Nat, x: U32, callback: U32 -> U32) -> U32:
  match n:
    case 0n: callback(x)
    case 1n+p: recurse(p, U32.inc(x), callback)

def main() -> U32:
  a = dynamic(True{}, 10)
  b = boxed(Array.new(U32, 0n, 7), a)
  recurse(20n, b, x => U32.add(x, 3))

#| 42
