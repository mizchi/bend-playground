// C twin of fmc.bend: flat Monte Carlo search for tic-tac-toe.
// A player rates each legal move by 2^DEP random playouts from the position
// after it (win 2, draw 1, loss 0 for the mover) and plays the best (lowest
// cell on a tie). Prints the ratings of the 9 first moves, then 2^GAMES
// games of that player against a uniformly random one (it is X in the
// even games, O in the odd ones). Same arithmetic as the Bend source, so
// those two lines match it exactly. With --audit (C only): exact minimax over
// every reachable position, and how often the player's move is optimal.
// Build: cc -std=c11 -O3 -DDEP=10 -DGAMES=8 fmc.c && ./a.out --audit
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#ifndef DEP
#define DEP 10     // 2^DEP playouts per move
#endif
#ifndef GAMES
#define GAMES 8    // 2^GAMES games against the random player
#endif

#define FULL 511u
#define ONGOING 3u // status: 0 X won, 1 draw, 2 O won, 3 not over

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

// the k-th (from 0) set bit of e, as a mask
static uint32_t nth(uint32_t e, uint32_t k) {
  for (uint32_t bit = 1; bit < 512; bit <<= 1) {
    uint32_t set = (e & bit) != 0;
    if (set && k == 0) return bit;
    k -= set;
  }
  return 0;
}

// a uniformly random empty cell, as a mask; the next rng state in *s
static uint32_t pick(uint32_t x, uint32_t o, uint32_t *s) {
  uint32_t e = FULL & ~(x | o);
  *s = prng(*s);
  uint32_t k = ((*s >> 16) * popcount(e)) >> 16;
  return nth(e, k);
}

// random playout to the end; t is the side to move (0 X, 1 O)
static uint32_t playout(uint32_t x, uint32_t o, uint32_t t, uint32_t s) {
  while (status(x, o) == ONGOING) {
    uint32_t c = pick(x, o, &s);
    if (t == 0) x |= c; else o |= c;
    t ^= 1;
  }
  return status(x, o);
}

// the mover's score of an outcome: win 2, draw 1, loss 0
static uint32_t score(uint32_t t, uint32_t st) { return t == 0 ? 2 - st : st; }

// rate every cell: playout j of cell c uses seed mix(salt + j, c)
static void rate(uint32_t x, uint32_t o, uint32_t t, uint32_t salt, uint32_t r[9]) {
  for (int c = 0; c < 9; c++) r[c] = 0;
  for (uint32_t j = 0; j < (1u << DEP); j++)
    for (uint32_t c = 0; c < 9; c++) {
      uint32_t bit = 1u << c;
      if ((x | o) & bit) continue;
      uint32_t nx = t == 0 ? x | bit : x, no = t == 1 ? o | bit : o;
      r[c] += score(t, playout(nx, no, t ^ 1, mix(salt + j, c)));
    }
}

static uint32_t best(uint32_t x, uint32_t o, uint32_t t, uint32_t salt) {
  uint32_t r[9];
  rate(x, o, t, salt, r);
  uint32_t b = 9, bv = 0;
  for (uint32_t c = 0; c < 9; c++)
    if (!((x | o) >> c & 1) && (b == 9 || r[c] > bv)) { b = c; bv = r[c]; }
  return 1u << b;
}

// game g: the flat player is X when g is even; returns the status
static uint32_t game(uint32_t g) {
  uint32_t x = 0, o = 0, t = 0, s = mix(g, 99), me = g & 1, turn = 0;
  while (status(x, o) == ONGOING) {
    uint32_t c = t == me ? best(x, o, t, g * 64 + turn * 4096) : pick(x, o, &s);
    if (t == 0) x |= c; else o |= c;
    t ^= 1;
    turn++;
  }
  return status(x, o);
}

// exact value for the side to move t: +1 win, 0 draw, -1 loss
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

// every reachable position that is not over, either side to move:
// count those where the flat player's move keeps the minimax value
static uint32_t seen[1 << 18], seen_n = 0, agree = 0, total = 0;
// mistakes by the value they give up: [value before + 1][value after + 1]
static uint32_t lost_value[3][3], example = 0x7FFFFFFF;

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
  if (after != before) {
    lost_value[before + 1][after + 1] += 1;
    // the first drawn position the player loses, kept to show it
    if (before == 0 && example == 0x7FFFFFFF) example = key | c << 18 | t << 27;
  }
  for (int k = 0; k < 9; k++) {
    uint32_t bit = 1u << k;
    if ((x | o) & bit) continue;
    audit(t == 0 ? x | bit : x, t == 1 ? o | bit : o, t ^ 1);
  }
}

int main(int argc, char **argv) {
  uint32_t r[9];
  rate(0, 0, 0, 0, r);
  for (int c = 0; c < 9; c++) printf(c ? " %u" : "%u", r[c]);
  printf("\n");
  uint32_t res[2][3] = {{0}};  // [flat is X/O][flat wins, draws, loses]
  for (uint32_t g = 0; g < (1u << GAMES); g++) {
    uint32_t st = game(g), me = g & 1;
    res[me][st == 1 ? 1 : (st == 0) == (me == 0) ? 0 : 2] += 1;
  }
  printf("as X: %u won %u drawn %u lost; as O: %u won %u drawn %u lost\n",
         res[0][0], res[0][1], res[0][2], res[1][0], res[1][1], res[1][2]);
  // C only, with --audit: the flat player against perfect play, position by
  // position (not timed by bench.sh)
  if (argc < 2 || strcmp(argv[1], "--audit") != 0) return 0;
  audit(0, 0, 0);
  printf("minimax-optimal moves: %u of %u reachable positions\n", agree, total);
  printf("mistakes: win->draw %u, win->loss %u, draw->loss %u\n",
         lost_value[2][1], lost_value[2][0], lost_value[1][0]);
  if (example != 0x7FFFFFFF) {
    uint32_t x = example & 511, o = example >> 9 & 511, c = example >> 18 & 511;
    printf("a drawn position it loses (%c to move, it plays *):\n", (example >> 27) ? 'O' : 'X');
    for (int r = 0; r < 3; r++) {
      for (int k = 0; k < 3; k++) {
        uint32_t bit = 1u << (3 * r + k);
        putchar(x & bit ? 'X' : o & bit ? 'O' : c & bit ? '*' : '.');
      }
      putchar('\n');
    }
  }
  return 0;
}
