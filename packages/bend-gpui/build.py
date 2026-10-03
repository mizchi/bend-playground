"""Standalone builder for the macOS Bend/GPUI package (Python standard library)."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess

PACKAGE = Path(__file__).resolve().parent
DEPLOYMENT = os.environ.get("MACOSX_DEPLOYMENT_TARGET", "15.0")
FRAMEWORKS = ("Cocoa", "Metal", "CoreVideo", "CoreGraphics", "CoreText", "QuartzCore",
              "Security", "SystemConfiguration", "VideoToolbox", "ScreenCaptureKit", "Carbon")


def executable_name(name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise ValueError("name must be a single executable filename")
    return name


def cargo(*args, target_dir=None, deployment=DEPLOYMENT):
    env = {**os.environ, "MACOSX_DEPLOYMENT_TARGET": deployment}
    if target_dir is not None:
        env["CARGO_TARGET_DIR"] = str(Path(target_dir).resolve())
    subprocess.run(["cargo", *args, "--manifest-path", str(PACKAGE / "Cargo.toml")],
                   env=env, check=True)


def shader_header(work):
    Path(work, "convert-source.h").write_text("static const char *gpui_shader_source = "
        + json.dumps((PACKAGE / "metal/convert.metal").read_text()) + ";\n")


def instrument_metal(source, prefix="grid_probe"):
    """Patch generated scratch C only; preserve upstream compiler and scheduling."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", prefix):
        raise ValueError("invalid GPU probe prefix")
    anchor = "static bool io_gpu;"
    declarations = """static uint32_t grid_probe_commands;
static uint64_t grid_probe_execution, grid_probe_wait, grid_probe_submit;
static uint64_t grid_probe_clock(void) {
  struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
  return (uint64_t)t.tv_sec * 1000000000ull + (uint64_t)t.tv_nsec;
}
"""
    if source.count(anchor) != 1:
        raise ValueError("unsupported generated runtime: IO anchor")
    source = source.replace(anchor, declarations.replace("grid_probe_", prefix + "_") + anchor)
    old = """static void gpu_pass(u32 f) {
  @autoreleasepool {
    id<MTLCommandBuffer> cb = [gpu_que commandBuffer];"""
    new = """static void gpu_pass(u32 f) {
  uint64_t grid_submit_begin = grid_probe_clock();
  @autoreleasepool {
    id<MTLCommandBuffer> cb = [gpu_que commandBuffer];"""
    ending = """    [cb commit];
    [cb waitUntilCompleted];
    if ([cb error]) {"""
    measured = """    [cb commit];
    uint64_t grid_wait_begin = grid_probe_clock();
    [cb waitUntilCompleted];
    uint64_t grid_wait_end = grid_probe_clock();
    grid_probe_commands++;
    grid_probe_submit += grid_wait_begin - grid_submit_begin;
    grid_probe_wait += grid_wait_end - grid_wait_begin;
    grid_probe_execution += (uint64_t)(([cb GPUEndTime] - [cb GPUStartTime]) * 1e9);
    if ([cb error]) {"""
    if source.count(old) != 1 or source.count(ending) != 1:
        raise ValueError("unsupported generated runtime: Metal dispatch anchor")
    return source.replace(old, new.replace("grid_probe_", prefix + "_")).replace(
        ending, measured.replace("grid_probe_", prefix + "_"))


def compile_app(work, generated, name="bend-gpui", bundle_id="com.mizchi.bend-gpui",
                extra_objects=(), *, target_dir=None, release=False,
                include_dirs=(), cflags=(), deployment=DEPLOYMENT):
    """Link generated Bend C with the static library and produce a macOS app."""
    executable_name(name)
    work, generated = Path(work).resolve(), Path(generated).resolve()
    target = Path(target_dir).resolve() if target_dir else work / "target"
    binary = work / name
    includes = [work, generated.parent, PACKAGE / "include", *map(Path, include_dirs)]
    frameworks = [arg for framework in FRAMEWORKS for arg in ("-framework", framework)]
    subprocess.run([os.environ.get("CC", "clang"), "-std=c11", "-O3", "-ffp-contract=off", "-pthread",
                    "-mmacosx-version-min=" + deployment,
                    "-x", "objective-c", "-fobjc-arc", "-fmodules", "-DBEND_METAL=1",
                    *[arg for directory in includes for arg in ("-I", str(directory))], *cflags,
                    str(generated), "-x", "none", *map(str, extra_objects),
                    str(target / ("release" if release else "debug") / "libbend_gpui.a"),
                    *frameworks, "-liconv", "-lm", "-o", str(binary)], check=True)
    subprocess.run([str(binary), "--gpu-build"], check=True)
    app = work / "BendGPUI.app/Contents"
    executable = app / "MacOS" / name
    executable.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, executable)
    shutil.copy2(Path(str(binary) + ".gpu"), Path(str(executable) + ".gpu"))
    (app / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": bundle_id, "CFBundleName": name, "CFBundleExecutable": name,
        "CFBundlePackageType": "APPL", "CFBundleVersion": "1",
        "NSHighResolutionCapable": True, "LSMinimumSystemVersion": deployment,
    }))
    return executable


def build(source, output, *, name="bend-gpui", bundle_id="com.mizchi.bend-gpui",
          bend_command="bend", target_dir=None, release=False):
    """Build a caller-owned Bend entry point without copying its source tree."""
    executable_name(name)
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if os.uname().sysname != "Darwin":
        raise RuntimeError("bend-gpui requires macOS/Metal")
    output.mkdir(parents=True, exist_ok=True)
    target = Path(target_dir).resolve() if target_dir else output / "target"
    cargo("build", "--locked", *(["--release"] if release else []), target_dir=target)
    shader_header(output)
    generated = output / "bend.c"
    subprocess.run([str(bend_command), str(source), "-o", str(generated)],
                   env={**os.environ, "BEND_NO_TELEMETRY": "1"}, check=True)
    generated.write_text(instrument_metal(generated.read_text(), prefix="bend_gpui_probe"))
    return compile_app(output, generated, name, bundle_id, target_dir=target,
                       release=release, include_dirs=[source.parent])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Bend file defining main")
    parser.add_argument("--output", type=Path, default=Path("build/bend-gpui"))
    parser.add_argument("--name", default="bend-gpui")
    parser.add_argument("--bundle-id", default="com.mizchi.bend-gpui")
    parser.add_argument("--bend-command", default="bend", help="Bend executable or wrapper path")
    parser.add_argument("--target-dir", type=Path, help="shared Cargo build cache")
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args()
    binary = build(args.source, args.output, name=args.name, bundle_id=args.bundle_id,
                   bend_command=args.bend_command, target_dir=args.target_dir, release=args.release)
    print(binary)


if __name__ == "__main__":
    main()
