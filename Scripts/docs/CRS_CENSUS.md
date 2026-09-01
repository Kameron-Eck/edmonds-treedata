# CRS CENSUS — where the pipeline assumes, converts, or chooses a projection

**Why this page exists** (Kam, 2026-09-01): imagery in the wrong projection "can lead
to faulty assumptions that drive stats — this happened quite a bit." Measured, it did:
areas computed in EPSG:2285 US-survey-feet ran 10.76× large; EPSG:3857 areas 2.215×
inflated at this latitude (the 2026-08-27 finding). This page is the census of every
load-bearing site, cited by symbol so `test_citations_resolve` fails it when code
moves. What each file actually carries is measured in `phase4/qc/imagery_geometry.csv`
(regenerate: `qc/instruments/imagery_geometry.py`).

**The archive's measured shape** (2026-09-01, all 36 acquisitions): four CRS families —
EPSG:2285 ×15 and EPSG:2926 ×2 (**US survey foot**, 17 files), EPSG:3857 ×13
(Web Mercator: naive "metre" pixel sizes run **+48.7% linear** vs true ground here),
EPSG:26910 ×6 (UTM 10N — CRS metres ≈ ground metres, 0.0%). Only 6 of 36 rasters
declare nodata. Catalog vs measured: **0 disagreements** — the catalog is honest; the
hazard is unit-blind consumers.

## The one converter

`common.py::_crs_unit_m` — CRS linear unit → metres. Every true-area computation goes
through it. Note its limit: it converts **units**, not projection scale — for EPSG:3857
the unit is "metre" (factor 1.0) while true ground is ~0.672× that here. Ground-true
lengths in 3857 need a warp (see `imagery_geometry.py::measure_one`), not a unit factor.

## Class A — TRUE-METRE computations (correct by construction)

| site | mechanism |
|---|---|
| `postproc.py::step_postproc` | `pixel_area_true = pixel_area * _crs_unit_m(crs)**2`; reported areas only |
| `postproc.py::_append_area_summary` | consumes the true-area figures |
| `build_buildings_layer.py::main` | `area_m2` computed in EPSG:26910 (its own doc table says so) |
| `build_corruption_overlay.py::main` | recomputes crown areas true; prints the measured inflation it is ignoring |
| `build_groves_overlay.py::main` | `_ha_ft2` survey-foot→ha conversion |
| `qc/instruments/support_matched_rescore.py` | ALL arms + reference on one `GRID_CRS` EPSG:26910 grid |

## Class B — CRS-UNIT BY DESIGN (documented, deliberately NOT converted)

- `postproc.py::step_postproc` `min_px` sieve: `MIN_CANOPY_PATCH` was **tuned against
  CRS-unit areas** (config.py, pure-move protected). Converting it would silently change
  every postproc mask — ~10.8× more permissive than "3.0 m²" reads on 2285 years, ~2.2×
  stricter on 3857. Retuning is a science decision, recorded, not a bug.
- Phase-0 crown `area_m2` + `size_class` (222,435 crowns): stored Web-Mercator-inflated
  (median 87.8 stored vs 39.5 true). **Documented-not-changed** (WORKPLAN); consumers
  that care recompute (`build_corruption_overlay.py::main` does, loudly).

## Class C — GRID CHOICES (which CRS governs a comparison)

- **Training/inference/tiling: NATIVE CRS, always** (CLAUDE.md rule 3.7 — no
  upscaling; `tiling.py` and `core.py::step_inference` never warp the year's ortho).
- **Independent scoring** (`qc/phase4_qc_indep.py`): the C-CAP **reference raster's
  grid** governs; the prob raster is warped onto it.
- **Cross-arm rescoring** (`support_matched_rescore.py`): EPSG:26910, declared inline.
- **Sectors** (`make_sectors.py`): bounds defined in EPSG:3857 (the anchor lattice),
  with `land_area_m2_true` fields carrying corrected areas alongside.
- **The analysis grid is now DECLARED**: `config.ANALYSIS_GRID_EPSG` (26910). New
  cross-year statistics use it or native-with-`_crs_unit_m`; nothing resamples the
  archive itself.

## Class D — coordinate lookups (unit-safe by nature)

`transform_bounds`/window reads that convert a POINT or BBOX to find pixels
(`phase4_sentinel_snap.py::read_window`, site evaluation, QC chips): no distance or
area arithmetic crosses the CRS boundary; these carry no unit risk and are not
enumerated per-site.

## Honest remainder

This census enumerates the statistics-bearing sites verified 2026-09-01. Builders not
listed in Class A/B were grepped for area arithmetic and showed none, but were not
line-audited; a new area computation anywhere must route through `_crs_unit_m` or the
analysis grid, and the geometry table's `crs_metric_inflation_pct` column says, per
acquisition, how wrong a naive metre assumption is.
