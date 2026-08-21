import io
p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - THE MODEL IS FAR BETTER THAN COLOUR, AND THE AREA SERIES IS THRESHOLD-COUNTED (Q135, Q132) *** - 2026-08-19
**PARTIAL: 2013 and 2021 still running. Three years reported.**

**1. THE MODEL BEATS EVERY SINGLE-PIXEL COLOUR CUE BY A WIDE MARGIN.**

| year | AUC model | AUC brightness | AUC GRVI | model gain | corr(model, bright) | corr(model, GRVI) |
|---|---|---|---|---|---|---|
| 2000 | **0.8760** | 0.6333 | 0.5927 | **+0.2427** | +0.3148 | +0.1882 |
| 2005 | **0.9134** | 0.7170 | 0.6941 | +0.1964 | +0.5338 | +0.4737 |
| 2009 | **0.9195** | 0.6847 | 0.7061 | +0.2348 | +0.3895 | +0.4745 |

**Context and texture buy roughly 0.20-0.24 of AUC over the best colour feature.** The model is not a
colour detector: its rank correlation with brightness is only 0.31-0.53 and with GRVI 0.19-0.47.

**AND IT LARGELY SURVIVES 2000'S RADIOMETRIC DAMAGE.** it.74/75 showed 2000's colour is saturated
and near-uninformative - GRVI AUC 0.5927, separation 0.057. **The model still reaches 0.8760 there.**
Whatever it is using, it is mostly not the channel that is broken. That is consistent with the
texture-bias reading (ID 207) and it is the strongest robustness evidence this loop has produced.

**2. THE NUMBER THAT REFRAMES EVERYTHING: AUC 0.88-0.92 AGAINST RECALL 0.65-0.72.**
it.73 measured recall of 0.645-0.717 across these years at a matched call rate. **AUC is
threshold-free and lands at 0.876-0.920.** The model's *ranking* of pixels is strong and stable;
what is weak is *where the line is drawn*. **The binding constraint on the reported numbers is
threshold placement, not model quality** - which is exactly what it.73 concluded from the other
direction, arrived at here by an independent route.

**3. Q132 PREMISE CONFIRMED BY READING THE CODE.** `phase3_semantic_dev.py:1722` computes
`canopy_area = total_canopy_px * pixel_area` - **the area series is pixel-counting off a thresholded
binary mask**, with `binary_closing` applied first. Two consequences:
* it is the "map count" estimator that the Olofsson/CEOS protocol already in this tracker exists to
  replace, and it is **fully exposed** to the 22.0%-30.5% per-year call-rate variation of it.73;
* **morphological closing compounds it** - closing fills gaps, so it inflates area by an amount that
  depends on how fragmented the mask is, which itself depends on the threshold.

**`phase4_qc_score.py:83` describes its own threshold source as "the (circular) eval CSV".** The
circularity is already known and documented in the code; what is new is the measurement of how much
it can move (it.73) and the fact that the deliverable inherits it directly.

**THE CONVERGENCE WORTH STATING PLAINLY.** Three independent lines - the operating-point spread
(it.73), the GRVI drift (it.72), and now the AUC-versus-recall gap - all say the same thing: **this
project's model is better than its numbers suggest, and its numbers are dominated by calibration and
by a map-count area estimator.** The remedy is already in the tracker rather than in a new method:
estimate area from a reference sample, not by counting thresholded pixels.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)
s = s.replace("""- **Q135. [DIRECTLY TESTABLE, ties to Q98]**""",
"""- **Q135. PARTIALLY ANSWERED (2013, 2021 pending).** Model AUC 0.876-0.920 vs brightness
  0.633-0.717; gain +0.196 to +0.243. Rank correlation with brightness only 0.31-0.53, so **the
  model is not a colour detector**, and it reaches 0.8760 even in 2000 where colour is saturated.
  A channel ablation on the trained net is still the only thing that settles Q98.
- **Q136. [THE HIGHEST-VALUE FIX NOW IDENTIFIED]** Replace map-count area with reference-sample
  estimation. `phase3_semantic_dev.py:1722` counts thresholded pixels and `binary_closing` inflates
  the count further; the Olofsson/CEOS machinery is already in this tracker and P3's sample design
  already exists. **This is not new research, it is applying what we already read** - and it would
  decouple the deliverable from the per-year threshold entirely.
- **Q135b. [ties to Q98]**""")
io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 76 | 2026-08-19 | *** EMPIRICAL (PARTIAL - 2013/2021 pending) - the model FAR exceeds "
       "colour, and the AREA SERIES is threshold-counted (Q135, Q132) *** | Geirhos 2019 (207) + the "
       "2025 paper CONTRADICTING it (208) | AUC model .8760/.9134/.9195 for 2000/2005/2009 vs "
       "brightness .6333/.7170/.6847 - context+texture buy +0.196 to +0.243 AUC over the best colour "
       "cue. Model is NOT a colour detector: rank corr with brightness only .31-.53, with GRVI "
       ".19-.47. AND IT SURVIVES 2000's SATURATION - .8760 there despite GRVI AUC .5927 and "
       "separation .057, so whatever it uses is mostly not the broken channel. THE REFRAMING NUMBER: "
       "AUC .876-.920 vs it.73's matched recall .645-.717 - the RANKING is strong and stable, only "
       "the THRESHOLD is weak. Q132 PREMISE CONFIRMED IN CODE: phase3_semantic_dev.py:1722 "
       "canopy_area = total_canopy_px * pixel_area = MAP-COUNT off a thresholded mask, with "
       "binary_closing INFLATING it further by a threshold-dependent amount; phase4_qc_score.py:83 "
       "already calls its threshold source '(circular)'. THREE INDEPENDENT LINES CONVERGE (it.72 "
       "GRVI drift, it.73 operating point, this AUC gap): the model is better than its numbers, and "
       "the numbers are dominated by calibration + a map-count estimator. Remedy is already in the "
       "tracker - Olofsson reference-sample area, not pixel counting (Q136) |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
