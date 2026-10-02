#ifndef GRID_GPU_PROFILE_H
#define GRID_GPU_PROFILE_H
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <math.h>
#include <string.h>
#include <time.h>

typedef struct { uint32_t page, node; float x, y, width, height; } GridRect;
_Static_assert(sizeof(GridRect) == 24, "rectangle wire format must be 24 bytes");
typedef struct {
  uint32_t pages, nodes_per_page, round, count, errors;
  uint64_t started;
  GridRect *rects;
  unsigned char *seen;
} GridProfile;

static uint64_t grid_clock(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (uint64_t)t.tv_sec * 1000000000ull + (uint64_t)t.tv_nsec;
}

static void grid_profile_start(GridProfile *p, uint32_t pages, uint32_t nodes, uint32_t round) {
  if (!pages || pages > 65536 || !nodes || nodes > 2048) abort();
  memset(p, 0, sizeof *p);
  p->pages = pages; p->nodes_per_page = nodes; p->round = round;
  p->rects = malloc((size_t)pages * nodes * sizeof(GridRect));
  p->seen = calloc((size_t)pages * nodes, 1);
  if (!p->rects || !p->seen) abort();
}

static void grid_profile_put(GridProfile *p, uint32_t page, uint32_t id,
    float x, float y, float width, float height) {
  if (page >= p->pages || id >= p->nodes_per_page ||
      !isfinite(x) || !isfinite(y) || !isfinite(width) || !isfinite(height)) abort();
  size_t at = (size_t)page * p->nodes_per_page + id;
  if (p->seen[at]) abort();
  p->seen[at] = 1;
  p->rects[at] = (GridRect){page, id, x, y, width, height};
  p->count++;
}

static uint32_t grid_profile_quantize(float x) {
  return (uint32_t)fminf(4294967040.0f, fmaxf(0.0f, x * 16.0f));
}

static uint32_t grid_profile_hash(const GridProfile *p) {
  uint32_t hash = 0;
  for (uint32_t i = 0; i < p->count; i++) {
    const GridRect *r = &p->rects[i];
    hash += (r->node + 1) * (grid_profile_quantize(r->x) +
      3 * grid_profile_quantize(r->y) + 5 * grid_profile_quantize(r->width) +
      7 * grid_profile_quantize(r->height));
  }
  return hash;
}

static void grid_profile_report(GridProfile *p, uint64_t layout, uint64_t materialize,
    uint64_t checksum_time, uint64_t drop, uint32_t hash, uint32_t commands,
    uint64_t execution, uint64_t wait, uint64_t submit) {
  if (p->count != p->pages * p->nodes_per_page || p->errors) abort();
  printf("{\"round\":%u,\"pages\":%u,\"nodes\":%u,\"errors\":%u,\"checksum\":%u,"
    "\"bytes\":%llu,\"layout_ns\":%llu,\"materialize_ns\":%llu,"
    "\"checksum_ns\":%llu,\"drop_ns\":%llu,\"gpu_commands\":%u,"
    "\"gpu_execution_ns\":%llu,\"gpu_wait_ns\":%llu,\"gpu_submit_ns\":%llu}\n",
    p->round, p->pages, p->count, p->errors, hash,
    (unsigned long long)((uint64_t)p->count * sizeof(GridRect)),
    (unsigned long long)layout, (unsigned long long)materialize,
    (unsigned long long)checksum_time, (unsigned long long)drop, commands,
    (unsigned long long)execution, (unsigned long long)wait, (unsigned long long)submit);
  const char *path = getenv("GRID_GPU_DUMP");
  if (path) {
    FILE *f = fopen(path, "wb");
    if (!f || fwrite(p->rects, sizeof(GridRect), p->count, f) != p->count || fclose(f)) abort();
  }
  free(p->rects); free(p->seen);
}
#endif
