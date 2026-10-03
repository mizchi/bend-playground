"""Published comparisons must use clean, named compiler commits."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import bend_step02_refactor as reference


class ReferenceCheckoutTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        origin = self.root / 'origin'
        origin.mkdir()
        self.git(origin, 'init', '-q')
        self.git(origin, 'config', 'user.name', 'Test')
        self.git(origin, 'config', 'user.email', 'test@example.invalid')
        compiler = origin / 'bend2/comp.ts'
        compiler.parent.mkdir()
        self.refs = {}
        for lane in ('base', 'patched'):
            compiler.write_text(lane + '\n')
            self.git(origin, 'add', 'bend2/comp.ts')
            self.git(origin, 'commit', '-qm', lane)
            self.refs[lane] = dict(repository=str(origin),
                                  revision=self.git(origin, 'rev-parse', 'HEAD'),
                                  compiler_sha256=hashlib.sha256(compiler.read_bytes()).hexdigest())
        self.manifest = self.root / 'reference.json'
        self.manifest.write_text(json.dumps(self.refs))
        self.work = self.root / 'comparison'

    def git(self, repo, *args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()

    def test_fetches_distinct_commits_and_can_reuse_them(self):
        repos = reference.prepare(self.manifest, self.work)
        self.assertNotEqual(self.git(repos['base'], 'rev-parse', 'HEAD'),
                            self.git(repos['patched'], 'rev-parse', 'HEAD'))
        self.assertEqual(reference.prepare(self.manifest, self.work), repos)

    def test_preserves_and_rejects_dirty_checkout(self):
        repos = reference.prepare(self.manifest, self.work)
        compiler = repos['patched'] / 'bend2/comp.ts'
        compiler.write_text('local experiment\n')
        with self.assertRaisesRegex(RuntimeError, 'dirty'):
            reference.prepare(self.manifest, self.work)
        self.assertEqual(compiler.read_text(), 'local experiment\n')

    def test_rejects_other_revision(self):
        repos = reference.prepare(self.manifest, self.work)
        self.git(repos['base'], 'fetch', str(self.root / 'origin'), self.refs['patched']['revision'])
        self.git(repos['base'], 'checkout', '--detach', self.refs['patched']['revision'])
        with self.assertRaisesRegex(RuntimeError, 'revision'):
            reference.prepare(self.manifest, self.work)

    def test_rejects_wrong_compiler_hash(self):
        self.refs['patched']['compiler_sha256'] = '0' * 64
        self.manifest.write_text(json.dumps(self.refs))
        with self.assertRaisesRegex(RuntimeError, 'hash'):
            reference.prepare(self.manifest, self.work)


if __name__ == '__main__':
    unittest.main()
