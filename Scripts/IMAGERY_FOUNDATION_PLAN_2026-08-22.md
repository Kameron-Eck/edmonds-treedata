# IMAGERY FOUNDATION PLAN — 2026-08-22

*Kam, 2026-08-22: "I need a work plan for updating the imagery. The goal is to settle the
foundation of imagery for this project... Before going about downloading imagery, I want to make
sure we have metadata on as much of it as possible. It's important to be thorough here."*

**This supersedes `IMAGERY_ACQUISITION_PLAN_2026-08-22.md`** (which lives on
`work/p11-5-autonomy`; mark it superseded when the branches meet — one fact, one home). The earlier
draft was acquisition-ordered. This one is **foundation-ordered**: correct what is false, document
what is held, verify it, repair it, and only then consider new pixels.

**Status: PLAN. Nothing downloaded under it yet.** The lidar acquisition that landed on
`work/p11-5-autonomy` (2005 PSLC 47 tiles / 407.5 MB, 2016 USGS 41 tiles / 5.9 GB, sha256-verified
on both planes) was executed under the earlier draft and stands.

**Companion instrument:** `Scripts/imagery_catalog_2026-08-22.xlsx` — 13 sheets, 220 products,
every row evidence-tagged MEASURED / PUBLISHED / UNVERIFIED. The catalogue is the working
inventory; `IMAGERY_FACTS.md` remains the authoritative home for facts about files we HOLD.

---

## 0. What "settled" means — the exit criteria

The foundation is settled when **all five** are true. Without testable criteria, "thorough" never
terminates.

1. **Provenance of record for every held file.** Each of the 27 held items (22 imagery + 4
   reference + 1 CHM) has: flight date or window, vendor, sensor/platform, GSD-of-record, band
   definition, CRS, licence, and a working metadata link — **or** an explicit
   `NOT FOUND — escalated <date> to <who>` entry. A recorded dead end is a pass; a blank is not.
2. **Measured properties agree with that record.** Every held raster's measured GSD, band count,
   CRS and footprint checked against its provenance *and* against `YEAR_CATALOG`, with
   disagreements resolved or written down.
3. **No known-false statement survives** in `IMAGERY_FACTS.md`, `CHATLOG.md`, `IMAGERY_PLAN.md`
   or `YEAR_CATALOG` (several exist today — Phase 0).
4. **The four repair/replace cases are dispositioned** — done, scheduled, or explicitly declined
   with a reason.
5. **Catalogue, `IMAGERY_FACTS.md` and `YEAR_CATALOG` agree**, and `qc/phase4_catalog_check.py`
   passes at N/N.

**Explicitly NOT required to call the foundation settled:** any new acquisition year, the NIR
expansion, or the gap years. Those are Phase 5 and deliberately out of scope.

---

## 1. Where the foundation stands today — MEASURED 2026-08-22

**Held: 27 items.** Metadata completeness, measured from the catalogue:

| gap | count | which |
|---|---|---|
| **No acquisition date** | **8** | all four **City of Edmonds** years (2017, 2020, 2022, 2024), 1998, 2019n, 2022n, C-CAP refs |
| **No metadata link** | **9** | the four CoE years, both NAIP, all three C-CAP refs |
| **Known defect** | **10** | see the catalogue's `DataLake_Issues` sheet |

**The worst gap is the City of Edmonds.** Four files, 25–48 GB each, ~5 cm — including
`2020_coe_rgb.tif`, **the project's only hand-labelled year** — have no flight date, no vendor and
no metadata link. *Every label in this project is anchored to an image whose acquisition date we
do not know.* That is the highest-value missing fact in the project.

**Second: Snohomish.** Their REST services publish extent, pixel size and band count but **no
vendor and no acquisition date** for any year.

**Verified clean — do not re-litigate:** all 32 catalogued rasters match `YEAR_CATALOG` on
`gsd_cm`, `bands` and `crs_epsg` with **zero mismatches**; every catalog entry's file exists; every
file present on both planes is byte-identical in size. The 2026-08-18 GSD correction is confirmed
against actual pixels.

---

## 2. Phases

Each phase is separately gated. **Phases 0–2 involve no downloads at all.**

### Phase 0 — Correct what is already false (no downloads; do FIRST)

These are known falsehoods sitting in the documents future sessions read. They must not survive
into an acquisition round, because acquisition decisions get made from them.

| # | correction | evidence | risk |
|---|---|---|---|
| 0.1 | `2022_naip_rgbi.tif` **is NAIP 2023-10-07**, not 2022 | bands 1–3 byte-identical to `rgb_2023.tif`, band 4 to `ir_2023.tif`, on 3 independent windows; `Optimal_Scenes.xlsx` lists no 2021/2022 NAIP over Edmonds | **docs safe now; the RENAME is not** |
| 0.2 | `2017_king_rgb.tif` is on **both** planes (not "D: only"); its "14.93 cm" is the **uncorrected** CRS-unit figure — true GSD **10.0 cm** | identical byte sizes both planes; `data_inventory.csv` true_gsd_m 0.1003 | doc-only |
| 0.3 | The 2000 King imagery **omits the blue band** — blue is synthesised | King SDC, verbatim: *"a natural color derivative rather than a true natural color product as the original data is limited to 3-bands only, omitting the blue band"* | doc-only |
| 0.4 | `lidar_snoh_chm.tif` is **not county data** — USGS 3DEP HAG via Planetary Computer, bilinear-upsampled 2 m→1 m, uint8 0.2 m/DN, capped at 50.6 m | `fetch_build_chm.py`; measured grid | doc-only |
| 0.5 | `2021_snoh_rgbi.tif` is **clipped** — 53.4% of the Edmonds bbox, identical grid to the known-clipped 2016 | measured 2026-08-22 | doc-only |
| 0.6 | King derived products (`TreeCanopy*`, `VegetationFeatureHeights*`, DGM/DSM) are **King-County-only and Not Public** — they do not reach Edmonds | SDC page fetched: extent *"Washington, King County"*, access *"Not Public"* | doc-only |

**Split the work by risk.** 0.2–0.6 are documentation edits, safe immediately. **0.1's rename is
not:** the `2022n` label is wired into `YEAR_CATALOG`, into `qc_indep_report.csv` rows, and into
the other session's live harvest machinery. **Correct the record now; defer the rename to a
coordinated window with no queue running**, then do it as a single atomic change across catalog +
filename + scored rows.

Consequences of 0.1, to record alongside it: the scored year `2022n` (.6564 / .8630) carries a
wrong label; the "2022 CoE vs 2022n NAIP same-year natural experiment" is actually **cross-year**;
and "NAIP is leaf-on by specification" is weakened, because **both** WA NAIP flights over Edmonds
are **October** (2019-10-11, 2023-10-07).

### Phase 1 — Metadata completion (no downloads; the bulk of the work)

**Acceptance bar per held file:** flight date/window · vendor · sensor · GSD-of-record · band
definition · CRS · accuracy · licence · working metadata URL. Anything unobtainable is recorded as
`NOT FOUND — escalated <date> to <who>`, never left blank.

**Pass 1 — web harvest** (running as this plan is written). Four agents against the measured gaps:
City of Edmonds years, Snohomish vendor/dates, NAIP + C-CAP lineage, King flight dates. Every date
must carry the URL fetched and the verbatim sentence supporting it.

**Pass 2 — escalate to the providers.** Web harvesting will probably fail on the CoE flight dates
and Snohomish vendor/dates, because neither publishes them. That is normal — unpublished flight
metadata is obtained by *asking*. Kam to contact:

- **City of Edmonds GIS** — flight dates, vendor and sensor for the 2015/2017/2020/2022/2024
  orthos and the 2018 marsh imagery. *The 2020 date is the single most valuable fact.* Ask also
  whether a **4-band (NIR)** version exists — the public service is RGB + alpha, so a real NIR
  original may exist unpublished. If it does, it would give the anchor year an NDVI reference.
- **Snohomish County GIS** — vendor and flight dates for the annual series, and whether their
  imagery comes through a regional consortium (which would document both counties at once).
- **King County GIS Center** (`giscenter@kingcounty.gov`) — the CIR products are marked *not yet
  available in ArcGIS Online*; ask access terms and per-frame flight dates.

**Pass 3 — mine what is already on disk (do this first; it costs nothing).**
`Full_Image/USGS/Edmonds_Optimal_Scenes.xlsx` carries per-scene `Acquisition_Date` for 406
USGS-sourced scenes 1941–2023 and already answers the NAIP years.

**Deliverable:** every held file's catalogue row filled or explicitly escalated;
`IMAGERY_FACTS.md` updated as the authoritative home. **Leave the citation gate in
`build_master_catalog.py` ON** — it downgraded 31 uncited dates this round; that behaviour is
correct and must never be relaxed to make the sheet look fuller.

### Phase 2 — Verify held files against the arriving provenance (no downloads)

Cheap, local, and what makes the foundation *verified* rather than merely *documented*.

1. Re-run the raster audit (already scripted) and diff against the Phase-1 provenance, not just
   against `YEAR_CATALOG`.
2. Resolve the two orphans with their new metadata — `2012_king_rgb.tif` and `2017_king_rgb.tif`:
   catalogue them or record why not. Confirm each King acquisition actually covered Edmonds (the
   descriptions say *"King County and southwestern Snohomish County"*).
3. Re-measure any file whose provenance contradicts the catalog. **Provenance is a claim; the
   pixels are the evidence.** `IMAGERY_FACTS.md` records the measurement.
4. Run `qc/phase4_catalog_check.py`; it must pass at N/N.

### Phase 3 — Repair and replace (the first downloads; four cases only)

| # | replace | with | gate |
|---|---|---|---|
| 3.1 | `2016_snoh_rgbi.tif` (53.4%) | Snohomish `Aerial_2016` full extent, 15.2 cm 4-band | none — measured and ready |
| 3.2 | `2021_snoh_rgbi.tif` (53.4%) | Snohomish `Aerial_2021` full extent | none — clip confirmed |
| 3.3 | `2015_king_rgb.tif` (10.0 cm) | CoE `2015_Aerial_Cached` (5.1 cm) | is the CoE 2015 a **different flight** or a finer copy of the same? Phase 1 answers |
| 3.4 | `ccap_2021_hires_lc.tif` (2.8 MB clip) | `wa_puget_2021_ccap_v2_hires_landcover.tif` (1,433 MB) | **LINEAGE** — same v2 product ⇒ a **patch**; different product/version ⇒ a **re-baseline** |

Gate 3.4 is the consequential one: it decides whether five scored years (2021k .6059, 2023 .6510,
2024 .6170, 2019 .6346, 2022 .6818) can simply be corrected onto full-coverage footing, or whether
doing so is a definitional change that breaks comparability with the existing series.

**Standing rules for all four:** never overwrite a held file — new filename, new catalog entry,
`IMAGERY_FACTS.md` records both. Prefer an original download over a cached REST export (King's
cache is lossy MIXED JPEG). Re-**measure** every delivered file's GSD; never copy a service's
advertised number. **Confirm King licensing before any King product is downloaded** — SDC records
are `IsPublic=false` and state *"Any sale of this map or information on this map is prohibited
except by written permission of King County."*

**Mechanics:** Snohomish and CoE serve via `exportImage` (max 15000×4100 per request, no Download
capability), so 3.1–3.3 need a tiling + stitching helper with overlap handling and per-tile
verification. Full-extent Edmonds at 0.5 ft ≈ 2.35 Gpx ⇒ ~5–6 GB per year.

### Phase 4 — Reconcile and close

`IMAGERY_FACTS.md` updated for every landed file (measured, not claimed) · new `YEAR_CATALOG`
entries only after `phase4_catalog_check.py` passes · catalogue rebuilt **through
`build_master_catalog.py`**, never hand-edited · a CHATLOG entry per phase · re-verify the §0 exit
criteria and either declare the foundation settled or name exactly what still blocks it.

### Phase 5 — OUT OF SCOPE for this plan

New acquisitions — the NIR expansion (4 → ~11 NIR-bearing years), the gap years (2003, 2010, 2011,
2018, 2025), second acquisitions of held years, and the statewide Ecopia third reference — are
**not** part of settling the foundation and must not be attached to it. They are the next plan. The
foundation must be able to finish without them. What is known about them already lives in the
catalogue's MASTER sheet; it is not restated here.

---

## 3. Decisions needed from Kam

1. **Phase 7 / the 1 TB question.** `Full_Image/Pipeline Imagery/upsample/` is **1,009 GB** — the
   largest object in the data lake. Its only consumer (phase-1 spectral extraction) is complete
   (`edmonds_crowns_phase1.parquet` postdates every input file); CLAUDE.md scopes it to
   phase1/phase7; phase 7 was never built. Fully regenerable (~20–25 h Colab) but **Drive is the
   only copy**, and `phase1c_review.py:90` still hardcodes a path into it. **If phase 7 is as dead
   as phases 5 and 6, deleting this frees ~1 TB and changes every storage gate in this plan.**
   Not actioned.
2. **Provider contacts** (Phase 1 pass 2) — the CoE flight dates in particular are unlikely to be
   obtainable any other way.
3. **The `2022n` rename window** (Phase 0.1) — needs a moment with no queue running.

---

## 4. Storage and gates

- **Drive free: 52.1 GB** (measured 2026-08-22); **D: free: 364.8 GB**. Phase 3 in full needs
  ~15–20 GB. Decision 1 would change this entirely.
- **Local-then-copy (CLAUDE.md rule 3):** download to `D:\edmonds-pipeline\Imagery\<SOURCE>\`,
  verify sizes + sha256, write `MANIFEST.sha256`, then copy to
  `G:\My Drive\treedata\Full_Image\<SOURCE>\`. Working rasters live in
  `Full_Image\Pipeline Imagery\`.
- **SIZE GATE:** stop and ask before any batch over 10 GB, or if projected Drive free would fall
  below 25 GB.
- **Units trap:** Snohomish pixel sizes are **US survey feet** (EPSG:2285); King/CoE are Web
  Mercator (×1.49 inflation at this latitude). This is the exact defect that produced the original
  `gsd_cm` error. Re-measure every delivered file.

---

## 5. Risks

- **The metadata may not exist publicly** for the CoE and Snohomish flights. Mitigation: the
  escalation path, with `NOT FOUND — escalated` as an acceptable terminal state. An unobtainable
  date must not block Phases 2–3.
- **Silent quality downgrade.** A cached-JPEG export can be *worse* than a file already held
  (`2017_king_rgb.tif` at 10.0 cm true is finer than a casual King export). Every replacement is
  gated on **measured** native GSD.
- **Two sessions, one working tree.** This plan lands on `fix/20260822-inference-throughput`; the
  earlier draft and catalogue v1 are on `work/p11-5-autonomy` (branches diverged at `f8949f6f`).
  Stage explicit paths, never `-A`; do not switch branches while the other session is live.
- **Scope creep.** Phase 5 is where new pixels live. Folding the NIR expansion into foundation work
  is the main way this plan fails to terminate.

---
## 6. Evidence appendix — measured 2026-08-22 (carried from the earlier draft)

### 6.1 Sources and access paths (all verified 2026-08-22 unless marked)

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

### 6.2 Preliminary analysis (measured 2026-08-22)

#### 6.2.1 The Snohomish 41.9% ceiling is a property of the FILE, not the source — MEASURED

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

#### 6.2.2 Snohomish annual series — surveyed directly from the REST API

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

#### 6.2.3 NIR inventory — the strategic prize

Held today: **2016, 2019n, 2021s, 2022n** (two of them 60 cm NAIP).

| source | NIR/CIR years available | native GSD |
|---|---|---|
| King County CIR | 2000, 2009, **2010**, 2015, **2023**, 2025 | 2010 & 2023 at 3–6 in |
| Snohomish 4-band | 2015, 2016, 2017, 2019, 2021 | 15–30 cm |
| NAIP | 2015, 2017, 2021 | 1 m |

Union ≈ **11 NIR-bearing years** against today's 4.

#### 6.2.4 King County metadata resolves two standing orphans

`KingCo_Aerial_2017` service description (verbatim): *"Natural-color aerial imagery mosaic of
King County and southwestern Snohomish County, captured by **Pictometry International Corp.**
from **February through October 2017**"*, 3 in/px over urbanized western King County **and
southwestern Snohomish County**. That is vendor + acquisition window + resolution-of-record for a
file the project currently holds with none of it — and it confirms King flights DO cover Edmonds.

Orphans this closes: `2012_king_rgb.tif` (on Drive, uncatalogued, never assessed) and
`2017_king_rgb.tif` (D:-only, a second 2017 acquisition).

#### 6.2.5 King export — corrected finding

An earlier read of this plan's author claimed the export "plateaus around 20 cm." **That was
wrong and is retracted.** A controlled test (312 m box, 4096 px request vs 1024 px upsampled to
the same grid) gives **2.16× the high-frequency energy** for the native request — real detail
below 30 cm. The cache carries LODs to level 21 ≈ **5.0 cm ground** at this latitude. The
laplacian-falloff proxy used earlier was measuring JPEG smoothing, not a resolution ceiling.

**Standing caveat:** the cache format is MIXED (lossy JPEG). Export is a legitimate path for
products with no download, but originals are preferred (§2 provenance rule).

#### 6.2.6 The county-line gate — RESOLVED 2026-08-22, by going around it

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

#### 6.2.6b Where the metadata lives — the map

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

#### 6.2.7 What this does NOT overturn

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

