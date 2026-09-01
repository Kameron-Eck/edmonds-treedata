# experiments/ — one file per experiment, the agent-facing contract

An experiment here is a COMMITMENT: hypothesis, arms, how it will be judged, and —
once judged — the verdict. Rationale used to live in queue-yaml comments and the
WORKPLAN board; an agent picking up cold had to reconstruct intent from context.
Now it reads one file and knows what is running, why, what "done" means, and where
to write the verdict.

Schema (enforced by `qc/test_experiments.py`):

```yaml
name:        pilot_2019            # == filename stem
status:      queued | live | complete | tabled
hypothesis:  one paragraph — what would change our mind
arms:                              # every (year, tag) the experiment owns
  - {year: "2019", tag: pilot_e2_fine}
baseline:    tag-or-null           # what the arms are compared against
metric:      where the judged numbers LIVE (pointer, never restated values)
decision_rule: what promotes/kills — written BEFORE results exist
verdict:     null until decided; then a paragraph with POINTERS to measured rows
decided:     null | YYYY-MM-DD
```

Rules:
- **Numbers are never restated here** — `metric`/`verdict` point at
  `qc_indep_report.csv` rows, registry rows, or a Reports/ file (one fact, one home).
- A `complete` experiment's arm tags must appear in `run_registry.csv` (gated).
- `decision_rule` is written at CREATION, before results — that is the point.
- Gate any experiment against the lake with
  `py -3.12 qc/pilot_gate.py --experiment experiments/<name>.yaml`.
- **Launching**: arms may carry `extra: [--flag, ...]` and the experiment may carry
  `launch_defaults: [...]` (applied to every arm, arm flags win).
  `py -3.12 qc/experiment_queue.py --experiment experiments/<name>.yaml` writes the
  queue yaml FROM the experiment — never hand-write one; a gate regenerates every
  GENERATED-headered queue file and fails on drift.
