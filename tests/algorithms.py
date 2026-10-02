"""Independent oracles for irregular search, factorization and AST rewriting."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("algorithm_bench", ROOT / "scripts/algorithm_bench.py")
suite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suite)
MASK = (1 << 32) - 1
PRIMES = [1009, 1013, 1019, 1021, 1031, 1033, 1039, 1049,
          1051, 1061, 1063, 1069, 1087, 1091, 1093, 1097]


def rng(x):
    x = (x ^ (x << 13)) & MASK
    x ^= x >> 17
    return (x ^ (x << 5)) & MASK


def seed(i):
    return (((i + 1) * 2654435761) & MASK) ^ 1013904223


def factor_checksum(dep):
    total = 0
    for i in range(1 << dep):
        s = rng(seed(i))
        n = PRIMES[s & 15] * PRIMES[(s >> 8) & 15]
        # Trial division is independent of the timed Pollard rho algorithm.
        p = next(d for d in range(2, 1100) if n % d == 0)
        q = n // p
        total = (total + ((p * 2654435761 + q) & MASK) * (i + 1)) & MASK
    return total


def expr(depth, s):
    if depth == 0:
        return ("var", (s >> 8) & 3) if s & 3 == 0 else ("const", (s >> 8) & 15)
    a, b = expr(depth - 1, rng(s)), expr(depth - 1, rng(s ^ 277803737))
    return ("add" if s & 1 == 0 else "mul", a, b)


def evaluate(t):
    if t[0] == "const":
        return t[1]
    if t[0] == "var":
        return [2, 3, 5, 7][t[1]]
    a, b = evaluate(t[1]), evaluate(t[2])
    return (a + b if t[0] == "add" else a * b) & MASK


def simplified_size(t):
    """Abstract interpretation returns known constants and live node counts."""
    if t[0] == "const":
        return t[1], 1
    if t[0] == "var":
        return None, 1
    a, na = simplified_size(t[1])
    b, nb = simplified_size(t[2])
    if a is not None and b is not None:
        return ((a + b if t[0] == "add" else a * b) & MASK), 1
    if t[0] == "add":
        if a == 0:
            return b, nb
        if b == 0:
            return a, na
    else:
        if a == 0 or b == 0:
            return 0, 1
        if a == 1:
            return b, nb
        if b == 1:
            return a, na
    return None, 1 + na + nb


class AlgorithmTest(unittest.TestCase):
    def compare(self, directory, name, dep, size=None):
        bend, c = suite.build_case(ROOT, Path(directory), name, dep, size)
        outputs = []
        for binary, args in [(bend, ["--threads", "1", "--gpu", "off"]),
                             (bend, ["--threads", "4", "--gpu", "off"]),
                             (c, ["--threads", "1"]), (c, ["--threads", "4"])]:
            result = subprocess.run([str(binary), *args], text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            outputs.append(suite.parse_result(result.stdout))
        self.assertTrue(all(output == outputs[0] for output in outputs), outputs)
        self.assertEqual(outputs[0]["errors"], 0)
        return outputs[0]

    def test_nqueens_matches_known_solution_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            for n, expected in [(4, 2), (8, 92), (10, 724)]:
                with self.subTest(n=n):
                    result = self.compare(directory, "nqueens", 8, n)
                    self.assertEqual(result["checksum"], expected)

    def test_pollard_rho_matches_independent_trial_division(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.compare(directory, "rho", 6)
        self.assertEqual(result["checksum"], factor_checksum(6))
        self.assertGreater(result["detail"], 0)

    def test_ast_fold_preserves_values_and_removes_nodes(self):
        with tempfile.TemporaryDirectory() as directory:
            for depth in [4, 9]:
                with self.subTest(depth=depth):
                    result = self.compare(directory, "astfold", 4, depth)
                    trees = [expr(depth, seed(i)) for i in range(16)]
                    checksum = sum(evaluate(t) * (i + 1) for i, t in enumerate(trees)) & MASK
                    count = sum(simplified_size(t)[1] for t in trees)
                    self.assertEqual(result["checksum"], checksum)
                    self.assertEqual(result["detail"], count)
                    self.assertLess(count, 16 * ((1 << (depth + 1)) - 1))

    def test_result_parser_rejects_missing_or_extra_fields(self):
        for output in ["checksum=1", "checksum=1 detail=2 errors=0 junk=4", "garbage",
                       "checksum=4294967296 detail=0 errors=0"]:
            with self.subTest(output=output):
                with self.assertRaises(ValueError):
                    suite.parse_result(output)

    def test_invalid_case_cannot_change_the_problem_silently(self):
        for case in [("nqueens", 7, 8), ("nqueens", 8, 17), ("rho", 4, 8), ("astfold", 4, 0)]:
            with self.subTest(case=case):
                with self.assertRaises(ValueError):
                    suite.validate_case(*case)

    def test_default_cli_selects_all_programs(self):
        args = suite.parse_args([])
        self.assertEqual(tuple(args.programs), suite.NAMES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
