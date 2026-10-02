"""Serial best-of-three wall clock, optionally with peak child RSS in MiB."""
import argparse
import resource
import subprocess
import sys
import time


def max_rss_mib(raw: int, platform: str) -> float:
    # Darwin reports bytes; Linux reports KiB.
    return raw / (1024 ** 2 if platform == "darwin" else 1024)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rss", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.command:
        parser.error("a command is required")

    best = float("inf")
    for _ in range(3):
        start = time.perf_counter()
        subprocess.run(args.command, stdout=subprocess.DEVNULL, check=True)
        best = min(best, time.perf_counter() - start)

    output = f"{best:.3f}s"
    if args.rss:
        rss = max_rss_mib(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss, sys.platform)
        output += f" {rss:.0f}MB"
    print(output)


if __name__ == "__main__":
    main()
