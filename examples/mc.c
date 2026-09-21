// Native C twin of mc.bend: same LCG, same branchless hit test, same
// leaf seeding and the same tree order (addition is associative, so a
// flat loop gives the identical u32 sum).
// Build: cc -std=c11 -O3 mc.c -o mc_c
#include <stdint.h>
#include <stdio.h>

#ifndef DEP
#define DEP 20
#endif
#ifndef PER
#define PER 4096
#endif

static inline uint32_t lcg(uint32_t s) { return s * 1664525u + 1013904223u; }

static uint32_t leaf(uint32_t i, uint32_t k) {
  uint32_t s = ((i + 1u) * 2654435761u) ^ 1013904223u;
  uint32_t acc = 0;
  for (uint32_t n = 0; n < k; n++) {
    uint32_t s1 = lcg(s);
    uint32_t s2 = lcg(s1);
    uint32_t x = s1 >> 17;
    uint32_t y = s2 >> 17;
    uint32_t q = x * x + y * y;
    acc += (q < 1073741824u);
    s = s2;
  }
  return acc;
}

int main(void) {
  uint32_t n = 1u << DEP;
  uint32_t t = 0;
  for (uint32_t i = 0; i < n; i++) t += leaf(i, PER);
  printf("%u\n", t);
  return 0;
}
