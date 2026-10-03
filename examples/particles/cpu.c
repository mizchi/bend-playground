#include "cpu.h"
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdlib.h>

// This is the production C comparison, independent of oracle.h. Compile it as
// a separate translation unit, with runtime rounds and no LTO/constant cloning.
static uint32_t cpu_random(uint32_t seed) {
  seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5;
  return seed & 0xffffff;
}

static void cpu_range(Particle *state, uint32_t begin, uint32_t end, uint32_t rounds) {
  for (uint32_t i = begin; i < end; ++i) {
    Particle *p = &state[i];
    float x = p->x, y = p->y, vx = p->vx, vy = p->vy, life = p->life;
    uint32_t seed = (uint32_t)p->seed;
    if (life <= 0) {
      seed = cpu_random(seed);
      x = (float)(seed % 4096) / 2048 - 1; y = -1;
      vx = ((float)((seed >> 12) % 4096) / 4096 - .5f) * .3f;
      vy = .5f + (float)(seed % 1024) / 2048;
      life = 1 + (float)(seed % 4096) / 1024;
    }
    for (uint32_t n = 0; n < rounds; ++n) seed = cpu_random(seed);
    float fx = rounds ? ((float)(seed % 4096) / 4096 - .5f) * .6f : 0;
    float fy = rounds ? ((float)((seed >> 12) % 4096) / 4096 - .5f) * .6f : 0;
    float ax = (-x * .15f - vx * .05f) + fx;
    float ay = ((-y * .15f - vy * .05f) - .12f) + fy;
    vx += ax * PARTICLE_DT; vy += ay * PARTICLE_DT;
    p->x = x + vx * PARTICLE_DT; p->y = y + vy * PARTICLE_DT;
    p->vx = vx; p->vy = vy; p->life = life - PARTICLE_DT; p->seed = (float)seed;
  }
}

struct ParticleCPU {
  pthread_t workers[128];
  uint32_t threads, ready, remaining;
  uint64_t generation;
  bool stop;
  pthread_mutex_t lock;
  pthread_cond_t wake;
  atomic_uint next_job;
  Particle *state;
  uint32_t count, jobs, rounds;
  ParticleCPUStats stats;
};

static bool cpu_valid(Particle *state, uint32_t count, uint32_t jobs,
    uint32_t rounds, ParticleCPUStats *stats) {
  return state && stats && count >= 1 && count <= 1000000 && jobs >= 64 && jobs <= 16384
    && !(jobs & (jobs - 1)) && (rounds == 0 || rounds == 64);
}

// Match the Bend fork leaves: ceil(count/jobs) consecutive particles per job.
// Empty jobs count as completed work descriptions and perform no array access.
static bool cpu_job(Particle *state, uint32_t count, uint32_t jobs,
    uint32_t rounds, uint32_t job) {
  uint32_t chunk = (count + jobs - 1) / jobs;
  uint32_t begin = job * chunk;
  if (begin >= count) return false;
  uint32_t end = begin + chunk < count ? begin + chunk : count;
  cpu_range(state, begin, end, rounds);
  return true;
}

static void *cpu_worker(void *context) {
  ParticleCPU *pool = context;
  uint64_t seen = 0;
  pthread_mutex_lock(&pool->lock);
  ++pool->ready;
  pthread_cond_broadcast(&pool->wake);
  for (;;) {
    while (!pool->stop && seen == pool->generation) pthread_cond_wait(&pool->wake, &pool->lock);
    if (pool->stop) break;
    seen = pool->generation;
    Particle *state = pool->state;
    uint32_t count = pool->count, jobs = pool->jobs, rounds = pool->rounds;
    pthread_mutex_unlock(&pool->lock);
    uint32_t completed = 0;
    bool used = false;
    for (;;) {
      uint32_t job = atomic_fetch_add_explicit(&pool->next_job, 1, memory_order_relaxed);
      if (job >= jobs) break;
      used |= cpu_job(state, count, jobs, rounds, job);
      ++completed;
    }
    pthread_mutex_lock(&pool->lock);
    pool->stats.completed_jobs += completed;
    pool->stats.workers_used += used;
    if (!--pool->remaining) pthread_cond_broadcast(&pool->wake);
  }
  pthread_mutex_unlock(&pool->lock);
  return NULL;
}

ParticleCPU *particle_cpu_create(uint32_t threads) {
  if (threads < 1 || threads > 128) return NULL;
  ParticleCPU *pool = calloc(1, sizeof *pool);
  if (!pool) return NULL;
  if (pthread_mutex_init(&pool->lock, NULL)) { free(pool); return NULL; }
  if (pthread_cond_init(&pool->wake, NULL)) {
    pthread_mutex_destroy(&pool->lock); free(pool); return NULL;
  }
  atomic_init(&pool->next_job, 0);
  for (uint32_t i = 0; i < threads; ++i) {
    if (pthread_create(&pool->workers[i], NULL, cpu_worker, pool)) {
      particle_cpu_destroy(pool); return NULL;
    }
    ++pool->threads;
  }
  // Exclude worker startup from updates as well as the allocation itself.
  pthread_mutex_lock(&pool->lock);
  while (pool->ready != threads) pthread_cond_wait(&pool->wake, &pool->lock);
  pthread_mutex_unlock(&pool->lock);
  return pool;
}

void particle_cpu_destroy(ParticleCPU *pool) {
  if (!pool) return;
  pthread_mutex_lock(&pool->lock);
  pool->stop = true;
  pthread_cond_broadcast(&pool->wake);
  pthread_mutex_unlock(&pool->lock);
  for (uint32_t i = 0; i < pool->threads; ++i) pthread_join(pool->workers[i], NULL);
  pthread_cond_destroy(&pool->wake); pthread_mutex_destroy(&pool->lock); free(pool);
}

int particle_cpu_run(ParticleCPU *pool, Particle *state, uint32_t count,
    uint32_t jobs, uint32_t rounds, ParticleCPUStats *stats) {
  if (!pool || !cpu_valid(state, count, jobs, rounds, stats)) return EINVAL;
  pthread_mutex_lock(&pool->lock);
  pool->state = state; pool->count = count; pool->jobs = jobs; pool->rounds = rounds;
  pool->stats = (ParticleCPUStats){0};
  atomic_store_explicit(&pool->next_job, 0, memory_order_relaxed);
  pool->remaining = pool->threads;
  ++pool->generation;
  pthread_cond_broadcast(&pool->wake);
  while (pool->remaining) pthread_cond_wait(&pool->wake, &pool->lock);
  *stats = pool->stats;
  pthread_mutex_unlock(&pool->lock);
  return 0;
}

int particle_cpu_direct(Particle *state, uint32_t count, uint32_t jobs,
    uint32_t rounds, ParticleCPUStats *stats) {
  if (!cpu_valid(state, count, jobs, rounds, stats)) return EINVAL;
  *stats = (ParticleCPUStats){0};
  for (uint32_t job = 0; job < jobs; ++job) {
    cpu_job(state, count, jobs, rounds, job);
    ++stats->completed_jobs;
  }
  stats->workers_used = 1;
  return 0;
}
