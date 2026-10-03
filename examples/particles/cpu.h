#ifndef BEND_PARTICLE_CPU_H
#define BEND_PARTICLE_CPU_H
#include "state.h"

typedef struct ParticleCPU ParticleCPU;
typedef struct { uint32_t completed_jobs, workers_used; } ParticleCPUStats;

// One caller owns the pool and particle buffer between synchronous updates.
// Create 1..128 persistent workers outside frame timing; destroy joins them.
ParticleCPU *particle_cpu_create(uint32_t threads);
void particle_cpu_destroy(ParticleCPU *pool);

// count=1..1,000,000; jobs=power of two in 64..16,384; rounds=0 or 64.
// Only [0,count) is written; padding and unused capacity are preserved.
// Return 0 on completion, EINVAL for invalid arguments. No update allocates.
int particle_cpu_run(ParticleCPU *pool, Particle *state, uint32_t count,
  uint32_t jobs, uint32_t rounds, ParticleCPUStats *stats);
int particle_cpu_direct(Particle *state, uint32_t count, uint32_t jobs,
  uint32_t rounds, ParticleCPUStats *stats);
#endif
