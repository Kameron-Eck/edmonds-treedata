import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 28 - single-domain generalization + the Search 5 rematch - 2026-08-18 - IDs 142-144
**OUR REGIME HAS A NAME AND A LITERATURE: SINGLE DOMAIN GENERALIZATION (SDG).**
Iteration 9 concluded that nobody publishes training from one labelled year and deploying across
decades. That was right about the *temporal* framing and wrong about the *general* one. Liang et
al. 2024 (ID 142, TGRS, peer-reviewed) formalizes exactly our constraint: **train on ONE source
domain, deploy to unseen domains, with no target data at training time.** That is 2020-labels-only
across 17 other acquisitions. This is the vocabulary we should have been searching under from
iteration 1, and it partially retracts the iteration-9 conclusion - the regime is studied, just
not with a 24-year temporal axis.

**The Search 5 rematch has a verdict, and simple wins (ID 143, Yaras et al. 2024, JSTARS).**
On OVERHEAD imagery specifically, **randomized histogram matching** - match each training image to
a randomly drawn reference histogram - is competitive with GAN-based style transfer and cleaner,
because the generative route introduces artifacts and blurred patterns. That is a direct caution
against the generative options already in our tracker (StandardGAN ID 30, diffusion ID 37).

**Why this matters more than any other single finding for near-term work:** RHM needs **no new
model, no labels, no GPU budget** - only a change to the augmentation pipeline. It is the cheapest
possible test of consensus finding (a), and the 2017 matched pair (iteration 13) is a ready-made
test bed with the temporal confound removed.

**Third convergence on style-vs-content (ID 144, Wang et al. 2025, IJCV).** A lightweight style
mapper built from statistical style prototypes, separated from a category-level prototypical
contrast for content. That is now FOUR independent lines - FDA (ID 136), amplitude mixup (ID 139),
this, and RHM - all saying: **handle style separately from semantics, and prefer statistical
transfer over generative.**

**Revised ranking of what to try first on the sensor gap:**
1. **Randomized histogram matching** (ID 143) - no new model, testable this week.
2. **FDA amplitude swap** (ID 136) - also training-free, tests the same hypothesis in the
   frequency domain rather than the intensity domain.
3. **SDG with domain randomization + category consistency** (ID 142) - needs a retrain, but it is
   the method built for our exact regime.
4. Generative style transfer (IDs 30, 37) - **demoted**; Yaras 2024 says it costs artifacts for
   no advantage on overhead imagery.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

old_q2 = """  **LARGELY ANSWERED (Search 23): no.** The nearest is SpADANN (ID 134), which transfers one
  year to the SUCCESSIVE year, same area, same sensor. Our regime — 24 years, three sensors,
  one labelled year — is past the demonstrated envelope of the published literature. Frame the
  work accordingly, and treat this literature's benchmark numbers as upper bounds, not
  expectations."""

new_q2 = """  **PARTLY RETRACTED (Search 28).** Search 23's "no" was right about the temporal framing but
  wrong about the general one. The regime is called **SINGLE DOMAIN GENERALIZATION** and it has a
  literature (ID 142, TGRS 2024): train on one source domain, deploy to unseen domains, no target
  data at training time. What remains genuinely unpublished is SDG over a **24-year temporal axis
  with sensor turnover** - the axis, not the one-source constraint. Search SDG vocabulary from
  here on; searching "temporal transfer" was finding the wrong shelf."""

assert old_q2 in s, "Q2 anchor not found"
s = s.replace(old_q2, new_q2, 1)

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Single-domain generalization (SDG) proper** - now that we have the right vocabulary
   (Search 28), sweep the SDG literature specifically. Iterations 1-27 searched "domain
   adaptation" and "temporal transfer"; SDG is the shelf our problem actually sits on.
2. **Shadow / illumination / sun-angle as a distinct domain axis.** Never searched; bears on
   whether the 2017 matched pair is truly controlled (Q24).
3. **Phenology / leaf-on vs leaf-off across acquisitions.** Never examined, despite deciduous
   crowns being the known blind spot.
4. **Deep ensembles vs cheaper uncertainty under shift.**
5. **Instance segmentation of tree crowns at 7.5 cm, 2025-2026 state of the art.**
6. **Temporal consistency as a training objective** rather than a post-hoc fix.
7. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11. Retry with
   different vocabulary (efficiency, informativeness, set size).
8. **Spatially-aware pseudo-labelling specifically** - the good half of SpADANN.
9. **How the Landsat/MODIS harmonization community validates a multi-decade series** - follow
   Vogeler (ID 138) into its methodological lineage.
10. **Domain randomization for overhead imagery specifically** - the mechanism inside ID 142;
    what randomizations are known to help vs hurt on aerial data.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 16 | 2026-08-18 | Search 28 - single-domain generalization + Search 5 rematch | 142-144 | "
       "OUR REGIME HAS A NAME: single domain generalization (SDG), TGRS 2024 - partially retracts "
       "iteration 9. Search 5 rematch verdict: randomized histogram matching beats GAN style "
       "transfer on OVERHEAD imagery (artifacts) - and needs no model, no labels, no GPU. Fourth "
       "convergence on style-separate-from-content. Generative route DEMOTED |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
