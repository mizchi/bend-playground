#ifndef BEND_PARTICLE_STATE_H
#define BEND_PARTICLE_STATE_H
#include <stdint.h>
#include <stddef.h>

// Shared CPU/Metal ABI: six state words and two preserved reserved words.
typedef struct { float x, y, vx, vy, life, seed, pad0, pad1; } Particle;
_Static_assert(sizeof(Particle) == 32, "particle stride");
_Static_assert(offsetof(Particle, seed) == 20, "particle seed offset");
#define PARTICLE_DT 0.016666667f
#endif
