import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### EMPIRICAL - THE EVALUATION FOOTPRINT HAS NEVER BEEN PINNED TO THE CITY - 2026-08-19
Chasing the two live C-CAP variants (iteration 54) turned up something larger than a labelling
question.

**THE TWO REFERENCES ARE NOT TWO VERSIONS OF THE SAME AREA.**

| raster | size | extent (UTM 10N) | area | canopy share |
|---|---|---|---|---|
| `ccap_2016_hires_lc` | 7431 x 5952 | 7.4 x 6.0 km | 44.2 km2 | 26.9% |
| `ccap_2016_hires_lc_snohfull` | 117603 x 64276 | **117.6 x 64.3 km** | ~7,560 km2 | **66.1%** |

`snohfull` is **the whole of Snohomish County**, not a fuller rendering of Edmonds. Its 66% canopy
share against the clip's 27% is the giveaway: it is dominated by rural forest.

**AND THE CLIPPED REFERENCE COVERS ONLY HALF THE EVALUATED FOOTPRINT.**

| | extent | area |
|---|---|---|
| model raster (2013) | 7.6 x 10.7 km | 80.8 km2 |
| C-CAP clip | 7.4 x 6.0 km | 44.2 km2 |
| **overlap** | | **41.8 km2 = 52% of the model footprint** |

The clip's northern edge is N 5297858; the model raster reaches N 5301429. **About 3.6 km of the
model's northern extent has no clipped-C-CAP coverage at all**, and every headline recall figure is
therefore computed on roughly the southern half of the area the model actually runs over.

**WHICH VARIANT IS RIGHT DEPENDS ON A QUESTION NOBODY HAS ASKED.** Two readings, and they point
opposite ways:
* **The clip is correct** and the model raster is an over-generous bounding box; `snohfull` inflates
  recall (.6303 -> .6749 on 2000) by adding easy rural conifer forest that is not Edmonds. This is
  the more likely reading, given the 66% canopy share.
* **The clip is too small** and is silently excluding real city area from every evaluation.

**THE FILE THAT SETTLES IT ALREADY EXISTS AND HAS NEVER BEEN USED FOR THIS.** `City Boundry/Edmonds
Boundry.shp` is in the repo. **Neither reference is clipped to the city boundary**, and the
evaluation footprint has never been defined as "Edmonds". Everything we report is implicitly scoped
to whichever rectangle a given raster happens to cover.

**Why this matters beyond tidiness.** The deliverable is a statement about a CITY - canopy percent
for Edmonds, tracked against a municipal goal. An area-based figure is only meaningful relative to a
stated area, and ours is currently "the intersection of whatever rectangles were available". The
4-point recall gap between the two C-CAP variants is not noise or reference error; it is a
**spatial-sampling difference**, and it is the same size as several of the effects this loop has
spent iterations chasing.

**Concrete fix, cheap:** clip every reference and every prob raster to `Edmonds Boundry.shp`, mark
one C-CAP variant canonical and the other superseded, and re-run the QC. That makes every figure a
statement about Edmonds rather than about a bounding box, and it removes a 4-point ambiguity from
the headline numbers.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q99.** What IS the evaluation footprint? Neither C-CAP variant is clipped to the city, the
  clipped one covers 52% of the model raster, and `City Boundry/Edmonds Boundry.shp` has never been
  used to scope the QC. Every reported canopy figure is implicitly scoped to an arbitrary rectangle.
  **For a municipal deliverable this is the difference between a number about Edmonds and a number
  about a bounding box.**
- **Q100.** Does the 3.6 km of model footprint north of the C-CAP clip lie inside or outside the
  city? If inside, the headline numbers omit real city area. If outside, the model is running over
  ground we do not need and the clip is correct. One overlay of the boundary shapefile answers it.

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Clip the QC to the city boundary (Q99/Q100).** `City Boundry/Edmonds Boundry.shp` exists and
   has never been used to scope evaluation. Would settle the C-CAP variant question, remove a
   4-point ambiguity, and make every reported figure a statement about Edmonds. Cheap, local, and
   it affects every number the project will publish.
2. **What DOES the model key on (Q98)?** Ablation on existing rasters.
3. **Test whether reference disagreement concentrates on deciduous crowns (Q89).**
4. **Specificity on the UNCHANGED class (Q66).**
5. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
6. **Geometric vs thematic accuracy for per-object products (Q41).**
7. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
8. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
9. **Finish the rendering index** (2017 especially - highest recall, no score yet).
10. **Get the flight dates.**

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 55 | 2026-08-19 | EMPIRICAL - the evaluation footprint was never pinned to the city | - | "
       "The two live C-CAP variants are NOT two versions of Edmonds: snohfull is the WHOLE COUNTY "
       "(117x64 km, 66% canopy) vs the clip (7.4x6.0 km, 27% canopy). AND THE CLIP COVERS ONLY 52% "
       "OF THE MODEL FOOTPRINT - 3.6 km of the model's northern extent has no C-CAP coverage, so "
       "every headline recall is computed on roughly the southern half. `City Boundry/Edmonds "
       "Boundry.shp` EXISTS IN THE REPO and has never been used to scope the QC. For a municipal "
       "deliverable this is the difference between a number about Edmonds and a number about a "
       "bounding box. New Q99/Q100 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
