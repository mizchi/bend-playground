#include "kernel.h"

__attribute__((noinline)) uint32_t ffi_kernel(uint32_t x, uint32_t rounds) {
  for (uint32_t i = 0; i < rounds; ++i) {
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
  }
  return x;
}
