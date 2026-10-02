import Base
import ./api.bend as UI
import ./simulation.bend as Physics

# The reference module owns the physics and array layout. These statically
# called readers thread the linear array handle without runtime callbacks.
def load_seed(result: Array<F32> & F32, x: F32, y: F32, vx: F32, vy: F32,
    +life: F32) -> Array<F32> & Physics.Particle:
  (buffer, seed) = result
  (buffer, Physics.respawn(F32.is_le(life, 0.0),
    Physics.Particle{x, y, vx, vy, life, F32.to_u32(seed)}))

def load_life(result: Array<F32> & F32, base: U32, x: F32, y: F32, vx: F32,
    vy: F32) -> Array<F32> & Physics.Particle:
  (buffer, life) = result
  load_seed(Array.get(F32, buffer, U32.add(base, 5)), x, y, vx, vy, life)

def load_vy(result: Array<F32> & F32, +base: U32, x: F32, y: F32,
    vx: F32) -> Array<F32> & Physics.Particle:
  (buffer, vy) = result
  load_life(Array.get(F32, buffer, U32.add(base, 4)), base, x, y, vx, vy)

def load_vx(result: Array<F32> & F32, +base: U32, x: F32,
    y: F32) -> Array<F32> & Physics.Particle:
  (buffer, vx) = result
  load_vy(Array.get(F32, buffer, U32.add(base, 3)), base, x, y, vx)

def load_y(result: Array<F32> & F32, +base: U32,
    x: F32) -> Array<F32> & Physics.Particle:
  (buffer, y) = result
  load_vx(Array.get(F32, buffer, U32.add(base, 2)), base, x, y)

def load_x(result: Array<F32> & F32, +base: U32) -> Array<F32> & Physics.Particle:
  (buffer, x) = result
  load_y(Array.get(F32, buffer, U32.add(base, 1)), base, x)

def read(buffer: Array<F32>, +base: U32) -> Array<F32> & Physics.Particle:
  load_x(Array.get(F32, buffer, base), base)

def advance(result: Array<F32> & Physics.Particle, base: U32, rounds: Nat,
    enabled: Bool) -> Array<F32>:
  (buffer, particle) = result
  Physics.write(buffer, base, Physics.integrate(particle, rounds, enabled))

# Exact range length removes the tile -> callback -> tile recursion cycle.
def tile(fuel: Nat, +rounds: Nat, +enabled: Bool, +at: U32,
    buffer: Array<F32>) -> Array<F32>:
  match fuel:
    case 0n: buffer
    case 1n+p:
      +base = U32.mul(at, 8)
      tile(p, rounds, enabled, U32.inc(at), advance(read(buffer, base), base, rounds, enabled))

# As in the reference, only disjoint ranges share array handles. Array.join
# releases the extra references. Empty jobs receive zero iterations.
@unsafe
def fork(+depth: Nat, +rounds: Nat, +enabled: Bool, +count: U32,
    +index: U32, +chunk: U32, +buffer: Array<F32>) -> Array<F32>:
  match depth:
    case 0n:
      +start = U32.min(U32.mul(index, chunk), count)
      end = U32.min(U32.add(start, chunk), count)
      tile(U32.to_nat(U32.sub(end, start)), rounds, enabled, start, buffer)
    case 1n+p:
      a b = fork(p, rounds, enabled, count, index, chunk, buffer)
        fork(p, rounds, enabled, count, U32.add(index, U32.shln(1, p)), chunk, buffer)
      Array.join(F32, a, b)

# Keep the reference update contract. The supplied upper-bound fuel is unused
# because each leaf derives its exact iteration count from its particle range.
def update(tick: UI.Tick, buffer: Array<F32>, +depth: Nat, fuel: Nat,
    rounds: Nat, enabled: Bool) -> Array<F32>:
  match tick:
    case UI.Tick{+count, frame}:
      +jobs = U32.shln(1, depth)
      fork(depth, rounds, enabled, count, 0, U32.div(U32.add(count, U32.sub(jobs, 1)), jobs), buffer)
