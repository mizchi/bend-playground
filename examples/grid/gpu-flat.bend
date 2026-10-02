import Base
import ./contract.bend as G
import ./layout.bend as L

# One packed F32 buffer. Page p owns [p*stride, (p+1)*stride).
# Node id j owns four floats x/y/width/height; padding stays unwritten.
type FlatOutput is Type:
  FlatResult{buffer: Array<F32>, errors: U32}

@unsafe
def write(buffer: Array<F32>, +base: U32, box: G.Box) -> Array<F32>:
  match box:
    case G.Box{id, x, y, w, h}:
      +at = U32.add(base, U32.mul(id, 4))
      Array.set(F32, Array.set(F32, Array.set(F32, Array.set(F32,
        buffer, at, x), U32.inc(at), y), U32.add(at, 2), w), U32.add(at, 3), h)

# Explicit pending-list stack; no output Tree or recursive child-output join.
@unsafe
def prepared(+fuel: Nat, plan: L.Prepared, tail: List<&2, L.Job>,
    parents: List<&2, List<&2, L.Job>>, buffer: Array<F32>, +base: U32, errors: U32) -> FlatOutput:
  match plan:
    case L.Prepared{box, jobs, own_errors}:
      walk(fuel, jobs, tail <> parents, write(buffer, base, box), base, U32.add(errors, own_errors))

@unsafe
def walk(fuel: Nat, pending: List<&2, L.Job>, parents: List<&2, List<&2, L.Job>>,
    buffer: Array<F32>, +base: U32, errors: U32) -> FlatOutput:
  match fuel pending:
    case 0n _: FlatResult{buffer, U32.inc(errors)}
    case 1n+p Nil{}:
      match parents:
        case Nil{}: FlatResult{buffer, errors}
        case head <> tail: walk(p, head, tail, buffer, base, errors)
    case 1n+p L.Job{node, box} <> tail:
      prepared(p, L.prepare(node, box), tail, parents, buffer, base, errors)

@unsafe
def join(left: FlatOutput, right: FlatOutput) -> FlatOutput:
  match left right:
    case FlatResult{a, ae} FlatResult{b, be}:
      FlatResult{Array.join(F32, a, b), U32.add(ae, be)}

# Unsafe sharing is confined to disjoint page slices. There are no racing writes.
# Array.join consumes both handles after their tasks finish; the host owns one.
@unsafe
def batch(+depth: Nat, +node: G.Node, +width: F32, +height: F32,
    +index: U32, +offset: U32, +stride: U32, +buffer: Array<F32>) -> FlatOutput:
  match depth:
    case 0n:
      delta = U32.to_f32(U32.mod(U32.add(offset, index), 97))
      walk(4100n, L.Job{node, G.Box{0, 0.0, 0.0, F32.add(width, delta), height}} <> Nil{},
        Nil{}, buffer, U32.mul(index, stride), 0)
    case 1n+p:
      a b = batch(p, node, width, height, index, offset, stride, buffer)
        batch(p, node, width, height, U32.add(index, U32.shln(1, p)), offset, stride, buffer)
      join(a, b)
