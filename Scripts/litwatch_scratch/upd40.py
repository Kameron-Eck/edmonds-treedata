import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 52 - CEOS PROTOCOL, SECTION 2.5 (CHANGE MAPS), READ - ID 190
The protocol addresses our architecture directly, and cautions against exactly what we do.

**1. IT RECOMMENDS MAPPING CHANGE INDEPENDENTLY OF MAPPING LAND COVER.**
> "Ideally, the land cover change mapping should be addressed **independently** from the land cover
> mapping to avoid the impact of classification error propagation."

And the caution is explicit about our method:
> "caution needs to be exercised when monitoring land cover change based on **post-classification
> comparison** of annual or multi-temporal maps, since differencing maps with misclassification
> errors (e.g., 20% error in each map) leads to the **erroneous detection of land cover change**."

Our pipeline is post-classification comparison, and our per-year error is in exactly that 20-30%
range. This is the rare-class trap of Search 49 restated as community guidance, and it is the
protocol-level version of He et al. 2024 (ID 176, Search 44) recommending direct temporal
segmentation. **Two independent sources now say our change architecture is the one to avoid.**

**2. THE STRATIFICATION FIX IS SPECIFIC AND WE ALREADY HOLD THE PAPER.**
> "Omission errors in the maps used for stratification might have a significant impact on precision
> of area estimates for these small land cover change classes, which is somewhat mitigated by...
> splitting large sampling strata into **sub-strata, targeting areas of potential omission errors**
> (Olofsson et al., 2020)."

That is ID 169, already in our tracker from Search 41. For us the omission-prone sub-stratum is
concrete and known: the **5-15 m height band** and **suburban/ornamental context**, which hold 53%
of missed pixels and 8/8 of the inspected missed stands. This is the most specific P3 design
guidance the loop has produced.

**3. THE PERMANENT-VS-TEMPORARY QUESTION IS IN THE PROTOCOL.** Stehman & Foody 2019 (ID 71,
already ours) is cited for exactly the choice Search 41 derived from forest inventory: *"a single,
permanent set of sample units observed each year, and a different sample for each annual change
estimate, with both approaches having their advantages for different estimation objectives."*
Our Search 41 recommendation is protocol-supported - but so is the alternative, and the choice
again depends on Q69 (accuracy study or area study).

**4. AGGREGATE THE TRANSITIONS.** Rather than validating every transition type, report accuracy for
AGGREGATED transitions - "forest to any class" (loss) and "any class to forest" (gain). For a binary
canopy product that is simply canopy->non-canopy and non-canopy->canopy, which is what we want
anyway; useful confirmation that we need not stratify by transition type.

**5. A NEW INSTRUMENT FOR A QUESTION STATE HAS CARRIED OPEN (ID 190, Pontius et al. 2017).**
The protocol recommends estimating Pontius's transition metrics **from the reference sample** and
comparing them to the same metrics **from the map**. The metrics: number of change incidents; the
number of distinct classes a location takes across all time points; and the flow matrices.

**The second metric is a flicker measure.** Computing it on both the sample and the model gives the
first principled test of whether our year-to-year instability is real change or model noise -
something nothing in the pipeline currently distinguishes (Q7, open since the flicker work). It
uses the P3 sample we are already planning, so it is nearly free.

**6. AND OUR HARD FLOOR IS A RECOGNIZED GENERAL PROBLEM, NOT OUR FAILURE.**
> "For historic land cover change assessments, the data being used for mapping... are often **the
> only source of reference data**."

That is STATE's King 2000/2002 position exactly, stated by the protocol as a general condition of
historic change assessment. Worth knowing when writing up: it is a limitation of the field, not a
defect of this project.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q74.** Should change be mapped DIRECTLY rather than derived by comparing per-year masks? The
  CEOS protocol and He et al. 2024 (ID 176) now both say post-classification comparison of maps with
  20-30% error produces erroneous change. Our architecture is post-classification comparison. This
  is an architectural question, not a tuning one, and it may be the most consequential open item on
  the modelling side.
- **Q75.** Is our observed FLICKER real change or model noise? Pontius's "number of distinct classes
  a location takes across all time points" (ID 190) computed on BOTH the P3 sample and the model
  answers it directly. Nothing currently distinguishes them, the deliverable is a change product,
  and the test is nearly free once the sample exists.

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

**CADENCE NOTE stands:** loop fires queue faster than iterations complete.

1. **Direct change mapping vs post-classification comparison (Q74)** - now flagged by two
   independent sources as an architectural defect. Read the direct-change-detection literature
   (siamese / bi-temporal change networks) against our constraint of one labelled year.
2. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69, and the deep-read
   continues to pay better than single-paper searches.
3. **Geometric vs thematic accuracy for per-object products (Q41)** - oldest unaddressed item.
4. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
5. **Canopy AREA turnover vs tree-COUNT mortality** - the Q50 counterweight.
6. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
7. **Instance-norm / whitening for style removal.**
8. **Shadow masking as IGNORE vs removal.**
9. **Ladder-side-tuning and cheap foundation-model adaptation.**
10. **Broadleaf / deciduous-specific crown segmentation** - known blind spot, still unread.

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 40 | 2026-08-18 | Search 52 - CEOS section 2.5 (change maps), read | 190 | "
       "PROTOCOL CAUTIONS AGAINST OUR ARCHITECTURE: change should be mapped INDEPENDENTLY of land "
       "cover; post-classification comparison of maps with ~20% error 'leads to erroneous detection "
       "of change'. Second independent source after He 2024 (Q74). SPECIFIC P3 FIX: sub-strata "
       "targeting areas of potential OMISSION (Olofsson ID 169) = our 5-15m band + suburban context. "
       "NEW FREE INSTRUMENT: Pontius transition metrics on sample vs map tests whether our FLICKER "
       "is real change or model noise (Q75). Our 2000/02 hard floor is a recognized general problem |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
