import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - THE INDEX IS MOSTLY RADIOMETRY, NOT PHENOLOGY (major self-correction) ***
2026-08-19. Four more King County years scored, and they break the interpretation I have been
building since iteration 45.

**Sixteen of eighteen acquisitions, ranked by fraction of canopy that is not green:**

| year | src | canopy non-green | | year | src | canopy non-green |
|---|---|---|---|---|---|---|
| 2019n | NAIP | 0.00% | | 2022 | CoE | 16.42% |
| 2021s | Snoh | 0.58% | | 2000 | King | 16.86% |
| 2016 | Snoh | 1.95% | | 2013 | King | 22.46% |
| 2022n | NAIP | 5.23% | | 2015 | King | 31.22% |
| 2009 | King | 8.47% | | 2020 | CoE | 33.02% |
| 2007 | King | 8.51% | | **2021** | King | **64.32%** |
| 2005 | King | 10.98% | | **2023** | King | **65.53%** |
| 2002 | King | 13.58% | | **2019** | King | **90.65%** |

**THE SANITY CHECK FAILS AT THE TOP.** 2019 King shows **90.65% of canopy pixels not green, with a
NEGATIVE median GRVI (-0.0118)**. Edmonds sits in the Puget Sound lowland - Douglas fir, western red
cedar, western hemlock. **A leaf-off flight here should still show large amounts of green, because
the conifers keep their needles.** Ninety percent non-green canopy is not credible as phenology.

**AND THE EXTREME YEARS ARE THE ONES WE ALREADY IDENTIFIED AS A DISTINCT RADIOMETRIC ERA.**
2019, 2023 and 2021 King are exactly the three lowest scene-wide greenness values found in
iteration 18, and 2017/2019 were the nearest-neighbour pair in iteration 11 that Kam identified as
the **EagleView** era. The index's extremes track the radiometric clustering, not a seasonal
calendar.

**SO THE HONEST READING IS: this index measures CANOPY GREENNESS, which conflates phenology with
sensor colour balance, and at the extremes radiometry dominates.** It is not a phenology index. I
have been calling it one since iteration 50 and that was wrong.

**WHAT THIS DOES TO THE LEAF-OFF LINE OF ARGUMENT (iterations 45-51):**
* **Iteration 47's central claim is substantially weakened.** I argued the split "follows the
  SPECIFICATION, not the vendor" from four acquisitions. With sixteen, the most extreme values
  belong to a single vendor era, which is the vendor explanation I claimed to have ruled out.
* **The published specifications still stand** - the consortium does specify leaf-off, NAIP does
  specify leaf-on. That is documentary fact and unaffected.
* **What is no longer supported is using canopy greenness as the measurement of it.** The NAIP and
  Snohomish years being greenest is consistent with leaf-on, but it is equally consistent with
  those programs having different radiometry, and the King EagleView years prove the radiometric
  channel is large enough to dominate.
* **2020 at 33.02% is no longer an outlier** - three King years exceed it, two by a factor of two.
  The iteration-47 line "we labelled on the barest imagery in the archive" is **false as stated**.
  2020 is the barest *City of Edmonds* year and mid-pack overall.

**WHAT SURVIVES, AND IT IS LESS THAN I CLAIMED.** A real, measured fact: **canopy greenness varies
enormously across the archive - 0% to 91% non-green - and nothing in the pipeline accounts for it.**
Whether that variation is season, sensor, or both, it is a large per-acquisition covariate that
affects any NDVI- or greenness-based reference, any change comparison, and any weak-supervision
pairing. That conclusion is robust to the cause.

**And the diagnostic value is intact even though the label was wrong:** matching year-pairs on this
score is still the right move, because what matters for a change comparison is that the two
acquisitions render canopy similarly - regardless of whether the difference is leaves or gain
settings.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q95.** How much of the canopy-greenness index is SEASON and how much is SENSOR? The extremes
  (2019/2021/2023 King at 64-91%) are implausible as phenology in a conifer-dominated region and
  coincide with the EagleView radiometric era. Separating them needs either flight dates, or a
  radiometric normalisation applied before the index is recomputed. **Until separated, the index
  should be described as a canopy-rendering index, not a phenology index.**
- **Q96.** Does the model's recall track canopy greenness at all? 2019 King renders 90.65% of canopy
  as non-green - if the model still detects canopy there, greenness is not what it keys on, and the
  whole greenness-based line of reasoning (including the NDVI reference) rests on a feature the
  model may not use. 2019 King has a prob raster; this is one command.

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Does model recall track canopy greenness (Q96)?** 2019 King renders 90.65% of canopy non-green.
   If recall there is normal, the model does not key on greenness - which undercuts both the
   leaf-off story AND the NDVI reference's construction. One command, raster exists.
2. **Recompute the index after radiometric normalisation (Q95)** - separates rendering from season.
3. **Finish the last two acquisitions** (2017, 2024 CoE - the 48 GB and 27 GB files).
4. **Establish C-CAP's season/rendering (Q90).**
5. **Test whether reference disagreement concentrates on deciduous crowns (Q89).**
6. **Specificity on the UNCHANGED class (Q66).**
7. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
8. **Geometric vs thematic accuracy for per-object products (Q41).**
9. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
10. **Get the flight dates** - now the only clean way to settle Q95.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 52 | 2026-08-19 | *** EMPIRICAL - the index is mostly RADIOMETRY, not phenology "
       "(self-correction) *** | - | Four more King years: 2015 31.22%, 2021 64.32%, 2023 65.53%, "
       "2019 90.65% non-green canopy (median GRVI NEGATIVE). SANITY CHECK FAILS: Puget Sound is "
       "conifer-dominated, so 90% non-green canopy is NOT credible as leaf-off. The extremes are "
       "exactly the EagleView era from it.11/it.18 - radiometry, not calendar. WITHDRAWING "
       "iteration 47's 'the split follows the SPEC not the vendor' and 'we labelled on the barest "
       "imagery' - 2020 at 33% is mid-pack, three King years exceed it. WHAT SURVIVES: canopy "
       "rendering varies 0-91% across the archive and nothing accounts for it. New Q95/Q96 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
