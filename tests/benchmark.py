"""Check benchmark units and subprocess handling without timing real workloads."""
import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/benchmark.py"


class BenchmarkTest(unittest.TestCase):
    def test_benchmark_scripts_parse_with_system_bash(self):
        for path in ["examples/sim/bench.sh", "examples/sim/probes/fork_cost.sh"]:
            with self.subTest(path=path):
                result = subprocess.run(
                    ["/bin/bash", "-n", str(ROOT / path)],
                    text=True, capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_max_rss_has_the_same_units_on_macos_and_linux(self):
        spec = importlib.util.spec_from_file_location("benchmark", SCRIPT)
        benchmark = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(benchmark)
        self.assertEqual(benchmark.max_rss_mib(67633152, "darwin"), 64.5)
        self.assertEqual(benchmark.max_rss_mib(66048, "linux"), 64.5)

    def test_measurement_suppresses_program_output(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--rss", sys.executable,
             "-c", "print('program output')"],
            text=True, capture_output=True, check=True,
        )
        self.assertRegex(result.stdout, r"^\d+\.\d{3}s \d+MB\n$")
        rss = int(re.search(r"(\d+)MB", result.stdout).group(1))
        self.assertGreater(rss, 0)
        self.assertLess(rss, 256)

    def test_failed_program_does_not_produce_a_measurement(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), sys.executable, "-c", "raise SystemExit(7)"],
            text=True, capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
