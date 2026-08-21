import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - THE "UNMEASURABLE BAND" IS ALMOST ENTIRELY TALL (Q111) *** - 2026-08-19
Phase 2 splits the model's C-CAP misses into *real miss* (both references agree it is canopy) and
*unmeasurable* (the references disagree). Iteration 62 refuted the assumption underpinning that
split. This tests it against **3DEP lidar, independent of both references**.

**LIDAR HEIGHT OF THE "UNMEASURABLE" MISSES**

| height | share |
|---|---|
| 0-2 m | **4.63%** |
| 2-3 m | 2.82% |
| 3-5 m | 16.96% |
| 5-10 m | 37.40% |
| 10-20 m | 26.19% |
| 20+ m | 12.01% |

**95.37% of the "unmeasurable" band is 2 m or taller by independent lidar.** Reclassifying those as
real miss moves the split from 68.2% / 31.8% to **98.5% real miss / 1.5% genuinely ambiguous**.

**So the band is not unmeasurable. It is mostly tall vegetation the NDVI reference rejects** -
presumably for insufficient greenness, since it requires NDVI >= 0.2 - **while lidar says it is
there and C-CAP says it is canopy.** The comfortable reading, that most of the shortfall is
reference disagreement rather than model failure, does not survive an independent height source.

**THE ALTERNATIVE I CANNOT RULE OUT HERE, AND IT IS SERIOUS.** The CHM is height-above-ground and
**includes buildings** - STATE says so explicitly ("HAG includes buildings (fine - RGB flags
non-green)"). So a tall, non-green, C-CAP-canopy pixel could be a **building C-CAP has miscalled**,
not a tree the model missed. The height profile is suggestive but not decisive: the 12% above 20 m
is almost certainly trees, and the 26% at 10-20 m probably is, but the 37% at 5-10 m overlaps
one-to-three-storey buildings squarely.

**The test that settles it is one run away and the data is on disk:** `building_footprints/data.json`
was noted in iteration 26 and never used. Excluding building footprints from the band and re-running
would separate "trees the model missed" from "buildings C-CAP miscalled". **Until that is done, the
98.5% figure is an upper bound on real miss, not a measurement.**

**A DISCREPANCY I AM NOT GLOSSING.** My split (68.2% agree / 31.8% disagree) does **not** reproduce
Phase 2's (35.4% / 64.6%). Three differences explain it and none is an error in either: Phase 2 used
`prob_2016_corrected` while I used the baseline `prob_2016`; Phase 2 ran on the old rectangle while
I ran on the city clip; and I additionally require CHM coverage, which drops 5% of the city. **The
direction of this finding does not depend on which baseline you start from** - whatever fraction is
labelled unmeasurable, 95% of it is tall - but the specific percentages are not comparable to
Phase 2's and should not be quoted as if they were.

**Why this matters for the project's headline.** STATE presents the ~30% shortfall as splitting into
real miss plus an unmeasurable band, and P2 was built to bound that band. If the band is 95% tall
vegetation, **the bound was generous and the model's genuine under-detection is larger than the
project has been assuming.** That is the third finding in three iterations to move in the
uncomfortable direction.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q111.** If the missed suburban stands are REAL misses rather than reference error, the
  "unmeasurable band" framing of Phase 2 needs revisiting.""",
"""- **Q111. ANSWERED, PENDING ONE CONTROL: the band is 95.37% TALL by independent lidar.**
  Reclassifying tall pixels as real miss moves the split to 98.5% real / 1.5% ambiguous. **But the
  CHM includes buildings**, so part of the band could be structures C-CAP miscalled rather than
  trees the model missed - `building_footprints/data.json` settles it and has never been used.
  Until then 98.5% is an upper bound. Original question below.
  If the missed suburban stands are REAL misses rather than reference error, the
  "unmeasurable band" framing of Phase 2 needs revisiting.""")

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q113.** How much of the tall "unmeasurable" band is BUILDINGS rather than trees? The CHM is
  height-above-ground and includes structures. 37% of the band sits at 5-10 m, which overlaps
  one-to-three-storey buildings. `building_footprints/data.json` is on disk and unused - one
  exclusion run separates "trees the model missed" from "buildings C-CAP miscalled", and the answer
  determines whether the project's genuine under-detection is larger than believed or the same.
- **Q114.** Why does the NDVI reference reject tall vegetation that C-CAP accepts? It requires
  NDVI >= 0.2, so the rejected pixels are tall-but-not-green: conifer in deep shadow, bare
  deciduous, or dark foliage. Each has a different implication for the model, and the P2 partition
  cannot distinguish them - but NDVI value plus CHM height on those exact pixels could.

### Known unknowns we are choosing to live with""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Exclude building footprints from the tall band (Q113)** - `building_footprints/data.json` is on
   disk and has never been used. It decides whether the 98.5%-real-miss figure holds or collapses,
   and that number changes how bad the model's under-detection actually is.
2. **Characterise the tall-but-not-green pixels (Q114)** - shadow, bare deciduous, or dark foliage?
   NDVI value and CHM height on those exact pixels would tell us, and each implies a different fix.
3. **Write down the canopy definition (Q1)** - now sharply posed: does 2-5 m green vegetation count?
4. **Test whether scrub reconciles the references (Q112)** - rows already exist in the QC CSV.
5. **Recover C-CAP's source imagery date (Q109).**
6. **Trace what else used the NDVI reference (Q107).**
7. **What DOES the model key on (Q98)?**
8. **Specificity on the UNCHANGED class (Q66).**
9. **CEOS Section 3.5 (sample size planning and allocation)** - bears on Q69.
10. **Simplify the canopy_def reporting (Q110).**

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 63 | 2026-08-19 | *** EMPIRICAL - the 'unmeasurable band' is 95% TALL (Q111) *** | - | "
       "Tested against 3DEP lidar, independent of both references: 95.37% of the disagreement band "
       "is >=2 m; only 4.63% is below. Reclassifying tall as real miss moves the split to 98.5% "
       "real / 1.5% ambiguous. So the band is NOT unmeasurable - it is tall vegetation the NDVI ref "
       "rejects for low greenness while lidar and C-CAP both find it. CAVEAT I CANNOT RULE OUT: the "
       "CHM includes BUILDINGS, and 37% of the band sits at 5-10 m where 1-3 storey structures live "
       "- building_footprints/data.json settles it and is unused (Q113), so 98.5% is an UPPER BOUND. "
       "Also: my 68/32 split does NOT reproduce Phase 2's 35/65 - different raster, footprint and "
       "CHM requirement; direction holds, percentages are not comparable |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
