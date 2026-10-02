#ifndef DEP
#define DEP 19
#endif
#include "batch.h"
static const uint32_t primes[16] = {1009,1013,1019,1021,1031,1033,1039,1049,
                                  1051,1061,1063,1069,1087,1091,1093,1097};
static uint32_t gcd(uint32_t a, uint32_t b) {
  while (b) { uint32_t r = a % b; a = b; b = r; }
  return a;
}
static uint32_t polynomial(uint32_t x, uint32_t n, uint32_t c) {
  return (uint32_t)(((uint64_t)x * x + c) % n);
}
static Result job(uint32_t i, void *context) {
  (void)context;
  uint32_t s = prng(seed(i)), n = primes[s & 15] * primes[(s >> 8) & 15];
  uint32_t x = 2, y = 2, c = 1, g = 1, count = 0;
  for (unsigned fuel = 65536; fuel; --fuel) {
    if (g > 1) {
      if (g == n) { x = y = 2; ++c; g = 1; }
      else {
        uint32_t q = n / g, p = g < q ? g : q, r = g < q ? q : g;
        return (Result){(p * 2654435761u + r) * (i + 1u), count, 0};
      }
    } else {
      x = polynomial(x, n, c);
      y = polynomial(polynomial(y, n, c), n, c);
      g = gcd(x > y ? x - y : y - x, n);
      ++count;
    }
  }
  return (Result){0, count, 1};
}
static void *worker_init(void) { return NULL; }
static void worker_destroy(void *context) { (void)context; }
