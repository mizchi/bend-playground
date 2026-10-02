import Base
# Probe (Bend 2.0.34, 7d24b8d0): the cost of a fork issued from a sequential
# loop. loop runs n() turns; each turn computes two calls of work (w() steps
# of an xorshift) and feeds their sum to the next turn, either as a parallel
# let (par() = True: a fork every turn) or as two plain lets. tree runs the
# same 2 * n() calls as the leaves of one fork tree. The two loops print
# the same number; the tree uses independent seeds and a different sum.
# Measure with fork_cost.sh: on 4 threads the forking loop
# runs far slower than the plain one, the tree does not.

def n() -> Nat:
  4096n

def w() -> Nat:
  64n

# 0 the plain loop, 1 the forking loop, 2 the fork tree
def mode() -> U32:
  1

def step(+x: U32) -> U32:
  +b = U32.xor(x, U32.shln(x, 13n))
  +d = U32.xor(b, U32.shrn(b, 17n))
  U32.xor(d, U32.shln(d, 5n))

def work(f: Nat, +x: U32) -> U32:
  match f:
    case 0n:
      x
    case 1n+p:
      work(p, step(x))

def loop.par(f: Nat, +acc: U32) -> U32:
  match f:
    case 0n:
      acc
    case 1n+p:
      a b = work(w(), acc) work(w(), U32.inc(acc))
      loop.par(p, (a + b : U32))

def loop.seq(f: Nat, +acc: U32) -> U32:
  match f:
    case 0n:
      acc
    case 1n+p:
      a = work(w(), acc)
      b = work(w(), U32.inc(acc))
      loop.seq(p, (a + b : U32))

# the 2 * n() calls of the loops as one fork tree of depth d (the sum differs
# from the loops' chained value; it is printed for the work to be done)
def tree(+d: Nat, +i: U32) -> U32:
  match d:
    case 0n:
      work(w(), i)
    case 1n+p:
      a b = tree(p, i) tree(p, U32.add(i, U32.shln(1, p)))
      (a + b : U32)

def run(choice: Cmp) -> U32:
  match choice:
    case LT{}:
      loop.seq(n(), 1)
    case EQ{}:
      loop.par(n(), 1)
    case GT{}:
      tree(U32.log2((2 * U32.from_nat(n()) : U32)), 1)

def main() -> IO(Unit):
  IO.print(U32.show(run(U32.cmp(mode(), 1))))
