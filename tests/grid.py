"""Grid contracts and native engines, independent of the browser oracle."""
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import grid


def page(columns="1fr 2fr", rows="100px", children=None, **css):
    return {"id": "root", "width": 600, "height": 300,
            "grid": {"columns": columns, "rows": rows, "auto_rows": "60px", **css},
            "children": children if children is not None else [{"id": "a"}, {"id": "b"}]}


class GridTest(unittest.TestCase):
    def test_css_track_parser_and_repeat(self):
        self.assertEqual(grid.parse_tracks("120px repeat(2, minmax(80px, 1fr) 2fr)"),
                         [(120, 120, 0), (80, 80, 1), (0, 0, 2), (80, 80, 1), (0, 0, 2)])
        self.assertEqual(grid.parse_tracks("minmax(100px, 50px) 0.25fr"),
                         [(100, 100, 0), (0, 0, .25)])

    def test_unsupported_or_invalid_inputs_fail_explicitly(self):
        for tracks in ["auto", "min-content", "10%", "repeat(auto-fit, 1fr)",
                       "minmax(auto, 1fr)", "-1px", "NaNfr", "repeat(33, 1fr)",
                       "minmax(10px,,20px)", "repeat(2, 1fr,)"]:
            with self.subTest(tracks=tracks), self.assertRaises(ValueError):
                grid.parse_tracks(tracks)
        for value in [page(unknown="ignored"), page(children=[{"id": "a", "span_column": 33}]),
                      page(children=[{"id": "a", "column": -1}]),
                      page(children=[{"id": "a"}, {"id": "a"}]),
                      {**page(), "width": math.inf}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                grid.normalize(value)

    def test_native_engines_match_hand_computed_geometry(self):
        cases = [page(), page("minmax(300px, 1fr) 3fr"), page("0.25fr 0.25fr"),
                 page("100px 100px", "40px", [
                     {"id": "a", "span_column": 2}, {"id": "b"}, {"id": "c"}], gap=10),
                 page("repeat(3, 1fr)", "100px", [
                     {"id": "a", "span_column": 2}, {"id": "b", "span_column": 2},
                     {"id": "c"}], dense=True),
                 page("minmax(50px, 100px) minmax(0px, 300px)")]
        expected = [
            {"a": (0, 0, 200, 100), "b": (200, 0, 400, 100)},
            {"a": (0, 0, 300, 100), "b": (300, 0, 300, 100)},
            {"a": (0, 0, 150, 100), "b": (150, 0, 150, 100)},
            {"a": (0, 0, 210, 40), "b": (0, 50, 100, 60), "c": (110, 50, 100, 60)},
            {"a": (0, 0, 400, 100), "b": (0, 100, 400, 60), "c": (400, 0, 200, 100)},
            {"a": (0, 0, 100, 100), "b": (100, 0, 300, 100)},
        ]
        with tempfile.TemporaryDirectory() as directory:
            binaries = grid.build_cases(ROOT, Path(directory), cases)
            for backend, binary in binaries.items():
                for threads in [1, 4]:
                    answers = grid.run_cases(binary, backend, cases, threads)
                    for answer, wanted in zip(answers, expected):
                        self.assertEqual(answer["errors"], 0)
                        for name, rect in wanted.items():
                            for actual, target in zip(answer["boxes"][name], rect):
                                self.assertAlmostEqual(actual, target, places=3)

    def test_capacity_exhaustion_is_an_error(self):
        case = page("1fr", "40px", [{"id": "a", "row": 128, "span_row": 2}])
        with self.assertRaises(ValueError):
            grid.normalize(case)

    def test_sparse_fixed_rows_keep_cursors_by_start_row(self):
        case = page("100px 100px 100px", "repeat(4, 100px)", [
            {"id": "block", "column": 1, "row": 3, "span_column": 2},
            {"id": "a", "row": 2, "span_row": 2},
            {"id": "b", "row": 1, "span_row": 2}])
        with tempfile.TemporaryDirectory() as directory:
            binaries = grid.build_cases(ROOT, Path(directory), [case])
            for backend, binary in binaries.items():
                answer = grid.run_cases(binary, backend, [case])[0]
                self.assertEqual(answer["boxes"]["a"], [200, 100, 100, 200])
                self.assertEqual(answer["boxes"]["b"], [0, 0, 100, 200])

    def test_placement_exhaustion_never_wraps_owned_arrays(self):
        case = page("1fr", "", [{"id": f"n{i}"} for i in range(129)])
        with tempfile.TemporaryDirectory() as directory:
            binaries = grid.build_cases(ROOT, Path(directory), [case])
            for backend, binary in binaries.items():
                self.assertGreater(grid.run_cases(binary, backend, [case])[0]["errors"], 0)

    def test_benchmark_counts_all_dynamic_layouts(self):
        cases = [page()]
        with tempfile.TemporaryDirectory() as directory:
            binaries = grid.build_cases(ROOT, Path(directory), cases, bench=(3, 5))
            outputs = []
            for backend, binary in binaries.items():
                for threads in [1, 4]:
                    extra = ["--threads", str(threads)] + (["--gpu", "off"] if backend == "bend" else [])
                    outputs.append(subprocess.check_output([str(binary), *extra], text=True).strip())
            self.assertEqual(len(set(outputs)), 1)
            self.assertIn("nodes=120 errors=0", outputs[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
