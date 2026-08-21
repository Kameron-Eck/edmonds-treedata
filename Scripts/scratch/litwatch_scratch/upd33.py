import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 45 - TRAJECTORY SEGMENTATION & DISTURBANCE - IDs 177-178
Searches 41-42 reasoned their way to a paired, trajectory-based interpretation protocol and then
worried about how to build it. **It already exists, is operational, and validates USFS/LCMAP.**

**TIMESYNC IS THE PROTOCOL WE DERIVED (ID 177, Cohen, Yang & Kennedy 2010, RSE).** An interpreter
works a sample point's ENTIRE TRAJECTORY across all dates at once, assigning change SEGMENTS rather
than classifying each date in isolation. That is the cascading design of Search 42 and the paired
estimator of Search 41, in a mature form with a documented workflow, used operationally for Landsat
validation. It also connects to Pengra 2020 (ID 99), already in our tracker from Search 14 - LCMAP
QC is the same family.

**So the Phase 3 redesign does not need inventing, it needs adopting** - with the Search 42
safeguards added, since TimeSync is trajectory-based and therefore anchoring-exposed by
construction. That is the one thing the established protocol does not solve for us.

**LANDTRENDR GIVES THE RIGHT DATA STRUCTURE, PROBABLY NOT THE RIGHT ALGORITHM (ID 178, Kennedy,
Yang & Cohen 2010).** It segments each pixel's trajectory into straight-line pieces with explicit
**vertex years**, representing abrupt disturbance and gradual recovery together. That is
structurally what a per-crown validity interval wants: **a trajectory with breakpoints, not a
smoothed series** - and it is the direct answer to Search 44's worry that smoothing deletes the
events we care about. Trajectory segmentation preserves abrupt change by design rather than
penalising it.

**But our sampling violates its assumptions, on three counts:**

| LandTrendr assumes | we have |
|---|---|
| yearly observations | 18 acquisitions over 24 years, gaps of 2-4 years pre-2013 |
| seasonal compositing to control phenology | one acquisition per year at best; no compositing possible |
| a consistent sensor across the series | four agencies, multiple contractors (iteration 11) |

Its acknowledged blind spot is phenology - handled upstream by compositing - which is precisely the
Search 30 problem we cannot solve the same way. **Adopt the trajectory-with-vertices framing;
do not assume the fitting machinery survives our sampling.**

**A useful reassurance and a useful warning from the same search.** Reassurance: the per-crown
matching approach - track annual tree-centre predictions and flag losses - is already in our
tracker as Ventura et al. (ID 7), so the urban method exists. Warning: fine-scale tree-loss
detection is dominated by **multi-temporal misalignment**, which Phase 3 Search 7 (IDs 21-26)
already covers - meaning the co-registration work is not a side quest but a precondition for any
per-crown change claim.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q57.** Can trajectory segmentation work on 18 IRREGULAR acquisitions with 2-4 year gaps and no
  phenological compositing? LandTrendr's fitting assumes annual, composited, single-sensor series
  and we violate all three. The trajectory-with-vertices REPRESENTATION is still right for
  per-crown validity intervals; whether any published fitting method survives our sampling is
  unknown, and nothing found addresses sparse irregular high-resolution series specifically.
- **Q58.** Should Phase 3 simply adopt TimeSync rather than build a new interpretation tool? It is
  operational, documented, and underpins LCMAP validation - and STATE's plan currently specifies
  reusing the `phase4_label_review.py` server pattern instead. Adopting a validated protocol would
  also make our numbers comparable to a body of existing work, which a bespoke tool never will be.

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Change detection on SPARSE / IRREGULAR high-resolution series (Q57)** - the gap LandTrendr
   and CCDC leave. Everything mature assumes dense annual satellite data; our 18 irregular aerial
   acquisitions are the awkward middle case and nothing found addresses them.
2. **Geometric vs thematic accuracy for per-object products (Q41).**
3. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11, deferred five
   times; retry with "efficiency / informativeness / set size".
4. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
5. **How the Landsat/MODIS harmonization community validates a multi-decade series.**
6. **Instance-norm / whitening for style removal.**
7. **Shadow masking as IGNORE vs removal.**
8. **Ladder-side-tuning and cheap foundation-model adaptation.**
9. **Broadleaf / deciduous-specific crown segmentation** - our known blind spot, still unread.
10. **Attenuation bias in change estimation** - the statistical framing of Q56's compounding
    no-change biases.

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 33 | 2026-08-18 | Search 45 - trajectory segmentation & disturbance | 177-178 | "
       "THE PROTOCOL WE DERIVED ALREADY EXISTS: TimeSync (RSE 2010) has interpreters work a point's "
       "whole TRAJECTORY across all dates - operational, documented, underpins LCMAP validation. "
       "Adopt rather than invent (Q58). LandTrendr gives the right DATA STRUCTURE for per-crown "
       "intervals - trajectory with VERTEX YEARS, preserving abrupt change by design - but assumes "
       "yearly, composited, single-sensor data and we violate all three. New Q57/Q58 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
