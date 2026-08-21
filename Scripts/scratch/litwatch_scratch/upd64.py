import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - BUILDINGS EXPLAIN OVER HALF THE TALL BAND (Q113) *** - 2026-08-19
Ran the control iteration 63 said was needed. `building_footprints/data.json` - 23,666 GeoJSON
building polygons with per-building heights - has been on disk since February and had never been
used for this. Rasterised and dilated by one cell to cover roof edges and reprojection slop.

**RESULT**

| | cells | share |
|---|---|---|
| "unmeasurable" band | 38,105 | 100% |
| of which TALL (>= 2 m) | 36,341 | 95.37% |
| **tall AND on a building footprint** | **21,044** | **57.91% of tall** |
| tall and NOT on a building | 15,297 | 42.09% of tall |

**Buildings occupy 14.84% of the city (29% dilated) but account for 57.91% of the tall band** - a
roughly four-fold enrichment. The building explanation is not incidental; it is the single largest
component.

**REVISED SPLIT OF THE MODEL'S SHORTFALL**

| component | share |
|---|---|
| real miss - both references agree it is canopy | 68.2% |
| real miss - tall, not on a building | 12.8% |
| **probable C-CAP error - tall, on a building** | **17.6%** |
| short / genuinely ambiguous | 1.5% |
| **REAL MISS TOTAL** | **80.9%** |

**So iteration 63's 98.5% upper bound comes down to 80.9% once buildings are excluded.**

**AND THE TWO FIGURES BRACKET THE ANSWER RATHER THAN COMPETING.** Canopy legitimately overhangs
buildings, and C-CAP folds an **impervious-under-canopy** class into canopy *by design*
(iteration 61). A tall C-CAP-canopy pixel over a roof may be a genuine overhanging crown that the
model missed - a hard case, dark roof under dark foliage - rather than a C-CAP error. So:
* **on-building 17.6% is an UPPER bound on C-CAP error**
* **80.9% is a LOWER bound on real miss**
* **real miss lies between 80.9% and 98.5% of the shortfall**

**Either end of that range demolishes the comfortable reading.** Phase 2 assigned 64.6% of the miss
to an unmeasurable band, implying roughly 35% real miss. **The true figure is at least 81%.** The
model's genuine under-detection is roughly twice what the project has been assuming, and the
"unmeasurable" framing was doing a great deal of unearned reassurance.

**What would close the remaining range.** The distinction is between overhanging canopy over roofs
(real miss, hard case) and roofs miscalled as canopy (C-CAP error). The building layer carries a
`height` attribute per structure - comparing CHM height against BUILDING height on those pixels
would separate them: canopy overhanging a roof sits ABOVE the building height, a miscalled roof
sits AT it. That is one more run on data already loaded.

**Method note.** The one-cell dilation is conservative toward finding buildings, so it inflates the
on-building count and therefore deflates the real-miss lower bound. The bracket is honest in the
direction that matters.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q113.** How much of the tall "unmeasurable" band is BUILDINGS rather than trees?""",
"""- **Q113. ANSWERED: 57.91% of the tall band sits on building footprints** - a four-fold enrichment
  over their 14.84% share of the city. Excluding them takes real miss from 98.5% down to **80.9%**.
  Because C-CAP includes impervious-under-canopy by design, the two figures BRACKET the answer:
  **real miss is 80.9-98.5% of the shortfall**, against Phase 2's implied ~35%. Original question
  below.
  How much of the tall "unmeasurable" band is BUILDINGS rather than trees?
- **Q115.** Is a tall C-CAP-canopy pixel over a roof an overhanging crown (real miss) or a miscalled
  roof (C-CAP error)? The building layer carries a per-structure `height`; **canopy overhanging a
  roof sits ABOVE the building height, a miscalled roof sits AT it.** Comparing CHM height against
  building height on those exact pixels closes the 80.9-98.5% range. One run, data already loaded.""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Close the 80.9-98.5% range (Q115)** - compare CHM height against per-building `height` on the
   on-building pixels. Overhang sits above the roof; a miscall sits at it. One run, and it converts
   a bracket into a number for the project's most important corrected statistic.
2. **Characterise the tall-but-not-green pixels (Q114)** - shadow, bare deciduous, or dark foliage?
   Each implies a different fix.
3. **Write down the canopy definition (Q1)** - does 2-5 m green vegetation count?
4. **Test whether scrub reconciles the references (Q112)** - rows already exist in the QC CSV.
5. **Trace what else used the NDVI reference (Q107).**
6. **Recover C-CAP's source imagery date (Q109).**
7. **What DOES the model key on (Q98)?**
8. **Specificity on the UNCHANGED class (Q66).**
9. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
10. **Simplify the canopy_def reporting (Q110).**

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 64 | 2026-08-19 | *** EMPIRICAL - buildings explain over half the tall band (Q113) *** "
       "| - | 23,666 building polygons rasterised (unused since February). Buildings are 14.84% of "
       "the city but 57.91% of the tall band - FOUR-FOLD enrichment. Excluding them takes real miss "
       "from 98.5% to 80.9%. But C-CAP includes impervious-under-canopy BY DESIGN, so overhang over "
       "a roof is a real miss not an error - the two figures BRACKET: real miss is 80.9-98.5% of the "
       "shortfall, against Phase 2's implied ~35%. EITHER END demolishes the comfortable reading: "
       "genuine under-detection is ~2x what the project assumed. Q115 closes the range using the "
       "per-building height attribute |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
