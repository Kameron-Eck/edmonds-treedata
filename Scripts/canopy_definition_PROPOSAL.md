# What counts as canopy? — PROPOSAL for sign-off (U1)

**STATUS: DRAFT. NOT ADOPTED. NOTHING IN THIS FILE IS IN FORCE.**
Kam signs off (or overrules) each decision below. On sign-off the adopted text moves to
`Method_Pipeline.md` — the one home for method — and this file is archived. Until then the
project has *no* written canopy definition, which is exactly the problem.

---

## Why this blocks everything

U1 is the top blocker in `Reports/Measurement_Validity_Assessment_2026-08-18.md` (NOTE: Reports/ is git-ignored, so
that file is NOT version-controlled), and the
work done since has raised its stakes rather than lowered them:

- **The definition is worth ~6 points of city canopy.** Latent-class modelling across four
  years (`phase4/qc/latent_class_*`) puts latent prevalence at **.2912 / .2820 / .2931 /
  .2863** — on C-CAP's total — while the NDVI+CHM reference says **.338–.387**. The gap is
  not mainly error. The NDVI reference's surplus is concentrated in the **2–5 m band**
  (specificity .78 in 2016, .72 in 2021s): shrubs and hedges. One definition counts them,
  the other does not.
- **No estimator can settle it.** That was tested, not assumed — latent class answers
  "which source is internally most consistent", not "which definition is right".
  Gutiérrez-Vélez 2024 (ID 81) is the general statement: most cross-product forest
  disagreement is manufactured by thresholding one continuous variable at different points.
- **A 250-point human sample *can* settle it** — `phase4/qc/design_power_2016` shows the real
  stratified design separates .29 from .35 with power ~1.0 at ≤5% interpreter error. But it
  can only reproduce a definition it has been given. Without this page, 250 points produce a
  third opinion instead of an arbitration.

**One-line consequence:** every canopy number this project has ever reported is conditional
on a rule nobody has written down.

---

## The six decisions

Each has a recommendation and its consequence. Accept, or strike and replace.

### D1 — Minimum height  ← **the one that moves the headline number**

| Option | Effect on city canopy | Notes |
|---|---|---|
| ≥ 2 m | ~.35 | matches the NDVI reference; counts hedges and large shrubs |
| **≥ 3 m, with 2–3 m as IGNORE** | ~.29–.31 | **RECOMMENDED** |
| ≥ 5 m | below .29 | discards genuine small/young street trees |

**Recommended: ≥ 3 m canopy, 2–3 m IGNORE.**
Reason: this is *already* the de facto rule — `phase4_build_corrected_labels.py` uses
NDVI≥.3 & CHM≥3 m → canopy and green 2–3 m → IGNORE. Adopting it makes the existing
corrected labels consistent with the definition rather than requiring them to be rebuilt,
and the IGNORE band puts the contested zone into the one state the mask convention already
has for "we do not claim to know" (rule 6: 0 / 1 / 255-IGNORE).
Against it: it partly *decides* the C-CAP-vs-NDVI dispute by construction. Declaring that
openly is better than leaving it implicit, which is the current state.

### D2 — Shrub versus short tree

**Recommended:** canopy requires **tree form** — a single identifiable stem/crown structure.
Hedges, laurel walls, and mass shrub plantings are **not** canopy even above 3 m.
**But the interpreter records them as a distinct class**, so the decision stays reversible
and can be re-scored later without re-interpreting (Guo 2023, ID 88: adding small-crown
examples recruits shrubs, so the two must be separable in the record).

### D3 — Pixels at the crown edge  ← **newly important**

The edge work (`phase4/qc/edge_vs_interior_*`) found the outer 2 m of crowns is ~16% of
canopy area but carries **~42% of all misses**, replicated across 2016 and 2021s. So the
rule for partial pixels is not a technicality — it governs a large share of every score.

**Recommended:** a pixel is canopy when the **vertical crown projection covers ≥50% of the
pixel**; interpreters judge the **pixel centre**. State the pixel size with every number,
since "≥50%" means different things at 15 cm and 60 cm.

### D4 — What is underneath the crown

**Recommended:** canopy is the **vertical projection of the crown**, irrespective of what
lies beneath — lawn, driveway, and roof under an overhanging limb all count as canopy.
This is the standard UTC convention and matches what the imagery can actually support.

### D5 — Binary mask or fractional cover

**Recommended:** **binary at pixel scale** under D3, with city totals reported as **area with
a confidence interval**, never as a bare percentage. Rationale: the pipeline is binary
end-to-end (rule 6), and the honest uncertainty belongs in the interval, not in a fractional
value that would imply a precision the labels do not have.

### D6 — What the interpreter records per point

**Recommended**, and this changes `phase4_accuracy_sample.py --step serve`:

1. **primary** label (canopy / not / unsure);
2. **alternate** label where the point is genuinely ambiguous — Wickham 2023 (ID 78) shows
   primary-vs-alternate scoring swings accuracy 10 points (77.5 → 87.1), and the current
   sampler *excludes* unsure, which discards exactly the contested pixels;
3. an explicit **short-tree vs shrub** flag (D2);
4. a **duplicate-interpreted subset** for interpreter variance (Stehman 2022, ID 100).
   `design_power_2016` makes this load-bearing rather than optional: at 0% interpreter error
   the design arbitrates easily, at 10% it is marginal — so the study's credibility rests on
   a number we do not yet measure.

---

## What this does *not* decide

- Whether C-CAP or the NDVI reference is "right". Under D1 the answer is closer to C-CAP's
  total; that is a **consequence of the chosen definition**, not evidence about either
  product, and must never be quoted as the latter.
- The 2016c deploy question. Latent class was shown to be **inadmissible** for it (feeding
  the corrected model moves latent prevalence 5.8 points because it descends from the NDVI
  reference). P3 under this definition decides it.
- Anything about pre-2016 years, where no NIR exists and C-CAP is out of epoch.

## On sign-off

1. Adopted text → `Method_Pipeline.md`; this file → `_archive/`.
2. `phase4_accuracy_sample.py --step design` re-run if D3 changes the stratification.
3. `--step serve` updated for D6 before any point is interpreted.
4. CHATLOG STATE: U1 closed, P3 unblocked.
