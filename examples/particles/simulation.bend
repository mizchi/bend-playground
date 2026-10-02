import Base
import ./api.bend as UI

type Particle is Data:
  Particle{x: F32, y: F32, vx: F32, vy: F32, life: F32, seed: U32}

def random(+x: U32) -> U32:
  +a = U32.xor(x, U32.shln(x, 13n))
  +b = U32.xor(a, U32.shrn(a, 17n))
  U32.and(U32.xor(b, U32.shln(b, 5n)), 16777215)

def noise(rounds: Nat, seed: U32) -> U32:
  match rounds:
    case 0n: seed
    case 1n+p: noise(p, random(seed))

def force(enabled: Bool, seed: U32) -> F32:
  match enabled:
    case False{}: 0.0
    case True{}:
      F32.mul(F32.sub(F32.div(U32.to_f32(U32.mod(seed, 4096)), 4096.0), 0.5), 0.6)

def respawn(dead: Bool, particle: Particle) -> Particle:
  match dead:
    case False{}: particle
    case True{}:
      match particle:
        case Particle{x, y, vx, vy, life, seed}:
          +r = random(seed)
          Particle{F32.sub(F32.div(U32.to_f32(U32.mod(r, 4096)), 2048.0), 1.0), F32.neg(1.0),
            F32.mul(F32.sub(F32.div(U32.to_f32(U32.mod(U32.shrn(r, 12n), 4096)), 4096.0), 0.5), 0.3),
            F32.add(0.5, F32.div(U32.to_f32(U32.mod(r, 1024)), 2048.0)),
            F32.add(1.0, F32.div(U32.to_f32(U32.mod(r, 4096)), 1024.0)), r}

def integrate(particle: Particle, rounds: Nat, +enabled: Bool) -> Particle:
  match particle:
    case Particle{+x, +y, +vx, +vy, life, seed}:
      +r = noise(rounds, seed)
      nx = force(enabled, r)
      ny = force(enabled, U32.shrn(r, 12n))
      ax = F32.add(F32.sub(F32.mul(F32.neg(x), 0.15), F32.mul(vx, 0.05)), nx)
      ay = F32.add(F32.sub(F32.sub(F32.mul(F32.neg(y), 0.15), F32.mul(vy, 0.05)), 0.12), ny)
      +ux = F32.add(vx, F32.mul(ax, 0.016666667))
      +uy = F32.add(vy, F32.mul(ay, 0.016666667))
      Particle{F32.add(x, F32.mul(ux, 0.016666667)), F32.add(y, F32.mul(uy, 0.016666667)),
        ux, uy, F32.sub(life, 0.016666667), r}

def get(result: Array<F32> & F32, rest: Array<F32> -> F32 -> Array<F32>) -> Array<F32>:
  (buffer, value) = result
  rest(buffer, value)

def read(buffer: Array<F32>, +base: U32,
    rest: Array<F32> -> Particle -> Array<F32>) -> Array<F32>:
  get(Array.get(F32, buffer, base), a => x =>
    get(Array.get(F32, a, U32.add(base, 1)), b => y =>
      get(Array.get(F32, b, U32.add(base, 2)), c => vx =>
        get(Array.get(F32, c, U32.add(base, 3)), d => vy =>
          get(Array.get(F32, d, U32.add(base, 4)), e => +life =>
            get(Array.get(F32, e, U32.add(base, 5)), f => seed =>
              rest(f, respawn(F32.is_le(life, 0.0), Particle{x, y, vx, vy, life, F32.to_u32(seed)}))))))))

def write(buffer: Array<F32>, +base: U32, particle: Particle) -> Array<F32>:
  match particle:
    case Particle{x, y, vx, vy, life, seed}:
      a = Array.set(F32, buffer, base, x)
      b = Array.set(F32, a, U32.add(base, 1), y)
      c = Array.set(F32, b, U32.add(base, 2), vx)
      d = Array.set(F32, c, U32.add(base, 3), vy)
      e = Array.set(F32, d, U32.add(base, 4), life)
      Array.set(F32, e, U32.add(base, 5), U32.to_f32(seed))

@unsafe
def tile_step(more: Bool, fuel: Nat, +rounds: Nat, +enabled: Bool,
    +at: U32, +end: U32, buffer: Array<F32>) -> Array<F32>:
  match more:
    case False{}: buffer
    case True{}:
      +base = U32.mul(at, 8)
      read(buffer, base, a => particle =>
        tile(fuel, rounds, enabled, U32.inc(at), end, write(a, base, integrate(particle, rounds, enabled))))

@unsafe
def tile(fuel: Nat, +rounds: Nat, +enabled: Bool, +at: U32, +end: U32,
    buffer: Array<F32>) -> Array<F32>:
  match fuel:
    case 0n: buffer
    case 1n+p: tile_step(U32.is_lt(at, end), p, rounds, enabled, at, end, buffer)

# Handles are shared only across disjoint particle ranges. Array.join releases
# the extra references; split would allocate/copy, so it is deliberately unused.
@unsafe
def fork(+depth: Nat, +fuel: Nat, +rounds: Nat, +enabled: Bool, +count: U32,
    +index: U32, +chunk: U32, +buffer: Array<F32>) -> Array<F32>:
  match depth:
    case 0n:
      +start = U32.mul(index, chunk)
      tile(fuel, rounds, enabled, start, U32.min(U32.add(start, chunk), count), buffer)
    case 1n+p:
      a b = fork(p, fuel, rounds, enabled, count, index, chunk, buffer)
        fork(p, fuel, rounds, enabled, count, U32.add(index, U32.shln(1, p)), chunk, buffer)
      Array.join(F32, a, b)

def update(tick: UI.Tick, buffer: Array<F32>, +depth: Nat, fuel: Nat,
    rounds: Nat, enabled: Bool) -> Array<F32>:
  match tick:
    case UI.Tick{+count, frame}:
      +jobs = U32.shln(1, depth)
      fork(depth, fuel, rounds, enabled, count, 0, U32.div(U32.add(count, U32.sub(jobs, 1)), jobs), buffer)
