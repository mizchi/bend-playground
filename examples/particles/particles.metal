#include <metal_stdlib>
using namespace metal;
struct Particle { float2 position, velocity; float life, seed, pad0, pad1; };
struct ParticleArgs { uint count, rounds, width, height; float radius; uint jobs; };

uint particle_random(uint x) {
  x ^= x << 13; x ^= x >> 17; x ^= x << 5;
  return x & 0xffffff;
}

Particle particle_advance(Particle p, uint rounds) {
  uint r = uint(p.seed);
  if (p.life <= 0) {
    r = particle_random(r);
    p.position = float2(float(r % 4096) / 2048 - 1, -1);
    p.velocity = float2((float((r >> 12) % 4096) / 4096 - .5) * .3,
                       .5 + float(r % 1024) / 2048);
    p.life = 1 + float(r % 4096) / 1024;
  }
  for (uint n = 0; n < rounds; ++n) r = particle_random(r);
  float nx = rounds ? (float(r % 4096) / 4096 - .5) * .6 : 0;
  float ny = rounds ? (float((r >> 12) % 4096) / 4096 - .5) * .6 : 0;
  float ax = (-p.position.x * .15 - p.velocity.x * .05) + nx;
  float ay = ((-p.position.y * .15 - p.velocity.y * .05) - .12) + ny;
  p.velocity.x += ax * 0.016666667;
  p.velocity.y += ay * 0.016666667;
  p.position.x += p.velocity.x * 0.016666667;
  p.position.y += p.velocity.y * 0.016666667;
  p.life -= 0.016666667; p.seed = float(r);
  return p;
}

kernel void particle_update(device Particle *particles [[buffer(0)]],
    constant ParticleArgs &a [[buffer(1)]], uint i [[thread_position_in_grid]]) {
  if (i < a.count) particles[i] = particle_advance(particles[i], a.rounds);
}

// Same ceil(count/jobs) consecutive ranges as Bend, without its fork runtime.
kernel void particle_update_tiled(device Particle *particles [[buffer(0)]],
    constant ParticleArgs &a [[buffer(1)]], uint job [[thread_position_in_grid]]) {
  uint chunk = (a.count + a.jobs - 1) / a.jobs;
  uint start = min(job * chunk, a.count), end = min(start + chunk, a.count);
  for (uint i = start; i < end; ++i) particles[i] = particle_advance(particles[i], a.rounds);
}

// Neighbouring lanes access neighbouring particles on every iteration.
kernel void particle_update_strided(device Particle *particles [[buffer(0)]],
    constant ParticleArgs &a [[buffer(1)]], uint job [[thread_position_in_grid]]) {
  for (uint i = job; i < a.count; i += a.jobs)
    particles[i] = particle_advance(particles[i], a.rounds);
}

struct ParticleVertex { float4 position [[position]]; float2 local; float4 color; };

vertex ParticleVertex particle_vertex(uint v [[vertex_id]], uint i [[instance_id]],
    device const Particle *particles [[buffer(0)]], constant ParticleArgs &a [[buffer(1)]]) {
  const float2 corners[6] = {float2(-1,-1), float2(1,-1), float2(-1,1),
                             float2(-1,1), float2(1,-1), float2(1,1)};
  Particle p = particles[i];
  float2 local = corners[v];
  float2 offset = local * a.radius * 2 / float2(a.width, a.height);
  float3 color = float3(.3 + float(i % 7) / 10, .5 + float(i % 3) / 8, 1);
  return {float4(p.position + offset, 0, 1), local,
          float4(color, clamp(p.life * 2, 0.0f, 1.0f) * .35)};
}

fragment float4 particle_fragment(ParticleVertex p [[stage_in]]) {
  return float4(p.color.rgb, p.color.a * max(1.0f - length(p.local), 0.0f));
}
