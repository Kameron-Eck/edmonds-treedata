import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 30 - PHENOLOGY - 2026-08-18 - IDs 147-148
**This may be an alternative explanation for our headline finding, and it has never been on the
table.**

The canopy-mapping literature is blunt about it: **leaf-off imagery underestimates canopy cover
in deciduous regions**, and seasonality is described as the single biggest source of error in
canopy work where leaf-on/leaf-off contrast is strong. Kokubu et al. 2020 (ID 147) quantifies
urban canopy cover changing with season at city scale.

Now put that next to STATE: **scrub recall .25 vs forest .68 - "fails on non-conifer/mixed
structure (the conifer-only-label blind spot)"**. Conifers hold colour year-round; deciduous do
not. **A shoulder-season or leaf-off acquisition would make any model look conifer-biased even if
it is not.** We have never had acquisition dates (Q19: no metadata in any raster), so this has
been an uncontrolled variable across all 18 acquisitions and all of our cross-year comparisons.

**Free screen run this iteration** - scene-mean greenness excess GRVI = (G-R)/(G+R), computed from
band statistics already in the catalog:

| lowest GRVI | | highest GRVI | |
|---|---|---|---|
| 2023 | 0.0143 | 2019n | 0.1521 |
| 2019 | 0.0224 | 2009 | 0.1187 |
| 2017 | 0.0242 | 2016 | 0.0875 |
| **2020** | **0.0250** | 2000 | 0.0850 |
| 2024 | 0.0322 | | |

**Our one labelled year, 2020, sits fourth-lowest.** If that reflects phenology, the 2020 labels
were drawn on imagery where deciduous canopy was least visible - which would *produce* the
conifer-only blind spot, and every coarse year taught from that mask would inherit it. That is a
mechanistic account of finding 4 we have not previously considered.

**BUT THE SCREEN IS BADLY CONFOUNDED AND MUST NOT BE OVERREAD.** The low-GRVI group
(2017, 2019, 2020, 2023, 2024) is almost exactly the group that clustered together in iteration 11,
and includes the 2017-2019 EagleView pair. Low greenness is equally consistent with a shared
contractor COLOUR BALANCE. A scene-wide mean is also dominated by roads and roofs, not canopy.
Nothing here distinguishes the two explanations.

**The discriminating test, and it is cheap and local.** Compute greenness over KNOWN-CANOPY
pixels only - split by conifer-dominated versus deciduous-dominated ground - instead of scene-wide:
* if **deciduous** areas lose greenness in a given year while **conifer** areas hold it -> PHENOLOGY.
* if **everything** shifts together -> COLOUR BALANCE / sensor.

Inputs all exist: the 2020 mask, C-CAP forest classes, the CHM, and the per-year orthos. No
labels, no GPU. This is now the highest-value cheap experiment the loop has identified, because it
discriminates between two explanations for the project's central finding.

**Framing to adopt either way (ID 148, Kou et al. 2020):** treat seasonal difference as a DOMAIN
SHIFT to be modelled, not as noise. We currently attribute every cross-year difference to canopy
change or model error, with no seasonal term at all.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Shadow / illumination / sun-angle as a distinct domain axis.** The other half of the
   acquisition-conditions problem; also decides whether the 2017 matched pair is controlled (Q24).
2. **Instance-norm / whitening families for style removal** - architecture-level branch of the
   style thread.
3. **Audit coverage against the Rafi 2024 survey taxonomy (Q28)** - which DG families has this
   loop never touched? Cheaper than sampling one more method.
4. **Recovering acquisition dates from external sources** - not a literature question but the
   single fact that would collapse Q19, Q24 and the phenology confound at once. King County GIS,
   WA state imagery programs, USDA NAIP metadata all publish flight dates.
5. **Deep ensembles vs cheaper uncertainty under shift.**
6. **Instance segmentation of tree crowns at 7.5 cm, 2025-2026 state of the art.**
7. **Temporal consistency as a training objective** rather than a post-hoc fix.
8. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
9. **Spatially-aware pseudo-labelling specifically** - the good half of SpADANN.
10. **How the Landsat/MODIS harmonization community validates a multi-decade series.**

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

s = s.replace("""### Answerable only by our own experiment""",
"""- **Q29.** Is the conifer-only blind spot partly PHENOLOGY rather than label bias? Our labelled
  year (2020) has the fourth-lowest scene greenness in the archive. If 2020 is a shoulder-season
  or leaf-off acquisition, the labels under-represent deciduous canopy by construction, and every
  coarse year inherits it. **Confounded with contractor colour balance** - the low-greenness group
  is nearly the iteration-11 cluster. Discriminating test: greenness over known-canopy pixels,
  split conifer vs deciduous. Cheap, local, no labels. **Highest-value experiment in the queue.**
- **Q30.** Should the per-crown validity intervals carry an explicit SEASONAL term? We currently
  attribute all cross-year difference to canopy change or model error. If seasonal canopy
  variation in a city is material (ID 147), a validity interval with no seasonal component is
  overstating its own precision.

### Answerable only by our own experiment""")

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 18 | 2026-08-18 | Search 30 - PHENOLOGY | 147-148 | "
       "POSSIBLE ALTERNATIVE EXPLANATION for the conifer-only blind spot: leaf-off imagery "
       "underestimates DECIDUOUS canopy, and our one labelled year (2020) has the 4th-LOWEST scene "
       "greenness of 17. Free GRVI screen run. HEAVILY CONFOUNDED with contractor colour balance "
       "(low-GRVI group ~= the iteration-11 cluster). Discriminating test identified: greenness "
       "over known-canopy pixels split conifer vs deciduous. New Q29/Q30 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
