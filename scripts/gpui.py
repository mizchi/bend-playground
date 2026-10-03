"""Build and run the macOS Bend → shared Metal surface → GPUI binding."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from grid import ROOT, integer, normalize, bend_node, c_input
from grid_cases import dashboard
from bend_gpui import LIBRARY, TARGET, DEPLOYMENT, cargo, compile_app, instrument_metal

FIELDS = {"frame", "width", "height", "kind", "bend_ns", "bend_gpu_commands",
          "bend_gpu_ns", "convert_gpu_ns", "convert_wait_ns", "cpu_payload_read_bytes",
          "verified_pixels", "handoff_ns", "drop_ns", "frame_ready_ns"}
SOURCE = ROOT / "examples/gpui"


def dimensions(width, height):
    return integer(width, "width", 2, 2048) & ~1, integer(height, "height", 2, 2048) & ~1


def parse_frame(line, gpu=False):
    value = json.loads(line)
    if set(value) != FIELDS or value["kind"] not in ("pixels", "rects"):
        raise ValueError("invalid GPUI frame fields")
    if any(type(v) is not int or v < 0 for k, v in value.items() if k != "kind"):
        raise ValueError("invalid GPUI frame values")
    if dimensions(value["width"], value["height"]) != (value["width"], value["height"]):
        raise ValueError("NV12 requires even dimensions")
    if value["cpu_payload_read_bytes"] != 0:
        raise ValueError("production path must not read the Bend buffer payload")
    if gpu and (not value["bend_gpu_commands"] or not value["bend_gpu_ns"]):
        raise ValueError("Bend GPU fallback")
    if not gpu and (value["bend_gpu_commands"] or value["bend_gpu_ns"]):
        raise ValueError("unexpected Bend GPU execution")
    if not value["convert_gpu_ns"] or not value["convert_wait_ns"]:
        raise ValueError("missing real conversion dispatch")
    if value["frame_ready_ns"] != value["bend_ns"] + value["handoff_ns"] + value["drop_ns"]:
        raise ValueError("inconsistent frame timing")
    if value["convert_wait_ns"] > value["handoff_ns"]:
        raise ValueError("conversion wait exceeds its containing phase")
    if value["verified_pixels"] not in (0, value["width"] * value["height"]):
        raise ValueError("incomplete pixel verification")
    return value


def build(mode="grid", work=None, page=None):
    if os.uname().sysname != "Darwin":
        raise RuntimeError("this binding requires macOS/Metal")
    if mode not in ("grid", "shader"):
        raise ValueError("mode must be grid or shader")
    work = Path(work or ROOT / "build/gpui" / mode)
    work.mkdir(parents=True, exist_ok=True)
    cargo("build", "--locked")
    for path in SOURCE.iterdir():
        if path.suffix in (".bend", ".c", ".h", ".metal"):
            (work / path.name).write_bytes(path.read_bytes())
    for name in ["contract.bend", "placement.bend", "tracks.bend", "layout.bend", "gpu-flat.bend", "grid.c", "grid.h"]:
        (work / name).write_bytes((ROOT / "examples/grid" / name).read_bytes())
    case = normalize(dashboard() if page is None else page)
    count = len(case['names'])
    depth = (count * 4 - 1).bit_length()
    stride = 1 << depth
    (work / "oracle-input.h").write_text(c_input([case]))
    (work / "convert-source.h").write_text("static const char *gpui_shader_source = " + json.dumps((SOURCE / "convert.metal").read_text()) + ";\n")
    grid_source = f'''import Base
import ./api.bend as UI
import ./contract.bend as G
import ./gpu-flat.bend as B

def output(result: B.FlatOutput) -> UI.Frame:
  match result:
    case B.FlatResult{{buffer, errors}}: UI.Rects{{{count}, errors, buffer}}

def frame(tick: UI.Tick) -> UI.Frame:
  match tick:
    case UI.Tick{{width, height, frame}}:
      buffer = Array.new(F32, {depth}n, 0.0)
      output(B.batch(0n, {bend_node(case)}, U32.to_f32(width), U32.to_f32(height), 0, 0, {stride}, buffer))
'''
    if mode == "grid":
        (work / "draw.bend").write_text(grid_source)
    else:
        (work / "draw.bend").write_bytes((SOURCE / "shader.bend").read_bytes())
    (work / "run.bend").write_text('''import Base
import ./api.bend as UI
import ./draw.bend as Draw

def main() -> IO(Unit):
  UI.run(960, 540, 0, tick => Draw.frame!(tick))
''')
    generated = work / "bend.c"
    subprocess.run([str(ROOT / "scripts/bend.sh"), str(work / "run.bend"), "-o", str(generated)],
                   env={**os.environ, "BEND_NO_TELEMETRY": "1"}, check=True, stdout=subprocess.DEVNULL)
    generated.write_text(instrument_metal(generated.read_text(), prefix="bend_gpui_probe"))
    return compile_app(work, generated, cflags=['-DBEND_GPUI_VERIFY_HEADER="verify.h"'])


def run(binary, gpu=False, frames=3, width=960, height=540, headless=False, verify=False, timeout=120):
    width, height = dimensions(width, height)
    integer(frames, "frames", 1, 10000)
    env = {**os.environ, "BEND_NO_TELEMETRY": "1", "BEND_GPUI_FRAMES": str(frames),
           "BEND_GPUI_WIDTH": str(width), "BEND_GPUI_HEIGHT": str(height)}
    for key, active in [("BEND_GPUI_HEADLESS", headless), ("BEND_GPUI_VERIFY", verify)]:
        env.pop(key, None)
        if active: env[key] = "1"
    result = subprocess.run([str(binary), "--gpu", "on" if gpu else "off", "--threads", str(min(os.cpu_count() or 1, 128))],
                            env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"GPUI exited {result.returncode}: {result.stderr}\n{result.stdout}")
    rows = [parse_frame(line, gpu) for line in result.stdout.splitlines() if line.startswith('{')]
    if [r["frame"] for r in rows] != list(range(frames)):
        raise RuntimeError(f"incomplete frame sequence: {result.stdout}\n{result.stderr}")
    return rows


def library_sources():
    return [p for p in LIBRARY.rglob('*') if p.suffix in ('.bend', '.c', '.h', '.metal', '.rs', '.py')] + [
        LIBRARY / 'Cargo.toml', LIBRARY / 'Cargo.lock']


def metadata(binary):
    from algorithm_bench import environment_metadata, command_output
    paths = [p for p in SOURCE.rglob('*') if p.suffix in ('.bend', '.c', '.h', '.metal', '.rs')]
    paths += library_sources() + [ROOT / "tests/gpui.py", ROOT / "scripts/bend_gpui.py",
              ROOT / "scripts/gpui.py", ROOT / "scripts/grid_gpu.py", ROOT / "scripts/grid.py", ROOT / "scripts/grid_cases.py"]
    paths += [p for p in (ROOT / "examples/grid").iterdir() if p.suffix in ('.bend', '.c', '.h')]
    work = Path(binary).parents[3]
    environment = environment_metadata()
    environment.update(rustc=command_output("rustc", "--version"), cargo=command_output("cargo", "--version"),
                       gpu=json.loads(command_output("system_profiler", "SPDisplaysDataType", "-json"))["SPDisplaysDataType"])
    return {"environment": environment, "gpui": "0.2.2", "rust_profile": "dev, debug=0",
            "deployment_target": DEPLOYMENT,
            "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
            "generated_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in [work / 'run.bend', work / 'draw.bend', work / 'bend.c']}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["grid", "shader"], nargs="?", default="grid")
    parser.add_argument("--gpu", choices=["on", "off"], default="off")
    parser.add_argument("--frames", type=int, default=0)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--page", type=Path, help="Grid JSON input; viewport replaces root size")
    args = parser.parse_args()
    width, height = dimensions(args.width, args.height)
    integer(args.frames, "frames", 0, 10000)
    if args.headless and not args.frames:
        parser.error("--headless requires a positive --frames")
    if args.output and not args.frames:
        parser.error("--output requires a positive --frames")
    if args.page and args.mode != "grid":
        parser.error("--page requires grid mode")
    binary = build(args.mode, page=json.loads(args.page.read_text()) if args.page else None)
    if args.frames:
        rows = run(binary, args.gpu == "on", args.frames, width, height, args.headless, args.verify)
        for row in rows: print(json.dumps(row))
        if args.output:
            record = {**metadata(binary), "mode": args.mode,
                      "bend_backend": args.gpu, "headless": args.headless, "verify": args.verify,
                      "samples": rows}
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(record, indent=2) + '\n')
    else:
        env = {**os.environ, "BEND_GPUI_WIDTH": str(width), "BEND_GPUI_HEIGHT": str(height),
               "BEND_GPUI_FRAMES": "0", "BEND_NO_TELEMETRY": "1"}
        env.pop("BEND_GPUI_HEADLESS", None)
        env.pop("BEND_GPUI_VERIFY", None)
        if args.verify: env["BEND_GPUI_VERIFY"] = "1"
        subprocess.run([str(binary), "--gpu", args.gpu], env=env, check=True)


if __name__ == "__main__":
    main()
