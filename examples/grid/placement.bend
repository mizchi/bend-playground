import Base
import ./contract.bend as G

# A grid owns its mutable occupancy and output arrays. Rows are 32-bit masks.
type Work is Type:
  Work{occupied: Array<U32>, locked: Array<U32>, places: Array<G.Place>,
    columns: U32, rows: U32, cursor_column: U32, cursor_row: U32, errors: U32}

type Found is Data:
  Found{column: U32, row: U32, ok: Bool}

def mask(+column: U32, span: U32) -> U32:
  U32.shln(U32.shrn(4294967295, U32.to_nat(U32.sub(32, span))), U32.to_nat(column))

def free_next(a: Array<U32>, clear: Bool, rest: Array<U32> -> Array<U32> & Bool) -> Array<U32> & Bool:
  match clear:
    case True{}: rest(a)
    case False{}: (a, False{})

def free_rows(f: Nat, a: Array<U32>, +row: U32, +bits: U32) -> Array<U32> & Bool:
  match f:
    case 0n: (a, True{})
    case 1n+p:
      G.read(~U32, ~Array<U32> & Bool, a, row, a2 => v =>
        free_next(a2, U32.is_zero((v .&. bits : U32)), b => free_rows(p, b, U32.inc(row), bits)))

def mark(f: Nat, a: Array<U32>, +row: U32, +bits: U32) -> Array<U32>:
  match f:
    case 0n: a
    case 1n+p:
      G.read(~U32, ~Array<U32>, a, row, a2 => v =>
        mark(p, Array.set(U32, a2, row, (v .|. bits : U32)), U32.inc(row), bits))

# mode 1 searches only columns in a fixed row; mode 2 only rows in a column.
# mode 3 wraps columns and searches rows. Every read is preceded by bounds checks.
def find_finish(a: Array<U32>, +c: U32, +r: U32, clear: Bool,
    rest: Array<U32> -> Array<U32> & Found) -> Array<U32> & Found:
  match clear:
    case True{}: (a, Found{c, r, True{}})
    case False{}: rest(a)

def free_result(pair: Array<U32> & Bool, c: U32, r: U32,
    rest: Array<U32> -> Array<U32> & Found) -> Array<U32> & Found:
  (a, clear) = pair
  find_finish(a, c, r, clear, rest)

def find_step(a: Array<U32>, +c: U32, +r: U32, +cs: U32, +rs: U32,
    +columns: U32, +mode: U32, valid: Bool, wrap: Bool,
    rest: Array<U32> -> U32 -> U32 -> Array<U32> & Found) -> Array<U32> & Found:
  match valid wrap:
    case False{} _: (a, Found{0, 0, False{}})
    case True{} True{}: rest(a, 0, U32.inc(r))
    case True{} False{}:
      +next_c = Bool.pick(U32, U32.is_eq(mode, 2), c, U32.inc(c))
      +next_r = Bool.pick(U32, U32.is_eq(mode, 2), U32.inc(r), r)
      free_result(free_rows(U32.to_nat(rs), a, r, mask(c, cs)), c, r, b => rest(b, next_c, next_r))

def find(f: Nat, a: Array<U32>, +c: U32, +r: U32, +cs: U32, +rs: U32,
    +columns: U32, +mode: U32) -> Array<U32> & Found:
  match f:
    case 0n: (a, Found{0, 0, False{}})
    case 1n+p:
      +wrap = Bool.and(U32.is_eq(mode, 3), U32.is_gt(U32.add(c, cs), columns))
      +valid = Bool.and(U32.is_le(U32.add(r, rs), 128),
        Bool.or(wrap, U32.is_le(U32.add(c, cs), 32)))
      find_step(a, c, r, cs, rs, columns, mode, valid, wrap,
        b => x => y => find(p, b, x, y, cs, rs, columns, mode))

def locked_start(f: Nat, a: Array<U32>, +r: U32, +value: U32) -> Array<U32> & U32:
  match f:
    case 0n: (a, value)
    case 1n+p:
      G.read(~U32, ~Array<U32> & U32, a, r, b => v => locked_start(p, b, U32.inc(r), U32.max(v, value)))

def locked_mark(f: Nat, a: Array<U32>, +r: U32, +value: U32) -> Array<U32>:
  match f:
    case 0n: a
    case 1n+p:
      locked_mark(p, Array.set(U32, a, r, value), U32.inc(r), value)

def commit(w: Work, index: U32, +cs: U32, +rs: U32, +phase: U32, found: Found) -> Work:
  match w found:
    case Work{a, lock, pos, +nc, +nr, cc, cr, err} Found{+c, +r, True{}}:
      +end_c = U32.add(c, cs)
      +end_r = U32.add(r, rs)
      a2 = mark(U32.to_nat(rs), a, r, mask(c, cs))
      lock2 = locked_mark(Bool.pick(Nat, U32.is_eq(phase, 1), 1n, 0n), lock, r, end_c)
      pos2 = Array.set(G.Place, pos, index, G.Place{c, r, cs, rs})
      +move = U32.is_eq(phase, 2)
      Work{a2, lock2, pos2, U32.max(nc, end_c), U32.max(nr, end_r),
        Bool.pick(U32, move, c, cc), Bool.pick(U32, move, r, cr), err}
    case Work{a, lock, pos, nc, nr, cc, cr, err} Found{c, r, False{}}:
      Work{a, lock, pos, nc, nr, cc, cr, U32.inc(err)}

def found_result(pair: Array<U32> & Found, lock: Array<U32>, pos: Array<G.Place>,
    nc: U32, nr: U32, cc: U32, cr: U32, err: U32, index: U32, cs: U32, rs: U32, phase: U32) -> Work:
  (a, found) = pair
  commit(Work{a, lock, pos, nc, nr, cc, cr, err}, index, cs, rs, phase, found)

def start_result(pair: Array<U32> & U32, a: Array<U32>, pos: Array<G.Place>,
    +nc: U32, nr: U32, +cc: U32, +cr: U32, err: U32, index: U32,
    +cs: U32, +rs: U32, +phase: U32, +mode: U32, +c: U32, +r: U32, advance: Bool) -> Work:
  (lock, start) = pair
  +actual_c = Bool.pick(U32, U32.is_eq(phase, 1), start, c)
  +actual_r = Bool.pick(U32, advance, U32.inc(r), r)
  found_result(find(4256n, a, actual_c, actual_r, cs, rs, nc, mode),
    lock, pos, nc, nr, cc, cr, err, index, cs, rs, phase)

def place(w: Work, +index: U32, item: G.Item, +phase: U32, +dense: Bool) -> Work:
  match w item:
    case Work{a, lock, pos, +nc, nr, +cc, +cr, err} G.Item{id, +col, +row, +cs, +rs}:
      +r = Bool.pick(U32, U32.is_zero(row), Bool.pick(U32, dense, 0, cr), U32.sub(row, 1))
      +c = Bool.pick(U32, U32.is_zero(col), Bool.pick(U32, dense, 0, cc), U32.sub(col, 1))
      +mode = Bool.pick(U32, U32.is_eq(phase, 1), 1,
        Bool.pick(U32, U32.is_zero(col), 3, 2))
      +advance = Bool.and(Bool.and(U32.is_eq(phase, 2), Bool.not(dense)),
        Bool.and(U32.is_ne(col, 0), U32.is_lt(c, cc)))
      start_result(locked_start(Bool.pick(Nat, Bool.and(U32.is_eq(phase, 1), Bool.not(dense)), 1n, 0n), lock, r, 0),
        a, pos, nc, nr, cc, cr, err, index, cs, rs, phase, mode, c, r, advance)

def definite(w: Work, index: U32, item: G.Item) -> Work:
  match item:
    case G.Item{id, col, row, cs, rs}:
      commit(w, index, cs, rs, 0, Found{U32.sub(col, 1), U32.sub(row, 1), True{}})

def pass_item(w: Work, index: U32, item: G.Item, +phase: U32, dense: Bool, selected: Bool, fixed: Bool) -> Work:
  match selected fixed:
    case False{} _: w
    case True{} True{}: definite(w, index, item)
    case True{} False{}: place(w, index, item, phase, dense)

def select(w: Work, index: U32, +item: G.Item, +phase: U32, dense: Bool) -> Work:
  match item:
    case G.Item{id, +col, +row, cs, rs}:
      +selected = Bool.pick(Bool, U32.is_eq(phase, 0), Bool.and(U32.is_ne(col, 0), U32.is_ne(row, 0)),
        Bool.pick(Bool, U32.is_eq(phase, 1), Bool.and(U32.is_zero(col), U32.is_ne(row, 0)), U32.is_zero(row)))
      pass_item(w, index, item, phase, dense, selected, U32.is_zero(phase))

def pass(xs: List<&2, G.Node>, w: Work, +index: U32, +phase: U32, +dense: Bool) -> Work:
  match xs:
    case Nil{}: w
    case head <> tail:
      pass(tail, select(w, index, G.item(head), phase, dense), U32.inc(index), phase, dense)

def item_width(item: G.Item, nc: U32) -> U32:
  match item:
    case G.Item{id, +col, row, +cs, rs}:
      U32.max(nc, Bool.pick(U32, U32.is_zero(col), cs, U32.add(U32.sub(col, 1), cs)))

def width(xs: List<&2, G.Node>, +nc: U32) -> U32:
  match xs:
    case Nil{}: nc
    case head <> tail:
      width(tail, item_width(G.item(head), nc))

def run(+xs: List<&2, G.Node>, nc: U32, nr: U32, +dense: Bool) -> Work:
  w: Work = Work{Array.new(U32, 7n, 0), Array.new(U32, 7n, 0),
    Array.new(G.Place, 8n, G.Place{0, 0, 1, 1}), width(xs, nc), nr, 0, 0, 0}
  pass(xs, pass(xs, pass(xs, w, 0, 0, dense), 0, 1, dense), 0, 2, dense)
