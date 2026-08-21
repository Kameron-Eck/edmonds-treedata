import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 32 - COVERAGE AUDIT + the corrective that deflates much of this loop - IDs 151-152
Twenty iterations in, first check of what whole FAMILIES we had skipped. Two results, and the
important one argues against a lot of what this loop has been accumulating.

**THE CORRECTIVE (ID 151, Gulrajani & Lopez-Paz, ICLR 2021).** Across seven datasets, nine
algorithms and three model-selection criteria, **carefully implemented empirical risk
minimization matches or beats every domain-generalization algorithm tested.** Their sharper claim
is the one that binds us:

> a DG algorithm **without a stated model-selection strategy should be regarded as INCOMPLETE**,
> because selecting hyperparameters using target-domain data leaks the very thing you claim to
> generalize to.

**That is our unexamined weak point.** We select checkpoints on validation built from PROJECTED
2020 LABELS. That is neither honest in-domain selection nor honest out-of-domain selection - it
is selection against a proxy that carries the same bias as the training signal (finding 4). Every
per-year number we have was produced under a model-selection scheme this paper would call
incomplete.

**Read together with Brigato 2021 (ID 137), two independent canonical results now say the same
thing:** a properly tuned, properly selected plain baseline is the thing to beat, and most
published gains do not survive fair comparison. **This deflates a good part of Searches 15-31.**
The style/frequency methods (RHM, FDA, FOSMix) survive that critique better than most, because
they are augmentation changes rather than new algorithms - but they still have to be measured
against a well-tuned ERM baseline with an honest selection rule, and we do not currently have one.

**THE FAMILY WE CAN NOW CLOSE (ID 152, Khoee et al. 2024, AI Review).** Meta-learning was the one
DG family this loop had never touched. It is a poor fit for us, for structural reasons:
episodic meta-learning is built for FAST ADAPTATION given a few target examples, while DG assumes
ZERO target examples; and with few source domains the task-generation capacity collapses into
overfitting to the training tasks. **We have exactly one labelled domain - the worst case.**
Closing this family with a reason is worth as much as opening a new one.

**Coverage status against the Rafi 2024 taxonomy (ID 146):**
| family | covered? |
|---|---|
| augmentation / domain randomization | YES - Searches 28, 29 (RHM, FOSMix, SDG) |
| feature normalization | YES - Searches 27, 29 (BN/AdaBN/DSBN, IN+BN) |
| style-content disentanglement | PARTLY - Searches 24, 26, 28, 29 |
| meta-learning | CLOSED this iteration, poor fit |
| causal / invariance (IRM, V-REx) | TOUCHED - and IRM reportedly underperforms ERM on DomainBed |
| ensembling / model soups | NEVER TOUCHED |

**What this changes about the loop's own recommendations.** Before running any of the methods
this loop has surfaced, we need (a) a tuned ERM baseline and (b) a written, honest model-selection
rule that does not use the target year. Without both, any measured "gain" is uninterpretable -
the same trap our honest-measurement workstream exists to avoid, arriving from the modelling side.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Model selection under domain shift** - forced to the top by Search 32. If selecting on
   target data is cheating and selecting on projected 2020 labels is biased, what IS the honest
   rule for us? This now gates every method comparison the loop has proposed.
2. **Ensembling / model soups for DG** - the one taxonomy family never touched at all.
3. **Instance-norm / whitening for style removal** - architecture branch, still unfollowed.
4. **Deep ensembles vs cheaper uncertainty under shift** - overlaps #2; do together.
5. **Instance segmentation of tree crowns at 7.5 cm, 2025-2026 state of the art.**
6. **Temporal consistency as a training objective.**
7. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
8. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
9. **How the Landsat/MODIS harmonization community validates a multi-decade series.**
10. **Shadow masking as IGNORE vs removal** - defensibility and area cost.

**NOT a literature item, still the highest-leverage action identified:** recover the acquisition
dates (King County GIS, WA state, USDA NAIP). Collapses Q19, Q24, Q29 and the illumination axis.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

s = s.replace("""- **Q17.** [LITERATURE ANSWERED, PROJECT SIDE OPEN] What hyperparameter-tuning budget did our
  ResNet-101 baseline actually receive?""",
"""- **Q33.** What is our honest MODEL-SELECTION rule? Gulrajani & Lopez-Paz (ID 151) argue a DG
  method without one is incomplete. We select on validation built from projected 2020 labels -
  a proxy carrying the same bias as the training signal. Options: leave-one-era-out selection,
  selection on the both-agree reference subset, or selection on a small in-year human sample.
  **This gates every method comparison the loop has proposed** and is now the top open question
  on the modelling side.
- **Q34.** Is there a tuned ERM baseline to compare anything against? Two canonical results
  (IDs 137, 151) say a well-tuned, honestly-selected baseline matches most specialist methods.
  We have neither the tuning (Q17) nor the selection rule (Q33), so no measured "gain" from any
  method in Searches 15-31 would currently be interpretable.
- **Q17.** [LITERATURE ANSWERED, PROJECT SIDE OPEN] What hyperparameter-tuning budget did our
  ResNet-101 baseline actually receive?""")

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 20 | 2026-08-18 | Search 32 - coverage audit + ERM corrective | 151-152 | "
       "DEFLATES MUCH OF SEARCHES 15-31: carefully implemented ERM matches/beats every DG algorithm "
       "(Gulrajani & Lopez-Paz ICLR 2021), and a DG method without a stated MODEL-SELECTION rule is "
       "incomplete. We select on projected 2020 labels = the same bias as the training signal. "
       "Meta-learning family CLOSED (needs target examples; we have one labelled domain). "
       "Ensembling/model-soups is the one family never touched. New Q33/Q34 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
