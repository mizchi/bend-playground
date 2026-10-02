"""Create a standalone comparison viewer from native Bend rectangles."""
import json
from grid import ROOT, build_cases, run_cases
from grid_cases import browser_cases


def main():
    pages = browser_cases()[:12]
    binaries = build_cases(ROOT, ROOT / "build/grid/demo", pages)
    answers = run_cases(binaries["bend"], "bend", pages)
    if any(a["errors"] for a in answers):
        raise RuntimeError("invalid demo layout")
    data = json.dumps([{"input": p, "bend": a} for p, a in zip(pages, answers)], ensure_ascii=False).replace("<", "\\u003c")
    out = ROOT / "build/grid/demo.html"
    out.write_text((ROOT / "examples/grid/demo.html").read_text().replace("__GRID_CASES__", data))
    print(out)


if __name__ == "__main__":
    main()
