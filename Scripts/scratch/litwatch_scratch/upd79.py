import io
p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - NOMINAL GSD IS NOT THE RIGHT AXIS; 1998 AND 2005 ARE SEVERELY OVERSAMPLED (Q137) *** - 2026-08-19
**A first attempt was thrown away.** It block-averaged different years by different factors (1, 2, 4)
to reach a common 40 cm, but the downsample factor reshapes the spectrum on its own, so 2005 (f=2)
and 2013 (f=4) were never comparable. **Confound removed: no resampling at all.** Each image is read
at native resolution and scored against **its own** Nyquist. 12 sites, 256 px windows.

| year | nominal GSD | HF share | sd |
|---|---|---|---|
| **1998** (1-band) | 40.1 cm | **0.0010** | 0.0021 |
| **2005** | 20.1 cm | **0.0010** | 0.0008 |
| 2000 | 40.1 cm | 0.0083 | 0.0098 |
| 2002 | 40.1 cm | 0.0138 | 0.0068 |
| **2013** | 10.0 cm | **0.0172** | 0.0095 |
| 2021 | 10.0 cm | 0.0530 | 0.0327 |
| 2015 | 10.0 cm | 0.0587 | 0.0439 |
| 2009 | 20.1 cm | 0.0597 | 0.0278 |
| 2023 | 10.0 cm | 0.0691 | 0.0609 |
| **2007** | 20.1 cm | **0.0770** | 0.0300 |
| 2019 | 10.0 cm | 0.0859 | 0.0579 |

**1. NOMINAL GSD IS A POOR GUIDE TO ACTUAL DETAIL IN THIS ARCHIVE.** **2007 at 20 cm carries 4.5x the
relative sharpness of 2013 at 10 cm** (0.0770 vs 0.0172). The config's `gsd_cm` - already corrected
once for CRS units - is still not measuring what the model can see. **This is the it.71 warning
generalised: it was raised for 1936/1998 and it applies to 2005 and 2013 as well.**

**2. 1998 AND 2005 ARE SEVERELY OVERSAMPLED - HF share 0.0010, essentially no detail at their own
Nyquist.** Their pixel grids are finer than their optics by roughly a factor of two or more. For
1998 this **directly confirms it.71's suspicion**: it was resampled onto the 2000 grid, so its
stated GSD is inherited from that grid rather than measured from the film. For 2005 the finding is
new and unexpected - it is a nominally 20 cm product carrying roughly 40 cm of real detail.

**3. THIS CORRECTS HOW I FRAMED it.77.** I wrote that "the only dip is 2000, and it is the coarsest
year - resolution separates the years." **The direction survives but the axis was wrong.** Sharpness
alone does not predict performance: **2005 is the softest acquisition of all and performs fine**
(AUC 0.9134, matched recall 0.7086), while 2000 is sharper by that measure and performs worst.

**What does line up is ABSOLUTE effective detail - grid spacing and sharpness together.** A soft
image on a 20 cm grid still resolves more ground detail than a soft image on a 40 cm grid. Ordered
that way, 2000 and 2002 sit clearly last: **coarsest grid AND soft for that grid, the only years bad
on both axes**, while 2005 is soft on a grid twice as fine and lands mid-pack. That ordering matches
the it.73 recall ranking and the it.77 AUC ranking.

**STATED AS THE HEURISTIC IT IS.** Turning an HF share into an effective GSD in centimetres would
need a proper MTF or edge-response analysis, which this is not. **The ordering is defensible; any
specific "effective cm" figure is not**, and I am deliberately not writing one down. What the
measurement supports is that two distinct defects - coarse sampling and optical softness - are being
collapsed into one number called `gsd_cm`, and that they do not travel together.

**4. PRACTICAL CONSEQUENCE FOR THE TIER LOGIC.** `tier_of(gsd_cm)` assigns training recipes from the
nominal figure. On this evidence 2005 is tiered as a fine 20 cm year while carrying 40 cm of detail,
and 2013 as the finest tier while sitting closer to 20 cm. **Recipe assignment is therefore keyed to
a quantity that does not measure what it is assumed to measure** - the same class of error the
2026-08-18 CRS-units audit caught, one level further in.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)
s = s.replace("""2. **Channel ablation on the trained net (Q98/Q135)**""",
"""2. **Q138. Measure effective resolution properly (edge response / MTF), not by HF share.** Q137
   established that nominal GSD misdescribes at least 1998, 2005 and 2013, but its metric only
   supports an ORDERING. A slanted-edge measurement on hard targets (roof ridges, road markings)
   would give a defensible effective GSD per year - and `tier_of(gsd_cm)` is currently assigning
   training recipes from the wrong number.
3. **Channel ablation on the trained net (Q98/Q135)**""")
io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 79 | 2026-08-19 | *** EMPIRICAL - nominal GSD is NOT the right axis; 1998 and 2005 are "
       "SEVERELY OVERSAMPLED (Q137) *** | - | THREW AWAY a first design that block-averaged years by "
       "different factors (1/2/4) to a common 40 cm - the factor reshapes the spectrum, so 2005 and "
       "2013 were never comparable. CLEAN RERUN, NO RESAMPLING, each image vs ITS OWN Nyquist, 12 "
       "sites: 1998 .0010 | 2005 .0010 | 2000 .0083 | 2002 .0138 | 2013 .0172 | 2021 .0530 | 2015 "
       ".0587 | 2009 .0597 | 2023 .0691 | 2007 .0770 | 2019 .0859. (1) 2007 at 20 cm carries 4.5x "
       "the relative sharpness of 2013 at 10 cm - NOMINAL GSD IS A POOR GUIDE TO REAL DETAIL. (2) "
       "1998 and 2005 are OVERSAMPLED (~no detail at own Nyquist); for 1998 this CONFIRMS it.71's "
       "grid-inherited-GSD suspicion, for 2005 it is NEW - a nominal 20 cm product carrying ~40 cm. "
       "(3) CORRECTS MY it.77 FRAMING: sharpness alone does NOT predict performance - 2005 is the "
       "SOFTEST year yet performs fine (AUC .9134, recall .7086) while 2000 is sharper and worst. "
       "What lines up is ABSOLUTE effective detail = grid AND sharpness together, where 2000/2002 "
       "are the only years bad on BOTH axes. STATED AS HEURISTIC: the ordering is defensible, an "
       "'effective cm' figure is not - that needs MTF/slanted-edge (Q138). (4) tier_of(gsd_cm) "
       "assigns TRAINING RECIPES from this wrong number - same class of error as the CRS-units "
       "audit, one level deeper |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
