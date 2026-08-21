import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 39 - CROWN INSTANCE SEGMENTATION, SAM ERA - IDs 165-166
Oldest gap in the queue: the fine-resolution instance stream had no update since Phase 1A. Two
findings, and the first is a warning about work the project has already committed to.

**MANUAL CROWN LABELS INFLATE MEASURED PERFORMANCE SEVEN-FOLD (ID 165, Allen et al. 2025).**
Validated against terrestrial laser scanning rather than hand-drawn labels, crown segmentation
performance collapses:

| evaluated against | AP50 |
|---|---|
| manual labels (Mediterranean) | 0.670 |
| **TLS ground truth (Mediterranean)** | **0.094** |
| TLS ground truth (boreal) | 0.142 |
| TLS, at IoU 0.75 (any) | max 0.051 |

The mechanism is the one Search 38 named: **human RGB labels and model predictions share the same
systematic errors**, so scoring against them measures agreement, not accuracy. That is
correlated-reference error (ID 163) arriving in the instance stream.

**This bears directly on annotation-plan item 1** - the ~1-3k hand-drawn 2020 crowns, listed as
the root fix for both heads. Those labels will inflate measured instance performance, and the
collapse is concentrated in **localization** (AP at IoU 0.75 near zero), which is precisely the
geometric-versus-thematic distinction of Q41. Detection can look fine while delineation is poor.

**Do not over-transfer the magnitude.** This is CLOSED-CANOPY forest. Much of Edmonds is
open-grown suburban crowns with visible gaps between them, which are far easier to delineate and
where hand labels are far more trustworthy. The mechanism transfers; the seven-fold figure almost
certainly does not. But the visual grounding says our missed stands are suburban/ornamental - the
easy-delineation case - so the inflation may bite hardest exactly where we are least worried, and
least where we are most.

**THE CURRENT REFERENCE POINT (ID 166, Huang et al. 2026, Remote Sensing, peer-reviewed).**
Tree-SAM: city-scale individual tree detection on SAM with **ladder-side-tuning**, reporting
**F1 0.830 / AP@50 0.526 in the URBAN scenario** versus 0.762/0.478 in forest - better in cities,
which is our setting. Ladder-side-tuning is the practically important part: it adapts a foundation
model **without backpropagating through it**, which is the difference between feasible and
infeasible on our Colab budget.

**And a negative result consistent with Search 32.** SAM used OUT OF THE BOX does not beat a custom
Mask R-CNN even with well-designed prompts. The adaptation is doing the work, not the foundation
model - the same lesson as ERM-with-tuning beating specialist DG methods.

**Also noted, not yet pursued:** Mask2Former beats Mask R-CNN by up to ~3.8% on tree instances
(modest), and training-free flow-based approaches (Cellpose-SAM lineage) come within ~2% of
supervised models with NO instance annotations - interesting given that annotation is our binding
constraint.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Urban forestry / arboriculture reporting standards for canopy change** - defines what "good
   enough" means for the deliverable, and 27 iterations in it has still never been searched. The
   loop has been optimizing without knowing the target.
2. **Training-free / annotation-free crown segmentation** - flow-based and Cellpose-SAM lineage
   came within ~2% of supervised without instance labels; annotation is our binding constraint.
3. **Geometric vs thematic accuracy for per-object products (Q41)** - sharpened by ID 165, where
   the collapse was in localization specifically.
4. **Temporal consistency as a training objective.**
5. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
6. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
7. **How the Landsat/MODIS harmonization community validates a multi-decade series.**
8. **Instance-norm / whitening for style removal.**
9. **Shadow masking as IGNORE vs removal.**
10. **Ladder-side-tuning and other cheap foundation-model adaptations** - the budget-feasible
    branch of the FM question, surfaced by ID 166.

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q46.** How much do our hand-drawn 2020 crowns inflate measured instance performance? Allen
  et al. (ID 165) report seven-fold in closed canopy; Edmonds is largely open-grown suburban, where
  hand labels are more trustworthy. Unknown for us, and it decides whether annotation-plan item 1
  produces a real fix or a flattering number. A partial check exists without TLS: compare
  hand-drawn crowns against CHM-derived crown segments on the same ground.
- **Q47.** Is annotation actually our binding constraint, given training-free crown segmentation
  now comes within ~2% of supervised models? If so, part of the annotation plan may be avoidable -
  but the ~2% figure is on forest benchmarks, not suburban ornamentals.

### Known unknowns we are choosing to live with""")

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 27 | 2026-08-18 | Search 39 - crown instance segmentation, SAM era | 165-166 | "
       "WARNING ON WORK ALREADY COMMITTED: manual crown labels inflate AP50 SEVEN-FOLD vs TLS truth "
       "(0.670 -> 0.094), collapse concentrated in LOCALIZATION - correlated-error again, now in the "
       "instance stream, bearing on annotation-plan item 1. Caveat: closed canopy, ours is largely "
       "open-grown. Tree-SAM (peer-reviewed) is the urban reference point, F1 0.830, and "
       "LADDER-SIDE-TUNING adapts an FM without backprop through it = Colab-feasible. SAM "
       "out-of-the-box still loses to custom Mask R-CNN. New Q46/Q47 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
