import Base
import ./contract.bend as G
import ./placement.bend as P
import ./tracks.bend as T

# Parent placement/sizing produces child jobs before recursive layout starts.
type Job is Data:
  Job{node: G.Node, box: G.Box}

type Prepared is Data:
  Prepared{box: G.Box, jobs: List<&2, Job>, errors: U32}

type Forest is Data:
  Forest{trees: List<&2, G.Tree>, errors: U32}

type Render is Type:
  Render{places: Array<G.Place>, x: Array<F32>, y: Array<F32>, jobs: List<&2, Job>}

def child_box(item: G.Item, x: F32, y: F32, w: F32, h: F32) -> G.Box:
  match item:
    case G.Item{id, c, r, cs, rs}: G.Box{id, x, y, w, h}

def join_job(job: Job, rendered: Render) -> Render:
  match rendered:
    case Render{p, x, y, jobs}: Render{p, x, y, job <> jobs}

def rectangle(p: Array<G.Place>, x: Array<F32>, y: Array<F32>, +head: G.Node,
    place: G.Place, parent: G.Box, cg: F32, rg: F32,
    rest: Array<G.Place> -> Array<F32> -> Array<F32> -> Render) -> Render:
  match place parent:
    case G.Place{+c, +r, cs, rs} G.Box{id, px, py, pw, ph}:
      G.read(~F32, ~Render, x, c, xx => +x0 =>
        G.read(~F32, ~Render, xx, U32.add(c, cs), xx2 => x1 =>
          G.read(~F32, ~Render, y, r, yy => +y0 =>
            G.read(~F32, ~Render, yy, U32.add(r, rs), yy2 => y1 =>
              join_job(Job{head, child_box(G.item(head), F32.add(px, x0), F32.add(py, y0),
                F32.max(0.0, F32.sub(F32.sub(x1, x0), cg)), F32.max(0.0, F32.sub(F32.sub(y1, y0), rg)))}, rest(p, xx2, yy2))))))

def children(xs: List<&2, G.Node>, p: Array<G.Place>, x: Array<F32>, y: Array<F32>,
    +index: U32, +parent: G.Box, +cg: F32, +rg: F32) -> Render:
  match xs:
    case Nil{}: Render{p, x, y, Nil{}}
    case head <> tail:
      G.read(~G.Place, ~Render, p, index, pp => place => rectangle(pp, x, y, head, place, parent, cg, rg,
        p2 => x2 => y2 => children(tail, p2, x2, y2, U32.inc(index), parent, cg, rg)))

def finish(parent: G.Box, r: Render) -> Prepared:
  match r:
    case Render{p, x, y, jobs}: Prepared{parent, jobs, 0}

def failed(parent: G.Box, w: P.Work) -> Prepared:
  match w:
    case P.Work{a, lock, p, nc, nr, cc, cr, errors}: Prepared{parent, Nil{}, errors}

def placed_good(parent: G.Box, xs: List<&2, G.Node>, style: G.Style, w: P.Work) -> Prepared:
  match parent style w:
    case G.Box{id, px, py, +pw, +ph}
      G.Style{cols, rows, ac, ar, +cg, +rg, dense, nc0, nr0}
      P.Work{a, lock, p, nc, nr, cc, cr, errors}:
      +box: G.Box = G.Box{id, px, py, pw, ph}
      x = T.run(cols, ac, nc, pw, cg)
      y = T.run(rows, ar, nr, ph, rg)
      finish(box, children(xs, p, x, y, 0, box, cg, rg))

def placed_choice(parent: G.Box, xs: List<&2, G.Node>, style: G.Style, w: P.Work, ok: Bool) -> Prepared:
  match ok:
    case False{}: failed(parent, w)
    case True{}: placed_good(parent, xs, style, w)

def placed(parent: G.Box, xs: List<&2, G.Node>, style: G.Style, w: P.Work) -> Prepared:
  match w:
    case P.Work{a, lock, p, nc, nr, cc, cr, +errors}:
      placed_choice(parent, xs, style, P.Work{a, lock, p, nc, nr, cc, cr, errors}, U32.is_zero(errors))

def prepare(node: G.Node, box: G.Box) -> Prepared:
  match node:
    case G.Leaf{i}: Prepared{box, Nil{}, 0}
    case G.Grid{i, +style, +xs}:
      match style:
        case G.Style{cols, rows, ac, ar, cg, rg, dense, nc, nr}:
          placed(box, xs, style, P.run(xs, nc, nr, dense))

def join_tree(box: G.Box, err: U32, a: Forest, b: Forest) -> Forest:
  match a b:
    case Forest{trees, +ae} Forest{rest, be}:
      +total = U32.add(err, ae)
      Forest{G.Tree{box, trees, total} <> rest, U32.add(total, be)}

def prepared(p: Prepared, rest: Prepared -> Forest) -> Forest:
  rest(p)

# Both calls decrease fuel. Siblings and child subtrees can run independently.
# 2050 is above the maximum number of input nodes, including the root.
def forest_step(plan: Prepared, left: List<&2, Job> -> Forest, right: Unit -> Forest) -> Forest:
  match plan:
    case Prepared{box, jobs, errors}:
      a b = left(jobs) right(Unit{})
      join_tree(box, errors, a, b)

def forest(+f: Nat, xs: List<&2, Job>) -> Forest:
  match f xs:
    case 0n _: Forest{Nil{}, 1}
    case 1n+p Nil{}: Forest{Nil{}, 0}
    case 1n+p Job{node, box} <> tail:
      prepared(prepare(node, box), plan => forest_step(plan,
        jobs => forest(p, jobs), u => forest(p, tail)))

def first(r: Forest, fallback: G.Box) -> G.Tree:
  match r:
    case Forest{Nil{}, errors}: G.Tree{fallback, Nil{}, errors}
    case Forest{head <> tail, errors}: head

def layout(f: Nat, node: G.Node, +box: G.Box) -> G.Tree:
  first(forest(f, Job{node, box} <> Nil{}), box)

def box_show(box: G.Box) -> String:
  match box:
    case G.Box{id, x, y, w, h}:
      "box=" ++ U32.show(id) ++ "," ++ F32.show(x) ++ "," ++ F32.show(y) ++ "," ++ F32.show(w) ++ "," ++ F32.show(h) ++ "\n"

def show_walk(f: Nat, xs: List<&2, G.Tree>) -> String:
  match f xs:
    case 0n _: ""
    case 1n+p Nil{}: ""
    case 1n+p G.Tree{box, children, errors} <> tail:
      box_show(box) ++ show_walk(p, List.append(&2, G.Tree, children, tail))

def show(fuel: Nat, +tree: G.Tree) -> String:
  match tree:
    case G.Tree{box, xs, errors}: show_walk(2050n, tree <> Nil{}) ++ "errors=" ++ U32.show(errors)

def add(a: G.Stats, b: G.Stats) -> G.Stats:
  match a b:
    case G.Stats{ac, an, ae} G.Stats{bc, bn, be}: G.Stats{U32.add(ac, bc), U32.add(an, bn), U32.add(ae, be)}

def quantize(x: F32) -> U32:
  F32.to_u32(F32.min(4294967040.0, F32.max(0.0, F32.mul(x, 16.0))))

def box_hash(box: G.Box) -> U32:
  match box:
    case G.Box{id, x, y, w, h}:
      U32.mul(U32.inc(id), U32.add(U32.add(quantize(x), U32.mul(3, quantize(y))),
        U32.add(U32.mul(5, quantize(w)), U32.mul(7, quantize(h)))))

def inspect_walk(f: Nat, xs: List<&2, G.Tree>, checksum: U32, nodes: U32, errors: U32) -> G.Stats:
  match f xs:
    case 0n _: G.Stats{checksum, nodes, U32.inc(errors)}
    case 1n+p Nil{}: G.Stats{checksum, nodes, errors}
    case 1n+p G.Tree{box, children, ignored} <> tail:
      inspect_walk(p, List.append(&2, G.Tree, children, tail), U32.add(checksum, box_hash(box)), U32.inc(nodes), errors)

def inspect(fuel: Nat, +tree: G.Tree) -> G.Stats:
  match tree:
    case G.Tree{box, children, errors}: inspect_walk(2050n, tree <> Nil{}, 0, 0, errors)

def stats_show(s: G.Stats) -> String:
  match s:
    case G.Stats{checksum, nodes, errors}:
      "checksum=" ++ U32.show(checksum) ++ " nodes=" ++ U32.show(nodes) ++ " errors=" ++ U32.show(errors)
