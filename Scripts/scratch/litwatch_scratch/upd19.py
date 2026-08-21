import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 31 - SUN ANGLE, ILLUMINATION & SHADOW - 2026-08-18 - IDs 149-150
The other half of the acquisition-conditions problem, and it surfaces an internal inconsistency
in our own pipeline that nobody has flagged.

**Shadow is not a nuisance, it silently corrupts the map.** Lasko et al. 2026 (ID 149, Ecological
Informatics) find that correcting low-sun-angle tree and terrain shadow **reveals land cover
mapping errors that were previously invisible**. In low-sun imagery, shadows extend well beyond
the actual canopy footprint - which is simultaneously a **commission** risk (shadow read as dark
canopy) and an **omission** risk (shadowed crowns too dark to detect). Both directions are live
for us, and neither is measured.

**THE INCONSISTENCY IN OUR OWN PIPELINE.** From STATE: the structure channel is
`struct = clip(hillshade_fr - hillshade_be + 127)`, and hillshade is computed at a **fixed 315
degree sun azimuth**. So:

* the LIDAR-derived channel assumes one fixed illumination geometry, for every year;
* the actual IMAGERY was flown at 17 different, unknown solar geometries;
* the model sees both, stacked, on every tile.

The structure channel therefore carries a *constant* illumination assumption while the RGB
carries a *varying* one. That mismatch has never been examined. It is a plausible contributor to
why the struct channel measured weak (AUC ~0.70) and was eventually superseded by the real CHM -
and if we ever revive hillshade-style inputs, the azimuth should match each acquisition, which we
cannot do without dates.

**Everything again points at the same missing fact.** Sun elevation and azimuth are deterministic
functions of date, time and location. We have the location. Dates would give us the rest for free -
and would simultaneously settle phenology (Q29), the 2017 pair's validity (Q24) and this. **The
single highest-leverage fact this loop has identified is not in any paper: it is the flight dates.**

**If we do handle shadow, weigh two options.** SARU (ID 150, ISPRS, peer-reviewed) is the current
state of the art for joint shadow detection and removal. But removal RECONSTRUCTS pixel values,
which the honest-measurement rule would then have to defend - the same objection raised against
colorization in Search 15. The cheaper and more defensible option for us is to **detect shadow and
mask it to IGNORE**, which fits our existing three-state supervision rule and invents nothing.
Read SARU as the upper bound on what shadow handling can buy before paying for it.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Audit coverage against the Rafi 2024 survey taxonomy (Q28)** - which DG families has this
   loop never touched at all? Cheaper and more informative than sampling one more method, and the
   loop is now 19 iterations deep without a coverage check.
2. **Instance-norm / whitening families for style removal** - architecture-level branch of the
   style thread, surfaced in Search 29 and still unfollowed.
3. **Deep ensembles vs cheaper uncertainty under shift.**
4. **Instance segmentation of tree crowns at 7.5 cm, 2025-2026 state of the art.**
5. **Temporal consistency as a training objective** rather than a post-hoc fix.
6. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11.
7. **Spatially-aware pseudo-labelling specifically** - the good half of SpADANN.
8. **How the Landsat/MODIS harmonization community validates a multi-decade series.**
9. **Shadow masking as IGNORE vs shadow removal** - which is defensible under an
   honest-measurement rule, and what does masking cost in usable area?
10. **Meta-learning family for DG** - named by Rafi 2024, never touched here.

**NOT a literature item, but the highest-leverage action identified in 19 iterations:**
**recover the acquisition dates.** King County GIS, WA state imagery programs and USDA NAIP all
publish flight dates. One fact collapses Q19, Q24, Q29 and the whole illumination axis at once.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

s = s.replace("""- **Q30.** Should the per-crown validity intervals carry an explicit SEASONAL term?""",
"""- **Q31.** Does the fixed-315-degree hillshade assumption in the structure channel conflict with
  17 different unknown imagery illumination geometries? The lidar channel carries a CONSTANT
  illumination assumption while the RGB carries a VARYING one, stacked on the same tile. Never
  examined; a plausible contributor to the struct channel's weak AUC (~0.70).
- **Q32.** Shadow: mask to IGNORE, or remove/reconstruct? Removal (ID 150) invents pixel values
  the honest-measurement rule would have to defend - the same objection raised against
  colorization. Masking fits our three-state supervision rule but costs usable area. How much
  area? Unmeasured.
- **Q30.** Should the per-crown validity intervals carry an explicit SEASONAL term?""")

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 19 | 2026-08-18 | Search 31 - sun angle, illumination, shadow | 149-150 | "
       "Shadow correction REVEALS hidden land-cover mapping errors (Lasko 2026) - low sun angle is "
       "both a commission and an omission risk, neither measured for us. INTERNAL INCONSISTENCY "
       "FOUND: our struct channel assumes a FIXED 315deg sun while 17 acquisitions have 17 unknown "
       "solar geometries. Flight dates now identified as the single highest-leverage missing fact "
       "(collapses Q19+Q24+Q29+illumination). New Q31/Q32 |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
