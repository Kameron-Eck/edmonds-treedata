import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 26 - paired cross-sensor imagery & canopy-series harmonization - 2026-08-18 - IDs 138-139
Prompted by the iteration-13 discovery that we hold a matched same-year 2017 pair.

**A published analogue for the WHOLE project finally exists (ID 138, Vogeler et al. 2018, RSE,
peer-reviewed).** A 42-year Minnesota forest CANOPY COVER series across multiple Landsat sensor
generations, where inter-sensor harmonization is the central problem rather than a footnote.
Search 23 concluded nobody spans our regime from the ML side; this is the same problem approached
from the remote-sensing side, and it is the precedent we should be measured against. The trade is
inverted: 42 years at coarse resolution there, 24 years at fine resolution here - so their sensor
problem is harder and our spatial problem is harder.

**Independent convergence on the amplitude thread (ID 139, Li et al. 2025).** Cross-sensor
high-resolution land use, and it splits the problem exactly along the axis our 2017 pair can
isolate: **positional encoding for RESOLUTION differences, random AMPLITUDE MIXUP for
SPECTRAL/style inconsistency.** That is the FDA principle (ID 136, amplitude = style) arriving
from a second direction. Three independent lines - iteration 10 (FDA), iteration 13 (the matched
pair), and this - now point at the same design: treat GSD and sensor as two separate axes, and
handle style in the frequency domain. Its dynamic pseudo-labelling stage carries the usual
confirmation-bias risk (ID 89) and should be treated as optional.

**The experimental template for the 2017 pair, from the search itself.** A Landsat sensor-transfer
study measured performance transferring OLI -> ETM+ *in the same area and year*, and reported that
upper-bound models trained and tested on the target sensor consistently beat directly transferred
models - the gap between the two IS the sensor gap. Applied to us:

| run | train on | test on | measures |
|---|---|---|---|
| upper bound | 2017-King | 2017-King | what the model can do on that sensor |
| transfer | 2017-CoE (or 2020) | 2017-King | what we actually get across the source gap |
| resolution control | 2017-CoE downsampled to 14.93 cm | 2017-King | isolates sensor from GSD |
| FDA arm | 2017-CoE, amplitude swapped to King | 2017-King | does frequency-domain style transfer close it |

Same ground, same year: canopy change, phenology and land-use change all cancel. This is the
first design in the loop that could give consensus finding (a) a NUMBER instead of an assertion.

**Caveat repeated:** within-2017 flight dates are unknown (Q19 - no metadata in any raster), so
season and sun angle are not guaranteed matched. Check before calling it controlled.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

old_q_start = s.index("## QUEUE - uncovered angles, highest value first") if "## QUEUE - uncovered" in s else s.index("## QUEUE")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **BN in segmentation under domain shift** - the `FREEZE_ENCODER_BN` conflict (Q9). Long
   deferred and now the oldest unaddressed item.
2. **Radiometric/style normalization vs style-transfer augmentation, head to head.** Phase 2
   Search 5 covered classical normalization; FDA (ID 136) and amplitude mixup (ID 139) are the
   generative-era contenders, and the 2017 pair is the test bed.
3. **Deep ensembles vs cheaper uncertainty under shift.**
4. **Instance segmentation of tree crowns at 7.5 cm, 2025-2026 state of the art.**
5. **Temporal consistency as a training objective** rather than a post-hoc fix.
6. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11. Retry with
   different vocabulary (efficiency, informativeness, set size).
7. **Spatially-aware pseudo-labelling specifically** - separate the good half of SpADANN from
   the half we distrust.
8. **Shadow / illumination / sun-angle as a distinct domain axis.** Never searched; sharpened by
   Q24 (unknown 2017 flight dates) - if sun angle is a major axis, the matched pair is weaker
   than it looks.
9. **Phenology / leaf-on vs leaf-off across acquisitions.** Related to #8 and never examined,
   despite deciduous crowns being the known blind spot.
10. **How the Landsat/MODIS harmonization community validates a multi-decade series** - follow
    Vogeler (ID 138) into its methodological lineage rather than the ML literature.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 14 | 2026-08-18 | Search 26 - paired cross-sensor & canopy-series harmonization | 138-139 | "
       "A published analogue for the whole project exists after all: Vogeler 2018, 42-yr Minnesota "
       "canopy series across Landsat sensor generations (RSE). Li 2025 independently splits "
       "RESOLUTION (positional encoding) from STYLE (amplitude mixup) - third line converging on "
       "amplitude=style. Extracted a 4-arm experimental template for the 2017 matched pair |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
