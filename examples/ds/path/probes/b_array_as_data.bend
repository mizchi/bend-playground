import Base
# The escape hatch that does not exist: + makes a value duplicable,
# but only for a Data type, and Array is not one.
#   Error: expected : Data
#          observed : Type
def peek.fin(r: Array<U32> & U32) -> U32:
  (d2, v) = r
  v

def probe(+a: Array<U32>) -> U32:
  U32.add(peek.fin(a[0]), peek.fin(a[1]))

def main() -> IO(Unit):
  IO.print(U32.show(probe(Array.new(U32, 4n, 7))))
