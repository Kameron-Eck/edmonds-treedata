import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### EMPIRICAL - PHENOLOGY DOES NOT PREDICT RECALL - 2026-08-19
Three more acquisitions scored. **Twelve of eighteen now have a phenology index**, ranked by the
fraction of canopy that is not green:

| rank | year | source | median GRVI | low-greenness |
|---|---|---|---|---|
| 1 | 2019n | NAIP | +0.2745 | 0.00% |
| 2 | 2021s | Snohomish | +0.1623 | 0.58% |
| 3 | 2016 | Snohomish | +0.2079 | 1.95% |
| 4 | 2022n | NAIP | +0.1226 | 5.23% |
| 5 | 2009 | King | +0.1222 | 8.47% |
| 6 | 2007 | King | +0.0732 | 8.51% |
| 7 | 2005 | King | +0.1169 | 10.98% |
| 8 | 2002 | King | +0.0737 | 13.58% |
| 9 | 2022 | City of Edmonds | +0.0485 | 16.42% |
| 10 | 2000 | King | +0.1000 | 16.86% |
| 11 | **2013** | King | +0.0455 | **22.46%** |
| 12 | **2020** | City of Edmonds | +0.0330 | **33.02%** |

**THE NEGATIVE RESULT THAT MATTERS: the index does NOT predict honest recall.**

| year | low-greenness | honest recall vs C-CAP |
|---|---|---|
| 2002 | 13.58% | .5069 |
| 2000 | 16.86% | .6303 |
| 2016 | 1.95% | .6844 |
| **2013** | **22.46%** | **.7094** |

Pearson r = **+0.03** (n=4) - no relationship, and if anything the sign is *positive*: **2013 is the
second-barest acquisition scored and has the HIGHEST honest recall of the live years, while 2016 is
nearly leaf-on and scores lower.**

**This is a third independent strike against the causal story** from iterations 45-47 (already
withdrawn in iteration 48):
1. the height staircase does not flatten on a leaf-on year (iteration 48, confounded by GSD);
2. the archive is a continuum, not the clean leaf-off/leaf-on split the story assumed (iteration 50);
3. and now: **cross-year phenology and cross-year recall are uncorrelated.**

**What survives, stated precisely.** The imagery finding stands and is now measured across twelve
acquisitions: **2020 is the barest year in the archive by a wide margin (33.0%, nearly 1.5x the next
worst), and it is our only hand-labelled year.** That is a real and quantified problem for the
LABEL SET. What is NOT supported is that phenology explains the recall differences BETWEEN years -
the data says it does not.

Those are compatible: leaf-off labelling could still bias WHAT the model learns to call canopy
(a systematic, all-years effect) while contributing nothing to why 2013 scores better than 2002
(a between-years effect). The first is untested; the second is now tested and negative.

**A DATA-QUALITY FLAG FOUND IN PASSING.** 2009 shows p90 = +0.63 and p95 = +0.77 for canopy
greenness. A GRVI of 0.77 requires the red channel to be near zero, which is not plausible
vegetation - it suggests channel saturation or a colour-processing anomaly in that acquisition.
2009 is currently unused in the live QC set, but this should be checked before it is.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q93.** Does leaf-off labelling bias WHAT the model calls canopy, even though it does not
  explain BETWEEN-year recall differences? These are different claims and only the second has been
  tested (negatively). The first predicts a systematic, all-years deficit concentrated on deciduous
  crowns - which is consistent with the height staircase surviving every attempt to remove it.
  Testable only by labelling a leaf-on year and comparing, which is the expensive experiment.
- **Q94.** Is the 2009 acquisition radiometrically sound? Canopy greenness p90 +0.63 / p95 +0.77
  implies a near-zero red channel, which is not plausible vegetation. Suggests saturation or a
  colour-processing fault. Unused in the live QC set today; check before using it.

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Finish the phenology index - 6 acquisitions remain** (2015, 2017, 2019, 2021, 2023, 2024).
   Completes a per-year covariate for all 18 that needs no flight dates.
2. **Check 2009's radiometry (Q94)** - implausible greenness tail suggests a processing fault.
3. **Establish C-CAP's season (Q90)** - every headline recall number is scored against it.
4. **Phenology index as a COVARIATE, not a filter (Q92).**
5. **Test whether reference disagreement concentrates on deciduous crowns (Q89)** - the remaining
   live test of the leaf-off story, and the one that would separate Q93's two claims.
6. **Separate season from resolution (Q86)** - needs one Colab re-inference.
7. **Specificity on the UNCHANGED class (Q66).**
8. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
9. **Geometric vs thematic accuracy for per-object products (Q41).**
10. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 51 | 2026-08-19 | EMPIRICAL - phenology does NOT predict recall | - | "
       "12 of 18 acquisitions now indexed. NEGATIVE RESULT: low-greenness vs honest recall gives "
       "Pearson r=+0.03 (n=4) - 2013 is the SECOND-BAREST (22.46%) with the HIGHEST recall (.7094), "
       "2016 nearly leaf-on (1.95%) scores LOWER (.6844). THIRD strike against the causal story "
       "(after it.48 steepening and it.50 continuum). What SURVIVES: 2020 is the barest year in the "
       "archive by ~1.5x and is our only labelled year - a real problem for the LABEL SET, distinct "
       "from between-year recall (Q93). FLAG: 2009 canopy greenness p95 +0.77 implies near-zero red "
       "- probable saturation/processing fault (Q94) |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
