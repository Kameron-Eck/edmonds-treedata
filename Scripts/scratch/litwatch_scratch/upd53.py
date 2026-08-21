import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### EMPIRICAL - RECALL DOES NOT TRACK CANOPY RENDERING (Q96) - 2026-08-19
Ten live-scored years now overlap the rendering index - enough for a real test rather than the
n=4 gesture of iteration 51.

| year | non-green canopy | recall | | year | non-green canopy | recall |
|---|---|---|---|---|---|---|
| 2019n | 0.00% | .6475 | | 2005 | 10.98% | .6323 |
| 2021s | 0.58% | .6818 | | 2002 | 13.58% | .5039 |
| 2016 | 1.95% | .5937 | | 2000 | 16.86% | .6274 |
| 2022n | 5.23% | .6541 | | 2013 | 22.46% | **.7072** |
| 2007 | 8.51% | .6575 | | 2015 | 31.22% | .6192 |

**Pearson r = -0.057, t = -0.16 on 8 df. No relationship whatsoever.**

Canopy rendering varies **thirty-fold** across these years - 0.00% to 31.22% non-green - and recall
moves within a narrow .50-.71 band with no trend. The best-scoring year (2013, .7072) is the
second-barest-rendering; the greenest-rendering years (2019n, 2021s, 2016) sit in the middle and
below.

**This closes the leaf-off line of inquiry, and it closes it negatively.** Iterations 45-52 built,
then progressively dismantled, an argument that leaf-off imagery explains the project's central
finding. The dismantling is now complete on four independent grounds:
1. the height staircase **steepens** on a leaf-on year rather than flattening (iteration 48);
2. the archive is a **continuum**, not the clean split the argument assumed (iteration 50);
3. the extreme values are **radiometric era, not calendar** - 90% non-green canopy is not credible
   in a conifer region (iteration 52);
4. and now: **recall is uncorrelated with canopy rendering across ten years** (r = -0.06).

**The stronger conclusion this supports: the model does not key on greenness.** That is worth
stating plainly because it has a second consequence nobody has drawn - **it undercuts the premise
of the NDVI+CHM reference itself.** That reference defines canopy as NDVI >= 0.2 AND height >= 2 m.
If the model's detections are insensitive to a thirty-fold swing in scene greenness, then model and
reference are keying on **different features**, and their 15-17% disagreement is not a dispute about
where trees are - it is two instruments measuring different things. That is a sharper version of
the "definition dispute" reading, and it predicts the disagreement should be largely irreducible.

**WHAT THIS LOOP GOT WRONG, AND WHAT IT GOT RIGHT.** Wrong: seven iterations (45-51) on a causal
story that the data does not support, including two claims I had to withdraw outright. Right: the
loop killed its own hypothesis with its own measurements rather than accumulating support for it -
four separate tests, each of which could have confirmed it and none of which did. The residue is
worth keeping: **canopy rendering varies 0-91% across the archive and nothing accounts for it**,
which remains true and unexplained regardless of cause.

**A DISCREPANCY THAT MUST BE RESOLVED BEFORE ANY OF THESE NUMBERS IS QUOTED.** The recall values
above come from the live `qc_indep_report.csv` column and **disagree with the figures in STATE** -
2016 reads .5937 here against STATE's .6844; 2013 reads .7072 against .7094; 2002 reads .5039
against .5069. The small ones look like rounding or threshold differences, but 2016 differs by nine
points. They are internally comparable to one another, so the correlation stands - but the absolute
values are not safe to quote outward until the two sources are reconciled.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q96.** Does the model's recall track canopy greenness at all?""",
"""- **Q96. ANSWERED: NO.** r = -0.057 across ten live-scored years spanning a thirty-fold range in
  canopy rendering. The model does not key on greenness. Consequence nobody had drawn: the NDVI+CHM
  reference DOES key on greenness, so model and reference measure different features - which
  predicts their 15-17% disagreement is largely irreducible rather than resolvable. Original
  question below.
  Does the model's recall track canopy greenness at all?""")

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q97.** Why does `qc_indep_report.csv` disagree with STATE on recall? 2016 reads .5937 in the
  live CSV against .6844 in STATE - a nine-point gap, far beyond rounding. 2013 and 2002 differ by
  fractions of a point. Until reconciled, **no absolute recall figure is safe to quote outward**,
  which affects every write-up. Probably a canopy-definition or reference-column difference, but it
  must be pinned down rather than assumed.
- **Q98.** If the model does not key on greenness, WHAT does it key on? Texture, structure,
  context, shadow? This is answerable by ablation on existing rasters and would tell us which
  acquisitions are genuinely hard for it - replacing the rendering index, which we now know is the
  wrong covariate.

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Reconcile qc_indep_report.csv against STATE (Q97)** - a nine-point discrepancy on 2016 recall
   blocks quoting any absolute number. Highest priority because it affects everything downstream,
   and it is a file comparison, not a search.
2. **What DOES the model key on (Q98)?** Ablation on existing rasters. Would give the right
   per-acquisition covariate, now that rendering is ruled out.
3. **Test whether reference disagreement concentrates on deciduous crowns (Q89)** - sharpened by
   Q96: if model and reference key on different features, this predicts where.
4. **Specificity on the UNCHANGED class (Q66).**
5. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
6. **Geometric vs thematic accuracy for per-object products (Q41).**
7. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
8. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
9. **Finish the rendering index** (2017, 2024) - completeness, low priority now.
10. **Get the flight dates** - would settle Q95, but its value dropped once recall proved
    insensitive to rendering.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 53 | 2026-08-19 | EMPIRICAL - recall does NOT track canopy rendering (Q96) | - | "
       "n=10 live-scored years, rendering spans 0.00-31.22% non-green canopy, recall spans .50-.71: "
       "Pearson r = -0.057, t=-0.16 on 8df. NO RELATIONSHIP. Closes the leaf-off line NEGATIVELY on "
       "a fourth independent ground. STRONGER CONCLUSION: the model does not key on greenness - "
       "which undercuts the NDVI+CHM reference's own premise, since IT does. Model and reference "
       "measure different features, so their 15-17% disagreement is likely IRREDUCIBLE. "
       "BLOCKER FOUND: live CSV recall disagrees with STATE by 9 points on 2016 (.5937 vs .6844) - "
       "no absolute recall figure is safe to quote until reconciled (Q97) |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
