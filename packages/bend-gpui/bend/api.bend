import Base

type Tick is Data:
  Tick{width: U32, height: U32, frame: U32}

# Pixels: 0xAABBGGRR, row-major. Rects: four F32 values x/y/w/h per node.
# The native adapter consumes the Array only after the conversion GPU finishes.
type Frame is Type:
  Pixels{width: U32, height: U32, buffer: Array<U32>}
  Rects{count: U32, errors: U32, buffer: Array<F32>}

# Power-of-two capacity for at most 2048*2048 cells; 0 and 1 use depth 0.
def capacity_step(more: Bool, depth: Nat, rest: Unit -> Nat) -> Nat:
  match more:
    case False{}: depth
    case True{}: rest(Unit{})

def capacity_go(fuel: Nat, +n: U32, +size: U32, +depth: Nat) -> Nat:
  match fuel:
    case 0n: depth
    case 1n+p:
      capacity_step(U32.is_lt(size, n), depth, u => capacity_go(p, n, U32.mul(size, 2), 1n+depth))

def capacity(n: U32) -> Nat:
  capacity_go(22n, n, 1, 0n)

# A resize-aware solid pixel frame; alpha is ignored by the NV12 surface.
def pixels(+width: U32, +height: U32, color: U32) -> Frame:
  Pixels{width, height, Array.new(U32, capacity(U32.mul(width, height)), color)}

# max_frames=0 keeps the window open; otherwise it closes after that many draws.
# The reusable callback is evaluated at an IO boundary, so its ! call can use GPU.
def run(width: U32, height: U32, max_frames: U32, draw: Tick -> Frame) -> IO(Unit):
  import "./native.c"
