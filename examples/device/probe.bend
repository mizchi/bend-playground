import Base

def begin(jobs: U32, calls: U32, round: U32) -> IO(U32):
  import "./probe.c"

# CPU consumes one scalar result and supplies the next batch's offset.
def next(checksum: U32) -> IO(U32):
  import "./probe.c"

def finish() -> IO(Unit):
  import "./probe.c"
