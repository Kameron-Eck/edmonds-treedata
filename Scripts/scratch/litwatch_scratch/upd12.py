import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 25 + INVENTORY AUDIT - 2026-08-18 - ID 137
**Q17 (tuning as the honest baseline) - the literature is blunt.** Brigato et al. 2021 (ID 137)
tuned only learning rate, weight decay and batch size on six datasets including satellite
imagery, and the resulting plain baseline **outperformed all but one specialized data-efficient
method**. Our v030-v048 history is dominated by DEBUGGING - sampler, BN freeze, metric artifacts,
OOM - not tuning. So the cheapest untried gain in the project may be a proper hyperparameter
search on the model we already have, and it sets the bar every fancier proposal must clear:
**beating an under-tuned baseline proves nothing.**

---

### Q19 ANSWERED - NO ACQUISITION METADATA EXISTS IN OUR RASTERS
Probed the TIFF tags on 2000 / 2013 / 2016 / 2017 / 2019 imagery. Every file carries only
`AREA_OR_POINT` plus compression settings (DEFLATE/LZW, PREDICTOR 2). **No camera, no
contractor, no flight date, no sun angle.** These are re-processed derivatives; the original
metadata was stripped or never carried through.

**Consequence:** the ground truth that would have beaten every pixel-based proxy is not in our
files. It would have to be recovered from the source portals (King County GIS, WA state,
USDA/NAIP), which is an external-data errand, not a computation. Until then the amplitude
signature (ID 136) is the best available instrument, and the iteration-11 clustering stands as
the only evidence we have about domain structure.

---

### INVENTORY IS INCONSISTENT - THREE DEFECTS, ALL NEW
Found while chasing the metadata question. None of these were known.

**1. `imagery_stats/imagery_catalog.csv` is INCOMPLETE.** It lists 17 images / 14 years and
**omits 2002 and 2012**, both of which exist on Drive as `2002_king_rgb.tif` and
`2012_king_rgb.tif`. STATE quotes an honest 2002 recall of .5069, so 2002 is actively in use
while being absent from the catalog that describes the stack.

**2. The iteration-11 domain clustering therefore has a HOLE.** It clustered the catalog's 17
acquisitions, so **2002 and 2012 were silently excluded**. The conclusions (agency is not the
domain axis; 2017-CoE pairs with 2019-KC; 2024 is an outlier) are unaffected in direction, but
the King County grouping is incomplete - two of its images were never scored. Re-run once the
catalog is fixed.

**3. CONFLICTING PROVENANCE LABEL FOR 2017.** Drive has `2017_coe_rgb.tif` (matching the
catalog's "City of Edmonds"); the local D: mirror has `2017_king_rgb.tif`. Same year, two
different agency labels, two different filenames. Either one is a renamed copy - in which case
a provenance label is simply wrong somewhere - or they are two different 2017 products and the
pipeline may be reading whichever the resolver finds first. **This is exactly the kind of
mislabelling that makes agency-keyed anchors unsafe**, and it is independent evidence for the
iteration-11 conclusion.

D: also holds 1936, 1998, 2002 and 2012 rasters that the catalog does not mention at all.

**Recommended, in order:** regenerate the catalog over the actual holdings; resolve the 2017
filename conflict; re-run `phase4_qc_domain_cluster.py`; only then rebuild the anchor grouping.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

old_q19 = """- **Q19.** What ARE the true domain groups? The screen suggests at least: {2005, 2007},
  {2009, 2021, 2023}, {2017, 2019, 2020, 2022 ...}, {2019n, 2021s}, {2024 alone}. But the screen
  is confounded and the real answer is acquisition metadata (camera, contractor, flight date, sun
  angle). **Does that metadata exist for these 17 images?** If yes it beats every pixel-based
  proxy and should be recovered first. If no, the amplitude signature (ID 136) is the fallback."""

new_q19 = """- **Q19.** What ARE the true domain groups? **PARTLY ANSWERED.** The metadata that would settle
  it does NOT exist in our rasters - TIFF tags carry only AREA_OR_POINT and compression. It would
  have to come from the source portals (King County GIS, WA state, USDA/NAIP): an external errand.
  Until then the amplitude signature (ID 136) is the best instrument and the iteration-11 screen
  is the only evidence. Screen suggests at least {2005, 2007}, {2009, 2021, 2023},
  {2017, 2019, 2020, 2022 ...}, {2019n, 2021s}, {2024 alone} - **but computed without 2002/2012**.
- **Q21.** Is `2017_coe_rgb.tif` (Drive) the same raster as `2017_king_rgb.tif` (D: mirror)?
  Same year, two agency labels, two filenames. If a renamed copy, one provenance label is wrong;
  if two products, the pipeline may be reading whichever resolves first. Cheap to check
  (dimensions, checksum) and it undermines any agency-keyed design until resolved.
- **Q22.** Why does the catalog omit 2002 and 2012 when both exist and 2002 is actively quoted
  in STATE? Is the catalog stale (May 2026), or were they deliberately excluded for a reason
  nobody recorded?"""

assert old_q19 in s, "Q19 anchor not found"
s = s.replace(old_q19, new_q19, 1)

old_q17 = """- **Q17.** What hyperparameter-tuning budget did our ResNet-101 baseline actually receive?"""
new_q17 = """- **Q17.** [LITERATURE ANSWERED, PROJECT SIDE OPEN] What hyperparameter-tuning budget did our
  ResNet-101 baseline actually receive?"""
s = s.replace(old_q17, new_q17, 1)

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 12 | 2026-08-18 | Search 25 (tuning baseline) + inventory audit | 137 | "
       "Tuning alone beat all but one specialist method (Brigato) - our history is debugging not "
       "tuning. Q19 ANSWERED: NO acquisition metadata in any raster. THREE NEW INVENTORY DEFECTS: "
       "catalog omits 2002+2012 (2002 is quoted in STATE); iteration-11 clustering therefore has a "
       "hole; 2017 has CONFLICTING agency labels across Drive vs D: |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
