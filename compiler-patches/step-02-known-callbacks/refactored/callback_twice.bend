# A known callback uses its scalar capture twice; the caller reuses it.
import Base

def twice(x: U32, callback: U32 -> U32) -> U32:
  callback(x)

def run(+bias: U32, x: U32) -> U32:
  y = twice(x, v => U32.add(v, U32.add(bias, bias)))
  U32.add(y, bias)

def main() -> U32:
  run(3, 33)

#|42
