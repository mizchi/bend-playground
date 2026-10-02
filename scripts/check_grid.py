"""Build native Grid engines and prepare the independent Playwright oracle."""
import json
from pathlib import Path
import sys

from grid import ROOT, build_cases, run_cases
from grid_cases import browser_cases


def main():
    pages = browser_cases()
    checks = []
    # Keep generated modules small, without changing the engine or the cases.
    for offset in range(0, len(pages), 24):
        group = pages[offset:offset + 24]
        binaries = build_cases(ROOT, ROOT / f"build/grid/check-{offset}", group)
        c = run_cases(binaries["c"], "c", group)
        for threads in [1, min(10, __import__("os").cpu_count() or 1)]:
            bend = run_cases(binaries["bend"], "bend", group, threads)
            for i, (a, b) in enumerate(zip(c, bend)):
                if a["errors"] or b["errors"] or set(a["boxes"]) != set(b["boxes"]):
                    raise RuntimeError(f"layout failure in case {offset + i}")
                for name in a["boxes"]:
                    if max(abs(x - y) for x, y in zip(a["boxes"][name], b["boxes"][name])) > .002:
                        raise RuntimeError(f"C/Bend mismatch in case {offset + i}, {name}")
        checks.extend({"input": page, "bend": answer, "c": twin} for page, answer, twin in zip(group, bend, c))
        print(f"C/Bend verified: {len(checks)}/{len(pages)}", flush=True)
    out = ROOT / "build/grid/checks.json"
    out.write_text(json.dumps(checks, indent=2) + "\n")
    for browser in ("chromium", "firefox"):
        (ROOT / f"build/grid/{browser}-results.json").unlink(missing_ok=True)
    print(f"browser oracle input: {out}")


if __name__ == "__main__":
    main()
