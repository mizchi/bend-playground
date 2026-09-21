import Base
# The asymmetry, spelled out. Uncomment one block at a time.
#
# (1) An Array cannot take a + binder at all:
#
#     def two(+a: Array<U32>) -> U32:
#       7
#     -> Error: expected : Data / observed : Type
#
# (2) One Array read from two forks:
#
#     def pick(r: Array<U32> & U32) -> U32:
#       (p, u) = r
#       u
#     def two(a: Array<U32>) -> U32:
#       x y = pick(a[0]) pick(a[1])
#       U32.add(x, y)
#     -> Error: a (consumed more than once)
#
# (3) The same shape over a Data tree: this one compiles and runs.

type T is Data:
  L{v: U32}
  N{a: T, b: T}

def sum(t: T) -> U32:
  match t:
    case L{v}:
      v
    case N{a, b}:
      x y = sum(a) sum(b)
      U32.add(x, y)

def two(+t: T) -> U32:
  x y = sum(t) sum(t)
  U32.add(x, y)

#|14
def main() -> IO(Unit):
  IO.print(U32.show(two(N{L{3}, L{4}})))
