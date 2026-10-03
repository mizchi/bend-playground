"""Run upstream closure/array probes locally, outside the cluster gate."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
REPO = Path(os.environ.get('BEND_REPO', ROOT / 'build/bend-steps/step-02/bend'))
ENV = {**os.environ, 'BEND_REPO': str(REPO), 'BEND_NO_TELEMETRY': '1'}
NAMES = ('closures_hof', 'fn_capture_owns', 'unsafe_mutual', 'array_map_loop',
         'js_tail_closure', 'js_loop_capture', 'array_poly_elem', 'array_boxed_get',
         'array_split_join', 'array_wrap_index', 'array_fill_fold', 'ids_unique')


def run(args):
    result = subprocess.run(list(map(str, args)), env=ENV, capture_output=True,
                            text=True, timeout=90)
    if result.returncode:
        raise RuntimeError(f'{args}: {result.stdout} {result.stderr}')
    return result.stdout.strip()


def main():
    records = []
    with tempfile.TemporaryDirectory() as temporary:
        for name in NAMES:
            source = REPO / 'tests/run' / (name + '.bend')
            expected = '\n'.join(line[2:].strip() for line in source.read_text().splitlines()
                                 if line.startswith('#|'))
            binary = Path(temporary) / name
            run([ROOT / 'scripts/bend.sh', source, '-o', binary.with_suffix('.c')])
            run(['clang', '-O3', '-std=c11', '-pthread', binary.with_suffix('.c'),
                 '-lm', '-o', binary])
            run([ROOT / 'scripts/bend.sh', source, '-o', binary.with_suffix('.js')])
            lanes = (
                ('interpreter', [ROOT / 'scripts/bend.sh', source]),
                ('js', ['bun', binary.with_suffix('.js')]),
                ('c-1', [binary, '--gpu', 'off', '--threads', '1']),
                ('c-4', [binary, '--gpu', 'off', '--threads', '4']),
            )
            for lane, args in lanes:
                actual = run(args)
                if actual != expected:
                    raise RuntimeError(f'{name}/{lane}: expected {expected!r}, got {actual!r}')
                records.append(dict(test=name, lane=lane, output=actual))
            print('PASS', name, flush=True)
    output = ROOT / 'build/bend-steps/step-02/upstream-check.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(records, indent=2) + '\n')


if __name__ == '__main__':
    main()
