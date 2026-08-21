import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - THE CITY-CLIPPED REFERENCE CHANGES THE HEADLINE NUMBER *** - 2026-08-19
Built `ccap_2016_edmonds.tif` by clipping the county-wide C-CAP to `Edmonds Boundry.shp`
(`Scripts/phase4_build_ccap_city.py`). First reference in this project whose footprint is the
deliverable's footprint: 24.65 km2, 5825 x 9122 @ 1 m.

**RESULT:**

| footprint | share of city | C-CAP 2016 canopy |
|---|---|---|
| old rectangle (what everything has used) | ~80% + non-city area | **29.5%** (STATE) |
| city ∩ south of the old clip's north edge | 81.5% | **32.30%** |
| **WHOLE CITY** | **100%** | **36.05%** |

**The omitted northern fifth is 52.58% canopy against the evaluated south's 32.30% - a difference
of +20.28 pp.** The omission was not merely a smaller sample. **It was a strongly biased one**, and
it removed the most forested part of Edmonds from every figure the project has produced.

**THIS UNDERCUTS A THREAD THAT HAS RUN FOR TWENTY ITERATIONS.** The "references disagree by 8.2 pp"
finding - C-CAP 29.5% against the NDVI reference's 37.7%, which drove iterations 28, 29, 44 and the
whole *which reference is right* line - **was comparing two different footprints**:
* C-CAP's 29.5% came from a rectangle covering ~80% of the city, missing its most forested fifth;
* the NDVI reference's 37.7% was computed over the Snohomish imagery extent, which the catalog
  records as covering **66.7%** of the city.

**Neither was citywide, and neither was the same area as the other.** Properly clipped, C-CAP 2016
gives **36.05%** - within 1.7 pp of the NDVI reference's 37.7%, not 8.2 pp away. **A large part of
what we have been calling a definitional dispute between references may simply be a footprint
mismatch.**

**AND THE POLICY-RELEVANT NUMBER MOVES A LONG WAY.** The comparison this project ultimately feeds -
a 32.4% baseline and a 35%-by-2036 goal - has been set against a C-CAP figure of 29.5%. Scoped to
the actual city, C-CAP 2016 reads **36.05%**. That is a 6.5 pp shift from footprint alone, **two and
a half times the size of the entire decadal policy effect** this loop computed in iteration 28.

**CAVEATS, AND THEY ARE NOT SMALL.**
* This is C-CAP's opinion, not ground truth. C-CAP hi-res carries ~84% regional overall accuracy and
  was never validated at single-pixel scale (ID 77) - and the same document says it should be used
  as a screening tool for local decisions.
* One reference, one year. No uncertainty interval attached.
* The canopy definition is C-CAP's forest + forested-wetland classes, which is not the same
  definition a municipal canopy goal uses - and iteration 1 of the P3 assessment already flagged
  that we have never written our own definition down (Q1, still open).
* **This does not mean Edmonds "has 36% canopy".** It means the reference we have been using says
  36.05% when asked about the whole city instead of four fifths of it.

**BLOCKED: the change comparison cannot yet be made citywide.** Only the 2016 county-wide C-CAP is
on disk; there is no `ccap_2021_hires_lc_snohfull.tif`. Until that is acquired, the properly-scoped
figure exists for 2016 alone and no citywide C-CAP change can be computed.

**Every stratified design in the P3 plan inherits the old bias.** Strata built on the old footprint
were drawn from a sample missing the most forested fifth of the city. That has to be redone against
the city-clipped reference before any sampling is executed.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q102.** Is the omitted northern fifth spatially unlike the rest of Edmonds?""",
"""- **Q102. ANSWERED - YES, STRONGLY.** North 52.58% canopy vs south 32.30%, a +20.28 pp difference.
  The omission removed the most forested fifth of the city. **Biased, not merely smaller** - every
  stratified design built on the old footprint inherits it. Original question below.
  Is the omitted northern fifth spatially unlike the rest of Edmonds?""")

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q103.** How much of the 15-17% inter-reference disagreement is FOOTPRINT rather than
  definition? C-CAP citywide is 36.05% against the NDVI reference's 37.7% - 1.7 pp apart, not 8.2.
  But the NDVI figure is itself computed over only 66.7% of the city. **Both references must be
  re-scored on the same city-clipped footprint before their disagreement means anything**, and
  twenty iterations of reasoning about that disagreement rest on the old numbers.
- **Q104.** Acquire the county-wide C-CAP 2021. Only the 2016 `snohfull` is on disk, so the
  properly-scoped figure exists for one year and no citywide change can be computed. This is a
  download, not an analysis.
- **Q105.** Do the per-year RECALL figures change when scored against the city-clipped reference?
  The omitted north is far more forested, and forest is where the model does best - so citywide
  recall is likely higher than every figure in `qc_indep_report.csv`. Re-running the QC against
  `ccap_2016_edmonds.tif` is one command per year.

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Re-score every year against `ccap_2016_edmonds.tif` (Q105).** The reference now exists. The
   omitted north is 52.6% canopy - forest, where the model does best - so citywide recall is likely
   higher than every published figure. One command per year, and it makes the numbers statements
   about Edmonds.
2. **Re-score the NDVI reference on the same city footprint (Q103)** - it currently covers 66.7% of
   the city, so the famous 8.2 pp reference gap has never been measured on common ground.
3. **Acquire county-wide C-CAP 2021 (Q104)** - a download; unblocks citywide change.
4. **What DOES the model key on (Q98)?**
5. **Specificity on the UNCHANGED class (Q66).**
6. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
7. **Geometric vs thematic accuracy for per-object products (Q41).**
8. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
9. **Write down the canopy definition (Q1)** - still open since the Phase 4 assessment, and now
   load-bearing for a number that may be quoted to a city.
10. **Get the flight dates.**

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 57 | 2026-08-19 | *** EMPIRICAL - city-clipped reference changes the headline number *** "
       "| - | Built ccap_2016_edmonds.tif (24.65 km2, the deliverable's own footprint). CITYWIDE "
       "C-CAP 2016 CANOPY = 36.05%, vs the 29.5% every figure has used. Omitted north is 52.58% "
       "canopy vs south 32.30% (+20.28pp) - the omission was BIASED, removing the most forested "
       "fifth. UNDERCUTS 20 ITERATIONS: the '8.2pp reference disagreement' compared a ~80% footprint "
       "against a 66.7% footprint; citywide C-CAP (36.05%) sits 1.7pp from the NDVI ref (37.7%). "
       "Policy-relevant: 6.5pp shift from footprint alone = 2.5x the whole decadal effect. "
       "BLOCKED on citywide change - no 2021 snohfull on disk. New Q103/Q104/Q105 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
