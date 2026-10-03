"""Reuse the original contracts, including capture liveness and fuel exhaustion."""
import unittest
import re
from bend_step02 import CallbackTest, SOURCE


class RefactoredCallbackTest(CallbackTest):
    def test_capture_used_twice_then_reused_by_caller(self):
        self.execute(SOURCE / 'refactored/callback_twice.bend', '42')

    def test_fuel_exhaustion_keeps_generic_calls_executable(self):
        source = self.work / 'fuel.bend'
        lines = ['import Base',
                 'def apply(x: U32, callback: U32 -> U32) -> U32:', '  callback(x)',
                 'def loop(x: U32) -> U32:']
        for i in range(600):
            previous = 'x' if i == 0 else f'a{i-1}'
            lines.append(f'  a{i} = apply({previous}, y => U32.inc(y))')
        lines.extend(['  a599', 'def main() -> U32:', '  loop(1)', '#| 601'])
        source.write_text('\n'.join(lines) + '\n')
        code = self.execute(source, '601')
        self.assertTrue(re.search(r'WL_CASE\(FID_[A-Z0-9_]+_C\d+\)', code),
                        'fuel exhaustion must retain a generic closure')

    def test_two_literal_callbacks_keep_generic_fallback(self):
        source = self.work / 'two_callbacks.bend'
        source.write_text('''import Base
def pipe(x: U32, f: U32 -> U32, g: U32 -> U32) -> U32:
  g(f(x))
def main() -> U32:
  pipe(39, x => U32.inc(x), x => U32.add(x, 2))
#| 42
''')
        code = self.execute(source, '42')
        self.assertTrue(re.search(r'WL_CASE\(FID_[A-Z0-9_]+_C\d+\)', code))

    def test_nested_nonflat_call_returns_to_its_caller(self):
        source = self.work / 'nonflat.bend'
        source.write_text('''import Base
@unsafe
def left(n: Nat, x: U32) -> U32:
  match n:
    case 0n: x
    case 1n+p: right(p, U32.inc(x))
@unsafe
def right(n: Nat, x: U32) -> U32:
  match n:
    case 0n: x
    case 1n+p: left(p, U32.inc(x))
def apply(x: U32, callback: U32 -> U32) -> U32:
  callback(left(2n, x))
def run(x: U32) -> U32:
  y = apply(x, v => U32.inc(v))
  U32.inc(y)
def main() -> U32:
  run(38)
#| 42
''')
        self.execute(source, '42')


if __name__ == '__main__':
    unittest.main(defaultTest='RefactoredCallbackTest')
