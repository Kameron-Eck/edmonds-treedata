import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 36 - ground-truth-free evaluation OUTSIDE medical imaging - IDs 159-160
**Q40 ANSWERED, and it corrects my own enthusiasm from Search 35.**

**RCA has NOT been applied to remote sensing.** Two searches for it found only medical imaging -
cardiac MR, multi-organ, UK Biobank. No aerial or satellite application exists. That materially
raises the risk of the RCA route, on top of Q39 (our 2020 reference set is itself a biased model
mask, which is exactly the assumption RCA needs to hold).

**But remote sensing has its own answer, and WE ALREADY HAVE IT.** The RS-native method for
assessing classification quality without ground reference is **latent class analysis** -
Foody 2022, already in the tracker as **ID 80** from Search 10. Comparing the two honestly:

| | needs | our situation |
|---|---|---|
| **RCA** (ID 157) | a clean labelled REFERENCE DATABASE | we have only 2020, and it is a biased model mask (Q39) |
| **Latent class** (ID 80) | several IMPERFECT sources on the same ground | we have C-CAP, the NDVI reference, and the model |

**So the ranking flips.** Latent class is better suited to us than RCA: it is validated on our data
type, it does not require a clean reference, and the very thing that breaks RCA - biased,
disagreeing sources - is what latent class is built to exploit. Search 35 over-weighted a
medical-imaging import when the field's own tool was already sitting in our tracker from Search 10.
Prefer ID 80; hold RCA/ConfIC-RCA as the fallback, and treat their conformal framing (ID 158) as
the useful transferable idea rather than the method.

**A DISTINCTION WE MUST NOT BLUR (ID 159, Gao et al. 2017).** Remote sensing does have unsupervised
segmentation quality evaluation - scoring segments by spatial stratified heterogeneity and
autocorrelation, no ground truth needed. But it measures whether segments are well **FORMED**
(homogeneous inside, distinct from neighbours), **not whether the label is CORRECT**. It would
happily certify a cleanly delineated hedge as a good segment. Useful as a geometry QC layer on the
instance stream; useless as an accuracy substitute. An eager reading of "ground-truth-free
evaluation" invites exactly this confusion.

**And a gap in our own reporting (ID 160, Costa, Foody & Boyd 2018, RSE).** Segmentation accuracy
has two separable components - GEOMETRIC agreement and THEMATIC correctness - and our pipeline
reports only a binary canopy mask. A crown correctly detected but badly delineated scores the same
as one delineated perfectly, and the per-crown validity interval inherits that blindness. For a
per-crown deliverable that is a real omission, not a technicality.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

old_q40 = """- **Q40.** Do RCA and ConfIC-RCA transfer from medical imaging to aerial canopy at all? Both are
  TMI results on organs - compact, consistent, high-contrast structures. Urban canopy is
  fragmented, low-contrast and scale-varying. Untested, and no aerial application was found."""

new_q40 = """- **Q40.** Do RCA and ConfIC-RCA transfer to aerial canopy? **ANSWERED: no application exists.**
  Two searches found only medical imaging. Combined with Q39 (our reference set is a biased model
  mask), the RCA route is higher-risk than Search 35 implied. **The RS-native answer is latent
  class analysis - Foody 2022, already in the tracker as ID 80** - which needs several imperfect
  sources rather than one clean reference, and we have three. Prefer ID 80; keep RCA as fallback
  and borrow only its conformal framing.
- **Q41.** Should the per-crown deliverable report GEOMETRIC and THEMATIC accuracy separately?
  Costa et al. 2018 (ID 160) separates them; our binary mask conflates them, so a correctly
  detected but badly delineated crown is indistinguishable from a perfect one. For a per-crown
  product that is a real omission. What would it cost to report both?"""

assert old_q40 in s, "Q40 anchor not found"
s = s.replace(old_q40, new_q40, 1)

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Latent class analysis, applied** - it is now the preferred ground-truth-free route (ID 80)
   and has been sitting unused in the tracker since Search 10. Read it properly: what does it
   need from three imperfect sources, and does it work per-year or only pooled?
2. **Instance segmentation of tree crowns at 7.5 cm, 2025-2026 state of the art** - fine-res half
   of the two-stream plan, untouched since Phase 1A.
3. **Geometric vs thematic accuracy for per-object products (Q41)** - what do object-based
   accuracy frameworks require, and what would reporting both cost us?
4. **Temporal consistency as a training objective.**
5. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11, deferred
   three times.
6. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
7. **How the Landsat/MODIS harmonization community validates a multi-decade series.**
8. **Instance-norm / whitening for style removal** - architecture branch.
9. **Shadow masking as IGNORE vs removal.**
10. **Urban forestry / arboriculture reporting standards for canopy change** - what do cities and
    ISA require of a canopy change number? Defines what "good enough" means for the deliverable.

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 24 | 2026-08-18 | Search 36 - GT-free evaluation outside medical imaging | 159-160 | "
       "Q40 ANSWERED: RCA has NO remote-sensing application - medical only. CORRECTS iteration 23: "
       "the RS-native answer is LATENT CLASS (Foody 2022 = ID 80, already in our tracker since "
       "Search 10), which needs several IMPERFECT sources (we have 3) not one clean reference "
       "(ours is biased, Q39). Ranking flips to ID 80. Also: unsupervised RS segment evaluation "
       "measures FORM not CORRECTNESS - do not confuse them. New Q41 on geometric vs thematic |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
