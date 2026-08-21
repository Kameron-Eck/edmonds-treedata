import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 44 - TEMPORAL CONSISTENCY - IDs 175-176
**THE COMPOUNDING BIAS THIS LOOP HAS BEEN ASSEMBLING WITHOUT NOTICING.**

Three separate mechanisms, found in three separate searches, all push the same way:

| mechanism | where it enters | direction |
|---|---|---|
| pseudo-labelling from the 2020 anchor mask (finding 4, ID 89) | training | toward the anchor year's state |
| anchoring in paired interpretation (ID 171, Search 42) | human reference | toward "no change" |
| temporal smoothing / HMM priors (ID 175, this search) | post-processing | toward "no change" |

**Every one of them suppresses apparent change, and the deliverable is a change product.** For a
project whose question is how much canopy has been lost, three independent no-change biases stacked
in series is a systemic risk, not three separate technical details. Nothing in the pipeline
currently measures any of them.

**HMM post-processing is the standard fix, and the standard hazard (ID 175, Abercrombie & Friedl
2016, TGRS).** Transition and emission probabilities separate real change from classification
error, and multitemporal products genuinely do exhibit unrealistic year-to-year label churn - our
flicker metric measures exactly that. The transition matrix is where domain knowledge enters:
canopy rarely appears or vanishes in a single year. **But that prior is precisely what would
suppress genuine rapid canopy LOSS** - a lot cleared, a stand removed - which is the signal a tree
ordinance is about. Adopt it only with the prior stated and its effect on real loss events measured.

**The model-side alternative (ID 176, He et al. 2024, RSE).** Segment the TEMPORAL dimension
directly rather than differencing independently classified dates. Our pipeline does the latter:
per-year masks produced independently, change inferred by comparison, so **every per-year error
becomes a candidate change event**. That is the model-side twin of the false-change problem
Search 42 found in human interpretation.

**And an asset we are not using.** Temporal-consistency losses do NOT require ground-truth labels,
so all 17 unlabelled years could contribute to TRAINING rather than only to inference. Combined
with Search 43 (lidar pseudo-labels) and Search 23 (in-archive pretraining), that is now the third
independent route by which our unlabelled archive could do more than it currently does.

**What this changes about the recommendations.** Any temporal smoothing we adopt must be paired
with a measurement of what it removes. The natural design: run the change estimate with and without
the temporal prior, and report the difference as a sensitivity - the same discipline the blind
subset provides for anchoring (Search 42). Otherwise we will produce a beautifully consistent
series that has quietly deleted the events the project exists to find.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q55.** How much real canopy LOSS would a temporal smoother delete? HMM transition priors and
  consistency losses suppress spurious change and genuine abrupt change alike, and abrupt loss -
  a cleared lot, a removed stand - is exactly the policy-relevant event. Run the change estimate
  with and without the temporal prior and report the difference as a sensitivity; never ship only
  the smoothed version.
- **Q56.** Do the three no-change biases COMPOUND? Pseudo-labelling toward the 2020 anchor,
  anchoring in paired interpretation, and temporal smoothing all push the same direction and enter
  at different stages. If they multiply rather than merely coexist, a change product could be badly
  attenuated with every individual step looking defensible. Nothing measures this, and it may be
  the most important unmeasured risk the loop has surfaced.

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Abrupt disturbance / loss detection specifically** - promoted by Q55. The literature on
   detecting rapid forest loss (LandTrendr, CCDC, disturbance mapping) is built to preserve exactly
   the events temporal smoothing deletes, and this loop has never touched it.
2. **Geometric vs thematic accuracy for per-object products (Q41).**
3. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11, deferred five
   times; retry with "efficiency / informativeness / set size".
4. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
5. **How the Landsat/MODIS harmonization community validates a multi-decade series.**
6. **Instance-norm / whitening for style removal.**
7. **Shadow masking as IGNORE vs removal.**
8. **Ladder-side-tuning and cheap foundation-model adaptation.**
9. **Broadleaf / deciduous-specific crown segmentation** - our known blind spot; a 2026 paper
   surfaced unread in Search 43.
10. **Attenuation bias in change estimation generally** - the statistical framing of Q56.

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 32 | 2026-08-18 | Search 44 - temporal consistency | 175-176 | "
       "THE COMPOUNDING BIAS: three mechanisms found in three separate searches ALL suppress "
       "apparent change - pseudo-labelling toward the 2020 anchor, anchoring in paired "
       "interpretation, and temporal smoothing/HMM priors. The deliverable IS a change product. "
       "HMM priors specifically would delete abrupt canopy LOSS, the policy-relevant event. "
       "Temporal-consistency losses need NO labels -> third route for the unlabelled archive. "
       "New Q55/Q56 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
