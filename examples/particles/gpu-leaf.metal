// Diagnostic lowering: use the exact emitted flat Bend leaf, without fork,
// work_loop, reference-count joins, ring management, or allocator bank packing.
// This is valid only for the inspected allocation-free particle leaf. Its
// scalar arithmetic, array addressing and coherent(device) qualifier remain.
struct ParticleLeafArgs { u64 buffer; u32 count, jobs, rounds, reserved; };
kernel void particle_bend_leaf(DEV u64 *H [[buffer(0)]],
    constant ParticleLeafArgs &a [[buffer(1)]], uint job [[thread_position_in_grid]]) {
  if (job >= a.jobs) return;
  u32 chunk = (a.count + a.jobs - 1) / a.jobs;
  u32 start = min(job * chunk, a.count), end = min(start + chunk, a.count);
  Env e = {H, H + ALC_OFF + job};
  Term result[1];
  spin_16(e, result, Term(end - start), Term(a.rounds), u32(a.rounds != 0),
    start, a.buffer, blk_loc(H, a.buffer));
}
