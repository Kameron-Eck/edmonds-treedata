import io
p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### LITERATURE + INVENTORY (NOT measured yet) - RELIEF DISPLACEMENT, AND THE ARCHIVE STARTS IN 1936 - 2026-08-19
**Labelled honestly: this iteration establishes a MECHANISM from the literature and an INVENTORY
fact from disk. Neither is a measurement of our data. The empirical test is queued, not done.**

**1. RELIEF DISPLACEMENT IS A REAL, TEXTBOOK DEFECT AND WE HAVE NEVER ACCOUNTED FOR IT (Q123).**
A conventional orthophoto is rectified with a **bare-earth DTM**. The consequence, stated the same
way by every source consulted: *only the BASE of a tree or building is placed in its true position;
everything above ground level is displaced radially from nadir, by an amount proportional to its
height.* Gharibi & Habib 2018 (ID 198) and Chen et al. 2014 (ID 200) both make this explicit.

**Why this is not a footnote for us.** The displacement magnitude is `d = (h/H) * r` - object height
over flying height, times radial distance from nadir. For a 20 m crown at 500 m from nadir on a
3,000 m flight, `d = 3.3 m`. **At our 10 cm King County GSD that is 33 pixels.** The displacement
therefore grows along **exactly the axis our height staircase runs on**, and it is largest for the
tall crowns where we report our best recall.

**It cuts against the staircase rather than creating it.** More displacement means more
mask-versus-reference disagreement, so it should DEPRESS tall-band recall. We measure tall-band
recall as our HIGHEST (0.9421 pervious, 30 m+). **So relief displacement cannot be manufacturing the
staircase - if anything the true height effect is stronger than measured.** That is a useful thing
to have established before testing it.

**Where it could bite hardest is the deliverable, not the accuracy table.** Our 17 acquisitions were
flown as different frame layouts, so **each year carries a different displacement field**. Chen 2014
and the general true-ortho literature are explicit that DTM orthorectification "can lead to spurious
changes when comparing multitemporal images, particularly in areas with buildings and trees."
**That predicts apparent canopy change where none occurred, concentrated on tall crowns and near
buildings - a threat to the 2000-2024 change series that no amount of extra labelling would fix.**

**Coverage check, which is why this counts as a blind spot rather than a parked question:** searching
all 197 tracker rows for `off-nadir`, `view angle`, `BRDF` and `orthorectif` returned **zero**.

**2. THE ARCHIVE HAS TWO ACQUISITIONS OLDER THAN ANYTHING IN THE CATALOG.**
`D:\edmonds-pipeline\Imagery\1936_king_rgb.tif` and `1998_king_rgb.tif` exist, are mirrored on
`G:\My Drive\treedata\Full_Image\KingCo\`, and **already have crops cut in `phase4/crops/`** - so
something in this project has looked at them before. They appear in **no** `imagery_catalog.csv` row.
The 2026-08-18 CHATLOG entry (13c) flagged them as "unassessed" alongside 2005/2007/2009/2012/2017/
2019/2021/2023; the middle years have since been scored, **these two have not**.

**A 1936 frame is panchromatic, and that is a different problem, not a harder version of ours.**
Tian et al. 2025 (ID 202) states plainly that **no** existing tree-delineation method works on
panchromatic alone because colour is treated as essential, and bridges the gap with a
**deep-learning colorization step** - a technique absent from all 200 prior tracker rows.
**This CONTRADICTS the framing of our own cross-sensor work**, which has treated the historical
problem as radiometric domain shift between comparable RGB sensors. For a single-band frame the gap
is a **missing modality**, not a shift, and the style-transfer methods in our plan (FDA, FOSMix)
assume matched channel counts and cannot apply. Every greenness diagnostic we have built - GRVI,
the leaf-off signature, the NDVI reference - is simply **undefined** there.

**3. A STALENESS FLAG, MINOR BUT WORTH ONE LINE.** `imagery_stats/imagery_catalog.csv` still carries
the pre-correction `gsd_cm` values (2013 as 14.9 cm) that the 2026-08-18 config fix replaced with
true ground GSD (10.0 cm). The CSV also has no 2002 row although 2002 masks and area figures exist.
**The audit already happened and I am not re-reporting it as new** - the point is only that this one
artefact was not regenerated afterwards, so reading it can re-introduce a corrected error.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""### Known unknowns we are choosing to live with""",
"""- **Q124.** Can the series be pushed back to 1936 and 1998 at all, and should it be? The frames
  exist and crops were cut, but a panchromatic frame breaks every greenness diagnostic we own and
  needs a colorization or texture-only route (IDs 201-203). **Decide before scoping, not after** -
  a 1936 baseline would roughly triple the temporal span of the deliverable, which is either the
  most valuable extension available or an unbudgeted research project.
- **Q125.** Does each acquisition's displacement field differ enough to manufacture apparent canopy
  CHANGE? This is the deliverable-level version of Q123 and matters more than the accuracy-table
  version. Testable by looking for change concentrated on tall crowns near buildings, with a
  spatial pattern that follows frame layout rather than parcels.

### Known unknowns we are choosing to live with""")

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 70 | 2026-08-19 | LITERATURE + INVENTORY (not measured) - relief displacement, and the "
       "archive starts in 1936 | Gharibi 2018 (198), Wagner 2024 (199), Chen 2014 (200), Mboga 2020 "
       "(201), Tian 2025 (202), Kostrzewa 2025 (203) | (1) A conventional orthophoto is rectified on "
       "a BARE-EARTH DTM, so only the BASE of a tree lands correctly and everything above ground is "
       "displaced radially, PROPORTIONAL TO HEIGHT. d=(h/H)*r: a 20 m crown 500 m off nadir at 3 km "
       "= 3.3 m = 33 px at our 10 cm King GSD. Runs along the SAME axis as our staircase but CUTS "
       "AGAINST it (more displacement = worse agreement, yet tall-band recall is our highest .9421), "
       "so it cannot be manufacturing the staircase - the true height effect may be STRONGER. Bigger "
       "risk is the DELIVERABLE: 17 acquisitions = 17 frame layouts = 17 displacement fields -> "
       "SPURIOUS CHANGE on tall crowns near buildings (Q125). 0 of 197 papers covered "
       "off-nadir/view-angle/BRDF/orthorectif. (2) 1936_king_rgb.tif and 1998_king_rgb.tif are ON "
       "DISK with crops already cut, in NO catalog row. Panchromatic = MISSING MODALITY not domain "
       "shift; FDA/FOSMix assume matched channels and cannot apply; GRVI/NDVI/leaf-off all UNDEFINED "
       "there. Tian 2025 uses DL COLORIZATION as the bridge - absent from all 200 prior rows (Q124) |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
