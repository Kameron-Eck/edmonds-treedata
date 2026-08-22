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

Every file verified against its S3 `Content-Length`; `MANIFEST.sha256` per directory
(the `mirror_sync.py` convention). Helper/metadata files — tile index `.gpkg`/`.zip`,
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
