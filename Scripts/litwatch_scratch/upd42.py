import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 54 - WEAK TEMPORAL SUPERVISION - ID 193
Search 53 said STAR solves our label shortage but not our domain shift, and that the two would have
to be composed. **This method composes them itself, and it fits our asset list better.**

**The mechanism (ID 193, Bou et al. 2026, preprint).** Uses *additional temporal observations of an
existing single-temporal labelled dataset, with no new annotations*, on two assumptions:
* pairs from the **SAME location across dates** predominantly contain **no real change**;
* pairs from **DIFFERENT locations** synthesise **change examples**.

We hold precisely those inputs - one labelled year plus seventeen unlabelled acquisitions of the
same city - and STAR ignores the second entirely.

**Why this is the best modelling-side fit the loop has produced.** A same-location cross-era pair
teaches the model: *these two images look very different, and yet nothing changed.* That is exactly
the sensor/era **invariance** that Searches 15-31 spent thirty iterations identifying as the core
problem. **The radiometric shift stops being a nuisance to normalise away and becomes the training
signal for invariance.** One mechanism, both problems - which Search 53 concluded would need two.

**BUT THE ASSUMPTION IS GAP-DEPENDENT, AND OUR GAPS ARE LONG.** "Predominantly no change" holds
over short intervals and fails over decades. Taking 2-4% point-level canopy turnover per year:

| gap | @2%/yr | @4%/yr | verdict | our pairs |
|---|---|---|---|---|
| 1 yr | 2% | 4% | SAFE | 2019-2020, 2021-2022 |
| 2 yr | 4% | 8% | SAFE | 2015-2017, 2020-2022 |
| 3 yr | 6% | 12% | SAFE | 2013-2016, 2017-2020 |
| 4 yr | 8% | 15% | marginal | 2005-2009 |
| 8 yr | 15% | 28% | marginal | 2005-2013 |
| 13 yr | 23% | 41% | **violated** | 2000-2013 |
| 20 yr | 33% | 56% | **violated** | 2000-2020 |

**So the design writes itself:** train the invariance on SHORT-gap pairs, where the no-change
assumption is safe, and *deploy* across the long gaps. That is attractive because our short-gap
pairs are also our cross-source pairs - 2019(King)/2020(CoE), 2020(CoE)/2021(King),
2016(Snoh)/2017(CoE) - so the training material spans agencies and radiometric clusters while
remaining genuinely unchanged on the ground. **The 2017 matched pair (iteration 13) is the extreme
case: zero temporal gap, maximum sensor difference - the perfect weak-supervision example.**

**Honest limits.** Preprint, January 2026. Demonstrated on FLAIR and IAILD (buildings/land cover in
France), not canopy - so Q76's fuzzy-crown objection from Search 53 applies here too. The
"different locations = change" synthesis has the same object-centric flavour that suits buildings
better than crowns. And the turnover rates above are our own estimates, not measured (Q50 again).

**Modelling-side summary after 42 iterations.** Three routes, honestly ranked for our constraint:
1. **Weak temporal supervision (ID 193)** - uses one labelled year AND the unlabelled archive,
   addresses label shortage and era invariance together. Preprint, unproven on canopy.
2. **STAR / ChangeStar (ID 191)** - peer-reviewed IJCV, uses the labelled year only, does not
   address era shift; would need composing with frequency-domain augmentation (ID 145).
3. **Keep differencing per-year masks** and fix them individually - incremental, uses existing
   code, but both CEOS and He 2024 say the differencing step itself manufactures change.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q77.** Can single-temporal change supervision be COMPOSED with era-shift handling? STAR's
  pseudo-pairs come from one acquisition, so the model never sees cross-era radiometry - it solves
  the label shortage, not the domain shift. Combining it with frequency-domain style augmentation
  (FOSMix, ID 145) is the obvious move and is untested by anyone.""",
"""- **Q77.** Can single-temporal change supervision be COMPOSED with era-shift handling?
  **Search 54 suggests it need not be composed - one method does both.** Weak temporal supervision
  (ID 193) trains on same-location cross-era pairs labelled "no change", which is directly a lesson
  in sensor invariance. Still preprint and unproven on canopy.
- **Q78.** At what temporal gap does "same location, predominantly unchanged" break for Edmonds
  canopy? Our estimate says safe to ~3 years, violated by ~13. That threshold determines which of
  our 18 acquisitions can serve as weak-supervision training pairs - and it depends on the real
  turnover rate, which is Q50, still unmeasured. **The two questions should be answered together.**
- **Q79.** Is the 2017 matched pair (iteration 13) the ideal weak-supervision example? Zero temporal
  gap, maximum sensor difference, same ground - by construction it is "looks different, nothing
  changed". If weak temporal supervision is pursued, that pair is the cleanest training and
  validation material we own, and it was sitting uncatalogued until iteration 13.""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Measure the real turnover rate (Q50/Q78)** - it now gates BOTH the paired-sample size and
   which acquisitions can serve as weak-supervision pairs. Computable from the P2 partition on
   existing rasters, no labels needed. **Highest-value item on the list and it is not a search.**
2. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
3. **Geometric vs thematic accuracy for per-object products (Q41)** - oldest unaddressed item.
4. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
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
s2 += ("\n| 42 | 2026-08-19 | Search 54 - weak temporal supervision | 193 | "
       "BEST MODELLING-SIDE FIT YET: uses one labelled year PLUS unlabelled repeat acquisitions - "
       "same-location cross-era pairs labelled 'no change' teach exactly the SENSOR INVARIANCE that "
       "30 iterations identified as our core problem. The radiometric shift becomes the training "
       "signal instead of a nuisance. ONE mechanism for both problems, where Search 53 needed two. "
       "GAP-DEPENDENT: assumption safe to ~3yr, violated by ~13yr -> train on short-gap CROSS-SOURCE "
       "pairs, deploy across long gaps. The 2017 matched pair is the ideal example (Q79) |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
