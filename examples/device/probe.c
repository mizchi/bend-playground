#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static uint32_t device_jobs, device_calls, device_round, device_count, device_checksum;
static uint32_t device_expected;
static uint64_t device_begin_time;

static uint64_t device_clock(void) {
  struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
  return (uint64_t)t.tv_sec * 1000000000ull + (uint64_t)t.tv_nsec;
}

static Term device_begin(Env e, Term *f, IoWork *w) {
  (void)e; (void)w;
  device_jobs = (uint32_t)f[0]; device_calls = (uint32_t)f[1]; device_round = (uint32_t)f[2];
  if (device_jobs != DEVICE_JOBS || device_calls != DEVICE_JOBS / DEVICE_GROUP) abort();
  device_count = device_checksum = 0;
  grid_probe_commands = 0;
  grid_probe_execution = grid_probe_wait = grid_probe_submit = 0;
  device_begin_time = device_clock();
  return 305419896;
}

static Term device_next(Env e, Term *f, IoWork *w) {
  (void)e; (void)w;
  device_checksum += (uint32_t)f[0];
  if (++device_count > device_calls) abort();
  return device_count * DEVICE_GROUP;
}

static Term device_finish(Env e, Term *f, IoWork *w) {
  (void)e; (void)f; (void)w;
  uint64_t end = device_clock();
  if (device_count != device_calls || device_checksum != device_expected) abort();
  printf("{\"round\":%u,\"calls\":%u,\"jobs\":%u,\"checksum\":%u,\"elapsed_ns\":%llu,"
    "\"gpu_commands\":%u,\"gpu_execution_ns\":%llu,\"gpu_wait_ns\":%llu,\"gpu_submit_ns\":%llu}\n",
    device_round, device_calls, device_jobs, device_checksum, (unsigned long long)(end-device_begin_time),
    grid_probe_commands, (unsigned long long)grid_probe_execution,
    (unsigned long long)grid_probe_wait, (unsigned long long)grid_probe_submit);
  return term_pak(CID(Unit), 0);
}

static void __attribute__((constructor)) device_use(void) {
  // Independent native checksum before any timed sample or GPU dispatch.
  for (uint32_t i = 0; i < DEVICE_JOBS; ++i) {
    uint32_t x = 305419896u + i;
    for (uint32_t j = 0; j < DEVICE_ROUNDS; ++j) {
      x ^= x << 13; x ^= x >> 17; x ^= x << 5;
    }
    device_expected += x;
  }
  io_eff(CID(begin), device_begin, 0);
  io_eff(CID(next), device_next, 0);
  io_eff(CID(finish), device_finish, 0);
}
