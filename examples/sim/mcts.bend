import Base
import ./ttt.bend as T
# Monte Carlo search: MCTS (UCT) for tic-tac-toe, with root parallelization.
# A player grows 2^dep independent trees of iters() iterations each from the
# position, sums the visit counts of the root's children over the trees
# and plays the most visited cell (the lowest on a tie). The trees are the
# leaves of a fork tree and their 9 visit counts merge in O(1); one tree
# grows sequentially, rebuilding the nodes on its path every iteration.
#
# One iteration takes, at each node, the lowest untried legal cell if there
# is one (it expands it and plays one random playout from it), else the
# child of highest UCT value w / (2 n) + 1.4 sqrt(ln N / n); then it adds
# each node's score (win 2, draw 1, loss 0 for the side that moved into it)
# along the path. A def cannot match a value it computes and defs cannot
# call each other, so the caller of descend splits the node it descends to
# at the cell chosen there (Tr.split) and passes the split node down: each
# child then moves once, and only the path's nodes are rebuilt.
#
# Prints the summed root visits of the empty board, then 2^games games
# against a uniformly random player (X in the even games, O in the odd
# ones), as fmc.bend does. examples/sim/mcts.c runs the same arithmetic (its
# first two lines match) and also checks the player against exact minimax.
# Knobs: dep() (trees per move), iters(), games().

def dep() -> Nat:
  4n

# at most 32767: a child's visits and score are packed in one word (Tr.nw)
def iters() -> Nat:
  576n

def games() -> Nat:
  8n

# a node: the score of the side that moved into it, its visits, and a
# child per cell (E{} until tried)
type Tr is Data:
  E{}
  N{w: U32, n: U32, c0: Tr, c1: Tr, c2: Tr, c3: Tr, c4: Tr, c5: Tr, c6: Tr, c7: Tr, c8: Tr}

# a rebuilt node, the status its playout ended in, and the rng state
type Res is Data:
  Res{t: Tr, st: U32, s: U32}

# the choice at a node so far: the lowest untried legal cell, the best
# tried one and its UCT value (9 for none)
type Ch is Data:
  Ch{e: U32, b: U32, v: F32}

# a node split at the cell k chosen there: its child there taken out as
# kid (E{} left in its slot), and ex: whether k is an untried cell
type Z is Data:
  Z{w: U32, n: U32, k: U32, ex: Bool, kid: Tr, c0: Tr, c1: Tr, c2: Tr, c3: Tr, c4: Tr, c5: Tr, c6: Tr, c7: Tr, c8: Tr}

def Tr.n(t: Tr) -> U32:
  match t:
    case E{}:
      0
    case N{w, n, c0, c1, c2, c3, c4, c5, c6, c7, c8}:
      n

# n << 16 | w in one word (n <= 2^15 and w <= 2 n here); 0 for an untried cell
def Tr.nw(t: Tr) -> U32:
  match t:
    case E{}:
      0
    case N{w, n, c0, c1, c2, c3, c4, c5, c6, c7, c8}:
      ((n << 16n) .|. w : U32)

def Tr.fresh(+w: U32) -> Tr:
  N{w, 1, E{}, E{}, E{}, E{}, E{}, E{}, E{}, E{}, E{}}

def Tr.visits(t: Tr) -> T.R9:
  match t:
    case E{}:
      T.R9{0, 0, 0, 0, 0, 0, 0, 0, 0}
    case N{w, n, c0, c1, c2, c3, c4, c5, c6, c7, c8}:
      T.R9{Tr.n(c0), Tr.n(c1), Tr.n(c2), Tr.n(c3), Tr.n(c4), Tr.n(c5), Tr.n(c6), Tr.n(c7), Tr.n(c8)}

# the UCT value of a tried legal child (packed as nw), 0.0 for any other:
# computed only when it can be used, as the C twin does
def uct(+nw: U32, +ln: F32, used: Bool) -> F32:
  match used:
    case False{}:
      0.0
    case True{}:
      +n = U32.to_f32((nw >> 16n : U32))
      (U32.to_f32((nw .&. 65535 : U32)) / (2.0 * n) + 1.4 * F32.sqrt((ln / n : F32)) : F32)

def legal(+occ: U32, +i: U32) -> Bool:
  U32.is_zero((occ .&. U32.shln(1, U32.to_nat(i)) : U32))

# fold cell i, whose child is c, into the choice so far
def Ch.step(ch: Ch, +i: U32, c: Tr, +occ: U32, +ln: F32) -> Ch:
  match ch:
    case Ch{+e, +b, +v}:
      +nw = Tr.nw(c)
      +ok = legal(occ, i)
      +tried = Bool.and(ok, U32.is_ne(nw, 0))
      +u = uct(nw, ln, tried)
      +better = Bool.and(tried, Bool.or(U32.is_eq(b, 9), F32.is_gt(u, v)))
      Ch{Bool.pick(U32, Bool.and(U32.is_eq(e, 9), Bool.and(ok, U32.is_zero(nw))), i, e),
         Bool.pick(U32, better, i, b), Bool.pick(F32, better, u, v)}

def Ch.end(ch: Ch) -> U32:
  match ch:
    case Ch{+e, b, v}:
      Bool.pick(U32, U32.is_ne(e, 9), (e .|. 16 : U32), b)

# the cell to take at a node of n visits and children c0..c8: the lowest
# untried legal cell with 16 added, else the legal child of highest UCT value
def choose(+n: U32, c0: Tr, c1: Tr, c2: Tr, c3: Tr, c4: Tr, c5: Tr, c6: Tr, c7: Tr, c8: Tr, +x: U32, +o: U32) -> U32:
  +occ = (x .|. o : U32)
  +ln = F32.log(U32.to_f32(n))
  Ch.end(Ch.step(Ch.step(Ch.step(Ch.step(Ch.step(Ch.step(Ch.step(Ch.step(Ch.step(
    Ch{9, 9, 0.0}, 0, c0, occ, ln), 1, c1, occ, ln), 2, c2, occ, ln), 3, c3, occ, ln),
    4, c4, occ, ln), 5, c5, occ, ln), 6, c6, occ, ln), 7, c7, occ, ln), 8, c8, occ, ln))

def Z.make(k: U32, ex: Bool, +w: U32, +n: U32, c0: Tr, c1: Tr, c2: Tr, c3: Tr, c4: Tr, c5: Tr, c6: Tr, c7: Tr, c8: Tr) -> Z:
  match k:
    case 0:
      Z{w, n, k, ex, c0, E{}, c1, c2, c3, c4, c5, c6, c7, c8}
    case 1:
      Z{w, n, k, ex, c1, c0, E{}, c2, c3, c4, c5, c6, c7, c8}
    case 2:
      Z{w, n, k, ex, c2, c0, c1, E{}, c3, c4, c5, c6, c7, c8}
    case 3:
      Z{w, n, k, ex, c3, c0, c1, c2, E{}, c4, c5, c6, c7, c8}
    case 4:
      Z{w, n, k, ex, c4, c0, c1, c2, c3, E{}, c5, c6, c7, c8}
    case 5:
      Z{w, n, k, ex, c5, c0, c1, c2, c3, c4, E{}, c6, c7, c8}
    case 6:
      Z{w, n, k, ex, c6, c0, c1, c2, c3, c4, c5, E{}, c7, c8}
    case 7:
      Z{w, n, k, ex, c7, c0, c1, c2, c3, c4, c5, c6, E{}, c8}
    case _:
      Z{w, n, k, ex, c8, c0, c1, c2, c3, c4, c5, c6, c7, E{}}

# split node t (side to move at x, o) at the cell chosen there
def Tr.split(t: Tr, +x: U32, +o: U32) -> Z:
  match t:
    case E{}:
      Z{0, 0, 0, False{}, E{}, E{}, E{}, E{}, E{}, E{}, E{}, E{}, E{}, E{}}
    case N{+w, +n, +c0, +c1, +c2, +c3, +c4, +c5, +c6, +c7, +c8}:
      +ch = choose(n, c0, c1, c2, c3, c4, c5, c6, c7, c8, x, o)
      Z.make((ch .&. 15 : U32), U32.is_ge(ch, 16), w, n, c0, c1, c2, c3, c4, c5, c6, c7, c8)

# the node, with child k replaced and this iteration's score added
def rebuild(k: U32, +w: U32, +n: U32, c0: Tr, c1: Tr, c2: Tr, c3: Tr, c4: Tr, c5: Tr, c6: Tr, c7: Tr, c8: Tr, +t: U32, r: Res) -> Res:
  match k r:
    case 0 Res{tc, +st, s}:
      Res{N{(w + T.score(U32.xor(t, 1), st) : U32), U32.inc(n), tc, c1, c2, c3, c4, c5, c6, c7, c8}, st, s}
    case 1 Res{tc, +st, s}:
      Res{N{(w + T.score(U32.xor(t, 1), st) : U32), U32.inc(n), c0, tc, c2, c3, c4, c5, c6, c7, c8}, st, s}
    case 2 Res{tc, +st, s}:
      Res{N{(w + T.score(U32.xor(t, 1), st) : U32), U32.inc(n), c0, c1, tc, c3, c4, c5, c6, c7, c8}, st, s}
    case 3 Res{tc, +st, s}:
      Res{N{(w + T.score(U32.xor(t, 1), st) : U32), U32.inc(n), c0, c1, c2, tc, c4, c5, c6, c7, c8}, st, s}
    case 4 Res{tc, +st, s}:
      Res{N{(w + T.score(U32.xor(t, 1), st) : U32), U32.inc(n), c0, c1, c2, c3, tc, c5, c6, c7, c8}, st, s}
    case 5 Res{tc, +st, s}:
      Res{N{(w + T.score(U32.xor(t, 1), st) : U32), U32.inc(n), c0, c1, c2, c3, c4, tc, c6, c7, c8}, st, s}
    case 6 Res{tc, +st, s}:
      Res{N{(w + T.score(U32.xor(t, 1), st) : U32), U32.inc(n), c0, c1, c2, c3, c4, c5, tc, c7, c8}, st, s}
    case 7 Res{tc, +st, s}:
      Res{N{(w + T.score(U32.xor(t, 1), st) : U32), U32.inc(n), c0, c1, c2, c3, c4, c5, c6, tc, c8}, st, s}
    case _ Res{tc, +st, s}:
      Res{N{(w + T.score(U32.xor(t, 1), st) : U32), U32.inc(n), c0, c1, c2, c3, c4, c5, c6, c7, tc}, st, s}

# one iteration below the node split in z (side t to move): live says the
# position is not over
def descend(f: Nat, z: Z, +x: U32, +o: U32, +t: U32, +s: U32, live: Bool) -> Res:
  match f z live:
    case 0n _ _:
      Res{E{}, 1, s}
    case 1n+p Z{+w, +n, +k, ex, kid, c0, c1, c2, c3, c4, c5, c6, c7, c8} False{}:
      rebuild(k, w, n, c0, c1, c2, c3, c4, c5, c6, c7, c8, t, Res{kid, T.status(x, o), s})
    case 1n+p Z{+w, +n, +k, True{}, kid, c0, c1, c2, c3, c4, c5, c6, c7, c8} True{}:
      +bit = U32.shln(1, U32.to_nat(k))
      +nx = Bool.pick(U32, U32.is_eq(t, 0), (x .|. bit : U32), x)
      +no = Bool.pick(U32, U32.is_eq(t, 1), (o .|. bit : U32), o)
      +s1 = T.prng(s)
      +st = T.playout(9n, nx, no, U32.xor(t, 1), T.mix(s1, 1), U32.is_eq(T.status(nx, no), 3))
      rebuild(k, w, n, c0, c1, c2, c3, c4, c5, c6, c7, c8, t, Res{Tr.fresh(T.score(t, st)), st, s1})
    case 1n+p Z{+w, +n, +k, False{}, kid, c0, c1, c2, c3, c4, c5, c6, c7, c8} True{}:
      +bit = U32.shln(1, U32.to_nat(k))
      +nx = Bool.pick(U32, U32.is_eq(t, 0), (x .|. bit : U32), x)
      +no = Bool.pick(U32, U32.is_eq(t, 1), (o .|. bit : U32), o)
      rebuild(k, w, n, c0, c1, c2, c3, c4, c5, c6, c7, c8, t,
        descend(p, Tr.split(kid, nx, no), nx, no, U32.xor(t, 1), s, U32.is_eq(T.status(nx, no), 3)))

# f more iterations of the tree in r, from a position that is not over
def grow(f: Nat, r: Res, +x: U32, +o: U32, +t: U32) -> Tr:
  match f r:
    case 0n Res{tr, st, s}:
      tr
    case 1n+p Res{tr, st, +s}:
      grow(p, descend(10n, Tr.split(tr, x, o), x, o, t, s, True{}), x, o, t)

# the summed root visits of 2^d trees; tree r uses seed mix(salt + r, 77)
def forest(+d: Nat, +x: U32, +o: U32, +t: U32, +salt: U32, +r: U32) -> T.R9:
  match d:
    case 0n:
      Tr.visits(grow(iters(), Res{N{0, 0, E{}, E{}, E{}, E{}, E{}, E{}, E{}, E{}, E{}}, 1,
        T.mix((salt + r : U32), 77)}, x, o, t))
    case 1n+p:
      a b = forest(p, x, o, t, salt, r) forest(p, x, o, t, salt, U32.add(r, U32.shln(1, p)))
      T.R9.add(a, b)

# the tree player's move
def best(+x: U32, +o: U32, +t: U32, +salt: U32) -> U32:
  T.argmax(forest(dep(), x, o, t, salt, 0), (x .|. o : U32))

# the next move of game g at its turn: the tree player's or a random one
def game.move(+x: U32, +o: U32, +t: U32, +s: U32, +g: U32, +turn: U32, live: Bool, mine: Bool) -> T.Mv:
  match live mine:
    case False{} _:
      T.Mv{0, s}
    case True{} True{}:
      T.Mv{best(x, o, t, ((g * 64) + (turn * 4096) : U32)), s}
    case True{} False{}:
      +s1 = T.prng(s)
      T.Mv{T.cell(x, o, s1), s1}

# play the move mv of side t, then pick the next one; the final status
def game.go(f: Nat, +x: U32, +o: U32, +t: U32, +g: U32, +turn: U32, mv: T.Mv) -> U32:
  match f mv:
    case 0n _:
      T.status(x, o)
    case 1n+p T.Mv{+c, +s}:
      +nx = Bool.pick(U32, U32.is_eq(t, 0), (x .|. c : U32), x)
      +no = Bool.pick(U32, U32.is_eq(t, 1), (o .|. c : U32), o)
      +t1 = U32.xor(t, 1)
      +n1 = U32.inc(turn)
      game.go(p, nx, no, t1, g, n1,
        game.move(nx, no, t1, s, g, n1, U32.is_eq(T.status(nx, no), 3), U32.is_eq(t1, (g .&. 1 : U32))))

def game(+g: U32) -> T.T6:
  T.T6.of(g, game.go(9n, 0, 0, 0, g, 0, game.move(0, 0, 0, T.mix(g, 99), g, 0, True{}, U32.is_eq((g .&. 1 : U32), 0))))

def games.tree(+d: Nat, +g: U32) -> T.T6:
  match d:
    case 0n:
      game(g)
    case 1n+p:
      a b = games.tree(p, g) games.tree(p, U32.add(g, U32.shln(1, p)))
      T.T6.add(a, b)

def main() -> IO(Unit):
  IO.print(T.R9.show(forest(dep(), 0, 0, 0, 0, 0)) ++ "\n" ++ T.T6.show(games.tree(games(), 0)))
