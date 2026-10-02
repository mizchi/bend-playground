"""Serial fixed-size frame preparation timings; excludes GPUI presentation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics

import gpui
from algorithm_bench import command_output
from grid import integer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=7)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--output", type=Path, default=gpui.SOURCE / "results-macos-m5.json")
    args = parser.parse_args()
    integer(args.frames, "frames", 1, 10000)
    integer(args.warmups, "warmups", 0, args.frames - 1)
    # Finish all builds before starting serial timing runs.
    binaries = {mode: gpui.build(mode) for mode in ["grid", "shader"]}
    record = {"method": "fixed 960x540 offscreen CVPixelBuffer preparation; serial within-process timings; no pixel verification in timed samples; GPUI draw/present/display latency excluded",
              "warmups": args.warmups, "frames": args.frames, "cases": []}
    for mode, binary in binaries.items():
        for gpu in [False, True]:
            rows = gpui.run(binary, gpu=gpu, frames=args.frames, headless=True)
            measured = rows[args.warmups:]
            median = {key: statistics.median(r[key] for r in measured)
                      for key in rows[0] if key.endswith('_ns')}
            case = {**gpui.metadata(binary), "mode": mode, "bend_backend": "metal" if gpu else f"cpu-{min(os.cpu_count() or 1, 128)}",
                    "samples": rows, "median": median}
            record['cases'].append(case)
            print(f'{mode}/{case["bend_backend"]}: Bend {median["bend_ns"]/1e6:.3f}ms; handoff {median["handoff_ns"]/1e6:.3f}ms; ready {median["frame_ready_ns"]/1e6:.3f}ms', flush=True)
    record['benchmark_source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    record['thermal_after'] = command_output('pmset', '-g', 'therm')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2) + '\n')
    print(args.output)


if __name__ == "__main__":
    main()
