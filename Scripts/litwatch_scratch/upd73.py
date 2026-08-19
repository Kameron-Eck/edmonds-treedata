import io
p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - MOST OF THE CROSS-YEAR RECALL WANDER IS THE OPERATING POINT (Q121) *** - 2026-08-19
One recipe (`_citywide_rgb`), one reference (C-CAP), one footprint (161,052 of 162,829 sample
points, 98.9%), eight years. The only thing varied is whether the operating point is held constant.

| year | recall @ FIXED thr 0.5 | call rate there | recall @ MATCHED call rate 0.30 |
|---|---|---|---|
| 2000 | 0.5303 | 0.2313 | 0.6454 |
| 2002 | 0.5853 | 0.2599 | 0.6541 |
| 2005 | 0.5806 | 0.2298 | 0.7086 |
| 2007 | 0.6915 | 0.2991 | 0.6974 |
| 2009 | 0.6801 | 0.2851 | 0.7052 |
| 2013 | 0.7123 | 0.3046 | 0.7069 |
| 2015 | 0.7130 | 0.2978 | 0.7174 |
| 2021 | 0.5577 | 0.2198 | 0.7155 |
| **SPREAD** | **0.1827** | 0.0847 | **0.0721** |

**Holding the operating point constant removes 61% of the cross-year spread** - 0.1827 down to
0.0721. The mechanism is visible in the middle column: **the same threshold 0.5 calls anywhere from
22.0% to 30.5% of the city canopy**, so a fixed threshold is not a fixed operating point.

**AND WHAT IS LEFT IS INTERPRETABLE, WHICH THE ORIGINAL WANDER WAS NOT.** Finding 3 described a
0.28 spread (.50-.78) "with no clear driver". At a matched operating point the residual has an
obvious structure:

* **2000 and 2002: 0.6454 and 0.6541** - the two oldest and coarsest acquisitions, ~40 cm true GSD;
* **2005 through 2021: 0.6974, 0.7052, 0.7069, 0.7174, 0.7155 and 0.7086** - a spread of **0.020
  across sixteen years, three providers and a four-fold resolution change.**

**That is a much stronger robustness result than this project has been claiming.** Read fairly, the
model is stable to within two points from 2005 to 2021, and the only genuine cross-year effect is a
~6-point penalty at the coarse end. The apparent instability was largely an artefact of comparing
models at thresholds calibrated separately per year.

**Credit, so this is not overclaimed:** the 2026-08-18 CHATLOG entry already showed that a per-year
spread dissolved when the RECIPE was held constant. That run used a fixed threshold of 0.5 - which
is exactly column two here. **This adds the second control, not the first.** The two together
account for most of finding 3.

**ONE ANOMALY, FLAGGED NOT EXPLAINED.** 2007 returns **identical recall at call rates 0.20 and 0.25**
(0.6189 both). That cannot happen with a well-spread probability distribution and indicates a large
mass of pixels sharing one value, so 2007's probability raster is likely degenerate or saturated in
some region. It is also why the cr=0.20 column shows a wider spread (0.1452) than the other three.
**Do not quote the cr=0.20 row until 2007 is understood.**

**WHAT THIS CHANGES DOWNSTREAM.** Every cross-year comparison in the pipeline is thresholded
per-year, so this applies to the canopy AREA series as well, not just recall - and the area series
is the deliverable. **A per-year threshold shift of the size seen here (22% to 30% call rate) is
large enough to manufacture or erase a canopy trend on its own.** That is the same class of error as
the GRVI drift found in it.72, arriving by a different route, and the two would compound.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q129. [AFFECTS PUBLISHED-STYLE OUTPUT]**""",
"""- **Q121. ANSWERED: 61% of the cross-year recall spread is the OPERATING POINT.** 0.1827 at fixed
  threshold 0.5 -> 0.0721 at matched call rate 0.30. Residual is interpretable: 2000/2002 at ~0.65
  (coarse), 2005-2021 all within **0.020** of each other. **The model is far more stable across
  years than finding 3 implied.**
- **Q132. [DELIVERABLE-LEVEL, HIGH PRIORITY]** Does the per-year threshold shift manufacture a trend
  in the canopy AREA series? At threshold 0.5 the call rate runs 22.0% to 30.5% across years - large
  enough to create or erase a canopy trend by itself. The area series is the deliverable, and this
  has never been checked. **Compounds with the GRVI drift (it.72), which points the same way.**
- **Q133.** Why does 2007 return identical recall at call rates 0.20 and 0.25? That implies a large
  mass of pixels sharing one probability value - a degenerate or saturated raster. Cheap to check
  with a histogram, and it invalidates the cr=0.20 comparison until resolved.
- **Q129. [AFFECTS PUBLISHED-STYLE OUTPUT]**""")

io.open(p, 'w', encoding='utf-8').write(s)
s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 73 | 2026-08-19 | *** EMPIRICAL - most of the cross-year recall wander is the OPERATING "
       "POINT (Q121) *** | - | One recipe, one reference, one footprint (161,052 pts, 98.9%), 8 "
       "years. Recall spread 0.1827 at FIXED threshold 0.5 -> 0.0721 at MATCHED call rate 0.30, a "
       "61% REDUCTION. Mechanism: thr 0.5 calls 22.0%-30.5% of the city depending on year, so a "
       "fixed threshold is NOT a fixed operating point. RESIDUAL IS INTERPRETABLE where finding 3's "
       "0.28 wander was not: 2000/2002 (~40cm, coarsest) .6454/.6541, and 2005-2021 all within "
       "0.020 of each other (.6974-.7174) across 16 years, 3 providers, 4x resolution change. THE "
       "MODEL IS MUCH MORE STABLE THAN CLAIMED; the instability was a calibration artefact. Credit: "
       "the 2026-08-18 recipe-controlled run is column two here - this adds the SECOND control. "
       "ANOMALY FLAGGED: 2007 gives IDENTICAL recall at cr .20 and .25 (.6189) = degenerate/saturated "
       "raster, so do not quote the cr=.20 row (Q133). DOWNSTREAM: the AREA series is thresholded "
       "per-year too, and a 22->30% call-rate shift can manufacture a canopy trend on its own "
       "(Q132) - compounds with the it.72 GRVI drift |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
