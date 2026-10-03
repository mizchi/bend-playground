"""Independent float32 simulation oracle and persistent CPU/GPU state checks."""
import math
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import particles
import particles_bench


def f32(x):
    return struct.unpack("=f", struct.pack("=f", x))[0]


DT = f32(1 / 60)


def rng(x):
    x = (x ^ (x << 13)) & 0xffffffff
    x = (x ^ (x >> 17)) & 0xffffffff
    return (x ^ (x << 5)) & 0xffffff


def initial(i):
    seed = rng((0x123456 + i) & 0xffffff)
    return [f32(f32(seed % 4096) / 2048 - 1),
            f32(f32((seed >> 12) % 4096) / 2048 - 1),
            f32((i % 17 - 8) / 32), f32((i % 13 - 6) / 32),
            f32((i % 240) * DT), float(seed), 0., 0.]


def update(p, rounds):
    x, y, vx, vy, life, seed, a, b = p
    seed = int(seed)
    if life <= 0:
        seed = rng(seed)
        x = f32(f32(seed % 4096) / 2048 - 1)
        y = -1.
        vx = f32(f32(f32((seed >> 12) % 4096) / 4096 - .5) * .3)
        vy = f32(.5 + f32(f32(seed % 1024) / 2048))
        life = f32(1 + f32(f32(seed % 4096) / 1024))
    for _ in range(rounds):
        seed = rng(seed)
    nx = ny = 0.
    if rounds:
        nx = f32(f32(f32(seed % 4096) / 4096 - .5) * .6)
        ny = f32(f32(f32((seed >> 12) % 4096) / 4096 - .5) * .6)
    ax = f32(f32(f32(-x * .15) - f32(vx * .05)) + nx)
    ay = f32(f32(f32(f32(-y * .15) - f32(vy * .05)) - .12) + ny)
    vx = f32(vx + f32(ax * DT))
    vy = f32(vy + f32(ay * DT))
    return [f32(x + f32(vx * DT)), f32(y + f32(vy * DT)), vx, vy,
            f32(life - DT), float(seed), a, b]


def single_particle_image(p, width, height):
    """Independent circular sprite, additive BGRA8 blending, and NV12 oracle."""
    cx, cy = (p[0] + 1) * width / 2, (1 - p[1]) * height / 2
    rgb = []
    for y in range(height):
        for x in range(width):
            distance = math.hypot((x + .5 - cx) / 2, (y + .5 - cy) / 2)
            alpha = min(1, max(0, p[4] * 2)) * .35 * max(0, 1 - distance)
            rgb.append([round(min(1, bg / 255 + color * alpha) * 255) / 255
                        for bg, color in zip((16, 23, 36), (.3, .5, 1))])
    ys, uvs = [], []
    for r, g, b in rgb:
        ys.append(round((.299 * r + .587 * g + .114 * b) * 255))
    for y in range(0, height, 2):
        for x in range(0, width, 2):
            u, v = 0., 0.
            for dy in range(2):
                for dx in range(2):
                    r, g, b = rgb[(y + dy) * width + x + dx]
                    u += -.168736 * r - .331264 * g + .5 * b + .5
                    v += .5 * r - .418688 * g - .081312 * b + .5
            uvs.extend((round(u / 4 * 255), round(v / 4 * 255)))
    return bytes(ys + uvs)


class ParticleTest(unittest.TestCase):
    def test_benchmark_compares_matching_threads_without_duplicate_controls(self):
        specs = particles_bench.specifications(['callback', 'flat'], [0], [64, 1024], [17],
                        ['bend-cpu', 'c-cpu', 'c-direct', 'metal'], [1, 4])
        self.assertEqual(len(specs), 15)
        self.assertEqual(len(set(specs)), 15)
        self.assertEqual({s[-1] for s in specs if s[-2] == 'c-direct'}, {1})
        self.assertEqual(len([s for s in specs if s[-2] == 'metal']), 1)
        self.assertEqual({s[0] for s in specs if s[-2] == 'c-cpu'}, {'callback'})

    def test_c_cpu_contract_and_thread_options(self):
        self.assertEqual(particles.options('c-cpu', 17, 4, 64, 32), (64, 32))
        self.assertEqual(particles.options('c-direct', 17, 4, 64, 32), (64, 32))
        self.assertEqual(particles.command(Path('/unused'), 'c-cpu', threads=4)[-2:], ['--threads', '4'])
        for value in [0, 129, True]:
            with self.subTest(threads=value), self.assertRaises(ValueError):
                particles.command(Path('/unused'), 'c-cpu', threads=value)
        with self.assertRaises(ValueError):
            particles.command(Path('/unused'), 'c-direct', threads=4)

    def test_c_workers_reuse_pool_across_counts_grains_and_rounds(self):
        # This portable harness uses only the production C kernel, not oracle.h.
        # Change the work description every frame while keeping one worker pool.
        driver = '''#include "cpu.h"
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
int main(int argc, char **argv) {
  if (argc != 3) return 1;
  unsigned threads = (unsigned)atoi(argv[1]), direct = (unsigned)atoi(argv[2]);
  ParticleCPU *pool = particle_cpu_create(threads);
  if (!pool || particle_cpu_create(0) || particle_cpu_create(129)) return 2;
  Particle *state = calloc(10003, sizeof *state);
  if (!state || fread(state, sizeof *state, 10003, stdin) != 10003) return 3;
  ParticleCPUStats stats;
  if (particle_cpu_run(pool, state, 17, 65, 0, &stats) != EINVAL ||
      particle_cpu_direct(state, 0, 64, 0, &stats) != EINVAL) return 4;
  unsigned config[3];
  while (fread(config, sizeof config, 1, stdin) == 1) {
    int result = direct ? particle_cpu_direct(state, config[0], config[1], config[2], &stats)
      : particle_cpu_run(pool, state, config[0], config[1], config[2], &stats);
    if (result || stats.completed_jobs != config[1] || !stats.workers_used ||
        stats.workers_used > (direct ? 1 : threads)) return 5;
    if (fwrite(state, sizeof *state, 10003, stdout) != 10003) return 6;
  }
  particle_cpu_destroy(pool); free(state); return 0;
}
'''
        configurations = [(1, 16384, 0), (17, 64, 64), (10003, 1024, 64), (4097, 4096, 0)] * 3
        start = [initial(i)[:6] + [float(i) + .5, -float(i) - .5] for i in range(10003)]
        packed = b''.join(struct.pack('=8f', *p) for p in start)
        expected, snapshots = start, []
        for count, jobs, rounds in configurations:
            expected = [update(p, rounds) if i < count else p for i, p in enumerate(expected)]
            snapshots.append(expected)
            packed += struct.pack('=3I', count, jobs, rounds)
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / 'driver.c').write_text(driver)
            binary = work / 'cpu-test'
            sanitizer = os.environ.get('BEND_PARTICLE_C_SANITIZER')
            if sanitizer not in (None, 'thread', 'address'):
                raise ValueError('invalid C test sanitizer')
            flags = ['-fsanitize=' + sanitizer, '-g'] if sanitizer else []
            subprocess.run(['clang', '-std=c11', '-O3', '-ffp-contract=off', '-pthread', *flags,
                            '-I', str(particles.SOURCE), str(work / 'driver.c'),
                            str(particles.SOURCE / 'cpu.c'), '-o', str(binary)], check=True)
            for threads, direct in [(1, 0), (4, 0), (1, 1)]:
                result = subprocess.run([str(binary), str(threads), str(direct)],
                                        input=packed, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                stride = 10003 * 32
                self.assertEqual(len(result.stdout), len(configurations) * stride)
                for frame, snapshot in enumerate(snapshots):
                    raw = result.stdout[frame*stride:(frame+1)*stride]
                    for i, actual in enumerate(struct.iter_unpack('=8f', raw)):
                        self.assertEqual(actual[5:], tuple(snapshot[i][5:]))
                        for got, wanted in zip(actual[:5], snapshot[i][:5]):
                            self.assertTrue(math.isfinite(got))
                            self.assertAlmostEqual(got, wanted, delta=2e-6)

    def test_contract_rejects_invalid_inputs_and_gpu_fallback(self):
        self.assertEqual(particles.options('bend-gpu', 10000, 4, 65, 33), (64, 32))
        self.assertEqual(particles.default_jobs('bend-cpu', 100000), 1024)
        self.assertEqual(particles.default_jobs('bend-gpu', 1000000), 16384)
        self.assertEqual(particles.default_jobs('bend-gpu', 10000), 4096)
        for args in [('invalid', 1, 1, 32, 16), ('metal', 1000001, 1, 32, 16),
                     ('bend-cpu', True, 1, 32, 16), ('metal', 1, -1, 32, 16)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                particles.options(*args)
        with self.assertRaises(ValueError):
            particles.run_env('metal', 1, 0, 32, 16, headless=True)
        with self.assertRaises(ValueError):
            particles.run_env('metal', 1, 1, 32, 16, dump=Path('/unused'))
        with self.assertRaises(ValueError):
            particles.build(variant='invalid')
        # Real measurements must contain dispatch evidence and consistent phases.
        row = dict.fromkeys(particles.FIELDS, 0)
        row.update(frame=0, backend='bend-gpu', width=32, height=16, count=17, jobs=4096, threads=10,
                   radius_px=2, buffer_bytes=1024, state_allocations=1, update_ns=1000,
                   update_gpu_ns=500, update_wait_ns=800, bend_gpu_commands=1,
                   draw_gpu_ns=10, convert_gpu_ns=10, render_wait_ns=100,
                   render_ns=200, frame_ready_ns=1200)
        particles.parse_frame(json.dumps(row), 'bend-gpu')
        for patch in [dict(bend_gpu_commands=0), dict(cpu_readback_bytes=4),
                      dict(state_allocations=2), dict(frame_ready_ns=999), dict(buffer_bytes=512),
                      dict(update_wait_ns=2000), dict(width=31), dict(verified_particles=1)]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                particles.parse_frame(json.dumps({**row, **patch}), 'bend-gpu')
        c_row = {**row, 'backend': 'c-cpu', 'update_gpu_ns': 0, 'update_wait_ns': 0,
                 'bend_gpu_commands': 0, 'c_completed_jobs': 4096, 'c_workers_used': 4}
        particles.parse_frame(json.dumps(c_row), 'c-cpu')
        for patch in [dict(c_completed_jobs=0), dict(c_workers_used=0), dict(c_workers_used=11),
                      dict(update_gpu_ns=1), dict(update_wait_ns=1), dict(threads=0)]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                particles.parse_frame(json.dumps({**c_row, **patch}), 'c-cpu')

    def test_persistent_updates_match_independent_float32_oracle(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            for rounds in [0, 64]:
                reference_images = {}
                configurations = [(variant, backend) for variant in ['callback', 'flat']
                                  for backend in particles.BACKENDS
                                  if (variant == 'callback' and backend in ('bend-cpu', 'bend-gpu', 'metal'))
                                  or (variant == 'flat' and backend != 'metal')]
                binaries = {variant: particles.build(work / f'{rounds}-{variant}',
                            noise_rounds=rounds, variant=variant) for variant in ['callback', 'flat']}
                report = particles.codegen_report((work / f'{rounds}-flat/bend.c').read_text())
                self.assertEqual(len(report['particle_loops']), 1)
                self.assertEqual(report['particle_loops'][0]['heap_alloc_sites'], 0)
                self.assertEqual(report['particle_loops'][0]['closure_sites'], 0)
                self.assertEqual(report['particle_loops'][0]['dynamic_apply_sites'], 0)
                for variant, backend in configurations:
                    for count in [1, 17, 10003]:
                        dump = work / f"dump-{rounds}-{variant}-{backend}-{count}"
                        rows = particles.run(binaries[variant], backend, count=count, frames=4,
                                             width=64, height=32, verify=True, dump=dump)
                        self.assertEqual([r["frame"] for r in rows], list(range(4)))
                        self.assertEqual(len({r["buffer_offset"] for r in rows}), 1)
                        self.assertTrue(all(r["cpu_readback_bytes"] == 0 for r in rows))
                        self.assertTrue(all(r["verified_particles"] == count for r in rows))
                        self.assertTrue(all(r["state_allocations"] == 1 for r in rows))
                        expected = [initial(i) for i in range(count)]
                        for frame in range(4):
                            expected = [update(p, rounds) for p in expected]
                            raw = (dump / f"{frame}.particles").read_bytes()
                            self.assertEqual(len(raw), count * 32)
                            for i, actual in enumerate(struct.iter_unpack("=8f", raw)):
                                self.assertEqual(actual[5:], tuple(expected[i][5:]))
                                for got, wanted in zip(actual[:5], expected[i][:5]):
                                    self.assertTrue(math.isfinite(got))
                                    self.assertAlmostEqual(got, wanted, delta=2e-6)
                            image = (dump / f"{frame}.nv12").read_bytes()
                            self.assertEqual(len(image), 64 * 32 * 3 // 2)
                            self.assertGreater(max(image[:64 * 32]), 22)
                            if count == 1:
                                oracle_image = single_particle_image(expected[0], 64, 32)
                                self.assertLessEqual(max(abs(a-b) for a, b in zip(image, oracle_image)), 2)
                            key = (count, frame)
                            if variant == 'callback' and backend == 'bend-cpu':
                                reference_images[key] = image
                            else:
                                self.assertLessEqual(max(abs(a-b) for a, b in zip(image, reference_images[key])), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
