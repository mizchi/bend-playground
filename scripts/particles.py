"""Persistent Bend/Metal particle state and a shared GPUI renderer (macOS)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import gpui
from algorithm_bench import ROOT, environment_metadata, command_output
from grid import integer
from grid_gpu import instrument_metal

SOURCE = ROOT / "examples/particles"
BACKENDS = ("bend-cpu", "bend-gpu", "metal", "c-cpu", "c-direct")
CPU_BACKENDS = ('bend-cpu', 'c-cpu', 'c-direct')
CPU_FLAGS = ('-std=c11', '-O3', '-ffp-contract=off', '-pthread')
VARIANTS = ('callback', 'flat')
FIELDS = {"frame", "width", "height", "count", "backend", "noise_rounds", "jobs", "threads", "radius_px",
          "c_completed_jobs", "c_workers_used",
          "buffer_offset", "buffer_bytes", "state_allocations", "state_prepare_ns", "surface_prepare_ns",
          "update_ns", "update_gpu_ns", "update_wait_ns", "bend_gpu_commands", "bend_gpu_submit_ns",
          "draw_gpu_ns", "convert_gpu_ns", "render_wait_ns", "render_ns", "release_ns", "frame_ready_ns",
          "cpu_readback_bytes", "verified_particles", "verify_ns"}


def default_jobs(backend, count):
    # Measured choices for this experiment, not a general scheduler heuristic.
    options(backend, count, 1, 960, 540)
    if backend == 'bend-gpu':
        return 4096 if count <= 10000 else 16384
    return 1024


def options(backend, count, frames, width, height):
    if backend not in BACKENDS:
        raise ValueError("invalid particle backend")
    integer(count, "count", 1, 1000000)
    integer(frames, "frames", 0, 10000)
    return gpui.dimensions(width, height)


def parse_frame(line, backend):
    row = json.loads(line)
    if set(row) != FIELDS or row["backend"] != backend:
        raise ValueError("invalid particle frame fields")
    if any(type(v) is not int or v < 0 for k, v in row.items() if k != "backend"):
        raise ValueError("invalid particle frame values")
    if options(backend, row['count'], row['frame'] + 1, row['width'], row['height']) != (row['width'], row['height']):
        raise ValueError("invalid particle dimensions")
    if row['cpu_readback_bytes'] or row['state_allocations'] != 1 or row['radius_px'] != 2:
        raise ValueError("particle readback/allocation contract violated")
    depth = (row['count'] * 8 - 1).bit_length()
    if row['buffer_bytes'] != (4 << depth) or row['verified_particles'] not in (0, row['count']):
        raise ValueError("incomplete particle state")
    if row['noise_rounds'] not in (0, 64) or not 64 <= row['jobs'] <= 16384 or row['jobs'] & (row['jobs'] - 1):
        raise ValueError("invalid simulation configuration")
    thread_count(backend, row['threads'])
    if backend.startswith('c-'):
        if row['c_completed_jobs'] != row['jobs'] or not 1 <= row['c_workers_used'] <= row['threads']:
            raise ValueError("incomplete C worker update")
    elif row['c_completed_jobs'] or row['c_workers_used']:
        raise ValueError("unexpected C worker update")
    if (backend == 'bend-gpu') != (row['bend_gpu_commands'] == 1):
        raise ValueError("Bend GPU fallback or unexpected dispatch")
    if backend != 'bend-gpu' and row['bend_gpu_commands']:
        raise ValueError("unexpected Bend GPU dispatch")
    if (backend not in CPU_BACKENDS) != bool(row['update_gpu_ns']):
        raise ValueError("invalid GPU update timing")
    if backend in CPU_BACKENDS and (row['update_wait_ns'] or row['bend_gpu_submit_ns']):
        raise ValueError("CPU update unexpectedly waited for the GPU")
    if row['update_wait_ns'] > row['update_ns'] or row['render_wait_ns'] > row['render_ns']:
        raise ValueError("wait exceeds its containing phase")
    phases = ['surface_prepare_ns', 'update_ns', 'render_ns', 'release_ns']
    if row['frame_ready_ns'] != sum(row[k] for k in phases) or not row['draw_gpu_ns'] or not row['convert_gpu_ns']:
        raise ValueError("inconsistent particle frame timing")
    return row


def build(work=None, noise_rounds=0, jobs=4096, variant='callback', gpu_probe=False):
    if os.uname().sysname != 'Darwin':
        raise RuntimeError("particles require macOS/Metal")
    if type(noise_rounds) is not int or noise_rounds not in (0, 64):
        raise ValueError("noise_rounds must be 0 or 64")
    integer(jobs, 'jobs', 64, 16384)
    if jobs & (jobs - 1):
        raise ValueError("jobs must be a power of two")
    if variant not in VARIANTS:
        raise ValueError("invalid particle code variant")
    work = Path(work or ROOT / 'build/particles' / variant / f'{noise_rounds}-{jobs}')
    work.mkdir(parents=True, exist_ok=True)
    gpui.cargo('build', '--locked')
    for path in SOURCE.iterdir():
        if path.suffix in ('.bend', '.c', '.h', '.metal'):
            (work / path.name).write_bytes(path.read_bytes())
    (work / 'abi.h').write_bytes((gpui.SOURCE / 'abi.h').read_bytes())
    shader = (gpui.SOURCE / 'convert.metal').read_text() + '\n' + (SOURCE / 'particles.metal').read_text()
    (work / 'particle-source.h').write_text('static const char *particle_shader_source = ' + json.dumps(shader) + ';\n')
    (work / 'particle-config.h').write_text(f'#define PARTICLE_NOISE_ROUNDS {noise_rounds}\n#define PARTICLE_JOBS {jobs}\n')
    depth, fuel = jobs.bit_length() - 1, (1000000 + jobs - 1) // jobs + 1
    enabled = 'True{}' if noise_rounds else 'False{}'
    simulation = 'simulation.bend' if variant == 'callback' else 'simulation-flat.bend'
    (work / 'run.bend').write_text(f'''import Base
import ./api.bend as UI
import ./{simulation} as Sim

def main() -> IO(Unit):
  UI.run(960, 540, 100000, 0, tick => state =>
    Sim.update!(tick, state, {depth}n, {fuel}n, {noise_rounds}n, {enabled}))
''')
    generated = work / 'bend.c'
    subprocess.run([str(ROOT / 'scripts/bend.sh'), str(work / 'run.bend'), '-o', str(generated)],
                   env={**os.environ, 'BEND_NO_TELEMETRY': '1'}, stdout=subprocess.DEVNULL, check=True)
    generated.write_text(instrument_metal(generated.read_text()))
    if gpu_probe:
        from particles_gpu import instrument_gpu
        loops = codegen_report(generated.read_text())['particle_loops']
        if len(loops) != 1 or loops[0]['function'] != 'spin_16' or any(
            loops[0][key] for key in ('heap_alloc_sites', 'closure_sites', 'dynamic_apply_sites')):
            raise ValueError('GPU leaf requires the pinned allocation-free flat particle loop')
        generated.write_text(instrument_gpu(generated.read_text()))
    cpu_object = work / 'cpu.o'
    subprocess.run([os.environ.get('CC', 'clang'), *CPU_FLAGS,
                    '-mmacosx-version-min=' + gpui.DEPLOYMENT,
                    '-c', str(work / 'cpu.c'), '-o', str(cpu_object)], check=True)
    return gpui.compile_app(work, generated, 'bend-particles', 'com.mizchi.bend-playground.particles',
                            extra_objects=[cpu_object])


def run_env(backend, count, frames, width, height, headless=False, verify=False, dump=None):
    width, height = options(backend, count, frames, width, height)
    if headless and not frames:
        raise ValueError("headless particles require finite frames")
    if dump is not None and not verify:
        raise ValueError("dump requires verification")
    env = {k: v for k, v in os.environ.items() if not k.startswith('BEND_PARTICLE_')}
    env.update(BEND_NO_TELEMETRY='1', BEND_PARTICLE_BACKEND=backend,
               BEND_PARTICLE_COUNT=str(count), BEND_PARTICLE_FRAMES=str(frames),
               BEND_PARTICLE_WIDTH=str(width), BEND_PARTICLE_HEIGHT=str(height))
    if headless: env['BEND_PARTICLE_HEADLESS'] = '1'
    if verify: env['BEND_PARTICLE_VERIFY'] = '1'
    if dump is not None:
        Path(dump).mkdir(parents=True, exist_ok=True)
        env['BEND_PARTICLE_DUMP'] = str(dump)
    return env


def thread_count(backend, threads=None):
    if backend not in BACKENDS:
        raise ValueError("invalid particle backend")
    value = (1 if backend == 'c-direct' else min(os.cpu_count() or 1, 128)) if threads is None else threads
    integer(value, 'threads', 1, 128)
    if backend == 'c-direct' and value != 1:
        raise ValueError('c-direct requires one thread')
    return value


def command(binary, backend, threads=None):
    return [str(binary), '--gpu', 'on' if backend == 'bend-gpu' else 'off',
            '--threads', str(thread_count(backend, threads))]


def run(binary, backend="bend-cpu", count=10000, frames=3, width=960, height=540,
        headless=True, verify=False, dump=None, timeout=300, threads=None):
    if not frames:
        raise ValueError("run requires finite frames")
    expected_threads = thread_count(backend, threads)
    result = subprocess.run(command(binary, backend, expected_threads), env=run_env(backend, count, frames, width, height,
                            headless, verify, dump), capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'Particles exited {result.returncode}: {result.stderr}\n{result.stdout}')
    rows = [parse_frame(line, backend) for line in result.stdout.splitlines() if line.startswith('{')]
    if [r['frame'] for r in rows] != list(range(frames)):
        raise RuntimeError(f'incomplete particle frames: {result.stdout}\n{result.stderr}')
    if len({r['buffer_offset'] for r in rows}) != 1:
        raise RuntimeError("particle allocation changed between frames")
    if any(r['threads'] != expected_threads or r['count'] != count or
           (r['verified_particles'] != count if verify else r['verified_particles'] != 0) for r in rows):
        raise RuntimeError('particle run configuration mismatch')
    return rows


def codegen_report(source):
    """Inspect pinned-compiler C, including the leaf's transitive spin helpers.

    Counts describe emitted source sites, not dynamic allocation counters or
    final Metal machine code. A particle loop must both read and write arrays.
    """
    functions = dict(re.findall(r'^INLINE Term (spin_\d+)\([^\n]+\) \{\n(.*?)^\}',
                                source, re.MULTILINE | re.DOTALL))
    loops = []
    for name, body in functions.items():
        if f'WL_AGAIN({name})' not in body:
            continue
        visited, pending = set(), [name]
        while pending:
            callee = pending.pop()
            if callee in visited:
                continue
            visited.add(callee)
            pending.extend(re.findall(r'\b(spin_\d+)\(', functions[callee]))
        code = '\n'.join(functions[callee] for callee in sorted(visited))
        if 'blk_read(' not in code or 'blk_write(' not in code:
            continue
        loops.append(dict(function=name, transitive_helpers=sorted(visited - {name}),
                          heap_alloc_sites=len(re.findall(r'\bheap_alloc\(', code)),
                          closure_sites=len(re.findall(r'\bterm_clo\(', code)),
                          dynamic_apply_sites=code.count('FID_CLO_APPLY')))
    return dict(particle_loops=loops, runtime_particle_closure_segments=len(re.findall(
                r'WL_CASE\(FID_SIMULATION_TILE_C\d+\)', source)))


def metadata(binary):
    environment = environment_metadata()
    environment.update(method='serial within-process particle frame preparation; startup excluded',
                       c_flags='-O3 -ffp-contract=off; Objective-C/Metal; GPUI Rust dev debug=0',
                       source_state='local particle additions on the recorded playground commit')
    environment.pop('source_sha256', None)
    environment.pop('c_scheduler', None)
    environment.pop('rss_unit', None)
    environment['logical_cpu_count'] = environment.pop('threads')
    environment.update(rustc=command_output('rustc', '--version'),
                       gpu=json.loads(command_output('system_profiler', 'SPDisplaysDataType', '-json'))['SPDisplaysDataType'])
    paths = [p for p in SOURCE.iterdir() if p.suffix in ('.bend', '.c', '.h', '.metal')]
    paths += [ROOT / 'scripts/particles.py', ROOT / 'scripts/gpui.py', ROOT / 'scripts/grid_gpu.py',
              ROOT / 'scripts/algorithm_bench.py', ROOT / 'scripts/grid.py', ROOT / 'tests/particles.py',
              gpui.SOURCE / 'abi.h', gpui.SOURCE / 'convert.metal', gpui.SOURCE / 'Cargo.toml',
              gpui.SOURCE / 'Cargo.lock', gpui.SOURCE / 'src/lib.rs']
    work = Path(binary).parents[3]
    return dict(environment=environment, gpui='0.2.2', deployment_target=gpui.DEPLOYMENT,
                c_cpu_flags=' '.join(CPU_FLAGS) + ' -mmacosx-version-min=' + gpui.DEPLOYMENT + '; separate TU, no LTO',
                variant='flat' if './simulation-flat.bend' in (work / 'run.bend').read_text() else 'callback',
                codegen=codegen_report((work / 'bend.c').read_text()),
                source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                generated_sha256={name: hashlib.sha256((work / name).read_bytes()).hexdigest()
                                  for name in ['run.bend', 'particle-config.h', 'particle-source.h', 'bend.c', 'cpu.o']})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=BACKENDS, default='bend-cpu')
    parser.add_argument('--variant', choices=VARIANTS, default='callback')
    parser.add_argument('--count', type=int, default=100000)
    parser.add_argument('--noise-rounds', type=int, choices=[0, 64], default=0)
    parser.add_argument('--jobs', type=int, help='power of two; defaults to measured CPU/GPU grain')
    parser.add_argument('--threads', type=int, help='CPU workers; c-direct requires one')
    parser.add_argument('--frames', type=int, default=0)
    parser.add_argument('--width', type=int, default=960)
    parser.add_argument('--height', type=int, default=540)
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--dump', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    threads = thread_count(args.backend, args.threads)
    env = run_env(args.backend, args.count, args.frames, args.width, args.height, args.headless, args.verify, args.dump)
    if args.output and not args.frames:
        parser.error('--output requires finite frames')
    binary = build(noise_rounds=args.noise_rounds,
                   jobs=args.jobs if args.jobs is not None else default_jobs(args.backend, args.count),
                   variant=args.variant)
    if args.frames:
        rows = run(binary, args.backend, args.count, args.frames, args.width, args.height,
                   args.headless, args.verify, args.dump, threads=threads)
        for row in rows: print(json.dumps(row))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({**metadata(binary), 'samples': rows,
                'headless': args.headless, 'verify': args.verify, 'threads': threads}, indent=2) + '\n')
    else:
        subprocess.run(command(binary, args.backend, threads), env=env, check=True)


if __name__ == '__main__':
    main()
