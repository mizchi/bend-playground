#include "gpu-profile.h"

static GridProfile grid_profile;

// ABI guards below match the pinned compiler's flattened constructor fields.
// Read shared nodes without consuming them; drop the complete result afterwards.
static const Term *grid_probe_fields(Env e, Term value, uint32_t arity) {
  if (term_tag(value) != TAG_CTR || cid_arity((uint32_t)term_aux(value)) != arity) abort();
  return e.mem + term_peek(e.mem, value);
}

static void grid_probe_tree(Env e, uint32_t page, const Term *tree, unsigned depth);

static void grid_probe_children(Env e, uint32_t page, Term list, unsigned depth) {
  unsigned count = 0;
  while (term_aux(list) != CID(Nil)) {
    if (term_aux(list) != CID(Con) || ++count > 256) abort();
    const Term *f = grid_probe_fields(e, list, 2);
    if (term_aux(f[0]) != CID(contract.Tree)) abort();
    grid_probe_tree(e, page, grid_probe_fields(e, f[0], 7), depth);
    list = f[1];
  }
}

static void grid_probe_tree(Env e, uint32_t page, const Term *tree, unsigned depth) {
  if (depth > 8) abort();
  grid_profile_put(&grid_profile, page, (uint32_t)tree[0],
    f32_unbox(tree[1]), f32_unbox(tree[2]), f32_unbox(tree[3]), f32_unbox(tree[4]));
  grid_probe_children(e, page, tree[5], depth + 1);
}

static void grid_probe_batch(Env e, Term value, unsigned depth) {
  if (depth > 16) abort();
  if (term_aux(value) == CID(gpu.Page)) {
    const Term *f = grid_probe_fields(e, value, 2);
    if (term_aux(f[1]) != CID(contract.Tree)) abort();
    const Term *tree = grid_probe_fields(e, f[1], 7);
    grid_profile.errors += (uint32_t)tree[6];
    grid_probe_tree(e, (uint32_t)f[0], tree, 0);
  } else if (term_aux(value) == CID(gpu.Fork)) {
    const Term *f = grid_probe_fields(e, value, 2);
    grid_probe_batch(e, f[0], depth + 1);
    grid_probe_batch(e, f[1], depth + 1);
  } else abort();
}

static Term grid_probe_start(Env e, Term *f, IoWork *w) {
  (void)e; (void)w;
  grid_profile_start(&grid_profile, (uint32_t)f[0], (uint32_t)f[1], (uint32_t)f[2]);
  grid_probe_commands = 0;
  grid_probe_execution = grid_probe_wait = grid_probe_submit = 0;
  grid_profile.started = grid_clock();
  return term_pak(CID(Unit), 0);
}

static Term grid_probe_consume(Env e, Term *f, IoWork *w) {
  (void)w;
  uint64_t ready = grid_clock();
  grid_probe_batch(e, f[0], 0);
  uint64_t copied = grid_clock();
  uint32_t hash = grid_profile_hash(&grid_profile);
  uint64_t hashed = grid_clock();
  term_drop(e, f[0]);
  uint64_t dropped = grid_clock();
  grid_profile_report(&grid_profile, ready - grid_profile.started, copied - ready,
    hashed - copied, dropped - hashed, hash, grid_probe_commands,
    grid_probe_execution, grid_probe_wait, grid_probe_submit);
  return term_pak(CID(Unit), 0);
}

static void __attribute__((constructor)) grid_probe_use(void) {
  if (cid_arity(CID(gpu.Page)) != 2 || cid_arity(CID(gpu.Fork)) != 2 ||
      cid_arity(CID(Con)) != 2 || cid_arity(CID(contract.Tree)) != 7) abort();
  io_eff(CID(start), grid_probe_start, 0);
  io_eff(CID(consume), grid_probe_consume, 0);
}
