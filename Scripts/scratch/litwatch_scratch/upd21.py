import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 33 - MODEL SELECTION & UNSUPERVISED ACCURACY ESTIMATION - IDs 153-154
Search 32 left us gated on one question: what is an honest selection rule when we cannot use the
target year? This iteration finds something better than a selection rule.

**AGREEMENT-ON-THE-LINE (ID 153, Baek et al., NeurIPS 2022) - estimate per-year accuracy with NO
LABELS AT ALL.** OOD agreement between the predictions of any two networks correlates linearly
with their in-distribution agreement, so out-of-distribution ACCURACY can be estimated from
unlabelled target data plus the predictions of several models.

Check it against what we already hold:

| the method needs | we have |
|---|---|
| unlabelled target data | 18 unlabelled acquisitions, city-wide |
| several trained models | 9 live per-year models, plus baseline/corrected variants on 2016 |
| in-distribution accuracy for the same models | 2020, our one labelled year |

**This is the most directly usable result in the entire loop.** It attacks the question that has
blocked the project from the beginning - *how good is the model on 2002, where no trustworthy
label exists* - and it needs no new imagery, no new labels, and no GPU beyond re-running inference
with a few model variants. It would also give us per-year numbers for the pre-2016 years that
C-CAP cannot score at all.

**And it is self-checking, which matters given how often this loop has had to caveat things.**
The phenomenon holds *whenever accuracy-on-the-line holds*, and that condition is itself testable
from unlabelled data. So the first output is not an estimate but a verdict on whether our years
are even amenable to the method. A negative result would be informative: it would say our shifts
are not of the type where ID performance predicts OOD performance, which is itself a strong
statement about the archive.

**Relation to what we already built.** `phase4_qc_flicker.py` measures disagreement of ONE model
ACROSS years. This is the orthogonal axis - agreement of SEVERAL models ON one year. The two
together would separate "the year is hard" from "the model is unstable", which nothing currently
distinguishes (open question Q7).

**On the selection rule itself (ID 154, Wang et al. 2024, SDM, peer-reviewed).** Takes up exactly
the problem Gulrajani & Lopez-Paz raised and proposes selection that never touches the target
domain. Read before we invent our own rule. The alternatives now on the table for Q33:
1. **Leave-one-era-out** - reported unbiased and better than training-domain validation, but it
   costs training data and we have one labelled year, so "era" would have to mean something other
   than a labelled domain.
2. **Agreement-on-the-line as the selection signal** - selects using unlabelled target data
   directly, and does not require any target labels.
3. **A small in-year human sample** - honest but expensive, and Search 21 showed 250 points buys
   calibration rather than discrimination.
4. **Current practice - projected 2020 labels** - carries the training signal's own bias.
   Option 4 is the one we use and the one with the clearest defect.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Ensembling / model soups for DG** - the one taxonomy family never touched, and now doubly
   relevant: agreement-on-the-line needs SEVERAL models, so an ensemble serves both purposes.
2. **Instance-norm / whitening for style removal** - architecture branch, still unfollowed.
3. **Instance segmentation of tree crowns at 7.5 cm, 2025-2026 state of the art.**
4. **Temporal consistency as a training objective.**
5. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
6. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
7. **How the Landsat/MODIS harmonization community validates a multi-decade series.**
8. **Shadow masking as IGNORE vs removal** - defensibility and area cost.
9. **Other unsupervised accuracy-estimation methods** (e.g. matrix-norm / confidence-based
   estimators) - alternatives to agreement-on-the-line if accuracy-on-the-line fails for us.
10. **Does agreement-on-the-line hold for SEGMENTATION?** It is demonstrated on classification;
    dense prediction may behave differently. Check before building on it.

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

s = s.replace("""- **Q34.** Is there a tuned ERM baseline to compare anything against?""",
"""- **Q35.** Does agreement-on-the-line hold for our archive - and for SEGMENTATION at all? The
  result is demonstrated on classification; dense prediction may behave differently, and
  "agreement" needs a definition for masks (per-pixel? per-crown? IoU-based?). The condition is
  self-testable from unlabelled data, so the first experiment produces a verdict rather than an
  estimate. **If it holds, we get per-year accuracy for 2000/2002 - the years STATE calls
  un-measurable.**
- **Q36.** Can agreement-on-the-line and the existing flicker analysis together separate "this
  year is hard" from "this model is unstable"? Flicker measures one model across years; this
  measures several models on one year. Nothing currently distinguishes the two, and the
  deliverable is a change product (Q7).
- **Q34.** Is there a tuned ERM baseline to compare anything against?""")

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 21 | 2026-08-18 | Search 33 - model selection & unsupervised accuracy estimation | 153-154 | "
       "AGREEMENT-ON-THE-LINE (NeurIPS 2022): estimate per-year OOD accuracy from UNLABELLED data + "
       "several models' predictions. We already have 18 unlabelled years and 9 per-year models. "
       "Could give numbers for 2000/2002 - the years STATE calls unmeasurable - and it is "
       "SELF-CHECKING. Orthogonal to our existing flicker metric. New Q35/Q36 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
