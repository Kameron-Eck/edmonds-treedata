import io
p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - THE WITHIN-YEAR GRVI CAVEAT HOLDS, EXCEPT IN 2000 (Q131) *** - 2026-08-19
it.72 concluded that cross-year GRVI is unsafe but **within-year** use survives "because the cast is
global". That was an assumption, not a measurement, and a first pass looked like it would fall:
2013's fraction-called-green ranges **0.179 to 0.843 across blocks of the same image**, nearly the
0.78 between-year spread. **But blocks genuinely differ in land cover** - a forested block IS greener
than downtown - so that number alone proves nothing.

**The separator: do the same blocks stay green across years?** Land cover cannot reshuffle in a few
years; a per-frame colour cast can. Per-block rank correlation between acquisitions:

| | mean rank correlation |
|---|---|
| all 28 pairs | +0.666 |
| **excluding 2000** | **+0.730** |
| excluding 2000 and 2005 | **+0.760** |

| acquisition | mean corr. with the others | frac>.02 | block range |
|---|---|---|---|
| **2000 King** | **+0.476** | **0.8446** | **0.142** |
| 2005 King | +0.617 | 0.4767 | 0.570 |
| 2016 Snoh | +0.657 | 0.7049 | 0.454 |
| 2019 NAIP | +0.661 | 0.8729 | 0.257 |
| 2021 King | +0.687 | 0.1854 | 0.700 |
| 2013 King | +0.725 | 0.4441 | 0.664 |
| 2019 King | +0.727 | 0.1862 | 0.748 |
| 2009 King | +0.781 | 0.6681 | 0.498 |

**I WAS TOO QUICK TO DOUBT MY OWN CAVEAT, AND THE MEASUREMENT SAYS SO.** From 2005 onward the block
ranking is stable at **+0.730**, and among the mid-to-late years the pairs run 0.84-0.90
(2009-2013 = 0.895, 2009-2021 = 0.877, 2019-2021 = 0.861). **The within-year spatial variation is
mostly real land cover, so the it.72 caveat holds** - within-year GRVI comparisons are usable.

**THE EXCEPTION IS 2000, AND IT FAILS IN A WORSE WAY THAN A RESHUFFLE.** 2000 calls **84.5% of every
pixel in the city green**, with a block range of only 0.142 (0.789 to 0.932). **The index is
saturated** - it has no dynamic range left to discriminate anything - and its spatial pattern
correlates only **+0.476** with the other years, the weakest of all eight. In 2000, GRVI carries
close to no usable information, within-year or across. 2005 is intermediate at +0.617 and should be
treated as suspect rather than sound.

**TWO INDEPENDENT LINES NOW CONVERGE ON THE PRE-2005 YEARS.** Q121 (it.73) found 2000 and 2002 are
the only years still measurably worse once the operating point is matched, at ~0.65 against
0.697-0.717 for everything from 2005 to 2021. This iteration finds 2000's radiometry is saturated
and its greenness pattern matches no other year. **Coarse resolution and degraded radiometry are
separate defects arriving at the same two acquisitions**, which is a much more specific statement
about where the archive is weak than "older is worse".

**Practical consequence, stated narrowly:** GRVI-derived diagnostics are usable within a year from
2005 onward, unusable in 2000, and unusable across years anywhere without normalisation (it.72).
That is three different verdicts and they should not be collapsed into one.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)
s = s.replace("""- **Q132. [DELIVERABLE-LEVEL, HIGH PRIORITY]**""",
"""- **Q131. ANSWERED: the within-year caveat HOLDS from 2005 on, FAILS in 2000.** Block rank
  correlation +0.730 excluding 2000, with mid/late-year pairs at 0.84-0.90 = real land cover. But
  2000 calls 84.5% of the city green with a block range of 0.142 - **saturated**, correlating only
  +0.476 with any other year.
- **Q134.** Is 2000's saturation recoverable, or is the dynamic range genuinely gone? If GRVI in 2000
  is saturated because of a global colour balance, IR-MAD-style affine correction (ID 204) may
  restore it; if it is JPEG or gamma damage, nothing will. **This decides whether the earliest years
  can contribute spectral signal at all**, and it is the same question as Q130 asked where it bites
  hardest.
- **Q132. [DELIVERABLE-LEVEL, HIGH PRIORITY]**""")
io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 74 | 2026-08-19 | *** EMPIRICAL - the within-year GRVI caveat HOLDS, except in 2000 "
       "(Q131) *** | - | I doubted my own it.72 caveat after seeing 2013's block range of 0.664, but "
       "blocks differ in LAND COVER so that proved nothing. Separator: does the block RANKING hold "
       "across years? Mean rank corr +0.666 all pairs, +0.730 excluding 2000, +0.760 excluding "
       "2000+2005; mid/late pairs 0.84-0.90 (2009-2013 .895). SO THE CAVEAT HOLDS - within-year GRVI "
       "is usable from 2005 on, and I was too quick to doubt it. EXCEPTION 2000: calls 84.5% of ALL "
       "pixels green with block range only 0.142 = SATURATED, no dynamic range left, and correlates "
       "just +0.476 with any other year - worse than a reshuffle. 2005 intermediate at +0.617 = "
       "suspect. CONVERGENCE: it.73 found 2000/2002 the only years still worse at matched operating "
       "point (~.65 vs .697-.717); now 2000's radiometry is independently shown saturated. COARSE "
       "RESOLUTION AND DEGRADED RADIOMETRY ARE SEPARATE DEFECTS HITTING THE SAME TWO YEARS. Three "
       "distinct verdicts, do not collapse: within-year usable 2005+, unusable 2000, cross-year "
       "unusable anywhere without normalisation (Q134) |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
