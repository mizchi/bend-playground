"""Serial persistent-state particle timings, with one renderer for all backends."""
import argparse
import hashlib
import json
from itertools import product
import os
from pathlib import Path
import statistics
import random

import particles
from algorithm_bench import command_output
from grid import integer


def specifications(variants, rounds, jobs, counts, backends, threads):
    specs = []
    for backend in backends:
        versions = variants[:1] if backend in ('c-cpu', 'c-direct', 'metal') else variants
        grains = jobs[:1] if backend == 'metal' else jobs
        workers = threads if backend in particles.CPU_BACKENDS else threads[:1]
        if backend == 'c-direct':
            workers = [1]
        specs.extend((v, r, j, count, backend, t)
                     for v, r, j, count, t in product(versions, rounds, grains, counts, workers))
    return specs


def main(cpu_comparison=False):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, action='append')
    parser.add_argument('--jobs', type=int, action='append')
    parser.add_argument('--noise-rounds', type=int, choices=[0, 64], action='append')
    parser.add_argument('--variant', choices=particles.VARIANTS, action='append')
    parser.add_argument('--backend', choices=particles.BACKENDS, action='append')
    parser.add_argument('--threads', type=int, action='append')
    parser.add_argument('--warmups', type=int, default=5 if cpu_comparison else 3)
    parser.add_argument('--samples', type=int, default=11 if cpu_comparison else 7)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--order-seed', type=int, default=20261003)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    integer(args.warmups, 'warmups', 1, 100)
    integer(args.samples, 'samples', 3, 100)
    integer(args.repeats, 'repeats', 1, 10)
    counts = args.count or [10000, 100000, 1000000]
    jobs = args.jobs or ([64, 1024, 4096, 16384] if cpu_comparison else [1024, 4096, 16384])
    rounds = args.noise_rounds or [0, 64]
    variants = args.variant or (['flat'] if cpu_comparison else ['callback'])
    backends = args.backend or (list(particles.CPU_BACKENDS) if cpu_comparison else ['bend-cpu', 'bend-gpu', 'metal'])
    workers = min(os.cpu_count() or 1, 128)
    threads = args.threads or (list(dict.fromkeys([1, workers])) if cpu_comparison else [workers])
    if any(len(set(items)) != len(items) for items in [counts, jobs, rounds, variants, backends, threads]):
        parser.error('duplicate configuration')
    default_output = 'results-macos-m5-cpu.json' if cpu_comparison else (
        'results-macos-m5-code.json' if 'flat' in variants else 'results-macos-m5.json')
    output = args.output or particles.SOURCE / default_output
    for t in threads: integer(t, 'threads', 1, 128)
    for count in counts: integer(count, 'count', 1, 1000000)
    for n in jobs:
        integer(n, 'jobs', 64, 16384)
        if n & (n - 1): parser.error('jobs must be a power of two')
    # Finish every CPU/GPU build before verification or timing begins.
    binaries = {(v, r, j): particles.build(noise_rounds=r, jobs=j, variant=v)
                for v in variants for r in rounds for j in jobs}
    record = dict(method='serial within-process fixed 960x540 offscreen CVPixelBuffer preparation; '
                  'radius=2 pixels, additive circular sprites, fixed dt=1/60 and seed; '
                  'same shared-buffer Metal renderer and NV12 pool for all backends; '
                  'update waits for GPU completion, render and conversion submit without an intervening CPU wait; '
                  'GPU durations and CPU waits overlap and must not be added; '
                  'GPUI scene/present/display, startup, initial state allocation, and verification excluded',
                  warmups=args.warmups, samples=args.samples, repeats=args.repeats,
                  variants=variants, backends=backends, thread_counts=threads,
                  cpu_scheduler='Bend: persistent runtime workers with fork/handle management; '
                  'c-cpu: persistent pthread workers with atomic job queue and completion barrier; '
                  'c-direct: calling thread runs the same job ranges sequentially; '
                  'thread counts refer to configured workers, excluding the calling thread; '
                  'Bend may evaluate initial tasks on its caller, while the C caller waits for its pool; '
                  'same ceil(count/jobs) consecutive ranges, different scheduler implementations; '
                  'C rounds are runtime parameters in a separate translation unit without LTO; '
                  'C pool allocation and thread startup are outside frame timings',
                  order_seed=args.order_seed,
                  execution_order_columns=['repeat', 'variant', 'noise_rounds', 'jobs', 'count', 'backend', 'threads'],
                  execution_order=[], cases=[], verification=[])
    metadata = {key: particles.metadata(binary) for key, binary in binaries.items()}
    specs = specifications(variants, rounds, jobs, counts, backends, threads)
    # Validate the actual full-scale count and every grain before timing it.
    # These reads occur in separate untimed processes, never in measured frames.
    for v, r, j, count, backend, t in specs:
        rows = particles.run(binaries[v, r, j], backend, count, frames=4, verify=True, threads=t)
        if any(row['jobs'] != j or row['noise_rounds'] != r for row in rows):
            raise RuntimeError('particle verification configuration mismatch')
        record['verification'].append(dict(variant=v, noise_rounds=r, jobs=j, count=count, backend=backend,
                                           threads=t,
                                           frames=len(rows), verified_particles=rows[-1]['verified_particles'],
                                           stable_buffer=len({row['buffer_offset'] for row in rows}) == 1))
        print(f'verified {v} {backend} count={count} noise={r} jobs={j} threads={t}', flush=True)
    record['thermal_before'] = command_output('pmset', '-g', 'therm')
    cases = {spec: dict(**metadata[spec[0], spec[1], spec[2]], noise_rounds=spec[1], jobs=spec[2],
                       count=spec[3], backend=spec[4], threads=spec[5], runs=[]) for spec in specs}
    rng = random.Random(args.order_seed)
    for repeat in range(args.repeats):
        order = specs.copy()
        rng.shuffle(order)
        for v, r, j, count, backend, t in order:
            record['execution_order'].append([repeat, v, r, j, count, backend, t])
            rows = particles.run(binaries[v, r, j], backend, count, frames=args.warmups + args.samples, threads=t)
            if any(row['jobs'] != j or row['noise_rounds'] != r for row in rows):
                raise RuntimeError('particle binary configuration mismatch')
            measured = rows[args.warmups:]
            medians = {key: statistics.median(row[key] for row in measured)
                       for key in rows[0] if key.endswith('_ns')}
            cases[v, r, j, count, backend, t]['runs'].append(dict(repeat=repeat, samples=rows, median=medians))
            print(f'run={repeat + 1} {v} {backend} count={count} noise={r} jobs={j} threads={t}: '
                  f'update={medians["update_ns"]/1e6:.3f}ms drawGPU={medians["draw_gpu_ns"]/1e6:.3f}ms '
                  f'ready={medians["frame_ready_ns"]/1e6:.3f}ms', flush=True)
    for case in cases.values():
        keys = case['runs'][0]['median']
        case['median'] = {key: statistics.median(run['median'][key] for run in case['runs']) for key in keys}
        case['run_median_range'] = {key: [min(run['median'][key] for run in case['runs']),
                                        max(run['median'][key] for run in case['runs'])] for key in keys}
        record['cases'].append(case)
    record['benchmark_source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    entrypoint = particles.ROOT / 'scripts' / ('particles_cpu_bench.py' if cpu_comparison else 'particles_bench.py')
    record['benchmark_entrypoint'] = str(entrypoint.relative_to(particles.ROOT))
    record['benchmark_entrypoint_sha256'] = hashlib.sha256(entrypoint.read_bytes()).hexdigest()
    record['thermal_after'] = command_output('pmset', '-g', 'therm')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + '\n')
    print(output)


if __name__ == '__main__':
    main()
