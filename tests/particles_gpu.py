"""GPU dispatch diagnostics and independent particle/mapping correctness."""
import json
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import particles
import particles_gpu
oracle_spec = importlib.util.spec_from_file_location('particle_oracle', ROOT / 'tests/particles.py')
oracle = importlib.util.module_from_spec(oracle_spec)
oracle_spec.loader.exec_module(oracle)
initial, update = oracle.initial, oracle.update


class ParticleGPU(unittest.TestCase):
    def test_probe_preserves_existing_code_and_guards_pinned_anchors(self):
        device = 'static const char BEND_SRC[] = {\n1, 2, 3, 0\n};'
        source = device + '''
static void gpu_kernel(u32 pass, u32 groups) {
  [gpu_enc setComputePipelineState:gpu_pso];
  [gpu_enc memoryBarrierWithScope:MTLBarrierScopeBuffers];
}
    gpu_enc = [cb computeCommandEncoder];
    gpu_run(f);
    [gpu_enc endEncoding];'''
        transformed = particles_gpu.instrument_gpu(source)
        self.assertIn(device, transformed)
        self.assertIn('[gpu_enc updateFence:particle_probe_fence]', transformed)
        self.assertIn('if (!particle_probe_active) [gpu_enc endEncoding]', transformed)
        for incompatible in [source.replace('gpu_run(f);', 'gpu_run(0);'), transformed]:
            with self.assertRaises(ValueError):
                particles_gpu.instrument_gpu(incompatible)

    def test_counter_conversion_and_rejection(self):
        row = dict(kind='gpu_dispatch_profile', frame=5, backend='bend-gpu', count=17,
                   jobs=1024, noise_rounds=64, cpu_before=1000, gpu_before=2000,
                   cpu_after=5000, gpu_after=4000,
                   dispatches=[dict(name='grow', pass_index=0, groups=1, threads=128,
                                    begin=2200, end=2500)])
        result = particles_gpu.parse_probe(json.dumps(row))
        self.assertEqual(result['dispatches'][0]['elapsed_ns'], 600)
        for patch in [dict(gpu_after=2000), dict(cpu_after=1000), dict(backend='c-cpu'),
                      dict(dispatches=[]), dict(jobs=65), dict(count=True)]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                particles_gpu.parse_probe(json.dumps({**row, **patch}))
        for patch in [dict(end=2100), dict(begin=2**64-1), dict(threads=0),
                      dict(pass_index=3), dict(end=5000)]:
            dispatch = {**row['dispatches'][0], **patch}
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                particles_gpu.parse_probe(json.dumps({**row, 'dispatches':[dispatch]}))

    def test_metal_controls_share_counts_and_grains(self):
        cases = particles_gpu.specifications([17, 10003], [0, 64], [1024, 16384])
        self.assertEqual(len(cases), 36)
        self.assertEqual(len(set(cases)), 36)
        for count in [17, 10003]:
            for rounds in [0, 64]:
                self.assertEqual(len([c for c in cases if c[:2] == (count, rounds) and c[3] == 'particle']), 1)
                for jobs in [1024, 16384]:
                    self.assertEqual({c[3] for c in cases if c[:3] == (count, rounds, jobs)},
                        {'bend', 'leaf', 'tiled', 'strided'} | ({'particle'} if jobs == 1024 else set()))

    def test_all_gpu_mappings_and_profiled_passes_match_oracle(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            for rounds in [0, 64]:
                binary = particles.build(work / str(rounds), noise_rounds=rounds, jobs=1024,
                                         variant='flat', gpu_probe=True)
                reference = {}
                for mapping in ('bend', 'leaf', 'particle', 'tiled', 'strided'):
                    for count in [1, 17, 10003]:
                        dump = work / f'{rounds}-{mapping}-{count}'
                        rows, probes, meta = particles_gpu.run(binary, mapping, count, frames=4,
                            width=64, height=32, verify=True, dump=dump, profile=True)
                        plain_dump = work / f'{rounds}-{mapping}-{count}-plain'
                        plain_rows, plain_probes, _ = particles_gpu.run(binary, mapping, count, frames=4,
                            width=64, height=32, verify=True, dump=plain_dump)
                        self.assertEqual(len(plain_rows), 4)
                        self.assertEqual(plain_probes, [])
                        self.assertEqual(len(rows), 4)
                        self.assertEqual(len(probes), 4)
                        self.assertEqual(meta['kind'], 'gpu_metadata')
                        self.assertTrue(meta['stage_boundary'])
                        for frame, probe in enumerate(probes):
                            self.assertEqual(probe['frame'], frame)
                            self.assertEqual(probe['count'], count)
                            self.assertEqual(probe['noise_rounds'], rounds)
                            self.assertTrue(all(d['elapsed_ns'] > 0 for d in probe['dispatches']))
                            if mapping == 'bend':
                                self.assertEqual([d['pass_index'] for d in probe['dispatches']], [0, 0, 1, 2])
                                self.assertEqual([d['groups'] for d in probe['dispatches']], [1, 128, 128, 1])
                            else:
                                self.assertEqual(len(probe['dispatches']), 1)
                        expected = [initial(i) for i in range(count)]
                        for frame in range(4):
                            expected = [update(p, rounds) for p in expected]
                            raw = (dump / f'{frame}.particles').read_bytes()
                            self.assertEqual(raw, (plain_dump / f'{frame}.particles').read_bytes())
                            self.assertEqual(len(raw), count * 32)
                            for i, actual in enumerate(struct.iter_unpack('=8f', raw)):
                                self.assertEqual(actual[5:], tuple(expected[i][5:]))
                                for got, wanted in zip(actual[:5], expected[i][:5]):
                                    self.assertAlmostEqual(got, wanted, delta=2e-6)
                            image = (dump / f'{frame}.nv12').read_bytes()
                            self.assertLessEqual(max(abs(a-b) for a,b in zip(image,
                                (plain_dump / f'{frame}.nv12').read_bytes())), 2)
                            key = count, frame
                            if mapping == 'bend':
                                reference[key] = image
                            else:
                                self.assertEqual(len(image), len(reference[key]))
                                self.assertLessEqual(max(abs(a-b) for a,b in zip(image, reference[key])), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
