# BACKFILL_RECONCILIATION — what became a registry entry, and what did not

**Written 2026-09-06 as the bound on the experiment-registry backfill.** The registry
(`experiments/*.yaml` + the generated `INDEX.md` / `index.json`) is meant to answer
"what has this project ever run, and what did it conclude" in one place. This file is
the audit trail of *which* sources were swept and what happened to each row — so a
later session can tell "not in the registry" apart from "deliberately not an entry".

Sources swept, in the order they were read:

| # | source | what it contributes |
|---|---|---|
| S1 | `experiments/*.yaml` (9 files) | the pre-existing authored registry |
| S2 | `Reports/FINDINGS_LEDGER_2026-09-03.docx` | 30 `Heading 1` sections, counted directly (the "~30" claim is confirmed, not assumed) |
| S3 | `WORKPLAN.md` MASTER BOARD → DONE table | the completed campaigns, incl. everything after the docx was generated |
| S4 | `CHATLOG.md` 2026-09-03 … 2026-09-06 | dates + file lists for the post-docx work |
| S5 | `Reports/*.md` | campaign reports the board points at, plus the pre-overhaul era |

Dispositions used:

- **exists-already** — already an `experiments/*.yaml`; the source is a *view* of it,
  recorded as a `reports:`/`extra:` pointer on that file, never as a second entry.
- **backfill** — became a new `experiments/*.yaml` with `retrospective: true`.
- **not-an-experiment** — machinery, ops, or documentation with no question and no
  measured answer of its own.
- **needs-kam** — backfilled, but the entry carries `status: needs-kam`: its result is
  documented and *not* signed off, or its primary output is not in the tracked record.

---

## A. The docx's 30 sections

The docx groups the Tier-1 sample into five arm-level sections plus a synthesis
section. Those six cannot become six registry entries: **tag ownership is exclusive**
(`test_experiments.py::test_every_tag_is_owned_by_one_experiment`), and all 28 `t1_*`
tags already belong to `tier1_science_sample.yaml`. They are sub-experiments of one
pre-registered design, so they map to that one file.

| # | docx section | disposition | registry name | kind |
|---|---|---|---|---|
| 1 | T1-A lidar as INPUT channel | exists-already | `tier1_science_sample` | experiment |
| 2 | T1-B lidar as label ADDER | exists-already | `tier1_science_sample` | experiment |
| 3 | T1-C the 4th (NIR) band | exists-already | `tier1_science_sample` | experiment |
| 4 | T1-D label-corruption dose-response | exists-already | `tier1_science_sample` | experiment |
| 5 | T1-E seed replicates / noise floor | exists-already | `tier1_science_sample` | experiment |
| 6 | EXP-A-ERA-MATCHED-RESCORE | **needs-kam** | `era_matched_rescore` | measurement-campaign |
| 7 | EXP-B-CCAP-MIXED-SIGN-BIAS | **needs-kam** | `ccap_mixed_sign_bias` | instrument-finding |
| 8 | pilot_2019 | exists-already | `pilot_2019` | experiment |
| 9 | resolution_1x2x4 | exists-already | `resolution_1x2x4` | experiment |
| 10 | hard_year_pilot | exists-already | `hard_year_pilot` | experiment |
| 11 | deeplab_arm | exists-already | `deeplab_arm` | experiment |
| 12 | degradation_synth_2000 | exists-already | `degradation_synth_2000` | experiment |
| 13 | full_archive_e3 | exists-already | `full_archive_e3` | experiment |
| 14 | RECIPE_AUDIT_2026-09-01 | backfill | `recipe_audit` | measurement-campaign |
| 15 | THRESHOLD_POLICY_C | backfill | `threshold_policy_c` | instrument-finding |
| 16 | RESCORE_2013_CITYWIDE | backfill | `rescore_2013_citywide` | instrument-finding |
| 17 | chm-roc-all-three | backfill | `chm_roc_all_three` | measurement-campaign |
| 18 | chm-roc-support-confound | backfill | `chm_roc_support_confound` | measurement-campaign |
| 19 | chm-standalone-prior-closure | backfill | `chm_standalone_prior_closure` | instrument-finding |
| 20 | fusion-5band-nir-chm | **needs-kam** | `fusion_5band_nir_chm` | measurement-campaign |
| 21 | old-chm-defect | backfill | `old_chm_defect` | instrument-finding |
| 22 | chm-encodings-and-year-assignment | backfill | `chm_encodings_year_assignment` | instrument-finding |
| 23 | chm-gap-2016 | backfill | `chm_gap_2016` | instrument-finding |
| 24 | accuracy-sample-design | backfill | `accuracy_sample_design` | measurement-campaign |
| 25 | tier1-lidar-input-closure | exists-already | `tier1_science_sample` | experiment |
| 26 | EXP-A-shadow-fp-fn-2016 | **needs-kam** | `shadow_fp_fn_2016` | measurement-campaign |
| 27 | EXP-B-leafoff-recall-gradient | backfill (superseded) | `leafoff_recall_gradient` | instrument-finding |
| 28 | EXP-C-stability-mining-closure | backfill | `stability_mining_closure` | measurement-campaign |
| 29 | EXP-D-coregistration-2020s-anchor | backfill | `coregistration_2020s_anchor` | measurement-campaign |
| 30 | EXP-E-2019-same-flight-pair | backfill | `same_flight_pair_2019` | instrument-finding |

**Count check:** 30 sections = 12 exists-already (6 Tier-1 views collapsing onto one
file + 6 sections that each mirror their own yaml) + 18 backfilled, of which 4 are
flagged needs-kam. Distinct existing yamls referenced: 7 of the 9.

The two existing yamls the docx never covers are `trend8_uniform_rgb` and
`overlap_floor` — both created after 2026-09-03. That is the docx's real staleness,
and it is the reason the registry is generated rather than re-issued as a document.

## B. The WORKPLAN MASTER BOARD → DONE table (post-docx work)

| board row | disposition | registry name | kind |
|---|---|---|---|
| Phase 0-3 + refactor + pilot slice | exists-already | `pilot_2019` | experiment |
| Policy-C threshold selection (recipe audit) | backfill (A.14/A.15) | `recipe_audit`, `threshold_policy_c` | — |
| Tier-1 science sample (28 arms) | exists-already | `tier1_science_sample` | experiment |
| Adversarial review + corrections | not-an-experiment | — | the docx itself; it is a `reports:` pointer on the entries it audits |
| Accuracy instruments: sampler repair, U1, E2, certified-flat, C1, C2/C2b, C3 | backfill (split 4 ways) | `accuracy_sample_design`, `certified_flat_scoring`, `metric_tolerance_c2b`, `sameflight_floor_c3` | — |
| Greenness gradient RESOLVED | backfill | `greenness_gradient_correction` | instrument-finding |
| Direction campaign / Panel A | backfill | `panel_a_direction` | measurement-campaign |
| Lidar leg revived (decimation null) | backfill | `lidar_decimation_null` | measurement-campaign |
| trend8 8-year map series + recalibration | exists-already | `trend8_uniform_rgb` | experiment |
| overlap_floor | exists-already | `overlap_floor` | experiment |
| Canopy DEFINITION review | backfill | `canopy_definition_review` | measurement-campaign |
| Literature: 4 papers read+reasoned | folded into `lit_hunt_temporal_inconsistency` | — | — |
| Overnight literature HUNT | backfill | `lit_hunt_temporal_inconsistency` | measurement-campaign |
| Change-detector design + adversarial review | backfill | `change_detector_design` | measurement-campaign |
| Flicker-program items 1, 2, 5, 6, 7 | items 2/5/7 = `overlap_floor` (exists-already); items 1+6 backfilled | `flicker_parcels_census` | measurement-campaign |

Also backfilled from S4/S5 because the board points at them but gives them no row of
their own:

| source | registry name | kind | why it is an entry |
|---|---|---|---|
| `Reports/EPOCH_DECAY_MVV0_2026-09-03.md` | `epoch_decay_mvv0` | instrument-finding | a pre-registered-style question (does CHM value decay with epoch distance) answered from tracked numbers; the KC/Shoreline re-open condition depends on it |
| `Reports/SECTOR_CAMPAIGN_REPORT_2026-08.md` | `sector_campaign_v1` | measurement-campaign | the pre-overhaul campaign that produced the `sectors_v1` arms `hard_year_pilot` was designed against; the champion-eligibility rule cites it |
| `Reports/M06_NIR_ARM.md` | `m06_nir_arm` | experiment | a real 2009 arm comparison with tracked PR-curve outputs; the earliest NIR evidence, superseded by Tier-1 T1-C |
| `phase4/qc/imagery_qc_*_2026-08-24.csv` + `qc/imagery_qc_suite.py` | `imagery_qc_suite_2026_08_24` | measurement-campaign | the archive-wide integrity/registration/radiometry sweep every later imagery claim rests on |
| `Reports/ARM_PR_CURVES_2009.md`, `CROWN_TOUCH_2009.md`, `phase4/qc/*_2009.md` | `arm_diagnostics_2009` | measurement-campaign | the 2009 diagnostic cluster (PR curves, bootstrap CI, region confusion, ensemble, seed floor) — one entry, many pointers |
| `Reports/DEGRADED_IMAGERY_RESEARCH_2026-08-27.md` | `degraded_imagery_lit_review` | measurement-campaign | the external literature review that produced the degradation-synthesis premise `degradation_synth_2000` tests |

## C. Deliberately NOT entries

| source | why not |
|---|---|
| `SEMANTIC_OVERHAUL_PLAN_2026-08-29.md`, `TIER1_SCIENCE_SAMPLE_PLAN_2026-09-02.md`, `WORKPLAN_2026-08-19.md` | plan documents. They are `design_doc:` pointers on the entries they planned, not entries. |
| `Reports/RECIPE_AUDIT_2026-09-01.md` as a *document* | the audit is entry `recipe_audit`; the file is its `reports:` pointer. One fact, one home. |
| `Reports/FINDINGS_LEDGER_2026-09-03.docx` | an audit *of* the registry's subject matter. It is cited by the entries it covers. |
| `Reports/Edmonds_Canopy_Brief.md`, `Edmonds_Report_Dossier.md`, `Edmonds_Verified_Results_2026-08-19.md`, `Measurement_Validity_Assessment_2026-08-18.md` | pre-overhaul narrative deliverables (EPOCH 0). Kam's 2026-08-30 decision was **do not backfill pre-EPOCH artifacts**; they restate numbers whose provenance predates the manifest/tag/registry era. |
| `Reports/CANOPY_DEFINITION_DECISION_2026-08.md` | an unsigned decision document (every checkbox `- [ ]`). It is the `design_doc:` of `ccap_mixed_sign_bias`, which carries `status: needs-kam` for exactly this reason. |
| `Reports/cost_per_arm.{csv,md}`, `gpu_launches.csv`, `inventory.csv` | operational accounting, not measurement. |
| `Reports/SECTOR_DESIGN_REVIEW_2026-08_lanes.txt`, `sector_campaign_design.md` | design inputs to `sector_campaign_v1`. |
| `Reports/edmonds_pipeline_overview.html`, `pipeline_architecture.html` | rendered views. |
| U1–U3, stages 0.x–3.x of the WORKPLAN board | machinery/refactor work. Real, tracked in git and CHATLOG; no hypothesis, no measured verdict. |

## D. Design forks recorded, conservative branch taken

1. **Sub-experiments vs. entries.** The docx's T1-A…T1-E read like five experiments.
   They share one pre-registered file, one sample, one noise floor, and one tag
   namespace. Making them five entries would have required splitting the arm list —
   which would silently rewrite what was pre-registered. Conservative branch: one
   entry, five `extra.docx_sections` pointers. If Kam wants arm-level rows, they
   belong in the *generated* layer (an arm view joined from `tier1_results.csv`),
   never in the authored one.
2. **`needs-kam` as a status, not a note.** Four docx sections document results that
   are explicitly not landed verdicts (pending K4 sign-off, or with the primary output
   in an untracked scratchpad). Rather than write a `verdict:` the record cannot
   support, those entries carry `status: needs-kam` and `verdict: null`, and the gate
   treats that status as undecided.
3. **Pre-overhaul (EPOCH 0/1) reports.** Included only where a campaign has tracked
   measured outputs still cited by live work (`sector_campaign_v1`, `m06_nir_arm`,
   `imagery_qc_suite_2026_08_24`, `arm_diagnostics_2009`). The narrative deliverables
   are excluded per Kam's do-not-backfill decision. **If Kam wants EPOCH-0 coverage,
   that is a decision, not an omission** — this row is the place it is recorded.

---

**Totals:** 9 pre-existing entries + 34 backfilled = 43 registry entries.
Backfilled = 18 (from the docx, §A) + 10 (new, from the board's DONE table, §B) +
6 (pointed at by the board but given no row of their own, §B second table).
Four backfilled entries carry `status: needs-kam`. Everything in §C is a deliberate
exclusion with a stated reason, not a gap.
