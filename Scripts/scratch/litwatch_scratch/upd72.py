import io
p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** CORRECTION + EMPIRICAL - THE 1936 FILE IS EMPTY, AND GRVI IS NOT COMPARABLE ACROSS SENSORS *** - 2026-08-19

**1. I WAS WRONG ABOUT 1936. IT CONTAINS NO IMAGE DATA OVER EDMONDS.**
Iteration 71 reported 1936 as "clipped at the bright end, p99 = 255, bright detail destroyed".
**Withdrawn.** Probing nine windows spread across the city, at 1200 px each:

| location | 1936 | 1998 | 2000 |
|---|---|---|---|
| south + centre (6 windows) | **mean 253.0, std 0.00, min = max = 253** | mean 105-141, std 32-44 | mean 78-96, std 38-65 |
| north (3 windows) | **mean 0.0, std 0.00** | mean 99-130, std 4-29 | 2 of 3 are 0 |

**Every window is a constant.** `1936_king_rgb.tif` is a georeferenced **empty shell** - 18944 x 26880
of uniform 253 or 0 fill. The "p99 = 255 clipping" I described was the fill value showing up in a
whole-raster downsample, not blown highlights. **This is not a hard research problem; it is an empty
file**, and the Q124 framing that a 1936 baseline "would roughly triple the temporal span of the
deliverable" is dead. I am striking it rather than softening it.

**THE LIKELY REASON, WHICH ALSO EXPLAINS SOMETHING ELSE.** These are **King County** mosaics, and
**Edmonds is in Snohomish County**, just north of the county line. A 1936 King County survey would
simply not extend this far north, so the mosaic carries fill here. The same boundary shows in 2000:
its northern probes are also all-zero. **That is a second, independent confirmation of the known
northern-coverage gap** - it is a county line, not a random footprint quirk.

**1998 IS REAL, AND IT IS THE ONLY HISTORICAL OPTION.** All nine probes carry genuine image
structure (std 29-44 over most of the city). So the conclusion of it.71 survives in stronger form:
**1998 is not merely the better pilot, it is the only one.** It covers the whole city, sits on the
identical grid to 2000, and is single-band - which still makes it a clean test of a panchromatic
route with a near-contemporaneous RGB control. The prize is smaller than claimed - two extra years,
not sixty - but the methodological test is unchanged and still worth running.

**2. EMPIRICAL - GRVI IS NOT COMPARABLE ACROSS SENSORS, AND THE PROOF IS UNARGUABLE.**
Sampled a 2400 px window over the **same ground** in every acquisition. `frac>.02` is the share of
pixels a naive GRVI vegetation test would call green:

| year | GRVI mean | frac>.02 | | year | GRVI mean | frac>.02 |
|---|---|---|---|---|---|---|
| 2000 King | +0.0875 | 0.8027 | | 2015 King | +0.0171 | 0.2745 |
| 2002 King | +0.0241 | 0.5029 | | 2017 King | -0.0082 | 0.1877 |
| 2005 King | +0.0310 | 0.4782 | | **2019 King** | **-0.0182** | **0.1146** |
| 2007 King | +0.0237 | 0.4016 | | 2021 King | -0.0123 | 0.1344 |
| 2009 King | +0.0848 | 0.6237 | | 2023 King | -0.0061 | 0.1541 |
| 2012 King | +0.1009 | 0.6268 | | 2016 Snoh | +0.1264 | 0.6928 |
| 2013 King | +0.0146 | 0.3463 | | **2019 NAIP** | **+0.1779** | **0.8919** |

**THE DECISIVE PAIR: 2019 King County reads 0.1146 and 2019 NAIP reads 0.8919 - the same year, the
same ground, the same season, differing by 0.78.** That cannot be vegetation, phenology, growth or
loss. It is purely sensor and processing colour balance. **No other explanation is available**, which
is why this pair is worth more than the whole rest of the table.

**AND THE KING COUNTY SERIES DRIFTS MONOTONICALLY.** frac>.02 falls 0.80 (2000) -> 0.35 (2013) ->
0.11 (2019), and GRVI mean crosses from positive to negative around 2017. **Any GRVI-based
diagnostic applied across this series would report a large, steady canopy decline that is entirely a
processing artefact.**

**THIS DAMAGES OUR OWN EARLIER WORK AND I AM SAYING SO.** The leaf-off / canopy-rendering signature
built on GRVI in an earlier iteration compared low-greenness fractions **between years**. Given the
table above, **those cross-year comparisons are not safe** - the between-year variation in the index
itself dwarfs any plausible leaf-on/leaf-off effect. The within-year use (comparing canopy-masked
pixels against the rest of the same image) is unaffected, because the cast is global. **That
distinction is the whole of what survives.**
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q126. [CHEAP, HIGH LEVERAGE]**""",
"""- **Q129. [AFFECTS PUBLISHED-STYLE OUTPUT]** Which existing results used GRVI or any RGB-only
  greenness index ACROSS years? Those are now suspect (see above). Within-year uses survive.
  Needs a trace like the Q107 NDVI-reference trace, and it should happen before any of it is quoted.
- **Q130.** Is per-year radiometric normalisation enough to rescue cross-year greenness, or does the
  index have to be abandoned for RGB-only years? A histogram-matching or per-year standardisation
  test on the same window set would answer it cheaply, and the answer decides whether the 13 RGB
  King County years can contribute any spectral signal at all.
- **Q126. [CHEAP, HIGH LEVERAGE]**""")

s = s.replace("""a 1936 baseline would roughly triple the temporal span of the deliverable, which is either the
  most valuable extension available or an unbudgeted research project.""",
"""**STRUCK: 1936 is an empty file** - uniform fill over all of Edmonds, because these are King
  County mosaics and Edmonds is in Snohomish County. The question reduces to 1998 alone, which is
  real, covers the whole city, and buys two years rather than sixty.""")

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 72 | 2026-08-19 | *** CORRECTION + EMPIRICAL - 1936 is an EMPTY FILE; GRVI is NOT "
       "comparable across sensors *** | - | (1) WITHDRAWN from it.71: 1936 is not 'clipped', it "
       "contains NO IMAGE DATA over Edmonds. Nine probe windows all constant - mean 253.0 std 0.00 "
       "min=max=253, or 0.0 in the north. A georeferenced empty shell; the 'p99=255 clipping' was "
       "fill in a whole-raster downsample. REASON: these are KING COUNTY mosaics and EDMONDS IS IN "
       "SNOHOMISH COUNTY - and 2000's northern probes are zero too, independently confirming the "
       "known north-coverage gap is a COUNTY LINE. 1998 IS real everywhere (std 29-44) so it is the "
       "ONLY historical option - prize is 2 years not 60, but the panchromatic test still stands. "
       "(2) GRVI over the SAME GROUND every year: frac>.02 spans 0.1146 to 0.8919. DECISIVE PAIR - "
       "2019 King .1146 vs 2019 NAIP .8919, SAME YEAR SAME GROUND SAME SEASON, differing by 0.78. "
       "Cannot be vegetation. King series DRIFTS MONOTONICALLY .80(2000)->.35(2013)->.11(2019), GRVI "
       "mean crossing to negative ~2017, so any cross-year GRVI diagnostic reports a steady canopy "
       "DECLINE that is pure artefact. DAMAGES OUR OWN leaf-off signature: its CROSS-year "
       "comparisons are unsafe; WITHIN-year use survives because the cast is global (Q129, Q130) |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
