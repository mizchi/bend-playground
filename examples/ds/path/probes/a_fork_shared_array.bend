import Base
# The thing P1 would need and cannot have: two forks reading ONE
# distance map. This is the frontier-parallel BFS in miniature -- two
# workers expanding from the same dist array -- and the checker stops
# it at the fork.
#   Error: expected : a
#          observed : a (consumed more than once)
def peek.fin(r: Array<U32> & U32) -> U32:
  (d2, v) = r
  v

def peek(a: Array<U32>, +i: U32) -> U32:
  peek.fin(a[i])

def probe(a: Array<U32>) -> U32:
  x y = peek(a, 0) peek(a, 1)
  U32.add(x, y)

def main() -> IO(Unit):
  IO.print(U32.show(probe(Array.new(U32, 4n, 7))))
