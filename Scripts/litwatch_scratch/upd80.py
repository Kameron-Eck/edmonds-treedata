import io
p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### *** EMPIRICAL - EFFECTIVE RESOLUTION MEASURED: gsd_cm IS WRONG BY UP TO 6x (Q138) *** - 2026-08-19
Automatic edge-response measurement: find strong gradients, take intensity profiles across them,
average into an Edge Spread Function, read the **10-90% rise distance** and multiply by true GSD.
Same 12 sites in every year, so scene content is controlled rather than assumed away.

**A BUG WAS CAUGHT AND FIXED MID-EXPERIMENT, AND IT IS WORTH RECORDING.** The first version used
`np.interp(0.10, e, off)` to find the crossing. **`np.interp` requires its x-array to be increasing,
and a real edge profile is noisy and non-monotonic**, so it returned garbage - five different years
came back at *exactly* 6.70 px, which is the profile's own half-width. **The tell was the
impossible coincidence, not the plausibility of the numbers.** Replaced with an explicit crossing
search walking outward from the profile centre. After the fix all 12 sites resolve in all 11 years,
and well-sampled years land at ~1.3 px rise - the physically expected value.

| year | nominal GSD | rise (px) | **EFFECTIVE resolution** | oversampling |
|---|---|---|---|---|
| **1998** | 40.1 cm | 6.10 | **244.7 cm** | **6.1x** |
| **2000** | 40.1 cm | 2.76 | **110.8 cm** | 2.8x |
| 2002 | 40.1 cm | 1.42 | 57.1 cm | 1.4x |
| **2005** | 20.1 cm | 4.02 | **80.7 cm** | **4.0x** |
| 2007 | 20.1 cm | 1.27 | 25.5 cm | 1.3x |
| 2009 | 20.1 cm | 1.30 | 26.1 cm | 1.3x |
| 2013 | 10.0 cm | 1.37 | 13.7 cm | 1.4x |
| 2015 | 10.0 cm | 1.29 | 12.9 cm | 1.3x |
| 2019 | 10.0 cm | 1.26 | 12.6 cm | 1.3x |
| 2021 | 10.0 cm | 1.31 | 13.1 cm | 1.3x |
| 2023 | 10.0 cm | 1.29 | 12.9 cm | 1.3x |

**EIGHT OF ELEVEN YEARS ARE PROPERLY SAMPLED at 1.26-1.42 px. Three are not, and badly:**
* **1998 resolves at 2.4 METRES** - six times its grid. For canopy work at individual-crown scale it
  is close to useless, which materially weakens the it.72/it.71 case for a 1998 panchromatic pilot.
  **I am revising that recommendation down**: the pilot would be testing a method on an image with
  no crown-scale detail.
* **2005 resolves at 81 cm despite a nominal 20 cm** - four times oversampled, and **coarser in
  reality than 2000's nominal 40 cm.**
* **2000 resolves at 111 cm**, nearly three times its grid.

**AND THIS STILL DOES NOT FULLY EXPLAIN PERFORMANCE, WHICH I SHOULD SAY PLAINLY.** Ordering by
effective resolution puts 2005 (81 cm) *worse* than 2002 (57 cm), yet matched recall runs the other
way - 2005 at 0.7086 against 2002 at 0.6541, and 2005's AUC of 0.9134 is mid-pack. **So effective
resolution is a better axis than nominal GSD but it is still not the whole explanation for the
2000/2002 deficit.** Three attempts at that explanation have now failed - nominal GSD (it.77),
spectral sharpness (it.79) and effective resolution (here). Something else distinguishes the two
oldest acquisitions and I do not yet know what it is.

**THE CAVEAT THAT MAY ALSO BE THE OPPORTUNITY.** Every King County file here is EPSG:3857, and
reprojection to Web Mercator is itself a resampling that blurs. **The softness measured above may
have been introduced by our own mosaicking and reprojection rather than by the original
acquisition.** That is testable and, if true, valuable: re-deriving the early years from
native-projection sources could recover real detail that no retraining can. **A 2.8x oversampling
in 2000 and 4.0x in 2005 are large enough to be worth checking before any further modelling effort
is spent on those years.**

**IMMEDIATE CONSEQUENCE.** `tier_of(gsd_cm)` assigns training recipes from the nominal figure. On
these numbers 2005 is tiered on 20 cm while resolving at 81 cm, and 1998 - if it were ever added -
would be tiered on 40 cm while resolving at 2.4 m. **The tier logic is keyed to a number that is
wrong by up to 6x for the years it matters most.**
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)
s = s.replace("""2. **Q138. Measure effective resolution properly""",
"""2. **Q139. [TESTABLE, POTENTIALLY RECOVERS REAL DETAIL] Is the softness ours or the sensor's?**
   Every King County file is EPSG:3857 and reprojection blurs. If 2000's 2.8x and 2005's 4.0x
   oversampling were introduced by our mosaicking, native-projection sources would recover detail
   that no retraining can. Check the source archives before spending more modelling effort on the
   early years.
3. **Q140. What DOES explain the 2000/2002 deficit?** Nominal GSD, spectral sharpness and now
   effective resolution have all failed to account for it. Remaining candidates: scanned film vs
   digital capture, compression, a different contractor's processing chain, or genuinely different
   canopy. **Three failed explanations is a signal to stop guessing and look at the imagery.**
4. **Q138 SUPERSEDED - measure effective resolution properly""")
io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 80 | 2026-08-19 | *** EMPIRICAL - effective resolution MEASURED; gsd_cm is wrong by up to "
       "6x (Q138) *** | - | Automatic edge-response, 10-90% rise x true GSD, same 12 sites all years. "
       "BUG CAUGHT MID-EXPERIMENT: np.interp(0.10,e,off) requires an INCREASING x-array and an edge "
       "profile is non-monotonic, so 5 years returned EXACTLY 6.70 px = the profile half-width. The "
       "tell was the impossible coincidence. Replaced with explicit crossing search; after the fix "
       "all 12 sites resolve in all 11 years and good years land at ~1.3 px, the expected value. "
       "EFFECTIVE cm: 1998 244.7 (6.1x oversampled!) | 2000 110.8 (2.8x) | 2005 80.7 (4.0x, and "
       "COARSER THAN 2000's NOMINAL 40cm) | 2002 57.1 | 2007 25.5 | 2009 26.1 | 2013 13.7 | 2015 "
       "12.9 | 2019 12.6 | 2021 13.1 | 2023 12.9. REVISING DOWN the 1998 panchromatic-pilot "
       "recommendation: at 2.4 m effective it has no crown-scale detail. BUT STILL DOESN'T EXPLAIN "
       "PERFORMANCE - 2005 (81cm) is worse than 2002 (57cm) yet recalls .7086 vs .6541. THREE "
       "explanations for the 2000/2002 deficit have now FAILED: nominal GSD, spectral sharpness, "
       "effective resolution (Q140). CAVEAT=OPPORTUNITY: all King files are EPSG:3857 and "
       "reprojection blurs, so the softness may be OURS, not the sensor's - native-projection "
       "sources could recover detail no retraining can (Q139). tier_of(gsd_cm) assigns recipes from "
       "a number wrong by up to 6x |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
