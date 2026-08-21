import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### WHICH IMAGERY DOES THE PIPELINE ACTUALLY USE? - 2026-08-18 (Kam asked)
Traced through the code rather than the catalogs. Three answers, one discovery.

**1. THE AUTHORITY IS `phase2_data_prep.py`, NOT `pipeline_config.py`.**
`phase4seg/config.py:317` says so in a comment: *"18-ENTRY IMAGERY CATALOG (verbatim from
phase2_data_prep.py - the authority)"*. The 18 entries are
2000, 2002, 2005, 2007, 2009, 2013, 2015, 2016, 2017, 2019, 2019n, 2020, 2021, 2021s,
2022, 2022n, 2023, 2024. All 18 files exist on Drive.

**But `pipeline_config.py` self-describes as "Single source of truth for all pipeline paths and
catalog" and holds a DIFFERENT, smaller catalog** - 2013/2015/2019/2021/2023 + 2017/2020/2022/
2024 + the starred supplementals. **It contains no pre-2013 year at all**, and
`raw_path(2000)` would raise `KeyError`. Two files each claim authority and they disagree; the
one that says "single source of truth" is the wrong one. This breaks the one-fact-one-home rule
directly.

**2. RESOLUTION ORDER.** `phase4seg/common.py:92 resolve_native_path()` tries `NATIVE_DIR`
(`Pipeline Imagery/native/`) then `IMAGERY_DIR` (`Pipeline Imagery/`). `native/` is empty, so
every year resolves to `Full_Image/Pipeline Imagery/<native_file>` on Drive. Training and
inference are Colab-only and read Drive exclusively. The LOCAL QC scripts are the opposite -
they prefer `D:\\edmonds-pipeline\\Imagery` and fall back to Drive.

**3. ORPHANS - on disk, not in the catalog, not used:** `2012_king_rgb.tif` (Drive),
plus `1936_king_rgb.tif`, `1998_king_rgb.tif` and `2017_king_rgb.tif` (D: only).

---

### THE DISCOVERY: THERE ARE TWO DIFFERENT 2017 ACQUISITIONS
`2017_king_rgb.tif` is **not** a renamed copy. Measured:

| file | dims | GSD | bounds |
|---|---|---|---|
| D: `2017_king_rgb.tif` | 74496 x 105984 | 14.93 cm | -13625894.0, 6068450.3, -13614772.4, 6084272.8 |
| Drive `2017_coe_rgb.tif` | 148736 x 211968 | 7.46 cm | -13625894.0, 6068450.3, -13614791.5, 6084272.8 |

Two distinct products, **same year, essentially the same ground** (eastern edge differs by ~19 m),
different source and different GSD. Only the CoE one is in the catalog.

**This is the cleanest natural experiment in the project and nobody has used it.** Every
cross-source comparison we have is confounded by canopy change, season and sun angle because the
years differ. A matched same-year pair removes the temporal confound entirely:

* **Measure the CoE-vs-King County domain gap directly** - the exact quantity the per-(sensor x
  era) anchors are supposed to absorb, and which iteration 11 could only infer from clustering.
* **Test the iteration-11 claim** that 2017-CoE pairs with 2019-King. If CoE and King share
  EagleView in the later years, 2017-King and 2017-CoE should be radiometrically close after
  resolution is matched. If they are far apart, the shared-contractor story starts later than 2017.
* **Test FDA (ID 136) with a ground truth** - swap low-frequency amplitude between the pair and
  check whether the model's output on one converges to its output on the other. On a matched pair
  the only differences are style, so this isolates exactly what FDA claims to fix.
* **Separate GSD from sensor** - downsample the 7.46 cm CoE raster to 14.93 cm and compare. What
  survives is sensor/contractor; what disappears was resolution. That is consensus finding (a)
  turned into a measurement instead of an assertion.

**Caveat:** acquisition DATES within 2017 are unknown (no metadata, per Q19), so season and sun
angle are not guaranteed matched. Check before treating the pair as a controlled comparison.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

old_q21 = """- **Q21.** Is `2017_coe_rgb.tif` (Drive) the same raster as `2017_king_rgb.tif` (D: mirror)?
  Same year, two agency labels, two filenames. If a renamed copy, one provenance label is wrong;
  if two products, the pipeline may be reading whichever resolves first. Cheap to check
  (dimensions, checksum) and it undermines any agency-keyed design until resolved."""

new_q21 = """- **Q21.** Is `2017_coe_rgb.tif` the same raster as `2017_king_rgb.tif`? **ANSWERED: NO.**
  Two genuinely different 2017 products - King County at 14.93 cm (74496x105984) and City of
  Edmonds at 7.46 cm (148736x211968), near-identical bounds. No silent wrong-file risk (the
  names differ, so a lookup cannot collide), but the King County 2017 raster is an orphan that
  is not in the catalog. **It is also the best unused asset in the project** - see the matched-pair
  experiments above.
- **Q23.** `pipeline_config.py` calls itself the single source of truth but omits every pre-2013
  year, while `phase4seg/config.py` names `phase2_data_prep.py` as the authority and carries all
  18. Which is meant to be canonical, and is anything still importing the wrong one? A stale
  `raw_path()` call on a pre-2013 year raises `KeyError` rather than failing quietly, so this has
  probably not corrupted results - but it should be reconciled before more code depends on it.
- **Q24.** Were the two 2017 acquisitions flown at similar dates? Without it the matched pair is
  still useful but is not a controlled comparison - season and sun angle would be confounded."""

assert old_q21 in s, "Q21 anchor not found"
s = s.replace(old_q21, new_q21, 1)

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 13 | 2026-08-18 | Which imagery does the pipeline use? (Kam asked) | - | "
       "AUTHORITY = phase2_data_prep.py (18 entries), mirrored into phase4seg/config.py; "
       "pipeline_config.py claims to be the single source of truth but omits ALL pre-2013 years. "
       "DISCOVERY: 2017_king_rgb.tif is NOT a copy - two distinct 2017 acquisitions, same ground, "
       "14.93cm vs 7.46cm. A matched same-year cross-source pair = the cleanest natural experiment "
       "in the project, currently unused |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
