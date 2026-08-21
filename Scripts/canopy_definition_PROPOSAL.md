# What counts as canopy? — PROPOSAL for sign-off (U1)

**STATUS: DRAFT except D2, which is DECIDED (Kam, 2026-08-20 — see the DECIDED block at D2;
it OVERRULES the draft recommendation there).** Kam signs off (or overrules) each remaining
decision below. When all of U1 is signed off the adopted text moves to `Method_Pipeline.md`
— the one home for method — and this file is archived. Until then the project has no
*complete* written canopy definition.

---

## Why this blocks everything

U1 is the top blocker in `Reports/Measurement_Validity_Assessment_2026-08-18.md` (NOTE: since
2026-08-18 Reports/*.md and *.csv are tracked, so that file IS version-controlled), and the
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
- **…but here it is probably NOT only a threshold difference.** The D1 sweep below shows no
  plausible NDVI/height pair reproduces C-CAP's ~.29 except the strictest corner. C-CAP's
  forest classes are stand-based and exclude isolated crowns *by kind* (McCombs 2016, ID 77:
  3×3 unit, six-of-nine homogeneity rule, sold as a screening product). So the gap is part
  threshold and part unit-of-analysis, and only the threshold part is ours to choose.
- **A 250-point human sample *can* settle it** — `phase4/qc/design_power_2016` shows the real
  stratified design separates .29 from .35 with power ~1.0 at ≤5% interpreter error. But it
  can only reproduce a definition it has been given. Without this page, 250 points produce a
  third opinion instead of an arbitration.

**One-line consequence:** every canopy number this project has ever reported is conditional
on a rule nobody has written down.

---

## The six decisions

Each has a recommendation and its consequence. Accept, or strike and replace.

> ### ⚠ D1 IS MIS-POSED — read this before deciding it (added 2026-08-18)
>
> D1 below asks for a **minimum height**. New evidence says height cannot decide the
> question it is being asked to decide.
>
> Crossing the NDVI reference against NOAA's purpose-built tree/shrub product,
> vintage-matched (`phase4/qc/ndvi_vs_tree_2021s.txt`): the entire .29-vs-.38 gap is **one
> population** — the 33% of NDVI-reference canopy that NOAA calls neither tree nor shrub.
> Its median height is **6.0 m**, **88.7% of it is ≥3 m** and **61.1% is ≥5 m**.
>
> So the recommended ≥3 m rule keeps ~89% of the disputed population and lands near the
> NDVI reference's number, not near .29. **No plausible height cut separates it.** And the
> same product shows height is a poor proxy for tree-vs-shrub in general: ≥3 m keeps 97.6%
> of tree but also 65.6% of shrub.
>
> The real decision is about **crown form / minimum crown size** — is a 6 m ornamental,
> hedgerow or understory crown a tree? — and that is what D2 asks, not D1. **Decide D2
> first and treat D1 as a secondary cleanup.** The table below is still correct arithmetic
> and still worth reading; it simply cannot arbitrate the reference dispute on its own.

### D1 — The two thresholds  ← **these move the headline number**

**These are measured, not estimated.** `phase4_qc_ndvi.py` already sweeps both cutoffs and
wrote the table below to `phase4/qc/ndvi_ref_2016.txt` — canopy as % of imaged 2016 pixels:

| | height ≥1 m | **≥2 m** | **≥3 m** | ≥5 m |
|---|---|---|---|---|
| NDVI ≥0.10 | 45.08 | 43.26 | 40.97 | 35.06 |
| NDVI ≥0.15 | 41.67 | 40.17 | 38.23 | 33.14 |
| **NDVI ≥0.20** | 39.00 | **37.74** ← NDVI ref | 36.07 | 31.59 |
| NDVI ≥0.25 | 36.58 | 35.49 | 34.05 | 30.10 |
| **NDVI ≥0.30** | 34.15 | 33.22 | **31.97** ← corrected labels | 28.50 |

Three things this shows that were not obvious before:

1. **The greenness cutoff matters as much as the height cutoff — arguably more.** Holding
   height at 2 m, moving NDVI .10→.30 costs **10.0 points**; holding NDVI at .20, moving
   height 1→5 m costs **7.4 points**. Earlier drafts of this page treated D1 as a height
   question. It is two questions, and the greenness one has been invisible because every
   document quotes a height but few quote the NDVI cut.
2. **Height is cheap in the 2→3 m step.** At NDVI ≥.20 it costs only 1.7 points
   (37.74 → 36.07). The IGNORE band therefore buys honesty about the contested zone at a
   small cost in area — that is a good trade.
3. **No cell on this table equals the latent-class estimate of ~.29** except the strictest
   corner (NDVI ≥.30 & ≥5 m = 28.50). The recommended rule lands at **31.97**, about
   3 points above. So C-CAP's total is probably **not** reproducible by any threshold pair
   here — its forest classes are *stand-based* and exclude isolated crowns as a matter of
   kind, not degree (McCombs 2016: 3×3 unit, six-of-nine rule). **Do not expect a threshold
   choice to reconcile the two references**; that was the assumption behind reading ~.29 as
   "the strict definition", and this table weakens it.

**Recommended: NDVI ≥ 0.30 AND height ≥ 3 m → canopy; green and 2–3 m → IGNORE.
Canopy ≈ 31.97% of the 2016 imaged area (2016).**

> **⚠ SCOPE CORRECTION 2026-08-18 — these are NOT citywide figures.** The 2016 ortho covers
> only **41.9% of the project's study area** (the phase3 2020-mask extent): a central/coastal
> band, lat 47.7830–47.8280, missing 3.99 km at the north, 1.59 km at the south and 0.82 km
> at the east. Every percentage in the table above is over that band, not over Edmonds.
> C-CAP is not much better at 53.1%. The *relative* comparisons between threshold pairs are
> unaffected — they all share one denominator — so **D1 remains decidable on this evidence**.
> But the absolute number must not be published as a city canopy figure, and a citywide
> figure cannot be produced from 2016 at all. The years with full coverage are 2000, 2013,
> 2015 and the CHM.

> **The CHM-coverage worry — RAISED, MEASURED, CLOSED (2026-08-18).** The rule requires a
> CHM height, so a pixel with no lidar is forced to non-canopy by absence of data rather than
> by the definition, and that is 16.5% of the analysis area. STATE had always *asserted* the
> uncovered strip was Puget Sound and the southern margin; `phase4_qc_chm_gap.py` checked it.
> The no-CHM zone is **99.8% negative NDVI** — open water — against 19.6% in the covered
> zone, and only **0.1%** of it is green at any threshold. Counting every green no-CHM pixel
> as canopy would raise city canopy by **+0.02 pp**. So the table above is a lower bound in
> principle and an exact figure in practice; **no coverage correction is needed and none
> should be applied.** (`phase4/qc/chm_gap_2016.txt`)
>
> What does *not* go away: a lidar-dependent definition cannot be applied to years the lidar
> does not cover — the whole pre-2016 record. See "what this does not decide". And this says
> nothing about whether the CHM is *accurate* where it exists, which is U6 and still open.
Reason: this is *already* the de facto rule — `phase4_build_corrected_labels.py` uses
NDVI≥.3 & CHM≥3 m → canopy and green 2–3 m → IGNORE. Adopting it makes the existing
corrected labels consistent with the definition rather than requiring them to be rebuilt,
and the IGNORE band puts the contested zone into the one state the mask convention already
has for "we do not claim to know" (rule 6: 0 / 1 / 255-IGNORE).
Against it: it partly *decides* the C-CAP-vs-NDVI dispute by construction. Declaring that
openly is better than leaving it implicit, which is the current state.

### D2 — Shrub versus short tree

> **DECIDED — Kam, 2026-08-20. OVERRULES the recommendation below.**
>
> **Mid-height woody vegetation COUNTS as canopy**: ornamentals, hedgerows, laurel
> walls, mass shrub plantings, understory crowns — the ~6 m-median disputed
> population — are canopy. The interpreter still **records them as their own
> distinct class** (the D6 item-3 flag stays mandatory), so the call remains
> reversible and can be re-scored later without re-interpreting.
>
> Consequences, stated openly:
> - The definitional side of the .29-vs-.38 dispute lands on the **NDVI-reference
>   side (~.38-family)**; C-CAP's stand-based forest classes under-cover this
>   definition *by kind* (its screening MMU drops isolated crowns), so C-CAP
>   recall/precision numbers are now read as a strict LOWER bound on agreement,
>   not as the definition.
> - The 5–15 m band's misses — **53% of all model misses** — count **fully
>   against the model**. Nothing in the honest scores is excused by definition.
> - D1's threshold question is now a calibration detail under this ruling
>   (which NDVI/height pair best operationalises "woody vegetation counts"),
>   not an arbitration between products.

**Recommended** *(the draft's original text, retained for the record — overruled above)*:
canopy requires **tree form** — a single identifiable stem/crown structure.
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
