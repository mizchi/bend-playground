#include "kernel.h"
#include <stdio.h>

#ifndef CALLS
#define CALLS 1048576
#endif
#ifndef ROUNDS
#define ROUNDS 1
#endif

int main(void) {
  uint32_t x = 305419896u;
  for (uint32_t i = 0; i < CALLS; ++i) x = ffi_kernel(x, ROUNDS);
  printf("checksum=%u\n", x);
  return 0;
}
