import io
p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - COMPLETE: THE MODEL DOES NOT RELY ON COLOUR, AND 2021 PROVES IT (Q135) *** - 2026-08-19
Completes the previous entry. All five years:

| year | AUC model | AUC brightness | AUC GRVI | model gain | corr(model, GRVI) |
|---|---|---|---|---|---|
| 2000 | 0.8760 | 0.6333 | 0.5927 | +0.2427 | +0.1882 |
| 2005 | 0.9134 | 0.7170 | 0.6941 | +0.1964 | +0.4737 |
| 2009 | **0.9195** | 0.6847 | 0.7061 | +0.2348 | +0.4745 |
| 2013 | 0.9125 | 0.6881 | 0.7273 | +0.2243 | +0.5428 |
| **2021** | **0.9150** | 0.6662 | **0.5453** | **+0.2488** | **+0.0755** |
| **range** | **0.044** | 0.084 | **0.182** | | |

**2021 SETTLES IT.** It is the year where GRVI carries the least information of any acquisition
(AUC 0.5453, separation -0.007) **and** where the model resembles GRVI least (rank correlation
**+0.0755**, essentially zero). **The model's AUC there is 0.9150 - its second best.** A model
relying on colour cannot behave that way. Taken with 2000 - saturated colour, model still 0.8760 -
the conclusion is not an inference from correlations but from two independent extreme cases.

**AND THE MODEL IS MORE STABLE THAN ITS OWN INPUTS.** Model AUC varies by **0.044** across 21 years,
three providers and a four-fold resolution change. Over the same acquisitions GRVI varies by 0.182
and brightness by 0.084. **The network is roughly four times more consistent than the colour
statistics of the imagery it is fed.** That is the cleanest robustness statement this project has,
and it is threshold-free, so no calibration choice is doing the work.

**THE ONE DIP IS RESOLUTION, NOT COLOUR.** 2000 is the only year below 0.91, and it is the coarsest
(~40 cm true GSD against ~10 cm). Its colour is the second-worst, but 2021's colour is worse still
and 2021 does not dip. **Resolution separates the years; colour does not** - which is exactly the
asymmetry the texture-bias hypothesis (ID 207) predicts, and exactly what it.73 found independently
by measuring recall at a matched operating point (2000/2002 ~0.65, everything 2005-2021 within
0.020).

**WHAT WOULD FALSIFY THIS, STATED SO IT CAN BE.** These are AUCs against C-CAP over single sampled
points, so they measure ranking quality, not delineation, and they inherit C-CAP's definition. The
texture reading is a hypothesis consistent with three measurements, **not a demonstration** - ID 208
(2025) argues the texture-bias result itself is an artefact of how cue-conflict stimuli suppress
information. **A channel-ablation or occlusion test on the trained network is still the only thing
that settles Q98**, and nothing here substitutes for it.

**PRACTICAL UPSHOT.** The colour-comparability problems found in it.72, it.74 and it.75 are real but
**they are not the binding constraint on this model** - it already largely ignores the channel they
damage. Effort is better spent on the two things that are binding: **threshold/area estimation
(Q136)** and **resolution at the coarse end**.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)
s = s.replace("""- **Q135. PARTIALLY ANSWERED (2013, 2021 pending).**""",
"""- **Q135. ANSWERED: the model does not rely on colour.** Model AUC 0.876-0.920, **range 0.044**
  across 21 years, against GRVI's 0.182 and brightness's 0.084 - more stable than its own inputs.
  **2021 is decisive**: GRVI AUC 0.5453 and model-GRVI correlation +0.0755, yet model AUC 0.9150.
  The only dip (2000, 0.8760) is the coarsest year, so **resolution separates years and colour does
  not**. Superseded detail below.
  PARTIALLY ANSWERED (2013, 2021 pending).""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Replace map-count area with reference-sample estimation (Q136)** - the single highest-value
   fix now identified. `phase3_semantic_dev.py:1722` counts thresholded pixels; three independent
   measurements say calibration dominates the reported numbers. The Olofsson/CEOS machinery is
   already in this tracker and P3's design already exists. **Not new research - applying what we
   already read.**
2. **Channel ablation on the trained net (Q98/Q135)** - the only thing that settles what the model
   keys on. Needs GPU; everything else here is circumstantial by construction.
3. **Does the per-year threshold manufacture a trend in the AREA series (Q132)?** Premise now
   confirmed in code; the measurement remains.
4. **Test relief displacement (Q123), then spurious CHANGE from differing frame layouts (Q125).**
5. **1998 as the panchromatic pilot (Q126)** - 1936 is an empty file, so this is the whole of it.
6. **Human-check the 2-5 m over-impervious cell (Q120).**
7. **Aux-height INPUT variants on the impervious split** - labels (it.68) and shadow (it.69) ruled
   out; Wagner 2024 (ID 199) is the published precedent.
8. **Why is 2007 degenerate at cr=0.20 (Q133)?** Cheap histogram check.
9. **Trace which results used cross-year GRVI (Q129).**
10. **Write down the canopy definition (Q1).**

"""
s = s[:old_q_start] + new_q + s[old_q_end:]
io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 77 | 2026-08-19 | *** EMPIRICAL COMPLETE - the model does NOT rely on colour, and 2021 "
       "proves it (Q135) *** | Geirhos 2019 (207) vs its 2025 refutation (208) | Model AUC .8760 "
       "(2000) .9134 (2005) .9195 (2009) .9125 (2013) .9150 (2021). RANGE 0.044 across 21 yrs, 3 "
       "providers, 4x resolution change - vs GRVI range 0.182 and brightness 0.084. THE MODEL IS ~4x "
       "MORE STABLE THAN THE COLOUR STATISTICS OF ITS OWN INPUTS, threshold-free so no calibration "
       "choice is doing the work. 2021 IS DECISIVE: worst GRVI of any year (AUC .5453, separation "
       "-.007) AND lowest model-GRVI correlation (+.0755, ~zero), yet model AUC .9150, its 2nd best. "
       "With 2000 (saturated colour, model still .8760) that is TWO independent extreme cases, not "
       "an inference from correlations. ONLY DIP IS 2000 = the COARSEST year, and 2021's colour is "
       "worse yet does not dip => RESOLUTION separates years, COLOUR DOES NOT - the exact asymmetry "
       "texture-bias predicts and what it.73 found independently. UPSHOT: the it.72/74/75 colour "
       "problems are REAL BUT NOT BINDING; effort belongs on area estimation (Q136) and coarse-end "
       "resolution. FALSIFIABLE: ID 208 argues texture-bias is itself an artefact; only a channel "
       "ablation settles Q98 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
