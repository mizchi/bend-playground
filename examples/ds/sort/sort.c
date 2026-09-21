// C twin for msort.bend / bsort.bend / nosort.bend.
//
//   cc -std=c11 -O3 -DDEP=25 -DMODE=0 sort.c -o ./c_merge    // array merge sort
//   cc -std=c11 -O3 -DDEP=25 -DMODE=1 sort.c -o ./c_qsort    // qsort(3)
//   cc -std=c11 -O3 -DDEP=25 -DMODE=2 sort.c -o ./c_nosort   // negative control
//
// Single threaded.  Keys are the same xorshift hash of the index the Bend
// sides use.  MODE=0 is a plain bottom-up merge sort over one input array and
// one scratch array, the shape a C programmer actually writes; nothing is
// slowed down on purpose.
//
// stdout: one line "ok cnt sum isum msum", all uint32
//   ok    1 iff the output is ascending
//   cnt   element count
//   sum   sum of the values      (order-independent)
//   isum  sum of i*v             (order-sensitive)
//   msum  sum of prng(v)         (order-independent multiset hash)
// stderr: whether sum / msum survived the sort, i.e. whether the output
// multiset still equals the input multiset.
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>

#ifndef DEP
#define DEP 25
#endif
#ifndef MODE
#define MODE 0
#endif

static inline uint32_t prng(uint32_t x) {
  x ^= x << 13; x ^= x >> 17; x ^= x << 5; return x;
}
static inline uint32_t key(uint32_t i) { return prng((i + 1u) * 2654435761u); }

static int cmp(const void *p, const void *q) {
  uint32_t x = *(const uint32_t *)p, y = *(const uint32_t *)q;
  return (x > y) - (x < y);
}

int main(void) {
  size_t n = (size_t)1 << DEP;
  uint32_t *a = malloc(n * sizeof(uint32_t));
  uint32_t *b = malloc(n * sizeof(uint32_t));
  if (!a || !b) return 1;

  uint32_t in_sum = 0, in_msum = 0;
  for (size_t i = 0; i < n; i++) {
    uint32_t v = key((uint32_t)i);
    a[i] = v; in_sum += v; in_msum += prng(v);
  }

  uint32_t *s = a;
#if MODE == 0
  uint32_t *src = a, *dst = b;
  for (size_t w = 1; w < n; w *= 2) {
    for (size_t lo = 0; lo < n; lo += 2 * w) {
      size_t mid = lo + w, hi = lo + 2 * w;
      if (mid > n) mid = n;
      if (hi > n) hi = n;
      size_t i = lo, j = mid, k = lo;
      while (i < mid && j < hi) dst[k++] = (src[i] <= src[j]) ? src[i++] : src[j++];
      while (i < mid) dst[k++] = src[i++];
      while (j < hi) dst[k++] = src[j++];
    }
    uint32_t *t = src; src = dst; dst = t;
  }
  s = src;
#elif MODE == 1
  qsort(a, n, sizeof(uint32_t), cmp);
  s = a;
#endif

  uint32_t ok = 1, sum = 0, isum = 0, msum = 0, prev = 0;
  for (uint32_t i = 0; i < (uint32_t)n; i++) {
    uint32_t v = s[i];
    if (prev > v) ok = 0;
    sum += v; isum += i * v; msum += prng(v); prev = v;
  }
  printf("%u %u %u %u %u\n", ok, (uint32_t)n, sum, isum, msum);
  fprintf(stderr, "multiset: sum %s, msum %s\n",
          sum == in_sum ? "kept" : "LOST", msum == in_msum ? "kept" : "LOST");
  return 0;
}
