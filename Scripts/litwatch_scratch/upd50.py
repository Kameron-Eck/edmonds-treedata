import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### EMPIRICAL - IT IS A CONTINUUM, NOT A BINARY (corrects iteration 49) - 2026-08-19
Scored three more acquisitions - the pre-2013 King County years - and they land **between** the two
groups iteration 49 called bimodal. Nine acquisitions now scored, ranked by canopy greenness:

| year | source | median GRVI over canopy | low-greenness |
|---|---|---|---|
| 2019n | NAIP | +0.2745 | 0.00% |
| 2016 | Snohomish | +0.2079 | 1.95% |
| 2021s | Snohomish | +0.1623 | 0.58% |
| 2022n | NAIP | +0.1226 | 5.23% |
| **2005** | King | +0.1169 | **10.98%** |
| **2000** | King | +0.1000 | **16.86%** |
| **2002** | King | +0.0737 | **13.58%** |
| 2022 | City of Edmonds | +0.0485 | 16.42% |
| 2020 | City of Edmonds | +0.0330 | **33.02%** |

**Iteration 49 said "bimodal and unambiguous, nothing in between". That was drawn from six
acquisitions and is now wrong.** The King County years occupy the middle - 11 to 17% - and the
distribution is a **continuum**.

**Which is what a March-May acquisition window actually predicts.** Flights spread across that
window give a gradient: fully bare in early March, substantially leafed by late May. A binary
leaf-off/leaf-on label was always the wrong model of the archive; the data says phenology varies
continuously across acquisitions.

**THE USEFUL REFRAME: this is a per-year PHENOLOGY INDEX, computed from the imagery, needing no
dates.** That is more valuable than a binary classification would have been:
* **year-pairs should be matched on the SCORE**, not on a leaf-off/leaf-on class. {2016, 2021s} at
  1.95% and 0.58% are well matched; {2020, 2022} at 33.0% and 16.4% are NOT, despite both being
  City of Edmonds and both nominally leaf-off.
* it gives a continuous covariate for the change model rather than a categorical one;
* it is computable for every acquisition without recovering a single flight date.

**TWO THINGS THIS DOES NOT CHANGE.**
1. **2020 is still the extreme.** At 33.0% it is nearly double the next-barest acquisition, and it
   remains our only hand-labelled year. "We labelled on the barest imagery in the archive" stands,
   and is now quantified against nine comparisons rather than three.
2. **2000 and 2002 - the "hard floor" years - are mid-range on phenology** (16.9%, 13.6%), not
   extreme. Their difficulty is resolution and missing NIR, not season. Worth knowing: it removes
   one candidate explanation for their poor recall and leaves the others standing.

**Caveat that grows with the continuum reading.** Sensor and vendor differ across these groups, and
colour balance remains an alternative explanation for part of the spread. The continuum reading is
more robust to that than the binary was - a vendor effect would produce clusters by program, and
what we see instead is King County straddling the gap between NAIP/Snohomish and City of Edmonds.
But it is not eliminated, and only flight dates would eliminate it.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q91.** Which year-pairs are season-matched?""",
"""- **Q92.** Should the phenology index be a COVARIATE in the change model rather than a filter?
  The continuum reading (iteration 50) says acquisitions differ continuously in canopy greenness.
  A binary season filter throws away most of the archive; a continuous covariate keeps it and
  models the effect. This connects to Search 48's covariate-conditional sensitivity (ID 184) - the
  phenology index is exactly the kind of per-acquisition covariate that framework accepts.
- **Q91.** Which year-pairs are season-matched?""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Finish the phenology index - 9 acquisitions remain** (2007, 2009, 2013, 2015, 2017, 2019,
   2021, 2023, 2024). One command each. Completes a per-year covariate that needs no flight dates
   and decides every valid year-pair.
2. **Establish C-CAP's season (Q90)** - every headline recall number is scored against it.
3. **Phenology index as a COVARIATE, not a filter (Q92)** - keeps the archive rather than
   discarding most of it; feeds the covariate-conditional sensitivity framework (ID 184).
4. **Test whether reference disagreement concentrates on deciduous crowns (Q89).**
5. **Separate season from resolution (Q86)** - needs one Colab re-inference.
6. **Specificity on the UNCHANGED class (Q66).**
7. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
8. **Geometric vs thematic accuracy for per-object products (Q41).**
9. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
10. **Get the flight dates** - would eliminate the colour-balance alternative outright.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 50 | 2026-08-19 | EMPIRICAL - it is a CONTINUUM, not a binary (corrects it.49) | - | "
       "Pre-2013 King years land BETWEEN the groups: 2005 10.98%, 2002 13.58%, 2000 16.86% "
       "non-green canopy. Iteration 49's 'bimodal, nothing in between' was drawn from six "
       "acquisitions and is WRONG - it is a continuum, which is what a March-May window predicts. "
       "REFRAME: this is a per-year PHENOLOGY INDEX from imagery alone, no flight dates needed - "
       "match year-pairs on the SCORE, not a binary class ({2020,2022} are both CoE yet 33.0 vs "
       "16.4 = badly matched). 2020 still the extreme, ~2x the next barest. 2000/2002 are MID-RANGE "
       "on phenology - their problem is resolution and no NIR, not season |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
