# What We Know About the Imagery — 2000–2024

**Scope fixed 2026-08-19: 2000–2024 only.** 1936 and 1998 sit outside that window, so no
number in this document covers them.

> **Correction, 2026-08-19 (later the same day): 1936 is NOT an empty shell.** This section
> originally said so, inheriting a CHATLOG finding that was drawn from nine probe windows —
> all of which missed the data. The content band starts **74.8% of the way down the file**
> (row 20094 of 26880). A full-extent read plus a rendered crop shows **real panchromatic
> aerial photography** — shoreline, street grid, forest stands, a lake, field boundaries —
> across the southern quarter, covering **24.4% of the study area** (lat 47.768–47.792).
> 89.9% of the canvas is fill; the other 10.1% is imagery. **Do not delete the file.**
> Out of scope is a decision about the study window, not a claim that the file is empty.
> Renamed `1936_king_pan.tif` / `1998_king_pan.tif` — both are single-band (IMAGERY_PLAN A3).
> See IMAGERY_PLAN.md A2 and the CHATLOG retraction entry.

Every number here is **measured from the files**, not read from a config. Where something has
not been measured, the cell says so — that distinction is the point of this document.

---

## 1. What exists

**19 rasters on Drive for 2000–2024, from four sources.** Two are not in the catalog.

| source | years | CRS | bands | footprint | file sizes |
|---|---|---|---|---|---|
| **King County** | 2000, 2002, 2005, 2007, 2009, *2012*, 2013, 2015, 2019, 2021, 2023 | EPSG:3857 | 3 (RGB) | **100%** | 1.3–12 GB |
| **City of Edmonds** | 2017, 2020, 2022, 2024 | EPSG:3857 | 3 (RGB) | 100% | **25–48 GB** |
| **Snohomish Co.** | 2016, 2021s | **EPSG:2285** | 4 (RGB+NIR) | **41.9%** | ~3.2 GB |
| **NAIP** | 2019n, 2022n | EPSG:26910 | 4 (RGB+NIR) | **69.2%** | ~0.5 GB |

*Italics = on disk, not in the catalog.*

**Two uncatalogued files:**
- `2012_king_rgb.tif` — real imagery on Drive, 2.2 GB, never assessed or used.
- `2017_king_rgb.tif` — **a second, different 2017 acquisition**, on `D:` only, 14.93 cm,
  distinct from the 48 GB `2017_coe_rgb.tif`. Same year, same ground, different source.

**2020 is the only year with hand labels.** Every other year is taught from a model
prediction of it.

---

## 2. Resolution — the config was wrong twice over

### 2.1 `gsd_cm` was CRS units × 100, not ground centimetres *(fixed)*

The catalog assumed every CRS was metric. Two are not:

| source | why it was wrong | stated | **true** |
|---|---|---|---|
| Snohomish | EPSG:2285 is **US survey feet** | 50.0 cm | **15.4 cm** |
| King / CoE | Web Mercator inflates by 1/cos(47.8°) = 1.49× | 59.7 / 14.9 / 7.5 | **40.1 / 10.0 / 5.0** |
| NAIP | EPSG:26910 is metric — was already right | 60.0 | 60.7 |

Corrected in `phase4seg/config.py`. **Tier is pinned** for 2016/2021s via `tier_for()` so the
correction did not silently re-recipe those years onto contaminated crown polygons.

### 2.2 The grid is not the resolution *(measured, King years only)*

Edge-response measurement over 12 fixed sites. **Effective resolution** is the ground distance
over which the image actually transitions across a sharp boundary:

| year | true GSD | **effective** | oversampling |
|---|---|---|---|
| 2000 | 40.1 cm | **110.8 cm** | **2.8×** |
| 2002 | 40.1 cm | 57.1 cm | 1.4× |
| 2005 | 20.1 cm | **80.7 cm** | **4.0×** |
| 2007 | 20.1 cm | 25.5 cm | 1.3× |
| 2009 | 20.1 cm | 26.1 cm | 1.3× |
| 2013 / 2015 / 2019 / 2021 / 2023 | 10.0 cm | 12.6–13.7 cm | 1.3–1.4× |

**2005 resolves coarser than 2000's nominal grid despite being nominally 2× finer.** Eight of
these years are properly sampled; 2000 and 2005 are not.

**NOT MEASURED:** Snohomish (2016, 2021s), NAIP (2019n, 2022n), City of Edmonds (2017, 2020,
2022, 2024). **That includes 2020, the labelled year.** Extending this to the other nine
acquisitions is the single biggest gap in our characterisation.

---

## 3. Colour is not comparable across sources — proven

Share of pixels a naive greenness test calls vegetated, **over identical ground in every
acquisition**:

| King County (drifts) | | other sources | |
|---|---|---|---|
| 2000 | **.8027** | 2016 Snoh | .6928 |
| 2002 | .5029 | 2021s Snoh | .6157 |
| 2005 | .4782 | 2019 NAIP | **.8919** |
| 2007 | .4016 | 2022 NAIP | .7822 |
| 2009 | .6237 | | |
| 2012 | .6268 | | |
| 2013 | .3463 | | |
| 2015 | .2745 | | |
| 2017k | .1877 | | |
| 2019k | **.1146** | | |
| 2021k | .1344 | | |
| 2023 | .1541 | | |

**The decisive pair: 2019 King reads .1146 and 2019 NAIP reads .8919 — same year, same
ground, same season, differing by 0.78.** That cannot be vegetation, phenology or change. It
is sensor and processing colour balance, and nothing else is available as an explanation.

**And the King series drifts monotonically**, .80 → .11 across 2000–2019, crossing from
positive to negative mean greenness around 2017. **Any greenness diagnostic applied across
this series reports a large, steady canopy decline that is entirely a processing artefact.**

**Consequence:** no cross-sensor or cross-year greenness comparison is valid. Within-year use
(canopy pixels vs the rest of the same image) is unaffected, because the cast is global.

**NOT MEASURED:** the four City of Edmonds years.

---

## 4. Footprints differ by more than 2×

Against the study area (the 2020 mask extent, 7.46 × 10.55 km):

| coverage | acquisitions |
|---|---|
| **100%** | all King County, all City of Edmonds |
| **69.2%** | NAIP 2019n, 2022n |
| **41.9%** | Snohomish 2016, 2021s — a central coastal band, missing 3.99 km north |

**2016 is the most-cited year in this project** — the only NIR year with a matched CHM, and
the year the corrected labels were built for — **and it sees 41.9% of the city.** Every
"citywide" number derived from it is scoped to that band.

The reference rasters have the same problem: C-CAP 2016 was a **clipped copy at 51.9%** until
the full 91% source was found; **C-CAP 2021 is still clipped**, so 2021k and 2023 are scored
on different ground from every other year.

---

## 5. What is missing

| gap | consequence |
|---|---|
| **No acquisition dates in any raster** | phenology and sun angle are uncontrolled across all 18 acquisitions and every cross-year comparison ever made |
| **No overviews on any raster** | every decimated read silently reads the whole multi-GB file — this is why full-raster QC takes 30–60 min a run |
| Effective resolution unmeasured for 9 of 19 | includes 2020, the labelled year |
| Colour cast unmeasured for the 4 CoE years | includes 2020 |
| `2012` and `2017_king` uncatalogued | one is a free extra year, the other is an unused experiment |

---

## 6. The hypothesis this all points at

A crude screen put **2020 fourth-lowest of 18 in scene greenness**. If that is phenological
rather than an artefact of the cast in §3, then the hand labels were drawn on imagery where
deciduous canopy was least visible — which would **manufacture the conifer-only blind spot**,
and every other year, taught from that mask, inherits it. That would make the project's
central defect an artefact of one acquisition date.

**It is currently untestable**, for two reasons that are both fixable: no raster carries a
date (§5), and the greenness screen it rests on is confounded by the cast (§3), which is only
separable *within* a sensor era.

**This is the most consequential open question about the imagery**, and both blockers are
addressable.

---

## 7. What follows

1. **Extend §2.2 and §3 to the missing nine acquisitions** — especially 2020. Both
   instruments exist and are verified (`scratch/litwatch_scratch/q138b.py`, `cast2.py`).
2. **Recover acquisition dates** from the four source archives. External, long lead time,
   and it unblocks §6.
3. **Build overviews.** Cheapest performance win available.
4. **Use the matched 2017 pair.** Two sources, same year, same ground — removes change,
   season and sun angle at once. Nothing else in this archive does that.
5. **Assess and adopt 2012**, or archive it deliberately.

Detail and sequencing: `Scripts/IMAGERY_PLAN.md`.

---

## 8. Lidar — the height layer (added 2026-08-22)

**Scope note.** Sections 1–7 cover the optical rasters. Lidar is here because the height
channel the model actually trains on is derived from it, and because the two facts below
change what heights the project can claim. The one-line CHM row in `CLAUDE.md` stays the
pointer; this is the measured detail behind it.

### 8.1 Two vintages exist, and one of them is era-matched to 2005

Both are public, credential-free, in the same NOAA bucket, same CRS, same tile grid
(`q47122####` quads), so tiles align between eras and one selection routine serves both.

| | **PSLC 2005** | **USGS 2016** |
|---|---|---|
| InPort | [item 50149](https://www.fisheries.noaa.gov/inport/item/50149), dataset 2579 | [item 51853](https://www.fisheries.noaa.gov/inport/item/51853), dataset 6331 |
| bucket prefix | `laz/geoid18/2579/` | `laz/geoid18/6331/` (`north/`, `south/`) |
| collected | 2004-11-11 … 2005-07-15 | 2016-03-17 … 2017-06-06 (Quantum Spatial for USGS/WADNR) |
| whole dataset | 1,444 files / 14 GB (5–17 MB per tile) | 13,205 files / 2.9 TB (50–272 MB per tile) |
| **density, stated** | 2 m spacing ⇒ **0.25 pts/m²** | 0.7 m spacing, **4 pts/m²** |
| **density, cross-checked** | ~2.38 B pts ⇒ **~0.17 pts/m²** | ~457 B pts ⇒ **~5 pts/m²** |
| vertical accuracy | **6.3 cm** fundamental vertical, 95th pct, mixed land covers (Digital Coast) — InPort *separately* states **25 cm avg / 15–25 cm soft-vegetated**. Different metrics: **record both, never average.** Horizontal 60 cm. | **8 cm** NVA |
| classes | **3 only** — Unclassified / Ground / Low Point. **Vegetation is left UNCLASSIFIED.** | **6** — Unclassified 410 B / Ground 39.5 B / Low Point 5.9 B / Water 953 M / Ignored Ground 19.8 M / Bridge Deck 10.8 M |
| format | COPC (`.copc.laz`) — PDAL can bbox-query over HTTP without bulk download | COPC |
| CRS / datum | NAD83(HARN) / UTM 10N; NAVD88 **GEOID18**, metres | same |

> **The governing fact: the density gap is ~16–29×** (0.17–0.25 vs 4–5 pts/m²). Every
> downstream use of the pair is constrained by it, and no comparison between the vintages is
> valid until it is handled — see WORKPLAN §4 Tier 2.

### 8.2 What was acquired (2026-08-22)

Selection: the Edmonds boundary (`City Boundry/Edmonds Boundry.shp` — both misspellings are
load-bearing) reprojected to each tile index's CRS and buffered **600 m**, then every
intersecting tile. The buffer keeps boundary-straddling crowns whole and stops derived
rasters degrading at the edge; at 200 m the selection was 41 + 35 tiles, so the wider margin
cost 12 tiles.

| | tiles | bytes | local plane | data lake |
|---|---|---|---|---|
| PSLC 2005 | 47 | 407.5 MB | `D:\edmonds-pipeline\Imagery\PSLC_2005\` | `Full_Image\PSLC_2005\` |
| USGS 2016 | 41 | 5,907.2 MB | `D:\edmonds-pipeline\Imagery\USGS_2016\` | `Full_Image\USGS_2016\` |

**Landed and verified 2026-08-22:** every file byte-checked against its S3
`Content-Length` on D: (405 laz + helpers; totals matched the Content-Length sum exactly,
no retries), `MANIFEST.sha256` written per directory (the `mirror_sync.py` convention:
54 entries for 2005, 48 for 2016), then copied to the data lake and size-verified there —
408.9 MB / 55 files and 5,986.3 MB / 50 files, both equal to local. Helper/metadata files — tile index `.gpkg`/`.zip`,
`urllist`, `minmax`, ISO metadata `.xml` + `forHumans.html`, and the 67.5 MB
`west_wash_breaklines.zip` — are on **both** planes. Any raster derived from these points
belongs in `Full_Image/Pipeline Imagery/` beside `lidar_snoh_chm.tif`, **not** in these
source directories.

### 8.3 The CHM in use is a degraded convenience product

`lidar_snoh_chm.tif` is **not** county data. The county files are the hillshades
`lidar_snoh_hillshade_fr/be.tif` and the retired `lidar_snoh_structure.tif`. The CHM is
**USGS 3DEP HAG from Planetary Computer**: a ~2 m derived raster, **bilinear-upsampled** to a
1 m EPSG:3857 grid, quantised to **uint8 at 0.2 m/DN**, and **capped at 50.6 m** (CHATLOG
records p99 = 44.6 m; western Washington Douglas-fir exceeds 50 m).

Bilinear upsampling **smooths local maxima**, and a canopy apex *is* a local maximum — so the
raster reads **systematically low**, worst on narrow conical crowns, which is exactly what the
conifer training sites are.

> **Caveat on the caveat.** U6 ("CHM error cannot have made the staircase; it barely dents
> it") injected **random Gaussian** error. Smoothing bias is **systematic and one-directional**,
> so U6 does **not** cover this case. Do not cite U6 as clearing it.

This does **not** reopen the coverage question: `qc/chm_gap_2016.txt` closed that — 83.5% of
the analysis area has CHM, the remainder is open water (99.8% negative NDVI), and counting
every green no-CHM pixel as canopy moves the number by **+0.02 pp**.

### 8.4 What this overturns

The CHATLOG line that **"a lidar-dependent definition cannot be applied pre-2016 (no
coverage)"** is **wrong**: pre-2016 height data exists, at **stand scale**, for the 2005
imagery year. What it cannot do is resolve individual suburban crowns — see the three-way
verdict in WORKPLAN §4 Tier 2.

---

## 9. Provenance of record (added 2026-08-23) — and two corrections to this document

Harvested 2026-08-22/23 by four Opus agents against provider metadata. **Every date below carries
the URL it came from; anything without one was downgraded to unknown by a citation gate (31 dates
were dropped that way).** Full record: `imagery_catalog_2026-08-22.xlsx`, sheets MASTER and
KingCo_SDC_Catalog.

### 9.1 The City of Edmonds "5 cm" is a SERVICE GRID, not a resolution — MEASURED

All four CoE ImageServers report **byte-identical** `pixelSizeX = 0.07620015240030481`. That is
exactly **3 inches applied as WEB MERCATOR units**, which at this latitude is **5.12 cm ground** —
while the flights themselves were **3 inch = 7.62 cm GROUND**.

```
served grid 5.12 cm  vs  native flight 7.62 cm   →  1.4887× oversampled
1.4887 == 1/cos(47.8°)
```

One 0.25 ft grid is stamped across four different flights from two different counties, so the
pixel size proves nothing about any of them. **This is the same units error that produced the
original `gsd_cm` defect (§2.1), this time baked into the city's own service grid.** The held CoE
files genuinely measure 5.0 cm — but that is the grid, not the resolution, which is exactly the
distinction §2.2 already draws for the King years. Treat the four CoE years as **7.62 cm native,
~1.49× oversampled**. `2020_coe_rgb.tif`, the anchor, is natively a 3-inch product.

### 9.2 Acquisition dates and true pixel size — ONE HOME NOW: `qc/imagery_pixelsize_and_date.csv`

**Superseded 2026-08-23.** The per-file date *and* the four pixel-size senses (grid / true ground /
effective / native flight) now live in **`Scripts/qc/imagery_pixelsize_and_date.csv`** (built by
`scratch/imagery_pixelsize_date_build.py`; copied into the catalogue as sheet `Pixel_Size_And_Date`;
evidence under `qc/imagery_date_evidence/`). Every date there carries a fetched URL and a verbatim quote
that was re-fetched and gate-checked; this section keeps only the headline deltas against what this
document said before, so the two never disagree again.

| file | before (this doc) | now (the table) | how |
|---|---|---|---|
| `2017_coe_rgb.tif` | 2017-02-17 → 10-30, INFERRED | **2017-05-04 → 05-10, MEASURED** | it is the *same orthomosaic* as `2017_king_rgb.tif` (r 0.957–0.997 over 66 citywide windows; identical relief displacement) — King's per-frame dates transfer |
| `2000_king_rgb.tif` | "late spring to early fall" | **2000-06-26** (township block T27N R3E/R4E) | King County's flight-date graphic, recovered from the only Wayback capture |
| `2022_coe_rgb.tif` | window INFERRED | window **PUBLISHED**: 2022-04-06 → 07-11 | identity with the county product *measured* (same MrSID encode as Everett's copy, input set 675,609,635,568 B) |
| `2020_coe_rgb.tif` (ANCHOR) | 2020-04-13 → 07-13, INFERRED | **still INFERRED**, head trimmed to 04-25 → 07-13; **consistent with one continuous pass** (10 sites, local times 10:22–13:39 PDT, monotone E→W) — single date NOT proven | shadow solar geometry with the 2012 index as positive control; weather eliminates 22 of 92 days |
| `2016_snoh_rgbi.tif` | "8 of 10 CONFIRMED" | **native 1 ft (30.5 cm)**, served at 0.5 ft; date **2016-08-12 morning (INFERRED, conditional)** — the Aug 11 16:52 sortie is excluded by shadow direction | county mosaic catalog LowPS=1; WA consortium footprints (SDATE is local PDT) |
| `2021_snoh_rgbi.tif` | — | 2021-06-25 → 11-11 PUBLISHED; flown in the **afternoon** | no consortium layer exists for 2021+ (closed) |
| `2002_king_rgb.tif` | — | **NOT FOUND for Edmonds**; product-level 2002-06-11 CONTESTED; delivered grid 0.98 ft ≈ 30.0 cm | archived USGS FGDC; EarthExplorer M2M is the open route |
| `lidar_snoh_chm.tif` | ~2016 | 2016-03-17 → 09-30 (North AOI); grid 1.0 m *Web Mercator* = **67 cm ground** — units trap #4 | InPort 51853 + NOAA tile index |

Still true and still important: the anchor's date is a **window**, the link from the city file to the
county flight is contractual (ILA 2021, `repo=Edmonds` id 1462454), and the definitive pin is a records
request to Snohomish County DoIT for the EagleView flight log / photo-centre index (King County RFP
1166-18-PCR, Piggyback PB-19-14BC) or a CONNECTExplorer capture-date screenshot. Two conflation hazards
are recorded as context rows: a **second 2020 acquisition** over Edmonds (WA consortium, Hexagon, 2020-08-27/28)
and the 2018 consortium/Marsh pair. The odd/even supplier pattern stands: odd years King County, even years
Snohomish County.

### 9.3 The two C-CAP references are DIFFERENT CLASS-SCHEME GENERATIONS — CONFIRMED

`ccap_2016_hires_lc_snohfull.tif` (behind 2000, 2002, 2013, 2015, 2016, **2017**) is a different
generation from the v2 2021 family (behind 2019, 2021k, 2022, 2023, 2024). Three independent
proofs:

1. class 4 *"Developed Impervious under Tree Canopy"* has a count of **exactly zero** across all of
   Snohomish County in the 2016 file's own GDAL histogram — impossible if the class existed;
2. its 256-entry palette is **undefined (0,0,0) at index 4** where v2 has (143,117,130), and
   differs at indices 11 and 25;
3. **two different class-scheme PDFs exist** — a 3-page one (md5 `ce2c38dd10a96e2a1ed3fe8e3dc4a90a`)
   whose class list has no class 4, and the 8-page one shipped in the Refined folder
   (md5 `ce2eaecb55172c900bbd5ff39828e864`).

**So cross-year recall comparisons that span the two reference groups are not merely a coverage
difference — they are two different definitions of canopy.** The existing "2-5 pp for the clip"
caveat (WORKPLAN §1.3) understates the problem. Note also that InPort 53263, the governing record
for the 2016 file, has been **withdrawn** (HTTP 403, "previously available, but has been
withdrawn"), so its source-imagery date may not be publicly recoverable.

**The mechanism is partly our own bug.** `qc/phase4_qc_indep.py:109` maps `"developed": [2, 3, 4]`
with the comment *"High / Medium / Low Intensity Developed"* — which describes the **older 30 m
C-CAP scheme**. In the **v2 hi-res generation class 4 is _believed_ to be "Developed Impervious
under Tree Canopy"**: pixels that ARE under a tree. If so, the scorer charges canopy-over-pavement
as a **false positive** on the v2 reference, while on the 2016 reference the class does not exist
(count 0) and those pixels are not penalised the same way.

**Confidence, stated precisely:** *presence* is MEASURED — class 4 is **480,208 px ≈ 2.40% of
valid** in `ccap_2021_hires_lc.tif` (decimated 4000-row read, so approximate and scoped to that
clip), against count 0 in the 2016 file. The *meaning* is **INFERRED — no RAT for the held clip has
been read.** Confirm it before acting on it; acting on an unverified class meaning is what produced
this defect. Consistent with the observed split — precision .9007 (2016 ref) vs
.8012–.8242 (v2 ref), developed FP-rate .0355 vs .0429–.0607.

Under the adopted **D2 ruling** (mid-height woody counts as canopy) *a tree over pavement is
canopy*, so class 4 belongs in the canopy groups or in `ignore` — **not** in `developed`. That is a
one-line `CCAP_DEFAULT` change plus a local re-score (no GPU). **Until it is decided and re-run,
every v2-scored number is provisional.** Expect **precision to rise**; **recall's direction is not
predicted** — the reference-canopy denominator grows ~2.4 pp while the numerator grows only by the
class-4 pixels the model already calls canopy, so recall may fall. Both outcomes are consistent with
the fix being correct. The file's own safeguard did not catch this because it
verifies which codes are *present*, not what they *mean*.

### 9.4 Corrections to this document

- §1 said `2017_king_rgb.tif` is "on `D:` only". **It is on BOTH planes**, identical byte sizes.
- §1 and IMAGERY_PLAN C1 quote it as "14.93 cm". That is the **uncorrected CRS-unit** figure; the
  true GSD is **10.0 cm** (`data_inventory.csv` true_gsd_m 0.1003). The C1 matched pair is
  **10.0 cm King vs 5.0 cm CoE**, not 14.93 vs 7.46.

---

## 10. Campaign acquisitions (2026-08-23 →) — measured on arrival

Every file below was acquired by `pipeline/acquire_imagery.py` from the manifest
`pipeline/imagery_acquisition_manifest.json`, measured by `qc/imagery_measure.py`, and entered in
`qc/imagery_pixelsize_and_date.csv` (sheet `Pixel_Size_And_Date`). Raw per-chunk ledgers, probe/pilot/
measure/decision JSON live beside each file under `Imagery/<SOURCE>/_acq/<ID>/` on **both** planes.
The replacement test (coverage / bands / effective resolution on a *common* grid / JPEG signature /
provenance / registration) is in `imagery_measure.decide()`; a REPLACE flips `YEAR_CATALOG` and lists the
old file in `qc/phase4_catalog_check.py:SUPERSEDED_FILES` — **the old file is never deleted.**

### 10.1 S16 — `2016_snoh_1ft_rgbi.tif` REPLACES `2016_snoh_rgbi.tif` (batch 1)

| | old (`2016_snoh_rgbi.tif`) | **new (`2016_snoh_1ft_rgbi.tif`)** |
|---|---|---|
| source | county `Aerial_2016` ImageServer, 0.5 ft **server upsample**, bilinear, unsnapped grid (March 2026 tool) | same service, **native 1 ft lattice** (LowPS=1), grid snapped to the service origin, nearest — pilot: nearest = bilinear to 0 differing pixels |
| grid / true GSD | 0.5 ftUS = 15.24 cm | 1.0 ftUS = **30.48 cm** |
| size | 43,893 × 31,965 px, 3.18 GB | **25,116 × 35,259 px, 2,586,179,492 B** (study extent) |
| coverage | 66.7% of the city polygon, 38% of the study extent | **100% of the city polygon**, 82.3% of the study extent (the remaining 17.7% is Puget Sound — 30 of 234 chunks empty in a clean NW staircase) |
| effective resolution (5 sites) | 35.37 cm (2.32× its grid) | 40.56 cm (1.33× its grid). **On a common 30.48 cm grid: 43.2 vs 43.0 cm, HF-energy ratio 1.01** — identical detail; the native-grid rise metric cannot read below ~1 px and flatters interpolated copies |
| bands | 4, NIR real | 4, **NIR real** (std 66, NDVI p90 0.73) |
| JPEG 8×8 signature | absent | absent |
| blue–green registration (phase correlation) | 0.018 px | 0.075 px (both negligible; the catalogue's 0.224 px used a different method) |
| fetch | — | 234 chunks of 2048 px + 64 px overlap, 0 failures, 9.5 min at 5.8 MB/s (4 streams; server ignores `compression=LZ77`; 15000-px strips → HTTP 500) |
| verification | — | each chunk: Content-Length, rasterio decode, band count, transform vs request; stitched BigTIFF spot-verified against 12 chunks; `MANIFEST.sha256` on both planes, sizes equal |
| decision | — | **REPLACE** — wins: coverage, provenance (no server resampling); losses: none |

Date/time evidence is inherited from the superseded row (same flight, same service; INFERRED Aug 12 2016
morning). `YEAR_CATALOG` 2016 now points at the new file (`gsd_cm` 30.5, tier still pinned `coarse`); the
2016 tile cache re-tiles on the next Colab run (`_tile_signature` keys on name + size — intended).
Corrected labels (`canopy_additions_2016.tif`) are reprojected per crop at tiling time and still apply over
the old strip; the newly covered northern third has no corrected labels (plain 2020-mask labels there).

**Method corrections made on this file (recorded so they are not re-derived):** the WGS84-span "true GSD"
(phase4_data_inventory) over-reads rotated Lambert grids by ~2.5% (31.26 vs 30.48 cm) — `imagery_measure`
now converts CRS units exactly and keeps the span figure only as `span_gsd_cm`; and the coverage floor is
judged against the city polygon (≥ 99%) plus ≥ 80% of the study extent, because the extent is ~83% land.
