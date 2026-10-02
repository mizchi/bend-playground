"""CPU/GPU task-boundary accounting and identical-work controls."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import device_bench


def oracle(depth, rounds, seed=305419896):
    total = 0
    for i in range(1 << depth):
        x = (seed + i) & 0xffffffff
        for _ in range(rounds):
            x ^= (x << 13) & 0xffffffff
            x ^= x >> 17
            x ^= (x << 5) & 0xffffffff
        total = (total + x) & 0xffffffff
    return total


class DeviceBenchTest(unittest.TestCase):
    def test_rejects_impossible_grouping_before_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            for depth, batch in [(4, -1), (4, 5), (17, 1)]:
                with self.subTest(depth=depth, batch=batch), self.assertRaises(ValueError):
                    device_bench.build_case(ROOT, Path(tmp), depth, batch, 1, 1, 0)

    def test_parser_rejects_fallback_and_bad_accounting(self):
        row = {"round":0,"calls":4,"jobs":16,"checksum":42,"elapsed_ns":100,
               "gpu_commands":4,"gpu_execution_ns":60,"gpu_wait_ns":80,"gpu_submit_ns":10}
        self.assertEqual(device_bench.parse_profile(json.dumps(row), 16, 4, True), row)
        for patch in [{"gpu_commands":0},{"calls":3},{"jobs":15},
                      {"gpu_wait_ns":101},{"elapsed_ns":-1},{"checksum":2**32}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                device_bench.parse_profile(json.dumps({**row,**patch}),16,4,True)

    def test_cpu_and_gpu_batch_boundaries_preserve_all_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            for rounds in [0, 3]:
                wanted = oracle(4, rounds)
                for batch in [0, 2, 4]:
                    work = Path(tmp) / f"{rounds}-{batch}"
                    binary = device_bench.build_case(ROOT, work, 4, batch, rounds, 2, 1)
                    for gpu in [False, True]:
                        rows = device_bench.run_case(binary, 16, 1 << (4-batch), gpu)
                        self.assertEqual([r["round"] for r in rows], [0,1,2])
                        self.assertTrue(all(r["checksum"]==wanted for r in rows))


if __name__ == "__main__":
    unittest.main(verbosity=2)
