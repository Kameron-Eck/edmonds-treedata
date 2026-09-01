# qc/instruments/ — measurement scripts (the root CLAUDE.md is the full rulebook)

- **Instruments MEASURE; they never write to the data lake.** `qc/conftest.py` enforces
  that for pytest runs ONLY — a direct `py -3.12` run has no such guard, so read twice
  before adding any write outside the repo's `phase4/qc/` measured-text dir.
- **Anchors here are `parents[2]`** (instruments/ → qc/ → Scripts/). A copied header
  from a qc-root file is one level short.
- Sibling imports work when run directly (script dir is sys.path[0]); a file imported BY
  another needs its own self-dir insert — and every insert must be on the ledger in
  `test_status_discovery.py::test_path_insert_ledger` or the suite fails.
- The VM-exec'd files (`imagery_qc_suite.py`, `phase4_qc_indep.py`) live at qc/ ROOT,
  not here — kernel-exec'd by path; see their KERNEL-EXEC KEEP headers before moving
  anything they import.
- Measured outputs are harvested to `phase4/qc/` and committed; numbers in chat rot.
