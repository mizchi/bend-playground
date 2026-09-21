import Base
# "pop until the queue drains" is not writable: recursion has to
# shrink an argument. This is why bfs() in p1.bend carries the cell
# count as fuel and reads the drained bit out of a pair.
#   Error: expected : a decreasing self-call (arguments are read left
#            to right: each passed unchanged until one shrinks)
#          observed : drain.go
def drain.go(+head: U32, +tail: U32, more: Bool) -> U32:
  match more:
    case False{}:
      head
    case True{}:
      drain.go(U32.inc(head), tail, U32.is_lt(U32.inc(head), tail))

def main() -> IO(Unit):
  IO.print(U32.show(drain.go(0, 10, True{})))
