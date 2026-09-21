import Base
# The one route the checker leaves open for a frontier-parallel BFS:
# give each fork its own O(N) clone of the distance map, expand both,
# then merge them in a def. This one compiles and runs -- and it
# shows why it is not a way out. The clone is a full pass over N
# cells before the fork and the merge is a full pass after it, so two
# forks pay 2N of bookkeeping to save N/2 of search; and a plain
# cell-wise merge is not even correct, because a distance found by
# the half that did not own the true shortest path is wrong, and
# fixing that needs another BFS.
#
# Contrast probes/a_fork_shared_array.bend, which is the cheap shape,
# and is rejected.
#|ok
type St is Type:
  St{d: Array<U32>}

def half(st: St, +i: U32) -> St:
  St{d} = st
  St{d[i] <- i}

def merge(x: St, y: St) -> St:
  St{a} = x
  St{b} = y
  St{a}

def probe.fork(d1: Array<U32>, d2: Array<U32>) -> St:
  x y = half(St{d1}, 0) half(St{d2}, 1)
  merge(x, y)

def probe.split(r: Array<U32> & Array<U32>) -> St:
  (d1, d2) = r
  probe.fork(d1, d2)

def probe(d: Array<U32>) -> St:
  probe.split(Array.clone(U32, d))

def show(st: St) -> String:
  St{d} = st
  "ok"

def main() -> IO(Unit):
  IO.print(show(probe(Array.new(U32, 4n, 7))))
