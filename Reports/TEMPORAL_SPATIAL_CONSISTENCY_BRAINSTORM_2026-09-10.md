# Temporal and spatial consistency — brainstorming brief (source of truth)

**Status: BRAINSTORM. Nothing in §4–§8 is validated. Every number in §2 is read from a
tracked file and cited; everything else is labelled inferred or proposed.** Written
2026-09-10 from the Kam / Claude discussion after the crown state model v2 verdict.
Owner: Kam. This file is the one home for the ideas; designs that graduate from it get
their own pre-registration under `experiments/` and are linked back here.

---

## 1. The problem in one paragraph

Twelve canopy masks (2009–2024) come from twelve surveys that see differently: resolution
7.5–80 cm effective, February–October flights, one RGB/NIR mix per year, and every label
projected from a single April–July 2020 flight. Read naively as a series, survey
differences masquerade as tree change. Every shortcut tried so far that hides the
difference has laundered real change into fake agreement (§2.2, §2.3). The goal is a
layer that reasons over time AND space with each survey's measured eyesight, so that a
tree on a roof in one year is removed, a tree missed in shadow in one year is kept, a
real clearing stays a clearing, and every assertion carries the uncertainty it earned.

## 2. What is MEASURED (tracked files; the constraints any design inherits)

### 2.1 The healer on twelve epochs (`experiments/heal_infill_2017_2023.yaml`, reads_12ep)
- BLIND brackets inside 2016–2024: 0. Tier mix 3 HEAL / 7 REVIEW / 0 BLIND
  (`phase4/qc/temporal_heal_12ep.csv`).
- `temporal_heal.py::tier_for` grants HEAL only when the bracket ends ≤ 2016 (a lidar epoch
  downstream). Post-2016 the healer writes IGNORE only: it never asserts canopy where the
  human gold lives. Not a defect; the design as built.
- Withheld (REVIEW) cells are concentrated in 2020 (404,413 cells, 6.6 pp of city), 2017
  (204,563, 3.3 pp), 2023 (90,155, 1.5 pp). The 2017 and 2020 masks sit on a probability
  cliff (arm_notes); 2023 King misses canopy both neighbours see. Calibration, not
  ecology, is the first suspect. A reading of counts, not a measured cause.
- No-change impossible triples fixed: 240 of 327 (149 by IGNORE, 58 by canopy);
  laundered 0/42 with at-risk = 0 in every gap bucket, a criterion with NO POWER for
  any both-sides rule at this cadence (`heal_gap_spectrum_12ep.csv`).
- Alignment: every measured inter-epoch shift is < 1 m and rounds to zero cells at 2 m;
  `shift_mask` is a no-op on this stack.

### 2.2 Harmonization H1/H2 (`experiments/harmonization_h1_h2.yaml`, decided)
- H1: five-year base spread of matched_p75 recall on ResNet-18 = 0.140 (vs C-CAP 2021) /
  0.154 (vs C-CAP 2016); not reference-epoch distance. 2019n is the worst survey (0.603),
  not 2006s.
- H2 KILLED: a 2016 lidar structure channel as INPUT converges the spread (−0.084 /
  −0.119) by importing 2016 canopy into older surveys. H2-K1 leak fires on both
  references (0.043 / 0.019 > floor 0.0069); H2-K2 change laundering fires every year:
  on lidar-certified 2005→2016 GAIN cells the in16 arm's call rate rises +0.035…+0.082
  more than on all cells (`phase4/qc/harm_change_laundering.csv`); the same-flight gap
  is unchanged. A fixed-epoch input is a time-stamped prior, not a harmonizer.
- The K2 instrument holds lidar-certified populations on the sample blocks: 46,805 GAIN
  cells and 40,609 FLAT cells (2005→2016). These are a reusable kill denominator.

### 2.3 Crown state model v1 / v2 (`experiments/crown_state_model*.yaml`, both decided)
- Unit = 2020 crown polygons. 726 of 1,214 Panel A gold points (59.8%) lie OUTSIDE every
  crown; 216 of the 327 no-change triples are off-crown. A crown model can fix at most
  111 of 327: a ceiling, unwinnable against the healer by construction.
- v1 died of a unit defect (pixel precision inverted with crown-pooled prevalence gave a
  false-positive rate ≥ recall in 11/12 epochs and constant paths). v2 fixed it (gate
  shown firing on v1, passing on the fix; 12 distinct paths) and laundered MORE: 11 of
  11 at-risk on-crown verified losses, all in 2021–2024, 26 of 33 epochs with the crown
  itself observed ABSENT.
- The arithmetic that explains it (derived by the referee from measured rates): at
  r ≈ 0.61, f ≈ 0.05 one observed absence is a likelihood ratio of (1−f)/(1−r) ≈ 2.5;
  four in a row ≈ 39:1; the pre-registered loss transition q_loss = 0.02 costs ≈ 49:1.
  The persistence prior beats four consecutive absences.
- The temporal engine (`crown_state_model.py`: transition_matrix, emission_matrix,
  forward_backward, viterbi, intervals) is shape-agnostic in N and ports to per-cell
  unchanged; memory as written ≈ 15 GB for 13.3 M cells × 12, so float32 + row-block
  chunking. Per-survey emission rates exist for all 12 stack tags (delivered cut,
  citywide, vs C-CAP 2021; `arm_metrics.csv` scored_live rows). 2016-referenced rates
  now exist for all 12 stack tags (citywide, delivered cut, vs C-CAP 2016; landed
  2026-09-10 22:00Z, `arm_metrics.csv` scored_live rows, ref ccap_2016_hires_lc.tif) and
  the model's emission gate passes on them (f 0.011–0.082 < r). Lidar-referenced rates
  do not exist yet.

### 2.4 What exists for space and for buildings
- Spatial operators in the repo: ONE 3×3 opening/closing at postproc
  (`phase4seg/postproc.py::threshold_and_clean`) and 8-connected component floors. No
  majority filter, no consensus map, no spatio-temporal operator anywhere. Every healing
  and state decision to date is 1-D along time.
- Buildings: `pipeline/builders/make_building_masks.py` writes per-year 1 m building-
  presence masks from `buildings_canonical.gpkg` (assessor `yr_built` on 97.5% of
  structures) fused with an imagery roof-presence probe
  (`qc/instruments/roof_presence_matrix.py`). Its own header records the failure of a
  static footprint (Greystone: bare graded earth 2000, houses by 2005).
- Gold: `phase4/qc/panel_a_gold.csv`, 1,214 points, 1,170 no-change / 42 loss / 2 gain,
  ruling on 2016→2024. There is NO false-positive label in the gold (no "roof tree").

### 2.5 The paper Kam brought (Mobsite et al. 2026, Artificial Intelligence in Geosciences 7:100222)
- MUSCLE-Net: auxiliary decoder outputs at H/4 and H/2 supervised by DOWNSAMPLED labels
  ("deep supervision"), weight 0.1, plus CBAM in the decoder. The same ResNet-50 U-Net
  goes 46.3 → 53.8 mIoU on DFC2020 (10 m Sentinel); the auxiliary loss carries the gain,
  the attention less. Gains concentrate on minority / fragmented classes. Not a
  curriculum: one resolution, graded coarse-first inside the decoder. Transfer caveats:
  10 m vs our 7.5–80 cm; label scale, not sensor scale.

## 3. Measured constraints, stated as rules for any design
1. The unit is the CELL (2 m stack), not the crown (§2.3).
2. Lidar is never an INPUT at inference (§2.2). It may correct labels, score rates, or
   teach a student, only in the years it can vouch for.
3. Global consensus can launder local change (§2.2): every design keeps the terminal-
   absence kill on the 42 verified losses, the triple criterion on the 1,170 no-change
   points, and adds the lidar-certified GAIN / FLAT populations as a denominator the
   healer never had. Any rule that can reach a terminal absence through SPACE needs its
   own at-risk count, shown to move on a bad input (CLAUDE.md 3.4c).
4. Each survey's vote is weighted by its measured eyesight (r, f per epoch); a design
   without that slot (plain closing, plain segmentation) is the baseline, not a candidate.
5. Healed / consistency output feeds trajectories, validity intervals and change maps,
   never the annual fraction series (endpoints cannot be healed).

## 4. The design, as brainstormed (PROPOSED, unvalidated)

### 4.1 Three axes of agreement
- **Time, per cell.** The state model's forward-backward with per-epoch (r, f). Exists.
- **Space, same year (local).** Does the cell's neighbourhood in THIS year's mask agree
  with the cell? A shadow miss sits inside a stand the same mask still calls canopy; a
  roof tree sits on a patch nothing else calls canopy.
- **Space, across years (global).** The consensus raster: share of the twelve years that
  call the cell canopy, and the same over a window. A stand canopy 11/12 years is the
  prior for every cell in it.
- Archetypes: roof tree = temporally AND spatially isolated positive. Shadow tree =
  temporally isolated absence inside spatial and temporal agreement. Real clearing =
  absence that persists and (with development) has a dated local cause.
- Formal object: a random field in space and time. Tractable form: the per-cell temporal
  chain with its PRIOR conditioned on the local and global consensus features; the
  local/global weight is a parameter to be MEASURED, not set.

### 4.2 Development as a dated, local, directional prior (Kam, 2026-09-10)
- A new building at year t says: within radius R, for the k years before t, losses are
  likely. Raise q_loss(x, t') locally so the year's own observation can beat the
  twelve-year consensus. Demolition is the mirror (a gain prior after). Formally one
  extra input raster per year to the chain; nothing else changes.
- Sequence on a lot: cut → grade → build. The roof is last; the cutting is 1–3 years
  older. Bare graded earth is the earlier marker and has no labels today.
- What exists: dated assessor footprints + per-year presence masks (§2.4). What a vision
  model (same U-Net frame, trained on the footprints) would ADD: structures outside the
  record, an imagery-based date to check the assessor, and, with new labels, the grading
  stage.
- Cautions: covers development-driven loss only (storm, disease, view cuts, single-lot
  removals get no anchor); must be one-directional (believe a loss more readily near a
  new building, never manufacture one; the no-change gold points near new buildings are
  the check); R and k come from data, not from Greystone alone.
- **First measurement (CPU, ~1 h, files on hand):** distance from each of the 42 losses
  and 1,170 no-change points to the nearest building dated 2016+; enrichment at 30 / 60
  / 100 m. Decides whether the assessor clock suffices or an imagery detector is needed.

### 4.3 Lidar as teacher, not crutch (three legitimate roles)
1. **Label correction in the years it vouches for.** The 2016 CHM refines 2015–2017
   training labels under the ADD-ONLY rule (add canopy where height says canopy and the
   projected label is unsure; add IGNORE where height says nothing and the label says
   canopy). The student never sees lidar.
2. **Reference for measuring eyesight.** Per-survey (r, f) scored against lidar canopy
   binaries instead of C-CAP (which overestimates canopy, Kam's observation).
3. **Distillation.** A lidar-fed teacher labels the lidar years; an imagery-only student
   trains on those labels; the student is examined on a year WITHOUT lidar. The
   exam-without-AI test is the existing H2-K1 interaction.

### 4.4 Better per-survey precision / recall makes year-of trust arithmetic, not faith
- At r = 0.61 one absence is LR 2.5, four are 39:1 (< the 49:1 loss cost). At r = 0.80
  one absence is LR 5, four are 625:1. Development anchors lower the bar further where a
  house appears. The two ideas compose: training changes raise each year's vote; the
  anchor says where to spend the trust.
- Two training levers (both engine changes, so numerics bench + pre-registration on
  ResNet-18 at the 33-block tier, matched-cut scoring, floor 0.0069):
  a. **Deep supervision** (the paper): two auxiliary heads at H/4 and H/2, weight 0.1,
     IGNORE-aware loss. Target years 2019n (fragmentation-shaped failure) and 2006s.
  b. **Resolution curriculum** (Kam): degrade the 2020 imagery + hand labels to 80 cm /
     1 m with the unblocked degradation synthesis, train coarse, fine-tune native.
     Target year 2005 (81 cm effective). Tempered by the measured fact that
     detectability is NOT ordered by resolution (season and sensor dominate), so expect
     help on the genuinely coarse surveys and little on 2019n.

### 4.5 Where the layer sits
Beside the healer on the RAW stack, not downstream of it: seven of ten interior epochs
carry only IGNORE from the healer, so a spatial layer on its output would reason over
255s. The healer's alignment step is dropped (no-op at 2 m); its component floor and
its output restriction (§3.5) are kept.

## 5. Kills and references every graduated design must carry
| Kill | Population | Source |
|---|---|---|
| Terminal-absence laundering of a verified loss | 42 losses (at-risk stated, per rule) | `heal_vs_gold.py` definitions |
| Impossible triples at no-change points, COUNT and SHARE | 1,170 points, 327 raw triples | `heal_vs_gold_12ep.csv` |
| Canopy painted on lidar-certified FLAT cells | 40,609 cells, sample blocks | `harm_change_laundering.py` |
| Canopy back-dated onto lidar-certified GAIN cells before the gain | 46,805 cells | same |
| No-change gold points near new buildings stay no-change | subset of 1,170 | §4.2 |
| Placebo: shuffle the survey-to-rate assignment; agreement must fall | 20 draws | `crown_state_model.py --placebo-seed` |
| Every kill shown to FIRE on a known-bad input before it counts | all | CLAUDE.md 3.4c |

## 6. Open questions for Kam (design decisions, not facts)
1. How much may the layer RESHAPE a mask? "Apply the consensus shape" (strongest, most
   likely to launder) vs "fill or veto single cells, never redraw" (weakest, safest).
2. Do dated building footprints and water enter as HARD negative context (a roof is a
   roof every year)? The certified-flat population makes this testable.
3. Vision model for buildings: worth building before the enrichment count (§4.2) says the
   assessor clock is insufficient?
4. Which training lever first: deep supervision (cheaper, engine change) or curriculum
   (needs the degradation set built)?

## 7. Proposed order (cheapest, most decisive first)
1. Building-proximity enrichment count on the gold (CPU, ~1 h). No design depends on the
   answer except §4.2's clock choice.
2. Per-cell port of the temporal chain (float32, row-block chunking) scored on ALL 1,214
   gold points: the first number that can be compared to the healer's 240/327 fairly.
   Pre-registered with the §5 kills; the K4 rate references (C-CAP 2016, lidar) as
   sensitivity.
3. Consensus features (local, global) as a prior on the chain; the local/global weight
   swept and READ against the gold, not chosen.
4. Development prior (§4.2) as an extra input to the chain, R and k from step 1.
5. Deep-supervision arm on ResNet-18 (§4.4a); curriculum arm (§4.4b) after the
   degradation set exists.
6. Lidar-as-teacher label correction (§4.3.1) as a labels experiment, scored the same way.

## 8. Not decided, not built
Everything in §4–§7. The only tracked artefacts are the ones cited in §2. This brief is
authored; when a measurement lands it goes to `phase4/qc/` and gets a pointer here, and
the brief's claim is rewritten to cite it.
