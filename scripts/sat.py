"""Compile and solve a DIMACS CNF with the Bend or C DPLL experiment (0..32 variables)."""
import argparse
import itertools
import os
from pathlib import Path
import re
import subprocess
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]


class Problem(NamedTuple):
    variables: int
    clauses: tuple[tuple[int, ...], ...]


def validate_problem(problem: Problem) -> None:
    if not 0 <= problem.variables <= 32 or len(problem.clauses) > 4096:
        raise ValueError("supported CNF: 0..32 variables, at most 4096 clauses")
    if any(not isinstance(lit, int) or isinstance(lit, bool) or not 1 <= abs(lit) <= problem.variables
           for clause in problem.clauses for lit in clause):
        raise ValueError("literal outside declared variable range")


def parse_dimacs(text: str) -> Problem:
    header = None
    tokens = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("c"):
            continue
        if line.startswith("p"):
            fields = line.split()
            if header is not None or len(fields) != 4 or fields[:2] != ["p", "cnf"]:
                raise ValueError("expected one 'p cnf <variables> <clauses>' header")
            try:
                header = tuple(map(int, fields[2:]))
            except ValueError as error:
                raise ValueError("invalid CNF header") from error
            if not 0 <= header[0] <= 32 or not 0 <= header[1] <= 4096:
                raise ValueError("supported CNF: 0..32 variables, at most 4096 clauses")
        elif header is None:
            raise ValueError("CNF header must precede literals")
        else:
            tokens.extend(line.split())
    if header is None:
        raise ValueError("missing CNF header")
    clauses, current = [], []
    for token in tokens:
        if not re.fullmatch(r"[+-]?\d+", token):
            raise ValueError(f"invalid literal: {token}")
        literal = int(token)
        if literal == 0:
            clauses.append(tuple(current))
            current = []
        else:
            current.append(literal)
    if current or len(clauses) != header[1]:
        raise ValueError("unterminated clause or clause count mismatch")
    problem = Problem(header[0], tuple(clauses))
    validate_problem(problem)
    return problem


def masks(problem: Problem) -> list[tuple[int, int]]:
    return [(sum(1 << (lit - 1) for lit in set(clause) if lit > 0),
             sum(1 << (-lit - 1) for lit in set(clause) if lit < 0)) for clause in problem.clauses]


def random_3sat(variables: int, index: int) -> Problem:
    """Input oracle for sat-input.bend/sat.c; deliberately has no planted model."""
    if not 3 <= variables <= 32 or not 0 <= index < 2 ** 24:
        raise ValueError("random 3-SAT requires variables=3..32 and index=0..2^24-1")
    s = (((index + 1) * 2654435761) & 0xffffffff) ^ 1013904223
    clauses = []
    for _ in range(variables * 17 // 4):
        a = s % variables
        b = (a + 1 + ((s >> 8) % (variables - 1))) % variables
        c = (s >> 16) % variables
        for _ in range(2):
            if c in (a, b):
                c = (c + 1) % variables
        clauses.append(tuple((v + 1) * (1 if s & (1 << (24 + sign)) else -1)
                             for sign, v in enumerate((a, b, c))))
        s = (s ^ (s << 13)) & 0xffffffff
        s ^= s >> 17
        s = (s ^ (s << 5)) & 0xffffffff
    return Problem(variables, tuple(clauses))


def pigeonhole(pigeons: int, holes: int) -> Problem:
    """Exactly one hole per pigeon, with no shared hole."""
    if pigeons < 1 or holes < 1 or pigeons * holes > 32:
        raise ValueError("pigeonhole requires positive dimensions and at most 32 variables")
    rows = [tuple(p * holes + h + 1 for h in range(holes)) for p in range(pigeons)]
    clauses = list(rows)
    clauses.extend((-a, -b) for row in rows for a, b in itertools.combinations(row, 2))
    clauses.extend((-rows[a][h], -rows[b][h]) for h in range(holes)
                   for a, b in itertools.combinations(range(pigeons), 2))
    return Problem(pigeons * holes, tuple(clauses))


def parse_answer(text: str) -> dict:
    match = re.fullmatch(r"status=(SAT|UNSAT|UNKNOWN) model=(\d+) nodes=(\d+) errors=(\d+)\n?", text)
    if not match:
        raise ValueError(f"invalid SAT answer: {text!r}")
    status = match[1]
    model, nodes, errors = map(int, match.groups()[1:])
    if max(model, nodes, errors) >= 2 ** 32 or (status != "SAT" and model != 0):
        raise ValueError("invalid SAT answer fields")
    if (status == "UNKNOWN") != (errors != 0):
        raise ValueError("exhaustion must be reported as UNKNOWN")
    return {"status": status, "model": model, "nodes": nodes, "errors": errors}


def build_problems(root: Path, work: Path, problems: list[Problem], split_depth: int = 0,
                   repetitions: int = 1) -> tuple[Path, Path]:
    if not problems or not 0 <= split_depth <= 12 or not 1 <= repetitions <= 2 ** 20:
        raise ValueError("need problems, split-depth=0..12 and repetitions=1..2^20")
    for problem in problems:
        validate_problem(problem)
        if split_depth > problem.variables:
            raise ValueError("split depth exceeds declared variables")
    work.mkdir(parents=True, exist_ok=True)
    source_dir = root / "examples/algorithms"
    (work / "sat-core.bend").write_text((source_dir / "sat-core.bend").read_text())
    bend_source = ["import Base", "import ./sat-core.bend as S"]
    bend_source.append(f'''def repeat(f: Nat, +cnf: S.CNF, acc: S.Answer) -> S.Answer:
  match f:
    case 0n: acc
    case 1n+p: repeat(p, cnf, S.merge(acc, S.partition({split_depth}n, cnf)))''')
    c_source = ['#include "sat-core.h"', '#include <errno.h>', '#include <string.h>']
    for i, problem in enumerate(problems):
        encoded = masks(problem)
        term = "S.End{}"
        for pos, neg in reversed(encoded):
            term = f"S.Clause{{{pos}, {neg}, {term}}}"
        bend_source.append(f"def problem_{i}() -> S.CNF:\n  {term}")
        array = ",".join(f"{{{p}u,{n}u}}" for p, n in encoded) or "{0,0}"
        c_source.append(f"static const Clause problem_{i}[] = {{{array}}};")
    bend_source.append("def main() -> IO(Unit):")
    action = "IO.pure(Unit, Unit{})"
    for i in reversed(range(len(problems))):
        action = (f"IO.bind(Unit, Unit, IO.print(S.show(repeat({repetitions}n, problem_{i}(), S.Unsat{{0}}))), u => {action})")
    bend_source.append("  " + action)
    c_source.append('''int main(int argc, char **argv) {
  unsigned threads = 1;
  if (argc != 1) {
    if (argc != 3 || strcmp(argv[1], "--threads")) return 2;
    char *end;
    errno = 0;
    long value = strtol(argv[2], &end, 10);
    if (errno || end == argv[2] || *end || value < 1 || value > 128) return 2;
    threads = (unsigned)value;
  }
  unsigned errors = 0;''')
    for i, problem in enumerate(problems):
        c_source.append(f"  Answer a{i} = sat_repeat_partition(problem_{i}, {len(problem.clauses)}, {split_depth}, threads, {repetitions});")
        c_source.append(f"  sat_show(a{i}); errors |= a{i}.errors;")
    c_source.append("  return errors ? 1 : 0;\n}")
    (work / "solve.bend").write_text("\n\n".join(bend_source) + "\n")
    (work / "solve.c").write_text("\n".join(c_source) + "\n")
    bend, c = work / "solve", work / "solve_c"
    subprocess.run([str(root / "scripts/bend.sh"), str(work / "solve.bend"), "-o", str(bend)],
                   env={**os.environ, "BEND_NO_TELEMETRY": "1"}, stdout=subprocess.DEVNULL, check=True)
    subprocess.run([os.environ.get("CC", "clang"), "-std=c11", "-O3", "-pthread", "-I", str(source_dir),
                    str(work / "solve.c"), "-o", str(c)], check=True)
    return bend, c


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cnf", type=Path)
    parser.add_argument("--backend", choices=("bend", "c"), default="bend")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--split-depth", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.threads <= 128:
        parser.error("threads must be 1..128")
    try:
        problem = parse_dimacs(args.cnf.read_text())
        bend, c = build_problems(ROOT, ROOT / "build/sat/solve", [problem], args.split_depth)
    except ValueError as error:
        parser.error(str(error))
    binary = bend if args.backend == "bend" else c
    extra = ["--gpu", "off"] if args.backend == "bend" else []
    answer = parse_answer(subprocess.check_output([str(binary), "--threads", str(args.threads), *extra], text=True))
    if answer["status"] == "SAT":
        if not all(any(bool(answer["model"] & (1 << (abs(lit) - 1))) == (lit > 0) for lit in clause)
                   for clause in problem.clauses):
            raise RuntimeError("solver returned an invalid witness")
        print("s SATISFIABLE")
        print("v", *(i if answer["model"] & (1 << (i - 1)) else -i for i in range(1, problem.variables + 1)), 0)
    elif answer["status"] == "UNSAT":
        print("s UNSATISFIABLE")
    else:
        raise RuntimeError("solver exhausted its termination bound")
    print(f'c nodes={answer["nodes"]} split-depth={args.split_depth} threads={args.threads}')


if __name__ == "__main__":
    main()
