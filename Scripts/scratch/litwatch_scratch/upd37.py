import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 49 - DIFFERENTIAL MISCLASSIFICATION & THE RARE-CLASS TRAP - IDs 185-186
Two findings, and the first destroys a piece of reassurance this project has been leaning on
implicitly.

**1. "OUR UNDER-DETECTION JUST MAKES US CONSERVATIVE" IS FALSE HERE.**
Epidemiology's standard result: **non-differential** misclassification - error rates equal across
groups - biases toward the null, which is the comforting case. **Differential** misclassification -
error rates that DIFFER between groups - "can bias results in any direction: toward, away from, or
even reversing an association."

**Ours is emphatically differential.** Recall varies from .16 to .93 across height bands, differs
between suburban and forest context, and differs across sensor eras. So if the canopy being lost is
not drawn uniformly from those strata - and it will not be, since development clears mature stands
while yard trees are removed one at a time - **the direction of the bias in our change estimate is
unknown**. We cannot claim our loss figures are conservative. That intuition has probably been
operating unstated throughout the project.

**2. THE RARE-CLASS TRAP: CHANGE PRODUCTS ARE GOVERNED BY A QUANTITY WE HAVE NEVER MEASURED.**
Foody 2013 (ID 185) shows change-area mis-estimation scales with how RARE the change class is, and
change is always rare. Taking canopy loss at 4% of pixels over an epoch and change-sensitivity 0.70
(our honest recall range):

| specificity on the UNCHANGED class | false change | true change | % of detections FALSE |
|---|---|---|---|
| 99.5% | 0.48 pp | 2.80 pp | 15% |
| 99.0% | 0.96 pp | 2.80 pp | 26% |
| 98.0% | 1.92 pp | 2.80 pp | 41% |
| **97.0%** | 2.88 pp | 2.80 pp | **51%** |
| 95.0% | 4.80 pp | 2.80 pp | 63% |

**At 97% specificity, half of all detected change is spurious.** And here is the gap: our per-year
precision (.77-.96) is measured on the **canopy** class. **Nobody has measured specificity on the
UNCHANGED class across an epoch pair** - and that, not canopy accuracy, is what governs a change
product. Every accuracy number in `qc_indep_report.csv` describes the wrong quantity for the thing
we are trying to deliver.

**3. AND CHANGE UNCERTAINTY CANNOT BE COMPOSED FROM PER-YEAR FIGURES (ID 186, Burnicki 2012).**
Misclassification propagates through change categorization with spatio-temporal interdependence;
naive variance/covariance propagation, which assumes independent per-date errors, gives biased
standard errors. Our per-year masks come from the same model with the same blind spot on the same
ground, so their errors are strongly correlated - meaning the obvious approach of combining per-year
accuracies would understate change uncertainty.

**Taken together with Search 48:** the change likelihood needs sensitivity and specificity as
inputs, those must be measured on the CHANGE classes rather than the canopy class, they are
covariate-dependent rather than scalar, and their errors are correlated across dates. None of the
four conditions is currently met.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q66.** What is our specificity on the UNCHANGED class across an epoch pair? This, not canopy
  precision, governs the change product - at 97% roughly half of detected change is spurious. Every
  figure we hold measures the canopy class instead. **Measurable directly**: take stable ground
  (both references agree canopy at both dates, or agree non-canopy) and count how often the model
  reports a transition. No new labels needed.
- **Q67.** Is our change bias conservative or not? Differential misclassification "can bias in any
  direction", and ours is differential by height, context and era. The comforting assumption that
  under-detection makes loss figures conservative is unsupported, and probably wrong if losses are
  concentrated in particular height bands or contexts - which development-driven clearing implies.
  Requires knowing WHICH strata the losses fall in, which the paired sample could answer.
- **Q68.** Can change uncertainty be composed from per-year accuracy figures? **No (ID 186)** -
  errors are spatio-temporally interdependent and naive propagation is biased. So the change
  product needs its own uncertainty estimation, not an arithmetic combination of per-year numbers.

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Accuracy assessment OF CHANGE specifically** - not of per-date maps. Search 49 shows the
   quantities we hold describe the wrong class. Olofsson 2014 (ID 69) covers change sampling; what
   this loop has never read is how change-class accuracy is estimated and reported in practice.
2. **Geometric vs thematic accuracy for per-object products (Q41)** - oldest unaddressed item.
3. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11, deferred
   seven times.
4. **Canopy AREA turnover vs tree-COUNT mortality** - the Q50 counterweight.
5. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
6. **How the Landsat/MODIS harmonization community validates a multi-decade series.**
7. **Instance-norm / whitening for style removal.**
8. **Shadow masking as IGNORE vs removal.**
9. **Ladder-side-tuning and cheap foundation-model adaptation.**
10. **Broadleaf / deciduous-specific crown segmentation** - known blind spot, still unread.

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 37 | 2026-08-18 | Search 49 - differential misclassification & rare-class trap | 185-186 | "
       "KILLS AN UNSTATED ASSUMPTION: non-differential misclassification biases toward the null, but "
       "DIFFERENTIAL misclassification biases in ANY direction - and ours is differential by height, "
       "context and era, so our loss figures are NOT provably conservative (Q67). RARE-CLASS TRAP: "
       "at 97% specificity on the unchanged class ~HALF of detected change is spurious - and we have "
       "only ever measured accuracy on the CANOPY class, never on the CHANGE class (Q66). Change "
       "uncertainty cannot be composed from per-year figures (Q68) |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
