import Base
import ./ttt.bend as T
# Monte Carlo search: MCTS (UCT) for Connect Four, root parallelization
# against one deep tree at the same budget.
# A player grows 2^d independent trees of k iterations each (the leaves of
# a fork tree) and plays the column most visited over all of them, the
# lowest on a tie. One iteration is mcts.bend's: expand the lowest untried
# column, else take the child of highest UCT value, play one random
# playout, add the scores along the path. Prints the summed root visits of
# the empty board for 2^dep() x iters(), then, for each width 2^w of 1, 4,
# 16 and 64, 2^games() games of 2^w trees x budget() / 2^w iterations
# against 1 tree x budget() (the wide player is X in the even games). The
# games of a match are the leaves of another fork tree.
#
# A board is five words: the stones of X and of O in rows 0-3 (bit r*7+c)
# and rows 4-5 (bit (r-4)*7+c), and the 7 column heights, 3 bits each. A
# win is checked around the stone just dropped. examples/sim/c4.c runs the
# same arithmetic, so the output matches it.

def dep() -> Nat:
  4n

# at most 32767 here and in budget(): a child's visits and score share a word
def iters() -> Nat:
  256n

def budget() -> U32:
  1024

def games() -> Nat:
  6n

# root visits per column
type R7 is Data:
  R7{r0: U32, r1: U32, r2: U32, r3: U32, r4: U32, r5: U32, r6: U32}

def R7.add(a: R7, b: R7) -> R7:
  match a b:
    case R7{a0, a1, a2, a3, a4, a5, a6} R7{b0, b1, b2, b3, b4, b5, b6}:
      R7{(a0 + b0 : U32), (a1 + b1 : U32), (a2 + b2 : U32), (a3 + b3 : U32), (a4 + b4 : U32),
         (a5 + b5 : U32), (a6 + b6 : U32)}

def R7.show(r: R7) -> String:
  match r:
    case R7{r0, r1, r2, r3, r4, r5, r6}:
      U32.show(r0) ++ " " ++ U32.show(r1) ++ " " ++ U32.show(r2) ++ " " ++ U32.show(r3) ++ " " ++
      U32.show(r4) ++ " " ++ U32.show(r5) ++ " " ++ U32.show(r6)

# games the wide player won, drew and lost
type W3 is Data:
  W3{won: U32, drawn: U32, lost: U32}

def W3.add(a: W3, b: W3) -> W3:
  match a b:
    case W3{a0, a1, a2} W3{b0, b1, b2}:
      W3{(a0 + b0 : U32), (a1 + b1 : U32), (a2 + b2 : U32)}

# Board
# =====

def height(+h: U32, +c: U32) -> U32:
  ((h >> U32.to_nat((3 * c : U32))) .&. 7 : U32)

def bit(+w: U32, +i: U32) -> U32:
  ((w >> U32.to_nat((i .&. 31 : U32))) .&. 1 : U32)

# is (c, r) a stone in the words lo, hi? 0 off the board (c, r wrap below 0)
def owns(+lo: U32, +hi: U32, +c: U32, +r: U32) -> U32:
  Bool.pick(U32, Bool.and(U32.is_lt(c, 7), U32.is_lt(r, 6)),
    Bool.pick(U32, U32.is_lt(r, 4), bit(lo, (r * 7 + c : U32)), bit(hi, ((r - 4) * 7 + c : U32))), 0)

# stones in a row from (c, r) along (dc, dr), up to 3, not counting (c, r)
def run(+lo: U32, +hi: U32, +c: U32, +r: U32, +dc: U32, +dr: U32) -> U32:
  +s1 = owns(lo, hi, (c + dc : U32), (r + dr : U32))
  +s2 = (s1 .&. owns(lo, hi, (c + 2 * dc : U32), (r + 2 * dr : U32)) : U32)
  +s3 = (s2 .&. owns(lo, hi, (c + 3 * dc : U32), (r + 3 * dr : U32)) : U32)
  (s1 + s2 + s3 : U32)

def line4(+lo: U32, +hi: U32, +c: U32, +r: U32, +dc: U32, +dr: U32) -> Bool:
  U32.is_ge((run(lo, hi, c, r, dc, dr) + run(lo, hi, c, r, (0 - dc : U32), (0 - dr : U32)) : U32), 3)

# does the stone just dropped at (c, r) win for the side whose words are lo, hi?
def wins(+lo: U32, +hi: U32, +c: U32, +r: U32) -> Bool:
  Bool.or(Bool.or(line4(lo, hi, c, r, 1, 0), line4(lo, hi, c, r, 0, 1)),
          Bool.or(line4(lo, hi, c, r, 1, 1), line4(lo, hi, c, r, 1, (0 - 1 : U32))))

# the columns that are not full, as a 7-bit mask
def open(+h: U32) -> U32:
  (Bool.to_u32(U32.is_lt(height(h, 0), 6)) .|. (Bool.to_u32(U32.is_lt(height(h, 1), 6)) << 1n)
    .|. (Bool.to_u32(U32.is_lt(height(h, 2), 6)) << 2n) .|. (Bool.to_u32(U32.is_lt(height(h, 3), 6)) << 3n)
    .|. (Bool.to_u32(U32.is_lt(height(h, 4), 6)) << 4n) .|. (Bool.to_u32(U32.is_lt(height(h, 5), 6)) << 5n)
    .|. (Bool.to_u32(U32.is_lt(height(h, 6), 6)) << 6n) : U32)

# the words lo, hi with a stone at (c, r)
def put.lo(+lo: U32, +c: U32, +r: U32) -> U32:
  Bool.pick(U32, U32.is_lt(r, 4), (lo .|. U32.shln(1, U32.to_nat(((r * 7 + c) .&. 31 : U32))) : U32), lo)

def put.hi(+hi: U32, +c: U32, +r: U32) -> U32:
  Bool.pick(U32, U32.is_lt(r, 4), hi, (hi .|. U32.shln(1, U32.to_nat((((r - 4) * 7 + c) .&. 31 : U32))) : U32))

# the status after side t's stone at (c, r): 0 X won, 1 draw, 2 O won, 3 not over
def after(+lo: U32, +hi: U32, +h: U32, +t: U32, +c: U32, +r: U32) -> U32:
  Bool.pick(U32, wins(lo, hi, c, r), (t * 2 : U32), Bool.pick(U32, U32.is_zero(open(h)), 1, 3))

# a board after side t drops a stone in column c, the status after it, and
# whether the game goes on (a def matches it; it cannot match st)
type Pos is Data:
  Pos{xl: U32, xh: U32, ol: U32, oh: U32, h: U32, st: U32, live: Bool}

def drop(+xl: U32, +xh: U32, +ol: U32, +oh: U32, +h: U32, +t: U32, +c: U32) -> Pos:
  +r = height(h, c)
  +h1 = (h + U32.shln(1, U32.to_nat((3 * c : U32))) : U32)
  +nxl = Bool.pick(U32, U32.is_eq(t, 0), put.lo(xl, c, r), xl)
  +nxh = Bool.pick(U32, U32.is_eq(t, 0), put.hi(xh, c, r), xh)
  +nol = Bool.pick(U32, U32.is_eq(t, 1), put.lo(ol, c, r), ol)
  +noh = Bool.pick(U32, U32.is_eq(t, 1), put.hi(oh, c, r), oh)
  +st = after(Bool.pick(U32, U32.is_eq(t, 0), nxl, nol), Bool.pick(U32, U32.is_eq(t, 0), nxh, noh), h1, t, c, r)
  Pos{nxl, nxh, nol, noh, h1, st, U32.is_eq(st, 3)}

def popcount7(+e: U32) -> U32:
  ((e .&. 1) + ((e >> 1n) .&. 1) + ((e >> 2n) .&. 1) + ((e >> 3n) .&. 1) + ((e >> 4n) .&. 1)
    + ((e >> 5n) .&. 1) + ((e >> 6n) .&. 1) : U32)

def here(+e: U32, +k: U32, +c: U32) -> Bool:
  Bool.and(U32.is_eq(bit(e, c), 1), U32.is_eq(k, 0))

# the k-th (from 0) open column of mask e at or above c; stops at it
def nth(f: Nat, +e: U32, +k: U32, +c: U32, at: Bool) -> U32:
  match f at:
    case 0n _:
      0
    case 1n+p True{}:
      c
    case 1n+p False{}:
      +k1 = (k - bit(e, c) : U32)
      nth(p, e, k1, U32.inc(c), here(e, k1, U32.inc(c)))

# the open column a random player takes with rng state s
def col(+h: U32, +s: U32) -> U32:
  +e = open(h)
  +k = (((s >> 16n) * popcount7(e)) >> 16n : U32)
  nth(7n, e, k, 0, here(e, k, 0))

# random playout to the end from pos, side t to move (42 moves suffice)
def playout(f: Nat, pos: Pos, +t: U32, +s: U32) -> U32:
  match f pos:
    case 0n Pos{xl, xh, ol, oh, h, st, live}:
      st
    case 1n+p Pos{xl, xh, ol, oh, h, st, False{}}:
      st
    case 1n+p Pos{+xl, +xh, +ol, +oh, +h, st, True{}}:
      +s1 = T.prng(s)
      playout(p, drop(xl, xh, ol, oh, h, t, col(h, s1)), U32.xor(t, 1), s1)

# Tree
# ====

# a node: the score of the side that moved into it, its visits, the status
# after that move, and a child per column (E{} until tried)
type Tr is Data:
  E{}
  N{w: U32, n: U32, st: U32, c0: Tr, c1: Tr, c2: Tr, c3: Tr, c4: Tr, c5: Tr, c6: Tr}

# a rebuilt node, the status its playout ended in, and the rng state
type Res is Data:
  Res{t: Tr, st: U32, s: U32}

# a node split at the column k chosen there: its child there taken out as
# kid (E{} left in its slot); ex: whether k is untried; live: whether the
# node's own position goes on
type Z is Data:
  Z{w: U32, n: U32, st: U32, k: U32, ex: Bool, live: Bool, kid: Tr,
    c0: Tr, c1: Tr, c2: Tr, c3: Tr, c4: Tr, c5: Tr, c6: Tr}

# the choice at a node so far: the lowest untried open column, the best
# tried one and its UCT value (7 for none)
type Ch is Data:
  Ch{e: U32, b: U32, v: F32}

def Tr.n(t: Tr) -> U32:
  match t:
    case E{}:
      0
    case N{w, n, st, c0, c1, c2, c3, c4, c5, c6}:
      n

# n << 16 | w in one word; 0 for an untried column
def Tr.nw(t: Tr) -> U32:
  match t:
    case E{}:
      0
    case N{w, n, st, c0, c1, c2, c3, c4, c5, c6}:
      ((n << 16n) .|. w : U32)

def Tr.fresh(+w: U32, +st: U32) -> Tr:
  N{w, 1, st, E{}, E{}, E{}, E{}, E{}, E{}, E{}}

def Tr.visits(t: Tr) -> R7:
  match t:
    case E{}:
      R7{0, 0, 0, 0, 0, 0, 0}
    case N{w, n, st, c0, c1, c2, c3, c4, c5, c6}:
      R7{Tr.n(c0), Tr.n(c1), Tr.n(c2), Tr.n(c3), Tr.n(c4), Tr.n(c5), Tr.n(c6)}

# the UCT value of a tried open child (packed as nw); 0.0 for any other
def uct(+nw: U32, +ln: F32, used: Bool) -> F32:
  match used:
    case False{}:
      0.0
    case True{}:
      +n = U32.to_f32((nw >> 16n : U32))
      (U32.to_f32((nw .&. 65535 : U32)) / (2.0 * n) + 1.4 * F32.sqrt((ln / n : F32)) : F32)

# fold column i, whose child is c, into the choice so far
def Ch.step(ch: Ch, +i: U32, c: Tr, +open: U32, +ln: F32) -> Ch:
  match ch:
    case Ch{+e, +b, +v}:
      +nw = Tr.nw(c)
      +ok = U32.is_eq(bit(open, i), 1)
      +tried = Bool.and(ok, U32.is_ne(nw, 0))
      +u = uct(nw, ln, tried)
      +better = Bool.and(tried, Bool.or(U32.is_eq(b, 7), F32.is_gt(u, v)))
      Ch{Bool.pick(U32, Bool.and(U32.is_eq(e, 7), Bool.and(ok, U32.is_zero(nw))), i, e),
         Bool.pick(U32, better, i, b), Bool.pick(F32, better, u, v)}

def Ch.end(ch: Ch) -> U32:
  match ch:
    case Ch{+e, b, v}:
      Bool.pick(U32, U32.is_ne(e, 7), (e .|. 16 : U32), b)

# the column to take at a node of n visits: the lowest untried open one
# with 16 added, else the open child of highest UCT value
def choose(+n: U32, c0: Tr, c1: Tr, c2: Tr, c3: Tr, c4: Tr, c5: Tr, c6: Tr, +h: U32) -> U32:
  +op = open(h)
  +ln = F32.log(U32.to_f32(n))
  Ch.end(Ch.step(Ch.step(Ch.step(Ch.step(Ch.step(Ch.step(Ch.step(
    Ch{7, 7, 0.0}, 0, c0, op, ln), 1, c1, op, ln), 2, c2, op, ln), 3, c3, op, ln),
    4, c4, op, ln), 5, c5, op, ln), 6, c6, op, ln))

def Z.make(k: U32, ex: Bool, +w: U32, +n: U32, +st: U32, c0: Tr, c1: Tr, c2: Tr, c3: Tr, c4: Tr, c5: Tr, c6: Tr) -> Z:
  match k:
    case 0:
      Z{w, n, st, k, ex, U32.is_eq(st, 3), c0, E{}, c1, c2, c3, c4, c5, c6}
    case 1:
      Z{w, n, st, k, ex, U32.is_eq(st, 3), c1, c0, E{}, c2, c3, c4, c5, c6}
    case 2:
      Z{w, n, st, k, ex, U32.is_eq(st, 3), c2, c0, c1, E{}, c3, c4, c5, c6}
    case 3:
      Z{w, n, st, k, ex, U32.is_eq(st, 3), c3, c0, c1, c2, E{}, c4, c5, c6}
    case 4:
      Z{w, n, st, k, ex, U32.is_eq(st, 3), c4, c0, c1, c2, c3, E{}, c5, c6}
    case 5:
      Z{w, n, st, k, ex, U32.is_eq(st, 3), c5, c0, c1, c2, c3, c4, E{}, c6}
    case _:
      Z{w, n, st, k, ex, U32.is_eq(st, 3), c6, c0, c1, c2, c3, c4, c5, E{}}

# split node t (position with column heights h) at the column chosen there
def Tr.split(t: Tr, +h: U32) -> Z:
  match t:
    case E{}:
      Z{0, 0, 1, 0, False{}, False{}, E{}, E{}, E{}, E{}, E{}, E{}, E{}, E{}}
    case N{+w, +n, +st, +c0, +c1, +c2, +c3, +c4, +c5, +c6}:
      +ch = choose(n, c0, c1, c2, c3, c4, c5, c6, h)
      Z.make((ch .&. 15 : U32), U32.is_ge(ch, 16), w, n, st, c0, c1, c2, c3, c4, c5, c6)

# the node, with child k replaced and this iteration's score added
def rebuild(k: U32, +w: U32, +n: U32, +st: U32, c0: Tr, c1: Tr, c2: Tr, c3: Tr, c4: Tr, c5: Tr, c6: Tr, +t: U32, r: Res) -> Res:
  match k r:
    case 0 Res{tc, +rs, s}:
      Res{N{(w + T.score(U32.xor(t, 1), rs) : U32), U32.inc(n), st, tc, c1, c2, c3, c4, c5, c6}, rs, s}
    case 1 Res{tc, +rs, s}:
      Res{N{(w + T.score(U32.xor(t, 1), rs) : U32), U32.inc(n), st, c0, tc, c2, c3, c4, c5, c6}, rs, s}
    case 2 Res{tc, +rs, s}:
      Res{N{(w + T.score(U32.xor(t, 1), rs) : U32), U32.inc(n), st, c0, c1, tc, c3, c4, c5, c6}, rs, s}
    case 3 Res{tc, +rs, s}:
      Res{N{(w + T.score(U32.xor(t, 1), rs) : U32), U32.inc(n), st, c0, c1, c2, tc, c4, c5, c6}, rs, s}
    case 4 Res{tc, +rs, s}:
      Res{N{(w + T.score(U32.xor(t, 1), rs) : U32), U32.inc(n), st, c0, c1, c2, c3, tc, c5, c6}, rs, s}
    case 5 Res{tc, +rs, s}:
      Res{N{(w + T.score(U32.xor(t, 1), rs) : U32), U32.inc(n), st, c0, c1, c2, c3, c4, tc, c6}, rs, s}
    case _ Res{tc, +rs, s}:
      Res{N{(w + T.score(U32.xor(t, 1), rs) : U32), U32.inc(n), st, c0, c1, c2, c3, c4, c5, tc}, rs, s}

def Pos.h(p: Pos) -> U32:
  match p:
    case Pos{xl, xh, ol, oh, h, st, live}:
      h

def Pos.st(p: Pos) -> U32:
  match p:
    case Pos{xl, xh, ol, oh, h, st, live}:
      st

# one iteration below the node split in z, whose board is pos (side t to move)
def descend(f: Nat, z: Z, pos: Pos, +t: U32, +s: U32) -> Res:
  match f z pos:
    case 0n _ _:
      Res{E{}, 1, s}
    case 1n+p Z{+w, +n, +st, +k, ex, False{}, kid, c0, c1, c2, c3, c4, c5, c6} _:
      rebuild(k, w, n, st, c0, c1, c2, c3, c4, c5, c6, t, Res{kid, st, s})
    case 1n+p Z{+w, +n, +st, +k, True{}, True{}, kid, c0, c1, c2, c3, c4, c5, c6} Pos{+xl, +xh, +ol, +oh, +h, ps, pl}:
      +s1 = T.prng(s)
      # drop runs twice: a Pos this def computes cannot be matched here
      +rs = playout(42n, drop(xl, xh, ol, oh, h, t, k), U32.xor(t, 1), T.mix(s1, 1))
      +st1 = Pos.st(drop(xl, xh, ol, oh, h, t, k))
      rebuild(k, w, n, st, c0, c1, c2, c3, c4, c5, c6, t, Res{Tr.fresh(T.score(t, rs), st1), rs, s1})
    case 1n+p Z{+w, +n, +st, +k, False{}, True{}, kid, c0, c1, c2, c3, c4, c5, c6} Pos{+xl, +xh, +ol, +oh, +h, ps, pl}:
      +h1 = (h + U32.shln(1, U32.to_nat((3 * k : U32))) : U32)
      rebuild(k, w, n, st, c0, c1, c2, c3, c4, c5, c6, t,
        descend(p, Tr.split(kid, h1), drop(xl, xh, ol, oh, h, t, k), U32.xor(t, 1), s))

# f more iterations of the tree in r, at board pos (side t to move, not over)
def grow(f: Nat, r: Res, +pos: Pos, +t: U32) -> Tr:
  match f r:
    case 0n Res{tr, st, s}:
      tr
    case 1n+p Res{tr, st, +s}:
      grow(p, descend(43n, Tr.split(tr, Pos.h(pos)), pos, t, s), pos, t)

def start() -> Pos:
  Pos{0, 0, 0, 0, 0, 3, True{}}

# the summed root visits of 2^d trees of k iterations; tree r uses seed
# mix(salt + r, 77)
def forest(+d: Nat, +k: Nat, +pos: Pos, +t: U32, +salt: U32, +r: U32) -> R7:
  match d:
    case 0n:
      Tr.visits(grow(k, Res{N{0, 0, 3, E{}, E{}, E{}, E{}, E{}, E{}, E{}}, 1, T.mix((salt + r : U32), 77)}, pos, t))
    case 1n+p:
      a b = forest(p, k, pos, t, salt, r) forest(p, k, pos, t, salt, U32.add(r, U32.shln(1, p)))
      R7.add(a, b)

# fold column c into the most visited so far, packed as c << 24 | visits
def take(+acc: U32, +c: U32, +vc: U32, +op: U32) -> U32:
  +b = U32.shrn(acc, 24n)
  Bool.pick(U32, Bool.and(U32.is_eq(bit(op, c), 1), Bool.or(U32.is_eq(b, 7), U32.is_gt(vc, (acc .&. 16777215 : U32)))),
    ((c << 24n) .|. vc : U32), acc)

def argmax(r: R7, +op: U32) -> U32:
  match r:
    case R7{+r0, +r1, +r2, +r3, +r4, +r5, +r6}:
      U32.shrn(take(take(take(take(take(take(take(U32.shln(7, 24n), 0, r0, op), 1, r1, op), 2, r2, op),
        3, r3, op), 4, r4, op), 5, r5, op), 6, r6, op), 24n)

def best(+pos: Pos, +t: U32, +d: Nat, +k: Nat, +salt: U32) -> U32:
  argmax(forest(d, k, pos, t, salt, 0), open(Pos.h(pos)))

# game g between the wide player (2^w trees x budget >> w) and the deep one
# (1 tree x budget), the wide one X in the even games; the final status
def game.go(f: Nat, pos: Pos, +t: U32, +g: U32, +w: U32, +turn: U32) -> U32:
  match f pos:
    case 0n Pos{xl, xh, ol, oh, h, st, live}:
      st
    case 1n+p Pos{xl, xh, ol, oh, h, st, False{}}:
      st
    case 1n+p Pos{+xl, +xh, +ol, +oh, +h, +st, True{}}:
      +wide = U32.is_eq(t, (g .&. 1 : U32))
      +salt = ((g * 64) + (turn * 4096) + (t * 65536) : U32)
      +d = U32.to_nat(Bool.pick(U32, wide, w, 0))
      +k = U32.to_nat(Bool.pick(U32, wide, (budget() >> U32.to_nat(w) : U32), budget()))
      +c = best(Pos{xl, xh, ol, oh, h, st, True{}}, t, d, k, salt)
      game.go(p, drop(xl, xh, ol, oh, h, t, c), U32.xor(t, 1), g, w, U32.inc(turn))

def game(+g: U32, +w: U32) -> W3:
  +st = game.go(42n, start(), 0, g, w, 0)
  +me = (g .&. 1 : U32)
  +draw = U32.is_eq(st, 1)
  +win = Bool.and(Bool.not(draw), Bool.not(Bool.xor(U32.is_eq(st, 0), U32.is_eq(me, 0))))
  W3{Bool.to_u32(win), Bool.to_u32(draw), Bool.to_u32(Bool.and(Bool.not(draw), Bool.not(win)))}

def duel(+d: Nat, +w: U32, +g: U32) -> W3:
  match d:
    case 0n:
      game(g, w)
    case 1n+p:
      a b = duel(p, w, g) duel(p, w, U32.add(g, U32.shln(1, p)))
      W3.add(a, b)

def W3.show(+w: U32, r: W3) -> String:
  match r:
    case W3{a, b, c}:
      U32.show(U32.shln(1, U32.to_nat(w))) ++ " trees x " ++ U32.show((budget() >> U32.to_nat(w) : U32)) ++
      " vs 1 x " ++ U32.show(budget()) ++ ": " ++ U32.show(a) ++ " won " ++ U32.show(b) ++ " drawn " ++
      U32.show(c) ++ " lost"

def main() -> IO(Unit):
  IO.print(R7.show(forest(dep(), iters(), start(), 0, 0, 0)) ++ "\n" ++ W3.show(0, duel(games(), 0, 0)) ++ "\n" ++
    W3.show(2, duel(games(), 2, 0)) ++ "\n" ++ W3.show(4, duel(games(), 4, 0)) ++ "\n" ++ W3.show(6, duel(games(), 6, 0)))
