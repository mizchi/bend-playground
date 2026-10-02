#ifndef DEP
#define DEP 12
#endif
#ifndef SIZE
#define SIZE 24
#endif
#if SIZE < 3 || SIZE > 32
#error SIZE must be in 3..32
#endif
#include "batch.h"
#include "sat-core.h"

static uint32_t avoid(uint32_t c, uint32_t a, uint32_t b) {
  return (c == a || c == b) ? (c + 1u) % SIZE : c;
}
static Result job(uint32_t i, void *context) {
  (void)context;
  Clause clauses[SIZE * 17 / 4];
  uint32_t s = seed(i);
  for (unsigned j = 0; j < SIZE * 17 / 4; ++j) {
    uint32_t a = s % SIZE, b = (a + 1u + ((s >> 8) % (SIZE - 1))) % SIZE;
    uint32_t c = avoid(avoid((s >> 16) % SIZE, a, b), a, b);
    uint32_t ba = 1u << a, bb = 1u << b, bc = 1u << c;
    uint32_t pos = ((s & 16777216u) ? ba : 0) | ((s & 33554432u) ? bb : 0) | ((s & 67108864u) ? bc : 0);
    clauses[j] = (Clause){pos, (ba | bb | bc) ^ pos};
    s = prng(s);
  }
  Answer answer = sat_solve(clauses, SIZE * 17 / 4, 0, 0);
  return (Result){answer.sat ? (answer.model + 2654435761u) * (i + 1u) : 0, answer.nodes,
                  answer.errors || (answer.sat && !sat_holds(clauses, SIZE * 17 / 4, answer.model))};
}
static void *worker_init(void) { return NULL; }
static void worker_destroy(void *context) { (void)context; }
