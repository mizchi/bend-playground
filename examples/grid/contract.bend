import Base
# Strict normalized API. Starts are CSS positive line numbers; 0 means auto.
# Capacities: 32 columns, 128 rows, 256 children; horizontal LTR, stretch.
type Track is Data:
  Track{minimum: F32, maximum: F32, flex: F32}

type Item is Data:
  Item{id: U32, column: U32, row: U32, cs: U32, rs: U32}

type Style is Data:
  Style{columns: List<&2, Track>, rows: List<&2, Track>, auto_column: Track, auto_row: Track,
    column_gap: F32, row_gap: F32, dense: Bool, nc: U32, nr: U32}

type Node is Data:
  Leaf{item: Item}
  Grid{item: Item, style: Style, children: List<&2, Node>}

type Place is Data:
  Place{column: U32, row: U32, cs: U32, rs: U32}

type Box is Data:
  Box{id: U32, x: F32, y: F32, width: F32, height: F32}

type Tree is Data:
  Tree{box: Box, children: List<&2, Tree>, errors: U32}

type Stats is Data:
  Stats{checksum: U32, nodes: U32, errors: U32}

def item(node: Node) -> Item:
  match node:
    case Leaf{i}: i
    case Grid{i, s, c}: i

# Array reads return an owned array plus a shared Data value.
def read_result(~T: Data, ~R: Type, pair: Array<T> & T, f: Array<T> -> T -> R) -> R:
  (a, v) = pair
  f(a, v)

def read(~T: Data, ~R: Type, a: Array<T>, i: U32, f: Array<T> -> T -> R) -> R:
  read_result(~T, ~R, Array.get(T, a, i), f)
