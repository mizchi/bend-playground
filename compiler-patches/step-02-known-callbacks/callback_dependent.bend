import Base

law apply:
  for +x: U32
  for -proof: {x == x : U32}
  for callback: U32 -> U32
  U32

def apply(x, proof, callback):
  callback(x)

def main() -> U32:
  apply(40, {==}, y => U32.add(y, 2))

#| 42
