"""Verify FFI measurements, control loops and regression units."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("ffi_bench", ROOT / "scripts/ffi_bench.py")
ffi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ffi)


def oracle(steps):
    x = 0x12345678
    for _ in range(steps):
        x = (x ^ (x << 13)) & 0xffffffff
        x ^= x >> 17
        x = (x ^ (x << 5)) & 0xffffffff
    return x


class FfiTest(unittest.TestCase):
    def test_native_and_pure_loops_match_independent_oracle(self):
        with tempfile.TemporaryDirectory() as directory:
            for calls, rounds in [(0, 1), (17, 0), (1, 1), (31, 7)]:
                binaries = ffi.build_case(ROOT, Path(directory), calls, rounds)
                for name, binary in binaries.items():
                    modes = [1] if name == "c-direct" else [1, 4]
                    for threads in modes:
                        args = [] if name == "c-direct" else ["--threads", str(threads), "--gpu", "off"]
                        run = subprocess.run([str(binary), *args], text=True, capture_output=True, timeout=30)
                        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                        self.assertEqual(ffi.parse_result(run.stdout), oracle(calls * rounds))

    def test_regression_removes_startup_and_reports_nanoseconds(self):
        fit = ffi.fit_cost([(0, 0.003), (1000000, 0.203), (2000000, 0.403), (4000000, 0.803)])
        self.assertAlmostEqual(fit["intercept_seconds"], 0.003)
        self.assertAlmostEqual(fit["nanoseconds_per_call"], 200)
        self.assertAlmostEqual(fit["r_squared"], 1)

    def test_fit_rejects_degenerate_or_nonfinite_measurements(self):
        for samples in [[], [(1, 0.1)], [(1, 0.1), (1, 0.2)], [(0, float("nan")), (1, 0.1)],
                        [(-1, 0.1), (1, 0.2)], [(0, -0.1), (1, 0.2)]]:
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                ffi.fit_cost(samples)

    def test_builder_rejects_invalid_sizes_before_compilation(self):
        with tempfile.TemporaryDirectory() as directory:
            for calls, rounds in [(-1, 1), (2 ** 26 + 1, 1), (1, -1), (1, 4097)]:
                with self.subTest(calls=calls, rounds=rounds), self.assertRaises(ValueError):
                    ffi.build_case(ROOT, Path(directory), calls, rounds)

    def test_output_parser_rejects_invalid_values(self):
        for output in ["garbage", "checksum=4294967296", "checksum=-1", "checksum=1 extra=2"]:
            with self.subTest(output=output), self.assertRaises(ValueError):
                ffi.parse_result(output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
