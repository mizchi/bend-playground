// C twin of anneal.bend: Monte Carlo search for a 0-1 knapsack.
// 2^DEP independent simulated-annealing chains search the same 32-item
// instance; the best value, how many chains reached it and the first such
// chain's item mask are reported. An exact dynamic program prints the true
// optimum next to it, so the search can be scored. Same f32 operations in
// the same order as the Bend source, so the search outputs match bit for bit.
// Build: cc -std=c11 -O3 -ffp-contract=off -DDEP=14 anneal.c -lm
#include <math.h>
#include <stdint.h>
#include <stdio.h>

#ifndef DEP
#define DEP 14     // 2^DEP chains
#endif
#ifndef STEPS
#define STEPS 4096 // proposals per chain
#endif
#define ITEMS 32
#define CAP 600u
#define T0 100.0f
#define COOL 0.9983f

static uint32_t prng(uint32_t x) {
  uint32_t b = x ^ (x << 13);
  uint32_t d = b ^ (b >> 17);
  return d ^ (d << 5);
}

static uint32_t seed(uint32_t i) { return ((i + 1) * 2654435761u) ^ 1013904223u; }

// item j: weight in [10, 73], value = weight + [0, 31] (correlated: hard)
static uint32_t item(uint32_t j) { return prng((j + 1) * 2654435769u); }
static uint32_t weight(uint32_t j) { return 10 + (item(j) & 63); }
static uint32_t value(uint32_t j) { return weight(j) + ((item(j) >> 8) & 31); }

typedef struct { uint32_t v, n, m; } Best;  // value, chains at it, first mask

static Best chain(uint32_t i) {
  uint32_t s = seed(i), m = 0, w = 0, v = 0, best = 0, bm = 0;
  float t = T0;
  for (int k = 0; k < STEPS; k++) {
    s = prng(s);
    uint32_t j = s >> 27;
    uint32_t in = (m >> j) & 1;
    uint32_t w2 = in ? w - weight(j) : w + weight(j);
    uint32_t v2 = in ? v - value(j) : v + value(j);
    s = prng(s);
    float u = (float)(s >> 8) / 16777216.0f;
    float dv = (float)v2 - (float)v;
    int ok = (w2 <= CAP) & ((0.0f <= dv) | (u < (float)exp(dv / t)));
    if (ok) {
      m = m ^ (1u << j);
      w = w2;
      v = v2;
      if (best < v) { best = v; bm = m; }
    }
    t = t * COOL;
  }
  Best b = { best, 1, bm };
  return b;
}

static uint32_t exact(void) {
  uint32_t dp[CAP + 1] = {0};
  for (uint32_t j = 0; j < ITEMS; j++)
    for (uint32_t c = CAP; c >= weight(j); c--)
      if (dp[c - weight(j)] + value(j) > dp[c]) dp[c] = dp[c - weight(j)] + value(j);
  return dp[CAP];
}

int main(void) {
  Best acc = { 0, 0, 0 };
  for (uint32_t i = 0; i < (1u << DEP); i++) {
    Best b = chain(i);
    if (acc.v < b.v) acc = b;
    else if (acc.v == b.v) acc.n += b.n;
  }
  printf("best=%u chains=%u mask=%u\n", acc.v, acc.n, acc.m);
  printf("exact=%u\n", exact());
  return 0;
}
