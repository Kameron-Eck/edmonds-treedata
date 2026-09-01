# STATS CHECKLIST — the GIS pre-flight for any statistic from this pipeline

**Why** (Kam, 2026-09-01): "bulletproof the statistics so we start our analysis right
more often than we get it wrong." This is the specialist's ten-question audit, each
with its measured state in THIS repo and the one-line rule that keeps it honest.
Run down this list before trusting — or publishing — any number. Gated; pointers,
not restated values.

## 1. Units & projection scale — HARDENED
17 of 36 rasters are in US survey feet; 13 are Web Mercator (+48.7% linear here).
Measured per acquisition: `phase4/qc/imagery_geometry.csv`; every statistics-bearing
code site: `docs/CRS_CENSUS.md`. **Rule: lengths/areas via `common._crs_unit_m` or
compute on `config.ANALYSIS_GRID_EPSG`; a "metre" in EPSG:3857 is not a metre.**

## 2. The denominator — MEASURED
A cross-year trend computed over different footprints is not a trend. Per-acquisition
`city_bounds_coverage_pct` lives in the geometry table. **Rule: every percentage
names its denominator (city polygon vs imaged extent vs valid pixels), and every
cross-year statistic uses the COMMON footprint of the years it compares.**

## 3. Valid data vs collar — MEASURED
Only 6 of 36 rasters declare nodata; on the rest, mosaic collar and void read as
data. Per-acquisition `black_px_pct_in_city` (decimated estimate) is in the geometry
table. **Rule: mask by GEOMETRY (the city/AOI polygon), never by trusting nodata;
report valid-pixel fraction beside any full-extent statistic.**

## 4. Co-registration — PARTIALLY MEASURED, protocol OPEN
Change statistics die on shift: one pixel of misregistration at 60 cm turns every
crown edge into "change". Cross-registration spot-checks exist
(`imagery_qc_suite.py::qc_crossreg`; the displacement investigations under
`qc/instruments/`), and the 2019s/2019n pair measured correlation peaking at exactly
zero shift. OPEN: no per-year-pair registration-error table. **Rule: no per-pixel
cross-year comparison without a measured registration bound for that pair; crown- or
block-level aggregation (as `build_validity_intervals.py` does) is the shift-tolerant
default.**

## 5. Support / MAUP — HARDENED for arms
Comparing statistics computed at different support sizes manufactures differences.
`support_matched_rescore.py` proved the pilot's coarse-vs-medium gap survives
1/2/4 m support matching. **Rule: cross-resolution comparisons are support-matched on
the analysis grid, each arm at its own operating point.**

## 6. Spatial autocorrelation in splits — HARDENED
Random splits leak neighboring tiles; the honest machinery exists and is default:
blocked ground splits with metre buffers (`splits.py::make_blocked_val_split`),
LOSO as the only honest site-level split (CLAUDE.md 3.5). **Rule: effective n is
~5 forest sites, not tile counts; random-split numbers are never headlines.**

## 7. Minimum mapping unit — RE-BASELINED (EPOCH 3, Kam 2026-09-01)
`postproc.py::sieve_min_px` now sieves at 3.0 m² TRUE everywhere (residual spread =
integer-pixel quantisation, 3.0–3.999 m², per-acquisition in the geometry table).
**Rule: EPOCH 2 and EPOCH 3 masks are never compared in one trend — the manifest
EPOCH stamp is the guard; masks regenerate per year via `--step postproc`.**

## 8. Area estimation bias — OPEN (the big one)
Pixel-counting a classified map gives MAP area, which is biased whenever omission and
commission errors are asymmetric — and ours are (recall ≠ precision in every live
row). Good practice (the Olofsson-style protocol) is a stratified reference sample,
photo-interpreted, driving an error-adjusted area estimator WITH a confidence
interval. The machinery half-exists: `phase4_accuracy_sample.py` + its review UI —
and the 14,476-crown human review was never finished (`polygons/` carries accept-all
test data; CLAUDE.md gotcha). **Rule: mask-derived areas are labeled MAP AREA;
nothing is published as an area ESTIMATE until it has the adjusted estimator and its
CI. This is the highest-leverage open item for trustworthy statistics.**

## 9. Reference data epoch & definition — DOCUMENTED
Scores are against C-CAP 2021 hi-res with the `forest_wetland` class mapping, one
epoch, its own errors. `docs/SCHEMAS.md` (qc_indep contract) carries the reader
rules. **Rule: reference epoch and class definition ride along with every quoted
score; C-CAP agreement is agreement, not truth.**

## 10. Temporal & seasonal validity — DOCUMENTED
The archive spans February–October; every label descends from an April–July 2020
flight, so leaf-off years carry systematic, species-correlated label error — and
2019s/2019n proved one flight can arrive as two different-looking products.
Dates + evidence: `qc/imagery_pixelsize_and_date.csv`. **Rule: effects smaller than
the measured noise floor are UNDETERMINED, never "no difference"; season is a
confound to name in every cross-year claim.**

---
The measurement contract behind this list: CLAUDE.md 3.4b — instrument → measured
CSV → gated finding. When a question here moves from OPEN to MEASURED, it gets its
instrument and its column, and this page updates in the same commit.
