// C twin #1 of fw.bend: idiomatic in-place array FWHT. This is what a C
// programmer actually writes -- no allocation after the input buffer.
// Butterfly order mirrors the Bend recursion: stride 1 first (deepest
// subtrees), doubling up to n/2 (the root).
// Build: cc -std=c11 -O3 fw_arr.c -o fw_arr
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef DEP
#define DEP 20
#endif

int main(void) {
  uint32_t n = 1u << DEP;
  uint32_t* a = malloc((size_t)n * 4);
  for (uint32_t i = 0; i < n; i++) a[i] = ((i + 1u) * 2654435761u) ^ (i >> 3);
  for (uint32_t len = 1; len < n; len <<= 1)
    for (uint32_t i = 0; i < n; i += len << 1)
      for (uint32_t j = i; j < i + len; j++) {
        uint32_t u = a[j], v = a[j + len];
        a[j] = u + v;
        a[j + len] = u - v;
      }
  uint32_t t = 0;
  for (uint32_t i = 0; i < n; i++) t += a[i] * (i * 2654435761u + 1u);
  printf("%u\n", t);
  free(a);
  return 0;
}
