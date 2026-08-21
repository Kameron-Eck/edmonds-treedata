import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - THE SPLIT FOLLOWS THE SPECIFICATION, NOT THE VENDOR *** - 2026-08-19
Iteration 46 left one alternative to leaf-off: sensor colour balance. Four acquisitions from two
programs, same canopy mask, same city:

| year | source | acquisition spec | median GRVI over canopy | low-greenness fraction |
|---|---|---|---|---|
| 2019n | NAIP | **LEAF-ON** | **+0.2745** | **0.00%** |
| 2022n | NAIP | **LEAF-ON** | +0.1226 | 5.23% |
| 2022 | CoE | consortium (**leaf-off**) | +0.0485 | 16.42% |
| 2020 | CoE | consortium (**leaf-off**) | +0.0330 | **33.02%** |

**The separation is clean and it follows the SPECIFICATION.** Both NAIP acquisitions: 0.0% and
5.2%. Both consortium acquisitions: 16.4% and 33.0%. Median canopy greenness differs by up to
**8x** between programs. For colour balance to explain this, two independent NAIP flights and two
independent City of Edmonds flights would have to align with their respective published seasonal
specs by coincidence.

**AND THE WITHIN-PROGRAM VARIATION IS ITSELF EVIDENCE.** 2020 (33.0%) and 2022 (16.4%) are both
City of Edmonds, presumably the same vendor and processing chain, yet differ **two-fold**. A fixed
vendor colour balance does not do that. **A March-May acquisition window does** - early March is
fully bare, late May is substantially leafed out. Same for NAIP: 2019n at 0.0% versus 2022n at
5.2%, consistent with different dates inside a growing season. **Between-program gap large and
consistent; within-program variation consistent with date. That is the signature of season, not
of sensor.**

**THE SAME-YEAR NATURAL EXPERIMENT.** 2022 CoE (16.42%) and 2022n NAIP (5.23%) are the **same
calendar year**, same ground, two acquisitions - and they differ three-fold. Within one year, the
only candidate explanations are season and sensor, and the within-program variation above already
argues against sensor.

**AND THE UNLUCKY PART: 2020 IS THE WORST CONSORTIUM YEAR MEASURED.** Our ONE hand-labelled year -
the mask that teaches every coarse year - has the highest non-green canopy fraction of any
acquisition tested. If leaf-off severity varies with flight date inside the March-May window, 2020
looks like an early-window flight. **We labelled on the barest imagery in the archive.**

**Status of Q84: strong evidence, four independent lines.** Published specification; scene-wide
greenness ranking; canopy-conditional greenness with resolution controlled; and now
spec-aligned separation across four acquisitions from two programs with sensible within-program
variation. **Still not proof** - only a flight date is proof - but the alternative explanations have
been narrowed to one that the data now argues against.

**What this changes, restated plainly.** The project's central empirical finding - a
height-monotonic recall curve with a conifer-only blind spot that no amount of model quality moves -
is very likely a **consequence of labelling on leaf-off imagery**. That is not a modelling problem
and no modelling fix addresses it. The remedy is labels on leaf-on imagery, and the archive already
contains leaf-on years: **2019n and 2022n**, both NAIP, both already scored.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""### Answerable only by our own experiment""",
"""- **Q87.** Does leaf-off severity vary enough between acquisitions to make some consortium years
  usable and others not? 2020 shows 33.0% non-green canopy, 2022 shows 16.4% - both City of
  Edmonds. If the March-May window drives it, the later-window years may be usable for deciduous
  canopy and the early ones not. **This turns "which years can we trust" from a sensor question
  into a phenology question**, and it is measurable for all 18 with one command each.
- **Q88.** Can the NAIP years (2019n, 2022n - leaf-on, 4-band with NIR, already scored) carry the
  labelling burden instead of 2020? They are 60 cm rather than 7.5 cm, so instance-level crown work
  is out - but for the SEMANTIC canopy stream, leaf-on 60 cm may beat leaf-off 7.5 cm. That is a
  direct trade of resolution against phenology, and nobody has posed it.

### Answerable only by our own experiment""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Season-score all 18 acquisitions (Q85/Q87)** - one command each, `phase4_qc_leafoff.py`.
   Produces a leaf-off severity ranking that decides which years can support deciduous canopy at
   all, which year-pairs are valid for change, and which are safe weak-supervision pairs.
2. **Recall-by-height on a LEAF-ON year vs a leaf-off year (Q86)** - does the height staircase
   flatten on 2019n/2022n? If it does, the curve is substantially a deciduous-fraction curve.
   Both rasters already scored; this is the decisive test of what the project's central finding is.
3. **Leaf-on labelling feasibility (Q88)** - can 60 cm leaf-on NAIP replace 7.5 cm leaf-off CoE for
   the semantic stream? Resolution against phenology.
4. **Get the flight dates (Q84 proof).**
5. **Specificity on the UNCHANGED class (Q66).**
6. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
7. **Geometric vs thematic accuracy for per-object products (Q41).**
8. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
9. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
10. **Broadleaf / deciduous-specific crown segmentation.**

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 47 | 2026-08-19 | *** EMPIRICAL - the split follows the SPEC, not the vendor *** | - | "
       "Four acquisitions, same mask: NAIP 2019n 0.00% and 2022n 5.23% low-greenness (LEAF-ON spec); "
       "CoE 2022 16.42% and 2020 33.02% (consortium LEAF-OFF spec). Median canopy greenness differs "
       "up to 8x BETWEEN programs. WITHIN-program variation (2020 vs 2022, same vendor, 2x apart) is "
       "what a March-May window predicts and a fixed colour balance does not. SAME-YEAR experiment: "
       "2022 CoE vs 2022n NAIP differ 3x. AND 2020 - our ONE labelled year - is the WORST consortium "
       "year measured: we labelled on the barest imagery in the archive. New Q87/Q88 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
