import Base

type Tick is Data:
  Tick{width: U32, height: U32, frame: U32}

# Pixels: 0xAABBGGRR, row-major. Rects: four F32 values x/y/w/h per node.
# The native adapter consumes the Array only after the conversion GPU finishes.
type Frame is Type:
  Pixels{width: U32, height: U32, buffer: Array<U32>}
  Rects{count: U32, errors: U32, buffer: Array<F32>}

# max_frames=0 keeps the window open; otherwise it closes after that many draws.
# The reusable callback is evaluated at an IO boundary, so its ! call can use GPU.
def run(width: U32, height: U32, max_frames: U32, draw: Tick -> Frame) -> IO(Unit):
  import "./native.c"
