import Base
import ./api.bend as UI

def color(+x: U32, +y: U32, +frame: U32) -> U32:
  r = U32.mod(U32.add(x, U32.mul(frame, 3)), 256)
  g = U32.mod(U32.add(U32.mul(y, 2), frame), 256)
  b = U32.xor(U32.div(x, 16), U32.div(y, 16))
  U32.or(4278190080, U32.or(r, U32.or(U32.shln(g, 8n), U32.shln(U32.mod(U32.mul(b, 37), 256), 16n))))

@unsafe
def tile_step(more: Bool, fuel: Nat, +width: U32, +height: U32, +frame: U32,
    +at: U32, +end: U32, buffer: Array<U32>) -> Array<U32>:
  match more:
    case False{}: buffer
    case True{}:
      tile(fuel, width, height, frame, U32.inc(at), end,
        Array.set(U32, buffer, at, color(U32.mod(at, width), U32.div(at, width), frame)))

@unsafe
def tile(fuel: Nat, +width: U32, +height: U32, +frame: U32,
    +at: U32, +end: U32, buffer: Array<U32>) -> Array<U32>:
  match fuel:
    case 0n: buffer
    case 1n+p:
      tile_step(U32.is_lt(at, end), p, width, height, frame, at, end, buffer)

# 256 independent jobs, each a flat loop, sharing disjoint slices.
@unsafe
def fork(+depth: Nat, +width: U32, +height: U32, +frame: U32,
    +index: U32, +chunk: U32, +buffer: Array<U32>) -> Array<U32>:
  match depth:
    case 0n:
      +start = U32.mul(index, chunk)
      tile(16385n, width, height, frame, start,
        U32.min(U32.add(start, chunk), U32.mul(width, height)), buffer)
    case 1n+p:
      a b = fork(p, width, height, frame, index, chunk, buffer)
        fork(p, width, height, frame, U32.add(index, U32.shln(1, p)), chunk, buffer)
      Array.join(U32, a, b)

def frame(tick: UI.Tick) -> UI.Frame:
  match tick:
    case UI.Tick{+width, +height, frame}:
      +count = U32.mul(width, height)
      buffer = Array.new(U32, UI.capacity(count), 0)
      UI.Pixels{width, height, fork(8n, width, height, frame, 0,
        U32.div(U32.add(count, 255), 256), buffer)}
