import Base
# Physics: interacting rigid balls in a box.
# Unlike galton.bend, the bodies here touch each other: each box holds 8
# equal-mass balls of radius 0.05 in the unit square, and every step resolves
# every overlapping, approaching pair with an elastic impulse along the
# contact normal (Jacobi: all impulses read the previous state, O(N^2) per
# step), reflects the walls and moves (dt = 0.002). The box state is a shared
# (+) list read by every ball's impulse sum; a step maps it to the next list,
# and each ball counts its own contacts. Boxes are independent leaves of a
# fork tree; the contact count and a position checksum add up the tree.
#
# examples/sim/balls.c runs the same f32 operations in the same order with
# arrays, so the outputs match bit for bit. Knobs: dep() (boxes = 2^dep),
# steps().

# position, velocity, and the contacts this ball has resolved so far
type Ball is Data:
  Ball{x: F32, y: F32, vx: F32, vy: F32, n: U32}

# impulse sum on one ball, and its running contact count
type Acc is Data:
  Acc{dvx: F32, dvy: F32, hits: U32}

type Out is Data:
  Out{hits: U32, cs: U32}

def Out.add(a: Out, b: Out) -> Out:
  match a b:
    case Out{ah, ac} Out{bh, bc}:
      Out{(ah + bh : U32), (ac + bc : U32)}

def prng(+x: U32) -> U32:
  +b = U32.xor(x, U32.shln(x, 13n))
  +d = U32.xor(b, U32.shrn(b, 17n))
  U32.xor(d, U32.shln(d, 5n))

def seed(+i: U32) -> U32:
  U32.xor(U32.mul(U32.inc(i), 2654435761), 1013904223)

def unit(+s: U32) -> F32:
  (U32.to_f32(U32.shrn(s, 8n)) / 16777216.0 : F32)

# ball k at grid slot (c, r) of (0.2, 0.5, 0.8)^2, jittered by +-0.05, with
# velocity in [-0.5, 0.5)^2
def spawn(+s: U32, +k: U32, +c: F32, +r: F32) -> Ball:
  +s1 = prng(U32.xor(s, U32.mul(k, 2246822519)))
  +s2 = prng(s1)
  +s3 = prng(s2)
  +s4 = prng(s3)
  +gx = (0.2 + 0.3 * c : F32)
  +gy = (0.2 + 0.3 * r : F32)
  Ball{(gx + (unit(s1) - 0.5) * 0.1 : F32), (gy + (unit(s2) - 0.5) * 0.1 : F32),
       (unit(s3) - 0.5 : F32), (unit(s4) - 0.5 : F32), 0}

def spawn.all(+s: U32) -> +List<Ball>:
  [spawn(s, 0, 0.0, 0.0), spawn(s, 1, 1.0, 0.0), spawn(s, 2, 2.0, 0.0),
   spawn(s, 3, 0.0, 1.0), spawn(s, 4, 1.0, 1.0), spawn(s, 5, 2.0, 1.0),
   spawn(s, 6, 0.0, 2.0), spawn(s, 7, 1.0, 2.0)]

def approach(acc: Acc, +nx: F32, +ny: F32, +rv: F32, yes: Bool) -> Acc:
  match acc yes:
    case Acc{dvx, dvy, h} True{}:
      Acc{(dvx - rv * nx : F32), (dvy - rv * ny : F32), U32.inc(h)}
    case Acc{dvx, dvy, h} False{}:
      Acc{dvx, dvy, h}

# one pair in contact: the relative velocity along the normal, if it closes
def pair(acc: Acc, +dx: F32, +dy: F32, +d2: F32, +rvx: F32, +rvy: F32, live: Bool) -> Acc:
  match live:
    case True{}:
      +d = F32.sqrt(d2)
      +nx = (dx / d : F32)
      +ny = (dy / d : F32)
      +rv = (rvx * nx + rvy * ny : F32)
      approach(acc, nx, ny, rv, F32.is_lt(rv, 0.0))
    case False{}:
      acc

# sum the impulses on ball (x, y, vx, vy) from every ball in js, in order
def push.go(js: +List<Ball>, +x: F32, +y: F32, +vx: F32, +vy: F32, acc: Acc) -> Acc:
  match js:
    case Nil{}:
      acc
    case b <> t:
      match b:
        case Ball{+bx, +by, +bvx, +bvy, bn}:
          +dx = (x - bx : F32)
          +dy = (y - by : F32)
          +d2 = (dx * dx + dy * dy : F32)
          live = Bool.and(F32.is_lt(0.0, d2), F32.is_lt(d2, ((0.05 + 0.05) * (0.05 + 0.05) : F32)))
          push.go(t, x, y, vx, vy, pair(acc, dx, dy, d2, (vx - bvx : F32), (vy - bvy : F32), live))

# reflect off the walls, then move
def move(+x: F32, +y: F32, +vx0: F32, +vy0: F32, n: U32) -> Ball:
  +vx = Bool.pick(F32, F32.is_lt(x, 0.05), F32.abs(vx0),
          Bool.pick(F32, F32.is_lt((1.0 - 0.05 : F32), x), (0.0 - F32.abs(vx0) : F32), vx0))
  +vy = Bool.pick(F32, F32.is_lt(y, 0.05), F32.abs(vy0),
          Bool.pick(F32, F32.is_lt((1.0 - 0.05 : F32), y), (0.0 - F32.abs(vy0) : F32), vy0))
  Ball{(x + vx * 0.002 : F32), (y + vy * 0.002 : F32), vx, vy, n}

def ball.fin(+x: F32, +y: F32, +vx: F32, +vy: F32, acc: Acc) -> Ball:
  match acc:
    case Acc{dvx, dvy, h}:
      move(x, y, (vx + dvx : F32), (vy + dvy : F32), h)

def ball.step(b: Ball, +all: +List<Ball>) -> Ball:
  match b:
    case Ball{+x, +y, +vx, +vy, n}:
      ball.fin(x, y, vx, vy, push.go(all, x, y, vx, vy, Acc{0.0, 0.0, n}))

# advance every ball of bs against the previous state all
def box.step(bs: +List<Ball>, +all: +List<Ball>) -> +List<Ball>:
  match bs:
    case Nil{}:
      Nil{}
    case b <> t:
      ball.step(b, all) <> box.step(t, all)

def box.run(k: Nat, +bs: +List<Ball>) -> +List<Ball>:
  match k:
    case 0n:
      bs
    case 1n+p:
      box.run(p, box.step(bs, bs))

# total contacts, and a checksum of the final positions
def box.out(bs: +List<Ball>, acc: Out) -> Out:
  match bs acc:
    case Nil{} _:
      acc
    case (Ball{x, y, vx, vy, n} <> t) Out{h, cs}:
      +w = (F32.to_u32((x * 65536.0 : F32)) * 31 + F32.to_u32((y * 65536.0 : F32)) : U32)
      box.out(t, Out{(h + n : U32), (cs + w : U32)})

def box(+k: Nat, +i: U32) -> Out:
  box.out(box.run(k, spawn.all(seed(i))), Out{0, 0})

def tree(+d: Nat, +k: Nat, +i: U32) -> Out:
  match d:
    case 0n:
      box(k, i)
    case 1n+p:
      a b = tree(p, k, i) tree(p, k, U32.add(i, U32.shln(1, p)))
      Out.add(a, b)

def Out.show(o: Out) -> String:
  match o:
    case Out{h, c}:
      "contacts=" ++ U32.show(h) ++ " checksum=" ++ U32.show(c)

def dep() -> Nat:
  12n

def steps() -> Nat:
  4096n

def main() -> IO(Unit):
  IO.print(Out.show(tree(dep(), steps(), 0)))
