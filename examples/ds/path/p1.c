// Native C twin of p1.bend: breadth-first search over ONE W x H grid
// maze, single-threaded, 1-to-1 with the Bend program: same seed and
// wall hash, a flat uint32 grid (1 open, 0 wall), a flat uint32 queue
// with head and tail, a flat uint32 distance map seeded unseen, the
// textbook pop loop with four bounds-checked neighbour looks, and the
// same position-weighted fold sealed by the reached count.
//   cc -std=c11 -O3 -DWB=14 -DHB=14 p1.c -o p1_c
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef WB
#define WB 14
#endif
#ifndef HB
#define HB 14
#endif

#define W ((uint32_t)1u << WB)
#define WMASK (W - 1u)
#define HMASK (((uint32_t)1u << HB) - 1u)
#define CELLS ((uint32_t)1u << (WB + HB))
#define UNSEEN 0xFFFFFFFFu

static uint32_t *g, *q, *d;
static uint32_t head, tail;

static uint32_t word_prng(uint32_t x) {
  uint32_t b = x ^ (x << 13u);
  uint32_t e = b ^ (b >> 17u);
  return e ^ (e << 5u);
}

// 1 when cell c of the maze seeded s is open: the start always, any
// other cell when its hash mod 100 is 30 or more (30% walls)
static uint32_t cell_open(uint32_t s, uint32_t c) {
  uint32_t h = word_prng(s ^ ((c + 1u) * 340573321u));
  return c == 0u || h % 100u >= 30u;
}

// one neighbour n at distance v: skip it out of bounds, a wall or
// seen; else stamp its distance and push it
static void bfs_look(uint32_t n, uint32_t v, int inb) {
  if (inb && g[n] != 0u && d[n] == UNSEEN) {
    d[n] = v;
    q[tail] = n;
    tail += 1u;
  }
}

// one pop: the head cell and its distance, then its four neighbours
static void bfs_pop(void) {
  uint32_t c = q[head];
  uint32_t v = d[c] + 1u;
  uint32_t x = c & WMASK;
  uint32_t y = c >> WB;
  head += 1u;
  bfs_look(c - 1u, v, x > 0u);
  bfs_look(c + 1u, v, x < WMASK);
  bfs_look(c - W, v, y > 0u);
  bfs_look(c + W, v, y < HMASK);
}

// the checksum: a reached cell mixes its distance position-weighted
// and counts one; the count seals the mix
static uint32_t bfs_fold(void) {
  uint32_t acc = 0u, cnt = 0u;
  for (uint32_t c = 0u; c < CELLS; ++c) {
    uint32_t v = d[c];
    uint32_t hit = v != UNSEEN;
    acc = (acc * 2654435761u) ^ (hit ? v * (c + 1u) : 0u);
    cnt += hit;
  }
  return acc ^ (cnt * 2246822519u);
}

// the whole search: fill the grid, seed the queue with cell 0 at
// distance 0, search, fold
static uint32_t solve(uint32_t m) {
  uint32_t s = (m + 1u) * 2654435761u;
  for (uint32_t c = 0u; c < CELLS; ++c) {
    g[c] = cell_open(s, c);
    d[c] = UNSEEN;
    q[c] = 0u;
  }
  d[0] = 0u;
  head = 0u;
  tail = 1u;
  while (head < tail) {
    bfs_pop();
  }
  return bfs_fold();
}

int main(void) {
  g = malloc((size_t)CELLS * 4);
  q = malloc((size_t)CELLS * 4);
  d = malloc((size_t)CELLS * 4);
  printf("%u\n", solve(0u));
  return 0;
}
