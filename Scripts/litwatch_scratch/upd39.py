import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 51 - CEOS PROTOCOL, READ (Section 4.3) - ID 189
Read Section 4.3 "Accounting for reference data errors" of the CEOS protocol (ID 187) directly.
It answers several of our open questions with community-endorsed guidance, and one passage
overturns a decision already written into the P3 plan.

**1. MORE POINTS DO NOT FIX A BIASED RESPONSE DESIGN - AND THE RATIO IS STARK.**
> "Increasing the size of the reference sample does not reduce the bias of the estimates
> originating from low quality response design... The estimates would converge to the wrong
> target... validation efforts should focus on improving the response design instead of adding
> more points of the same quality."

With a worked comparison: on RMSE of overall accuracy, **100 sample sites at 99% accuracy beat
10,000 sample sites at 95%**, and the protocol states plainly that it is *"worth spending 100 times
more effort on the response design than collecting 100 times more sample units."* That settles the
sizing anxiety running through Searches 21, 40, 41 and 47: our 250-750 point budget is not the
problem. **Point quality is.**

**2. IT CORRECTS THE P3 PLAN DIRECTLY.** The plan states Unsure responses are "EXCLUDED from
estimation, never coerced". The protocol says the opposite:
> "Low confidence assessment units, however, should NOT be excluded from the analysis, and
> secondary labels in uncertain cases should NOT be purposefully used to decrease the number of
> cases with disagreement between the reference classification and the map, but rather should be
> used as a measure of uncertainty of reference classification."

So: record primary + alternate + a confidence flag, keep every unit in the analysis, and use the
uncertain ones to MEASURE reference uncertainty. It also names the abuse to avoid - using alternate
labels to make the map look better - which is exactly the temptation the 77.5% -> 87.1% NLCD swing
(ID 78) creates.

**3. A STRUCTURAL FLAW IN OUR NDVI REFERENCE, STATED BY THE PROTOCOL:**
> "if the source of reference data is the same as the source of classification data... geolocation
> errors in the resulting map will be UNDERESTIMATED / NOT EVALUATED BY DESIGN."

Our NDVI+CHM reference is derived from the *same imagery* the model classifies. Therefore
**geolocation error is invisible in every NDVI-scored number we have** - not poorly measured,
structurally unmeasurable. C-CAP, being independent imagery, is the only reference that can see it.
A new and specific defect, distinct from the correlated-thematic-error problem of Search 38.

And the protocol adds that geolocation impact is greatest for high-resolution mapping (<30 m - we
are 7.5-60 cm) and that **"fragmented classes and items with a vertical structure are typically the
most affected"**. Fragmented, vertical: that is a description of urban tree crowns.

**4. THE CORRELATED-ERROR FIX HAS A CONCRETE FORM.** Correcting sensitivity/specificity assumes
conditional independence, and testing that assumption "requires a gold standard reference dataset
as a SUBSET of the main reference dataset to determine if there is a correlation between the
classification errors and the main reference dataset." So: a small near-gold-standard core inside
the ordinary sample. That is the disciplined version of the negative-control idea from Search 38,
and it is what makes the whole correction defensible.

**5. VINDICATIONS AND CALIBRATIONS.**
* Latent class analysis IS named as the model-based route when no gold standard exists (Foody 2010,
  2012) - but described as **"the subject of research"**, not settled practice. That is the fair
  calibration of the Search 37 retraction: not wrong, but research-grade.
* Radoux & Bogaert 2020 (ID 163) is cited here - our Search 38 finding is protocol-endorsed.
* Stehman 2022 (ID 100) and Xing & Stehman 2024 (ID 101) are both cited for interpreter variance -
  already in our tracker from Search 14, and the protocol prefers **interpenetrating subsampling**
  precisely because it avoids repeat interpretation.
* McRoberts 2018 (ID 189, new) shows majority-interpretation bias grows with FEWER interpreters and
  GREATER CORRELATION among them. A single interpreter is the limiting case - and is our plan.
  The protocol's preferred alternative is the **consensus interpretation approach**: independent
  labels first, then discussion of disagreements to consensus.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q71.** Our NDVI+CHM reference cannot see geolocation error AT ALL - it is derived from the same
  imagery the model classifies, so map-vs-reference geolocation error is zero by construction
  (CEOS 4.3). Every NDVI-scored figure therefore understates total error by an unknown amount, and
  the protocol notes geolocation impact is worst for high-resolution, fragmented, vertically
  structured classes - i.e. exactly urban crowns. Only C-CAP can see it. How much is it worth?
- **Q72.** Can we build a small NEAR-GOLD-STANDARD subset inside the P3 sample? The protocol says
  detecting correlation between map errors and reference errors REQUIRES one. Without it, no
  sensitivity/specificity correction is defensible - and with it, 100 excellent points may be worth
  more than 10,000 ordinary ones.
- **Q73.** Should P3 use CONSENSUS interpretation (independent labels, then discussion to consensus)
  rather than a single interpreter? McRoberts 2018 (ID 189) shows bias grows as interpreters become
  fewer and more correlated; one interpreter is the worst case on both counts. This is a resourcing
  question for Kam, not a technical one.

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

**CADENCE NOTE stands:** loop fires are queuing faster than iterations complete. Recommend a longer
interval or dynamic pacing.

1. **CEOS protocol Section 2.5 (Land cover CHANGE maps) and 3.5 (sample size / allocation)** -
   the deep-read is paying better than single-paper searches; two more sections bear directly on
   open questions Q59, Q66 and Q69.
2. **Geometric vs thematic accuracy for per-object products (Q41)** - oldest unaddressed item;
   CEOS 2.4 (categorical vs continuous fields) may also speak to it.
3. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
4. **Canopy AREA turnover vs tree-COUNT mortality** - the Q50 counterweight.
5. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
6. **Instance-norm / whitening for style removal.**
7. **Shadow masking as IGNORE vs removal.**
8. **Ladder-side-tuning and cheap foundation-model adaptation.**
9. **Broadleaf / deciduous-specific crown segmentation** - known blind spot, still unread.
10. **How the Landsat/MODIS harmonization community validates a multi-decade series.**

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 39 | 2026-08-18 | Search 51 - CEOS protocol section 4.3, read | 189 | "
       "PROTOCOL CORRECTS THE P3 PLAN: 'Unsure' must NOT be excluded - keep it, flag it, use it to "
       "measure reference uncertainty. MORE POINTS DO NOT FIX A BIASED RESPONSE DESIGN - 100 sites "
       "at 99% beat 10,000 at 95%; spend effort on point QUALITY not count. NEW STRUCTURAL FLAW: our "
       "NDVI ref shares imagery with the model, so geolocation error is UNMEASURABLE BY DESIGN - and "
       "it hits fragmented vertical classes hardest, i.e. crowns (Q71). Correlated-error correction "
       "needs a near-gold-standard SUBSET (Q72). Single interpreter is the worst case (Q73) |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
