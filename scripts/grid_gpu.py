"""Build full-output independent Grid batches and profile native Metal handoffs."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import struct
import subprocess

from algorithm_bench import environment_metadata, command_output
from bend_gpui import instrument_metal
from grid import ROOT, normalize, bend_node, bend_float, c_input, integer
from grid_cases import dashboard, cards, nested

FIELDS = {"round", "pages", "nodes", "errors", "checksum", "bytes", "layout_ns",
          "materialize_ns", "checksum_ns", "drop_ns", "gpu_commands",
          "gpu_execution_ns", "gpu_wait_ns", "gpu_submit_ns"}


class ProfileFailure(RuntimeError):
    def __init__(self, result):
        self.returncode = result.returncode
        self.stderr = result.stderr
        self.stdout = result.stdout
        super().__init__(f"Grid profile failed ({result.returncode}): {result.stderr.strip()}")


def parse_profile(text, gpu=False):
    value = json.loads(text)
    if set(value) != FIELDS or any(type(x) is not int or x < 0 for x in value.values()):
        raise ValueError("invalid Grid profile fields")
    if not value["pages"] or not value["nodes"] or value["errors"] or value["checksum"] >= 2 ** 32:
        raise ValueError("incomplete/failed Grid result")
    if value["bytes"] != value["nodes"] * 24 or value["nodes"] % value["pages"]:
        raise ValueError("invalid rectangle payload size")
    if gpu and (not value["gpu_commands"] or not value["gpu_execution_ns"]):
        raise ValueError("GPU measurement fell back to CPU")
    if not gpu and any(value[k] for k in ("gpu_commands", "gpu_execution_ns", "gpu_wait_ns", "gpu_submit_ns")):
        raise ValueError("CPU measurement unexpectedly used the GPU")
    if value["gpu_wait_ns"] > value["layout_ns"]:
        raise ValueError("GPU wait cannot exceed its containing layout phase")
    return value


def build_case(root, work, page, depth, samples=5, warmups=2, page_parallel=False):
    integer(depth, "batch depth", 0, 16)
    integer(samples, "samples", 1, 100)
    integer(warmups, "warmups", 0, 100)
    case = normalize(page)
    work.mkdir(parents=True, exist_ok=True)
    source = root / "examples/grid"
    for name in ["contract.bend", "placement.bend", "tracks.bend", "layout.bend",
                 "serial-layout.bend", "gpu.bend", "gpu-probe.bend", "gpu-probe.c", "gpu-profile.h"]:
        text = (source / name).read_text()
        if name == "gpu.bend" and page_parallel:
            text = text.replace("import ./serial-layout.bend as S", "import ./layout.bend as S")
        (work / name).write_text(text)
    pages, nodes = 1 << depth, len(case["names"])
    (work / "run.bend").write_text(f'''import Base
import ./contract.bend as G
import ./gpu.bend as B
import ./gpu-probe.bend as P

def page() -> G.Node:
  {bend_node(case)}

def repeat(f: Nat, +node: G.Node, +round: U32) -> IO(Unit):
  match f:
    case 0n: IO.pure(Unit, Unit{{}})
    case 1n+p:
      IO.bind(Unit, Unit, P.start({pages}, {nodes}, round), u =>
        IO.bind(Unit, Unit, P.consume(B.batch!({depth}n, node,
          {bend_float(case['width'])}, {bend_float(case['height'])}, 0, U32.mul(round, {pages}))), v =>
          repeat(p, node, U32.inc(round))))

def main() -> IO(Unit):
  repeat({samples + warmups}n, page(), 0)
''')
    generated = work / "bend.c"
    subprocess.run([str(root / "scripts/bend.sh"), str(work / "run.bend"), "-o", str(generated)],
                   env={**os.environ, "BEND_NO_TELEMETRY": "1"}, stdout=subprocess.DEVNULL, check=True)
    generated.write_text(instrument_metal(generated.read_text()))
    cc = os.environ.get("CC", "clang")
    bend = work / "grid_gpu"
    flags = [cc, "-std=c11", "-O3", "-ffp-contract=off", "-pthread"]
    if os.uname().sysname == "Darwin":
        flags += ["-x", "objective-c", "-fobjc-arc", "-fmodules", "-DBEND_METAL=1"]
    subprocess.run([*flags, str(generated), "-lm", "-o", str(bend)], check=True)
    if os.uname().sysname == "Darwin":
        subprocess.run([str(bend), "--gpu-build"], check=True)
    (work / "run.c").write_text('#include "grid.h"\n' + c_input([case]) + '\n#include "gpu-control.c"\n' +
        f'int main(int argc, char **argv) {{ return grid_control(argc, argv, pages[0], widths[0], heights[0], {pages}, {nodes}, {samples + warmups}); }}\n')
    c = work / "grid_c"
    subprocess.run([cc, "-std=c11", "-O3", "-ffp-contract=off", "-pthread", "-I", str(source),
                    str(work / "run.c"), str(source / "grid.c"), "-lm", "-o", str(c)], check=True)
    return {"bend": bend, "c": c}


def run_case(binary, backend, threads, gpu=False, dump=None, timeout=300):
    if gpu and backend != "bend":
        raise ValueError("GPU requires the Bend backend")
    flags = ["--threads", str(threads)]
    if backend == "bend":
        flags += ["--gpu", "on" if gpu else "off"]
    env = {**os.environ, "BEND_NO_TELEMETRY": "1"}
    if dump is not None:
        env["GRID_GPU_DUMP"] = str(dump)
    run = subprocess.run([str(binary), *flags], env=env, text=True, capture_output=True, timeout=timeout)
    if run.returncode:
        raise ProfileFailure(run)
    return [parse_profile(line, gpu) for line in run.stdout.splitlines()]


def read_rectangles(path):
    content = path.read_bytes()
    if len(content) % 24:
        raise ValueError("truncated rectangle output")
    answer = {}
    for page, node, *rect in struct.iter_unpack("=IIffff", content):
        key = (page, node)
        if key in answer or not all(math.isfinite(x) for x in rect):
            raise ValueError("invalid/duplicate rectangle")
        answer[key] = rect
    return answer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", choices=("dashboard", "catalog", "nested"), action="append")
    parser.add_argument("--depth", type=int, action="append")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--page-parallel", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "examples/grid/results/macos-m5-grid-gpu.json")
    args = parser.parse_args()
    workloads = {"dashboard": dashboard(), "catalog": cards(), "nested": nested(4)}
    specifications = [(name, depth) for name in args.workload or workloads for depth in args.depth or [0, 6, 9, 12, 14]]
    built = []
    for name, depth in specifications:
        work = ROOT / "build/grid/gpu" / f"{name}-{depth}-{'forked' if args.page_parallel else 'serial'}"
        binaries = build_case(ROOT, work, workloads[name], depth, args.samples, args.warmups, args.page_parallel)
        built.append((name, depth, work, binaries))
        print(f"built {name}/{1 << depth} pages", flush=True)
    meta = environment_metadata()
    sources = [*sorted((ROOT / "examples/grid").glob("*.bend")),
               *sorted((ROOT / "examples/grid").glob("*.c")), *sorted((ROOT / "examples/grid").glob("*.h")),
               ROOT / "scripts/grid.py", Path(__file__)]
    meta.update(method="serial within-process stage timings; two warmups then median-of-five by default; full result retained",
                measurement_scope="input construction, compilation and GPU setup excluded; layout returns all rectangles; host materialization, checksum and drop reported separately",
                source_state="local full-output Grid GPU experiment",
                page_parallel=args.page_parallel, samples=args.samples, warmups=args.warmups,
                readback="Metal shared heap: no explicit device-to-host copy; synchronous GPU wait and CPU materialization measured separately; wait overlaps GPU execution",
                source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                generated_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for _, _, work, _ in built for p in [work / "run.bend", work / "bend.c", work / "run.c"]})
    record = {"environment": meta, "cases": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for name, depth, work, binaries in built:
        timings, reference = {}, None
        case_record = {"workload": name, "depth": depth, "pages": 1 << depth,
                       "nodes_per_page": len(normalize(workloads[name])["names"]), "timings": timings}
        record["cases"].append(case_record)
        for backend, threads, gpu in [("c", 1, False), ("c", meta["threads"], False),
                                      ("bend", 1, False), ("bend", meta["threads"], False),
                                      ("bend", meta["threads"], True)]:
            label = "bend-gpu" if gpu else f"{backend}-{threads}"
            try:
                rows = run_case(binaries[backend], backend, threads, gpu)
            except (RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
                if not gpu:
                    raise
                timings[label] = {"status": "failed", "error": str(error)}
                if isinstance(error, ProfileFailure):
                    timings[label].update(returncode=error.returncode, stderr=error.stderr,
                                          partial_stdout=error.stdout)
                args.output.write_text(json.dumps(record, indent=2) + "\n")
                print(f"{name}/{1 << depth} {label}: FAILED: {error}", flush=True)
                continue
            if len(rows) != args.samples + args.warmups:
                raise RuntimeError("incomplete sample sequence")
            answers = [(r["round"], r["pages"], r["nodes"], r["checksum"]) for r in rows]
            if reference is not None and answers != reference:
                raise RuntimeError("CPU/GPU batch output mismatch")
            reference = answers
            samples = rows[args.warmups:]
            median = {key: statistics.median(r[key] for r in samples) for key in FIELDS if key.endswith("_ns")}
            median["layout_and_materialize_ns"] = statistics.median(r["layout_ns"] + r["materialize_ns"] for r in samples)
            median["end_to_end_ns"] = statistics.median(sum(r[k] for k in ["layout_ns", "materialize_ns", "checksum_ns", "drop_ns"]) for r in samples)
            timings[label] = {"status": "ok", "samples": rows, "median": median}
            print(f'{name}/{1 << depth} {label}: layout {median["layout_ns"] / 1e6:.3f}ms; materialize {median["materialize_ns"] / 1e6:.3f}ms', flush=True)
            args.output.write_text(json.dumps(record, indent=2) + "\n")
    meta["thermal_after"] = command_output("pmset", "-g", "therm")
    args.output.write_text(json.dumps(record, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
