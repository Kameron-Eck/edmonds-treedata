import io
p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - NEGATIVE RESULT: THE CORRECTED MODEL'S OVERHANG GAIN IS AN OPERATING-POINT ARTEFACT (Q119) *** - 2026-08-19
Compared `prob_2016` (baseline) against `prob_2016_corrected` (trained on ADD-ONLY labels built
from NIR+CHM) on the **common footprint**, 321,651 C-CAP canopy cells, 17.2% of them over
impervious.

**(a) At the deployed threshold 0.509 it looks like a decisive win:**

| model | recall | over IMP | over PERV | gap | call rate on non-canopy |
|---|---|---|---|---|---|
| baseline (RGB) | 0.6279 | 0.3183 | 0.6922 | -0.3739 | 0.0493 |
| corrected (NIR+CHM) | 0.8533 | **0.5612** | 0.9139 | -0.3527 | **0.1725** |

Over-impervious recall rises 0.24 and the worst cell (2-5 m over impervious) goes 0.028 -> 0.183,
a six-fold gain. **But the call rate on C-CAP non-canopy triples, 4.9% to 17.3%.**

**(b) Re-thresholded to the SAME overall recall, the gain vanishes:**

| model | thr | recall | over IMP | over PERV | gap |
|---|---|---|---|---|---|
| baseline | 0.509 | 0.6279 | 0.3183 | 0.6922 | -0.3739 |
| corrected, matched | 0.835 | 0.6296 | **0.3070** | 0.6965 | **-0.3895** |

**Over-impervious recall goes DOWN, and the gap gets slightly WIDER.** The worst cell recovers to
0.0366 against the baseline's 0.0282 - essentially nothing. And by height band the matched gap is
**worse where it matters most**: -0.076 at 2-5 m, -0.050 at 5-10 m.

**Q119 ANSWERED: NO. The corrected model did not learn about overhang; it moved its operating
point.** Everything the headline comparison shows is explained by calling more canopy everywhere,
which the impervious subset shares in proportion.

**THIS IS A DEPLOY-RELEVANT WARNING, NOT JUST A NEGATIVE RESULT.** A +0.225 recall gain at a fixed
threshold is the kind of number that gets a model deployed. Held at equal recall the corrected model
is marginally **worse** on every axis measured here. **Any future comparison in this project must
match operating points before claiming an improvement** - and none of the year-to-year recall
comparisons in the pipeline currently do.

**THE CAVEAT THAT COULD OVERTURN THIS, STATED PLAINLY.** The corrections were built from NIR+CHM;
the scoring here is against C-CAP. If the corrected labels moved the model toward the NDVI/CHM
canopy definition and away from C-CAP's, it would score worse against C-CAP while being closer to
truth. **This is the it.55 error in a new costume and I am not going to repeat it: the result above
is a statement about agreement with C-CAP, not about truth.** Settling it needs the human-checked
cell (Q120), which is reference-independent. Until then the honest reading is narrower: *the
corrected model's apparent overhang gain is not supported by the reference we scored it on.*

**WHAT STILL HASN'T BEEN TESTED.** Corrected LABELS are not a height INPUT. The v045/v046
aux-height variants put the CHM in as a channel, which is the actual structural fix Q116 pointed at.
That remains untested against the impervious split, and this negative result does not bear on it -
if anything it raises the value, because label correction has now been ruled out as the cheap route.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q119.** Would a height channel fix the overhang deficit?""",
"""- **Q119. ANSWERED: NO for corrected LABELS - the gain is an operating-point artefact.** At the
  deployed threshold the corrected model lifts over-impervious recall 0.3183 -> 0.5612, but its call
  rate on non-canopy triples; held at equal overall recall its over-impervious recall **falls** to
  0.3070 and the gap **widens** to -0.3895. Caveat: scored against C-CAP while corrected from
  NIR+CHM, so this is an agreement statement, not a truth statement. **A height INPUT channel
  (v045/v046) is still untested and is now the more valuable experiment.** Original question below.
  Would a height channel fix the overhang deficit?
- **Q121. [METHOD, applies to everything already measured]** How many of this project's
  year-to-year and variant-to-variant recall comparisons are operating-point artefacts? Q119 shows
  a fixed threshold can manufacture a +0.225 "improvement" that survives no matched comparison.
  **Every per-year threshold in the pipeline is calibrated separately**, so the cross-year recall
  series (.50-.78, finding 3) may be partly a threshold series. Testable by re-scoring at matched
  call rate rather than matched threshold.""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Re-score the cross-year recall series at matched CALL RATE (Q121)** - Q119 proved a fixed
   threshold can manufacture a +0.225 gain out of nothing. The .50-.78 cross-year wander is the
   project's finding 3 and it has never been checked against this. Highest value: it can only
   confirm or dissolve an existing headline number.
2. **Human-check the 2-5 m over-impervious cell (Q120)** - recall under 3%, small enough to inspect
   exhaustively, and reference-independent, which is what Q119's caveat needs.
3. **Test the v045/v046 aux-height INPUT variants on the impervious split (Q119 proper)** - corrected
   labels are now ruled out; a height channel is the remaining structural candidate.
4. **Characterise the tall-but-not-green pixels (Q114).**
5. **Write down the canopy definition (Q1)** - Q119's caveat is a definition dispute in disguise.
6. **Test whether scrub reconciles the references (Q112).**
7. **Trace what else used the NDVI reference (Q107).**
8. **What DOES the model key on (Q98)?**
9. **Specificity on the UNCHANGED class (Q66).**
10. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]
io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 68 | 2026-08-19 | *** EMPIRICAL NEGATIVE - the corrected model's overhang gain is an "
       "OPERATING-POINT ARTEFACT (Q119) *** | - | At thr 0.509 prob_2016_corrected looks decisive: "
       "over-impervious recall 0.3183 -> 0.5612, worst cell 0.028 -> 0.183. But its call rate on "
       "C-CAP non-canopy TRIPLES (4.9% -> 17.3%). RE-THRESHOLDED TO EQUAL OVERALL RECALL the gain "
       "REVERSES: over-impervious 0.3070 (down), gap -0.3895 (wider), worst cell 0.0366 (nothing), "
       "and the matched gap is WORSE at 2-5 m (-0.076) and 5-10 m (-0.050). It moved its operating "
       "point, it did not learn overhang. DEPLOY WARNING: no comparison in this project matches "
       "operating points before claiming improvement (Q121). CAVEAT STATED: corrected from NIR+CHM, "
       "scored against C-CAP - an agreement statement, not a truth statement (Q120 settles it). "
       "Height INPUT channel v045/v046 still untested and now MORE valuable |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
