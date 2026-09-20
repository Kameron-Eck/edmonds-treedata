# fixture — a minimal work plan that grades itself

This file is the GOOD input for `qc/instruments/litkb_acceptance.py plan`. Every known-bad in
qc/test_litkb_acceptance.py is a one-edit mutation of it, made in a tmp_path copy, so the
mutation is the only difference between passing and failing.

A ruling is an id: `litkb-fixture-one` resolves in the fixture registry beside this file.

---

## The ladder

### S0 — First session

Work
- (a) a bullet under Work, which must NOT satisfy the done-state
- (b) another one
- build the thing

Done-state
- (a) a tracked artifact
- (b) a command that prints counters
- (c) a known-bad input the new gate REJECTS

### S1 — Second session

Work
- the second thing, ruled by `litkb-fixture-two`

Done-state
- (a) an artifact
- (b) a command
  wrapping onto an indented continuation line that is not a bullet
- (c) the known-bad this session's gate refuses

---

## A section that is not a session

Nothing here is graded.

<!-- drift-gate:dated-begin -->
## Appendix — a dated record, not a current claim

`litkb-dated-only` is cited here and is deliberately absent from the fixture registry: ids inside
the dated region are not checked.
<!-- drift-gate:dated-end -->
