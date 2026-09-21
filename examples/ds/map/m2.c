// C twins of m2.bend. Single threaded; both print the same two lines
// (checksum, ok) as the Bend program.
//   -DMODE=0  array binary min-heap (what a C programmer writes)
//   -DMODE=1  the same skew heap as the Bend program, nodes malloc'd and
//             freed exactly where Bend's affine types allocate and free
// The keys are distinct, so the pop order is unique and both modes and
// Bend must agree bit for bit.
// Build: cc -std=c11 -O3 -DMODE=0 -DLGK=0 -DLGN=22 m2.c -o bin/m2c_bheap
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef LGK
#define LGK 0
#endif
#ifndef LGN
#define LGN 22
#endif
#ifndef MODE
#define MODE 0
#endif

static inline uint32_t prng(uint32_t x) {
  x ^= x << 13; x ^= x >> 17; x ^= x << 5; return x;
}
static inline uint32_t key(uint32_t s, uint32_t j) {
  return prng(((j + 1u) * 2654435761u) ^ (s * 340573321u));
}

#if MODE == 0
static uint32_t *hp; static uint32_t hn;
static void push(uint32_t k) {
  uint32_t i = hn++;
  while (i) { uint32_t p = (i - 1u) >> 1; if (hp[p] <= k) break; hp[i] = hp[p]; i = p; }
  hp[i] = k;
}
static uint32_t pop(void) {
  uint32_t top = hp[0], last = hp[--hn], i = 0;
  for (;;) {
    uint32_t c = 2u * i + 1u;
    if (c >= hn) break;
    if (c + 1u < hn && hp[c + 1u] < hp[c]) c++;
    if (hp[c] >= last) break;
    hp[i] = hp[c]; i = c;
  }
  if (hn) hp[i] = last;
  return top;
}
#else
typedef struct S { uint32_t k; struct S *l, *r; } S;
static S* mk(uint32_t k) { S* s = malloc(sizeof(S)); s->k = k; s->l = s->r = 0; return s; }
static S* mrg(S* a, S* b) {
  if (!a) return b;
  if (!b) return a;
  if (a->k > b->k) { S* t = a; a = b; b = t; }
  S* nr = mrg(a->r, b);
  a->r = a->l; a->l = nr;          // skew: merge into the right, then swap
  return a;
}
static S* root;
static void push(uint32_t k) { root = mrg(root, mk(k)); }
static uint32_t pop(void) {
  S* t = root; uint32_t k = t->k;
  root = mrg(t->l, t->r);
  free(t);
  return k;
}
#endif

int main(void) {
  uint32_t K = 1u << LGK, n = 1u << LGN, acc = 0, ok = 1;
#if MODE == 0
  hp = malloc((size_t)n * 4);
#endif
  for (uint32_t g = 0; g < K; g++) {
    uint32_t s = (g + 1u) * 2654435761u;
#if MODE == 0
    hn = 0;
#else
    root = 0;
#endif
    for (uint32_t j = 0; j < n; j++) push(key(s, j));
    uint32_t prev = 0, a = 0, o = 1;
    for (uint32_t i = 0; i < n; i++) {
      uint32_t k = pop();
      a += k * (i * 2654435761u + 1u);
      o *= (prev <= k);
      prev = k;
    }
    acc += a; ok *= o;
  }
  printf("%u\n%u\n", acc, ok);
  return 0;
}
