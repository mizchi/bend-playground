import Base
# Can a SHARED read-only structure be indexed from many forks at once?
#
# An Array cannot: it is Type, not Data, so it takes no + binder, and
# one owner means one reader. See nofork_array.bend for the two errors.
#
# A Data tree can: + on a Data value is a refcount bump (comp.ts:4056,
# term_keep -> rfc_bump), not a deep copy. So this program builds one
# perfect tree of 2^D leaves and does 2^G random lookups into it from a
# fork tree, every fork holding the same tree through +.
#
# The question is not whether it works -- it does -- but what it costs
# against a flat array. gather.c and gather_tree.c are the two controls.

type T is Data:
  L{v: U32}
  N{a: T, b: T}

def hash(+i: U32) -> U32:
  U32.xor(U32.mul(U32.inc(i), 2654435761), U32.shrn(i, 3n))

def build(+d: Nat, +i: U32) -> T:
  match d:
    case 0n:
      L{hash(i)}
    case 1n+p:
      a b = build(p, i) build(p, U32.add(i, U32.shln(1, p)))
      N{a, b}

# Descend by halving stride; the unused half is dropped. The branch
# rides in as a Bool parameter because a match cannot scrutinize a
# computed value, and a helper def would be mutual recursion (banned).
# So the whole descent is one self-recursive def over (tree, bit).
def get(t: T, +i: U32, +s: U32, lt: Bool) -> U32:
  match t lt:
    case L{v} True{}:
      v
    case L{v} False{}:
      v
    case N{a, b} True{}:
      +h = U32.shrn(s, 1n)
      get(a, i, h, U32.is_lt(i, h))
    case N{a, b} False{}:
      +j = U32.sub(i, s)
      +h = U32.shrn(s, 1n)
      get(b, j, h, U32.is_lt(j, h))

# 2^g lookups, forked; t is shared across every fork via +
def gather(+g: Nat, +t: T, +i: U32, +s: U32, +m: U32) -> U32:
  match g:
    case 0n:
      +q = U32.and(hash(i), m)
      get(t, q, s, U32.is_lt(q, s))
    case 1n+p:
      a b = gather(p, t, i, s, m) gather(p, t, U32.add(i, U32.shln(1, p)), s, m)
      U32.add(a, b)

def dep() -> Nat:
  22n

def gat() -> Nat:
  24n

def run(+d: Nat, +g: Nat) -> U32:
  +n = U32.shln(1, d)
  gather(g, build(d, 0), 0, U32.shrn(n, 1n), U32.sub(n, 1))

def main() -> IO(Unit):
  IO.print(U32.show(run!(dep(), gat())))
