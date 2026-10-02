#ifndef SIZE
#define SIZE 15
#endif
#define JOB_CHUNK 1
#include "batch.h"
#if DEP != 8 || SIZE < 4 || SIZE > 16
#error nqueens requires DEP=8 and SIZE=4..16
#endif

static uint32_t search(uint32_t mask, uint32_t cols, uint32_t left, uint32_t right) {
  if (cols == mask) return 1;
  uint32_t available = mask & ~(cols | left | right), count = 0;
  while (available) {
    uint32_t bit = available & (0u - available);
    available ^= bit;
    count += search(mask, cols | bit, ((left | bit) << 1) & mask, (right | bit) >> 1);
  }
  return count;
}
static Result job(uint32_t i, void *context) {
  (void)context;
  uint32_t c0 = i & 15, c1 = i >> 4;
  uint32_t a = 1u << c0, b = 1u << c1, mask = (1u << SIZE) - 1;
  if (c0 >= SIZE || c1 >= SIZE || (b & (a | (a << 1) | (a >> 1)))) return (Result){0};
  uint32_t cols = a | b, left = (((a << 1) | b) << 1) & mask, right = ((a >> 1) | b) >> 1;
  return (Result){search(mask, cols, left, right), 0, 0};
}
static void *worker_init(void) { return NULL; }
static void worker_destroy(void *context) { (void)context; }
