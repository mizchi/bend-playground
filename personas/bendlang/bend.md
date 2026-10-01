# bendlang/bend

<!-- measured:begin -->
Measured by hand on 2026-10-01 from a git clone at main @ 7d24b8d0 (the
skill's measure.ts needs an authenticated `gh`, which this session lacked:
the PR/issue numbers below come from commit subjects and CHANGELOG.md, not
from the GitHub API, so first-time-author outcomes and review latency are
NOT measured).

- context: oss, first-time (no merged PR by mizchi), public
- language: en (issues and PRs; every commit, template and CHANGELOG line)
- commits on main since 2026-09-15: 460, of which 78 carry `(#N)`; subject
  length median 62 chars, p90 141. Subjects are one declarative English
  sentence stating the new behaviour ("U32.to_nat widens to u64 in C, so Nat
  arithmetic on a u32 local no longer wraps at 2^32 (#1142)"), no
  `fix:`/`feat:` prefix, issue numbers in parentheses at the end.
- authors on main since 2026-08-01: Victor Taelin 604 (+ aliases), Nicolas
  Abril 38, Paulo Cavalcanti 13, Lorenzo Battistela 13, aldeni 7, others.
- CHANGELOG credits outside PRs as `(PR #N by login)`: nicolas-abril 4,
  aldeni 4, oxura 3, vicmcorrea 2, Giulio2002 2, six others 1 each.
- Co-authored-by trailers since 2026-09-01: Claude models 83, humans ~20.
  AI-assisted commits are the norm.
- issue templates: blank issues disabled (`config.yml`), so `bug.yml` is
  mandatory: What you did (command), What happened (output), The file,
  `bend --version`, `uname -sm`, clang first line. Questions go to Discord.
- PR template: none. CODEOWNERS: none. CONTRIBUTING: none; AGENTS.md is the
  contributor guide.
- gates (AGENTS.md, gates/): test.ts (every tests/**.bend through check,
  interpreter, C, JS), perf.ts (benches vs pins), repo.ts (file allow list
  and permanent ttok caps: comp.ts 64k ...), safe.ts. They run on the
  maintainers' Mac mini cluster, not in GitHub Actions (`.github/` holds only
  issue templates).
<!-- measured:end -->

## 1. Readers

- Victor Taelin writes almost all of `bend2/` and owns the caps in
  gates/repo.ts ("only Taelin changes them").
- Nicolas Abril (nicolas-abril) lands most outside-looking compiler and
  kernel fixes in comp.ts and safe.ts; the borrow inference
  (9015fe19) and spin/array fixes (ef66a7cc) went through this lane.
- AGENTS.md: "bend2/bend.ts ... is human-written: do not edit it". comp.ts
  may be edited.

## 2. Vocabulary usable bare

From comp.ts comments, tests/reg headers and CHANGELOG: spin (a flat def
emitted as a C function, `spin_N`), fused call / flat call, lend / lent,
borrow / borrowed parameter, twin (one value passed twice in one call),
keep / `term_keep`, sink / `term_sink`, `bind_dead`, self-jump, "the jump
runs no bind_dead", regression witness, RSS, `--threads 1`, `--gpu off`.

## 3. Needs translating

| ours | theirs |
|---|---|
| leak / not freed | "leaves ... cells", "leaked the cell", RSS grows (both used) |
| tail-recursive accumulator | a spin (flat loop) |
| shared list passed twice | one value twice in one call (a twin) |
| missing decrement | the lent copy is never sunk |

## 4. Issue conventions

- Bug form fields only; the maintainers' own issues are not visible here
  (no API). Repro file inline in "The file" when small.

## 5. PR conventions

- One fix + one test under tests/<ns>/ whose header comment says what the
  test witnesses and what went wrong before (tests/reg/borrow_spin_sink.bend,
  tests/compile/u32_to_nat_widen.bend from Giulio2002's c97ebd53).
- A test ends in `#|` lines with the expected stdout; the gate compares four
  lanes. RSS is not checked by test.ts; leak witnesses
  (tests/reg/closure_value_owns.bend) pin the answer and describe the RSS
  in the header.
- Commit subject: the declarative sentence of §measured, `(#issue)` at the
  end. Squash-merged under the maintainer's name or the author's.

## 6. Landmines

- Raising a ttok cap; editing bend.ts; adding files outside the allow list
  (tests must match `tests/[a-z]+/[a-z0-9_]+.bend`).
- WONTFIX.txt lists design choices (lazy pure main, clang only, no CSE ...);
  read before filing.
- gcc is not a target: report clang versions.

## 7. Evidence and weak spots

- Not measured: first-time PR outcomes, closed-by-automation share, review
  latency, open-issue duplicates (no API access in this session). Duplicate
  search covered only open PR heads fetched by git (`refs/pull/*/head`).
- Commands: git log/show on main @ 7d24b8d0; grep of CHANGELOG.md, AGENTS.md,
  gates/repo.ts, tests/reg/*.bend.
