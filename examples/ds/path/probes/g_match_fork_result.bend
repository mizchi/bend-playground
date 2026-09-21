import Base
# A fork's two results cannot be opened where they are bound, so two
# array-carrying states can only be merged by handing both to a def.
#   Error: a match cannot scrutinize a local binder (give it its own
#          def)
type St is Type:
  St{d: Array<U32>}

def half(st: St, +i: U32) -> St:
  St{d} = st
  St{d[i] <- i}

def probe(d1: Array<U32>, d2: Array<U32>) -> St:
  x y = half(St{d1}, 0) half(St{d2}, 1)
  St{dx} = x
  St{dy} = y
  St{dx}

def main() -> IO(Unit):
  IO.print("x")
