import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 43 - ANNOTATION-FREE CROWN SEGMENTATION - IDs 173-174
Annotation is our binding constraint, and Search 39 showed hand-drawn crowns inflate measured
performance. This search finds a route that avoids both problems.

**LIDAR PSEUDO-LABELS + SAM2 REFINEMENT, AT ZERO ANNOTATION COST (ID 173, Pesonen et al. 2026).**
Train an image-based crown segmentation model on pseudo-labels derived from airborne laser
scanning and refined with SAM 2, reporting better results than available general-domain models -
with no manual annotation at all.

**We already hold every input, and the vintages line up:**

| the method needs | we have |
|---|---|
| airborne lidar over the target area | 3DEP HAG CHM, `lidar_snoh_chm.tif`, 59.8% city coverage |
| high-resolution optical imagery | 2017 CoE at 7.46 cm, 2016 Snohomish at 50 cm |
| near-contemporaneous lidar and imagery | CHM is ~2016; the 2016 and 2017 acquisitions bracket it |
| SAM 2 for refinement | public weights, inference only |

So crown pseudo-labels could be generated wherever the CHM covers, refined, used to train the
instance head, and the trained model applied city-wide including the 40% with no CHM. **That is a
direct alternative to annotation-plan item 1** - the ~1-3k hand-drawn 2020 crowns currently listed
as the root fix for both heads.

**And it sidesteps the correlated-error problem, which is the deeper reason to prefer it.**
Allen et al. (ID 165) showed hand-drawn RGB crowns inflate measured performance seven-fold because
human labels and model predictions share the same RGB-based errors. **Lidar-derived crowns do not
share those errors** - they come from a different physical measurement. That makes them both a
cheaper training signal AND a less circular one, which is the same argument that made the CHM
valuable for the semantic stream.

**THE RANKING IS NOW SETTLED FOR THE INSTANCE STREAM (ID 174, Chen et al. 2025, plus Search 39).**
1. **Pseudo-label from lidar, refine with SAM2, then TRAIN** - best available without annotation.
2. **Train on coarse or noisy labels** - explicitly reported as more robust than any current
   zero-shot option. A quiet endorsement of our existing noisy-label pipeline design.
3. **Zero-shot SAM2 alone** - worst; it complements trained methods rather than replacing them,
   and does not beat a custom Mask R-CNN even with good prompts (Search 39).

Zero-shot is a REFINEMENT STAGE, not a substitute for training. That is a useful correction to the
temptation to reach for a foundation model as a shortcut.

**Honest limits.** Both are preprints. ID 173's quantitative comparison against manually-annotated
baselines is not stated in the abstract, so "outperforms general-domain models" is a weaker claim
than "matches hand annotation". Our CHM is also coarser and staler than the ALS these methods
assume - one ~2016 snapshot at 1 m, versus dense contemporaneous point clouds - and Hamraz (ID 86)
already told us understory segmentation depends on point density. Blocky CHM-derived segments are
exactly the problem SAM2 refinement is introduced to fix, so the approach may still work, but the
degradation at our CHM quality is unmeasured.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q53.** Can our ~2016 1 m CHM produce usable crown pseudo-labels, or is it too coarse and too
  stale? The methods assume dense, contemporaneous ALS; ours is a single 1 m snapshot at 59.8%
  coverage. SAM2 refinement exists precisely to fix blocky CHM segments, but the degradation at our
  CHM quality is unmeasured. **Testable cheaply on the 2017 CoE imagery**, which is near-contemporaneous
  with the CHM - and the 2017 matched pair gives a second acquisition on the same ground.
- **Q54.** Would lidar-derived crowns avoid the ID 165 inflation? They come from a different
  physical measurement than RGB, so their errors should not correlate with an RGB model's - the same
  argument that made the CHM valuable for the semantic stream. If so, pseudo-labels are not merely
  cheaper than hand annotation but LESS CIRCULAR, which reverses the usual quality assumption.

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Temporal consistency as a training objective** - the model-side counterpart to the
   false-change problem Search 42 surfaced on the human side; repeatedly deferred.
2. **Geometric vs thematic accuracy for per-object products (Q41).**
3. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11, deferred four
   times; retry with "efficiency / informativeness / set size".
4. **Spatially-aware pseudo-labelling** - the good half of SpADANN, and now doubly relevant since
   Search 43 puts pseudo-labelling back at the centre of the instance stream.
5. **How the Landsat/MODIS harmonization community validates a multi-decade series.**
6. **Instance-norm / whitening for style removal.**
7. **Shadow masking as IGNORE vs removal.**
8. **Ladder-side-tuning and cheap foundation-model adaptation.**
9. **False change in MODEL time series** - we measure flicker but have never read on suppressing
   spurious model-side transitions without suppressing real ones.
10. **Broadleaf / deciduous-specific crown segmentation** - our known blind spot, and a 2026 paper
    on "highly detailed and generalizable broadleaf crown instance segmentation" surfaced unread.

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 31 | 2026-08-18 | Search 43 - annotation-free crown segmentation | 173-174 | "
       "DIRECT ALTERNATIVE TO ANNOTATION-PLAN ITEM 1: lidar pseudo-labels + SAM2 refinement, zero "
       "manual annotation - and we hold every input, with CHM (~2016) near-contemporaneous with the "
       "2016/2017 acquisitions. Also LESS CIRCULAR than hand labels, since lidar errors do not "
       "correlate with an RGB model's (cf ID 165 seven-fold inflation). RANKING SETTLED: "
       "pseudo-label-and-train > noisy-label training > zero-shot SAM2. New Q53/Q54 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
