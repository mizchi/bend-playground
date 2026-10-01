// C twin of balls.bend: interacting rigid balls in a box.
// 2^DEP independent boxes, each holding NB equal-mass balls of radius R in
// the unit square. Every step resolves every overlapping, approaching pair
// with an elastic impulse along the contact normal (Jacobi: all impulses
// read the previous state), reflects the walls, then moves. Same f32
// operations in the same order as the Bend source, so outputs match bit for
// bit. Prints the contact count and a position checksum summed over boxes.
// Build: cc -std=c11 -O3 -ffp-contract=off -DDEP=12 balls.c -lm
#include <math.h>
#include <stdint.h>
#include <stdio.h>

#ifndef DEP
#define DEP 12      // 2^DEP boxes
#endif
#ifndef STEPS
#define STEPS 4096  // integration steps per box
#endif
#define NB 8        // balls per box
#define R 0.05f
#define DT 0.002f

typedef struct { float x, y, vx, vy; } Ball;

static uint32_t prng(uint32_t x) {
  uint32_t b = x ^ (x << 13);
  uint32_t d = b ^ (b >> 17);
  return d ^ (d << 5);
}

static uint32_t seed(uint32_t i) { return ((i + 1) * 2654435761u) ^ 1013904223u; }

static float unit(uint32_t s) { return (float)(s >> 8) / 16777216.0f; }

// ball k of a box: a slot of the 3x3 grid (0.2, 0.5, 0.8) jittered by
// +-0.05, velocity in [-0.5, 0.5)^2
static Ball spawn(uint32_t s, uint32_t k) {
  uint32_t s1 = prng(s ^ (k * 2246822519u));
  uint32_t s2 = prng(s1);
  uint32_t s3 = prng(s2);
  uint32_t s4 = prng(s3);
  float gx = 0.2f + 0.3f * (float)(k % 3);
  float gy = 0.2f + 0.3f * (float)(k / 3);
  Ball b = { gx + (unit(s1) - 0.5f) * 0.1f, gy + (unit(s2) - 0.5f) * 0.1f,
             unit(s3) - 0.5f, unit(s4) - 0.5f };
  return b;
}

// sum the impulses on ball i from every other ball j, in index order
static Ball push(const Ball *bs, int i, uint32_t *hits) {
  Ball a = bs[i];
  float dvx = 0.0f, dvy = 0.0f;
  for (int j = 0; j < NB; j++) {
    Ball b = bs[j];
    float dx = a.x - b.x;
    float dy = a.y - b.y;
    float d2 = dx * dx + dy * dy;
    if ((0.0f < d2) & (d2 < (R + R) * (R + R))) {
      float d = sqrtf(d2);
      float nx = dx / d;
      float ny = dy / d;
      float rv = (a.vx - b.vx) * nx + (a.vy - b.vy) * ny;
      if (rv < 0.0f) {
        dvx = dvx - rv * nx;
        dvy = dvy - rv * ny;
        *hits += 1;
      }
    }
  }
  Ball o = { a.x, a.y, a.vx + dvx, a.vy + dvy };
  return o;
}

// reflect off the walls, then move
static Ball move(Ball b) {
  float vx = (b.x < R) ? fabsf(b.vx) : (1.0f - R < b.x) ? 0.0f - fabsf(b.vx) : b.vx;
  float vy = (b.y < R) ? fabsf(b.vy) : (1.0f - R < b.y) ? 0.0f - fabsf(b.vy) : b.vy;
  Ball o = { b.x + vx * DT, b.y + vy * DT, vx, vy };
  return o;
}

// one box: contact count, and a checksum of the final positions
static void box(uint32_t i, uint32_t *hits, uint32_t *cs) {
  Ball bs[NB], nx[NB];
  uint32_t s = seed(i);
  for (uint32_t k = 0; k < NB; k++) bs[k] = spawn(s, k);
  for (int t = 0; t < STEPS; t++) {
    for (int k = 0; k < NB; k++) nx[k] = move(push(bs, k, hits));
    for (int k = 0; k < NB; k++) bs[k] = nx[k];
  }
  for (int k = 0; k < NB; k++)
    *cs += (uint32_t)(bs[k].x * 65536.0f) * 31u + (uint32_t)(bs[k].y * 65536.0f);
}

int main(void) {
  uint32_t hits = 0, cs = 0;
  for (uint32_t i = 0; i < (1u << DEP); i++) box(i, &hits, &cs);
  printf("contacts=%u checksum=%u\n", hits, cs);
  return 0;
}
