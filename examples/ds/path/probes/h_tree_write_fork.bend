import Base
# The Data-tree escape hatch, taken as far as it goes for BFS.
#
# A Data tree CAN take a + binder, and + is a refcount bump, not a
# deep copy, so two forks may read one tree (see
# ../../p3/nofork_array.bend). Writing is the part that does not
# carry over: each fork's set() returns its OWN tree, so after the
# fork there are two distance maps and no shared one. Putting them
# back together is merge(), a full walk over both -- and for BFS a
# cell-wise min is not even the right answer, because a distance
# found by the half that did not own the true shortest path is wrong.
#
# So the tree buys the fork and loses the sharing: the two halves
# stop seeing each other's stamps, which is exactly the thing that
# makes BFS visit each cell once. This compiles and runs; it is not
# a parallel BFS.
#|57
type T is Data:
  L{v: U32}
  N{a: T, b: T}

# write v at index i of a tree of size s; lt says whether i is in the
# left half (a computed value cannot be matched, so the caller hands
# the bit in, and the two scrutinees are folded into one match to
# avoid a helper def, which would be mutual recursion)
def set(t: T, +i: U32, +s: U32, lt: Bool, +v: U32) -> T:
  match t lt:
    case L{u} True{}:
      L{v}
    case L{u} False{}:
      L{v}
    case N{a, b} True{}:
      +h = U32.shrn(s, 1n)
      N{set(a, i, h, U32.is_lt(i, U32.shrn(h, 1n)), v), b}
    case N{a, b} False{}:
      +h = U32.shrn(s, 1n)
      +j = U32.sub(i, h)
      N{a, set(b, j, h, U32.is_lt(j, U32.shrn(h, 1n)), v)}

# the merge the fork forces: a full walk over both trees
def merge(x: T, y: T) -> T:
  match x y:
    case L{+u} L{+v}:
      L{U32.min(u, v)}
    case L{u} N{a, b}:
      L{u}
    case N{a, b} L{v}:
      L{v}
    case N{a, b} N{c, e}:
      N{merge(a, c), merge(b, e)}

def fin(t: T) -> U32:
  match t:
    case L{v}:
      v
    case N{a, b}:
      U32.add(fin(a), fin(b))

# the shape Array cannot have and the tree can: one t, two forks
def probe(+t: T) -> U32:
  x y = set(t, 1, 8, True{}, 1) set(t, 6, 8, False{}, 2)
  fin(merge(x, y))

def main() -> IO(Unit):
  IO.print(U32.show(probe(N{N{N{L{9}, L{9}}, N{L{9}, L{9}}}, N{N{L{9}, L{9}}, N{L{9}, L{9}}}})))
