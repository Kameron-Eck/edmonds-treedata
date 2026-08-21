import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - THE CANONICAL REFERENCE OMITS 20% OF EDMONDS (Q99/Q100) *** - 2026-08-19
Read `City Boundry/Edmonds Boundry.shp` and overlaid it on the rasters. Q100 is answered, and the
answer is the bad one.

| | area | covers of the city |
|---|---|---|
| **City of Edmonds** | **24.65 km2** | 100% |
| model raster (2013) | 80.8 km2 box | **100.0%** (reaches 0.5 km beyond) |
| **`ccap_2016_hires_lc` (canonical)** | 44.2 km2 box | **80.0% - 19.71 km2** |

**The canonical C-CAP reference stops 3.06 km short of the city's northern edge and omits
4.94 km2 - one fifth of Edmonds.** Every headline recall and precision figure in
`qc_indep_report.csv`, and every number quoted in STATE, is computed on **80% of the city**, with
the northern fifth silently excluded.

**The model is not the limitation - the reference is.** The model raster covers 100% of the city
and then some. The evaluation footprint is smaller than the deliverable footprint purely because of
how the reference was clipped.

**AND THE OMITTED FIFTH IS WHERE THE MODEL DOES BETTER.** Recall on 2000 rises .6303 -> .6749 and on
2013 .7094 -> .7395 when scored against `snohfull` instead. `snohfull` adds both the missing
northern city strip and a great deal of non-Edmonds rural forest, so the 4-point gain cannot be
attributed to the city strip alone - but the direction is consistent and the omission is certain.
**Our headline numbers are very likely understating citywide performance**, and by an amount
comparable to several effects this loop has spent iterations chasing.

**IT ALSO TOUCHES THE POLICY COMPARISON.** The canopy-fraction figures underpinning the
29.5% (C-CAP) vs 37.7% (NDVI reference) dispute - and the comparison against a 32.4% baseline and a
35% goal - are computed on this same partial footprint. A canopy PERCENTAGE is a ratio over a stated
area; ours has been a ratio over 80% of the city without that being said anywhere.

**THE FIX IS CHEAP AND ALREADY POSSIBLE.** `snohfull` covers the entire county, so it contains the
missing northern strip. Clip `snohfull` to `Edmonds Boundry.shp`, use that as the canonical C-CAP
reference, mark the current clip superseded, and re-run the QC. That produces, for the first time,
**numbers that are statements about Edmonds** rather than about a rectangle - and it removes the
4-point variant ambiguity at the same time.

**What this does NOT invalidate.** Relative comparisons across years all used the same footprint, so
year-to-year rankings, the recall-by-height staircase, the reference-disagreement work and the
rendering index are unaffected in direction. What changes is the **absolute** level of every
citywide figure, and the fact that they can now be stated as being about the city.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q100.** Does the 3.6 km of model footprint north of the C-CAP clip lie inside or outside the
  city? If inside, the headline numbers omit real city area. If outside, the model is running over
  ground we do not need and the clip is correct. One overlay of the boundary shapefile answers it.""",
"""- **Q100. ANSWERED - INSIDE THE CITY.** The canonical C-CAP clip covers 19.71 of 24.65 km2 =
  **80.0% of Edmonds**, stopping 3.06 km short of the northern boundary. The model raster covers
  100%. Every headline figure is computed on four fifths of the city. Fix: clip `snohfull` (which
  covers the whole county) to `Edmonds Boundry.shp`.
- **Q101.** How much of the .6303 -> .6749 gain is the missing city strip versus non-Edmonds rural
  forest? `snohfull` adds both. Clipping it to the boundary separates them - and gives the first
  properly-scoped citywide recall figure the project has had.
- **Q102.** Is the omitted northern fifth spatially unlike the rest of Edmonds? If north Edmonds
  differs in canopy structure or development pattern, the omission is not just a smaller sample but
  a BIASED one - which would matter for every stratified design in the P3 plan.""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Build a city-clipped C-CAP reference and re-run QC (Q99/Q100/Q101).** `snohfull` covers the
   whole county; clip it to `Edmonds Boundry.shp`. First properly-scoped citywide numbers the
   project will have, and it retires a 4-point ambiguity. Highest value on the list.
2. **Characterise the omitted northern fifth (Q102)** - is it structurally different from the
   evaluated 80%? Decides whether the omission is a smaller sample or a biased one.
3. **What DOES the model key on (Q98)?** Ablation on existing rasters.
4. **Test whether reference disagreement concentrates on deciduous crowns (Q89).**
5. **Specificity on the UNCHANGED class (Q66).**
6. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
7. **Geometric vs thematic accuracy for per-object products (Q41).**
8. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
9. **Finish the rendering index** (2017 especially).
10. **Get the flight dates.**

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 56 | 2026-08-19 | *** EMPIRICAL - the canonical reference OMITS 20% OF EDMONDS *** | - | "
       "City = 24.65 km2. Canonical `ccap_2016_hires_lc` covers 19.71 km2 = 80.0% of it, stopping "
       "3.06 km short of the northern boundary. The MODEL raster covers 100% - the reference is the "
       "limitation, not the model. Every headline recall/precision figure, and the canopy fractions "
       "behind the 29.5% vs 37.7% policy dispute, are computed on FOUR FIFTHS OF THE CITY without "
       "that being stated. And the omitted fifth is where the model scores BETTER (.6303->.6749 on "
       "2000 with snohfull). FIX IS CHEAP: clip snohfull to Edmonds Boundry.shp. New Q101/Q102 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
