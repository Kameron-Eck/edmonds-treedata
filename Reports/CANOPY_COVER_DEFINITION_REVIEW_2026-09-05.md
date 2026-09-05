# What Counts as Canopy — The Definitive Review
**Edmonds Tree Canopy Assessment · definitional review for the study's core variable**
*Prepared 2026-09-05. Synthesized from measured pipeline outputs (cited by file), primary-source documents fetched this session (marked ✅), and standard literature (marked ◻ = from training knowledge, not fetched this session — verify before quoting verbatim). Snippet-only sources marked ⚠.*

---

## Table of Contents

1. [Kam's four questions, answered](#1-kams-four-questions-answered)
   - 1.1 Is canopy what you'd see looking straight down at high noon?
   - 1.2 Do small breaks inside a crown count as canopy?
   - 1.3 Is there a gap-size threshold?
   - 1.4 Does density matter — full coverage vs scattered clusters?
2. [The definitional lineage: cover, closure, crown cover](#2-the-definitional-lineage)
3. [The gap-threshold table across products and protocols](#3-the-gap-threshold-table)
4. [Pipeline self-audit: every implicit choice](#4-pipeline-self-audit)
5. [Measured sensitivity: each knob in pp of city area, on our data](#5-measured-sensitivity-table)
6. [Recommended written definition + implications for Panel B / K1 / the 36-run](#6-recommended-written-definition)
7. [Open decisions that are Kam's](#7-open-decisions-that-are-kams)
8. [Sources](#8-sources)

---

## 1. Kam's four questions, answered

### 1.1 "Is canopy what you'd see looking straight down — like the shadow at high noon?"

**The literature's answer: yes, almost exactly — the technical term is *vertical projection*, and your intuition is the standard definition.** Jennings, Brown & Sheil (1999), the canonical reference on this, define **canopy cover** as "the area of ground covered by a vertical projection of the canopy" (✅ verbatim, [OUP abstract](https://academic.oup.com/forestry/article/72/1/59/546241)). Two refinements to the high-noon picture:

- It is an **orthographic** (parallel-ray, straight-down) projection, not a sun-shadow. The sun is never directly overhead at Edmonds' latitude (~47.8°N; minimum solar zenith ~24°), so a real noon shadow is always displaced and slightly enlarged. The definition deliberately removes the sun from the question.
- The sister quantity, **canopy closure** — "the proportion of the sky hemisphere obscured by vegetation when viewed from a single point" (✅ verbatim, same source) — is what a fisheye photo or a spherical densiometer measures, and it is *not* our variable. Jennings et al. note the literature routinely confuses the two (✅). Cover is measured with vertical sighting tubes (GRS densitometer, Cajanus tube ◻); closure with hemispherical instruments ◻.

**What our pipeline does:** everything we produce is a vertical-projection quantity, with three different fidelities to "vertical":
- The **semantic masks** are predicted on orthorectified aerial imagery — approximately vertical, but crowns lean off-nadir by the acquisition's view geometry, and the between-year component of that is measured: `phase4/qc/coregistration.csv` medians (e.g. 2016: dx 0.49 m) are applied as chip shifts in Panel A.
- The **lidar CHMs** are true vertical measurements — the cleanest instantiation of the definition we own.
- **Panel A** had Kam judge "canopy AT THE CROSSHAIR" on ortho chips (`panel_a_paired_change.py` UI) — a vertical-projection point-intercept, the same logic as i-Tree Canopy's random-point method ◻.

So: adopt "vertical projection of tree crowns onto the ground" as the written phrase. It is what we already measure, and it is the phrase both a reviewer and a council will recognize.

### 1.2 "Do small breaks inside a crown count as canopy?"

**The literature's answer: this is precisely the split between two named, incompatible conventions, and you must pick one in writing.**
- **Crown cover** (Australian NFI usage; Walker & Hopkins ◻; FIA ocular estimation ◻) treats each crown as a **solid, opaque outline** — the small sky-holes between branches are *inside* the crown perimeter and count as cover.
- **Foliage projective cover (FPC)** (Specht ◻) counts only ground directly beneath **foliage** — within-crown breaks are gaps. FPC is always lower than crown cover for the same trees, by roughly the crown's internal porosity ◻.
- Field-method comparisons find the choice is not cosmetic: "different techniques yield considerably different canopy cover estimates" (⚠ snippet, [Korhonen et al. 2006 abstract](https://www.silvafennica.fi/article/315)).
- Practical rule of thumb in photo-interpretation and UTC practice: at typical imagery resolution the interpreter cannot resolve within-crown porosity anyway, so **crown cover (solid crowns) is the de facto standard for urban tree canopy** ◻; lidar-return methods are inherently FPC-like ◻ (Korhonen et al. 2011, first-return fraction above a height cut ◻).

**What our pipeline does — both conventions, in different instruments, and we have measured them disagreeing.** This is the report's central finding:
- The **2020 hand labels** are hand-traced crown polygons (`polygons/{site}_crowns_review.gpkg`, Method_Pipeline "Label provenance") — **solid crowns = crown cover**. The model was taught crown cover.
- The **old CHM** (`lidar_snoh_chm.tif`) behaves as a neighbourhood **maximum** — a *dilated* canopy that spreads crown height into gaps (`build_chm2_2016.py` [2b]; IMAGERY_FACTS 8.3) — effectively crown cover with gaps closed.
- **chm2** (`lidar_chm2_2016_50cm.tif`) reports height *at the cell* — gaps open — effectively FPC.
- **C-CAP** labels forest patches "wall to wall, gaps included" (`phase4_chm_standalone_roc.py` docstring) — coarser still than crown cover: *stand* cover.
- The disagreement is measured, not hypothetical: the old CHM scores *better* against C-CAP than the sharper chm2 "purely by matching the reference's [gaps-included convention]", and applying dilate-then-blur to chm2 closes the entire ROC gap (`phase4/qc/CHM_STANDALONE_PRIOR_2026-08-29.md`).

**Recommended answer for the study:** small within-crown breaks **count as canopy** (crown-cover convention) — it matches the 2020 hand labels the whole archive is trained on, matches UTC practice, and matches what an interpreter can actually see. The mapped product then honestly under-implements this at pixel support (see 1.3), which the audit states.

### 1.3 "Is there a gap-size threshold — how big does a break have to be before it's not canopy?"

**The literature's answer: there is no ecological number. Every product has a threshold, and it is always set by the measurement support (pixel size, point, or minimum mapping unit), then declared as if it were a definition.** The honest move is to state ours explicitly. The comparative table is Section 3. Headlines:
- FAO's forest definition operates at a **0.5 ha** minimum area ◻ — gaps smaller than the MMU are absorbed into "forest."
- 30 m products (C-CAP regional, NLCD TCC, Hansen) absorb any gap smaller than ~900 m² into the pixel's class or fraction ◻ / ⚠ ([USFS TCC page](https://data.fs.usda.gov/geodata/rastergateway/treecanopycover/) confirms 30 m + "minimum-mapping unit (MMU) routines", page-level only).
- Point-sampling protocols (i-Tree Canopy ◻) have **zero** gap threshold — a point either lands on crown or on gap at whatever zoom the interpreter uses. The threshold silently becomes the interpreter's zoom level.
- Field crown mapping uses the solid-crown outline (gap threshold = the crown perimeter itself) ◻.

**What our pipeline does — three numbers, all now explicit:**
1. **Patch MMU (canopy side): 3 m² true.** `postproc.sieve_min_px` deletes canopy patches under `MIN_CANOPY_PATCH = 3.0 m²` (EPOCH 3 re-baseline, Kam 2026-09-01; pre-EPOCH-3 masks carried a CRS-unit bug spanning 0.28–3.24 m²).
2. **Gap closing: a 3×3 morphological open+close whose ground scale is GSD-dependent** — ~0.23 m at the 7.6 cm year, 3.0 m at 100 cm years (`postproc_variant_scores.csv` note). Gaps larger than that survive; there is **no** large-hole-filling rule. So between-crown gaps are non-canopy at pixel support.
3. **Measured consequence: nearly zero.** The recipe audit found morphology + sieve **neutral even at the 3 m-kernel extreme** — 1264.0 vs 1263.8 ha on 2011s (`Reports/RECIPE_AUDIT_2026-09-01.md`, `phase4/qc/postproc_variant_scores.csv`). The gap-size knob, the one that sounds most definitional, is the one that moves our numbers least.

**Recommended answer:** write the threshold we run: *canopy patches smaller than 3 m² are not mapped; gaps between crowns are non-canopy at pixel resolution; no minimum gap size.* And note the cross-year inconsistency (GSD-dependent closing) in the audit — measured neutral, but it should be said.

### 1.4 "Does density matter — does it have to be full coverage, or do scattered clusters count?"

**The literature's answer: canopy *cover* is density-blind by definition — each crown contributes its projected area wherever it stands — but land-cover *classifications* smuggle a density rule in, and that is exactly the difference between our two references.** The primary source, verbatim (✅ [NOAA C-CAP Regional Land Cover Classification Scheme](https://coast.noaa.gov/data/digitalcoast/pdf/ccap-class-scheme-regional.pdf)):

> **Deciduous Forest (9)** — "contains areas dominated by trees generally greater than 5 meters tall and greater than 20 percent of total vegetation cover" (Evergreen 10 and Mixed 11 read the same; Palustrine/Estuarine Forested Wetland 13/16 require "woody vegetation greater than or equal to 5 meters"; **Scrub/Shrub (12)** takes "shrubs less than 5 meters … includ[ing] tree shrubs, young trees in an early successional stage, or trees stunted from environmental conditions").

Three consequences: C-CAP's unit is the **area** ("areas dominated by trees"), not the crown — a lone street tree in a lawn is not an "area dominated by trees," so **isolated trees are excluded as a matter of kind** (our catalogue's "stands, not crowns"); its height cut is **5 m**; and young trees land in Scrub/Shrub, outside our `CCAP_CANOPY = [9,10,11,13,16]` class set. By contrast, per-pixel/per-crown definitions (NLCD TCC fraction ⚠, UTC crown mapping ◻, i-Tree points ◻, our masks) count every crown regardless of arrangement. FAO's forest likewise carries stand rules — ≥10% cover, trees ≥5 m, ≥0.5 ha, ≥20 m width ◻ — appropriate for forests, wrong for a city where much of the resource *is* isolated and clustered yard trees.

**What our pipeline does:** the semantic masks are **cluster-agnostic** — a lone madrona over a driveway counts identically to interior forest. The stand rule enters only through the C-CAP reference, and its cost is measured: the two references differ by **8.24 pp of city area** (`design_power_2016.txt`), disagree on 15–17% of pixels every year (`phase4_accuracy_sample.py` header), and C-CAP simultaneously over-calls stands (0.30% of certified physically-empty ground called canopy in 2016, `certified_flat_scores` work, CHATLOG 2026-09-04) while excluding isolated crowns. **Recommended answer:** scattered trees count fully; no density or stand-size rule in the study definition; C-CAP is retained only as a trend covariate, never as the headline's definition of canopy.

---

## 2. The definitional lineage

Compact genealogy — five quantities that all get called "canopy":

| Term | Definition | Geometry | Small breaks | Isolated trees | Canonical home |
|---|---|---|---|---|---|
| **Canopy cover** | ground covered by vertical projection of crowns | orthographic, areal | convention-dependent | count | Jennings et al. 1999 ✅ |
| **Crown cover** | cover with crowns as solid outlines | orthographic, areal | **canopy** | count | Walker & Hopkins ◻; FIA ocular ◻ |
| **Foliage projective cover** | ground directly beneath foliage only | orthographic, areal | **gap** | count | Specht ◻; lidar-return methods ◻ |
| **Canopy closure** | sky hemisphere obscured at a point | angular, point | n/a | n/a | Jennings et al. 1999 ✅ — *not our variable* |
| **Forest / tree land-cover class** | area *dominated* by trees above thresholds | classification, per-area | absorbed | **excluded** | C-CAP ✅; FAO FRA ◻; Anderson system ◻ |

The urban-forestry "tree canopy" of UTC assessments — "the layer of leaves, branches, and stems of trees that cover the ground when viewed from above" ◻ (UVM SAL / i-Tree phrasing) — is crown cover, row 2. Hansen et al. 2013 define their global "tree cover" as canopy closure for vegetation taller than 5 m at 30 m pixels ◻ (their "closure" is actually per-pixel cover fraction — the terminological confusion Jennings warned about, alive in the field's most-cited product). **Our study variable is row 2, crown cover, and should say so by name.**

---

## 3. The gap-threshold table

"Support" = the smallest unit at which canopy/not-canopy is decided; that unit *is* the effective gap threshold.

| Product / protocol | Support | Effective gap rule | Height rule | Isolated trees |
|---|---|---|---|---|
| FAO FRA forest ◻ | 0.5 ha area | gaps < MMU absorbed; temporarily unstocked still forest | trees ≥5 m (in situ) | excluded (stand def) |
| C-CAP regional 30 m ✅ | 30 m pixel (~900 m²) | absorbed into dominance call | trees >5 m, >20% of veg cover | excluded |
| C-CAP/NOAA hi-res LC (our `ccap_*_hires_lc.tif`) | 1 m pixel | stand-painted "wall to wall, gaps included" (`phase4_chm_standalone_roc.py`) | same scheme | largely excluded |
| NLCD TCC ⚠ | 30 m fraction | none at pixel; MMU routines in post | (methods report; not fetched) | contribute to fraction |
| Hansen GFC ◻ | 30 m fraction | none at pixel | veg >5 m | contribute |
| i-Tree Canopy ◻ | a point | zero (interpreter's zoom decides) | interpreter's judgment | count |
| UTC object-based (UVM-style) ◻ | ~1 m objects | internal holes smoothed at object scale | often ~2–2.5 m via lidar | count |
| Lidar cover metrics ◻ | return / grid cell | FPC-like, gaps open | first returns ≥2 m (convention) | count |
| **Ours — masks** | native pixel, 7.6–100 cm | open+close at 3×3 px (0.23–3.0 m ground, GSD-dependent); patch MMU 3 m²; no hole-fill | none explicit (learned from 2020 labels) | count |
| **Ours — NDVI+CHM ref** | 60 cm–1 m pixel | none (per-pixel) | ≥2 m (ref) / ≥3 m (corrected labels) — *old-CHM scale, see §4* | count |
| **Ours — Panel A** | a point on a 2 m draw lattice | zero (Kam's eye at chip zoom) | Kam's protocol (shrubs out) | count |
| **Ours — validity ladder** | a 2020 crown polygon | per-crown: ≥0.5 mask coverage PRESENT / ≤0.15 ABSENT | inherited | count |

---

## 4. Pipeline self-audit

Every implicit definitional choice currently running, with disagreements flagged **⚡**.

1. **Training labels define canopy as "what the 2020 model called canopy in April–July 2020."** Hand truth exists only as solid crown polygons at 6 sites; every other year learns the projected citywide 2020 mask (`--force-citywide`, all 56 manifests). The de facto convention is **crown cover, leaf-on, as of 2020**. Growth/removal/season enter as label error (CLAUDE.md §1).
2. **⚡ Three NDVI+CHM variants coexist:** the QC reference at NDVI≥0.2 & h≥2 m (`phase4_qc_ndvi.py`, → 37.7% of the imaged band); the corrected-label rule at NDVI≥0.3 & h≥3 m with a 2–3 m IGNORE band (`phase4_build_corrected_labels.py:145,193-198`); design-power's H_NDVI "woody veg ≥2 m." Three cutoff pairs, one name.
3. **⚡ The height scale under all of variant-2's numbers is broken, and this contaminates the definitional evidence base.** `ndvi_ref_*`, the D1 threshold sweep, `phase4_qc_height_by_agreement`, `phase4_qc_ndvi_vs_tree`, and the corrected-labels builder all hardcode `lidar_snoh_chm.tif` — measured **+4.1 to +5.4 m high in every bin from 0 to 30 m**, calling 8.82% of certified-flat ground >2 m (`build_chm2_2016.py` [2b]; IMAGERY_FACTS 8.3). The accuracy sampler switched to chm2 on 2026-09-03 ("strata drawn from it put the '5–15 m' band at ~0–11 m true"); the reference rasters were not rebuilt. Consequences:
   - The claim that the contested population is "trees, not shrubs — median height 6.0 m, 88.7% ≥3 m" (`ndvi_vs_tree_2021s.txt`, echoed in `Reports/CANOPY_DEFINITION_DECISION_2026-08.md`) inherits the inflated scale. **UNDETERMINED pending re-measure on chm2** — the offset is a neighbourhood-max mechanism, worst exactly where ornamentals sit near tall trees, so per-pixel correction is not a uniform subtraction; but the possibility that a substantial share of the contested 12.85% is truly <2 m must be treated as open.
   - Likewise the D1 finding "greenness matters more than height": with a +4–5 m inflated CHM, the height knob was tested slack. **UNDETERMINED pending the chm2 re-sweep.**
   - The old CHM's dilated form is itself a definition: it closes within-crown gaps (≈crown cover), which is *why* it out-scores chm2 against gaps-included C-CAP (`CHM_STANDALONE_PRIOR_2026-08-29.md`). Our two CHMs are the literature's two conventions wearing raster clothes.
4. **⚡ C-CAP class set imports the stand rule.** `CCAP_CANOPY = [9,10,11,13,16]` — forest classes only, Scrub/Shrub (12) excluded. Per the verbatim scheme (✅), that is trees >5 m, >20% dominance, area-based; young trees land in class 12 and are counted against us or not at all. NOAA's hi-res tree/shrub product separately confirms shrub is only 1.25% of the grid — the reference gap is *not* mostly literal shrubs (`phase4_qc_ndvi_vs_tree.py` header, subject to item 3's caveat).
5. **The operating threshold is the dominant, and least definitional-sounding, knob.** Per-year best-F1 thresholds span 0.332–0.643 across the fleet; threshold choice moved 2011s canopy **area by 54%** (RECIPE_AUDIT). Threshold policy C (Kam, 2026-09-01) governs; any written definition must note that the mapped number is conditional on it.
6. **Postproc MMU:** 3 m² true patch sieve (EPOCH 3); GSD-dependent 3×3 closing; no hole-fill; all measured area-neutral (§1.3).
7. **⚡ Denominator choices are live and large.** Whole-city C-CAP hi-res canopy 36.05% vs 32.30% on the south band we usually evaluate (`ccap_city_2016.txt`); the D1 grid is over the 2016 imaged band = 41.9% of the study area, not the city; CHM covers only ~60% of the city (no_chm stratum 16.5% of area, `design_power_2016.txt`) — the NDVI+CHM definition **cannot currently be evaluated on roughly a sixth of the city**. Which ground is in the denominator moves the headline as much as most definition knobs.
8. **Human instruments carry a fourth definition.** Panel A gave Kam no written rule ("pairing cancels … the interpreter's private canopy definition", docstring); Kam's in-session protocol ruled **shrubs NOT canopy** (growth form) and **canopy-over-pavement IS canopy**. The growth-form rule and the height rule disagree exactly on tall hedges/ornamentals — the contested population. Duplicate disagreement was 2/28 ≈ 3.6% (`panel_a_estimate.txt`), already past the power curve's bend (design_power: 0% err → arbitrates; 5% → power .889; 10% → .436 marginal).
9. **Scoring conventions:** unsure/IGNORE excluded from denominators (masks 0/1/255, rule 3.6); Panel A "unsure" (37 pts) excluded; edge pixels are ~2–3 recall pts of pure 1-px accounting at 1 m GSD (C2), and 2 m tolerance makes 2020 the best year at .920 (C2b) — the definition's edge rule (pixel-center, ≥50% crown) is doing real work.
10. **Resampling conventions differ by instrument:** Panel A strata warp model masks with `Resampling.max` (any canopy in the 2 m cell) but C-CAP with nearest — a per-instrument gap rule at the 2 m lattice (stratification only; labels unaffected).

---

## 5. Measured sensitivity table

Every number below is from our own instruments, on our data. "Band" = the 2016 imaged band (41.9% of study area) unless said otherwise.

| Knob | Swing | Where measured | Status |
|---|---|---|---|
| Reference family: C-CAP stands vs NDVI+CHM per-pixel | **8.24 pp** of city area (.2952 vs .3776) | `design_power_2016.txt` | measured; NDVI side on old-CHM scale ⚡ |
| Reference disagreement extent | 15–17% of pixels, every year | `phase4_accuracy_sample.py` header | measured |
| Greenness cut .10→.30 (at h≥2 m) | **−10.0 pp** of band (43.26→33.22) | `ndvi_ref_2016.txt` sweep | UNDETERMINED — old CHM ⚡ |
| Height cut 1→5 m (at NDVI≥0.2) | **−7.4 pp** of band (39.00→31.59) | same | UNDETERMINED — old CHM ⚡ |
| Recommended pair (.30/3 m) vs D2-literal (.20/2 m) | 31.97 vs 37.74 = **−5.8 pp** of band | same | UNDETERMINED — old CHM ⚡ |
| Contested population (NDVI-canopy ∧ NOAA-neither) | **12.85%** of grid; heights p50 6.0 m *(old scale)* | `ndvi_vs_tree_2021s.txt` | composition UNDETERMINED ⚡ |
| "Unsure" pixels: excluded vs counted non-canopy | ≈ the policy gap (~2–3 pp) | `CANOPY_DEFINITION_DECISION` A2 | inferred from band shares, not a standalone instrument |
| Model operating threshold | **54% of canopy AREA**, 23 recall pts (2011s) | RECIPE_AUDIT / `postproc_variant_scores.csv` | measured |
| Morphology + sieve (the literal gap knobs) | **~0** (1264.0 vs 1263.8 ha) | `postproc_variant_scores.csv` | measured NEUTRAL |
| Denominator: whole city vs south band (C-CAP hi-res) | 36.05% vs 32.30% = **3.75 pp** | `ccap_city_2016.txt` | measured |
| CHM coverage hole | ~40% of city unevaluable under NDVI+CHM; no_chm stratum 16.5% | design_power allocation | measured |
| Same flight, two deliveries | **1.3 pp** citywide, IoU .738 | C3, CHATLOG 2026-09-04 | measured — consistency floor |
| Edge accounting (1 px at 1 m) | ~2–3 recall pts / ~2.4 precision pts | C2 | measured |
| C-CAP over-call on certified-empty ground | 0.30% of flat cells (2016) | certified-flat scoring | measured |
| Interpreter error (measured, Kam, duplicates) | 3.6% → definition-arbitration power ~.9 and falling | `panel_a_estimate.txt` × `design_power_2016.txt` | measured |
| The signal all of this must not swamp | **−2.21 pp** 2016→2024, CI ±1.10 | `panel_a_estimate.txt` | measured |
| Map-series trend (for contrast) | sawtooth ±3–6 pp; +4.2 pp 2016→2024, sign-opposite Panel A — disqualified | trend8, CHATLOG 2026-09-05 | measured |

Reading: the definition is worth ~8 pp, the threshold policy ~half the mapped area, the denominators ~4 pp, the human's consistency ~everything (it gates whether definitions can be told apart at all) — and the gap/morphology knobs, the ones that *sound* like the definition, are worth ~0. The knobs that matter are the invisible ones.

---

## 6. Recommended written definition

> **Edmonds study definition of tree canopy (draft for sign-off).** Tree canopy is the area of ground covered by the **vertical projection of live tree crowns** — woody vegetation at least **3 m tall** (true height, chm2 scale) — as visible in leaf-on imagery, with crowns treated as **solid outlines** (small within-crown breaks count as canopy). What lies beneath the crown is irrelevant: canopy over pavement, roofs, or lawn is canopy. **Isolated trees count identically to forest stands**: there is no minimum stand size, density, or clustering requirement. Between-crown gaps are non-canopy at the resolution of the imagery, with no minimum gap size; mapped canopy patches smaller than **3 m²** are not reported. Woody vegetation **2–3 m** tall is recorded as *unsure*, excluded from published totals, and the exclusion is stated in every caption. A sample point is judged at the pixel center; a pixel is canopy if crown covers ≥50% of it. Totals are published as **area with a 95% confidence interval**, never a bare percentage, over a stated denominator (whole city vs imaged band, named explicitly).

Defensible to a council because every clause answers a plain question (§1); defensible to a reviewer because every clause names its convention (crown cover, Jennings-style vertical projection, declared MMU, declared abstention band, Olofsson-style area+CI) and each was chosen to match the measured, running system rather than force a rebuild (`CANOPY_DEFINITION_DECISION` — the no-op path). One deliberate change from the running system: **"3 m true height" means the rule's rasters must be rebuilt on chm2**, because the code's existing "3 m" is old-CHM 3 m ≈ a much lower true cut.

**Implications for Panel B / K1 labeling instructions:**
1. **This definition is written down and handed to the interpreter *before* the first point.** Measured interpreter error is already 3.6% (Panel A duplicates); the design's arbitration power falls to marginal at 10% (design_power). A mid-campaign definition quietly favors the tree-friendly side.
2. **K1 pre-gate (CPU, free, do first): rebuild `ndvi_ref_{2016,2023n}` + rerun the D1 sweep + `ndvi_vs_tree` + `height_by_agreement` on chm2.** Until then the height-knob sensitivity and the contested population's "trees not shrubs" composition are UNDETERMINED (§4.3), and K1's strata semantics ride on them.
3. Interpreter records per point: primary label + alternate where ambiguous + **shrub/growth-form flag** + the duplicate-judged subset (decision-doc B4). The flag keeps the form-vs-height question (§7.1) reversible instead of baked in.
4. Judge the pixel center; under-crown surface irrelevant; leaf-on cross-check imagery for leaf-off epochs (the Oct-2023 verify pass is the template — Kam already caught 2024's Mar–May leaf-off flight).
5. **Panel A/B consistency caveat, one sentence for the report:** Panel A's −2.21 pp was judged under Kam's growth-form rule (shrubs out). Pairing cancels level definitions but not boundary-crossing events — a removed 4 m hedge is a loss under the height rule and a non-event under the form rule. If Panel B adopts this written definition, say so and note the variable shifts slightly.

**Implications for the 36-run (`full_archive_e3`):** none on the engine — the definition was chosen to be the no-op path (threshold policy C stands; labels untouched; no retrain). It touches only measurement-layer artifacts: ndvi_ref rebuilds are scoring references, rebuilt on free CPU; and it reinforces the K4 recipe constraint forbidding old-CHM (`lidar_snoh_chm.tif`) overlays anywhere in the recipe.

---

## 7. Open decisions that are Kam's

1. **Form vs height for tall woody non-trees.** A 4 m laurel hedge: canopy (height rule, the draft above) or not (your Panel A growth-form rule)? Remote sensing cannot see growth form, so the map can only implement height — my recommendation is the height rule with the shrub flag recorded — but the call is yours, and it moves some share of the contested 12.85% band.
2. **The 2–3 m unsure band: excluded from totals (recommended) or counted as non-canopy.** Worth roughly the policy gap; changes a caption and a denominator, nothing in the model.
3. **Reaffirm or supersede D2.** Your 2026-08-20 ruling ("woody ≥2 m counts") taken literally means a 2 m cut — a genuine recipe change; the draft honors its intent by abstaining on 2–3 m instead. Signing the draft supersedes D2's letter.
4. **Headline reference and denominator:** NDVI+CHM-on-chm2 with the CHM-coverage hole stated, vs C-CAP, vs both-with-definitions-named; and whole-city vs imaged-band reporting. (C-CAP as headline is hard to defend for a city — §1.4.)
5. **Order of operations:** approve the chm2 rebuild set (§6.2) as the K1 pre-gate, or accept K1 on the current strata knowing item §4.3 stands unresolved.
6. **Sign-off itself:** the `CANOPY_DEFINITION_DECISION_2026-08.md` checkboxes, amended by this review (its cutoff table and "trees not shrubs" evidence are old-CHM and now carry the UNDETERMINED flag).

---

## 8. Sources

**Fetched and verified this session (✅):**
- Jennings, S.B., N.D. Brown & D. Sheil (1999), "Assessing forest canopies and understorey illumination: canopy closure, canopy cover and other measures," *Forestry* 72(1):59–74 — definitions quoted from the [OUP article page](https://academic.oup.com/forestry/article/72/1/59/546241) (abstract).
- NOAA Office for Coastal Management, *C-CAP Regional Land Cover Classification Scheme* — [PDF](https://coast.noaa.gov/data/digitalcoast/pdf/ccap-class-scheme-regional.pdf), read in full; class definitions quoted verbatim.

**Snippet-only (⚠):**
- Korhonen, L. et al. (2006), "Estimation of forest canopy cover: a comparison of field measurement techniques," *Silva Fennica* 40(4) — [abstract only](https://www.silvafennica.fi/article/315); full text PDF-restricted.
- USFS NLCD Tree Canopy Cover — [rastergateway page](https://data.fs.usda.gov/geodata/rastergateway/treecanopycover/) (page-level; the Mapping Methods Report was not fetched).

**From training knowledge — standard references, not fetched this session; verify before quoting verbatim (◻):**
- FAO FRA 2020 *Terms and Definitions* (forest: ≥0.5 ha, trees ≥5 m, canopy cover ≥10%, width ≥20 m; fetch attempts 403'd).
- Hansen, M.C. et al. (2013), "High-Resolution Global Maps of 21st-Century Forest Cover Change," *Science* 342 (tree cover as canopy closure for vegetation >5 m).
- Walker, J. & M.S. Hopkins (1990), vegetation structure attributes (crown cover, solid outlines), in *Australian Soil and Land Survey Field Handbook*; Specht, R.L., foliage projective cover.
- Korhonen, L. et al. (2011), airborne lidar estimation of canopy cover (first-return ratio above a height cut), *Remote Sens. Environ.*
- i-Tree Canopy (Nowak et al., USDA Forest Service) random-point photo-interpretation method; UVM Spatial Analysis Lab UTC assessment protocols ("…cover the ground when viewed from above").

**Pipeline artifacts cited (all repo-relative):** `phase4/qc/design_power_2016.txt`, `phase4/qc/ndvi_ref_2016.txt`, `phase4/qc/ndvi_vs_tree_2021s.txt`, `phase4/qc/ccap_city_2016.txt`, `phase4/qc/panel_a_estimate.txt`, `phase4/qc/postproc_variant_scores.csv`, `phase4/qc/CHM_STANDALONE_PRIOR_2026-08-29.md`, `phase4/qc/coregistration.csv`, `Reports/CANOPY_DEFINITION_DECISION_2026-08.md`, `Reports/RECIPE_AUDIT_2026-09-01.md`, `Scripts/IMAGERY_FACTS.md` (§8.3), `Scripts/Method_Pipeline.md` (Label provenance E06), `Scripts/qc/instruments/{panel_a_paired_change,phase4_accuracy_sample,phase4_qc_ndvi,phase4_qc_ndvi_vs_tree,phase4_qc_height_by_agreement,phase4_chm_standalone_roc,certified_flat_scoring,lidar_decimation_null}.py`, `Scripts/pipeline/{phase4_build_corrected_labels.py,builders/build_chm2_2016.py,phase4seg/postproc.py,phase4seg/config.py}`, `Scripts/CHATLOG.md` (2026-09-04/05 entries), `Scripts/WORKPLAN.md`.