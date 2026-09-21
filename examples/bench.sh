#!/bin/bash
# best-of-3 wall clock, in seconds
best() {
  local b=999
  for i in 1 2 3; do
    local s=$(python3 -c 'import time,subprocess,sys
t=time.perf_counter(); subprocess.run(sys.argv[1:],stdout=subprocess.DEVNULL); print(f"{time.perf_counter()-t:.3f}")' "$@")
    b=$(python3 -c "print(min($b,$s))")
  done
  echo "$b"
}
