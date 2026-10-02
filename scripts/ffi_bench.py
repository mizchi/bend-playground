"""Measure native C FFI round trips with scalar arguments and no per-call printing."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess

from algorithm_bench import ROOT, command_output, environment_metadata

SOURCE = ROOT / "examples/ffi"
KINDS = {"bend-pure": "pure", "bend-io-pure": "io-pure", "bend-ffi": "foreign"}


def parse_result(output: str) -> int:
    match = re.fullmatch(r"checksum=(\d+)\n?", output)
    if not match or int(match[1]) >= 2 ** 32:
        raise ValueError(f"invalid FFI output: {output!r}")
    return int(match[1])


def fit_cost(samples: list[tuple[int, float]]) -> dict:
    """OLS T(N)=intercept+slope*N; report slope in ns per call, never as latency."""
    if len(samples) < 2 or any(n < 0 or t < 0 or not math.isfinite(t) for n, t in samples):
        raise ValueError("need finite nonnegative measurements with distinct call counts")
    nx, ty = zip(*samples)
    xm, ym = statistics.mean(nx), statistics.mean(ty)
    xx = sum((n - xm) ** 2 for n in nx)
    if not xx:
        raise ValueError("call counts must vary")
    slope = sum((n - xm) * (t - ym) for n, t in samples) / xx
    intercept = ym - slope * xm
    residual = sum((t - intercept - slope * n) ** 2 for n, t in samples)
    total = sum((t - ym) ** 2 for t in ty)
    return {"intercept_seconds": intercept, "nanoseconds_per_call": slope * 1e9,
            "r_squared": 1 - residual / total if total else 1.0}


def build_case(root: Path, out: Path, calls: int, rounds: int) -> dict[str, Path]:
    if not 0 <= calls <= 2 ** 26 or not 0 <= rounds <= 4096:
        raise ValueError("calls must be 0..2^26, rounds 0..4096")
    source_dir = root / "examples/ffi"
    work = out / f"calls-{calls}-rounds-{rounds}"
    work.mkdir(parents=True, exist_ok=True)
    common = (source_dir / "common.bend").read_text()
    for name, value in (("calls", calls), ("rounds", rounds)):
        common, count = re.subn(rf"(?m)^(def {name}\(\) -> Nat:\n)  \d+n$", rf"\g<1>  {value}n", common)
        if count != 1:
            raise ValueError(f"missing or duplicate {name} knob")
    (work / "common.bend").write_text(common)
    (work / "effect.c").write_text((source_dir / "effect.c").read_text())
    flags = [os.environ.get("CC", "clang"), "-std=c11", "-O3", "-pthread", "-I", str(source_dir)]
    binaries = {}
    for kind, stem in KINDS.items():
        (work / f"{stem}.bend").write_text((source_dir / f"{stem}.bend").read_text())
        generated = work / f"{stem}.c"
        binary = work / stem
        subprocess.run([str(root / "scripts/bend.sh"), str(work / f"{stem}.bend"), "-o", str(generated)],
                       env={**os.environ, "BEND_NO_TELEMETRY": "1"}, stdout=subprocess.DEVNULL, check=True)
        # Same kernel.c is separately compiled for C and the foreign caller;
        # without LTO, callers cannot fold, inline or remove its calls.
        subprocess.run([*flags, str(generated), str(source_dir / "kernel.c"), "-lm", "-o", str(binary)], check=True)
        binaries[kind] = binary
    c = work / "direct"
    subprocess.run([*flags, f"-DCALLS={calls}", f"-DROUNDS={rounds}", str(source_dir / "direct.c"),
                    str(source_dir / "kernel.c"), "-o", str(c)], check=True)
    return {"c-direct": c, **binaries}


def measure(binary: Path, threads: int, kind: str) -> tuple[int, dict]:
    extra = [] if kind == "c-direct" else ["--threads", str(threads), "--gpu", "off"]
    output = parse_result(command_output(str(binary), *extra))
    timing = json.loads(command_output("python3", str(ROOT / "scripts/benchmark.py"), "--json", str(binary), *extra))
    return output, timing


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calls", type=int, nargs="+", default=[0, 1048576, 4194304, 16777216])
    parser.add_argument("--rounds", type=int, nargs="+", default=[0, 1])
    parser.add_argument("--batch", action="store_true", help="also measure rounds=16/256/4096 with 2^26 total rounds")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if any(not 0 <= n <= 2 ** 26 for n in args.calls) or any(not 0 <= n <= 4096 for n in args.rounds):
        parser.error("calls must be 0..2^26, rounds 0..4096")
    os.environ["BEND_NO_TELEMETRY"] = "1"
    metadata = environment_metadata()
    metadata.update(c_flags="-std=c11 -O3 -pthread; separate kernel.c, no LTO, noinline kernel",
                    method="serial best-of-3 wall clock; median regression on nonzero call counts; startup included then removed by slope",
                    payload="U32 input state + U32 rounds -> U32 result; no buffers or per-call output; synchronous host FFI",
                    kernel="sequential xorshift32; next call depends on previous result; seed=0x12345678")
    metadata["source_sha256"].update({str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in [*sorted(SOURCE.iterdir()), Path(__file__)] if p.is_file() and p.suffix in (".bend", ".c", ".h", ".py")})
    record = {"environment": metadata, "cases": [], "fits": {}, "overhead": {}}
    cases = [(n, r, "slope") for r in args.rounds for n in args.calls]
    if args.batch:
        cases.extend((2 ** 26 // r, r, "batch") for r in (16, 256, 4096))
    print("calls rounds group C-direct pure-1 IO-pure-1 FFI-1 pure-all IO-pure-all FFI-all", flush=True)
    for calls, rounds, group in cases:
        binaries = build_case(ROOT, ROOT / "build/ffi", calls, rounds)
        timings, expected = {}, None
        modes = [("c-direct", "c-direct", 1)] + [(f"{kind}-{label}", kind, threads)
                 for label, threads in (("1", 1), ("all", metadata["threads"])) for kind in KINDS]
        for label, kind, threads in modes:
            output, timing = measure(binaries[kind], threads, kind)
            if expected is not None and output != expected:
                raise RuntimeError(f"calls={calls} rounds={rounds} {label}: checksum mismatch")
            expected = output
            timings[label] = timing
        record["cases"].append({"calls": calls, "rounds": rounds, "group": group, "checksum": expected, "timings": timings})
        print(calls, rounds, group, *(f'{timings[label]["median_seconds"]:.6f}' for label, _, _ in modes), flush=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    for rounds in args.rounds:
        values = [c for c in record["cases"] if c["group"] == "slope" and c["rounds"] == rounds and c["calls"] > 0]
        if len({c["calls"] for c in values}) < 2:
            continue
        fits = {mode: fit_cost([(c["calls"], c["timings"][mode]["median_seconds"]) for c in values])
                for mode in values[0]["timings"]}
        record["fits"][str(rounds)] = fits
        overhead = {}
        for label in ("1", "all"):
            slope = fits[f"bend-ffi-{label}"]["nanoseconds_per_call"]
            overhead[label] = {"ffi_minus_c_direct_ns": slope - fits["c-direct"]["nanoseconds_per_call"],
                               "ffi_minus_bend_pure_ns": slope - fits[f"bend-pure-{label}"]["nanoseconds_per_call"],
                               "ffi_minus_bend_io_pure_ns": slope - fits[f"bend-io-pure-{label}"]["nanoseconds_per_call"]}
        record["overhead"][str(rounds)] = overhead
        print("rounds", rounds, "fits(ns/call)", json.dumps(fits), "overhead(ns/call)", json.dumps(overhead), flush=True)
    if "thermal_before" in metadata:
        metadata["thermal_after"] = command_output("pmset", "-g", "therm")
    if args.output:
        args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
