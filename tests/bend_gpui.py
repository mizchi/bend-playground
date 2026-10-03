"""Consume the GPUI package outside the playground, with no demo dependencies."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'packages/bend-gpui'


class BendGpuiLibraryTest(unittest.TestCase):
    def test_external_app_with_a_vendored_package(self):
        with tempfile.TemporaryDirectory(prefix='bend gpui consumer ') as temporary:
            project = Path(temporary)
            package = project / 'vendor/bend-gpui'
            shutil.copytree(PACKAGE, package, ignore=shutil.ignore_patterns('__pycache__', 'target'))
            source = project / 'main.bend'
            source.write_text('''import Base
import ./vendor/bend-gpui/bend/api.bend as UI

def draw(tick: UI.Tick) -> UI.Frame:
  match tick:
    case UI.Tick{width, height, frame}:
      UI.pixels(width, height, 4281558681)

def main() -> IO(Unit):
  UI.run(32, 16, 3, tick => draw!(tick))
''')
            result = subprocess.run([
                'python3', str(package / 'build.py'), str(source),
                '--output', str(project / 'output app'),
                '--bend-command', str(ROOT / 'scripts/bend.sh'),
                '--target-dir', str(ROOT / 'build/gpui/target'),
            ], cwd=project, text=True, capture_output=True, timeout=180)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            binary = project / 'output app/BendGPUI.app/Contents/MacOS/bend-gpui'
            self.assertTrue(binary.is_file())
            self.assertTrue(Path(str(binary) + '.gpu').is_file())
            import sys
            sys.path.insert(0, str(ROOT / 'scripts'))
            import gpui
            for gpu in (False, True):
                rows = gpui.run(binary, gpu=gpu, width=32, height=16,
                                frames=3, headless=True)
                self.assertEqual([r['frame'] for r in rows], [0, 1, 2])
                self.assertTrue(all(r['cpu_payload_read_bytes'] == 0 for r in rows))
            self.assertNotIn('grid.c', (project / 'output app/bend.c').read_text())

    def test_capacity_covers_supported_sizes(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as temporary:
            project = Path(temporary)
            relative = Path(os.path.relpath(PACKAGE / 'bend/api.bend', project))
            source = project / 'capacity.bend'
            values = (0, 1, 2, 512, 513, 4194304)
            calls = ' ++ " " ++ '.join(f'Nat.show(UI.capacity({n}))' for n in values)
            source.write_text(f'import Base\nimport ./{relative} as UI\n'
                              f'def main() -> String:\n  {calls}\n')
            result = subprocess.run([str(ROOT / 'scripts/bend.sh'), str(source)],
                                    text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.strip(), '"0 0 1 9 10 22"')

    def test_build_rejects_invalid_executable_names_without_invoking_tools(self):
        spec = importlib.util.spec_from_file_location('bend_gpui_package', PACKAGE / 'build.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            source = project / 'main.bend'
            source.write_text('import Base\ndef main() -> U32:\n  42\n')
            with self.assertRaises(ValueError):
                module.build(source, project / 'output', name='../escape')
            self.assertFalse((project / 'output').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
