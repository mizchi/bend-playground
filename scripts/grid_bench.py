"""Serial Grid timings: dependent page relayouts versus independent page batches."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from algorithm_bench import command_output, environment_metadata
from ffi_bench import fit_cost
from grid import ROOT, build_cases, normalize
from grid_cases import cards, dashboard, nested


def parse_stats(text):
    match = re.fullmatch(r"checksum=(\d+) nodes=(\d+) errors=(\d+)\n?", text)
    if not match or any(int(x) >= 2 ** 32 for x in match.groups()):
        raise ValueError("invalid Grid statistics")
    return dict(zip(("checksum", "nodes", "errors"), map(int, match.groups())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "examples/grid/results/macos-m5-grid.json")
    parser.add_argument("--workload", choices=("dashboard", "catalog", "nested"), action="append")
    args = parser.parse_args()
    pages = {"dashboard": dashboard(), "catalog": cards(), "nested": nested(4)}
    names = args.workload or list(pages)
    threads = min(os.cpu_count() or 1, 128)
    work = ROOT / "build/grid/bench"
    specifications = []
    for name in names:
        for repetitions in [1, 2048, 16384]:
            specifications.append((name, "latency", 0, repetitions))
        for depth in [13, 16]:
            specifications.append((name, "batch", depth, 1))
    built = []
    for name, mode, depth, repetitions in specifications:
        out = work / f"{name}-{mode}-{depth}-{repetitions}"
        binaries = build_cases(ROOT, out, [pages[name]], (depth, repetitions))
        built.append((name, mode, depth, repetitions, binaries, out))
        print(f"built {name}/{mode}/{(1 << depth) * repetitions}", flush=True)
    meta = environment_metadata()
    source_paths = [*sorted((ROOT / "examples/grid").glob("*.bend")),
                    ROOT / "examples/grid/grid.h", ROOT / "examples/grid/grid.c",
                    ROOT / "scripts/grid.py", ROOT / "scripts/grid_cases.py", ROOT / "scripts/grid_bench.py"]
    meta.update(method="serial median-of-3 wall clock; compilation and output rectangles excluded; CPU only",
                source_state="local Grid implementation on recorded playground commit",
                c_scheduler="pthread dynamic page queue, chunk 16; sequential layout within each page",
                bend_scheduler="fork across sibling subtrees and independent pages; immutable input tree shared",
                measurement_scope="normalize/build excluded; placement, track sizing, recursive boxes, allocation, output checksum included",
                source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
                generated_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for *_, out in built for p in (out / "run.bend", out / "run.c")})
    records = []
    for name, mode, depth, repetitions, binaries, out in built:
        layouts = (1 << depth) * repetitions
        modes = [("c", 1), ("bend", 1), ("bend", threads)] if mode == "latency" else [("c", 1), ("c", threads), ("bend", 1), ("bend", threads)]
        results, expected = {}, None
        for backend, count in modes:
            command = [str(binaries[backend]), "--threads", str(count)] + (["--gpu", "off"] if backend == "bend" else [])
            answer = parse_stats(subprocess.check_output(command, text=True))
            if answer["errors"] or answer["nodes"] != layouts * len(normalize(pages[name])["names"]):
                raise RuntimeError("benchmark did not lay out every node")
            if expected is not None and expected != answer:
                raise RuntimeError(f"C/Bend checksum mismatch: {name}, {mode}, {count}")
            expected = answer
            measured = json.loads(subprocess.check_output([sys.executable, str(ROOT / "scripts/benchmark.py"), "--json", *command], text=True))
            results[f"{backend}-{count}"] = measured
            print(f'{name}/{mode}/{layouts} {backend}-{count}: {measured["median_seconds"]:.6f}s', flush=True)
        records.append({"workload": name, "mode": mode, "nodes_per_page": len(normalize(pages[name])["names"]),
                        "batch_depth": depth, "repetitions": repetitions, "layouts": layouts, "result": expected, "timings": results})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"environment": meta, "cases": records}, indent=2) + "\n")
    fits = {}
    for name in names:
        samples = [r for r in records if r["workload"] == name and r["mode"] == "latency"]
        fits[name] = {key: fit_cost([(r["layouts"], r["timings"][key]["median_seconds"]) for r in samples])
                      for key in samples[0]["timings"]}
    meta["thermal_after"] = command_output("pmset", "-g", "therm") if meta["platform"].startswith("Darwin") else "not available"
    args.output.write_text(json.dumps({"environment": meta, "cases": records, "latency_fits_ns_per_layout": fits}, indent=2) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
