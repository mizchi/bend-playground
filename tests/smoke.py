"""Check that the playground runs independently of the caller's directory."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PlaygroundSmokeTest(unittest.TestCase):
    def run_bend(self, *args, cwd, **env):
        environ = {k: v for k, v in os.environ.items() if k != "BEND_REPO"}
        environ.update(BEND_NO_TELEMETRY="1", **env)
        return subprocess.run(
            ["bash", str(ROOT / "scripts/bend.sh"), *map(str, args)],
            cwd=cwd, env=environ, text=True, capture_output=True, timeout=60,
        )

    def test_run_from_unrelated_directory_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="bend playground ") as directory:
            Path(directory, "hello world.bend").write_text(
                (ROOT / "examples/intro/s01_hello.bend").read_text()
            )
            result = self.run_bend("hello world.bend", cwd=directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "hello")

    def test_missing_compiler_explains_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_bend("version", cwd=directory, BEND_REPO=directory)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("just setup", result.stderr)

    def test_intro_includes_expected_type_errors(self):
        environ = {k: v for k, v in os.environ.items() if k != "BEND_REPO"}
        environ["BEND_NO_TELEMETRY"] = "1"
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                ["bash", str(ROOT / "examples/intro/check.sh")],
                cwd=directory, env=environ, text=True, capture_output=True, timeout=60,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: 13 / 13", result.stdout)

    def test_just_forwards_multiple_arguments(self):
        with tempfile.TemporaryDirectory(prefix="bend playground ") as directory:
            sample = Path(directory, "hello world.bend")
            sample.write_text((ROOT / "examples/intro/s01_hello.bend").read_text())
            result = subprocess.run(
                ["just", "--justfile", str(ROOT / "justfile"), "bend", str(sample), "--check-only"],
                cwd=directory, env={**os.environ, "BEND_NO_TELEMETRY": "1"},
                text=True, capture_output=True, timeout=60,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "All terms check.")

    def test_fwht_involution(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_bend(ROOT / "examples/fwht_check.bend", cwd=directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            "d=1  involution: True",
            "d=2  involution: True",
            "d=5  involution: True",
            "d=10 involution: True",
        ])


if __name__ == "__main__":
    unittest.main(verbosity=2)
