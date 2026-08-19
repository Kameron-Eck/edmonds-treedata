import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 35 - SEGMENTATION QUALITY WITHOUT GROUND TRUTH - IDs 157-158
Q35 asked whether agreement-on-the-line transfers from classification to segmentation. The honest
answer is that nothing found demonstrates it for dense prediction - **but segmentation has its own,
older, better-suited instrument, and we had not looked for it.**

**Reverse Classification Accuracy (ID 157, Valindria et al. 2017, IEEE TMI).** Predicts a
segmentation quality score (Dice) for an image with NO ground truth: train a classifier using that
image's own predicted mask as pseudo-truth, then test it against a small reference database that
does have labels. If the prediction was good, the reverse classifier does well on the reference
set; if it was poor, it fails. **Its single requirement - a small labelled reference set - is
exactly what we have in 2020.**

**ConfIC-RCA (ID 158, Cosarinsky et al. 2025, IEEE TMI) joins the two threads this loop has been
developing separately.** It combines RCA with **split conformal prediction**, so the output is a
**prediction INTERVAL on segmentation quality** - the true score lies inside with a user-specified
probability - rather than a point estimate. It also adds retrieval-augmented reference selection,
so it needs minimal reference data.

That is our deliverable's own statistical shape, applied one level up:

| level | quantity | instrument |
|---|---|---|
| per crown | temporal validity interval | conformal / risk control (Searches 18-21) |
| per YEAR | segmentation quality interval | ConfIC-RCA (this search) |

**Why this may be the best-fitting result of the whole loop.** STATE calls King 2000/2002
"un-trainable AND un-measurable" - a hard floor, to be shipped LOW-CONFIDENCE with no number.
Between Barber 2023 (ID 125, coverage with a stated penalty) and ConfIC-RCA, we now have two
independent routes to replacing "no number" with "a bounded number and an honest interval". That
converts the hard floor from a silence into a measurement.

**The caveat is real and must ride with it.** Both are medical-imaging results. Transfer to aerial
canopy is untested, and RCA's reference database would need to span our land-cover variety -
suburban, forest, water, impervious - not a handful of sites. Our 2020 labels are training-site
footprints plus a citywide model mask, which is not obviously the right reference set. Whether RCA
survives that is an experiment, not a reading question.

**Also surfaced:** a Segmentation Performance Evaluator line reporting ~0.956 correlation between
estimated and true metrics across six datasets and six metrics, including Dice and HD95. Worth
following as an alternative if RCA's reference-set requirement proves awkward.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

old_q35 = """- **Q35.** Does agreement-on-the-line hold for our archive - and for SEGMENTATION at all? The
  result is demonstrated on classification; dense prediction may behave differently, and
  "agreement" needs a definition for masks (per-pixel? per-crown? IoU-based?). The condition is
  self-testable from unlabelled data, so the first experiment produces a verdict rather than an
  estimate. **If it holds, we get per-year accuracy for 2000/2002 - the years STATE calls
  un-measurable.**"""

new_q35 = """- **Q35.** Does agreement-on-the-line hold for SEGMENTATION? **PARTLY ANSWERED (Search 35): no
  demonstration found for dense prediction** - but segmentation has its own instrument, reverse
  classification accuracy (ID 157), which is purpose-built for it and needs only a small labelled
  reference set. Prefer RCA over agreement-on-the-line for our case; keep agreement-on-the-line as
  the cross-check, since the two fail for different reasons.
- **Q39.** Is our 2020 label set a valid RCA reference database? RCA needs reference images that
  span the target variety. Ours are training-site footprints plus a citywide MODEL mask - which
  carries the finding-4 bias. A reference set built from biased masks would return optimistic
  quality scores for exactly the years that share the bias. This is the load-bearing question for
  the whole RCA route.
- **Q40.** Do RCA and ConfIC-RCA transfer from medical imaging to aerial canopy at all? Both are
  TMI results on organs - compact, consistent, high-contrast structures. Urban canopy is
  fragmented, low-contrast and scale-varying. Untested, and no aerial application was found."""

assert old_q35 in s, "Q35 anchor not found"
s = s.replace(old_q35, new_q35, 1)

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Ground-truth-free segmentation evaluation OUTSIDE medical imaging** - RCA and ConfIC-RCA are
   both TMI results (Q40). Does anyone do this on aerial or satellite imagery? If nobody does,
   that is a finding and it raises the risk of the whole route.
2. **Instance segmentation of tree crowns at 7.5 cm, 2025-2026 state of the art** - fine-res half
   of the two-stream plan, untouched since Phase 1A.
3. **Temporal consistency as a training objective** rather than a post-hoc fix.
4. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11, deferred
   three times now; retry with "efficiency / informativeness / set size".
5. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
6. **How the Landsat/MODIS harmonization community validates a multi-decade series.**
7. **Instance-norm / whitening for style removal** - architecture branch, repeatedly deferred.
8. **Shadow masking as IGNORE vs removal** - defensibility and area cost.
9. **Urban forestry / arboriculture reporting standards for canopy change** - what do cities and
   ISA actually require of a canopy change number? Never searched, and it defines what "good
   enough" means for the deliverable.
10. **Segmentation Performance Evaluator and similar estimators** - alternatives to RCA if the
    reference-set requirement proves awkward.

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 23 | 2026-08-18 | Search 35 - segmentation quality without ground truth | 157-158 | "
       "Q35: no agreement-on-the-line demo for dense prediction, BUT segmentation has its own "
       "instrument - Reverse Classification Accuracy (TMI 2017), needing only a small labelled "
       "reference set (we have 2020). ConfIC-RCA (TMI 2025) adds SPLIT CONFORMAL -> a prediction "
       "INTERVAL on segmentation quality. Second route (with Barber 2023) to replacing 'no number' "
       "for 2000/2002 with a bounded one. Both are MEDICAL results; transfer untested. New Q39/Q40 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
