import Base
# Tic-tac-toe for fmc.bend and mcts.bend: the board, random playouts, the
# 9-cell tallies and their argmax, and the game record against the random
# player. A board is two 9-bit masks, x and o (cell c is bit c, row-major);
# t is the side to move (0 X, 1 O). A random move takes the k-th empty cell
# with k = (rng >> 16) * empties >> 16, so no division is needed.

# the 9 cell ratings of one position
type R9 is Data:
  R9{r0: U32, r1: U32, r2: U32, r3: U32, r4: U32, r5: U32, r6: U32, r7: U32, r8: U32}

def R9.add(a: R9, b: R9) -> R9:
  match a b:
    case R9{a0, a1, a2, a3, a4, a5, a6, a7, a8} R9{b0, b1, b2, b3, b4, b5, b6, b7, b8}:
      R9{(a0 + b0 : U32), (a1 + b1 : U32), (a2 + b2 : U32), (a3 + b3 : U32), (a4 + b4 : U32),
         (a5 + b5 : U32), (a6 + b6 : U32), (a7 + b7 : U32), (a8 + b8 : U32)}

def R9.show(r: R9) -> String:
  match r:
    case R9{r0, r1, r2, r3, r4, r5, r6, r7, r8}:
      U32.show(r0) ++ " " ++ U32.show(r1) ++ " " ++ U32.show(r2) ++ " " ++
      U32.show(r3) ++ " " ++ U32.show(r4) ++ " " ++ U32.show(r5) ++ " " ++
      U32.show(r6) ++ " " ++ U32.show(r7) ++ " " ++ U32.show(r8)

# a move to play (a one-bit mask, 0 for none) and the rng state after it
type Mv is Data:
  Mv{c: U32, s: U32}

# games the flat player won, drew and lost, as X and as O
type T6 is Data:
  T6{xw: U32, xd: U32, xl: U32, ow: U32, od: U32, ol: U32}

def T6.add(a: T6, b: T6) -> T6:
  match a b:
    case T6{a0, a1, a2, a3, a4, a5} T6{b0, b1, b2, b3, b4, b5}:
      T6{(a0 + b0 : U32), (a1 + b1 : U32), (a2 + b2 : U32), (a3 + b3 : U32), (a4 + b4 : U32), (a5 + b5 : U32)}

def T6.show(r: T6) -> String:
  match r:
    case T6{xw, xd, xl, ow, od, ol}:
      "as X: " ++ U32.show(xw) ++ " won " ++ U32.show(xd) ++ " drawn " ++ U32.show(xl) ++
      " lost; as O: " ++ U32.show(ow) ++ " won " ++ U32.show(od) ++ " drawn " ++ U32.show(ol) ++ " lost"

def prng(+x: U32) -> U32:
  +b = U32.xor(x, U32.shln(x, 13n))
  +d = U32.xor(b, U32.shrn(b, 17n))
  U32.xor(d, U32.shln(d, 5n))

def mix(+a: U32, +b: U32) -> U32:
  prng(U32.xor(U32.mul(U32.inc(a), 2654435761), U32.mul(U32.inc(b), 2246822519)))

def line(+m: U32, +l: U32) -> Bool:
  U32.is_eq((m .&. l : U32), l)

def won(+m: U32) -> Bool:
  Bool.or(Bool.or(Bool.or(line(m, 7), line(m, 56)), Bool.or(line(m, 448), line(m, 73))),
          Bool.or(Bool.or(line(m, 146), line(m, 292)), Bool.or(line(m, 273), line(m, 84))))

# 0 X won, 1 draw, 2 O won, 3 not over
def status(+x: U32, +o: U32) -> U32:
  Bool.pick(U32, won(x), 0, Bool.pick(U32, won(o), 2,
    Bool.pick(U32, U32.is_eq((x .|. o : U32), 511), 1, 3)))

def popcount(+e: U32) -> U32:
  ((e .&. 1) + ((e >> 1n) .&. 1) + ((e >> 2n) .&. 1) + ((e >> 3n) .&. 1) + ((e >> 4n) .&. 1)
    + ((e >> 5n) .&. 1) + ((e >> 6n) .&. 1) + ((e >> 7n) .&. 1) + ((e >> 8n) .&. 1) : U32)

# is bit the k-th (from 0) set bit of e, counting from it?
def here(+e: U32, +k: U32, +bit: U32) -> Bool:
  Bool.and(U32.is_ne((e .&. bit : U32), 0), U32.is_eq(k, 0))

# the k-th set bit of e at or above bit, as a mask; stops at it
def nth(f: Nat, +e: U32, +k: U32, +bit: U32, at: Bool) -> U32:
  match f at:
    case 0n _:
      0
    case 1n+p True{}:
      bit
    case 1n+p False{}:
      +k1 = (k - Bool.to_u32(U32.is_ne((e .&. bit : U32), 0)) : U32)
      +b1 = (bit << 1n : U32)
      nth(p, e, k1, b1, here(e, k1, b1))

# the empty cell a random player takes with rng state s
def cell(+x: U32, +o: U32, +s: U32) -> U32:
  +e = U32.xor(511, (x .|. o : U32))
  +k = (((s >> 16n) * popcount(e)) >> 16n : U32)
  nth(9n, e, k, 1, here(e, k, 1))

# random playout to the end (9 moves always suffice); the final status
def playout(f: Nat, +x: U32, +o: U32, +t: U32, +s: U32, live: Bool) -> U32:
  match f live:
    case 0n _:
      status(x, o)
    case 1n+p False{}:
      status(x, o)
    case 1n+p True{}:
      +s1 = prng(s)
      +c = cell(x, o, s1)
      +nx = Bool.pick(U32, U32.is_eq(t, 0), (x .|. c : U32), x)
      +no = Bool.pick(U32, U32.is_eq(t, 1), (o .|. c : U32), o)
      playout(p, nx, no, U32.xor(t, 1), s1, U32.is_eq(status(nx, no), 3))

# the mover's score of a final status: win 2, draw 1, loss 0
def score(+t: U32, +st: U32) -> U32:
  Bool.pick(U32, U32.is_eq(t, 0), (2 - st : U32), st)

# fold cell c into the best so far, packed as cell << 24 | rating
def take(+acc: U32, +c: U32, +rc: U32, +occ: U32) -> U32:
  +b = U32.shrn(acc, 24n)
  +free = U32.is_zero((occ .&. U32.shln(1, U32.to_nat(c)) : U32))
  Bool.pick(U32, Bool.and(free, Bool.or(U32.is_eq(b, 9), U32.is_gt(rc, (acc .&. 16777215 : U32)))),
    ((c << 24n) .|. rc : U32), acc)

def argmax(r: R9, +occ: U32) -> U32:
  match r:
    case R9{+r0, +r1, +r2, +r3, +r4, +r5, +r6, +r7, +r8}:
      +a0 = take(U32.shln(9, 24n), 0, r0, occ)
      +a1 = take(a0, 1, r1, occ)
      +a2 = take(a1, 2, r2, occ)
      +a3 = take(a2, 3, r3, occ)
      +a4 = take(a3, 4, r4, occ)
      +a5 = take(a4, 5, r5, occ)
      +a6 = take(a5, 6, r6, occ)
      +a7 = take(a6, 7, r7, occ)
      +a8 = take(a7, 8, r8, occ)
      U32.shln(1, U32.to_nat(U32.shrn(a8, 24n)))

# game g's result for the player under test, X in the even games, O in the
# odd ones: won, drawn or lost, as X or as O
def T6.of(+g: U32, +st: U32) -> T6:
  +me = (g .&. 1 : U32)
  +draw = U32.is_eq(st, 1)
  +win = Bool.and(Bool.not(draw), Bool.not(Bool.xor(U32.is_eq(st, 0), U32.is_eq(me, 0))))
  +loss = Bool.and(Bool.not(draw), Bool.not(win))
  +asx = U32.is_eq(me, 0)
  T6{Bool.to_u32(Bool.and(asx, win)), Bool.to_u32(Bool.and(asx, draw)), Bool.to_u32(Bool.and(asx, loss)),
     Bool.to_u32(Bool.and(Bool.not(asx), win)), Bool.to_u32(Bool.and(Bool.not(asx), draw)),
     Bool.to_u32(Bool.and(Bool.not(asx), loss))}
