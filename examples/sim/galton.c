// C twin of galton.bend: a Galton board as a rigid-ball physics ensemble.
// Every ball falls under gravity through a triangular lattice of round pegs,
// collides (push-out + restitution along the contact normal), bounces off two
// side walls, and is binned where it ends. Same f32 operations in the same
// order as the Bend source, so the outputs match bit for bit.
// Build: cc -std=c11 -O3 -ffp-contract=off -DDEP=16 galton.c -lm
#include <math.h>
#include <stdint.h>
#include <stdio.h>

#ifndef DEP
#define DEP 16       // 2^DEP balls
#endif
#ifndef STEPS
#define STEPS 2048   // integration steps per ball
#endif
#define ROWS 12.0f   // peg rows 0..11 at y = 1..12 (y grows downward)
#define DT 0.005f
#define G 9.8f
#define REACH 0.4f   // ball radius + peg radius
#define REST 0.3f    // restitution
#define WALL 7.0f    // side walls at x = +-WALL
#define FLOOR 13.0f  // bins start below the last row

typedef struct { float x, y, vx, vy; } Ball;

static uint32_t prng(uint32_t x) {
  uint32_t b = x ^ (x << 13);
  uint32_t d = b ^ (b >> 17);
  return d ^ (d << 5);
}

static uint32_t seed(uint32_t i) { return ((i + 1) * 2654435761u) ^ 1013904223u; }

// uniform in [-0.05, 0.05) from the top 24 bits
static float jitter(uint32_t s) {
  float u = (float)(s >> 8) / 16777216.0f;
  return (u - 0.5f) * 0.1f;
}

// one peg contact: push the ball out to the contact distance and reflect
// the normal velocity if it approaches the peg
static Ball hit(Ball b, float px, float py, float dx, float dy, float d2) {
  float d = sqrtf(d2);
  float nx = dx / d;
  float ny = dy / d;
  float vn = b.vx * nx + b.vy * ny;
  float k = (vn < 0.0f) ? (1.0f + REST) * vn : 0.0f;
  Ball o = { px + nx * REACH, py + ny * REACH, b.vx - k * nx, b.vy - k * ny };
  return o;
}

// side walls reflect; the floor below the last row absorbs (the ball rests
// in its bin)
static Ball bound(Ball b) {
  if (b.y > FLOOR) { Ball o = { b.x, FLOOR, 0.0f, 0.0f }; return o; }
  if (b.x < 0.0f - WALL) { Ball o = { 0.0f - WALL, b.y, 0.0f - b.vx * REST, b.vy }; return o; }
  if (b.x > WALL) { Ball o = { WALL, b.y, 0.0f - b.vx * REST, b.vy }; return o; }
  return b;
}

static Ball step(Ball b) {
  float vy = b.vy + G * DT;
  float x = b.x + b.vx * DT;
  float y = b.y + vy * DT;
  // nearest peg: row by rounding y, column by rounding x in that row's offset
  float r = floorf(y + 0.5f);
  float o = (r - floorf(r * 0.5f) * 2.0f) * 0.5f;
  float px = floorf(x - o + 0.5f) + o;
  float dx = x - px;
  float dy = y - r;
  float d2 = dx * dx + dy * dy;
  Ball m = { x, y, b.vx, vy };
  int live = (1.0f <= r) & (r <= ROWS) & (d2 < REACH * REACH);
  return bound(live ? hit(m, px, r, dx, dy, d2) : m);
}

// bin 0..15 by the final x (column width 1, centre bin 8)
static uint32_t bin(float x) {
  float c = fminf(fmaxf(floorf(x + 8.5f), 0.0f), 15.0f);
  return (uint32_t)c;
}

static uint32_t ball(uint32_t i) {
  uint32_t s1 = prng(seed(i));
  uint32_t s2 = prng(s1);
  Ball b = { jitter(s1), 0.0f, jitter(s2), 0.0f };
  for (int t = 0; t < STEPS; t++) b = step(b);
  return bin(b.x);
}

int main(void) {
  uint32_t hist[16] = {0};
  for (uint32_t i = 0; i < (1u << DEP); i++) hist[ball(i)] += 1;
  for (int k = 0; k < 16; k++) printf(k ? " %u" : "%u", hist[k]);
  printf("\n");
  return 0;
}
