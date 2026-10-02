#ifndef BEND_PARTICLE_ORACLE_H
#define BEND_PARTICLE_ORACLE_H
#include <stdint.h>
#include <math.h>

// Independent scalar reference. It is used for initialization and optional
// verification, never for the timed update of any of the three backends.
typedef struct { float x, y, vx, vy, life, seed, pad0, pad1; } Particle;
_Static_assert(sizeof(Particle) == 32, "particle stride");
#define PARTICLE_DT 0.016666667f

static uint32_t particle_random(uint32_t x) {
  x ^= x << 13; x ^= x >> 17; x ^= x << 5;
  return x & 0xffffff;
}

static Particle particle_initial(uint32_t i) {
  uint32_t r = particle_random((0x123456 + i) & 0xffffff);
  return (Particle){(float)(r % 4096) / 2048 - 1,
    (float)((r >> 12) % 4096) / 2048 - 1,
    ((float)(i % 17) - 8) / 32, ((float)(i % 13) - 6) / 32,
    (float)(i % 240) * PARTICLE_DT, (float)r, 0, 0};
}

static Particle particle_reference(Particle p, uint32_t rounds) {
  uint32_t r = (uint32_t)p.seed;
  if (p.life <= 0) {
    r = particle_random(r);
    p.x = (float)(r % 4096) / 2048 - 1; p.y = -1;
    p.vx = ((float)((r >> 12) % 4096) / 4096 - .5f) * .3f;
    p.vy = .5f + (float)(r % 1024) / 2048;
    p.life = 1 + (float)(r % 4096) / 1024;
  }
  for (uint32_t n = 0; n < rounds; ++n) r = particle_random(r);
  float nx = rounds ? ((float)(r % 4096) / 4096 - .5f) * .6f : 0;
  float ny = rounds ? ((float)((r >> 12) % 4096) / 4096 - .5f) * .6f : 0;
  float ax = (-p.x * .15f - p.vx * .05f) + nx;
  float ay = ((-p.y * .15f - p.vy * .05f) - .12f) + ny;
  p.vx += ax * PARTICLE_DT; p.vy += ay * PARTICLE_DT;
  p.x += p.vx * PARTICLE_DT; p.y += p.vy * PARTICLE_DT;
  p.life -= PARTICLE_DT; p.seed = (float)r;
  return p;
}
#endif
