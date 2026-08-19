import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 46 - SPARSE / IRREGULAR SERIES - IDs 179-180
**Q57 ANSWERED, and the answer is that our series is not a series.**

Zhu 2017 (ID 179, ISPRS, review) organizes change detection by OBSERVATION FREQUENCY and makes
explicit which algorithm families each frequency supports: bi-temporal, multi-temporal, and dense
annual/sub-annual trajectory methods. Placing ourselves on that map:

| our archive | 18 acquisitions / 24 years, gaps of 2-4 years pre-2013, one per year at best |
|---|---|
| what trajectory fitting needs | dense annual or sub-annual, seasonally composited, one sensor |
| what our density supports | **epoch-pair comparison** |

And the historical-aerial literature confirms it in practice: multi-decadal aerial studies work in
**intersectional epochs** (e.g. 1957, 1980, 1994-97, 2006, 2014, 2018), with the temporal component
explicitly "on the order of a decade". Nobody fits trajectories to sparse aerial archives, because
you cannot.

**THIS IS THE FOURTH INDEPENDENT LINE ARRIVING AT PAIRS, NOT SERIES:**
1. Search 40 - absolute per-year levels inherit every source-driven offset; paired change cancels
   shared bias.
2. Search 41 - paired estimation is the only design that resolves a 2.6 pp effect at an affordable
   sample size.
3. Search 42 - cascading paired interpretation is the response design that controls false change.
4. Search 46 - the historical-aerial field itself works in epoch pairs, and our observation density
   supports nothing more.

**Four different literatures, four different reasons, same conclusion.** That is a stronger basis
for a design decision than any single result in this loop, and it argues against the standing
"18-year continuous series" framing of the deliverable. The honest product is a small number of
well-chosen, well-matched EPOCH PAIRS with intervals attached - not a continuous canopy trajectory.

**AND THE PRECONDITION HAS A METHOD (ID 180, Zhang, Rupnik & Pierrot-Deseilligny 2021, ISPRS).**
Feature matching BETWEEN EPOCHS of historical aerial imagery, where radiometry, sensor and scene
have all changed. Our Phase 3 Search 7 (IDs 21-26) covered the CONSEQUENCES of misregistration;
this is the method for reducing it on exactly our kind of archive. It matters most for the 2000/2002
King acquisitions - the era where co-registration is worst, recall is lowest, and STATE already
calls the years un-measurable.

**What this does NOT resolve.** Choosing epoch pairs requires knowing which acquisitions are
instrument-comparable, which is Q19 - still open, still blocked on acquisition dates, and still the
highest-leverage missing fact. A badly chosen pair reintroduces exactly the source-driven offset
that pairing was supposed to cancel.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q57.** Can trajectory segmentation work on 18 IRREGULAR acquisitions with 2-4 year gaps and no
  phenological compositing? LandTrendr's fitting assumes annual, composited, single-sensor series
  and we violate all three. The trajectory-with-vertices REPRESENTATION is still right for
  per-crown validity intervals; whether any published fitting method survives our sampling is
  unknown, and nothing found addresses sparse irregular high-resolution series specifically.""",
"""- **Q57.** Can trajectory segmentation work on 18 IRREGULAR acquisitions? **ANSWERED: no, and the
  field does not try.** Zhu 2017 (ID 179) ties algorithm family to observation frequency; our
  density supports EPOCH-PAIR comparison, not trajectory fitting, and multi-decadal aerial studies
  work in intersectional epochs at roughly decadal resolution. Fourth independent line arriving at
  pairs-not-series.
- **Q59.** WHICH epoch pairs? Pairing only cancels shared bias if the two acquisitions are
  instrument-comparable, which is Q19 - open, and blocked on acquisition dates. A badly chosen pair
  reintroduces the offset pairing was meant to remove. **This is now the binding question for the
  deliverable's design**, and it is answerable from the radiometric clustering plus dates.
- **Q60.** Does the per-crown validity interval survive an epoch-pair framing? The deliverable is
  specified as continuous per-crown intervals over 2000-2024, but epoch pairs give crown state at a
  handful of dates with gaps between. An interval bounded by "present in epoch A, absent in epoch B"
  is honest but coarser than the current specification implies - a scope question for Kam.""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Geometric vs thematic accuracy for per-object products (Q41)** - now the oldest unaddressed
   queue item.
2. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11, deferred six
   times; retry with "efficiency / informativeness / set size".
3. **Interval-censored / coarsened data methods** - new, from Q60. Epoch pairs give crown state at
   sparse dates, so "the tree was lost between 2013 and 2016" is an INTERVAL-CENSORED observation.
   Survival analysis handles this routinely and this loop has never touched it - and the
   deliverable is literally called a validity INTERVAL.
4. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
5. **How the Landsat/MODIS harmonization community validates a multi-decade series.**
6. **Instance-norm / whitening for style removal.**
7. **Shadow masking as IGNORE vs removal.**
8. **Ladder-side-tuning and cheap foundation-model adaptation.**
9. **Broadleaf / deciduous-specific crown segmentation** - known blind spot, still unread.
10. **Attenuation bias in change estimation** - statistical framing of Q56.

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates. It now
also gates Q59, the binding design question.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 34 | 2026-08-18 | Search 46 - sparse/irregular series | 179-180 | "
       "Q57 ANSWERED: OUR SERIES IS NOT A SERIES. Zhu 2017 ties algorithm family to observation "
       "frequency - our density supports EPOCH-PAIR comparison, not trajectory fitting, and "
       "multi-decadal aerial studies work in decadal epochs. FOURTH independent line arriving at "
       "pairs-not-series (40, 41, 42, 46) - four literatures, four reasons, same conclusion. "
       "Multi-epoch feature matching (ID 180) is the co-registration method for exactly our archive. "
       "New Q59 (which pairs?) is now the binding design question |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
