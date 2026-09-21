// C control #2 for gather.bend: the SAME pointer tree, the same D-level
// descent per lookup. Isolates "tree walk vs array index" from "Bend vs
// C". Nodes come from a bump arena, which is strictly cheaper than what
// Bend's allocator does, and the descent is an iterative loop, which is
// strictly cheaper than recursion.
// Build: cc -std=c11 -O3 -DDEP=22 -DGAT=24 gather_tree.c -o gather_tree
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef DEP
#define DEP 22
#endif
#ifndef GAT
#define GAT 24
#endif

typedef struct T { struct T *a, *b; uint32_t v; } T;

static T* ARENA;
static size_t TOP;

static inline uint32_t hash(uint32_t i) {
  return ((i + 1u) * 2654435761u) ^ (i >> 3);
}

static T* build(uint32_t d, uint32_t i) {
  T* t = &ARENA[TOP++];
  if (d == 0) { t->a = 0; t->v = hash(i); return t; }
  t->a = build(d - 1, i);
  t->b = build(d - 1, i + (1u << (d - 1)));
  return t;
}

static inline uint32_t get(T* t, uint32_t i, uint32_t s) {
  while (t->a) {
    if (i < s) { t = t->a; }
    else       { i -= s; t = t->b; }
    s >>= 1;
  }
  return t->v;
}

int main(void) {
  uint32_t n = 1u << DEP, g = 1u << GAT, m = n - 1u;
  ARENA = malloc((size_t)(2 * n) * sizeof(T));
  if (!ARENA) { printf("oom\n"); return 1; }
  T* r = build(DEP, 0);
  uint32_t t = 0;
  for (uint32_t i = 0; i < g; i++) t += get(r, hash(i) & m, n >> 1);
  printf("%u\n", t);
  return 0;
}
