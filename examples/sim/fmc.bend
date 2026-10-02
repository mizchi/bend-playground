import Base
import ./ttt.bend as T
# Monte Carlo search: flat Monte Carlo for tic-tac-toe.
# A player rates each legal move by 2^dep random playouts from the position
# after it (win 2, draw 1, loss 0 for the mover) and plays the best, the
# lowest cell on a tie. The playouts are the leaves of a fork tree (one leaf
# plays each of the 9 moves once) and their 9 sums merge in O(1). Prints the
# ratings of the 9 first moves, then 2^games games of that player against a
# uniformly random one (X in the even games, O in the odd ones), the games
# themselves the leaves of a second fork tree.
# The board, the playouts and the game record are in ttt.bend.
# examples/sim/fmc.c runs the same arithmetic (its first two lines match)
# and also checks the player against exact minimax. Knobs: dep(), games().

def dep() -> Nat:
  10n

def games() -> Nat:
  8n

# one playout after the mover t takes cell bit (0 if the cell is taken)
def try(+x: U32, +o: U32, +t: U32, +s: U32, +bit: U32, free: Bool) -> U32:
  match free:
    case False{}:
      0
    case True{}:
      +nx = Bool.pick(U32, U32.is_eq(t, 0), (x .|. bit : U32), x)
      +no = Bool.pick(U32, U32.is_eq(t, 1), (o .|. bit : U32), o)
      T.score(t, T.playout(9n, nx, no, U32.xor(t, 1), s, U32.is_eq(T.status(nx, no), 3)))

def try.at(+x: U32, +o: U32, +t: U32, +salt: U32, +j: U32, +c: Nat) -> U32:
  +bit = U32.shln(1, c)
  try(x, o, t, T.mix((salt + j : U32), U32.from_nat(c)), bit, U32.is_zero(((x .|. o) .&. bit : U32)))

# playout j of every cell
def leaf(+x: U32, +o: U32, +t: U32, +salt: U32, +j: U32) -> T.R9:
  T.R9{try.at(x, o, t, salt, j, 0n), try.at(x, o, t, salt, j, 1n), try.at(x, o, t, salt, j, 2n),
     try.at(x, o, t, salt, j, 3n), try.at(x, o, t, salt, j, 4n), try.at(x, o, t, salt, j, 5n),
     try.at(x, o, t, salt, j, 6n), try.at(x, o, t, salt, j, 7n), try.at(x, o, t, salt, j, 8n)}

def rate(+d: Nat, +x: U32, +o: U32, +t: U32, +salt: U32, +j: U32) -> T.R9:
  match d:
    case 0n:
      leaf(x, o, t, salt, j)
    case 1n+p:
      a b = rate(p, x, o, t, salt, j) rate(p, x, o, t, salt, U32.add(j, U32.shln(1, p)))
      T.R9.add(a, b)

# the flat player's move
def best(+x: U32, +o: U32, +t: U32, +salt: U32) -> U32:
  T.argmax(rate(dep(), x, o, t, salt, 0), (x .|. o : U32))

# the next move of game g at its turn: the flat player's or a random one
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
  IO.print(T.R9.show(rate(dep(), 0, 0, 0, 0, 0)) ++ "\n" ++ T.T6.show(games.tree(games(), 0)))
