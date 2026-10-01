// C twin of mcts.bend: Monte Carlo tree search (UCT) for tic-tac-toe with
// root parallelization. A player grows 2^DEP independent trees of ITERS
// iterations each from the position, sums the visit counts of the root's
// children over the trees and plays the most visited cell (lowest on a
// tie). One iteration expands the lowest untried legal cell of the first
// node met that has one, else descends to the child of highest UCT value
// w / (2 n) + 1.4 sqrt(ln N / n), then plays one random playout from the
// new node and adds each node's score (win 2, draw 1, loss 0 for the side
// that moved into it) along the path. Prints the root visits of the empty
// board, then 2^GAMES games against a uniformly random player, as
// fmc.c does; the same arithmetic as the Bend source, so those two lines
// match it. With --audit (C only): the player against exact minimax.
// Build: cc -std=c11 -O3 -ffp-contract=off -DDEP=4 -DITERS=576 -DGAMES=8 mcts.c -lm
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef DEP
#define DEP 4       // 2^DEP trees per move
#endif
#ifndef ITERS
#define ITERS 576   // iterations per tree: 16 x 576 = 9216 playouts a move
#endif
#ifndef GAMES
#define GAMES 8     // 2^GAMES games against the random player
#endif

#define FULL 511u
#define ONGOING 3u  // status: 0 X won, 1 draw, 2 O won, 3 not over

static uint32_t prng(uint32_t x) {
  uint32_t b = x ^ (x << 13);
  uint32_t d = b ^ (b >> 17);
  return d ^ (d << 5);
}

static uint32_t mix(uint32_t a, uint32_t b) {
  return prng(((a + 1) * 2654435761u) ^ ((b + 1) * 2246822519u));
}

static const uint32_t LINES[8] = {7, 56, 448, 73, 146, 292, 273, 84};

static uint32_t won(uint32_t m) {
  uint32_t w = 0;
  for (int i = 0; i < 8; i++) w |= (m & LINES[i]) == LINES[i];
  return w;
}

static uint32_t status(uint32_t x, uint32_t o) {
  return won(x) ? 0 : won(o) ? 2 : (x | o) == FULL ? 1 : ONGOING;
}

static uint32_t popcount(uint32_t e) {
  uint32_t n = 0;
  for (int i = 0; i < 9; i++) n += (e >> i) & 1;
  return n;
}

static uint32_t nth(uint32_t e, uint32_t k) {
  for (uint32_t bit = 1; bit < 512; bit <<= 1) {
    uint32_t set = (e & bit) != 0;
    if (set && k == 0) return bit;
    k -= set;
  }
  return 0;
}

static uint32_t cell(uint32_t x, uint32_t o, uint32_t s) {
  uint32_t e = FULL & ~(x | o);
  return nth(e, ((s >> 16) * popcount(e)) >> 16);
}

static uint32_t playout(uint32_t x, uint32_t o, uint32_t t, uint32_t s) {
  while (status(x, o) == ONGOING) {
    s = prng(s);
    uint32_t c = cell(x, o, s);
    if (t == 0) x |= c; else o |= c;
    t ^= 1;
  }
  return status(x, o);
}

static uint32_t score(uint32_t t, uint32_t st) { return t == 0 ? 2 - st : st; }

typedef struct Node { uint32_t w, n; struct Node *kid[9]; } Node;

static Node *node_new(uint32_t w, uint32_t n) {
  Node *a = calloc(1, sizeof(Node));
  a->w = w;
  a->n = n;
  return a;
}

static void node_free(Node *a) {
  if (!a) return;
  for (int i = 0; i < 9; i++) node_free(a->kid[i]);
  free(a);
}

// the cell to take at a node with side t to move: the lowest untried legal
// cell with 16 added, else the legal child of highest UCT value
static uint32_t choose(const Node *a, uint32_t x, uint32_t o) {
  uint32_t e = 9, b = 9;
  float v = 0.0f;
  float ln = (float)log((double)(float)a->n);
  for (uint32_t i = 0; i < 9; i++) {
    int legal = !((x | o) >> i & 1);
    const Node *k = a->kid[i];
    if (legal && !k && e == 9) e = i;
    if (legal && k) {
      float u = (float)k->w / (2.0f * (float)k->n) + 1.4f * sqrtf(ln / (float)k->n);
      if (b == 9 || u > v) { b = i; v = u; }
    }
  }
  return e != 9 ? e | 16 : b;
}

// one iteration below node a (side t to move); returns the playout status
static uint32_t descend(Node *a, uint32_t x, uint32_t o, uint32_t t, uint32_t *s) {
  uint32_t st = status(x, o);
  if (st == ONGOING) {
    uint32_t ch = choose(a, x, o), k = ch & 15, bit = 1u << k;
    uint32_t nx = t == 0 ? x | bit : x, no = t == 1 ? o | bit : o;
    if (ch & 16) {
      *s = prng(*s);
      st = playout(nx, no, t ^ 1, mix(*s, 1));
      a->kid[k] = node_new(score(t, st), 1);
    } else {
      st = descend(a->kid[k], nx, no, t ^ 1, s);
    }
  }
  a->w += score(t ^ 1, st);
  a->n += 1;
  return st;
}

// the summed root visits of 2^DEP trees; tree r uses seed mix(salt + r, 77)
static void visits(uint32_t x, uint32_t o, uint32_t t, uint32_t salt, uint32_t v[9]) {
  for (int c = 0; c < 9; c++) v[c] = 0;
  for (uint32_t r = 0; r < (1u << DEP); r++) {
    Node *root = node_new(0, 0);
    uint32_t s = mix(salt + r, 77);
    for (int i = 0; i < ITERS; i++) descend(root, x, o, t, &s);
    for (int c = 0; c < 9; c++) v[c] += root->kid[c] ? root->kid[c]->n : 0;
    node_free(root);
  }
}

static uint32_t best(uint32_t x, uint32_t o, uint32_t t, uint32_t salt) {
  uint32_t v[9];
  visits(x, o, t, salt, v);
  uint32_t b = 9, bv = 0;
  for (uint32_t c = 0; c < 9; c++)
    if (!((x | o) >> c & 1) && (b == 9 || v[c] > bv)) { b = c; bv = v[c]; }
  return 1u << b;
}

static uint32_t game(uint32_t g) {
  uint32_t x = 0, o = 0, t = 0, s = mix(g, 99), me = g & 1, turn = 0;
  while (status(x, o) == ONGOING) {
    uint32_t c;
    if (t == me) {
      c = best(x, o, t, g * 64 + turn * 4096);
    } else {
      s = prng(s);
      c = cell(x, o, s);
    }
    if (t == 0) x |= c; else o |= c;
    t ^= 1;
    turn++;
  }
  return status(x, o);
}

static int minimax(uint32_t x, uint32_t o, uint32_t t) {
  uint32_t st = status(x, o);
  if (st != ONGOING) return st == 1 ? 0 : (st == 0) == (t == 0) ? 1 : -1;
  int v = -2;
  for (int c = 0; c < 9; c++) {
    uint32_t bit = 1u << c;
    if ((x | o) & bit) continue;
    int w = -minimax(t == 0 ? x | bit : x, t == 1 ? o | bit : o, t ^ 1);
    if (w > v) v = w;
  }
  return v;
}

static uint32_t seen[1 << 18], seen_n = 0, agree = 0, total = 0;
static uint32_t lost_value[3][3];

static void audit(uint32_t x, uint32_t o, uint32_t t) {
  if (status(x, o) != ONGOING) return;
  uint32_t key = x | o << 9;
  for (uint32_t i = 0; i < seen_n; i++) if (seen[i] == key) return;
  seen[seen_n++] = key;
  uint32_t c = best(x, o, t, key);
  uint32_t nx = t == 0 ? x | c : x, no = t == 1 ? o | c : o;
  int before = minimax(x, o, t), after = -minimax(nx, no, t ^ 1);
  total++;
  agree += after == before;
  if (after != before) lost_value[before + 1][after + 1] += 1;
  for (int k = 0; k < 9; k++) {
    uint32_t bit = 1u << k;
    if ((x | o) & bit) continue;
    audit(t == 0 ? x | bit : x, t == 1 ? o | bit : o, t ^ 1);
  }
}

int main(int argc, char **argv) {
  uint32_t v[9];
  visits(0, 0, 0, 0, v);
  for (int c = 0; c < 9; c++) printf(c ? " %u" : "%u", v[c]);
  printf("\n");
  uint32_t res[2][3] = {{0}};
  for (uint32_t g = 0; g < (1u << GAMES); g++) {
    uint32_t st = game(g), me = g & 1;
    res[me][st == 1 ? 1 : (st == 0) == (me == 0) ? 0 : 2] += 1;
  }
  printf("as X: %u won %u drawn %u lost; as O: %u won %u drawn %u lost\n",
         res[0][0], res[0][1], res[0][2], res[1][0], res[1][1], res[1][2]);
  if (argc < 2 || strcmp(argv[1], "--audit") != 0) return 0;
  audit(0, 0, 0);
  printf("minimax-optimal moves: %u of %u reachable positions\n", agree, total);
  printf("mistakes: win->draw %u, win->loss %u, draw->loss %u\n",
         lost_value[2][1], lost_value[2][0], lost_value[1][0]);
  return 0;
}
