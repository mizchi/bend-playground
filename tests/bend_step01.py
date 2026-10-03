"""Regression contracts for step 1; use BEND_REPO to select the compiler."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "compiler-patches/step-01-ffi-runtime-ids"
REPO = Path(os.environ.get("BEND_REPO", ROOT / "upstream/bend")).resolve()
BASE_REPO = Path(os.environ.get("BEND_BASE_REPO", ROOT / "upstream/bend")).resolve()
ENV = {**os.environ, "BEND_REPO": str(REPO), "BEND_NO_TELEMETRY": "1"}


def run(*args):
    return subprocess.run([str(arg) for arg in args], env=ENV, text=True,
                          capture_output=True, timeout=60)


class RuntimeIdsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.work = Path(self.directory.name)
        for source in SOURCE.glob("foreign_runtime_*.*"):
            shutil.copyfile(source, self.work / source.name)

    def compile_run(self, source, expected="42"):
        binary = self.work / source.stem
        generated = self.work / (source.stem + ".generated.c")
        result = run(ROOT / "scripts/bend.sh", source, "-o", generated)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = run(os.environ.get("CC", "clang"), "-std=c11", "-O3",
                     "-pthread", generated, "-lm", "-o", binary)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for threads in (1, 4):
            result = run(binary, "--threads", threads, "--gpu", "off")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.strip(), expected)

    def test_foreign_closure_without_bend_dynamic_application(self):
        self.compile_run(self.work / "foreign_runtime_apply.bend")

    def test_foreign_emit_without_bend_declaration(self):
        self.compile_run(self.work / "foreign_runtime_emit.bend")

    def test_javascript_twins_and_interpreter_match_native_effects(self):
        for name in ("apply", "emit"):
            with self.subTest(segment=name):
                source = self.work / ("foreign_runtime_" + name + ".bend")
                generated = self.work / (name + ".generated.js")
                result = run(ROOT / "scripts/bend.sh", source, "-o", generated)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                for command in (("bun", generated), (ROOT / "scripts/bend.sh", source)):
                    result = run(*command)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(result.stdout.strip(), "42")

    def test_namespaced_effects_fall_back_to_runtime_ids(self):
        source = self.work / "namespaced.bend"
        for name, call in (("apply", "N.native.apply(x => (x + 2 : U32), 40)"),
                           ("emit", "N.native.emit(42)")):
            with self.subTest(segment=name):
                source.write_text(f'''import Base
import ./foreign_runtime_{name}.bend as N

def main() -> IO(Unit):
  {call}
''')
                self.compile_run(source)

    def test_macro_name_collisions_preserve_symbolic_runtime_ids(self):
        source = self.work / "foreign_runtime_apply.bend"
        source.write_text(source.read_text().replace("def main()", '''def Clo_apply(x: U32) -> U32:
  (x + 1 : U32)

def IO_emit(x: U32) -> U32:
  (x + 1 : U32)

def main()''').replace("x => (x + 2 : U32)", "x => IO_emit(Clo_apply(x))"))
        self.compile_run(source)

    def test_unknown_ids_still_fail(self):
        source = self.work / "foreign_runtime_apply.bend"
        effect = self.work / "foreign_runtime_apply.c"
        original = effect.read_text()
        for token in ("FID(Missing~segment)", "CID(Missing~segment)",
                      "CID(Clo~apply)", "CID(IO~emit)"):
            with self.subTest(token=token):
                effect.write_text(original.replace("FID(Clo~apply)", token))
                result = run(ROOT / "scripts/bend.sh", source, "-o", self.work / "invalid.c")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(token + " names no constructor or def",
                              result.stdout + result.stderr)

    def test_c_compilation_resets_ids_after_c_and_js_compilation(self):
        result = run("bun", SOURCE / "compile-repeat.ts", REPO,
                     self.work / "foreign_runtime_apply.bend",
                     REPO / "tests/io/effect_cid_in_comment.bend")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {
            "same_book_equal": True, "c_after_js_equal": True,
            "fresh_book_equal": True, "js_generated": True})

    def test_comment_and_string_literals_keep_existing_behavior(self):
        self.compile_run(REPO / "tests/io/effect_cid_in_comment.bend")
        effect = self.work / "foreign_runtime_apply.c"
        effect.write_text(effect.read_text() + '''
// FID(Missing~segment)
/* CID(Missing~segment) */
static const char* quoted_id = "FID(Missing~segment)";
''')
        self.compile_run(self.work / "foreign_runtime_apply.bend")

    def test_existing_programs_keep_byte_identical_c_codegen(self):
        for source in (ROOT / "examples/particles").iterdir():
            if source.suffix in (".bend", ".c"):
                shutil.copyfile(source, self.work / source.name)
        # Resolve constructors in the effect's own namespace on both revisions.
        native = self.work / "native.c"
        native.write_text(native.read_text().replace("CID(api.", "CID("))
        particle = self.work / "particles.bend"
        particle.write_text('''import Base
import ./api.bend as UI
import ./simulation-flat.bend as Sim

def main() -> IO(Unit):
  UI.run(960, 540, 100000, 0, tick => state =>
    Sim.update!(tick, state, 14n, 63n, 64n, True{}))
''')
        programs = [ROOT / "examples/ffi" / (name + ".bend")
                    for name in ("pure", "io-pure", "foreign")] + [particle]
        for source in programs:
            with self.subTest(program=source.stem):
                outputs = []
                for lane, repo in (("fixed", BASE_REPO), ("selected", REPO)):
                    generated = self.work / (source.stem + "." + lane + ".c")
                    result = subprocess.run(
                        [str(ROOT / "scripts/bend.sh"), str(source), "-o", str(generated)],
                        env={**ENV, "BEND_REPO": str(repo)}, text=True,
                        capture_output=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    outputs.append(generated.read_bytes())
                self.assertEqual(outputs[0], outputs[1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
