# IMAGERY ACQUISITION PLAN — 2026-08-22

> ## ⚠ SUPERSEDED — dated record, not a live plan
>
> Superseded by `IMAGERY_FOUNDATION_PLAN_2026-08-22.md`, whose own header said to mark
> this file when the branches met. That never happened, so it kept reading as live.
>
> Its status line below still says "PLAN ONLY. Nothing here has been acquired" — **29
> rasters landed under it.** Read it as what was intended on 2026-08-22; for what the
> campaign actually produced see `IMAGERY_FACTS.md` §9–§13, and for current counts
> `STATUS.md`.

*Kam, 2026-08-22: "I want to go all out. Add additional new imagery; if a better version of an
image I already have is available, I want it; or if there is metadata I want it; or if there is
additional imagery for a year I already have coverage for, I want it."*

**Status: PLAN ONLY.** Nothing here has been acquired. Preliminary analysis below is measured,
not assumed — every claim carries how it was established. Execution is gated per phase.

**Relationship to other docs:** `IMAGERY_FACTS.md` remains the authoritative record of what the
project HAS (one fact, one home) — this plan describes what EXISTS and how to get it, and every
acquisition that lands must be written back into `IMAGERY_FACTS.md`. WORKPLAN §4 Tier 2 gets a
one-line pointer here. This plan does not touch the GPU queues or `phase4seg/`.

---

## 1. Why this is worth doing (and where it is not)

The project's stated bottleneck is **measurement and definition**, not data volume (WORKPLAN §3:
U1 is the only thing blocking Phase 3). New imagery years arrive carrying the same reference
problem the existing 18 have. So the ranking below is deliberately **not** "most pixels first" —
it is ordered by which acquisitions remove an EXISTING constraint versus which add new material
that must then be reconciled.

Three findings drive the order:

1. **The 41.9% ceiling on Snohomish years is self-inflicted** (measured, §3.1). Fixing it removes
   a caveat currently attached to 2016 — the most-cited year in the project, the only NIR year
   with a matched CHM, and the year the corrected labels were built for. Highest value per unit
   of work, and it adds nothing new to reconcile.
2. **NIR-bearing years could go from 4 to ~11** (§3.2). Only NIR years can carry an independent
   NDVI+CHM reference; that reference currently exists at four points in an 18-acquisition series.
3. **County metadata replaces measured guesswork** (§3.4). The project had to MEASURE `gsd_cm`
   because the config was wrong twice over; vendor, acquisition dates and resolution-of-record
   are published and free.

---

## 2. Sources and access paths (all verified 2026-08-22 unless marked)

| source | what it holds | access | quality note |
|---|---|---|---|
| **Snohomish County** `gis.snoco.org/img/rest/services/Imagery` | 23 annual ImageServers, `Aerial_1990` … `Aerial_2024` | `exportImage`, native res, tiled | `Catalog,Image,Metadata`; `ExportTilesAllowed:false`; max **15000×4100 px/request** |
| **King County REST** `gismaps.kingcounty.gov/arcgis/rest/services/BaseMaps` | `KingCo_Aerial_*` 1936–2025 (natural colour only) | `/export` **works** (despite `capabilities` omitting it) | **cached** `singleFusedMapCache`, 24 LODs to level 23, format **MIXED = lossy JPEG**; max **4096×4096 px/request** |
| **King County data catalog** `www5.kingcounty.gov/sdc/?Layer=<NAME>` | the full product list incl. **CIR**, TreeCanopy, LiDAR DGM/DSM, landcover | metadata pages; downloads via [KCGIS Open Data](https://gis-kingcounty.opendata.arcgis.com/pages/download-gis-data) + legacy FTP portal | **preferred for originals** — no double-JPEG |
| **NOAA Digital Coast** `coastalimagery.blob.core.windows.net/digitalcoast/` | NAIP WA 2015 (`6208`), 2017 (`8572`), 2021 (`9586`) | direct file download + `tileindex` + `urllist` + VRT + STAC | 4-band, 1 m, EPSG:26910 — cleanest path of all |

**Provenance rule for this plan:** prefer an original file download over a REST export wherever
both exist. A REST export of a cached MapServer is re-encoded lossy JPEG; the project's existing
King GeoTIFFs came from original downloads. Use export only for products with no download path.

---

## 3. Preliminary analysis (measured 2026-08-22)

### 3.1 The Snohomish 41.9% ceiling is a property of the FILE, not the source — MEASURED

| | extent | contains Edmonds? |
|---|---|---|
| `Aerial_2016` ImageServer | 45 × 55 km (EPSG:2285) | **yes, entirely** |
| project's `2016_snoh_rgbi.tif` | 6.7 × 4.9 km | **no — stops 3.5 km short at the north** |

Probe of the missing northern strip, against a control inside the existing file:

| probe | in-city % | non-black % |
|---|---|---|
| control (file covers it) | 85.3 | 100.0 |
| **missing north-east** | **87.3** | **100.0** |
| missing north-mid | 23.9 | 89.1 |
| missing far-north | 5.6 | 76.8 |

Black pixels track *being outside the city polygon* (Puget Sound / beyond the city), not missing
data. **Conclusion: Snohomish holds full 2016 coverage of Edmonds at 0.5 ft, 4-band.** Same
expected for `2021s`; verify identically before acquiring.

### 3.2 Snohomish annual series — surveyed directly from the REST API

Pixel sizes reported in FEET (EPSG:2285) — the units trap that caused the original `gsd_cm`
defect. All listed years confirmed to contain the Edmonds bbox.

| year | true GSD | bands | | year | true GSD | bands |
|---|---|---|---|---|---|---|
| 1990 | 3.05 m | 1 (pan) | | **2015** | **30.5 cm** | **4 (NIR)** |
| 1996 | 1.0 m | 3 | | **2016** | **15.2 cm** | **4 (NIR)** |
| 2003 | 30.5 cm | 3 | | **2017** | **30.5 cm** | **4 (NIR)** |
| 2007 | 30.5 cm | 3 | | **2019** | **30.5 cm** | **4 (NIR)** |
| 2009 | 30.5 cm | 3 | | 2020 | **7.6 cm** | 3 |
| 2011 | 30.5 cm | 3 | | **2021** | **15.2 cm** | **4 (NIR)** |
| 2013 | 1.0 m | 3 | | 2022, 2024 | untested | untested |

1993 / 2000 / 2005 did not parse — naming variants; re-check during Phase 1.

### 3.3 NIR inventory — the strategic prize

Held today: **2016, 2019n, 2021s, 2022n** (two of them 60 cm NAIP).

| source | NIR/CIR years available | native GSD |
|---|---|---|
| King County CIR | 2000, 2009, **2010**, 2015, **2023**, 2025 | 2010 & 2023 at 3–6 in |
| Snohomish 4-band | 2015, 2016, 2017, 2019, 2021 | 15–30 cm |
| NAIP | 2015, 2017, 2021 | 1 m |

Union ≈ **11 NIR-bearing years** against today's 4.

### 3.4 King County metadata resolves two standing orphans

`KingCo_Aerial_2017` service description (verbatim): *"Natural-color aerial imagery mosaic of
King County and southwestern Snohomish County, captured by **Pictometry International Corp.**
from **February through October 2017**"*, 3 in/px over urbanized western King County **and
southwestern Snohomish County**. That is vendor + acquisition window + resolution-of-record for a
file the project currently holds with none of it — and it confirms King flights DO cover Edmonds.

Orphans this closes: `2012_king_rgb.tif` (on Drive, uncatalogued, never assessed) and
`2017_king_rgb.tif` (D:-only, a second 2017 acquisition).

### 3.5 King export — corrected finding

An earlier read of this plan's author claimed the export "plateaus around 20 cm." **That was
wrong and is retracted.** A controlled test (312 m box, 4096 px request vs 1024 px upsampled to
the same grid) gives **2.16× the high-frequency energy** for the native request — real detail
below 30 cm. The cache carries LODs to level 21 ≈ **5.0 cm ground** at this latitude. The
laplacian-falloff proxy used earlier was measuring JPEG smoothing, not a resolution ceiling.

**Standing caveat:** the cache format is MIXED (lossy JPEG). Export is a legitimate path for
products with no download, but originals are preferred (§2 provenance rule).

### 3.6 The county-line gate — RESOLVED 2026-08-22, by going around it

**The original question:** King's *derived* products (`TreeCanopy2016/2017/2021`,
`TreeCanopy2021Height`, `TreeCanopy2021 TreePoints`, `ForestCover2019Ecopia`,
`Landcover2019Ecopia`, `VegetationFeatureHeights*`, the annual LiDAR DGM/DSM series) are scoped
"Western King County". Edmonds is in **Snohomish County**, its southern boundary (47.7777 N)
essentially on the King line — so those products probably stop ~0.1 km short. King *imagery*
demonstrably spills north (§3.4); derived products likely do not. **That specific question remains
untested** and is now low priority, because a better instrument exists that has no county problem
at all.

**The bypass — a statewide equivalent, MEASURED to cover Edmonds:**

`Land Cover Statewide Ecopia Data 2021-2022, 3 ft raster`
- service: `https://imagery-public.watech.wa.gov/arcgis/rest/services/LandCover/Statewide_Ecopia_LandCover_2021_2022_3ft_1band_wsps_83h_rstr/ImageServer`
- hub item: `fc19471352fb4a6195715cf5a7f40a0a` (owner `WAGeoservices`), created 2023-10-25, modified 2025-02-13
- extent 598091–2570050 × 81835–1376956 in **EPSG:2927** (NAD83 HARN WA State Plane South, feet);
  Edmonds bbox 1173981–1193579 × 896660–926579 → **COVERS EDMONDS: verified**
- pixel 3.28 ft = **1.0 m**; 1 band, U8 class codes; **7 land-cover categories**, Ecopia
  proprietary extraction from 2021–2022 high-resolution statewide imagery
- capabilities `Catalog, Mensuration, Download, Image, Metadata` — **Download IS permitted**
  (`maxDownloadSizeLimit` 2048 MB, `maxDownloadImageCount` 20); `exportTilesAllowed` false;
  max 15000×4100 px per `exportImage`
- raster functions render it with **C-CAP class names and colour scheme** — an independent
  extraction presented in a familiar label scheme
- item snippet: *"DO NOT DOWNLOAD HERE. \"View Full Details\" for download info."* — resolve the
  real download route in Phase 1.

**Why this matters more than the King derived products would have.** The project's
`ccap_2021_hires_lc.tif` is the **clipped 53.1%** copy; that is precisely why 2021k (.6059) and
2023 (.6510) carry the "T3 footing, understated 2–5 pp" caveat — and the pending queue scores for
**2024, 2019 and 2022** are all slated against the same clipped reference. A full-coverage 1 m
2021-era land cover removes the coverage limitation.

**But state it correctly:** adopting Ecopia as a scoring reference is a **re-baseline, not a
patch.** WORKPLAN §1.3 already made this ruling about the other candidate
(`wa_2021_ccap_v2_hires_canopy.tif`, 1.14 m): a different product means a different canopy
definition, so numbers scored against it are not comparable to the existing C-CAP series. Ecopia
is a second such candidate and inherits the same rule. Its highest-confidence uses are therefore:
1. **A third independent instrument** for the reference-disagreement problem (the two current
   references disagree on 15–17% of pixels with no tiebreaker; the project's Foody-2022 latent-class
   work explicitly needs independent instruments, and this one shares no method with C-CAP or the
   NDVI+CHM reference).
2. **A full-coverage 2021-epoch reference** for the T3 years — as a declared re-baseline, reported
   alongside the clipped-C-CAP numbers, never silently substituted for them.

**Also on that server** (`imagery-public.watech.wa.gov`, folders `County`, `ImageServices`,
`LandCover`, `Municipality`, `NAIP`, `Regional`, `Utilities`, `WSDOT`): `County` holds 17
ImageServers including `SnohomishCo_2002_1ft_color` and `SnohomishCo_2007_1ft_color` — duplicates
of what Snohomish's own server serves, so low value. `LandCover` holds only the Ecopia service.
`ImageServices` is empty. `NAIP`, `Municipality` and `Regional` are unexplored (Phase 1).

### 3.6b Where the metadata lives — the map

| source | metadata endpoint | contents | format |
|---|---|---|---|
| **King County products** (the catalog file names: `Ortho*`, `TreeCanopy*`, `LiDAR*`, `Landcover*`) | `https://www5.kingcounty.gov/sdc/?Layer=<NAME>` | vendor, acquisition dates, native GSD, projection, accuracy, licence | HTML page per layer |
| **King County REST** | `.../BaseMaps/<service>/MapServer?f=json` | `serviceDescription` (vendor + window + res-by-zone), `tileInfo.lods` (exact cache resolutions), extents | JSON |
| **Snohomish County REST** | `https://gis.snoco.org/img/rest/services/Imagery/Aerial_<YYYY>/ImageServer?f=json` | extent, `pixelSizeX/Y` (**FEET**), `bandCount`, `pixelType`, capabilities | JSON — sparse; **no vendor or acquisition date** |
| **WA statewide public imagery** | `https://imagery-public.watech.wa.gov/arcgis/rest/services/<folder>/<svc>/ImageServer?f=json` | extent, pixel size, bands, capabilities, raster functions | JSON |
| **WA Geoservices hub** | `https://geo.wa.gov/datasets/<slug>` → item API `https://www.arcgis.com/sharing/rest/content/items/<id>?f=json` | title, description, tags, extent, **licenseInfo**, `accessInformation`, service `url`, created/modified | JSON — **best licence source** |
| **NAIP (NOAA Digital Coast)** | `<blob prefix>/<dataset>_met.xml`, `metadata_*forHumans.html`, `stac/catalog.json` | full FGDC lineage, dates, accuracy, class/band detail | FGDC XML + HTML + STAC JSON |
| **Lidar (PSLC 2005 / USGS 2016)** | NOAA InPort item pages (50149 / 51853) + `metadata_*.xml` in the S3 prefix | collection dates, density, accuracy, classes, lineage, constraints | HTML + FGDC XML |

**Gaps this map exposes:** Snohomish's REST metadata carries **no vendor and no acquisition
date** — the two fields most needed to interpret a year. Phase 1 must find Snohomish's own
metadata portal or contact the county; do not infer dates from the service name.

### 3.7 What this does NOT overturn

WORKPLAN §2 withdrew *"the 2021 pair isolates the sensor effect"* because resolution → tier →
tiling params entangle by design. After true-GSD correction no clean **same-tier same-year** pair
emerges from the new inventory: Snohomish's 30.5 cm years sit just above the 29.9 cm medium
boundary, 2021 pairs 10 cm (fine) against 15.2 cm, and `2021s` is *pinned* coarse from the
pre-correction era. **The withdrawal stands.** Do not resurrect it on the strength of this plan.

A different and better prize is available instead: Snohomish 2015→2021 is presumably **one
contractor lineage**, giving a self-consistent multi-year 4-band series — worth more than a
sensor control, because cross-contractor drift is exactly what destroyed GRVI comparability
(.80 → .11 from processing alone).

---

## 4. Phases

Each phase is separately gated. Do not begin a phase before its predecessor's outputs are
recorded.

### Phase 0 — Master cross-reference (no downloads, no pixels)

Build `phase4/qc/imagery_crossref.csv` (measured text; harvested into the repo), one row per
(year, source, product):

`year · source · product_name · native_gsd_cm · bands · crs · edmonds_coverage · held_now ·
held_file · held_gsd_cm · better_than_held · access_path · download_url · metadata_url · notes`

Inputs: the King catalog names (§2), the 23 Snohomish services, the three NAIP datasets, and
`IMAGERY_FACTS.md` + `YEAR_CATALOG` for what is held. **This table is the anti-double-download
instrument** — nothing gets acquired that is not a row here with `better_than_held` or
`held_now = no`.

### Phase 1 — Metadata harvest (cheap, no pixels, highest value per byte)

- King: fetch `https://www5.kingcounty.gov/sdc/?Layer=<NAME>` for every `Ortho*` (natural **and**
  CIR), plus the TreeCanopy / LiDAR / landcover products of interest. Record vendor, acquisition
  dates, native GSD, projection, accuracy, licence.
- Snohomish: `?f=json` for all 23 services — extent, pixelSize, bandCount; plus any published
  metadata page.
- NAIP: the `*_met.xml` files already identified.
- **Deliverable:** populate Phase 0's table; write vendor/date/GSD-of-record into
  `IMAGERY_FACTS.md`, explicitly resolving `2012_king_rgb.tif` and `2017_king_rgb.tif`.
- **Record licensing verbatim for every source.** "Viewable in a county app" and "redistributable
  in a pipeline" are not the same thing.

### Phase 2 — Coverage gates (cheap probes, no bulk downloads)

For every candidate product, establish Edmonds coverage *empirically*, not from a bounding box:
- rasters: small `exportImage`/`export` probe over in-city and out-of-city windows, compare
  non-nodata fraction against the city polygon (the method used in §3.1 — it works);
- vectors/derived: query the service extent AND fetch one feature over Edmonds.
- **Settle §3.6 first** — it decides whether the King derived-product family is in scope at all.

### Phase 3 — Acquisition, in this order

**Tier A — removes an existing constraint (do first)**
1. Full-extent Snohomish **2016** (0.5 ft, 4-band) — replaces the clipped `2016_snoh_rgbi.tif`.
2. Full-extent Snohomish **2021s**, same treatment (verify the clip first, §3.1 method).

3. **Statewide Ecopia land cover 2021-2022** (1 m, covers Edmonds, Download permitted) — a
   THIRD independent reference and a full-coverage 2021-epoch alternative to the clipped
   `ccap_2021_hires_lc.tif`. Acquire the Edmonds clip; treat any score against it as a declared
   **re-baseline** reported alongside the existing C-CAP numbers (§3.6), never a silent swap.

**Tier B — NIR expansion (attacks the reference problem)**
4. NAIP **2015, 2017, 2021** — cleanest downloads, tileindex-driven, ~200–700 MB/yr.
5. Snohomish **2015, 2017, 2019** (30.5 cm, 4-band) — double NAIP's resolution.
6. King CIR **2010, 2023** (3–6 in) — finest NIR available anywhere in this inventory; then
   `Ortho2000DAISCIR` / `Ortho2000EmergeCIR` / `Ortho2009AerialsExpressCIR` / `Ortho2015CITYCIR`.

**Tier C — years not held at all**
7. King **2025**, Snohomish **1990/1996/2003/2011/2013/2020/2022/2024**, and any 1993/2000/2005
   services that resolve in Phase 1.

**Tier D — better versions of years already held**
8. Only where Phase 0 marks `better_than_held = yes` on *measured* native GSD, and only from an
   original-download path (§2 provenance rule). **Never overwrite** — new filename, new catalog
   entry, and `IMAGERY_FACTS.md` records both.

**Tier E — second acquisitions of years already covered**
9. Same-year alternates (e.g. Snohomish 2020 at 7.6 cm alongside `2020_coe_rgb.tif`; King vs
   Snohomish for any shared year). Value is cross-source comparison, **not** the sensor control
   (§3.7). Catalogue them as distinct acquisitions with distinct labels.

### Phase 4 — Integration

- `IMAGERY_FACTS.md`: every acquisition, measured GSD (measure — do not trust the metadata),
  bands, coverage %, provenance, licence.
- `phase4seg/config.py YEAR_CATALOG`: new entries **only** after `qc/phase4_catalog_check.py`
  passes 18/18 → N/N. Remember `config.py` is pure-move protected and feeds `_tile_signature`;
  adding catalog entries is fine, changing constants is not.
- `qc/phase4_data_inventory.py`: extend to cover the new sources.
- CHATLOG entry per acquisition batch; `run_registry.csv` is for Colab runs and is NOT used here.

---

## 5. Storage, gates and limits

- **Drive free: 52.1 GB** (measured 2026-08-22); tonight's GPU output will consume ~20 GB.
  **D: free: 364.8 GB.**
- **Local-then-copy (CLAUDE.md rule 3):** download to `D:\edmonds-pipeline\Imagery\<SOURCE>\`
  first, verify sizes/sha256, write `MANIFEST.sha256`, then copy to
  `G:\My Drive\treedata\Full_Image\<SOURCE>\` (the convention KingCo / USGS / WA_NAIP /
  USDA_NRCS already follow). Working rasters the pipeline reads go to
  `Full_Image\Pipeline Imagery\`.
- **SIZE GATE:** stop and ask Kam before any single batch exceeding **10 GB**, or whenever
  projected Drive free would fall below **25 GB**.
- **Re-downloadable-source precedent:** `impervious.tif` (1.48 GB statewide) was deleted from
  Drive, keeping only the Edmonds clip. Prefer boundary-clipped acquisitions; do not mirror
  statewide products.
- **Request limits:** Snohomish 15000×4100 px/request; King 4096×4096. Both need a tiling +
  stitching helper with overlap handling and per-tile verification. Full-extent Edmonds at
  0.5 ft ≈ 2.35 Gpx ⇒ ~5–6 GB per year; 30.5 cm years ≈ 1.5 GB.

---

## 6. Risks

- **Double-download.** Mitigated by Phase 0's cross-reference being a hard precondition.
- **Silent quality downgrade.** A cached-JPEG export can be *worse* than a file already held
  (the project's `2017_king_rgb.tif` at 10.0 cm true is finer than a casual export). Tier D is
  gated on measured native GSD, not on a service's advertised resolution.
- **Units trap.** Snohomish pixel sizes are FEET (EPSG:2285); King/CoE are Web Mercator (×1.49
  inflation). This is the exact defect that produced the original `gsd_cm` error — every GSD in
  this plan must be re-measured from the delivered file, never copied from a service field.
- **Scope.** This plan is large and none of it is on the critical path to U1. It is Tier-2 work
  and must not displace the canopy definition or the GPU series.
- **Licensing.** Unrecorded until Phase 1. No redistribution assumption until it is.
