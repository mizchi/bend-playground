// C twin #2 of fw.bend: the SAME tree shape as the Bend program, so the
// only difference left is the runtime, not the data structure. Nodes are
// malloc'd and freed exactly where Bend's affine types free them -- a
// bump arena with no free would need ~19 GB at d=24, which is itself the
// point: the C programmer has to write the frees Bend infers.
// Build: cc -std=c11 -O3 fw_tree.c -o fw_tree
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef DEP
#define DEP 20
#endif

typedef struct T { struct T *a, *b; uint32_t v; } T;

static inline T* leaf(uint32_t v) { T* t = malloc(sizeof(T)); t->a = 0; t->v = v; return t; }
static inline T* node(T* a, T* b) { T* t = malloc(sizeof(T)); t->a = a; t->b = b; return t; }

static T* mk(uint32_t d, uint32_t i) {
  if (d == 0) return leaf(((i + 1u) * 2654435761u) ^ (i >> 3));
  return node(mk(d - 1, i), mk(d - 1, i + (1u << (d - 1))));
}

// one pass returning (x+y, x-y), exactly as bfly in fw.bend
static void bfly(T* x, T* y, T** p, T** m) {
  if (!x->a) {
    *p = leaf(x->v + y->v); *m = leaf(x->v - y->v);
    free(x); free(y); return;
  }
  T *pa, *ma, *pb, *mb;
  bfly(x->a, y->a, &pa, &ma);
  bfly(x->b, y->b, &pb, &mb);
  *p = node(pa, pb);
  *m = node(ma, mb);
  free(x); free(y);
}

static T* fwht(T* t) {
  if (!t->a) return t;
  T* a = fwht(t->a);
  T* b = fwht(t->b);
  T *p, *m;
  bfly(a, b, &p, &m);
  free(t);
  return node(p, m);
}

static uint32_t mix(T* t, uint32_t i, uint32_t s) {
  if (!t->a) { uint32_t r = t->v * (i * 2654435761u + 1u); free(t); return r; }
  uint32_t r = mix(t->a, i, s >> 1) + mix(t->b, i + s, s >> 1);
  free(t);
  return r;
}

int main(void) {
  T* r = fwht(mk(DEP, 0));
  printf("%u\n", mix(r, 0, 1u << (DEP - 1)));
  return 0;
}
