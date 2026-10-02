"""Normalize a CSS Grid subset, compile either native engine, and emit rectangles."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MAX_COLUMNS, MAX_ROWS, MAX_CHILDREN, MAX_NODES, MAX_DEPTH = 32, 128, 256, 2048, 8


def split_top(text, delimiter=None):
    parts, start, depth = [], 0, 0
    for i, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("unbalanced track expression")
        if depth == 0 and (char == delimiter if delimiter else char.isspace()):
            if delimiter and not text[start:i].strip():
                raise ValueError("empty function argument")
            if text[start:i].strip():
                parts.append(text[start:i].strip())
            start = i + 1
    if depth:
        raise ValueError("unbalanced track expression")
    if text[start:].strip():
        parts.append(text[start:].strip())
    elif delimiter and parts:
        raise ValueError("empty function argument")
    return parts


def dimension(text, unit):
    match = re.fullmatch(r"(\d+(?:\.\d+)?|\.\d+)" + unit, text)
    if not match:
        raise ValueError(f"expected nonnegative {unit} dimension: {text!r}")
    value = float(match[1])
    if not math.isfinite(value) or value > 1000000:
        raise ValueError("dimension must be finite and <= 1000000")
    return value


def parse_tracks(text, limit=MAX_COLUMNS):
    if not isinstance(text, str) or len(text) > 8192:
        raise ValueError("track list must be a CSS string of <= 8192 characters")
    tracks = []
    for token in split_top(text.strip()):
        if token.startswith("repeat(") and token.endswith(")"):
            args = split_top(token[7:-1], ",")
            if len(args) != 2 or not re.fullmatch(r"[1-9]\d*", args[0]):
                raise ValueError("repeat() requires a positive integer count")
            count = int(args[0])
            if count > limit or "repeat(" in args[1]:
                raise ValueError("nested/oversized repeat() is unsupported")
            tracks.extend(parse_tracks(args[1], limit) * count)
        elif token.startswith("minmax(") and token.endswith(")"):
            args = split_top(token[7:-1], ",")
            if len(args) != 2:
                raise ValueError("minmax() requires two dimensions")
            minimum = dimension(args[0], "px")
            if args[1].endswith("fr"):
                tracks.append((minimum, minimum, dimension(args[1], "fr")))
            else:
                tracks.append((minimum, max(minimum, dimension(args[1], "px")), 0))
        elif token.endswith("fr"):
            tracks.append((0, 0, dimension(token, "fr")))
        else:
            value = dimension(token, "px")
            tracks.append((value, value, 0))
        if len(tracks) > limit:
            raise ValueError(f"at most {limit} tracks per axis")
    return tracks


def number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1000000:
        raise ValueError(f"{name} must be finite and in 0..1000000")
    return float(value)


def integer(value, name, lo, hi):
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise ValueError(f"{name} must be an integer in {lo}..{hi}")
    return value


def keys(value, allowed):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(f"unsupported properties: expected {', '.join(allowed)}")


def normalize(page):
    """Strict boundary: horizontal LTR, definite content size, stretch, no intrinsic sizing."""
    names = []
    def visit(node, depth, root=False):
        if depth > MAX_DEPTH or len(names) >= MAX_NODES:
            raise ValueError("tree exceeds depth=8 or nodes=2048")
        keys(node, ("id", "width", "height", "grid", "children", "column", "row", "span_column", "span_row"))
        name = node.get("id")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("every node needs a unique nonempty string id")
        index = len(names)
        names.append(name)
        if not root and ("width" in node or "height" in node):
            raise ValueError("only the root has a definite size; children stretch to their areas")
        col = integer(node.get("column", 0), "column", 0, MAX_COLUMNS)
        row = integer(node.get("row", 0), "row", 0, MAX_ROWS)
        cs = integer(node.get("span_column", 1), "span_column", 1, MAX_COLUMNS)
        rs = integer(node.get("span_row", 1), "span_row", 1, MAX_ROWS)
        if (col and col - 1 + cs > MAX_COLUMNS) or (row and row - 1 + rs > MAX_ROWS):
            raise ValueError("definite placement exceeds grid capacity")
        if root and (col or row or cs != 1 or rs != 1):
            raise ValueError("root has no parent grid for placement")
        result = {"id": name, "index": index, "placement": (col, row, cs, rs)}
        if "grid" in node:
            css = node["grid"]
            keys(css, ("columns", "rows", "auto_columns", "auto_rows", "gap", "column_gap", "row_gap", "dense"))
            cols = parse_tracks(css.get("columns", "1fr"))
            rows = parse_tracks(css.get("rows", ""), MAX_ROWS)
            ac = parse_tracks(css.get("auto_columns", "0px"))
            ar = parse_tracks(css.get("auto_rows", "64px"))
            if not cols or len(ac) != 1 or len(ar) != 1:
                raise ValueError("explicit columns required; implicit sizing requires one track")
            cg = number(css.get("column_gap", css.get("gap", 0)), "column gap")
            rg = number(css.get("row_gap", css.get("gap", 0)), "row gap")
            dense = css.get("dense", False)
            if not isinstance(dense, bool):
                raise ValueError("dense must be a boolean")
            result["grid"] = {"columns": cols, "rows": rows, "auto_columns": ac[0], "auto_rows": ar[0],
                              "column_gap": cg, "row_gap": rg, "dense": dense}
            children = node.get("children", [])
            if not isinstance(children, list) or len(children) > MAX_CHILDREN:
                raise ValueError("at most 256 children per grid")
            result["children"] = [visit(child, depth + 1) for child in children]
        elif "children" in node or root:
            raise ValueError("children and root require a grid")
        if root:
            result["width"] = number(node.get("width"), "width")
            result["height"] = number(node.get("height"), "height")
        return result
    result = visit(page, 0, True)
    result["names"] = names
    return result


def bend_float(value):
    return f"{float(value):.9f}"


def bend_list(terms):
    return " <> ".join([*terms, "Nil{}"])


def bend_track(track):
    return "G.Track{" + ", ".join(map(bend_float, track)) + "}"


def bend_node(node):
    item = "G.Item{" + ", ".join(map(str, [node["index"], *node["placement"]])) + "}"
    if "grid" not in node:
        return f"G.Leaf{{{item}}}"
    g = node["grid"]
    style = "G.Style{" + ", ".join([
        "(" + bend_list([bend_track(t) for t in g["columns"]]) + ")",
        "(" + bend_list([bend_track(t) for t in g["rows"]]) + ")",
        bend_track(g["auto_columns"]), bend_track(g["auto_rows"]),
        bend_float(g["column_gap"]), bend_float(g["row_gap"]),
        "True{}" if g["dense"] else "False{}", str(len(g["columns"])), str(len(g["rows"]))]) + "}"
    return f"G.Grid{{{item}, {style}, (" + bend_list([bend_node(c) for c in node["children"]]) + ")}"


def c_input(cases):
    text = []
    def visit(node, prefix):
        ident = f"{prefix}_n{node['index']}"
        children = [visit(c, prefix) for c in node.get("children", [])]
        item = ",".join(map(str, [node["index"], *node["placement"]]))
        style = "NULL"
        if "grid" in node:
            g = node["grid"]
            def track(t):
                return "{" + ",".join(bend_float(v) + "f" for v in t) + "}"
            for axis in ("columns", "rows"):
                text.append(f"static const Track {ident}_{axis}[] = {{" + (",".join(map(track, g[axis])) or "{0,0,0}") + "};")
            text.append(f"static const Style {ident}_style = {{" + ",".join([
                f"{ident}_columns", f"{ident}_rows", str(len(g["columns"])), str(len(g["rows"])),
                track(g["auto_columns"]), track(g["auto_rows"]),
                bend_float(g["column_gap"]) + "f", bend_float(g["row_gap"]) + "f", str(int(g["dense"]))]) + "};")
            style = f"&{ident}_style"
        text.append(f"static const Node *const {ident}_children[] = {{" + (",".join("&" + c for c in children) or "NULL") + "};")
        text.append(f"static const Node {ident} = {{{{{item}}},{style},{ident}_children,{len(children)}}};")
        return ident
    roots = [visit(case, f"p{i}") for i, case in enumerate(cases)]
    text.append("static const Node *const pages[] = {" + ",".join("&" + r for r in roots) + "};")
    text.append("static const float widths[] = {" + ",".join(bend_float(c["width"]) + "f" for c in cases) + "};")
    text.append("static const float heights[] = {" + ",".join(bend_float(c["height"]) + "f" for c in cases) + "};")
    return "\n".join(text)


def build_cases(root, work, pages, bench=None):
    cases = [normalize(page) for page in pages]
    if not cases:
        raise ValueError("at least one page required")
    work.mkdir(parents=True, exist_ok=True)
    source = root / "examples/grid"
    for name in ("contract.bend", "placement.bend", "tracks.bend", "layout.bend"):
        (work / name).write_text((source / name).read_text())
    bend = ["import Base", "import ./contract.bend as G", "import ./layout.bend as L"]
    for i, case in enumerate(cases):
        bend.append(f"def page_{i}() -> G.Node:\n  {bend_node(case)}")
        bend.append(f"def layout_{i}(+delta: F32) -> G.Tree:\n  L.layout(2050n, page_{i}(), G.Box{{0, 0.0, 0.0, F32.add({bend_float(case['width'])}, delta), {bend_float(case['height'])}}})")
    c = ['#include "grid.h"', c_input(cases)]
    if bench is None:
        action = "IO.pure(Unit, Unit{})"
        for i in reversed(range(len(cases))):
            action = f'IO.bind(Unit, Unit, IO.print("case={i}\\n" ++ L.show(10n, layout_{i}(0.0))), u => {action})'
        bend.append("def main() -> IO(Unit):\n  " + action)
        c.append("int main(void) { unsigned errors=0; Output out; ")
        for i in range(len(cases)):
            c.append(f'grid_run(pages[{i}], widths[{i}], heights[{i}], &out); printf("case={i}\\n"); grid_show(&out); errors |= out.errors;')
        c.append("return errors ? 1 : 0; }")
    else:
        depth, repetitions = bench
        integer(depth, "batch depth", 0, 20)
        integer(repetitions, "repetitions", 1, 2 ** 20)
        if len(cases) != 1:
            raise ValueError("benchmark uses one page template")
        bend.append(f'''def bench_layout(+node: G.Node, +delta: F32) -> G.Tree:
  L.layout(2050n, node, G.Box{{0, 0.0, 0.0, F32.add({bend_float(cases[0]['width'])}, delta), {bend_float(cases[0]['height'])}}})

def repeat(+f: Nat, +node: G.Node, +i: U32, acc: G.Stats) -> G.Stats:
  match f:
    case 0n: acc
    case 1n+p:
      +j = U32.add(i, U32.from_nat(p))
      repeat(p, node, i, L.add(acc, L.inspect(10n, bench_layout(node, U32.to_f32(U32.mod(j, 97))))))

def batch(+f: Nat, +node: G.Node, +i: U32) -> G.Stats:
  match f:
    case 0n: repeat({repetitions}n, node, i, G.Stats{{0, 0, 0}})
    case 1n+p:
      a b = batch(p, node, i) batch(p, node, U32.add(i, U32.shln(1, p)))
      L.add(a, b)

def main() -> IO(Unit):
  IO.print(L.stats_show(batch({depth}n, page_0(), 0)))''')
        c.append(f"int main(int argc, char **argv) {{ return grid_bench(argc, argv, pages[0], widths[0], heights[0], {1 << depth}u, {repetitions}u); }}")
    (work / "run.bend").write_text("\n\n".join(bend) + "\n")
    (work / "run.c").write_text("\n".join(c) + "\n")
    binaries = {"bend": work / "grid", "c": work / "grid_c"}
    subprocess.run([str(root / "scripts/bend.sh"), str(work / "run.bend"), "-o", str(binaries["bend"])],
                   env={**os.environ, "BEND_NO_TELEMETRY": "1"}, stdout=subprocess.DEVNULL, check=True)
    subprocess.run([os.environ.get("CC", "clang"), "-std=c11", "-O3", "-ffp-contract=off", "-pthread",
                    "-I", str(source), str(work / "run.c"), str(source / "grid.c"), "-o", str(binaries["c"])], check=True)
    return binaries


def parse_output(text, pages):
    cases = [normalize(p) for p in pages]
    answers, current = [], None
    for line in text.splitlines():
        if not line:
            continue
        if line == f"case={len(answers)}":
            current = {"boxes": {}, "errors": None}
            answers.append(current)
        elif line.startswith("box=") and current is not None:
            parts = line[4:].split(",")
            index = int(parts[0])
            rect = list(map(float, parts[1:]))
            names = cases[len(answers) - 1]["names"]
            if len(rect) != 4 or not all(math.isfinite(v) for v in rect) or not 0 <= index < len(names) or names[index] in current["boxes"]:
                raise ValueError("invalid/duplicate output rectangle")
            current["boxes"][names[index]] = rect
        elif re.fullmatch(r"errors=\d+", line) and current is not None:
            current["errors"] = int(line[7:])
        else:
            raise ValueError(f"invalid grid output: {line}")
    if len(answers) != len(cases) or any(a["errors"] is None or (not a["errors"] and len(a["boxes"]) != len(c["names"])) for a, c in zip(answers, cases)):
        raise ValueError("incomplete grid output")
    return answers


def run_cases(binary, backend, pages, threads=1):
    args = ["--threads", str(threads), "--gpu", "off"] if backend == "bend" else []
    result = subprocess.run([str(binary), *args], capture_output=True, text=True, timeout=120)
    answers = parse_output(result.stdout, pages)
    if result.returncode and not any(a["errors"] for a in answers):
        raise RuntimeError(result.stderr)
    return answers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--backend", choices=("bend", "c"), default="bend")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.threads <= 128:
        parser.error("threads must be 1..128")
    page = json.loads(args.input.read_text())
    try:
        binaries = build_cases(ROOT, ROOT / "build/grid/cli", [page])
        answer = run_cases(binaries[args.backend], args.backend, [page], args.threads)[0]
    except ValueError as error:
        parser.error(str(error))
    if answer["errors"]:
        raise RuntimeError("grid exceeded placement capacity; no valid layout")
    output = json.dumps(answer, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
