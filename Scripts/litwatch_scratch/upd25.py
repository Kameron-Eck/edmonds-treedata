import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 37 - LATENT CLASS, READ PROPERLY - IDs 161-162
Latent class analysis has been this loop's recommended escape from "we cannot tell which reference
is right" since Search 17, was promoted again in Search 36, and had never been examined past its
abstract. Read properly, **it does not work on three sources, and our three are the wrong three.**

**1. THREE SOURCES AND TWO CLASSES IS JUST-IDENTIFIED - FITTABLE BUT UNTESTABLE.**
Three binary indicators give 2^3 - 1 = 7 free cells; the model estimates 3 sensitivities, 3
specificities and 1 prevalence = 7 parameters. **Zero degrees of freedom.** It will always fit
perfectly and no goodness-of-fit test is possible. We have exactly three sources: C-CAP, the
NDVI+CHM reference, and the model.

**2. CONDITIONAL DEPENDENCE BIASES IT IN THE DIRECTION THAT FLATTERS US (ID 161).**
When sources are correlated but independence is assumed, the correlated tests' SENSITIVITIES are
OVERESTIMATED (median bias +0.094) and prevalence plus the uncorrelated tests' specificities are
underestimated. Our correlated pair is obvious: **the model was trained on labels derived from the
same imagery and the same NDVI+CHM logic as the NDVI reference**, and after the v042 overlay that
reference literally supplied training labels. A naive latent class fit would inflate exactly that
pair's apparent recall. **It would tell us what we want to hear**, which is the one outcome our
honest-measurement workstream exists to prevent.

**3. AND WE COULD NOT DETECT THE PROBLEM (ID 162).** Residual correlation plots and pairwise
G2/chi-square identified the genuinely correlated pair only **10-12%** of the time, while falsely
flagging an innocent pair **50-65%** of the time, and caught overall lack of fit in only about
two-thirds of cases. So neither assuming independence nor testing for its violation is safe.

**Net: the latent-class route as scoped is unfalsifiable and biased toward optimism.** That is a
retraction of guidance this loop gave three times (Searches 17, 36, and by implication 10).

**THE CONSTRUCTIVE VERSION - GET A FOURTH, GENUINELY INDEPENDENT SOURCE.** With four indicators the
model gains degrees of freedom, fit becomes testable, and conditional-dependence formulations
become estimable. Candidates, ranked by independence from the existing three:
1. **The P3 human photo-interpretation sample** - genuinely independent of imagery-derived logic,
   and it is already planned. This is the strongest argument yet for running P3, and it reframes
   its purpose: not only calibration (Search 17) but the fourth indicator that makes latent class
   identifiable at all.
2. **The CHM alone**, thresholded as a height-only canopy test - shares the CHM with the NDVI
   reference, so only partly independent.
3. **A second model of a different family** trained without NDVI-derived labels.
4. **C-CAP 2021 as distinct from C-CAP 2016** - cheap, but shares C-CAP's definitions, so it is
   nearly a repeat of the same test rather than a new one.

**This is the third time the loop has deflated its own recommendation** (Search 20 on DG methods,
Search 36 on RCA, now this). The pattern is worth naming: the promising result usually assumes
something our archive violates, and the violation is usually CORRELATED ERRORS between things we
treat as independent.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Instance segmentation of tree crowns at 7.5 cm, 2025-2026 state of the art** - fine-res half
   of the two-stream plan, untouched since Phase 1A and now the oldest gap.
2. **Geometric vs thematic accuracy for per-object products (Q41).**
3. **Temporal consistency as a training objective.**
4. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
5. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
6. **How the Landsat/MODIS harmonization community validates a multi-decade series.**
7. **Instance-norm / whitening for style removal.**
8. **Shadow masking as IGNORE vs removal.**
9. **Urban forestry / arboriculture reporting standards for canopy change** - defines what "good
   enough" means for the deliverable; never searched.
10. **Correlated-error methods generally** - the recurring reason this loop's recommendations
    fail. Is there a literature on estimating accuracy when ALL available references share a
    common cause? Foody 2010 (ID 79) touched it; nothing since has been read on it directly.

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q42.** What is our FOURTH independent source? Latent class needs four indicators to be
  testable, and the P3 human sample is the only candidate genuinely independent of imagery-derived
  logic. This reframes P3's purpose a second time: Search 17 made it a calibration set rather than
  an arbiter; this makes it the indicator that renders latent class identifiable at all.
- **Q43.** Is there a method for estimating accuracy when ALL available references share a common
  cause? This loop has now deflated three of its own recommendations (DG methods, RCA, latent
  class) and the reason was the same each time: correlated errors between sources we treat as
  independent. That recurring failure deserves a search of its own.

### Known unknowns we are choosing to live with""")

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 25 | 2026-08-18 | Search 37 - latent class read properly | 161-162 | "
       "RETRACTS guidance given 3x: with THREE sources and two classes the model is JUST-IDENTIFIED "
       "(zero df, unfalsifiable), and conditional dependence OVERESTIMATES the correlated pair's "
       "sensitivity (+0.094) - our correlated pair is model+NDVI-ref, so it would flatter exactly "
       "what we doubt. Detection tools find the right pair only 10-12% of the time. FIX: a FOURTH "
       "independent source = the P3 human sample. New Q42/Q43 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
