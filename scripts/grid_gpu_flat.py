"""Profile Bend Grid output written directly into one shared packed F32 buffer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess

from algorithm_bench import environment_metadata, command_output
from grid import ROOT, normalize, bend_node, bend_float, integer
from grid_cases import dashboard, cards, nested
import grid_gpu

FIELDS = grid_gpu.FIELDS | {"buffer_bytes", "stride", "prepare_ns", "view_ns", "read_ns",
                          "read_again_ns", "copy_ns", "copy_read_ns", "read_checksum",
                          "read_again_checksum", "copy_checksum"}


def buffer_shape(nodes, depth):
    integer(nodes, "nodes", 1, 2048)
    integer(depth, "batch depth", 0, 16)
    page_depth = (nodes * 4 - 1).bit_length()
    return 1 << page_depth, page_depth + depth


def parse_profile(text, gpu=False):
    value = json.loads(text)
    if set(value) != FIELDS or any(type(x) is not int or x < 0 for x in value.values()):
        raise ValueError("invalid flat profile fields")
    grid_gpu.parse_profile(json.dumps({k: value[k] for k in grid_gpu.FIELDS}), gpu)
    nodes = value["nodes"] // value["pages"]
    stride = buffer_shape(nodes, 0)[0]
    if value["stride"] != stride or value["buffer_bytes"] != 4 * stride * value["pages"]:
        raise ValueError("invalid flat buffer shape")
    if any(value[k] != value["checksum"] for k in ["read_checksum", "read_again_checksum", "copy_checksum"]):
        raise ValueError("direct/copy output mismatch")
    return value


def build_case(root, work, page, depth, samples=5, warmups=2):
    integer(samples, "samples", 1, 100)
    integer(warmups, "warmups", 0, 100)
    case = normalize(page)
    stride, capacity_depth = buffer_shape(len(case["names"]), depth)
    pages, nodes = 1 << depth, len(case["names"])
    work.mkdir(parents=True, exist_ok=True)
    source = root / "examples/grid"
    for name in ["contract.bend", "placement.bend", "tracks.bend", "layout.bend",
                 "gpu-flat.bend", "gpu-flat-probe.bend", "gpu-flat-probe.c", "gpu-profile.h"]:
        (work / name).write_bytes((source / name).read_bytes())
    (work / "run.bend").write_text(f'''import Base
import ./contract.bend as G
import ./gpu-flat.bend as B
import ./gpu-flat-probe.bend as P

def page() -> G.Node:
  {bend_node(case)}

def repeat(f: Nat, +node: G.Node, +round: U32) -> IO(Unit):
  match f:
    case 0n: IO.pure(Unit, Unit{{}})
    case 1n+p:
      IO.bind(Array<F32>, Unit, P.start({pages}, {nodes}, round, {capacity_depth}, {stride}), buffer =>
        IO.bind(Unit, Unit, P.consume(B.batch!({depth}n, node,
          {bend_float(case['width'])}, {bend_float(case['height'])}, 0, U32.mul(round, {pages}),
          {stride}, buffer)), u => repeat(p, node, U32.inc(round))))

def main() -> IO(Unit):
  repeat({samples + warmups}n, page(), 0)
''')
    generated = work / "bend.c"
    subprocess.run([str(root / "scripts/bend.sh"), str(work / "run.bend"), "-o", str(generated)],
                   env={**os.environ, "BEND_NO_TELEMETRY": "1"}, stdout=subprocess.DEVNULL, check=True)
    generated.write_text(grid_gpu.instrument_metal(generated.read_text()))
    binary = work / "grid_gpu_flat"
    flags = [os.environ.get("CC", "clang"), "-std=c11", "-O3", "-ffp-contract=off", "-pthread"]
    if os.uname().sysname == "Darwin":
        flags += ["-x", "objective-c", "-fobjc-arc", "-fmodules", "-DBEND_METAL=1"]
    subprocess.run([*flags, str(generated), "-lm", "-o", str(binary)], check=True)
    if os.uname().sysname == "Darwin":
        subprocess.run([str(binary), "--gpu-build"], check=True)
    return binary


def run_case(binary, threads, gpu=False, dump=None, timeout=300):
    env = {**os.environ, "BEND_NO_TELEMETRY": "1"}
    if dump is not None:
        env["GRID_GPU_DUMP"] = str(dump)
    result = subprocess.run([str(binary), "--threads", str(threads), "--gpu", "on" if gpu else "off"],
                            env=env, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise grid_gpu.ProfileFailure(result)
    return [parse_profile(line, gpu) for line in result.stdout.splitlines()]


def medians(rows):
    answer = {key: statistics.median(r[key] for r in rows) for key in rows[0] if key.endswith("_ns")}
    answer["layout_and_direct_read_ns"] = statistics.median(
        r["layout_ns"] + r["view_ns"] + r["read_ns"] for r in rows)
    answer["direct_end_to_end_ns"] = statistics.median(
        r["layout_ns"] + r["view_ns"] + r["read_ns"] + r["drop_ns"] for r in rows)
    answer["direct_with_prepare_ns"] = statistics.median(
        r["prepare_ns"] + r["layout_ns"] + r["view_ns"] + r["read_ns"] + r["drop_ns"] for r in rows)
    return answer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", choices=("dashboard", "catalog", "nested"), action="append")
    parser.add_argument("--depth", type=int, action="append")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--output", type=Path, default=ROOT / "examples/grid/results/macos-m5-grid-gpu-flat.json")
    args = parser.parse_args()
    workloads = {"dashboard": dashboard(), "catalog": cards(), "nested": nested(4)}
    built = []
    for name in args.workload or workloads:
        for depth in args.depth or [0, 9, 12]:
            work = ROOT / "build/grid/gpu-flat" / f"{name}-{depth}"
            flat = build_case(ROOT, work / "flat", workloads[name], depth, args.samples, args.warmups)
            tree = grid_gpu.build_case(ROOT, work / "tree", workloads[name], depth, args.samples, args.warmups)
            built.append((name, depth, work, flat, tree))
            print(f"built {name}/{1 << depth} pages", flush=True)
    meta = environment_metadata()
    sources = [*sorted((ROOT / "examples/grid").glob("*.bend")),
               *sorted((ROOT / "examples/grid").glob("*.c")), *sorted((ROOT / "examples/grid").glob("*.h")),
               ROOT / "scripts/grid.py", ROOT / "scripts/grid_gpu.py", Path(__file__)]
    generated = [p for _, _, work, _, _ in built for branch in ["tree", "flat"]
                 for p in [work / branch / "run.bend", work / branch / "bend.c", work / branch / "run.c"] if p.exists()]
    if os.uname().sysname == "Darwin":
        displays = json.loads(command_output("system_profiler", "SPDisplaysDataType", "-json"))
        meta["gpu"] = [{"model": d.get("sppci_model"), "cores": d.get("sppci_cores"),
                        "metal": d.get("spdisplays_mtlgpufamilysupport")}
                       for d in displays["SPDisplaysDataType"]]
    meta.update(samples=args.samples, warmups=args.warmups,
                c_scheduler="persistent pthread workers; dynamic atomic queue; chunks 16",
                method="serial within-process stage timings; warmups discarded, same-sample sum medians",
                source_state="local direct shared-buffer Grid GPU experiment",
                measurement_scope="Bend writes x/y/width/height to packed F32 buffer; allocation/NaN initialization before dispatch measured as prepare; first CPU full read validates and checksums; memcpy destination pre-touched; subsequent reads are warm",
                buffer_contract="four F32 coordinates per node; page/node ids implicit; each page padded to power-of-two floats; disjoint writes via unsafe Array sharing; no output Tree",
                readback="Metal shared storage; no explicit device-to-host copy; view borrows pointer, read traverses all active coordinates, copy is optional CPU memcpy including padding; GPU execution/wait overlap",
                bend_flags="-std=c11 -O3 -ffp-contract=off -pthread -x objective-c -fobjc-arc -fmodules -DBEND_METAL=1 -lm",
                source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                generated_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in generated})
    record = {"environment": meta, "cases": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for name, depth, work, flat, tree in built:
        timings, reference = {}, None
        nodes = len(normalize(workloads[name])["names"])
        stride, _ = buffer_shape(nodes, depth)
        record["cases"].append({"workload": name, "depth": depth, "pages": 1 << depth,
                                "nodes_per_page": nodes, "stride": stride,
                                "active_coordinate_bytes": (1 << depth) * nodes * 16,
                                "buffer_bytes": (1 << depth) * stride * 4, "timings": timings})
        modes = [("c-1", "c", 1, False, False), ("c-all", "c", meta["threads"], False, False),
                 ("tree-cpu", "bend", meta["threads"], False, False), ("tree-gpu", "bend", meta["threads"], True, False),
                 ("flat-cpu", "bend", meta["threads"], False, True), ("flat-gpu", "bend", meta["threads"], True, True)]
        for label, backend, threads, gpu, direct in modes:
            try:
                rows = run_case(flat, threads, gpu) if direct else grid_gpu.run_case(tree[backend], backend, threads, gpu)
            except (RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
                if not gpu:
                    raise
                timings[label] = {"status": "failed", "error": str(error)}
                if isinstance(error, grid_gpu.ProfileFailure):
                    timings[label].update(returncode=error.returncode, stderr=error.stderr, partial_stdout=error.stdout)
                args.output.write_text(json.dumps(record, indent=2) + "\n")
                print(f"{name}/{1 << depth} {label}: FAILED: {error}", flush=True)
                continue
            if len(rows) != args.samples + args.warmups or [r["round"] for r in rows] != list(range(len(rows))):
                raise RuntimeError("incomplete sample sequence")
            answers = [(r["pages"], r["nodes"], r["checksum"]) for r in rows]
            if reference is not None and answers != reference:
                raise RuntimeError("tree/flat/C output mismatch")
            reference = answers
            measured = rows[args.warmups:]
            if direct:
                median = medians(measured)
            else:
                median = {k: statistics.median(r[k] for r in measured) for k in grid_gpu.FIELDS if k.endswith("_ns")}
                median["layout_and_materialize_ns"] = statistics.median(r["layout_ns"] + r["materialize_ns"] for r in measured)
                median["end_to_end_ns"] = statistics.median(sum(r[k] for k in ["layout_ns", "materialize_ns", "checksum_ns", "drop_ns"]) for r in measured)
            timings[label] = {"status": "ok", "samples": rows, "median": median}
            detail = f'direct read {median["read_ns"] / 1e6:.3f}ms; copy {median["copy_ns"] / 1e6:.3f}ms' if direct else f'materialize {median["materialize_ns"] / 1e6:.3f}ms'
            print(f'{name}/{1 << depth} {label}: layout {median["layout_ns"] / 1e6:.3f}ms; {detail}', flush=True)
            args.output.write_text(json.dumps(record, indent=2) + "\n")
    meta["thermal_after"] = command_output("pmset", "-g", "therm")
    args.output.write_text(json.dumps(record, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
