"""Measure synchronous CPU/GPU task handoffs with fixed total arithmetic work."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess

from algorithm_bench import ROOT, environment_metadata, command_output
from grid import integer
from grid_gpu import instrument_metal, ProfileFailure

FIELDS = {"round", "calls", "jobs", "checksum", "elapsed_ns", "gpu_commands",
          "gpu_execution_ns", "gpu_wait_ns", "gpu_submit_ns"}


def parse_profile(text, jobs, calls, gpu):
    value = json.loads(text)
    if set(value) != FIELDS or any(type(v) is not int or v < 0 for v in value.values()):
        raise ValueError("invalid device profile")
    if value["jobs"] != jobs or value["calls"] != calls or value["checksum"] >= 2**32:
        raise ValueError("invalid device work accounting")
    if value["gpu_wait_ns"] > value["elapsed_ns"]:
        raise ValueError("GPU wait exceeds total time")
    if gpu and (value["gpu_commands"] < calls or not value["gpu_execution_ns"]):
        raise ValueError("GPU work fell back to CPU")
    if not gpu and any(value[k] for k in ["gpu_commands", "gpu_execution_ns", "gpu_wait_ns", "gpu_submit_ns"]):
        raise ValueError("CPU measurement ran on GPU")
    return value


def build_case(root, work, depth, batch, rounds=0, samples=5, warmups=2):
    integer(depth, "total depth", 0, 16)
    integer(batch, "batch depth", 0, depth)
    integer(rounds, "rounds", 0, 4096)
    integer(samples, "samples", 1, 100)
    integer(warmups, "warmups", 0, 100)
    jobs, group, calls = 1 << depth, 1 << batch, 1 << (depth-batch)
    work.mkdir(parents=True, exist_ok=True)
    for name in ["kernel.bend", "probe.bend", "probe.c"]:
        (work / name).write_bytes((root / "examples/device" / name).read_bytes())
    (work / "run.bend").write_text(f'''import Base
import ./kernel.bend as K
import ./probe.bend as P

def batches(f: Nat, +seed: U32, +offset: U32) -> IO(Unit):
  match f:
    case 0n: P.finish()
    case 1n+p:
      IO.bind(U32, Unit, P.next(K.batch!({batch}n, {rounds}n, seed, offset)), next =>
        batches(p, seed, next))

def repeat(f: Nat, +round: U32) -> IO(Unit):
  match f:
    case 0n: IO.pure(Unit, Unit{{}})
    case 1n+p:
      IO.bind(U32, Unit, P.begin({jobs}, {calls}, round), seed =>
        IO.bind(Unit, Unit, batches({calls}n, seed, 0), u => repeat(p, U32.inc(round))))

def main() -> IO(Unit):
  repeat({samples+warmups}n, 0)
''')
    generated = work / "bend.c"
    subprocess.run([str(root / "scripts/bend.sh"), str(work / "run.bend"), "-o", str(generated)],
                   env={**os.environ,"BEND_NO_TELEMETRY":"1"}, stdout=subprocess.DEVNULL, check=True)
    generated.write_text(instrument_metal(generated.read_text()))
    binary = work / "device_bench"
    flags = [os.environ.get("CC","clang"),"-std=c11","-O3","-ffp-contract=off","-pthread",
             f"-DDEVICE_JOBS={jobs}",f"-DDEVICE_GROUP={group}",f"-DDEVICE_ROUNDS={rounds}"]
    if os.uname().sysname == "Darwin":
        flags += ["-x","objective-c","-fobjc-arc","-fmodules","-DBEND_METAL=1"]
    subprocess.run([*flags,str(generated),"-lm","-o",str(binary)],check=True)
    if os.uname().sysname == "Darwin":
        subprocess.run([str(binary),"--gpu-build"],check=True)
    return binary


def run_case(binary, jobs, calls, gpu, threads=10):
    result = subprocess.run([str(binary),"--threads",str(threads),"--gpu","on" if gpu else "off"],
                            env={**os.environ,"BEND_NO_TELEMETRY":"1"},text=True,capture_output=True,timeout=300)
    if result.returncode:
        raise ProfileFailure(result)
    return [parse_profile(line,jobs,calls,gpu) for line in result.stdout.splitlines()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--depth",type=int,default=14)
    parser.add_argument("--batch-depth",type=int,action="append")
    parser.add_argument("--rounds",type=int,action="append")
    parser.add_argument("--samples",type=int,default=5)
    parser.add_argument("--warmups",type=int,default=2)
    parser.add_argument("--output",type=Path,default=ROOT / "examples/device/results-macos-m5.json")
    args = parser.parse_args()
    batches = args.batch_depth or list(dict.fromkeys(min(args.depth,b) for b in [7,10,12,args.depth]))
    specs = [(args.depth,b,r) for r in args.rounds or [0,64,4096] for b in batches]
    if args.depth==14 and args.batch_depth is None and args.rounds is None:
        specs.insert(0,(0,0,0)) # one scalar, no fork: tiny synchronous boundary
    built = []
    for d,b,r in specs:
        work = ROOT / "build/device" / f"{d}-{b}-{r}"
        binary = build_case(ROOT,work,d,b,r,args.samples,args.warmups)
        built.append((d,b,r,work,binary))
        print(f"built jobs={1<<d} calls={1<<(d-b)} rounds={r}",flush=True)
    meta = environment_metadata()
    sources = [*sorted((ROOT / "examples/device").glob("*.bend")),
               ROOT / "examples/device/probe.c",Path(__file__),ROOT / "scripts/grid_gpu.py",
               ROOT / "scripts/grid.py", ROOT / "scripts/algorithm_bench.py"]
    if os.uname().sysname == "Darwin":
        displays = json.loads(command_output("system_profiler", "SPDisplaysDataType", "-json"))
        meta["gpu"] = [{"model":d.get("sppci_model"),"cores":d.get("sppci_cores"),
                        "metal":d.get("spdisplays_mtlgpufamilysupport")}
                       for d in displays["SPDisplaysDataType"]]
    meta.update(method="serial within-process timings; same total jobs/rounds across batch depths; 2 warmups + median-of-5 by default",
                samples=args.samples,warmups=args.warmups,source_state="local synchronous CPU/GPU boundary experiment",
                measurement_scope="CPU IO next consumes one U32 and supplies the next batch offset; GPU waits per bang; excludes build/setup, native oracle and stdout; no bulk result readback",
                control="Bend CPU 1/all threads runs the same program with --gpu off; native oracle checks complete aggregate",
                c_scheduler="not applicable; controls use Bend's CPU fork/join runtime",
                bend_flags="-std=c11 -O3 -ffp-contract=off -pthread -x objective-c -fobjc-arc -fmodules -DBEND_METAL=1 -lm plus DEVICE_JOBS/GROUP/ROUNDS",
                source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                generated_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                                  for _,_,_,work,_ in built for p in [work / "run.bend",work / "bend.c"]})
    record = {"environment":meta,"cases":[]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for d,b,r,work,binary in built:
        timings,reference = {},None
        jobs,calls=1<<d,1<<(d-b)
        record["cases"].append({"depth":d,"batch_depth":b,"rounds":r,"jobs":jobs,
                                "jobs_per_call":1<<b,"calls":calls,"timings":timings})
        for label,threads,gpu in [("cpu-1",1,False),("cpu-all",meta["threads"],False),("gpu",meta["threads"],True)]:
            rows=run_case(binary,jobs,calls,gpu,threads)
            if len(rows)!=args.samples+args.warmups or [v["round"] for v in rows]!=list(range(len(rows))):
                raise RuntimeError("incomplete sample sequence")
            values=[v["checksum"] for v in rows]
            if reference is not None and values!=reference:
                raise RuntimeError("CPU/GPU output mismatch")
            reference=values
            measured=rows[args.warmups:]
            median={k:statistics.median(v[k] for v in measured) for k in FIELDS if k.endswith("_ns")}
            median["per_call_ns"]=statistics.median(v["elapsed_ns"]/calls for v in measured)
            timings[label]={"samples":rows,"median":median}
            print(f'jobs={jobs} calls={calls} rounds={r} {label}: {median["elapsed_ns"]/1e6:.3f}ms; {median["per_call_ns"]/1e3:.3f}us/call',flush=True)
            args.output.write_text(json.dumps(record,indent=2)+"\n")
    meta["thermal_after"]=command_output("pmset","-g","therm")
    args.output.write_text(json.dumps(record,indent=2)+"\n")
    print(args.output)


if __name__ == "__main__":
    main()
