import Base
import ./gpu.bend as B

# Only instrumentation and output conversion use host FFI; layout stays in Bend.
def start(pages: U32, nodes: U32, round: U32) -> IO(Unit):
  import "./gpu-probe.c"

def consume(result: B.Batch) -> IO(Unit):
  import "./gpu-probe.c"
