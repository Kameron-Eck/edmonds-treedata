import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### EMPIRICAL - THE LEAF-ON TEST FAILS, AND IT CORRECTS ME (Q86) - 2026-08-19
Iteration 47 predicted the height staircase would FLATTEN on a leaf-on year if the curve were
substantially a deciduous-fraction artefact. It does the opposite.

**Recall by CHM band, same reference family (C-CAP), deployed thresholds:**

| band | 2022n **LEAF-ON** (NAIP) | 2013 **leaf-off** (King) | 2016 baseline |
|---|---|---|---|
| 0-2 m | **0.0622** | 0.2090 | 0.16 |
| 2-5 m | **0.0636** | 0.1955 | 0.16 |
| 5-10 m | 0.2063 | 0.3869 | 0.36 |
| 10-15 m | 0.4924 | 0.6070 | 0.57 |
| 15-20 m | 0.7466 | 0.7700 | 0.74 |
| 20-25 m | 0.8840 | 0.8562 | 0.83 |
| 30+ m | **0.9853** | 0.9449 | 0.93 |

**The leaf-on year has a STEEPER staircase, not a flatter one.** Low-band recall is three times
WORSE on leaf-on (0.062 vs 0.209 at 0-2 m), and top-band recall is better (0.985 vs 0.945).

**BUT THE TEST IS CONFOUNDED, AND THAT IS THE REAL FINDING.** In this archive, **leaf-on is
perfectly confounded with coarse resolution**: NAIP is the only leaf-on program and it is the only
60 cm program. 2013 is 14.9 cm. A small crown at 60 cm occupies a handful of pixels and is far
harder to detect regardless of season, which predicts exactly the low-band collapse we see.

**So the archive cannot separate season from resolution by comparing years.** There is no leaf-on
fine-resolution acquisition in the whole 18. That is a structural limitation of the dataset, not of
the test, and it means Q86 is **not answerable from existing rasters** - it needs either new
leaf-on fine imagery or a re-inference of a fine leaf-off year degraded to 60 cm.

**AND IT CORRECTS AN OVERSTATEMENT I MADE IN ITERATION 47.** I wrote that the height curve "is very
likely a consequence of labelling on leaf-off imagery". **That went further than the evidence.**
Two claims must be kept apart:

1. **2020 imagery shows a leaf-off signature** - 33% non-green canopy vs NAIP's 0-5%, resolution
   controlled, spec-aligned across four acquisitions. **This stands.** It is a statement about the
   imagery.
2. **Leaf-off labelling CAUSES the height curve** - **this is not established**, and the one test
   available in the archive points the other way while being confounded.

Iteration 47 conflated them. The corrected position: **we have strong evidence about what the 2020
imagery contains, and no evidence that it explains the height staircase.**

**What survives, and it still matters.** Even without the causal claim, leaf-off labelling is a
real problem on its own terms: a third of the canopy in the labelling year is not green, and
whatever else that does, it makes the 2020 mask a poor training signal for deciduous crowns and
makes any leaf-off/leaf-on year-pair comparison a phenology measurement. Those consequences do not
depend on the height curve.

**And the height staircase itself is now better supported than before**, because it survives on
both a leaf-on and a leaf-off year, and earlier (iteration 12, U3) survived inside the both-agree
reference partition. Three different ways of trying to make it go away have failed.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q86.** Is the height curve partly a DECIDUOUS-FRACTION curve?""",
"""- **Q86. [TESTED, INCONCLUSIVE - AND THE ARCHIVE CANNOT SETTLE IT]** The leaf-on year (2022n) has a
  STEEPER staircase, not flatter - but leaf-on is perfectly confounded with 60 cm resolution in this
  archive, since NAIP is the only leaf-on program and the only coarse one. No leaf-on FINE
  acquisition exists among the 18. Needs new imagery or a re-inference of a fine leaf-off year
  degraded to 60 cm. **My iteration-47 claim that the height curve is "very likely a consequence of
  leaf-off labelling" is withdrawn** - the imagery finding stands, the causal claim does not.
  Original question below.
  Is the height curve partly a DECIDUOUS-FRACTION curve?""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Separate season from resolution properly (Q86).** The archive cannot do it by comparing years.
   The one feasible route: take a FINE leaf-off year, degrade the IMAGERY to 60 cm, re-run
   inference, and compare its height curve against native-fine. That isolates GSD; season then
   falls out by difference against NAIP. Needs one Colab inference run, not new data.
2. **Season-score the remaining acquisitions** - `phase4_qc_leafoff.py`, one command each. Still
   worth doing: it decides which year-pairs are phenology-matched for the CHANGE product, which is
   independent of the height-curve question.
3. **Recall by height WITHIN the P2 agreement partitions on a leaf-on year** - iteration 12 did this
   for 2016 (leaf-off) and the staircase survived. Repeating on 2022n would show whether the
   leaf-on staircase is also reference-independent.
4. **Specificity on the UNCHANGED class (Q66).**
5. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
6. **Geometric vs thematic accuracy for per-object products (Q41).**
7. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
8. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
9. **Get the flight dates** - still the cleanest proof for the imagery claim.
10. **Broadleaf / deciduous-specific crown segmentation.**

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 48 | 2026-08-19 | EMPIRICAL - the leaf-on test FAILS and corrects me (Q86) | - | "
       "PREDICTED the staircase would flatten on leaf-on. IT STEEPENS: 2022n LEAF-ON gives 0.062 at "
       "0-2m vs 2013 leaf-off 0.209, and 0.985 vs 0.945 at 30m+. BUT CONFOUNDED - leaf-on is "
       "PERFECTLY confounded with 60cm in this archive (NAIP is the only leaf-on AND only coarse "
       "program; no leaf-on FINE year exists among the 18). Archive cannot settle Q86. "
       "WITHDRAWING my iteration-47 claim that the height curve is 'very likely a consequence of "
       "leaf-off labelling' - the IMAGERY finding (33% non-green canopy in 2020) stands, the CAUSAL "
       "claim does not. Height staircase now survives THREE attempts to explain it away |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
