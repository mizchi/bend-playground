import Base
# Intentionally fails. 03-bend-wall.md (a): an @unsafe loop proves a false
# law. On 2.0.23 the check printed "All terms check, but 2 defs rely on
# unsafe or foreign code" and exited 0; on 2.0.34 it prints SOME PROOFS
# FAIL, lists the same two defs and exits 1. Do not make it pass.

@unsafe
def loop(-A: Type) -> A:
  loop(A)

law anything:
  for x: Nat
  {Nat.add(x, 1n) == x : Nat}

def anything(x):
  loop({Nat.add(x, 1n) == x : Nat})
