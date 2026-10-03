"""Known callback specialization contracts; BEND_REPO selects the compiler."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'compiler-patches/step-02-known-callbacks'
ENV = {**os.environ, 'BEND_NO_TELEMETRY': '1'}


def run(*args, env=ENV):
    return subprocess.run([str(a) for a in args], env=env, capture_output=True,
                          text=True, timeout=90)


class CallbackTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.work = Path(self.directory.name)

    def emit(self, name='known_callback', source=None):
        source = source or SOURCE / (name + '.bend')
        output = self.work / (name + '.c')
        result = run(ROOT / 'scripts/bend.sh', source, '-o', output)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return output

    def execute(self, source, expected):
        generated = self.emit(source.stem, source)
        binary = self.work / source.stem
        result = run('clang', '-O3', '-std=c11', '-pthread', generated, '-lm', '-o', binary)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for threads in (1, 4):
            result = run(binary, '--threads', threads, '--gpu', 'off')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.strip(), expected)
        js = self.work / (source.stem + '.js')
        result = run(ROOT / 'scripts/bend.sh', source, '-o', js)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for command in (('bun', js), (ROOT / 'scripts/bend.sh', source)):
            result = run(*command)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.strip(), expected)
        return generated.read_text()

    def test_known_callback_captures_and_tuple_match_keep_results(self):
        self.execute(SOURCE / 'known_callback.bend', '42')

    def test_linear_array_handle_and_scalar_captures(self):
        self.execute(SOURCE / 'callback_array.bend', '42')

    def test_dynamic_boxed_and_recursive_callbacks_keep_results(self):
        code = self.execute(SOURCE / 'callback_fallback.bend', '42')
        self.assertIn('FID_CLO_APPLY', code)
        self.assertTrue(re.findall(r'WL_CASE\(FID_[A-Z0-9_]+_C\d+\)', code))

    def test_compilation_does_not_mutate_book_and_resets_specializations(self):
        repo = Path(ENV.get('BEND_REPO', ROOT / 'upstream/bend'))
        result = run('bun', SOURCE / 'compile-repeat.ts', repo,
                     SOURCE / 'known_callback.bend')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_specialization_budget_keeps_large_input_executable(self):
        source = self.work / 'budget.bend'
        lines = ['import Base',
                 'def apply(x: U32, callback: U32 -> U32) -> U32:', '  callback(x)',
                 'def loop(x: U32) -> U32:']
        for i in range(80):
            previous = 'x' if i == 0 else f'a{i-1}'
            lines.append(f'  a{i} = apply({previous}, y => U32.inc(y))')
        lines.extend(['  a79', 'def main() -> U32:', '  loop(1)', '#| 81'])
        source.write_text('\n'.join(lines) + '\n')
        code = self.execute(source, '81')
        self.assertLessEqual(len(set(re.findall(r'FID_APPLY_CALLBACK(\d+)\b', code))), 64)

    def test_function_capture_keeps_generic_fallback(self):
        source = self.work / 'function_capture.bend'
        source.write_text('''import Base
 def apply(x: U32, callback: U32 -> U32) -> U32:
   callback(x)
 def forward(f: U32 -> U32, x: U32) -> U32:
   apply(x, y => f(y))
 def main() -> U32:
   forward(y => U32.add(y, 2), 40)
'''.replace('\n ', '\n'))
        self.execute(source, '42')

    def test_flat_particle_codegen_is_byte_identical(self):
        for path in (ROOT / 'examples/particles').iterdir():
            if path.suffix in ('.bend', '.c', '.h'):
                (self.work / path.name).write_bytes(path.read_bytes())
        (self.work / 'abi.h').write_bytes((ROOT / 'examples/gpui/abi.h').read_bytes())
        # Newer compilers use the constructor's short name in imported C.
        if ENV.get('BEND_PARTICLE_CID') == 'Tick':
            native = self.work / 'native.c'
            native.write_text(native.read_text().replace('CID(api.Tick)', 'CID(Tick)'))
        source = self.work / 'run.bend'
        source.write_text('''import Base
import ./api.bend as UI
import ./simulation-flat.bend as Sim
def main() -> IO(Unit):
  UI.run(960, 540, 100000, 0, tick => state =>
    Sim.update!(tick, state, 10n, 978n, 64n, True{}))
''')
        generated = self.emit(source.stem, source).read_bytes()
        base = self.work / 'base.c'
        result = run(ROOT / 'scripts/bend.sh', source, '-o', base,
                     env={**ENV, 'BEND_REPO': ENV.get('BEND_BASE_REPO', str(ROOT / 'upstream/bend'))})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(generated, base.read_bytes())

    def test_dependent_equality_domain_keeps_generic_fallback(self):
        code = self.execute(SOURCE / 'callback_dependent.bend', '42')
        self.assertNotIn('FID_APPLY_CALLBACK', code)

    def test_known_callback_has_no_live_closure_segments(self):
        code = self.emit().read_text()
        # The runtime's generic apply case remains; user closure cases must disappear.
        closures = re.findall(r'WL_CASE\(FID_[A-Z0-9_]+_C\d+\)', code)
        self.assertEqual(closures, [])


if __name__ == '__main__':
    unittest.main()
