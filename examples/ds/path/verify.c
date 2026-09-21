// Algorithm-independent check of the BFS the two programs run. It
// redoes the search (the same code as the twins) and then, instead of
// trusting the queue, tests the distance map against the definition
// of a graph distance on the open subgraph rooted at cell 0:
//   A  only open cells are reached, and cell 0 is reached at 0
//   B  every reached cell but 0 has an open neighbour one nearer
//         (so no distance is too small)
//   C  every open neighbour of a reached cell is itself reached
//         (so the reached set is closed: nothing was missed)
//   D  no open neighbour of a reached cell is more than one further
//         (so no distance is too large)
// B and D pin each distance to the true one; A and C pin the reached
// set. It prints the same checksum the twins print, so a pass binds
// the invariants to the number that is reported. It also prints the
// cell census, because P1 and P2 walk the same number of cells but
// not the same number of pops: a 16384 x 16384 grid at 70% open is
// above the site-percolation threshold, so one giant component takes
// almost every open cell, while a 32 x 32 grid reached from its
// corner takes only part of its own.
//   cc -std=c11 -O3 -DWB=14 -DHB=14 -DDEPTH=0  verify.c -o verify_p1
//   cc -std=c11 -O3 -DWB=5  -DHB=5  -DDEPTH=18 verify.c -o verify_p2
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef WB
#define WB 5
#endif
#ifndef HB
#define HB 5
#endif
#ifndef DEPTH
#define DEPTH 0
#endif

#define W ((uint32_t)1u << WB)
#define WMASK (W - 1u)
#define HMASK (((uint32_t)1u << HB) - 1u)
#define CELLS ((uint32_t)1u << (WB + HB))
#define UNSEEN 0xFFFFFFFFu

static uint32_t *g, *q, *d;
static uint32_t head, tail;
static long bad_a, bad_b, bad_c, bad_d;
static long reached_all, cells_all, open_all;

static uint32_t word_prng(uint32_t x) {
  uint32_t b = x ^ (x << 13u);
  uint32_t e = b ^ (b >> 17u);
  return e ^ (e << 5u);
}

static uint32_t cell_open(uint32_t s, uint32_t c) {
  uint32_t h = word_prng(s ^ ((c + 1u) * 340573321u));
  return c == 0u || h % 100u >= 30u;
}

static void bfs_look(uint32_t n, uint32_t v, int inb) {
  if (inb && g[n] != 0u && d[n] == UNSEEN) {
    d[n] = v;
    q[tail] = n;
    tail += 1u;
  }
}

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

// the four in-bounds neighbours of c, written into nb; the count back
static int nbrs(uint32_t c, uint32_t *nb) {
  uint32_t x = c & WMASK, y = c >> WB;
  int k = 0;
  if (x > 0u) nb[k++] = c - 1u;
  if (x < WMASK) nb[k++] = c + 1u;
  if (y > 0u) nb[k++] = c - W;
  if (y < HMASK) nb[k++] = c + W;
  return k;
}

static void check(void) {
  if (d[0] != 0u || g[0] == 0u) bad_a++;
  cells_all += CELLS;
  for (uint32_t c = 0u; c < CELLS; ++c) {
    reached_all += d[c] != UNSEEN;
    open_all += g[c] != 0u;
  }
  for (uint32_t c = 0u; c < CELLS; ++c) {
    if (d[c] == UNSEEN) continue;
    if (g[c] == 0u) { bad_a++; continue; }
    uint32_t nb[4];
    int k = nbrs(c, nb), nearer = 0;
    for (int i = 0; i < k; ++i) {
      uint32_t n = nb[i];
      if (g[n] == 0u) continue;
      if (d[n] == UNSEEN) { bad_c++; continue; }
      if (d[n] + 1u == d[c]) nearer = 1;
      if (d[n] > d[c] + 1u) bad_d++;
    }
    if (c != 0u && !nearer) bad_b++;
  }
}

static uint32_t maze_run(uint32_t m) {
  uint32_t s = (m + 1u) * 2654435761u;
  for (uint32_t c = 0u; c < CELLS; ++c) {
    g[c] = cell_open(s, c);
    d[c] = UNSEEN;
    q[c] = 0u;
  }
  d[0] = 0u;
  head = 0u;
  tail = 1u;
  while (head < tail) bfs_pop();
  check();
  return bfs_fold();
}

static uint32_t batch_run(uint32_t k, uint32_t i) {
  if (k == 0u) return maze_run(i);
  uint32_t a = batch_run(k - 1u, i);
  uint32_t b = batch_run(k - 1u, i + (1u << (k - 1u)));
  return a + b;
}

int main(void) {
  g = malloc((size_t)CELLS * 4);
  q = malloc((size_t)CELLS * 4);
  d = malloc((size_t)CELLS * 4);
  uint32_t sum = batch_run(DEPTH, 0u);
  printf("checksum %u  cells %ld  open %ld  reached %ld (%.1f%% of cells, "
         "%.1f%% of open)  A=%ld B=%ld C=%ld D=%ld  %s\n",
         sum, cells_all, open_all, reached_all,
         100.0 * reached_all / cells_all, 100.0 * reached_all / open_all,
         bad_a, bad_b, bad_c, bad_d,
         (bad_a | bad_b | bad_c | bad_d) == 0 ? "OK" : "VIOLATION");
  return 0;
}
