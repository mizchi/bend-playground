#ifndef DEP
#define DEP 14
#endif
#ifndef SIZE
#define SIZE 9
#endif
#include "batch.h"
#if SIZE < 1 || SIZE > 14
#error astfold requires SIZE=1..14
#endif

enum { CONSTANT, VARIABLE, ADD, MULTIPLY };
typedef struct { uint32_t tag, value, left, right; } Node;
typedef struct { Node *nodes; uint32_t used; } Arena;
typedef struct { uint32_t value, nodes; } Stats;

static uint32_t generate(Arena *arena, unsigned depth, uint32_t s) {
  uint32_t i = arena->used++;
  Node *node = &arena->nodes[i];
  if (!depth) {
    node->tag = (s & 3) == 0 ? VARIABLE : CONSTANT;
    node->value = (s >> 8) & (node->tag == VARIABLE ? 3 : 15);
  } else {
    node->tag = (s & 1) == 0 ? ADD : MULTIPLY;
    node->left = generate(arena, depth - 1, prng(s));
    node->right = generate(arena, depth - 1, prng(s ^ 277803737u));
  }
  return i;
}

static uint32_t fold(Arena *arena, uint32_t i) {
  Node *node = &arena->nodes[i];
  if (node->tag <= VARIABLE) return i;
  node->left = fold(arena, node->left);
  node->right = fold(arena, node->right);
  Node *a = &arena->nodes[node->left], *b = &arena->nodes[node->right];
  if (a->tag == CONSTANT && b->tag == CONSTANT) {
    node->value = node->tag == ADD ? a->value + b->value : a->value * b->value;
    node->tag = CONSTANT;
  } else if (node->tag == ADD) {
    if (a->tag == CONSTANT && a->value == 0) return node->right;
    if (b->tag == CONSTANT && b->value == 0) return node->left;
  } else {
    if ((a->tag == CONSTANT && a->value == 0) || (b->tag == CONSTANT && b->value == 0)) {
      node->tag = CONSTANT; node->value = 0;
    } else {
      if (a->tag == CONSTANT && a->value == 1) return node->right;
      if (b->tag == CONSTANT && b->value == 1) return node->left;
    }
  }
  return i;
}

static Stats inspect(Arena *arena, uint32_t i) {
  Node *node = &arena->nodes[i];
  static const uint32_t values[4] = {2, 3, 5, 7};
  if (node->tag == CONSTANT) return (Stats){node->value, 1};
  if (node->tag == VARIABLE) return (Stats){values[node->value], 1};
  Stats a = inspect(arena, node->left), b = inspect(arena, node->right);
  return (Stats){node->tag == ADD ? a.value + b.value : a.value * b.value, 1 + a.nodes + b.nodes};
}

static Result job(uint32_t i, void *context) {
  Arena *arena = context;
  arena->used = 0;
  uint32_t root = generate(arena, SIZE, seed(i));
  root = fold(arena, root);
  Stats stats = inspect(arena, root);
  return (Result){stats.value * (i + 1u), stats.nodes, 0};
}
static void *worker_init(void) {
  Arena *arena = malloc(sizeof(*arena));
  if (!arena) { perror("arena allocation"); exit(1); }
  arena->nodes = malloc(sizeof(Node) * ((1u << (SIZE + 1)) - 1));
  if (!arena->nodes) { perror("node allocation"); exit(1); }
  return arena;
}
static void worker_destroy(void *context) {
  Arena *arena = context;
  free(arena->nodes);
  free(arena);
}
