import Base
import ./contract.bend as G
import ./layout.bend as L

# An explicit DFS stack bounds machine-stack use independently of page size.
# A whole page stays on one lane; independent pages supply the broad fork tree.
type Frames is Data:
  SerialRoot{}
  SerialParent{box: G.Box, own_errors: U32, pending: List<&2, L.Job>,
    previous: List<&2, G.Tree>, previous_errors: U32, parent: Frames}

type State is Data:
  SerialCursor{pending: List<&2, L.Job>, trees: List<&2, G.Tree>, errors: U32, frames: Frames}
  SerialDone{forest: L.Forest}

def prepared(plan: L.Prepared, tail: List<&2, L.Job>, previous: List<&2, G.Tree>,
    previous_errors: U32, frames: Frames) -> State:
  match plan:
    case L.Prepared{box, jobs, errors}:
      SerialCursor{jobs, Nil{}, 0, SerialParent{box, errors, tail, previous, previous_errors, frames}}

def finish(trees: List<&2, G.Tree>, errors: U32, frames: Frames) -> State:
  match frames:
    case SerialRoot{}: SerialDone{L.Forest{List.reverse(&2, G.Tree, trees), errors}}
    case SerialParent{box, own, pending, previous, previous_errors, parent}:
      +total = U32.add(own, errors)
      SerialCursor{pending, G.Tree{box, List.reverse(&2, G.Tree, trees), total} <> previous,
        U32.add(previous_errors, total), parent}

def step(state: State) -> State:
  match state:
    case SerialDone{forest}: SerialDone{forest}
    case SerialCursor{Nil{}, trees, errors, frames}: finish(trees, errors, frames)
    case SerialCursor{L.Job{node, box} <> tail, trees, errors, frames}:
      prepared(L.prepare(node, box), tail, trees, errors, frames)

def run(+f: Nat, state: State, +fallback: G.Box) -> G.Tree:
  match f state:
    case _ SerialDone{forest}: L.first(forest, fallback)
    case 0n _: G.Tree{fallback, Nil{}, 1}
    case 1n+p state: run(p, step(state), fallback)

def layout(f: Nat, node: G.Node, +box: G.Box) -> G.Tree:
  # Each input node is entered and finished once, then the root list is finished.
  run(4100n, SerialCursor{L.Job{node, box} <> Nil{}, Nil{}, 0, SerialRoot{}}, box)
