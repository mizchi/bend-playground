"""Bend/GPUI ABI, real Metal dispatch, and offscreen pixel correctness."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import gpui


class GpuiTest(unittest.TestCase):
    def test_options_reject_invalid_sizes_and_counts(self):
        self.assertEqual(gpui.dimensions(33, 17), (32, 16))
        for width, height in [(0, 10), (10, 1), (2049, 10), (True, 10)]:
            with self.subTest(width=width, height=height), self.assertRaises(ValueError):
                gpui.dimensions(width, height)

    def test_profile_rejects_fallback_and_payload_reads(self):
        row = dict(frame=0, width=32, height=16, kind="pixels", bend_ns=1000,
                   bend_gpu_commands=1, bend_gpu_ns=500, convert_gpu_ns=100,
                   convert_wait_ns=200, handoff_ns=300, drop_ns=0, frame_ready_ns=1300,
                   cpu_payload_read_bytes=0, verified_pixels=512)
        self.assertEqual(gpui.parse_frame(json.dumps(row), True)["width"], 32)
        for patch in [dict(bend_gpu_commands=0), dict(cpu_payload_read_bytes=4),
                      dict(width=31), dict(bend_ns=-1), dict(kind="bogus")]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                gpui.parse_frame(json.dumps({**row, **patch}), True)

    def test_cpu_gpu_pixels_and_grid_without_production_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            for mode in ["shader", "grid"]:
                binary = gpui.build(mode, work / mode)
                for gpu in [False, True]:
                    for width, height in [(32, 16), (384, 256)]:
                        rows = gpui.run(binary, gpu=gpu, frames=3, width=width, height=height,
                                        headless=True, verify=True)
                        self.assertEqual([r["frame"] for r in rows], [0, 1, 2])
                        self.assertTrue(all(r["verified_pixels"] == width * height for r in rows))
                        self.assertTrue(all(r["cpu_payload_read_bytes"] == 0 for r in rows))


if __name__ == "__main__":
    unittest.main(verbosity=2)
