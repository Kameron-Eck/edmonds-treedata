import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 34 - WEIGHT AVERAGING & ENSEMBLING - IDs 155-156
Last untouched taxonomy family, and it turns out to contain the cheapest experiment in the loop
after FDA - because it requires no retraining at all.

**WiSE-FT (ID 156, Wortsman et al., CVPR 2022) applies to checkpoints we already have.**
Interpolate between the PRETRAINED and the FINE-TUNED weights: `w = (1-a)*w_base + a*w_finetuned`.
Every one of our per-year models is fine-tuned from `sem_best_2020.pt`, so this is **weight
arithmetic over existing checkpoints** - no Colab training, no new imagery, no labels. Each value
of `a` can be scored with the QC scripts already built.

What it buys is a principled dial on **how far a coarse year is allowed to drift from the 2020
base**. That is precisely the failure mode behind our label-circularity concern: a year fine-tuned
hard on projected 2020 labels inherits their bias, while a year held close to base keeps whatever
generality the base had. Right now that trade-off is implicit in epochs and learning rate. WiSE-FT
makes it an explicit, sweepable parameter, evaluated post hoc.

**Model soups (ID 155, Wortsman et al., ICML 2022) solve our inference-cost problem.** Averaging
the weights of several differently-tuned fine-tunes improves accuracy AND out-of-distribution
robustness **at no extra inference or memory cost**. That matters concretely here: our full-city
inference already OOM'd at batch 160 on an A100 (v044), and a true ensemble over 18 citywide
rasters is unaffordable. A soup gives ensemble-grade robustness at single-model expense.

**And it composes with the tuning sweep Q17 already demands.** A hyperparameter search produces a
pile of runs that are normally discarded once the best is picked. Model soups say keep them and
average them. So the tuned-ERM baseline (Q34) and the soup are the same piece of work.

**One tension to design around.** Agreement-on-the-line (ID 153) NEEDS several distinct models to
measure agreement; a soup collapses them into one. Sequence matters: **train the variants, measure
agreement to estimate per-year accuracy, THEN soup for deployment.** Doing it the other way round
destroys the instrument.

**Taxonomy coverage is now complete** against Rafi 2024 (ID 146): augmentation/randomization,
normalization, style-content disentanglement, meta-learning (closed), causal/invariance (touched),
and ensembling (this iteration). Twenty-two iterations, 34 searches, no family left unexamined.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

**Taxonomy coverage is complete.** The queue is no longer "families we have not read"; it is
specific questions and adjacent literatures.

1. **Does agreement-on-the-line hold for SEGMENTATION?** (Q35) The single result that would
   unlock per-year accuracy on 2000/2002 rests on it, and it is demonstrated on classification.
2. **Instance segmentation of tree crowns at 7.5 cm, 2025-2026 state of the art** - the fine-res
   half of the two-stream plan, untouched since Phase 1A.
3. **Temporal consistency as a training objective** rather than a post-hoc fix.
4. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11, deferred
   twice; retry with vocabulary "efficiency / informativeness / set size".
5. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
6. **How the Landsat/MODIS harmonization community validates a multi-decade series** - follow
   Vogeler (ID 138) into its methodological lineage.
7. **Instance-norm / whitening for style removal** - architecture branch, repeatedly deferred.
8. **Shadow masking as IGNORE vs removal** - defensibility and area cost.
9. **Other unsupervised accuracy estimators** - fallbacks if accuracy-on-the-line fails for us.
10. **Urban forestry / arboriculture literature on canopy change reporting standards** - never
    searched; what do cities and ISA actually require of a canopy change number?

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q37.** What is the right WiSE-FT interpolation for each year - and does the optimum vary
  systematically with how far that year's imagery sits from 2020? If it does, the interpolation
  coefficient becomes a measurable proxy for domain distance, and it is derivable from checkpoints
  we already hold. Cheapest untried experiment in the loop.
- **Q38.** Do we still have the discarded runs from earlier sweeps? Model soups (ID 155) turn a
  hyperparameter search's rejects into ingredients rather than waste. If `checkpoints/` retained
  them, part of the soup is already paid for; if not, Q17's tuning sweep should be run in a way
  that keeps them.

### Known unknowns we are choosing to live with""")

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 22 | 2026-08-18 | Search 34 - weight averaging & ensembling | 155-156 | "
       "WiSE-FT applies to checkpoints WE ALREADY HAVE - interpolate sem_best_2020 with each "
       "per-year fine-tune, pure weight arithmetic, no retraining, scored by existing QC. Makes "
       "label-circularity drift an explicit sweepable dial. Model soups give ensemble robustness "
       "at ZERO extra inference cost (we OOM'd at batch 160). TAXONOMY COVERAGE NOW COMPLETE. "
       "Tension: measure agreement BEFORE souping. New Q37/Q38 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
