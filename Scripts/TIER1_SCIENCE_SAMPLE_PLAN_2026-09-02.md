# Tier 1 — the science sample plan

*2026-09-02. Kam's direction after declining the full 36-run: "groups of high
priority runs that will tell us a lot of info" on "a sub sample of the full
imagery … representative … appropriate for training and validation", testing
lidar as label context, lidar as input, and the 4th band — "creating a rocket
for the moon", integrated into the repo, not decoration.*

**The run matrix, decision rules, kill rules, and metrics are PRE-REGISTERED in
`experiments/tier1_science_sample.yaml` — that file is the science contract and
this plan never restates its numbers.** This document holds the design
rationale, the phases, and where every artifact lands. Tier 2 (trend spine) and
Tier 3 (fill-in) wait; `experiments/full_archive_e3.yaml` stays queued as their
eventual vehicle and inherits whatever recipe Tier 1 settles.

## Why a sample, and what kind

Postproc is free to redo (masks re-derive from prob rasters); **labels and
input bands are not** — they invalidate trained models. So the open
training-side questions get answered on a small fixed sample before any
full-archive spend. Design principles, each with its mechanism:

1. **One geographic sample, every year, every arm** — fixed ground blocks
   projected into each acquisition's grid. All comparisons become PAIRED
   differences on identical ground; pairing is the variance reducer that lets a
   small sample resolve small effects.
2. **Three-way spatial split, fixed forever**: train blocks / selection blocks
   (early stop + the policy-C threshold sweep) / test blocks (final scores
   only). Selecting the threshold and scoring on the same cells would tune the
   knob on its own scorer — the split prevents it.
3. **Measured noise floor**: seed replicates of one baseline cell. Every arm
   delta is judged against that measured spread; below it → UNDETERMINED by
   pre-registration, never a win.
4. **Free kill-tests before GPU**: the CHM additions builders run first and the
   contradiction-rate instrument measures how much label each lidar epoch can
   actually change per year. Arms below the floor are struck before launch.
5. **Curve-matched comparisons**: primary statistic recall @ precision 0.75
   read from each arm's dense sweep on test blocks — immune to calibration
   differences that flip single-point rankings.
6. **Screened stratification**: blocks stratified across the canopy gradient
   (forest / residential / hard negatives), screened for CHM coverage in BOTH
   lidar epochs (2016 has known gaps), coregistration-quiet ground
   (median < 0.5 m), and radiometric representativeness (block DN quantiles ≈
   citywide quantiles, per band per year). Radiometric NORMALIZATION stays out
   of the matrix — the degradation-synthesis workstream owns it.
7. **Label-corruption dose curve**: seeded, crown-structured flips at known
   rates in clearly-tagged tile sets (the engine and the ADD-ONLY rule for
   real labels are untouched). The dose–response slope converts label-arm
   deltas into "equivalent % label error removed" — the calibration that makes
   the label axis interpretable.
8. **NIR replicated on two sensors** (2016 RGBI, 2019n NAIP) so the band
   answer is not a one-sensor story.
9. **The sample is permanent**: the same blocks later host the
   photo-interpretation accuracy campaign. Nothing here is single-use.

## Phases

**Phase 0 — free (local + CPU VMs).** Build and gate the machinery; run the
free measurements that can kill arms or invalidate the sample:
- `pipeline/builders/build_science_sample.py` → block GPKG + manifest
  (lake `phase4/qc/`), all screens applied, sized by
  `qc/instruments/phase4_qc_design_power.py`, split recorded per block.
- `pipeline/builders/build_chm_additions.py` (per lidar epoch, ADD-ONLY
  codes) + contradiction-rate instrument → measured CSV (the kill-test).
- `pipeline/builders/build_corrupted_tiles.py` (seeded doses, tagged dirs).
- Sample-vs-city calibration: score the EXISTING citywide prob rasters on the
  sample blocks; the sample must rank known arms the way the city does.
- Resolve the open picks (2020 vs 2020s per measured facts; block size/count
  per the power instrument) and record them in the experiment yaml before
  launch.

**Phase A — free (CPU VMs, parallel).** Labels + tiling for every cell into
tagged tile dirs. Every torch-free step happens OFF the GPUs.

**Phase B — the only GPU spend (2×A100, gate ask before launch).** Two
balanced queues running ONLY train/evaluate/inference; babysitter on both.
Utilization is a REPORTED MEASUREMENT (registry step-hours ÷ session
wall-hours), target ≥ 0.85 — achieved by the pre-staging, not promised.
Estimate: ~28 runs × 20–30 min ≈ 11–13 A100-hr ≈ ~6 wall-clock hours on the
pair (~100–115 CU).

**Phase C — free.** Dense sweeps + policy-C selection on selection blocks,
final scores on test blocks, paired deltas vs the noise floor, verdicts into
the experiment yaml, results CSV harvested, WORKPLAN/CHATLOG updated.

## Repo citizenship

Builders in `pipeline/builders/`, instruments in `qc/instruments/`, contracts
for every new CSV in `docs/SCHEMAS.md`, gates in the suite (strata/screen
integrity, ADD-ONLY compliance of additions, corruption confined to tagged
dirs), verdicts in the experiment file, sequence in CHATLOG. Anything that
would outlive its usefulness goes to scratch and the archive branch, not the
tree.
