import Base
# No mutual recursion, no forward references: every helper has to be
# defined above its use. This is what forces the pop path in p1.bend
# to read bottom-up (look.push, look.seen, look.wall, look.open,
# look, look4, pop.done, pop.dist, pop.cell, pop).
#   Error: expected : a defined name
#          observed : later
def probe(x: U32) -> U32:
  later(x)

def later(x: U32) -> U32:
  U32.inc(x)

def main() -> IO(Unit):
  IO.print(U32.show(probe(1)))
