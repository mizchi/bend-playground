import Base

type Tick is Data:
  Tick{count: U32, frame: U32}

# State is one packed, power-of-two Array of eight F32 words per particle:
# x/y/vx/vy/lifetime/24-bit RNG state/reserved/reserved.
# The callback consumes and returns the same allocation. Native drawing borrows
# it until the GPU finishes; the next callback then receives sole ownership.
def run(width: U32, height: U32, count: U32, max_frames: U32,
    update: Tick -> Array<F32> -> Array<F32>) -> IO(Unit):
  import "./native.c"
