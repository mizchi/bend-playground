"""Check C/FFI timing order using binaries from an existing FFI measurement."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

from ffi_bench import ROOT, command_output, measure


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    args = parser.parse_args()
    record = json.loads(args.record.read_text())
    for name, digest in record["environment"]["source_sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"measurement source changed: {name}")
    selected = []
    for rounds in (0, 1, 256, 4096):
        cases = [c for c in record["cases"] if c["rounds"] == rounds]
        if cases:
            selected.append(max(cases, key=lambda c: c["calls"]))
    confirmation = {"method": "serial C->FFI, FFI->C, C->FFI; each entry measures 3 runs; threads=1",
                    "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "cases": []}
    for case in selected:
        work = ROOT / f'build/ffi/calls-{case["calls"]}-rounds-{case["rounds"]}'
        runs = []
        for order in (("c-direct", "bend-ffi"), ("bend-ffi", "c-direct"), ("c-direct", "bend-ffi")):
            pair = {"order": list(order), "timings": {}}
            for kind in order:
                binary = work / ("direct" if kind == "c-direct" else "foreign")
                output, timing = measure(binary, 1, kind)
                if output != case["checksum"]:
                    raise RuntimeError("confirmation checksum mismatch")
                pair["timings"][kind] = timing
            runs.append(pair)
        medians = {kind: statistics.median(pair["timings"][kind]["median_seconds"] for pair in runs)
                   for kind in ("c-direct", "bend-ffi")}
        confirmation["cases"].append({"calls": case["calls"], "rounds": case["rounds"], "pairs": runs,
                                       "median_of_medians_seconds": medians,
                                       "raw_difference_ns_per_call": (medians["bend-ffi"] - medians["c-direct"]) / case["calls"] * 1e9})
        print(case["calls"], case["rounds"], medians, flush=True)
    confirmation["thermal_after"] = command_output("pmset", "-g", "therm") if record["environment"]["platform"].startswith("Darwin") else None
    record["order_confirmation"] = confirmation
    args.record.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
