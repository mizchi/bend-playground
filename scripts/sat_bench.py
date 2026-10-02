"""Measure prefix partitions of one CNF, separately from independent SAT batches."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from algorithm_bench import ROOT, command_output, environment_metadata
from sat import build_problems, parse_answer, parse_dimacs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cnf", type=Path)
    parser.add_argument("--repetitions", type=int, default=2048)
    parser.add_argument("--depths", type=int, nargs="+", default=[0, 2, 4, 8])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    problem = parse_dimacs(args.cnf.read_text())
    if not 1 <= args.repetitions <= 2 ** 20 or any(not 0 <= d <= min(12, problem.variables) for d in args.depths):
        parser.error("invalid repetitions or prefix depth")
    os.environ["BEND_NO_TELEMETRY"] = "1"
    metadata = environment_metadata()
    metadata.update(c_flags="-std=c11 -O3 -pthread",
                    c_scheduler="one atomic-queued prefix per job; persistent pthread pool and a barrier between repetitions; threads capped at prefixes",
                    cnf=str(args.cnf), cnf_sha256=hashlib.sha256(args.cnf.read_bytes()).hexdigest(),
                    repetitions=args.repetitions,
                    method="serial best-of-3 wall clock; repeated same CNF sequentially; startup included; compilation excluded")
    record = {"environment": metadata, "cases": []}
    print(f'CNF: {problem.variables} variables, {len(problem.clauses)} clauses, repeat={args.repetitions}', flush=True)
    print("depth C-1 C-all Bend-1 Bend-all nodes/solve", flush=True)
    verdict = None
    for depth in args.depths:
        bend, c = build_problems(ROOT, ROOT / f"build/sat/partition-{depth}", [problem], depth, args.repetitions)
        results, expected = {}, None
        for label, binary, extra in [("c-1", c, ["--threads", "1"]),
                                     ("c-all", c, ["--threads", str(metadata["threads"])]),
                                     ("bend-1", bend, ["--threads", "1", "--gpu", "off"]),
                                     ("bend-all", bend, ["--threads", str(metadata["threads"]), "--gpu", "off"])]:
            answer = parse_answer(command_output(str(binary), *extra))
            if answer["errors"] or (expected is not None and answer != expected):
                raise RuntimeError(f"depth={depth}, {label}: incorrect or mismatched SAT answer {answer}")
            if verdict is not None and answer["status"] != verdict:
                raise RuntimeError("partitioning changed the SAT verdict")
            if answer["status"] == "SAT" and not all(any(bool(answer["model"] & (1 << (abs(lit) - 1))) == (lit > 0)
                                                           for lit in clause) for clause in problem.clauses):
                raise RuntimeError("invalid SAT witness")
            expected, verdict = answer, answer["status"]
            results[label] = json.loads(command_output("python3", str(ROOT / "scripts/benchmark.py"), "--json", str(binary), *extra))
        record["cases"].append({"depth": depth, "prefixes": 1 << depth, "output": expected, "timings": results})
        print(depth, *(f'{results[k]["best_seconds"]:.3f}s' for k in ["c-1", "c-all", "bend-1", "bend-all"]),
              expected["nodes"] / args.repetitions, flush=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    if "thermal_before" in metadata:
        metadata["thermal_after"] = command_output("pmset", "-g", "therm")
    if args.output:
        args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
