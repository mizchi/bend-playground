// C twins of m1.bend. Three modes, all single threaded, all printing the
// same checksum as the Bend program:
//   -DMODE=0  open-addressing hash table (what a C programmer writes)
//   -DMODE=1  plain destructive BST, one malloc per insert, freed at the end
//   -DMODE=2  the same BST rebuilt the way an affine language has to: every
//             node on the insert path is malloc'd fresh and the old one is
//             freed. The "same data structure, different runtime" twin.
// Build: cc -std=c11 -O3 -DMODE=0 -DLGK=0 -DLGN=22 m1.c -o bin/m1c_hash
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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
// ---- open addressing, linear probing, power-of-two table ----
static uint32_t *hk, *hv; static uint8_t *hu; static uint32_t hmask;
static void h_init(uint32_t cap) {
  hmask = cap - 1u;
  hk = malloc((size_t)cap * 4); hv = malloc((size_t)cap * 4); hu = calloc(cap, 1);
}
static void h_free(void) { free(hk); free(hv); free(hu); }
static void h_put(uint32_t k, uint32_t v) {
  uint32_t i = (k * 2654435761u) & hmask;
  while (hu[i]) { if (hk[i] == k) { hv[i] = v; return; } i = (i + 1u) & hmask; }
  hu[i] = 1; hk[i] = k; hv[i] = v;
}
static uint32_t h_get(uint32_t k) {
  uint32_t i = (k * 2654435761u) & hmask;
  while (hu[i]) { if (hk[i] == k) return hv[i]; i = (i + 1u) & hmask; }
  return 0;
}
static uint32_t one(uint32_t g, uint32_t n) {
  uint32_t s = (g + 1u) * 2654435761u, cap = 1u; while (cap < 2u * n) cap <<= 1;
  h_init(cap);
  for (uint32_t j = 0; j < n; j++) h_put(key(s, j), j + 1u);
  uint32_t acc = 0;
  for (uint32_t j = 0; j < n; j++) acc += h_get(key(s, j)) * (j * 2654435761u + 1u);
  h_free();
  return acc;
}

#else
// ---- binary search tree ----
typedef struct T { uint32_t k, v; struct T *l, *r; } T;
static T* mk(uint32_t k, uint32_t v) {
  T* t = malloc(sizeof(T)); t->k = k; t->v = v; t->l = 0; t->r = 0; return t;
}
static void kill(T* t) { if (!t) return; kill(t->l); kill(t->r); free(t); }
static uint32_t get(T* t, uint32_t k) {
  while (t) { if (k == t->k) return t->v; t = (k < t->k) ? t->l : t->r; }
  return 0;
}

#if MODE == 1
static T* put(T* t, uint32_t k, uint32_t v) {
  if (!t) return mk(k, v);
  T** p = &t;
  while (*p) { if (k == (*p)->k) { (*p)->v = v; return t; }
               p = (k < (*p)->k) ? &(*p)->l : &(*p)->r; }
  *p = mk(k, v);
  return t;
}
#else
// path copying: a fresh node for every node on the path, the old one freed,
// exactly where Bend's affine types rebuild and free
static T* put(T* t, uint32_t k, uint32_t v) {
  if (!t) return mk(k, v);
  T* n = mk(t->k, t->v);
  if (k == t->k)      { n->k = k; n->v = v; n->l = t->l; n->r = t->r; }
  else if (k < t->k)  { n->l = put(t->l, k, v); n->r = t->r; }
  else                { n->l = t->l;            n->r = put(t->r, k, v); }
  free(t);
  return n;
}
#endif

static uint32_t one(uint32_t g, uint32_t n) {
  uint32_t s = (g + 1u) * 2654435761u;
  T* t = 0;
  for (uint32_t j = 0; j < n; j++) t = put(t, key(s, j), j + 1u);
  uint32_t acc = 0;
  for (uint32_t j = 0; j < n; j++) acc += get(t, key(s, j)) * (j * 2654435761u + 1u);
  kill(t);
  return acc;
}
#endif

int main(void) {
  uint32_t K = 1u << LGK, n = 1u << LGN, acc = 0;
  for (uint32_t g = 0; g < K; g++) acc += one(g, n);
  printf("%u\n", acc);
  return 0;
}
