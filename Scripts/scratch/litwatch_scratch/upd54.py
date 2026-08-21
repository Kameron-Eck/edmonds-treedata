import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### CORRECTION - THE "DISCREPANCY" WAS MY EXTRACTION ERROR (Q97) - 2026-08-19
Iteration 53 reported that `qc_indep_report.csv` disagrees with STATE by nine points on 2016 recall
and warned that **no absolute recall figure was safe to quote**. That was a false alarm and it was
my fault. Retracting it in full.

**WHAT ACTUALLY HAPPENED.** The CSV is keyed on THREE dimensions, not one:
* `ref` - which reference (`ndvi_ref_*`, `ccap_*_hires_lc`, `ccap_*_hires_lc_snohfull`)
* `canopy_def` - `forest_only` / `forest_wetland` / `forest_wetland_scrub` (or `canopy_only` for
  the NDVI reference)
* `prob` - which model raster, including baseline vs corrected

My iteration-53 extraction deduplicated on `(year, prob)` and took whichever row came first. For
2016 that was `ref=ndvi_ref_2016.tif, canopy_def=canopy_only` -> **.5937, which is the NDVI-reference
number STATE also quotes as ".594"**. Every other year happened to come back as C-CAP/`forest_only`.
**I mixed two references and two canopy definitions in one correlation table.**

**THE DATA IS CONSISTENT.** Restricting to `ref=ccap_*_hires_lc` (not snohfull) and
`canopy_def=forest_wetland`, the CSV reproduces STATE exactly: 2013 .7094, 2000 .6303, 2015 .6222,
2002 .5069. **STATE and the CSV agree on every year present. There is no integrity problem, and the
absolute recall figures ARE safe to quote.**

**A REAL THING THE INVESTIGATION SURFACED.** There are two C-CAP variants in the live rows, and they
differ materially: `ccap_2016_hires_lc` vs `ccap_2016_hires_lc_snohfull` gives 2000 .6303 vs .6749
and 2013 .7094 vs .7395 - **three to four points, purely from reference extent.** Both are marked
live. Any figure quoted outward must name which variant it used, and STATE's numbers correspond to
the non-snohfull one.

**THE CORRELATION, REDONE ON A CONSISTENT SLICE (n=7):**

| year | non-green canopy | recall (C-CAP, forest_wetland) |
|---|---|---|
| 2019n | 0.00% | .6499 |
| 2021s | 0.58% | .6851 |
| 2022n | 5.23% | .6564 |
| 2002 | 13.58% | .5069 |
| 2000 | 16.86% | .6303 |
| 2013 | 22.46% | .7094 |
| 2015 | 31.22% | .6222 |

**Pearson r = -0.132, t = -0.30 on 5 df.** Still no relationship.

**So iteration 53's CONCLUSION survives its own broken table.** The headline - recall does not track
canopy rendering, and therefore the model does not key on greenness - holds on the corrected,
consistent slice. The numbers changed; the answer did not. That is the good case for an error: the
finding was robust to it. But the table as published in iteration 53 was wrong and should not be
reused.

**WHAT I SHOULD HAVE DONE.** Inspected the CSV schema before extracting from it. A file with `ref`
and `canopy_def` columns is telling you it holds multiple incommensurable series; I treated it as
one series keyed on year. The generalisable lesson for this loop: **when a QC file carries
qualifier columns, the qualifiers are the schema, not metadata.**
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q97.** Why does `qc_indep_report.csv` disagree with STATE on recall?""",
"""- **Q97. RESOLVED - NO DISCREPANCY. My extraction error.** The CSV is keyed on
  (year, ref, canopy_def, prob); I deduped on (year, prob) and silently mixed the NDVI reference
  into a C-CAP series. On a consistent slice the CSV reproduces STATE exactly. Absolute recall
  figures ARE safe to quote. **Real finding in passing:** two live C-CAP variants
  (`hires_lc` vs `hires_lc_snohfull`) differ by 3-4 recall points on the same year - any quoted
  figure must name which. Original question below.
  Why does `qc_indep_report.csv` disagree with STATE on recall?""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Which C-CAP variant is canonical?** `ccap_2016_hires_lc` vs `..._snohfull` differ by 3-4 recall
   points and both are marked live. STATE uses the former. This should be settled and the other
   marked superseded, or every quoted figure must carry the variant name.
2. **What DOES the model key on (Q98)?** Ablation on existing rasters - the useful successor to the
   rendering question now that greenness is ruled out.
3. **Test whether reference disagreement concentrates on deciduous crowns (Q89).**
4. **Specificity on the UNCHANGED class (Q66).**
5. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
6. **Geometric vs thematic accuracy for per-object products (Q41).**
7. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
8. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
9. **Finish the rendering index** (2017, 2024) - 2017 now has a recall figure (.7784, the highest in
   the series) but no rendering score, so it is the most informative missing point.
10. **Get the flight dates.**

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 54 | 2026-08-19 | CORRECTION - the 'discrepancy' was MY extraction error (Q97) | - | "
       "RETRACTING iteration 53's claim that the CSV disagrees with STATE and that no recall figure "
       "is safe to quote. The CSV is keyed on (year, ref, canopy_def, prob); I deduped on "
       "(year, prob) and pulled the NDVI-reference row for 2016 into a C-CAP series. On a consistent "
       "slice it reproduces STATE EXACTLY - no integrity problem. Correlation redone properly (n=7): "
       "r = -0.132, still no relationship, so iteration 53's CONCLUSION survives its broken table. "
       "REAL find in passing: two live C-CAP variants (hires_lc vs snohfull) differ by 3-4 recall "
       "points on the same year - quoted figures must name which |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
