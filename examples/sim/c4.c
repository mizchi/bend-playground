// C twin of c4.bend: MCTS (UCT) for Connect Four, root parallelization
// against one deep tree at the same budget.
// A player grows 2^d independent trees of k iterations each and plays the
// column most visited over all of them (the lowest on a tie); one iteration
// is mcts.c's (expand the lowest untried column, else the child of highest
// UCT value, one random playout, scores added along the path). Prints the
// summed root visits of the empty board for 2^DEP x ITERS, then, for each
// width 2^w in WIDTHS, 2^GAMES games of 2^w trees x BUDGET/2^w iterations
// against 1 tree x BUDGET (colours alternate). Same arithmetic as the Bend
// source, so the output matches it.
// Build: cc -std=c11 -O3 -ffp-contract=off -DGAMES=6 c4.c -lm
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef DEP
#define DEP 4        // trees for the first line
#endif
#ifndef ITERS
#define ITERS 256    // iterations per tree for the first line
#endif
#ifndef BUDGET
#define BUDGET 1024  // iterations per move in the matches
#endif
#ifndef GAMES
#define GAMES 6      // 2^GAMES games per match
#endif

// a board: stones of each side in two words, rows 0-3 (bits r*7+c) and
// rows 4-5 (bits (r-4)*7+c), and the 7 column heights in 3 bits each
typedef struct { uint32_t xl, xh, ol, oh, h; } Board;

#define ONGOING 3u   // status: 0 X won, 1 draw, 2 O won, 3 not over

static uint32_t prng(uint32_t x) {
  uint32_t b = x ^ (x << 13);
  uint32_t d = b ^ (b >> 17);
  return d ^ (d << 5);
}

static uint32_t mix(uint32_t a, uint32_t b) {
  return prng(((a + 1) * 2654435761u) ^ ((b + 1) * 2246822519u));
}

static uint32_t height(uint32_t h, uint32_t c) { return (h >> (3 * c)) & 7; }

// is (c, r) a stone of side t? 0 off the board (c, r wrap below 0)
static uint32_t owns(const Board *b, uint32_t t, uint32_t c, uint32_t r) {
  if (c >= 7 || r >= 6) return 0;
  uint32_t lo = t == 0 ? b->xl : b->ol, hi = t == 0 ? b->xh : b->oh;
  return r < 4 ? (lo >> (r * 7 + c)) & 1 : (hi >> ((r - 4) * 7 + c)) & 1;
}

// stones of side t in a row from (c, r) along (dc, dr), up to 3, not
// counting (c, r)
static uint32_t run(const Board *b, uint32_t t, uint32_t c, uint32_t r, uint32_t dc, uint32_t dr) {
  uint32_t s1 = owns(b, t, c + dc, r + dr);
  uint32_t s2 = s1 & owns(b, t, c + 2 * dc, r + 2 * dr);
  uint32_t s3 = s2 & owns(b, t, c + 3 * dc, r + 3 * dr);
  return s1 + s2 + s3;
}

static uint32_t line4(const Board *b, uint32_t t, uint32_t c, uint32_t r, uint32_t dc, uint32_t dr) {
  return run(b, t, c, r, dc, dr) + run(b, t, c, r, 0u - dc, 0u - dr) >= 3;
}

// does the stone side t just put at (c, r) win?
static uint32_t wins(const Board *b, uint32_t t, uint32_t c, uint32_t r) {
  return line4(b, t, c, r, 1, 0) | line4(b, t, c, r, 0, 1) |
         line4(b, t, c, r, 1, 1) | line4(b, t, c, r, 1, 0u - 1);
}

// the columns that are not full, as a 7-bit mask
static uint32_t open_cols(uint32_t h) {
  uint32_t m = 0;
  for (uint32_t c = 0; c < 7; c++) m |= (height(h, c) < 6) << c;
  return m;
}

// side t drops a stone in column c; the status after it
static uint32_t drop(Board *b, uint32_t t, uint32_t c) {
  uint32_t r = height(b->h, c);
  uint32_t *lo = t == 0 ? &b->xl : &b->ol, *hi = t == 0 ? &b->xh : &b->oh;
  if (r < 4) *lo |= 1u << (r * 7 + c); else *hi |= 1u << ((r - 4) * 7 + c);
  b->h += 1u << (3 * c);
  if (wins(b, t, c, r)) return t == 0 ? 0 : 2;
  return open_cols(b->h) == 0 ? 1 : ONGOING;
}

static uint32_t popcount(uint32_t e) {
  uint32_t n = 0;
  for (int i = 0; i < 7; i++) n += (e >> i) & 1;
  return n;
}

static uint32_t nth(uint32_t e, uint32_t k) {
  for (uint32_t c = 0; c < 7; c++) {
    uint32_t set = (e >> c) & 1;
    if (set && k == 0) return c;
    k -= set;
  }
  return 0;
}

// a uniformly random open column with rng state s
static uint32_t col(uint32_t h, uint32_t s) {
  uint32_t e = open_cols(h);
  return nth(e, ((s >> 16) * popcount(e)) >> 16);
}

static uint32_t playout(Board b, uint32_t t, uint32_t s) {
  uint32_t st = ONGOING;
  while (st == ONGOING) {
    s = prng(s);
    st = drop(&b, t, col(b.h, s));
    t ^= 1;
  }
  return st;
}

static uint32_t score(uint32_t t, uint32_t st) { return t == 0 ? 2 - st : st; }

typedef struct Node { uint32_t w, n, st; struct Node *kid[7]; } Node;

static Node *node_new(uint32_t w, uint32_t n, uint32_t st) {
  Node *a = calloc(1, sizeof(Node));
  a->w = w;
  a->n = n;
  a->st = st;
  return a;
}

static void node_free(Node *a) {
  if (!a) return;
  for (int i = 0; i < 7; i++) node_free(a->kid[i]);
  free(a);
}

static uint32_t choose(const Node *a, uint32_t h) {
  uint32_t e = 7, b = 7, open = open_cols(h);
  float v = 0.0f;
  float ln = (float)log((double)(float)a->n);
  for (uint32_t i = 0; i < 7; i++) {
    int legal = (open >> i) & 1;
    const Node *k = a->kid[i];
    if (legal && !k && e == 7) e = i;
    if (legal && k) {
      float u = (float)k->w / (2.0f * (float)k->n) + 1.4f * sqrtf(ln / (float)k->n);
      if (b == 7 || u > v) { b = i; v = u; }
    }
  }
  return e != 7 ? e | 16 : b;
}

// one iteration below node a, whose position is b with side t to move and
// status a->st; returns the playout status
static uint32_t descend(Node *a, Board b, uint32_t t, uint32_t *s) {
  uint32_t st = a->st;
  if (st == ONGOING) {
    uint32_t ch = choose(a, b.h), k = ch & 15;
    uint32_t st1 = drop(&b, t, k);
    if (ch & 16) {
      *s = prng(*s);
      st = st1 == ONGOING ? playout(b, t ^ 1, mix(*s, 1)) : st1;
      a->kid[k] = node_new(score(t, st), 1, st1);
    } else {
      st = descend(a->kid[k], b, t ^ 1, s);
    }
  }
  a->w += score(t ^ 1, st);
  a->n += 1;
  return st;
}

// the summed root visits of 2^d trees of k iterations; tree r uses seed
// mix(salt + r, 77)
static void visits(Board b, uint32_t t, uint32_t d, uint32_t k, uint32_t salt, uint32_t v[7]) {
  for (int c = 0; c < 7; c++) v[c] = 0;
  for (uint32_t r = 0; r < (1u << d); r++) {
    Node *root = node_new(0, 0, ONGOING);
    uint32_t s = mix(salt + r, 77);
    for (uint32_t i = 0; i < k; i++) descend(root, b, t, &s);
    for (int c = 0; c < 7; c++) v[c] += root->kid[c] ? root->kid[c]->n : 0;
    node_free(root);
  }
}

static uint32_t best(Board b, uint32_t t, uint32_t d, uint32_t k, uint32_t salt) {
  uint32_t v[7], open = open_cols(b.h);
  visits(b, t, d, k, salt, v);
  uint32_t c = 7, cv = 0;
  for (uint32_t i = 0; i < 7; i++)
    if ((open >> i & 1) && (c == 7 || v[i] > cv)) { c = i; cv = v[i]; }
  return c;
}

// game g between the wide player (2^w trees x BUDGET >> w) and the deep one
// (1 tree x BUDGET); the wide player is X in the even games
static uint32_t game(uint32_t g, uint32_t w) {
  Board b = {0, 0, 0, 0, 0};
  uint32_t t = 0, st = ONGOING, me = g & 1, turn = 0;
  while (st == ONGOING) {
    uint32_t salt = g * 64 + turn * 4096 + t * 65536;
    uint32_t c = t == me ? best(b, t, w, BUDGET >> w, salt) : best(b, t, 0, BUDGET, salt);
    st = drop(&b, t, c);
    t ^= 1;
    turn++;
  }
  return st;
}

int main(void) {
  uint32_t v[7];
  Board b0 = {0, 0, 0, 0, 0};
  visits(b0, 0, DEP, ITERS, 0, v);
  for (int c = 0; c < 7; c++) printf(c ? " %u" : "%u", v[c]);
  printf("\n");
  static const uint32_t WIDTHS[] = {0, 2, 4, 6};
  for (int i = 0; i < 4; i++) {
    uint32_t w = WIDTHS[i], res[3] = {0, 0, 0};  // wide player won, drew, lost
    for (uint32_t g = 0; g < (1u << GAMES); g++) {
      uint32_t st = game(g, w), me = g & 1;
      res[st == 1 ? 1 : (st == 0) == (me == 0) ? 0 : 2] += 1;
    }
    printf("%u trees x %u vs 1 x %u: %u won %u drawn %u lost\n",
           1u << w, BUDGET >> w, BUDGET, res[0], res[1], res[2]);
  }
  return 0;
}
