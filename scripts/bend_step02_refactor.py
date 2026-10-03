"""Compare pinned upstream and fork commits using identical particle sources."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from bend_step02 import git
import bend_step02_bench as bench

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'compiler-patches/step-02-known-callbacks/refactored'
WORK = ROOT / 'build/bend-steps/step-02-refactored'
REFERENCE = SOURCE / 'reference.json'


def prepare(manifest=REFERENCE, work=WORK):
    repositories = {}
    for lane, spec in json.loads(manifest.read_text()).items():
        repo = work / ('base' if lane == 'base' else 'bend')
        if not repo.exists():
            repo.mkdir(parents=True)
            git(repo, 'init', '-q')
            git(repo, 'fetch', '--depth=1', spec['repository'], spec['revision'])
            git(repo, 'checkout', '--detach', spec['revision'])
        if git(repo, 'rev-parse', 'HEAD').stdout.strip() != spec['revision']:
            raise RuntimeError('existing checkout has another revision; preserved it')
        if git(repo, 'status', '--porcelain', '--untracked-files=all').stdout.strip():
            raise RuntimeError('existing checkout is dirty; preserved it')
        if bench.digest(repo / 'bend2/comp.ts') != spec['compiler_sha256']:
            raise RuntimeError('compiler hash does not match the reference')
        repositories[lane] = repo
    return repositories


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('setup', 'check', 'bench'))
    parser.add_argument('--phase', choices=('all', 'build', 'verify', 'bench'), default='all')
    parser.add_argument('--samples', type=int, default=15)
    parser.add_argument('--warmups', type=int, default=5)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--output', type=Path, default=SOURCE / 'results-macos-m5.json')
    args = parser.parse_args()
    if min(args.samples, args.repeats) < 1 or args.warmups < 0:
        parser.error('invalid measurement configuration')
    repos = prepare()
    if args.action == 'setup':
        print(repos['patched'])
        return 0
    if args.action == 'check':
        subprocess.run(['python3', str(ROOT / 'tests/bend_step02_reference.py')], check=True)
        env = {**os.environ, 'BEND_REPO': str(repos['patched']),
               'BEND_BASE_REPO': str(repos['base']), 'BEND_PARTICLE_CID': 'Tick',
               'BEND_NO_TELEMETRY': '1'}
        return subprocess.run(['python3', str(ROOT / 'tests/bend_step02_refactor.py')], env=env).returncode
    # Adapt only the copied C constructor name for this upstream revision.
    # Both lanes use identical Bend sources and this same C adapter.
    sources = WORK / 'sources'
    sources.mkdir(parents=True, exist_ok=True)
    for path in bench.particles.SOURCE.iterdir():
        if path.suffix in ('.bend', '.c', '.h', '.metal'):
            shutil.copyfile(path, sources / path.name)
    native = sources / 'native.c'
    native.write_text(native.read_text().replace('CID(api.Tick)', 'CID(Tick)'))
    bench.particles.SOURCE = sources
    bench.SOURCE = SOURCE
    bench.WORK = WORK / 'particles'
    args.count = [1000000]
    args.compiler_references = json.loads(REFERENCE.read_text())
    configs = [(lane, variant, 64, jobs) for lane in ('base', 'patched')
               for variant in ('callback', 'flat') for jobs in (1024, 16384)]
    rows = bench.build(repos, configs) if args.phase in ('all', 'build') else json.loads((bench.WORK / 'manifest.json').read_text())
    if args.phase == 'build': return 0
    verified = bench.verify(rows, args.count) if args.phase in ('all', 'verify') else json.loads((bench.WORK / 'verification.json').read_text())
    if args.phase == 'verify': return 0
    bench.measure(rows, verified, args, repos)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except RuntimeError as error:
        sys.exit(str(error))
