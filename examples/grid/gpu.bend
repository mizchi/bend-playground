import Base
import ./contract.bend as G
import ./serial-layout.bend as S

# Keep every rectangle in the result: host consumption is a separate IO step.
type Batch is Data:
  Page{index: U32, tree: G.Tree}
  Fork{left: Batch, right: Batch}

def batch(+depth: Nat, +node: G.Node, +width: F32, +height: F32,
    +index: U32, +offset: U32) -> Batch:
  match depth:
    case 0n:
      delta = U32.to_f32(U32.mod(U32.add(offset, index), 97))
      Page{index, S.layout(2050n, node, G.Box{0, 0.0, 0.0, F32.add(width, delta), height})}
    case 1n+p:
      a b = batch(p, node, width, height, index, offset)
        batch(p, node, width, height, U32.add(index, U32.shln(1, p)), offset)
      Fork{a, b}
