"""Full rectangle GPU handoff, real dispatch and timing contracts."""
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import grid
import grid_gpu
from grid_cases import dashboard, cards, nested


class GridGpuTest(unittest.TestCase):
    def test_profile_parser_rejects_missing_gpu_and_invalid_timings(self):
        sample = {"round": 0, "pages": 4, "nodes": 12, "errors": 0, "checksum": 42,
                  "bytes": 288, "layout_ns": 100, "materialize_ns": 10, "checksum_ns": 3,
                  "drop_ns": 2, "gpu_commands": 1, "gpu_execution_ns": 70,
                  "gpu_wait_ns": 80, "gpu_submit_ns": 5}
        self.assertEqual(grid_gpu.parse_profile(json.dumps(sample), gpu=True)["pages"], 4)
        for patch in [{"gpu_commands": 0}, {"materialize_ns": -1},
                      {"gpu_execution_ns": math.nan}, {"bytes": 1}, {"nodes": 0},
                      {"errors": 1}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                grid_gpu.parse_profile(json.dumps({**sample, **patch}), gpu=True)

    def test_builder_rejects_invalid_batch_before_compilation(self):
        with tempfile.TemporaryDirectory() as tmp:
            for depth in [-1, 17]:
                with self.subTest(depth=depth), self.assertRaises(ValueError):
                    grid_gpu.build_case(ROOT, Path(tmp), dashboard(), depth, samples=1, warmups=0)

    def test_instrumentation_rejects_unknown_runtime(self):
        with self.assertRaises(ValueError):
            grid_gpu.instrument_metal("unrecognized compiler output")

    def test_rectangle_reader_rejects_malformed_payloads(self):
        row = struct.pack("=IIffff", 0, 0, 0, 0, 100, 100)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rectangles.bin"
            for payload in [row[:-1], row + row, struct.pack("=IIffff", 0, 0, math.nan, 0, 100, 100)]:
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    path.write_bytes(payload)
                    grid_gpu.read_rectangles(path)

    def test_original_page_forks_also_return_full_gpu_geometry(self):
        page = nested(2)
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            binaries = grid_gpu.build_case(ROOT, work, page, 2, samples=1, warmups=0, page_parallel=True)
            expected_path, actual_path = work / "c.bin", work / "gpu.bin"
            expected = grid_gpu.run_case(binaries["c"], "c", 1, dump=expected_path)
            actual = grid_gpu.run_case(binaries["bend"], "bend", 4, True, dump=actual_path)
            self.assertEqual(actual[0]["checksum"], expected[0]["checksum"])
            wanted, got = grid_gpu.read_rectangles(expected_path), grid_gpu.read_rectangles(actual_path)
            self.assertEqual(set(wanted), set(got))
            for key in wanted:
                for a, b in zip(got[key], wanted[key]):
                    self.assertAlmostEqual(a, b, delta=.002)

    def test_full_gpu_geometry_matches_c_and_cpu_for_dynamic_pages(self):
        cases = [dashboard(), cards(24), nested(2),
                 {"id": "edge", "width": 601, "height": 300,
                  "grid": {"columns": "minmax(300px, 1fr) 3fr", "rows": "0.25fr 0.25fr", "gap": 3},
                  "children": [{"id": "a", "span_row": 2}, {"id": "b"}]}]
        with tempfile.TemporaryDirectory() as tmp:
            for i, page in enumerate(cases):
                work = Path(tmp) / str(i)
                binaries = grid_gpu.build_case(ROOT, work, page, 2, samples=2, warmups=1)
                outputs = []
                for backend, threads, gpu in [("c", 1, False), ("c", 4, False),
                                               ("bend", 1, False), ("bend", 4, False),
                                               ("bend", 4, True)]:
                    dump = work / f"{backend}-{threads}-{gpu}.bin"
                    records = grid_gpu.run_case(binaries[backend], backend, threads, gpu, dump=dump)
                    self.assertEqual(len(records), 3)
                    self.assertEqual([r["round"] for r in records], [0, 1, 2])
                    self.assertEqual(records[-1]["pages"], 4)
                    self.assertEqual(records[-1]["bytes"], 4 * len(grid.normalize(page)["names"]) * 24)
                    self.assertGreaterEqual(records[-1]["layout_ns"], records[-1]["gpu_wait_ns"])
                    outputs.append((records[-1], grid_gpu.read_rectangles(dump)))
                reference, rectangles = outputs[0]
                for record, actual in outputs[1:]:
                    self.assertEqual(record["checksum"], reference["checksum"])
                    self.assertEqual(set(actual), set(rectangles))
                    for key in actual:
                        for value, expected in zip(actual[key], rectangles[key]):
                            self.assertAlmostEqual(value, expected, delta=.002)
                # Independently verify the exported final batch against the existing C engine.
                final_pages = [{**page, "width": page["width"] + (8 + j) % 97} for j in range(4)]
                original = grid.build_cases(ROOT, work / "oracle", final_pages)
                answers = grid.run_cases(original["c"], "c", final_pages)
                names = grid.normalize(page)["names"]
                for j, answer in enumerate(answers):
                    for index, name in enumerate(names):
                        for value, expected in zip(rectangles[j, index], answer["boxes"][name]):
                            self.assertAlmostEqual(value, expected, delta=.002)


if __name__ == "__main__":
    unittest.main(verbosity=2)
