import Base
# Physics: a Galton board as a rigid-ball ensemble.
# Each ball falls under gravity (semi-implicit Euler, dt = 0.005) through 12
# rows of round pegs on a triangular lattice. A contact pushes the ball out to
# the contact distance and reflects its normal velocity with restitution 0.3;
# two side walls reflect, and the floor below the last row absorbs, so the
# ball rests in its bin. Balls never touch each other, so the 2^dep balls are
# independent instances on the leaves of a fork tree, and the 16-bin
# histograms merge pairwise up the tree (combine is O(1): 16 adds).
#
# examples/sim/galton.c runs the same f32 operations in the same order, so the
# two histograms match bit for bit. Knobs: dep() (balls = 2^dep), steps().

# position and velocity; y grows downward
type Ball is Data:
  Ball{x: F32, y: F32, vx: F32, vy: F32}

type Hist is Data:
  Hist{h0: U32, h1: U32, h2: U32, h3: U32, h4: U32, h5: U32, h6: U32, h7: U32,
       h8: U32, h9: U32, ha: U32, hb: U32, hc: U32, hd: U32, he: U32, hf: U32}

def Hist.add(a: Hist, b: Hist) -> Hist:
  match a b:
    case Hist{a0, a1, a2, a3, a4, a5, a6, a7, a8, a9, aa, ab, ac, ad, ae, af}
         Hist{b0, b1, b2, b3, b4, b5, b6, b7, b8, b9, ba, bb, bc, bd, be, bf}:
      Hist{(a0 + b0 : U32), (a1 + b1 : U32), (a2 + b2 : U32), (a3 + b3 : U32),
           (a4 + b4 : U32), (a5 + b5 : U32), (a6 + b6 : U32), (a7 + b7 : U32),
           (a8 + b8 : U32), (a9 + b9 : U32), (aa + ba : U32), (ab + bb : U32),
           (ac + bc : U32), (ad + bd : U32), (ae + be : U32), (af + bf : U32)}

# a histogram with a single ball in bin k
def Hist.one(+k: U32) -> Hist:
  Hist{Bool.to_u32(U32.is_eq(k, 0)), Bool.to_u32(U32.is_eq(k, 1)),
       Bool.to_u32(U32.is_eq(k, 2)), Bool.to_u32(U32.is_eq(k, 3)),
       Bool.to_u32(U32.is_eq(k, 4)), Bool.to_u32(U32.is_eq(k, 5)),
       Bool.to_u32(U32.is_eq(k, 6)), Bool.to_u32(U32.is_eq(k, 7)),
       Bool.to_u32(U32.is_eq(k, 8)), Bool.to_u32(U32.is_eq(k, 9)),
       Bool.to_u32(U32.is_eq(k, 10)), Bool.to_u32(U32.is_eq(k, 11)),
       Bool.to_u32(U32.is_eq(k, 12)), Bool.to_u32(U32.is_eq(k, 13)),
       Bool.to_u32(U32.is_eq(k, 14)), Bool.to_u32(U32.is_eq(k, 15))}

def Hist.show(h: Hist) -> String:
  match h:
    case Hist{h0, h1, h2, h3, h4, h5, h6, h7, h8, h9, ha, hb, hc, hd, he, hf}:
      U32.show(h0) ++ " " ++ U32.show(h1) ++ " " ++ U32.show(h2) ++ " " ++
      U32.show(h3) ++ " " ++ U32.show(h4) ++ " " ++ U32.show(h5) ++ " " ++
      U32.show(h6) ++ " " ++ U32.show(h7) ++ " " ++ U32.show(h8) ++ " " ++
      U32.show(h9) ++ " " ++ U32.show(ha) ++ " " ++ U32.show(hb) ++ " " ++
      U32.show(hc) ++ " " ++ U32.show(hd) ++ " " ++ U32.show(he) ++ " " ++
      U32.show(hf)

def prng(+x: U32) -> U32:
  +b = U32.xor(x, U32.shln(x, 13n))
  +d = U32.xor(b, U32.shrn(b, 17n))
  U32.xor(d, U32.shln(d, 5n))

def seed(+i: U32) -> U32:
  U32.xor(U32.mul(U32.inc(i), 2654435761), 1013904223)

# uniform in [-0.05, 0.05) from the top 24 bits
def jitter(s: U32) -> F32:
  +u = (U32.to_f32(U32.shrn(s, 8n)) / 16777216.0 : F32)
  ((u - 0.5) * 0.1 : F32)

# one peg contact: push out to the contact distance (0.4 = ball + peg radius)
# and reflect the normal velocity when the ball approaches the peg
def hit(+vx: F32, +vy: F32, +px: F32, +py: F32, +dx: F32, +dy: F32, +d2: F32) -> Ball:
  +d = F32.sqrt(d2)
  +nx = (dx / d : F32)
  +ny = (dy / d : F32)
  +vn = (vx * nx + vy * ny : F32)
  +k = Bool.pick(F32, F32.is_lt(vn, 0.0), ((1.0 + 0.3) * vn : F32), 0.0)
  Ball{(px + nx * 0.4 : F32), (py + ny * 0.4 : F32), (vx - k * nx : F32), (vy - k * ny : F32)}

def contact(+x: F32, +y: F32, +vx: F32, +vy: F32, +px: F32, +py: F32, +dx: F32, +dy: F32,
            +d2: F32, live: Bool) -> Ball:
  match live:
    case True{}:
      hit(vx, vy, px, py, dx, dy, d2)
    case False{}:
      Ball{x, y, vx, vy}

# the floor (y > 13) absorbs; the side walls (|x| > 7) reflect
def bound.go(+x: F32, +y: F32, +vx: F32, +vy: F32, floor: Bool, lo: Bool, hi: Bool) -> Ball:
  match floor:
    case True{}:
      Ball{x, 13.0, 0.0, 0.0}
    case False{}:
      match lo:
        case True{}:
          Ball{(0.0 - 7.0 : F32), y, (0.0 - vx * 0.3 : F32), vy}
        case False{}:
          match hi:
            case True{}:
              Ball{7.0, y, (0.0 - vx * 0.3 : F32), vy}
            case False{}:
              Ball{x, y, vx, vy}

def bound(b: Ball) -> Ball:
  match b:
    case Ball{+x, +y, +vx, +vy}:
      bound.go(x, y, vx, vy, F32.is_gt(y, 13.0), F32.is_lt(x, (0.0 - 7.0 : F32)), F32.is_gt(x, 7.0))

def step(b: Ball) -> Ball:
  match b:
    case Ball{+x0, +y0, +vx, +vy0}:
      +vy = (vy0 + 9.8 * 0.005 : F32)
      +x = (x0 + vx * 0.005 : F32)
      +y = (y0 + vy * 0.005 : F32)
      # nearest peg: row by rounding y, column by rounding x in that row's offset
      +r = F32.floor((y + 0.5 : F32))
      +o = ((r - F32.floor((r * 0.5 : F32)) * 2.0) * 0.5 : F32)
      +px = (F32.floor((x - o + 0.5 : F32)) + o : F32)
      +dx = (x - px : F32)
      +dy = (y - r : F32)
      +d2 = (dx * dx + dy * dy : F32)
      live = Bool.and(Bool.and(F32.is_le(1.0, r), F32.is_le(r, 12.0)), F32.is_lt(d2, (0.4 * 0.4 : F32)))
      bound(contact(x, y, vx, vy, px, r, dx, dy, d2, live))

def run(s: Nat, b: Ball) -> Ball:
  match s:
    case 0n:
      b
    case 1n+p:
      run(p, step(b))

# bin 0..15 by the final x (column width 1, centre bin 8)
def bin(b: Ball) -> U32:
  match b:
    case Ball{x, y, vx, vy}:
      F32.to_u32(F32.min(F32.max(F32.floor((x + 8.5 : F32)), 0.0), 15.0))

def ball(+s: Nat, +i: U32) -> Hist:
  +s1 = prng(seed(i))
  +s2 = prng(s1)
  Hist.one(bin(run(s, Ball{jitter(s1), 0.0, jitter(s2), 0.0})))

def tree(+d: Nat, +s: Nat, +i: U32) -> Hist:
  match d:
    case 0n:
      ball(s, i)
    case 1n+p:
      a b = tree(p, s, i) tree(p, s, U32.add(i, U32.shln(1, p)))
      Hist.add(a, b)

def dep() -> Nat:
  16n

def steps() -> Nat:
  2048n

def main() -> IO(Unit):
  IO.print(Hist.show(tree(dep(), steps(), 0)))
