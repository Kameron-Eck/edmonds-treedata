# experiments/ — one file per entry, the agent-facing contract

An entry here is a COMMITMENT: the question, how it will be judged, and — once judged —
the verdict. Rationale used to live in queue-yaml comments and the WORKPLAN board; an
agent picking up cold had to reconstruct intent from context. Now it reads one file and
knows what was done, why, what "done" means, and where the numbers live.

**Two layers.** This directory is the AUTHORED layer: pointers, never restated numbers.
`qc/experiments_index.py` is the GENERATED layer: it loads every file here, joins it
against the measured homes at build time, and emits [`INDEX.md`](INDEX.md) (scannable)
and [`index.json`](index.json) (machine). Restating a number is illegal here and legal
there, because there it is harvested rather than typed. Same rule as
`phase4/qc/acquisition_passport.csv`. Start at `INDEX.md`; come here to edit.

The backfill's audit trail — what was swept, and what deliberately did not become an
entry — is [`BACKFILL_RECONCILIATION.md`](BACKFILL_RECONCILIATION.md).

---

## Schema (enforced by `qc/test_experiments.py`)

```yaml
# ---- identity ----------------------------------------------------------------
name:        pilot_2019            # == filename stem
kind:        experiment            # experiment | measurement-campaign | instrument-finding
status:      complete              # queued | live | complete | tabled | needs-kam
retrospective: false               # true = written AFTER the fact (see below)

# ---- the science -------------------------------------------------------------
hypothesis:  one paragraph — what would change our mind
arms:                              # every (year, tag) the entry owns; [] for non-experiments
  - {year: "2019", tag: pilot_e2_fine}
baseline:    tag-or-null           # what the arms are compared against
metric:      where the judged numbers LIVE (pointer, never restated values)
decision_rule: what promotes/kills — written BEFORE results exist
verdict:     null until decided; then a paragraph with POINTERS to measured rows
decided:     null | YYYY-MM-DD

# ---- provenance (all optional; gated when present) ---------------------------
category:    machinery             # one word, for grouping in the index
tags:        [pilot, three-tier]   # free keywords, for searching
design_doc:  Scripts/SEMANTIC_OVERHAUL_PLAN_2026-08-29.md   # repo-relative
reports:     [Reports/RECIPE_AUDIT_2026-09-01.md]   # owning write-ups
instruments: [Scripts/qc/instruments/postproc_variant_score.py]   # what measured it
inputs:      [phase4/qc/science_sample_manifest.csv]
outputs:     [phase4/qc/qc_indep_report.csv]
run_ids:     [20260831T015830Z_2019s_pilot_e2_medium_postproc]
commit:      528c980
imagery:     ["2019", 2019s, 2019n]                 # config.YEAR_CATALOG labels
sample:      what the unit of analysis is, in words
n:           1250                                   # the ONE sanctioned restatement
n_source:    phase4/qc/panel_a_meta.json#json:n_live
supersedes:     [leafoff_recall_gradient]           # registry names, must resolve
superseded_by:  [greenness_gradient_correction]
extra:       {docx_sections: [T1-A, T1-B]}          # anything else, free map
```

### `kind:` — what an entry IS

The archive holds three shapes of work, and forcing them all into an arms table would
have meant inventing arms that never existed.

| kind | what it is | arms | may be launched |
|---|---|---|---|
| `experiment` | trained arms compared under a pre-registered rule | **required, non-empty** | yes |
| `measurement-campaign` | designed data collection with no (year, tag) arms — a human panel, a coregistration sweep, a literature hunt | `[]` | no |
| `instrument-finding` | one measured fact, correction, or decision record | `[]` (or arms, if it owns some) | no |

`kind` defaults to `experiment` when absent, so the pre-existing files keep validating.
`qc/experiment_queue.py` refuses anything that is not `kind: experiment` — a campaign
has nothing to launch — and `qc/pilot_gate.py` refuses an entry with no arms rather
than reporting a vacuous pass.

### `status: needs-kam`

A result that is measured and written down but **not signed off**, or whose primary
output never reached the tracked record. `verdict:` stays `null` — writing a verdict
the record cannot support is the failure mode this status exists to prevent. Treated as
undecided by the gate, exactly like `queued`.

### `retrospective:` — the anti-fabrication flag

`decision_rule` is written at CREATION, before results — that is the point of this
directory. A backfilled entry inverts that: the rule is reconstructed from a verdict
that already exists. Recording such a rule silently would fabricate pre-registration.

So: **if an entry's `decided:` date is earlier than the date its file was first
committed, `retrospective: true` is required** (gated via `git log --diff-filter=A`).
On a retrospective entry, `decision_rule` describes the rule the work was actually
judged by, sourced from the write-up — it is a reconstruction, and the flag says so.

### `n:` / `n_source:` — the one legal number

Sample size is the single value allowed in the authored layer, because a pointer alone
("N is in the manifest") fails the question everyone actually asks. It is safe only
because it is PINNED: the gate resolves `n_source` and fails if it disagrees with `n`.
Both or neither.

`n_source` grammar (resolver: `qc/test_experiments.py::resolve_n`):

| form | means |
|---|---|
| `path#rows` | data rows in a CSV (header and `#` comment lines excluded) |
| `path#rows:col=val` | data rows where column `col` equals `val` |
| `path#json:key` | a top-level integer key in a JSON file |
| `path#lines` | non-blank, non-`#` lines in a text file |

### Pointer fields

`design_doc`, `reports`, `instruments`, `inputs`, `outputs` hold **repo-relative** paths
(from the repo root, so `Scripts/...` or `phase4/qc/...`; a bare name resolves under
`Scripts/`). The gate checks every one exists. Lake paths (`G:\...`, `/content/...`) and
glob patterns are legitimate provenance but are **not** existence-checked — CI has no
lake mounted.

`instruments:` is CLAUDE.md 3.4b made machine-readable: instrument in
`qc/instruments/` → measured CSV in `phase4/qc/` → gated finding. An entry that names
no instrument and no output is a restatement, not a measurement.

`run_ids` name the `run_registry.csv` rows that produced the entry's DELIVERABLES —
normally the terminal step per arm, not every step. `imagery` uses
`config.YEAR_CATALOG` labels; the gate rejects a label the catalog does not hold.
`supersedes` / `superseded_by` name other entries by registry name, and must resolve.

---

## Rules

- **Numbers are never restated here.** `metric` is a POINTER — it names where the
  judged values live (`qc_indep_report.csv` rows, registry rows, a `Reports/` file),
  never a value. `verdict` states the READ — confirmed / not confirmed / undetermined /
  the direction — and may carry the decisive figure **only in a sentence that names the
  file it was read from**, which is what the nine pre-existing verdicts already do.
  Anything beyond the decisive figure belongs in the measured home and reaches the
  reader through the generated index, which resolves it at build time. The one
  unconditionally legal number is the gated `n`/`n_source` pair.
- A `complete` **experiment**'s arm tags must appear in `run_registry.csv` (gated) —
  a finished experiment leaves provenance.
- Every tag is owned by exactly one entry (gated). A sub-experiment of a
  pre-registered design does NOT get its own file; it gets a pointer in `extra:`.
- `decision_rule` is written at CREATION, before results — unless `retrospective`.
- Gate one entry against the lake:
  `py -3.12 qc/pilot_gate.py --experiment experiments/<name>.yaml`
- **Launching**: arms may carry `extra: [--flag, ...]` and the entry may carry
  `launch_defaults: [...]` (applied to every arm, arm flags win).
  `py -3.12 qc/experiment_queue.py --experiment experiments/<name>.yaml` writes the
  queue yaml FROM the entry — never hand-write one; a gate regenerates every
  GENERATED-headered queue file and fails on drift.
- **Regenerate the index after any edit here**:
  `py -3.12 qc/experiments_index.py` — `test_experiments.py::test_index_is_fresh`
  fails on drift, same pattern as the generated queue files.
