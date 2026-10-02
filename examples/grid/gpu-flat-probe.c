#include "gpu-profile.h"

static GridProfile grid_flat_profile;
static uint32_t grid_flat_depth, grid_flat_stride;
static uint64_t grid_flat_prepare;
static unsigned char *grid_flat_copy;

// memcpy avoids C effective-type assumptions about the runtime's u64 heap.
static float grid_flat_float(const unsigned char *buffer, size_t at) {
  float value;
  memcpy(&value, buffer + at * sizeof(float), sizeof value);
  return value;
}

static uint32_t __attribute__((noinline)) grid_flat_hash(const unsigned char *buffer) {
  __asm__ __volatile__("" ::: "memory"); // every pass reads the source again
  uint32_t hash = 0;
  for (uint32_t page = 0; page < grid_flat_profile.pages; ++page) {
    size_t base = (size_t)page * grid_flat_stride;
    for (uint32_t node = 0; node < grid_flat_profile.nodes_per_page; ++node) {
      float x = grid_flat_float(buffer, base + 4 * node);
      float y = grid_flat_float(buffer, base + 4 * node + 1);
      float w = grid_flat_float(buffer, base + 4 * node + 2);
      float h = grid_flat_float(buffer, base + 4 * node + 3);
      if (!isfinite(x) || !isfinite(y) || !isfinite(w) || !isfinite(h)) abort();
      hash += (node + 1) * (grid_profile_quantize(x) + 3 * grid_profile_quantize(y) +
        5 * grid_profile_quantize(w) + 7 * grid_profile_quantize(h));
    }
  }
  return hash;
}

static Term grid_flat_start(Env e, Term *f, IoWork *w) {
  (void)w;
  uint64_t begin = grid_clock();
  grid_profile_start(&grid_flat_profile, (uint32_t)f[0], (uint32_t)f[1], (uint32_t)f[2]);
  grid_flat_depth = (uint32_t)f[3]; grid_flat_stride = (uint32_t)f[4];
  if (grid_flat_depth > 29 || grid_flat_stride < grid_flat_profile.nodes_per_page * 4 ||
      (grid_flat_stride & (grid_flat_stride - 1)) ||
      (1ull << grid_flat_depth) != (uint64_t)grid_flat_profile.pages * grid_flat_stride) abort();
  size_t bytes = (size_t)(1ull << grid_flat_depth) * sizeof(float);
  grid_flat_copy = malloc(bytes);
  if (!grid_flat_copy) abort();
  memset(grid_flat_copy, 0, bytes); // copy destination is already committed
  Term initial = f32_rewrap(NAN); // missing writes fail the first full CPU read
  Term buffer = blk_new(e, false, grid_flat_depth, 0, 1, &initial);
  if (err_seen(e.mem)) abort();
  grid_probe_commands = 0;
  grid_probe_execution = grid_probe_wait = grid_probe_submit = 0;
  grid_flat_profile.started = grid_clock();
  grid_flat_prepare = grid_flat_profile.started - begin;
  return buffer;
}

static Term grid_flat_consume(Env e, Term *f, IoWork *w) {
  (void)w;
  uint64_t ready = grid_clock();
  Term result = f[0];
  if (term_tag(result) != TAG_CTR || term_aux(result) != CID(gpu-flat.FlatResult)) abort();
  const Term *fields = e.mem + term_peek(e.mem, result);
  Term buffer = fields[0];
  grid_flat_profile.errors = (uint32_t)fields[1];
  if (grid_flat_profile.errors || term_tag(buffer) != TAG_BUF || blk_cls(buffer) != grid_flat_depth) abort();
  const unsigned char *view = (const unsigned char *)(e.mem + blk_loc(e.mem, buffer));
  size_t bytes = (size_t)(1ull << grid_flat_depth) * sizeof(float);
  uint64_t viewed = grid_clock();
  uint32_t read_hash = grid_flat_hash(view);
  uint64_t read = grid_clock();
  uint32_t again_hash = grid_flat_hash(view);
  uint64_t again = grid_clock();
  memcpy(grid_flat_copy, view, bytes);
  uint64_t copied = grid_clock();
  uint32_t copy_hash = grid_flat_hash(grid_flat_copy);
  uint64_t copy_read = grid_clock();
  for (uint32_t page = 0; page < grid_flat_profile.pages; ++page) {
    size_t base = (size_t)page * grid_flat_stride;
    for (uint32_t node = 0; node < grid_flat_profile.nodes_per_page; ++node)
      grid_profile_put(&grid_flat_profile, page, node,
        grid_flat_float(view, base + node * 4), grid_flat_float(view, base + node * 4 + 1),
        grid_flat_float(view, base + node * 4 + 2), grid_flat_float(view, base + node * 4 + 3));
  }
  uint64_t materialized = grid_clock();
  uint32_t hash = grid_profile_hash(&grid_flat_profile);
  uint64_t hashed = grid_clock();
  if (hash != read_hash || hash != again_hash || hash != copy_hash ||
      grid_flat_profile.count != grid_flat_profile.pages * grid_flat_profile.nodes_per_page) abort();
  term_drop(e, result);
  uint64_t dropped = grid_clock();
  printf("{\"round\":%u,\"pages\":%u,\"nodes\":%u,\"errors\":%u,\"checksum\":%u,"
    "\"bytes\":%llu,\"buffer_bytes\":%llu,\"stride\":%u,\"prepare_ns\":%llu,"
    "\"layout_ns\":%llu,\"view_ns\":%llu,\"read_ns\":%llu,\"read_again_ns\":%llu,"
    "\"copy_ns\":%llu,\"copy_read_ns\":%llu,\"materialize_ns\":%llu,\"checksum_ns\":%llu,"
    "\"drop_ns\":%llu,\"gpu_commands\":%u,\"gpu_execution_ns\":%llu,\"gpu_wait_ns\":%llu,"
    "\"gpu_submit_ns\":%llu,\"read_checksum\":%u,\"read_again_checksum\":%u,\"copy_checksum\":%u}\n",
    grid_flat_profile.round, grid_flat_profile.pages, grid_flat_profile.count, grid_flat_profile.errors, hash,
    (unsigned long long)grid_flat_profile.count * sizeof(GridRect), (unsigned long long)bytes, grid_flat_stride,
    (unsigned long long)grid_flat_prepare,
    (unsigned long long)(ready - grid_flat_profile.started), (unsigned long long)(viewed - ready),
    (unsigned long long)(read - viewed), (unsigned long long)(again - read),
    (unsigned long long)(copied - again), (unsigned long long)(copy_read - copied),
    (unsigned long long)(materialized - copy_read), (unsigned long long)(hashed - materialized),
    (unsigned long long)(dropped - hashed), grid_probe_commands,
    (unsigned long long)grid_probe_execution, (unsigned long long)grid_probe_wait,
    (unsigned long long)grid_probe_submit, read_hash, again_hash, copy_hash);
  const char *path = getenv("GRID_GPU_DUMP");
  if (path) {
    FILE *file = fopen(path, "wb");
    if (!file || fwrite(grid_flat_profile.rects, sizeof(GridRect), grid_flat_profile.count, file) != grid_flat_profile.count || fclose(file)) abort();
  }
  free(grid_flat_copy); free(grid_flat_profile.rects); free(grid_flat_profile.seen);
  return term_pak(CID(Unit), 0);
}

static void __attribute__((constructor)) grid_flat_use(void) {
  _Static_assert(sizeof(float) == 4, "flat buffer requires 32-bit float");
  if (cid_arity(CID(gpu-flat.FlatResult)) != 2) abort();
  io_eff(CID(start), grid_flat_start, 0);
  io_eff(CID(consume), grid_flat_consume, 0);
}
