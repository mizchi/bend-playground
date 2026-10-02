"""Direct shared-buffer output and CPU read/copy contracts."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import grid_gpu
import grid_gpu_flat
from grid_cases import dashboard, cards, nested


class GridGpuFlatTest(unittest.TestCase):
    def test_buffer_contract_and_invalid_arguments(self):
        self.assertEqual(grid_gpu_flat.buffer_shape(99, 12), (512, 21))
        self.assertEqual(grid_gpu_flat.buffer_shape(341, 12), (2048, 23))
        for nodes, depth in [(0, 1), (2049, 1), (2, -1), (2, 17)]:
            with self.subTest(nodes=nodes, depth=depth), self.assertRaises(ValueError):
                grid_gpu_flat.buffer_shape(nodes, depth)

    def test_direct_parser_rejects_bad_buffer_or_gpu_fallback(self):
        row = {**{key: 1 for key in grid_gpu_flat.FIELDS}, "round": 0, "pages": 4,
               "nodes": 8, "errors": 0, "checksum": 42, "read_checksum": 42,
               "read_again_checksum": 42, "copy_checksum": 42, "bytes": 192,
               "buffer_bytes": 128, "stride": 8, "layout_ns": 100}
        self.assertEqual(grid_gpu_flat.parse_profile(json.dumps(row), gpu=True)["buffer_bytes"], 128)
        for patch in [{"buffer_bytes": 127}, {"stride": 7}, {"gpu_commands": 0},
                      {"read_ns": -1}, {"read_checksum": 43}, {"copy_checksum": 43}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                grid_gpu_flat.parse_profile(json.dumps({**row, **patch}), gpu=True)

    def test_all_coordinates_and_reads_match_tree_and_c(self):
        cases = [dashboard(), cards(24), nested(4),
                 {"id": "single", "width": 601, "height": 300,
                  "grid": {"columns": "1fr", "rows": "1fr"}, "children": []},
                 {"id": "edge", "width": 601, "height": 300,
                  "grid": {"columns": "minmax(300px, 1fr) 3fr", "rows": "0.25fr 0.25fr", "gap": 3},
                  "children": [{"id": "a", "span_row": 2}, {"id": "b"}]}]
        with tempfile.TemporaryDirectory() as tmp:
            for i, page in enumerate(cases):
                work = Path(tmp) / str(i)
                flat = grid_gpu_flat.build_case(ROOT, work / "flat", page, 2, samples=2, warmups=1)
                tree = grid_gpu.build_case(ROOT, work / "tree", page, 2, samples=2, warmups=1)
                expected_path = work / "c.bin"
                expected = grid_gpu.run_case(tree["c"], "c", 1, dump=expected_path)
                rectangles = grid_gpu.read_rectangles(expected_path)
                for threads, gpu in [(1, False), (4, False), (4, True)]:
                    path = work / f"flat-{threads}-{gpu}.bin"
                    rows = grid_gpu_flat.run_case(flat, threads, gpu, dump=path)
                    self.assertEqual([r["round"] for r in rows], [0, 1, 2])
                    for row, wanted in zip(rows, expected):
                        self.assertEqual(row["checksum"], wanted["checksum"])
                        self.assertEqual(row["read_checksum"], wanted["checksum"])
                        self.assertEqual(row["copy_checksum"], wanted["checksum"])
                    actual = grid_gpu.read_rectangles(path)
                    self.assertEqual(set(actual), set(rectangles))
                    for key in actual:
                        for a, b in zip(actual[key], rectangles[key]):
                            self.assertAlmostEqual(a, b, delta=.002)


if __name__ == "__main__":
    unittest.main(verbosity=2)
