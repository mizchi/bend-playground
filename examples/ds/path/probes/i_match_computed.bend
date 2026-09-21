import Base
# A match may only scrutinize a parameter or a field. "which branch do
# I take" therefore cannot be computed where it is used: the bit has
# to ride in as a parameter from the caller. This is what shapes get()
# in ../../p3/gather.bend and set() in h_tree_write_fork.bend -- both
# fold the decision into a multi-scrutinee match over (structure, Bool)
# rather than a helper def, because a helper would be mutual recursion
# and that is banned too (see d_forward_ref.bend).
#   Error: a parameter or field scrutinee (a match cannot scrutinize a
#          computed value: give it its own def)
def probe(+i: U32, +s: U32) -> U32:
  match U32.is_lt(i, s):
    case True{}:
      1
    case False{}:
      0

def main() -> IO(Unit):
  IO.print(U32.show(probe(1, 2)))
