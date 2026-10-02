"""Build and compare irregular algorithms on C/Bend, using CPU threads only."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("nqueens", "rho", "astfold", "sat")


def parse_result(output: str) -> dict[str, int]:
    match = re.fullmatch(r"checksum=(\d+) detail=(\d+) errors=(\d+)\n?", output)
    if not match:
        raise ValueError(f"invalid algorithm output: {output!r}")
    values = list(map(int, match.groups()))
    if any(value >= 2 ** 32 for value in values):
        raise ValueError("result fields must be U32")
    return dict(zip(("checksum", "detail", "errors"), values))


def validate_case(name: str, dep: int, size: Optional[int]) -> None:
    if name not in NAMES or not 0 <= dep <= 24:
        raise ValueError("invalid program or batch depth")
    if name == "nqueens" and (dep != 8 or size is None or not 4 <= size <= 16):
        raise ValueError("nqueens requires dep=8 and size=4..16")
    if name == "astfold" and (size is None or not 1 <= size <= 14):
        raise ValueError("astfold requires size=1..14")
    if name == "rho" and size is not None:
        raise ValueError("rho has no size knob")
    if name == "sat" and (size is None or not 3 <= size <= 32):
        raise ValueError("sat requires size=3..32")


def build_case(root: Path, out: Path, name: str, dep: int,
               size: Optional[int] = None) -> tuple[Path, Path]:
    validate_case(name, dep, size)
    source_dir = root / "examples/algorithms"
    work = out / f"{name}-{dep}-{size}"
    work.mkdir(parents=True, exist_ok=True)
    source = (source_dir / f"{name}.bend").read_text()
    knobs = {"dep": dep}
    if size is not None:
        knobs["size"] = size
    for knob, value in knobs.items():
        source, count = re.subn(rf"(?m)^(def {knob}\(\) -> Nat:\n)  \d+n$",
                                rf"\g<1>  {value}n", source)
        if count != 1:
            raise ValueError(f"missing or duplicate {knob} knob in {name}")
    (work / f"{name}.bend").write_text(source)
    (work / "common.bend").write_text((source_dir / "common.bend").read_text())
    if name == "sat":
        for dependency in ("sat-core.bend", "sat-input.bend"):
            (work / dependency).write_text((source_dir / dependency).read_text())
    bend, c = work / name, work / f"{name}_c"
    subprocess.run([str(root / "scripts/bend.sh"), str(work / f"{name}.bend"), "-o", str(bend)],
                   env={**os.environ, "BEND_NO_TELEMETRY": "1"}, stdout=subprocess.DEVNULL, check=True)
    flags = [f"-DDEP={dep}"] + ([f"-DSIZE={size}"] if size is not None else [])
    subprocess.run([os.environ.get("CC", "clang"), "-std=c11", "-O3", "-ffp-contract=off", "-pthread",
                    *flags, str(source_dir / f"{name}.c"), "-o", str(c)], check=True)
    return bend, c


def command_output(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("programs", nargs="*", metavar="PROGRAM", help="nqueens, rho, astfold, sat (default: all)")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--case", action="append", dest="case_labels", help="select a suite case label; repeatable")
    args = parser.parse_args(argv)
    args.programs = args.programs or list(NAMES)
    if set(args.programs) - set(NAMES):
        parser.error("unknown program")
    cases = json.loads((ROOT / "examples/algorithms/suite.json").read_text())
    if args.case_labels and set(args.case_labels) - {case["label"] for case in cases}:
        parser.error("unknown case label")
    return args


def environment_metadata() -> dict:
    """Capture the actual checkout, tools and sources used by either CPU suite."""
    threads = min(os.cpu_count() or 1, 128)
    bend_repo = os.environ.get("BEND_REPO", str(ROOT / "upstream/bend"))
    metadata = {
        "date": datetime.now().astimezone().isoformat(timespec="seconds"),
        "playground_commit": command_output("git", "-C", str(ROOT), "rev-parse", "HEAD"),
        "bend_commit": command_output("git", "-C", bend_repo, "rev-parse", "HEAD"),
        "bend_version": command_output(str(ROOT / "scripts/bend.sh"), "version"),
        "platform": command_output("uname", "-sm"), "threads": threads,
        "compiler": command_output(os.environ.get("CC", "clang"), "--version").splitlines()[0],
        "c_flags": "-std=c11 -O3 -ffp-contract=off -pthread",
        "python": sys.version.split()[0],
        "method": "serial best-of-3 wall clock; process startup included; CPU only; compilation excluded",
        "rss_unit": "MiB (helper output label MB)",
        "c_scheduler": "pthread workers; dynamic atomic queue; chunks 1 for nqueens, 16 otherwise",
        "source_state": "local algorithm additions on the recorded playground commit",
        "background": "existing UI applications running; no benchmark/build jobs launched concurrently by this run",
        "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in [*sorted((ROOT / "examples/algorithms").iterdir()),
                                       ROOT / "scripts/algorithm_bench.py", ROOT / "scripts/benchmark.py",
                                       ROOT / "scripts/sat.py", ROOT / "scripts/sat_bench.py"]
                          if path.is_file() and (path.suffix in (".bend", ".c", ".h", ".py") or path.name == "suite.json")},
    }
    if metadata["platform"].startswith("Darwin"):
        metadata.update(cpu=command_output("sysctl", "-n", "machdep.cpu.brand_string"),
                        memory_bytes=int(command_output("sysctl", "-n", "hw.memsize")),
                        os_version=command_output("sw_vers", "-productVersion"),
                        thermal_before=command_output("pmset", "-g", "therm"))
    return metadata


def main() -> None:
    os.environ["BEND_NO_TELEMETRY"] = "1"
    args = parse_args()
    selected = args.programs
    cases = json.loads((ROOT / "examples/algorithms/suite.json").read_text())
    metadata = environment_metadata()
    threads = metadata["threads"]
    record = {"environment": metadata, "cases": []}
    print(json.dumps(metadata, ensure_ascii=False), flush=True)
    print("program size C-1 C-all Bend-1 Bend-all output", flush=True)
    for case in cases:
        if case["name"] not in selected or (args.case_labels and case["label"] not in args.case_labels):
            continue
        bend, c = build_case(ROOT, ROOT / "build/algorithms", case["name"], case["dep"], case.get("size"))
        results = {}
        expected = None
        for label, binary, extra in [("c-1", c, ["--threads", "1"]),
                                     ("c-all", c, ["--threads", str(threads)]),
                                     ("bend-1", bend, ["--threads", "1", "--gpu", "off"]),
                                     ("bend-all", bend, ["--threads", str(threads), "--gpu", "off"])]:
            output = command_output(str(binary), *extra)
            value = parse_result(output)
            if value["errors"] or (expected is not None and value != expected):
                raise RuntimeError(f"{case}: failed correctness check for {label}: {output}")
            expected = value
            timing = command_output("python3", str(ROOT / "scripts/benchmark.py"), "--json", str(binary), *extra)
            results[label] = json.loads(timing)
        record["cases"].append({**case, "output": expected, "timings": results})
        print(case["name"], case["label"], *(f'{results[k]["best_seconds"]:.3f}s' for k in
                                              ["c-1", "c-all", "bend-1", "bend-all"]), expected, flush=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    if "thermal_before" in metadata:
        metadata["thermal_after"] = command_output("pmset", "-g", "therm")
    if args.output:
        args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
