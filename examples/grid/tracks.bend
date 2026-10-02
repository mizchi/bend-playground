import Base
import ./contract.bend as G

type Cell is Data:
  Cell{base: F32, maximum: F32, flex: F32, active: F32}

type Sum is Data:
  Sum{base: F32, fixed: F32, flex: F32, growing: U32}

def cell(track: G.Track) -> Cell:
  match track:
    case G.Track{minimum, maximum, +flex}: Cell{minimum, maximum, flex, flex}

def make(f: Nat, xs: List<&2, G.Track>, +implicit: G.Track) -> List<&2, Cell>:
  match f xs:
    case 0n _: Nil{}
    case 1n+p Nil{}: cell(implicit) <> make(p, Nil{}, implicit)
    case 1n+p head <> tail: cell(head) <> make(p, tail, implicit)

def add_cell(c: Cell, s: Sum) -> Sum:
  match c s:
    case Cell{+base, maximum, flex, +active} Sum{b, fixed, total_flex, growing}:
      Sum{F32.add(b, base), F32.add(fixed, Bool.pick(F32, F32.is_gt(active, 0.0), 0.0, base)),
        F32.add(total_flex, active),
        U32.add(growing, Bool.pick(U32, F32.is_gt(maximum, base), 1, 0))}

def sum(xs: List<&2, Cell>) -> Sum:
  match xs:
    case Nil{}: Sum{0.0, 0.0, 0.0, 0}
    case head <> tail: add_cell(head, sum(tail))

def grow(c: Cell, +amount: F32) -> Cell:
  match c:
    case Cell{base, +maximum, flex, active}:
      Cell{F32.min(maximum, F32.add(base, amount)), maximum, flex, active}

def grow_all(xs: List<&2, Cell>, +amount: F32) -> List<&2, Cell>:
  match xs:
    case Nil{}: Nil{}
    case head <> tail: grow(head, amount) <> grow_all(tail, amount)

def maximize_choice(xs: List<&2, Cell>, +space: F32, base: F32, growing: U32,
    more: Bool, rest: List<&2, Cell> -> List<&2, Cell>) -> List<&2, Cell>:
  match more:
    case False{}: xs
    case True{}: rest(grow_all(xs, F32.div(F32.sub(space, base), U32.to_f32(growing))))

def maximize_step(+xs: List<&2, Cell>, +space: F32, s: Sum,
    rest: List<&2, Cell> -> List<&2, Cell>) -> List<&2, Cell>:
  match s:
    case Sum{+base, fixed, flex, +growing}:
      maximize_choice(xs, space, base, growing,
        Bool.and(F32.is_gt(F32.sub(space, base), 0.00001), U32.is_ne(growing, 0)), rest)

def maximize(f: Nat, +xs: List<&2, Cell>, +space: F32) -> List<&2, Cell>:
  match f:
    case 0n: xs
    case 1n+p: maximize_step(xs, space, sum(xs), ys => maximize(p, ys, space))

def fraction(s: Sum, space: F32) -> F32:
  match s:
    case Sum{base, fixed, flex, growing}:
      F32.div(F32.max(0.0, F32.sub(space, fixed)), F32.max(1.0, flex))

def freeze(c: Cell, +unit: F32) -> Cell:
  match c:
    case Cell{+base, maximum, flex, +active}:
      Cell{base, maximum, flex, Bool.pick(F32, F32.is_lt(F32.mul(active, unit), base), 0.0, active)}

def freeze_all(xs: List<&2, Cell>, +unit: F32) -> List<&2, Cell>:
  match xs:
    case Nil{}: Nil{}
    case head <> tail: freeze(head, unit) <> freeze_all(tail, unit)

def any_frozen(xs: List<&2, Cell>, +unit: F32) -> Bool:
  match xs:
    case Nil{}: False{}
    case Cell{base, maximum, flex, +active} <> tail:
      Bool.or(Bool.and(F32.is_gt(active, 0.0), F32.is_lt(F32.mul(active, unit), base)), any_frozen(tail, unit))

def set_flex(xs: List<&2, Cell>, +unit: F32) -> List<&2, Cell>:
  match xs:
    case Nil{}: Nil{}
    case Cell{base, maximum, +flex, active} <> tail:
      Cell{F32.max(base, F32.mul(flex, unit)), maximum, flex, active} <> set_flex(tail, unit)

def flex_choice(xs: List<&2, Cell>, +unit: F32, more: Bool,
    rest: List<&2, Cell> -> List<&2, Cell>) -> List<&2, Cell>:
  match more:
    case False{}: set_flex(xs, unit)
    case True{}: rest(freeze_all(xs, unit))

def flexible(f: Nat, +xs: List<&2, Cell>, +space: F32) -> List<&2, Cell>:
  match f:
    case 0n: xs
    case 1n+p:
      +unit = fraction(sum(xs), space)
      flex_choice(xs, unit, any_frozen(xs, unit), ys => flexible(p, ys, space))

def prefix(xs: List<&2, Cell>, a: Array<F32>, +index: U32, +offset: F32, +gap: F32) -> Array<F32>:
  match xs:
    case Nil{}: Array.set(F32, a, index, offset)
    case Cell{base, maximum, flex, active} <> tail:
      prefix(tail, Array.set(F32, a, index, offset), U32.inc(index), F32.add(F32.add(offset, base), gap), gap)

def run(xs: List<&2, G.Track>, implicit: G.Track, +count: U32, available: F32, +gap: F32) -> Array<F32>:
  +space = F32.max(0.0, F32.sub(available, F32.mul(gap, U32.to_f32(U32.sub(U32.max(count, 1), 1)))))
  cells = make(U32.to_nat(count), xs, implicit)
  prefix(flexible(129n, maximize(129n, cells, space), space), Array.new(F32, 8n, 0.0), 0, 0.0, gap)
