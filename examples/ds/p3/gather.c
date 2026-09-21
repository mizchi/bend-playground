// C control #1 for gather.bend: the same hash, the same mask, the same
// number of lookups -- but into a flat array, so a lookup is one index
// instead of a D-level tree walk. This is the bar.
// Build: cc -std=c11 -O3 -DDEP=22 -DGAT=24 gather.c -o gather_c
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef DEP
#define DEP 22
#endif
#ifndef GAT
#define GAT 24
#endif

static inline uint32_t hash(uint32_t i) {
  return ((i + 1u) * 2654435761u) ^ (i >> 3);
}

int main(void) {
  uint32_t n = 1u << DEP, g = 1u << GAT, m = n - 1u;
  uint32_t* a = malloc((size_t)n * 4);
  for (uint32_t i = 0; i < n; i++) a[i] = hash(i);
  uint32_t t = 0;
  for (uint32_t i = 0; i < g; i++) t += a[hash(i) & m];
  printf("%u\n", t);
  free(a);
  return 0;
}
