import Base
import ./gpu-flat.bend as B

# Allocate and initialize the shared output before the timed dispatch.
def start(pages: U32, nodes: U32, round: U32, depth: U32, stride: U32) -> IO(Array<F32>):
  import "./gpu-flat-probe.c"

def consume(result: B.FlatOutput) -> IO(Unit):
  import "./gpu-flat-probe.c"
