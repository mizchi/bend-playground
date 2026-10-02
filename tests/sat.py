"""Check SAT answers against exhaustive truth tables, including witnesses."""
import importlib.util
import itertools
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sat_cli", ROOT / "scripts/sat.py")
sat = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sat
spec.loader.exec_module(sat)
suite_spec = importlib.util.spec_from_file_location("algorithm_bench", ROOT / "scripts/algorithm_bench.py")
suite = importlib.util.module_from_spec(suite_spec)
suite_spec.loader.exec_module(suite)


def holds(problem, model):
    return all(any(bool(model & (1 << (abs(literal) - 1))) == (literal > 0)
                   for literal in clause) for clause in problem.clauses)


def exhaustive(problem):
    return any(holds(problem, model) for model in range(1 << problem.variables))


class SatTest(unittest.TestCase):
    def compare(self, problems, split=0):
        with tempfile.TemporaryDirectory() as directory:
            bend, c = sat.build_problems(ROOT, Path(directory), problems, split)
            outputs = []
            for binary, args in [(bend, ["--threads", "1", "--gpu", "off"]),
                                 (bend, ["--threads", "4", "--gpu", "off"]),
                                 (c, ["--threads", "1"]), (c, ["--threads", "4"])]:
                run = subprocess.run([str(binary), *args], capture_output=True, text=True, timeout=60)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                outputs.append([sat.parse_answer(line) for line in run.stdout.splitlines()])
        self.assertTrue(all(output == outputs[0] for output in outputs), outputs)
        self.assertEqual(len(outputs[0]), len(problems))
        for problem, answer in zip(problems, outputs[0]):
            self.assertEqual(answer["errors"], 0)
            self.assertEqual(answer["status"] == "SAT", exhaustive(problem))
            self.assertGreater(answer["nodes"], 0)
            if answer["status"] == "SAT":
                self.assertLess(answer["model"], 1 << problem.variables)
                self.assertTrue(holds(problem, answer["model"]))
        return outputs[0]

    def test_dimacs_comments_multiline_duplicate_literals_and_empty_clause(self):
        text = "c example\np cnf 3 3\n1 1\n-2 0 3 -3 0\nc comment\n0\n"
        self.assertEqual(sat.parse_dimacs(text), sat.Problem(3, ((1, 1, -2), (3, -3), ())))
        self.assertEqual(sat.parse_dimacs("p cnf 0 0\n"), sat.Problem(0, ()))
        self.assertEqual(sat.parse_dimacs("p cnf 32 1\n-32 0\n").variables, 32)

    def test_dimacs_rejects_unsupported_or_malformed_inputs(self):
        for text in ["1 0", "p cnf 33 0", "p cnf -1 0", "p cnf 2 4097",
                     "p cnf 2 1\n3 0", "p cnf 2 1\n1", "p cnf 2 0\n0",
                     "p cnf 2 1\n1 x 0", "p cnf 2 1\n", "p cnf 2 0\np cnf 2 0"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                sat.parse_dimacs(text)

    def test_truth_tables_units_tautologies_and_backtracking(self):
        # The last formula needs to reject x1=true before finding x1=false.
        formulas = [sat.Problem(0, ()), sat.Problem(0, ((),)),
                    sat.Problem(1, ((1,),)), sat.Problem(1, ((1,), (-1,))),
                    sat.Problem(2, ((1, -1), (2, 2))),
                    sat.Problem(4, ((1,), (-1, 2), (-2, 3), (-3, 4))),
                    sat.Problem(2, tuple(itertools.product((1, -1), (2, -2)))),
                    sat.Problem(3, ((-1, 2), (-1, -2), (1, 3)))]
        answers = self.compare(formulas)
        # One DPLL node suffices with units; an unused second branch is not explored.
        self.assertEqual(answers[2]["nodes"], 1)
        self.assertEqual(answers[-1]["nodes"], 3)
        self.assertFalse(answers[-1]["model"] & 1)

    def test_random_cnfs_against_exhaustive_oracle(self):
        rng = random.Random(20261002)
        problems = [sat.Problem(6, tuple(tuple(rng.choice((-1, 1)) * v for v in rng.sample(range(1, 7), 3))
                                        for _ in range(count))) for count in range(1, 49)]
        self.compare(problems)

    def test_prefix_partition_preserves_sat_unsat_and_witnesses(self):
        # Every assignment has exactly one falsified clause in the UNSAT formula.
        clauses = tuple(tuple(v if sign else -v for v, sign in enumerate(bits, 1))
                        for bits in itertools.product((False, True), repeat=4))
        self.compare([sat.Problem(4, clauses), sat.Problem(4, clauses[:-1]),
                      sat.Problem(4, ((-1,), (2, -3), (-2, 4)))], split=3)

    def test_pigeonhole_and_repeated_single_formula(self):
        self.compare([sat.pigeonhole(3, 2), sat.pigeonhole(2, 2)])
        problem = sat.pigeonhole(3, 2)
        with tempfile.TemporaryDirectory() as directory:
            bend, c = sat.build_problems(ROOT, Path(directory), [problem], 2, repetitions=3)
            outputs = [sat.parse_answer(subprocess.check_output([str(binary), *args], text=True).strip())
                       for binary, args in [(bend, ["--threads", "4", "--gpu", "off"]), (c, ["--threads", "4"])]]
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0]["status"], "UNSAT")
        single = self.compare([problem], split=2)[0]
        self.assertEqual(outputs[0]["nodes"], single["nodes"] * 3)

    def test_bit_32_and_invalid_split_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            problems = [sat.Problem(32, ((32,), (-1,))), sat.Problem(32, ((32,),) * 4096)]
            bend, c = sat.build_problems(ROOT, Path(directory), problems, 0)
            for binary, args in [(bend, ["--threads", "1", "--gpu", "off"]), (c, ["--threads", "1"])]:
                answers = subprocess.check_output([str(binary), *args], text=True).splitlines()
                self.assertEqual(len(answers), 2)
                for output in answers:
                    answer = sat.parse_answer(output)
                    self.assertEqual(answer["status"], "SAT")
                    self.assertEqual(answer["model"], 1 << 31)
            for split in (-1, 2, 13):
                with self.assertRaises(ValueError):
                    sat.build_problems(ROOT, Path(directory), [sat.Problem(1, ((1,),))], split)

    def test_answer_parser_rejects_unknown_and_invalid_witness_fields(self):
        for text in ["status=UNSAT model=1 nodes=1 errors=0", "status=SAT model=4294967296 nodes=1 errors=0",
                     "status=UNKNOWN model=0 nodes=1 errors=0", "status=SAT model=1 nodes=1 errors=0 trailing"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                sat.parse_answer(text)

    def test_generated_batch_matches_truth_tables_and_validated_witnesses(self):
        problems = [sat.random_3sat(8, i) for i in range(32)]
        answers = self.compare(problems)
        self.assertIn("SAT", {a["status"] for a in answers})
        self.assertIn("UNSAT", {a["status"] for a in answers})
        checksum = sum(((a["model"] + (2654435761 if a["status"] == "SAT" else 0)) & 0xffffffff) * (i + 1)
                       for i, a in enumerate(answers)) & 0xffffffff
        with tempfile.TemporaryDirectory() as directory:
            bend, c = suite.build_case(ROOT, Path(directory), "sat", 5, 8)
            for binary, args in [(bend, ["--threads", "1", "--gpu", "off"]),
                                 (bend, ["--threads", "4", "--gpu", "off"]),
                                 (c, ["--threads", "1"]), (c, ["--threads", "4"])]:
                answer = suite.parse_result(subprocess.check_output([str(binary), *args], text=True))
                self.assertEqual(answer, {"checksum": checksum, "detail": sum(a["nodes"] for a in answers), "errors": 0})


if __name__ == "__main__":
    unittest.main(verbosity=2)
