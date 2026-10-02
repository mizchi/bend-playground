import Base
# Immutable CNF, at most 32 variables. Bit i denotes DIMACS variable i+1.
# Repeated literals collapse in each mask; pos & neg marks a tautology.
type CNF is Data:
  End{}
  Clause{pos: U32, neg: U32, tail: CNF}

type Check is Data:
  Clear{}
  Clash{}
  Force{yes: U32, no: U32}
  Open{bit: U32}

type Propagation is Data:
  Failed{}
  Ready{model: U32}
  Split{yes: U32, no: U32, bit: U32}
  Overflow{}

type Answer is Data:
  Sat{model: U32, nodes: U32}
  Unsat{nodes: U32}
  Unknown{nodes: U32}

def inspect_open(+pos: U32, +remaining: U32, empty: Bool, unit: Bool) -> Check:
  match empty unit:
    case True{} _:
      Clash{}
    case False{} True{}:
      Force{(remaining .&. pos : U32), (remaining .&. U32.not(pos) : U32)}
    case False{} False{}:
      Open{(remaining .&. (0 - remaining) : U32)}

def inspect(+pos: U32, +neg: U32, +yes: U32, +no: U32, satisfied: Bool) -> Check:
  match satisfied:
    case True{}:
      Clear{}
    case False{}:
      +remaining = ((pos .|. neg) .&. U32.not((yes .|. no : U32)) : U32)
      inspect_open(pos, remaining, U32.is_zero(remaining),
        U32.is_zero((remaining .&. (remaining - 1) : U32)))

def finish_scan(+choice: U32, empty: Bool) -> Check:
  match empty:
    case True{}: Clear{}
    case False{}: Open{choice}

def scan_next(head: Check, +choice: U32, rest: U32 -> Check) -> Check:
  match head:
    case Clear{}: rest(choice)
    case Clash{}: Clash{}
    case Force{yes, no}: Force{yes, no}
    case Open{bit}: rest(Bool.pick(U32, U32.is_zero(choice), bit, choice))

def scan(cnf: CNF, +yes: U32, +no: U32, +choice: U32) -> Check:
  match cnf:
    case End{}:
      finish_scan(choice, U32.is_zero(choice))
    case Clause{+pos, +neg, tail}:
      head = inspect(pos, neg, yes, no,
        U32.is_ne(((pos .&. yes) .|. (neg .&. no) .|. (pos .&. neg) : U32), 0))
      scan_next(head, choice, c => scan(tail, yes, no, c))

# At most 32 previously unassigned variables are forced. The 33rd iteration
# inspects the final state. Exhaustion is an explicit error, never UNSAT.
def propagate(f: Nat, +cnf: CNF, +yes: U32, +no: U32, state: Check) -> Propagation:
  match f state:
    case 0n _: Overflow{}
    case 1n+p Clear{}: Ready{yes}
    case 1n+p Clash{}: Failed{}
    case 1n+p Open{bit}: Split{yes, no, bit}
    case 1n+p Force{y, n}:
      +yes2 = (yes .|. y : U32)
      +no2 = (no .|. n : U32)
      propagate(p, cnf, yes2, no2, scan(cnf, yes2, no2, 0))

def add_nodes(answer: Answer, extra: U32) -> Answer:
  match answer:
    case Sat{model, nodes}: Sat{model, U32.add(nodes, extra)}
    case Unsat{nodes}: Unsat{U32.add(nodes, extra)}
    case Unknown{nodes}: Unknown{U32.add(nodes, extra)}

# The alternative is a thunk: a successful first branch does not evaluate it.
def alternative(first: Answer, second: Unit -> Answer) -> Answer:
  match first:
    case Sat{model, nodes}: Sat{model, U32.inc(nodes)}
    case Unsat{nodes}: add_nodes(second(Unit{}), U32.inc(nodes))
    case Unknown{nodes}: Unknown{U32.inc(nodes)}

# Each decision assigns a new variable. 33 bounds depth, not total tree size.
# The branch rule is the lowest bit of the first unresolved clause, true first.
def search(+f: Nat, +cnf: CNF, state: Propagation) -> Answer:
  match f state:
    case 0n _: Unknown{1}
    case 1n+p Overflow{}: Unknown{1}
    case 1n+p Failed{}: Unsat{1}
    case 1n+p Ready{model}: Sat{model, 1}
    case 1n+p Split{+yes, +no, +bit}:
      +yes2 = (yes .|. bit : U32)
      +no2 = (no .|. bit : U32)
      first = search(p, cnf, propagate(33n, cnf, yes2, no, scan(cnf, yes2, no, 0)))
      alternative(first, u => search(p, cnf, propagate(33n, cnf, yes, no2, scan(cnf, yes, no2, 0))))

# Precondition: yes & no == 0, all bits are declared variables.
def solve(+cnf: CNF, +yes: U32, +no: U32) -> Answer:
  search(33n, cnf, propagate(33n, cnf, yes, no, scan(cnf, yes, no, 0)))

def merge(a: Answer, b: Answer) -> Answer:
  match a b:
    case Unknown{an} Sat{m, bn}: Unknown{U32.add(an, bn)}
    case Unknown{an} Unsat{bn}: Unknown{U32.add(an, bn)}
    case Unknown{an} Unknown{bn}: Unknown{U32.add(an, bn)}
    case Sat{m, an} Unknown{bn}: Unknown{U32.add(an, bn)}
    case Unsat{an} Unknown{bn}: Unknown{U32.add(an, bn)}
    case Sat{+am, an} Sat{+bm, bn}:
      Sat{Bool.pick(U32, U32.is_lt(am, bm), am, bm), U32.add(an, bn)}
    case Sat{m, an} Unsat{bn}: Sat{m, U32.add(an, bn)}
    case Unsat{an} Sat{m, bn}: Sat{m, U32.add(an, bn)}
    case Unsat{an} Unsat{bn}: Unsat{U32.add(an, bn)}

# All 2^depth prefixes are completed, including after a SAT prefix is found.
# This gives deterministic work and output without shared mutable cancellation.
def partitions(+d: Nat, +cnf: CNF, +i: U32, +mask: U32) -> Answer:
  match d:
    case 0n: solve(cnf, i, U32.xor(mask, i))
    case 1n+p:
      a b = partitions(p, cnf, i, mask) partitions(p, cnf, U32.add(i, U32.shln(1, p)), mask)
      merge(a, b)

# Contract: depth <= declared variables, depth <= 12.
def partition(+depth: Nat, cnf: CNF) -> Answer:
  partitions(depth, cnf, 0, U32.sub(U32.shln(1, depth), 1))

def holds(cnf: CNF, +model: U32) -> Bool:
  match cnf:
    case End{}: True{}
    case Clause{pos, neg, tail}:
      Bool.and(U32.is_ne(((pos .&. model) .|. (neg .&. U32.not(model)) : U32), 0), holds(tail, model))

def show(answer: Answer) -> String:
  match answer:
    case Sat{model, nodes}: "status=SAT model=" ++ U32.show(model) ++ " nodes=" ++ U32.show(nodes) ++ " errors=0"
    case Unsat{nodes}: "status=UNSAT model=0 nodes=" ++ U32.show(nodes) ++ " errors=0"
    case Unknown{nodes}: "status=UNKNOWN model=0 nodes=" ++ U32.show(nodes) ++ " errors=1"
