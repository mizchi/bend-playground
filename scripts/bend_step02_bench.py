"""Build and validate identical particle sources, then time compiler lanes serially."""
import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import re
import statistics
import struct
import subprocess

import particles
from algorithm_bench import command_output
from bend_step02 import CHECKOUT, prepare

ROOT = particles.ROOT
SOURCE = ROOT / 'compiler-patches/step-02-known-callbacks'
WORK = ROOT / 'build/bend-steps/step-02/particles'


@contextmanager
def compiler(repo):
    previous = os.environ.get('BEND_REPO')
    os.environ['BEND_REPO'] = str(repo)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('BEND_REPO', None)
        else:
            os.environ['BEND_REPO'] = previous


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def definitions():
    # Same grain on old/new compilers. These are earlier measured settings,
    # not a search for the best grain of the new compiler.
    return [(lane, variant, rounds, jobs)
            for lane in ('base', 'patched') for variant in particles.VARIANTS
            for rounds in (0, 64) for jobs in (1024, 16384)]


def build():
    prepare()
    rows = []
    for lane, variant, rounds, jobs in definitions():
        repo = ROOT / 'upstream/bend' if lane == 'base' else CHECKOUT
        with compiler(repo):
            binary = particles.build(WORK / f'{lane}-{variant}-{rounds}-{jobs}',
                                     noise_rounds=rounds, jobs=jobs, variant=variant)
            meta = particles.metadata(binary)
        code = (Path(binary).parents[3] / 'bend.c').read_text()
        rows.append(dict(lane=lane, rounds=rounds, jobs=jobs,
                         binary=str(binary.relative_to(ROOT)),
                         compiler_sha256=digest(repo / 'bend2/comp.ts'),
                         live_closure_segments=len(re.findall(r'WL_CASE\(FID_[A-Z0-9_]+_C\d+\)', code)),
                         **meta))
        print(f'built {lane}/{variant}, noise={rounds}, jobs={jobs}', flush=True)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / 'manifest.json').write_text(json.dumps(rows, indent=2) + '\n')
    return rows


def oracle():
    spec = importlib.util.spec_from_file_location('particle_oracle', ROOT / 'tests/particles.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify(rows, counts):
    reference = oracle()
    records = []
    image_reference = {}
    # Every compiled binary is checked, including empty ranges and edge counts.
    for spec in rows:
        backend = 'bend-cpu' if spec['jobs'] == 1024 else 'bend-gpu'
        for count in (1, 17, 10003):
            dump = WORK / ('dump-' + Path(spec['binary']).parts[4]) / str(count)
            frames = particles.run(ROOT / spec['binary'], backend, count, frames=4,
                                   width=64, height=32, verify=True, dump=dump)
            expected = [reference.initial(i) for i in range(count)]
            for frame in range(4):
                expected = [reference.update(p, spec['rounds']) for p in expected]
                raw = (dump / f'{frame}.particles').read_bytes()
                if len(raw) != count * 32:
                    raise RuntimeError('particle dump length mismatch')
                for index, actual in enumerate(struct.iter_unpack('=8f', raw)):
                    if actual[5:] != tuple(expected[index][5:]) or any(
                            not math.isfinite(got) or abs(got - wanted) > 2e-6
                            for got, wanted in zip(actual[:5], expected[index][:5])):
                        raise RuntimeError('independent float32 oracle mismatch')
                image = (dump / f'{frame}.nv12').read_bytes()
                if len(image) != 64 * 32 * 3 // 2:
                    raise RuntimeError('image dump length mismatch')
                if count == 1 and max(abs(a-b) for a, b in zip(
                        image, reference.single_particle_image(expected[0], 64, 32))) > 2:
                    raise RuntimeError('independent image oracle mismatch')
                key = (spec['rounds'], spec['jobs'], count, frame)
                if spec['lane'] == 'base' and spec['variant'] == 'callback':
                    image_reference[key] = image
                elif max(abs(a-b) for a, b in zip(image, image_reference[key])) > 2:
                    raise RuntimeError('compiler/variant image comparison mismatch')
            records.append(dict(lane=spec['lane'], variant=spec['variant'], rounds=spec['rounds'],
                                jobs=spec['jobs'], count=count, backend=backend,
                                independent_frames=4))
        for count in counts:
            for threads in ((1, 10) if backend == 'bend-cpu' else (10,)):
                frames = particles.run(ROOT / spec['binary'], backend, count, frames=4,
                                       verify=True, threads=threads)
                if len({r['buffer_offset'] for r in frames}) != 1:
                    raise RuntimeError('persistent buffer offset changed')
                records.append(dict(lane=spec['lane'], variant=spec['variant'], rounds=spec['rounds'],
                                    jobs=spec['jobs'], count=count, backend=backend,
                                    threads=threads, full_scale_frames=4))
        print(f'verified {spec["lane"]}/{spec["variant"]}, noise={spec["rounds"]}, jobs={spec["jobs"]}', flush=True)
    (WORK / 'verification.json').write_text(json.dumps(records, indent=2) + '\n')
    return records


def measure(rows, verification, args):
    specs = []
    for row in rows:
        backend = 'bend-cpu' if row['jobs'] == 1024 else 'bend-gpu'
        repo = ROOT / 'upstream/bend' if row['lane'] == 'base' else CHECKOUT
        if digest(repo / 'bend2/comp.ts') != row['compiler_sha256']:
            raise RuntimeError('compiler changed since build; rebuild and verify first')
        if row['generated_sha256']['bend.c'] != digest(Path(ROOT / row['binary']).parents[3] / 'bend.c'):
            raise RuntimeError('generated code changed since build')
        for count in args.count:
            for threads in ((1, 10) if backend == 'bend-cpu' else (10,)):
                specs.append(dict(**row, backend=backend, count=count, threads=threads, runs=[]))
    record = dict(method='serial fixed 960x540 offscreen particle frame preparation; '
                  'identical callback/flat sources across compiler lanes; '
                  'GPU update waits for completion, render/conversion then share a command buffer; '
                  'GPU timestamps and CPU waits overlap; no measured-frame readback; '
                  'startup/build/verification excluded; UI presentation excluded',
                  warmups=args.warmups, samples=args.samples, repeats=args.repeats,
                  order_seed=20261003, compiler_patch_sha256=digest(SOURCE / 'compiler.patch'),
                  benchmark_source_sha256=digest(__file__), verification=verification,
                  execution_order=[], cases=specs,
                  thermal_before=command_output('pmset', '-g', 'therm'),
                  cpu_load_before=command_output('top', '-l', '2', '-n', '0', '-s', '1'))
    for spec in specs:
        if not any(v.get('full_scale_frames') == 4 and all(v.get(k) == spec[k]
                   for k in ('lane', 'variant', 'rounds', 'jobs', 'count', 'backend', 'threads'))
                   for v in verification):
            raise RuntimeError('missing verification for a timed configuration')
    rng = random.Random(record['order_seed'])
    for repeat in range(args.repeats):
        order = specs.copy()
        rng.shuffle(order)
        for spec in order:
            record['execution_order'].append([repeat, spec['lane'], spec['variant'],
                                              spec['rounds'], spec['count'], spec['backend'], spec['threads']])
            frames = particles.run(ROOT / spec['binary'], spec['backend'], spec['count'],
                                   frames=args.warmups + args.samples, threads=spec['threads'])
            median = {k: statistics.median(frame[k] for frame in frames[args.warmups:])
                      for k in frames[0] if k.endswith('_ns')}
            spec['runs'].append(dict(repeat=repeat, frames=frames, median=median))
            print(f'{repeat+1}: {spec["lane"]}/{spec["variant"]} noise={spec["rounds"]} '
                  f'{spec["backend"]}/{spec["threads"]} count={spec["count"]}: '
                  f'{median["update_ns"]/1e6:.3f} ms', flush=True)
    for spec in specs:
        keys = spec['runs'][0]['median']
        spec['median'] = {k: statistics.median(r['median'][k] for r in spec['runs']) for k in keys}
        spec['run_median_range'] = {k: [min(r['median'][k] for r in spec['runs']),
                                       max(r['median'][k] for r in spec['runs'])] for k in keys}
    record['thermal_after'] = command_output('pmset', '-g', 'therm')
    record['cpu_load_after'] = command_output('top', '-l', '2', '-n', '0', '-s', '1')
    args.output.write_text(json.dumps(record, indent=2) + '\n')
    print(args.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('all', 'build', 'verify', 'bench'), default='all')
    parser.add_argument('--count', type=int, action='append')
    parser.add_argument('--samples', type=int, default=25)
    parser.add_argument('--warmups', type=int, default=5)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--output', type=Path, default=SOURCE / 'results-macos-m5.json')
    args = parser.parse_args()
    args.count = sorted(set(args.count or [1000000]))
    if any(not 1 <= n <= 1000000 for n in args.count) or min(args.samples, args.repeats) < 1 or args.warmups < 0:
        parser.error('invalid benchmark configuration')
    rows = build() if args.phase in ('all', 'build') else json.loads((WORK / 'manifest.json').read_text())
    if args.phase == 'build': return
    verification = verify(rows, args.count) if args.phase in ('all', 'verify') else json.loads((WORK / 'verification.json').read_text())
    if args.phase == 'verify': return
    measure(rows, verification, args)


if __name__ == '__main__':
    main()
