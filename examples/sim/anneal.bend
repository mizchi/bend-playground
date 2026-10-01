import Base
# Monte Carlo search: simulated annealing on a 0-1 knapsack.
# 32 items (weight in [10, 73], value = weight + [0, 31]: correlated, so
# greedy fails) and capacity 600. The item set is a U32 bitmask, so a state is
# four scalars and a proposal (flip one random item) is O(1). 2^dep chains
# start from the empty set with different seeds and cool geometrically from
# T = 100 by 0.9983 per proposal (Metropolis acceptance). The chains are
# independent leaves of a fork tree; Best merges in O(1): the larger value
# wins, a tie sums the chain counts and keeps the left (lower-index) mask.
#
# examples/sim/anneal.c runs the same search bit for bit and also solves the
# instance exactly by dynamic programming (optimum 976). Knobs: dep(), steps().

# best value, chains that reached it, item mask of the first such chain
type Best is Data:
  Best{v: U32, n: U32, m: U32}

def Best.pick(a: Best, b: Best, +av: U32, +an: U32, +am: U32, +bv: U32, +bn: U32, lt: Bool, eq: Bool) -> Best:
  match lt eq:
    case True{} _:
      b
    case False{} True{}:
      Best{av, (an + bn : U32), am}
    case False{} False{}:
      a

def Best.max(a: Best, b: Best) -> Best:
  match a b:
    case Best{+av, +an, +am} Best{+bv, +bn, +bm}:
      Best.pick(Best{av, an, am}, Best{bv, bn, bm}, av, an, am, bv, bn, U32.is_lt(av, bv), U32.is_eq(av, bv))

def prng(+x: U32) -> U32:
  +b = U32.xor(x, U32.shln(x, 13n))
  +d = U32.xor(b, U32.shrn(b, 17n))
  U32.xor(d, U32.shln(d, 5n))

def seed(+i: U32) -> U32:
  U32.xor(U32.mul(U32.inc(i), 2654435761), 1013904223)

def item(+j: U32) -> U32:
  prng(U32.mul(U32.inc(j), 2654435769))

def weight(+j: U32) -> U32:
  (10 + (item(j) .&. 63) : U32)

def value(+j: U32) -> U32:
  (weight(j) + ((item(j) >> 8n) .&. 31) : U32)

def cap() -> U32:
  600

# the chain's state: rng, mask, weight, value, best value, its mask, temperature
type St is Data:
  St{s: U32, m: U32, w: U32, v: U32, best: U32, bm: U32, t: F32}

def St.keep(+s: U32, +m: U32, +w: U32, +v: U32, +best: U32, +bm: U32, +t: F32, better: Bool) -> St:
  match better:
    case True{}:
      St{s, m, w, v, v, m, (t * 0.9983 : F32)}
    case False{}:
      St{s, m, w, v, best, bm, (t * 0.9983 : F32)}

# accept: flip item j and record a new best; reject: only cool
def St.move(+s: U32, +m: U32, +w: U32, +v: U32, +best: U32, +bm: U32, +t: F32,
            +j: U32, +w2: U32, +v2: U32, ok: Bool) -> St:
  match ok:
    case True{}:
      +m2 = U32.xor(m, U32.shln(1, U32.to_nat(j)))
      St.keep(s, m2, w2, v2, best, bm, t, U32.is_lt(best, v2))
    case False{}:
      St{s, m, w, v, best, bm, (t * 0.9983 : F32)}

# one Metropolis proposal: flip a random item, keep it if it fits and the
# value does not drop, or drops by dv with probability exp(dv / t)
def St.step(st: St) -> St:
  match st:
    case St{s0, +m, +w, +v, +best, +bm, +t}:
      +s1 = prng(s0)
      +j = U32.shrn(s1, 27n)
      +in = ((m >> U32.to_nat(j)) .&. 1 : U32)
      +w2 = Bool.pick(U32, U32.is_eq(in, 1), (w - weight(j) : U32), (w + weight(j) : U32))
      +v2 = Bool.pick(U32, U32.is_eq(in, 1), (v - value(j) : U32), (v + value(j) : U32))
      +s2 = prng(s1)
      +u = (U32.to_f32(U32.shrn(s2, 8n)) / 16777216.0 : F32)
      +dv = (U32.to_f32(v2) - U32.to_f32(v) : F32)
      ok = Bool.and(U32.is_le(w2, cap()), Bool.or(F32.is_le(0.0, dv), F32.is_lt(u, F32.exp((dv / t : F32)))))
      St.move(s2, m, w, v, best, bm, t, j, w2, v2, ok)

def run(k: Nat, st: St) -> St:
  match k:
    case 0n:
      st
    case 1n+p:
      run(p, St.step(st))

def St.best(st: St) -> Best:
  match st:
    case St{s, m, w, v, best, bm, t}:
      Best{best, 1, bm}

def chain(+k: Nat, +i: U32) -> Best:
  St.best(run(k, St{seed(i), 0, 0, 0, 0, 0, 100.0}))

def tree(+d: Nat, +k: Nat, +i: U32) -> Best:
  match d:
    case 0n:
      chain(k, i)
    case 1n+p:
      a b = tree(p, k, i) tree(p, k, U32.add(i, U32.shln(1, p)))
      Best.max(a, b)

def Best.show(b: Best) -> String:
  match b:
    case Best{v, n, m}:
      "best=" ++ U32.show(v) ++ " chains=" ++ U32.show(n) ++ " mask=" ++ U32.show(m)

def dep() -> Nat:
  14n

def steps() -> Nat:
  4096n

def main() -> IO(Unit):
  IO.print(Best.show(tree(dep(), steps(), 0)))
