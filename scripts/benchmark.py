"""Serial best-of-three wall clock, optionally with peak child RSS in MiB."""
import argparse
import json
import resource
import statistics
import subprocess
import sys
import time


def max_rss_mib(raw: int, platform: str) -> float:
    # Darwin reports bytes; Linux reports KiB.
    return raw / (1024 ** 2 if platform == "darwin" else 1024)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rss", action="store_true")
    parser.add_argument("--json", action="store_true", help="include individual samples, median and peak RSS")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.command:
        parser.error("a command is required")

    samples = []
    for _ in range(3):
        start = time.perf_counter()
        subprocess.run(args.command, stdout=subprocess.DEVNULL, check=True)
        samples.append(time.perf_counter() - start)

    best = min(samples)
    rss = max_rss_mib(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss, sys.platform)
    if args.json:
        print(json.dumps({"best_seconds": best, "median_seconds": statistics.median(samples),
                          "samples_seconds": samples, "peak_rss_mib": rss}))
        return
    output = f"{best:.3f}s"
    if args.rss:
        output += f" {rss:.0f}MB"
    print(output)


if __name__ == "__main__":
    main()
