// Common CPU baseline: a dynamic queue of independent jobs, private worker state.
// Result fields accumulate modulo 2^32; scheduling cannot change the output.
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#ifndef DEP
#define DEP 8
#endif
#ifndef JOB_CHUNK
#define JOB_CHUNK 16
#endif
#if DEP < 0 || DEP > 24
#error DEP must be in 0..24
#endif

typedef struct { uint32_t checksum, detail, errors; } Result;
static Result job(uint32_t i, void *context);
static void *worker_init(void);
static void worker_destroy(void *context);

static uint32_t prng(uint32_t x) {
  x ^= x << 13; x ^= x >> 17; x ^= x << 5;
  return x;
}
static uint32_t seed(uint32_t i) {
  return ((i + 1u) * 2654435761u) ^ 1013904223u;
}
static Result result_add(Result a, Result b) {
  return (Result){a.checksum + b.checksum, a.detail + b.detail, a.errors + b.errors};
}

static atomic_uint next_job;
typedef struct { Result result; } Worker;
static void *worker_run(void *argument) {
  Worker *worker = argument;
  void *context = worker_init();
  Result result = {0};
  for (;;) {
    uint32_t first = atomic_fetch_add_explicit(&next_job, JOB_CHUNK, memory_order_relaxed);
    if (first >= (1u << DEP)) break;
    uint32_t last = first + JOB_CHUNK;
    if (last > (1u << DEP)) last = (1u << DEP);
    for (uint32_t i = first; i < last; ++i) result = result_add(result, job(i, context));
  }
  worker_destroy(context);
  worker->result = result;
  return NULL;
}

int main(int argc, char **argv) {
  long threads = sysconf(_SC_NPROCESSORS_ONLN);
  if (threads < 1) threads = 1;
  if (threads > 128) threads = 128;
  if (argc != 1) {
    if (argc != 3 || strcmp(argv[1], "--threads") != 0) {
      fprintf(stderr, "usage: %s [--threads 1..128]\n", argv[0]);
      return 2;
    }
    char *end;
    errno = 0;
    threads = strtol(argv[2], &end, 10);
    if (errno || *end || end == argv[2] || threads < 1 || threads > 128) return 2;
  }
  Worker workers[128] = {0};
  pthread_t handles[127];
  atomic_init(&next_job, 0);
  for (long i = 0; i < threads - 1; ++i) {
    int error = pthread_create(&handles[i], NULL, worker_run, &workers[i]);
    if (error) { fprintf(stderr, "pthread_create failed: %d\n", error); return 1; }
  }
  worker_run(&workers[threads - 1]);
  for (long i = 0; i < threads - 1; ++i) {
    int error = pthread_join(handles[i], NULL);
    if (error) { fprintf(stderr, "pthread_join failed: %d\n", error); return 1; }
  }
  Result total = {0};
  for (long i = 0; i < threads; ++i) total = result_add(total, workers[i].result);
  printf("checksum=%u detail=%u errors=%u\n", total.checksum, total.detail, total.errors);
  return total.errors ? 1 : 0;
}
