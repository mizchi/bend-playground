"""Separate GPU stage diagnostics from serial, uninstrumented mapping timings."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import statistics
import subprocess

import particles
from algorithm_bench import command_output
from grid import integer

MAPPINGS = ('bend', 'leaf', 'particle', 'tiled', 'strided')
PROBE_FIELDS = {'kind', 'frame', 'backend', 'count', 'jobs', 'noise_rounds',
                'cpu_before', 'gpu_before', 'cpu_after', 'gpu_after', 'dispatches'}
DISPATCH_FIELDS = {'name', 'pass_index', 'groups', 'threads', 'begin', 'end'}


def parse_probe(line):
    row = json.loads(line)
    if set(row) != PROBE_FIELDS or row['kind'] != 'gpu_dispatch_profile' or row['backend'] not in ('bend-gpu', 'metal'):
        raise ValueError('invalid GPU probe fields')
    for key in PROBE_FIELDS - {'kind', 'backend', 'dispatches'}:
        integer(row[key], key, 0, 2**64-2)
    integer(row['count'], 'count', 1, 1000000)
    integer(row['jobs'], 'jobs', 64, 16384)
    if row['jobs'] & (row['jobs']-1) or row['noise_rounds'] not in (0, 64):
        raise ValueError('invalid GPU probe work')
    cpu_delta = row['cpu_after'] - row['cpu_before']
    gpu_delta = row['gpu_after'] - row['gpu_before']
    if cpu_delta <= 0 or gpu_delta <= 0 or not isinstance(row['dispatches'], list) or not 1 <= len(row['dispatches']) <= 4:
        raise ValueError('invalid GPU probe calibration')
    end = row['gpu_before']
    for dispatch in row['dispatches']:
        if set(dispatch) != DISPATCH_FIELDS or not isinstance(dispatch['name'], str) or not dispatch['name']:
            raise ValueError('invalid GPU dispatch fields')
        for key in DISPATCH_FIELDS - {'name'}:
            integer(dispatch[key], key, 0, 2**64-2)
        integer(dispatch['groups'], 'groups', 1, 1000000)
        integer(dispatch['threads'], 'threads', 1, 1024)
        if dispatch['pass_index'] not in (0, 1, 2) or not end <= dispatch['begin'] < dispatch['end'] <= row['gpu_after']:
            raise ValueError('invalid GPU dispatch timestamps')
        end = dispatch['end']
        dispatch['elapsed_ns'] = (dispatch['end'] - dispatch['begin']) * cpu_delta / gpu_delta
    row['gpu_to_cpu_ratio'] = cpu_delta / gpu_delta
    return row


def instrument_gpu(source):
    """Patch host dispatch; append a direct kernel calling the unchanged leaf."""
    opening = 'static void gpu_kernel(u32 pass, u32 groups) {\n  [gpu_enc setComputePipelineState:gpu_pso];'
    replacement = '''#define PARTICLE_GPU_PROBE 1
#include "gpu-profile.h"
static void gpu_kernel(u32 pass, u32 groups) {
  if (particle_probe_active) gpu_enc = particle_probe_encoder(particle_probe_command,
    pass == 2 ? "pack" : pass == 1 ? "drain" : groups == 1 ? "grow_single" : "grow_all",
    pass, groups, CUBE_T);
  [gpu_enc setComputePipelineState:gpu_pso];'''
    closing = '  [gpu_enc memoryBarrierWithScope:MTLBarrierScopeBuffers];\n}'
    encoded = '''    gpu_enc = [cb computeCommandEncoder];
    gpu_run(f);
    [gpu_enc endEncoding];'''
    guarded = '''    particle_probe_command = cb;
    gpu_enc = particle_probe_active ? nil : [cb computeCommandEncoder];
    gpu_run(f);
    if (!particle_probe_active) [gpu_enc endEncoding];'''
    for old, new in [(opening, replacement),
                     (closing, closing[:-2] + '\n  if (particle_probe_active) {\n'
                      '    [gpu_enc updateFence:particle_probe_fence];\n'
                      '    [gpu_enc endEncoding];\n  }\n}'),
                     (encoded, guarded)]:
        if source.count(old) != 1:
            raise ValueError('unsupported pinned Metal runtime for GPU probe')
        source = source.replace(old, new)
    return source + '\n#ifdef __METAL_VERSION__\n' + (particles.SOURCE / 'gpu-leaf.metal').read_text() + '\n#endif\n'


def specifications(counts, rounds, grains):
    return [(count, noise, jobs, mapping)
            for count in counts for noise in rounds for jobs in grains for mapping in MAPPINGS
            if mapping != 'particle' or jobs == grains[0]]


def run(binary, mapping, count, frames=4, width=960, height=540, verify=False,
        dump=None, profile=False):
    if mapping not in MAPPINGS:
        raise ValueError('invalid GPU mapping')
    backend = 'bend-gpu' if mapping == 'bend' else 'metal'
    env = particles.run_env(backend, count, frames, width, height, headless=True, verify=verify, dump=dump)
    env['BEND_PARTICLE_GPU_INFO'] = '1'
    if mapping != 'bend': env['BEND_PARTICLE_METAL_MAPPING'] = mapping
    if profile: env['BEND_PARTICLE_GPU_PROFILE'] = '1'
    cmd = particles.command(binary, backend)
    if mapping == 'leaf': cmd[2] = 'on'
    result = subprocess.run(cmd, env=env,
                            text=True, capture_output=True, timeout=300)
    if result.returncode:
        raise RuntimeError(f'GPU experiment failed {result.returncode}: {result.stderr}\n{result.stdout}')
    rows, probes, metadata = [], [], []
    for line in result.stdout.splitlines():
        if line.startswith('{'): rows.append(particles.parse_frame(line, backend))
        elif line.startswith('GPU_PROFILE '):
            raw = line[len('GPU_PROFILE '):]
            if json.loads(raw).get('kind') == 'gpu_metadata': metadata.append(json.loads(raw))
            else: probes.append(parse_probe(raw))
    if [r['frame'] for r in rows] != list(range(frames)) or len(metadata) != 1:
        raise RuntimeError('incomplete GPU frames or metadata')
    if any(r['count'] != count or r['verified_particles'] != (count if verify else 0) for r in rows):
        raise RuntimeError('GPU experiment count mismatch')
    if len({r['buffer_offset'] for r in rows}) != 1:
        raise RuntimeError('GPU state allocation changed')
    if [p['frame'] for p in probes] != (list(range(frames)) if profile else []):
        raise RuntimeError('incomplete/unexpected GPU probes')
    for p, row in zip(probes, rows):
        if any(p[k] != row[k] for k in ('frame', 'backend', 'count', 'jobs', 'noise_rounds')):
            raise RuntimeError('GPU probe configuration mismatch')
    return rows, probes, metadata[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, action='append')
    parser.add_argument('--jobs', type=int, action='append')
    parser.add_argument('--noise-rounds', type=int, choices=[0, 64], action='append')
    parser.add_argument('--warmups', type=int, default=5)
    parser.add_argument('--samples', type=int, default=11)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--output', type=Path, default=particles.SOURCE / 'results-macos-m5-gpu.json')
    args = parser.parse_args()
    counts, rounds, grains = args.count or [100000, 1000000], args.noise_rounds or [0, 64], args.jobs or [1024, 4096, 16384]
    for items in (counts, rounds, grains):
        if len(set(items)) != len(items): parser.error('duplicate GPU configuration')
    for count in counts: integer(count, 'count', 1, 1000000)
    for jobs in grains:
        integer(jobs, 'jobs', 64, 16384)
        if jobs & (jobs-1): parser.error('jobs must be a power of two')
    integer(args.warmups, 'warmups', 1, 100)
    integer(args.samples, 'samples', 3, 100)
    integer(args.repeats, 'repeats', 1, 10)
    binaries = {(r,j):particles.build(particles.ROOT / 'build/particles/gpu-profile' / f'{r}-{j}',
                noise_rounds=r, jobs=j, variant='flat', gpu_probe=True) for r in rounds for j in grains}
    meta = {key:particles.metadata(binary) for key,binary in binaries.items()}
    cases = specifications(counts, rounds, grains)
    record = dict(method='serial matched GPU update comparison, same renderer/state/math; '
        'particle=one native Metal thread/particle, tiled=same consecutive ranges as Bend, '
        'strided=interleaved particles per job; same helper for all handwritten Metal mappings; '
        'leaf=unchanged emitted Bend spin_16 called directly from an added Metal kernel; '
        'same consecutive ranges and coherent array accesses, bypassing generic runtime; '
        'generic Bend retains its emitted device code and original dispatch sequence; '
        'counter branch disabled during speed timings; '
        'encoder-boundary GPU counter diagnostics recorded in separate processes; '
        'Bend diagnostics split its encoder and perturb scheduling; do not subtract these '
        'durations from normal command-buffer time; calibrated CPU/GPU clocks; '
        'GPU execution overlaps CPU wait; startup/verification/GPUI present excluded',
        warmups=args.warmups, samples=args.samples, repeats=args.repeats,
        order_seed=20261003, verification=[], diagnostics=[], execution_order=[],
        execution_order_columns=['repeat', 'count', 'noise_rounds', 'jobs', 'mapping'], cases=[])
    # Finish all full-scale verification and diagnostic work before normal timing.
    for count,r,j,mapping in cases:
        rows, probes, gpu = run(binaries[r,j], mapping, count, frames=4, verify=True)
        if any(row['jobs'] != j or row['noise_rounds'] != r for row in rows):
            raise RuntimeError('GPU verification shape mismatch')
        record['verification'].append(dict(count=count, noise_rounds=r, jobs=j, mapping=mapping,
            frames=len(rows), verified_particles=count, gpu=gpu))
        rows, probes, gpu = run(binaries[r,j], mapping, count, frames=args.warmups+args.samples, profile=True)
        measured = probes[args.warmups:]
        # A labelled phase may occur only once per update in the pinned runtime.
        phase_names = [d['name'] for d in measured[0]['dispatches']]
        stage_medians = {name:statistics.median(next(d['elapsed_ns'] for d in p['dispatches']
                              if d['name'] == name) for p in measured) for name in phase_names}
        record['diagnostics'].append(dict(count=count, noise_rounds=r, jobs=j, mapping=mapping,
            gpu=gpu, rows=rows, probes=probes, stage_median_ns=stage_medians))
        print(f'verified/profiled {mapping} count={count} noise={r} jobs={j}', flush=True)
    record['thermal_before'] = command_output('pmset','-g','therm')
    results = {case:dict(**meta[case[1],case[2]], count=case[0], noise_rounds=case[1],
                 jobs=case[2], mapping=case[3], runs=[]) for case in cases}
    rng = random.Random(record['order_seed'])
    for repeat in range(args.repeats):
        order = cases.copy(); rng.shuffle(order)
        for count,r,j,mapping in order:
            rows, probes, gpu = run(binaries[r,j], mapping, count, frames=args.warmups+args.samples)
            if any(row['jobs'] != j or row['noise_rounds'] != r for row in rows):
                raise RuntimeError('GPU timed configuration mismatch')
            medians = {k:statistics.median(row[k] for row in rows[args.warmups:]) for k in rows[0] if k.endswith('_ns')}
            results[count,r,j,mapping]['runs'].append(dict(repeat=repeat, samples=rows, median=medians))
            record['execution_order'].append([repeat,count,r,j,mapping])
            print(f'run={repeat+1} {mapping} count={count} noise={r} jobs={j}: '
                  f'GPU={medians["update_gpu_ns"]/1e6:.3f}ms update={medians["update_ns"]/1e6:.3f}ms',flush=True)
    for case in results.values():
        keys = case['runs'][0]['median']
        case['median'] = {k:statistics.median(run['median'][k] for run in case['runs']) for k in keys}
        case['run_median_range'] = {k:[min(run['median'][k] for run in case['runs']),
                                     max(run['median'][k] for run in case['runs'])] for k in keys}
        record['cases'].append(case)
    record['thermal_after'] = command_output('pmset','-g','therm')
    record['source_sha256'] = {str(p.relative_to(particles.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in [Path(__file__),particles.ROOT/'tests/particles_gpu.py']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(record,indent=2)+'\n')
    print(args.output)


if __name__ == '__main__':
    main()
