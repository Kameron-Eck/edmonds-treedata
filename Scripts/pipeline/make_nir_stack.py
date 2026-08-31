#!/usr/bin/env python3
"""
  NIR MEGA-STACK — every 4th band of every 4-band acquisition, one aligned raster
  ---------------------------------------------------------------------------

WHY
    Ten of the held acquisitions carry a real near-infrared band. NIR is the
    single cheapest "is this actually live vegetation?" signal we own, and it is
    the ONLY model-independent one (qc/phase4_qc_ndvi.py builds its independent
    canopy reference from exactly this band). Scattered across ten files in four
    CRSs at five ground resolutions it is unusable as a *looking* tool.

    This script pulls every NIR band onto ONE grid, one band per acquisition, in
    chronological order, so you can flicker through them in ArcGIS as a
    vegetation-confidence focus tool: bright = vegetation, and a pixel bright in
    2015 and dark in 2023 is a candidate loss.

WHAT IT WRITES
    nir_stack_1m.tif        uint8,  N bands — the NIR bands themselves.
    nir_stack_ndvi_1m.tif   int16,  N bands — NDVI x 1000 per acquisition.
    nir_stack_README.txt    band order, source file, date, native GSD, root.

    Both share ONE grid: EPSG:3857, 1.0 unit pixels, extent = the Edmonds city
    polygon (qc/imagery_measure.CITY_SHP) padded >=100 m and SNAPPED TO THE CHM
    LATTICE (Imagery/lidar_snoh_chm.tif), so the stack overlays the CHM /
    structure / hillshade rasters pixel-for-pixel with no resampling.

    CAUTION ON "1 m": EPSG:3857 is not metric on the ground. At Edmonds
    (lat ~47.81) Web Mercator inflates distance by 1/cos(lat) = 1.49, so a 1.0
    *unit* pixel is ~0.67 m of ground — the same correction the YEAR_CATALOG
    gsd_cm note applies. The grid is named "1m" for its CRS units, matching the
    CHM and every other 3857 product in the project.

BAND CONVENTION (not invented here — reused verbatim)
    Every 4-band file in the catalog is R,G,B,NIR: band 1 = RED, band 4 = NIR.
    That is the convention of qc/phase4_qc_ndvi.py and
    pipeline/phase4_build_corrected_labels.py, both of which do
        rgbi = img.read([1, 2, 3, nir_b]); r, nir = rgbi[0], rgbi[3]
        ndvi = (nir - r) / (nir + r + 1e-6)
    and it is confirmed per file by the band DESCRIPTIONS on disk
    (('Red','Green','Blue','NIR')). Sources are checked at build time: a file
    whose band 4 is constant (an alpha channel masquerading as NIR — see the
    superseded 2023_naip_rgbi.tif and the 2015s pilot) is REPORTED and its NDVI
    band is skipped rather than guessed.

DTYPE HANDLING
    All ten sources are uint8 today, so the NIR stack is a straight uint8 copy —
    no rescale, no stretch, values are the source DNs. If a future source lands
    as uint16 / float, --scale-mode decides: "auto" (default) percentile-stretches
    it to 0..255 and RECORDS the stretch in the README; "raw" clips. NDVI is
    computed in float32 from the native DNs (before any 8-bit squeeze) and stored
    as int16 x1000, so the NDVI product is unaffected by that choice.

NODATA
    NIR stack : 0 = no data. A pixel is "not imaged" when all four source bands
                are exactly 0 — the COVERAGE_NODATA convention of phase4seg.
    NDVI      : -32768 = no data (so a legitimate NDVI of 0.000 stays readable).

USAGE
    py -3.12 pipeline/make_nir_stack.py --step inventory      # look, write nothing
    py -3.12 pipeline/make_nir_stack.py                       # build everything
    py -3.12 pipeline/make_nir_stack.py --only 2016,2023n     # rebuild a subset
    py -3.12 pipeline/make_nir_stack.py --resampling average  # see note below

    --resampling defaults to BILINEAR. Note that the two 6-inch sources (2018s,
    2021s) are downsampled ~4.4x onto this grid, where bilinear SAMPLES rather
    than averages and can alias; "average" is the anti-aliased alternative if
    you are reading fine texture rather than flickering years.

Kam's tool. Local-only (rasterio + geopandas install locally); no Colab, no GPU.
"""

from __future__ import annotations

from phase4seg.names import clean_argv
import argparse
import csv
import math
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import ColorInterp, Resampling
from rasterio.vrt import WarpedVRT

_HERE = Path(__file__).resolve().parent           # …/Scripts/pipeline
_SCRIPTS = _HERE.parent                           # …/Scripts
sys.path.insert(0, str(_SCRIPTS / "qc"))          # imagery_measure (CITY_SHP)

from phase4seg import config as C                 # noqa: E402
import imagery_measure as im                      # noqa: E402  (CITY_SHP local-first)

try:
    from pipeline_log import write_step_log       # noqa: E402
except Exception:                                 # logging is a nicety, not a gate
    write_step_log = None


# ── Grid + output constants ───────────────────────────────────────────────────

DST_CRS      = "EPSG:3857"
DST_RES      = 1.0                       # CRS units (~0.67 m ground at Edmonds)
PAD_M        = 100.0                     # pad on the city polygon, CRS units
SNAP_RASTER  = "lidar_snoh_chm.tif"      # snap the lattice to this (1 m, 3857)

OUT_DIR      = Path(r"D:\edmonds-pipeline\ARCGIS\MachineLearning\nir_stack")
NIR_TIF      = "nir_stack_1m.tif"
NDVI_TIF     = "nir_stack_ndvi_1m.tif"
README_TXT   = "nir_stack_README.txt"

NIR_NODATA   = 0
NDVI_NODATA  = -32768
NDVI_SCALE   = 1000                      # NDVI stored as round(ndvi * 1000)

# ── LIFTED BLACK POINT test ───────────────────────────────────────────────────
# Open water absorbs NIR almost completely, so a healthy NIR band bottoms out
# near 0 DN over Puget Sound (~40% of this grid) and its NDVI carries a clear
# negative tail. A hazy or uncorrected delivery lifts every band's floor, and
# because NDVI is a RATIO the lift does not cancel: dark NIR-absorbing targets
# stop reading negative and the whole NDVI scale is biased upward.
#
# The test is deliberately TWO-SIDED, because each half alone false-positives:
#   * a water-tail FRACTION at a fixed NDVI cut is seasonally brittle. Measured
#     2026-08-25: AUGUST water reads NDVI ~-0.25 to -0.35 (2016, 2017n, 2017s)
#     while OCTOBER water reads -0.5 to -0.9 (2019n, 2023n), so a -0.3 cut
#     condemned three healthy August bands.
#   * a partial-coverage band (2016 has a NW water gap) is missing an unknown
#     share of the Sound from its valid-pixel denominator.
# The NIR band's OWN dark-target floor is immune to both, and the NDVI tail
# confirms it. Measured: NAIP 2015 carries a band-4 floor of 32-33 DN against
# 2-3 DN for NAIP 2017 — and it is in the source DOQQs, not our mosaic, so the
# whole 2015 delivery is hazy.
#
# Flagged, never silently "fixed": a per-band offset would be a guess, and the
# relative vegetation contrast is still honest.
LIFTED_NIR_P1  = 20                      # DN: a healthy NIR band floors near 0
LIFTED_NDVI_P1 = -200                    # NDVI x1000: healthy bands keep a negative tail
WATER_NDVI     = -300                    # NDVI x1000: reported as a diagnostic only

RED_BAND     = 1                         # repo-wide RGBI convention (see header)
NIR_BAND     = 4

DATE_CSV     = _SCRIPTS / "qc" / "imagery_pixelsize_and_date.csv"
LOGS_DIR     = Path(r"G:\My Drive\treedata\phase4\logs")

RESAMPLING = {"nearest": Resampling.nearest, "bilinear": Resampling.bilinear,
              "cubic": Resampling.cubic, "average": Resampling.average}


# ── Inventory ─────────────────────────────────────────────────────────────────

def _resolve(native_file: str):
    """Catalog filename -> (path, root) through config.imagery_roots().

    imagery_roots() makes recording WHICH root answered a caller obligation —
    a silent cross-root fallback is the bug that ordering exists to expose.
    """
    for root in C.imagery_roots():
        p = root / native_file
        if p.exists():
            return p, root
    return None, None


_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def _load_dates():
    """file -> {date_shot, date_precision, evidence_grade, true_ground_cm}.

    qc/imagery_pixelsize_and_date.csv is the ONE HOME for per-acquisition date +
    true pixel size; the catalog's gsd_cm is a rounded convenience copy.
    """
    out = {}
    if not DATE_CSV.exists():
        return out
    with open(DATE_CSV, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            out[row["file"]] = row
    return out


def _compact_date(row, key_year: str):
    """A short date for the band description + a sortable key.

    date_shot in the CSV is prose (the 2016 cell is a paragraph of shadow-azimuth
    reasoning). Pull the ISO dates out of it: one -> that date; several -> the
    earliest with a '+' (multi-day flight or a window); none -> the year label.
    """
    if not row:
        return f"{key_year}?", f"{key_year[:4]}-07-01"
    hits = _ISO.findall(row.get("date_shot", "") or "")
    if not hits:
        return f"{key_year}?", f"{key_year[:4]}-07-01"
    # FIRST occurrence, not min(): the cells lead with the operative date and may
    # mention EXCLUDED alternatives later (2016 rules out an 2016-08-11 sortie by
    # shadow azimuth after stating 2016-08-12), so min() would report the reject.
    first = hits[0]
    return (first if len(hits) == 1 else first + "+"), first


def _source_short(fname: str):
    low = fname.lower()
    if "naip" in low:
        return "NAIP"
    if "snoh" in low:
        return "SnohCo"
    if "coe" in low:
        return "CoE"
    if "usgs" in low:
        return "USGS"
    return "?"


def build_inventory(only=None):
    """Every YEAR_CATALOG entry with bands == 4, resolved, opened and verified.

    Returns (included, problems). An entry is INCLUDED only when the file
    resolves through imagery_roots() AND rasterio agrees it has 4 bands.
    """
    dates = _load_dates()
    included, problems = [], []

    for entry in C.YEAR_CATALOG:
        if int(entry.get("bands", 0)) != 4:
            continue
        label = str(entry["label"])
        if only and label not in only:
            continue

        fname = entry["native_file"]
        path, root = _resolve(fname)
        if path is None:
            problems.append((label, fname, "NOT FOUND in any imagery root"))
            continue

        try:
            with rasterio.open(path) as ds:
                count, dtype = ds.count, ds.dtypes[0]
                descs, crs = ds.descriptions, (ds.crs.to_string() if ds.crs else "?")
                nodata, res = ds.nodata, ds.res
                size = (ds.width, ds.height)
        except Exception as exc:
            problems.append((label, fname, f"rasterio could not open: {exc}"))
            continue

        if count != 4:
            problems.append((label, fname,
                             f"catalog says bands=4 but the file has {count}"))
            continue

        row = dates.get(fname)
        disp, sortkey = _compact_date(row, label)
        included.append(dict(
            label=label, key=entry["key"], file=fname, path=path, root=root,
            source=entry["source"], src_short=_source_short(fname),
            gsd_cm=float(entry["gsd_cm"]),
            true_cm=(row or {}).get("true_ground_cm", ""),
            eff_cm=(row or {}).get("effective_cm", ""),
            date=disp, sortkey=sortkey,
            date_full=(row or {}).get("date_shot", ""),
            date_prec=(row or {}).get("date_precision", ""),
            grade=(row or {}).get("evidence_grade", ""),
            coverage=entry.get("coverage", ""),
            dtype=dtype, descs=descs, crs=crs, nodata=nodata,
            native_res=res, size=size, bytes=path.stat().st_size,
        ))

    included.sort(key=lambda d: (d["sortkey"], d["label"]))
    return included, problems


def orphan_four_band(known_files):
    """4-band rasters sitting in an imagery root that no catalog entry claims.

    Reported, never included — an uncataloged file has no provenance row, and
    the project's rule is that YEAR_CATALOG is the authority on what exists.
    """
    found = {}
    for root in C.imagery_roots():
        for p in sorted(root.glob("*.tif")):
            if p.name in known_files:
                continue
            try:
                with rasterio.open(p) as ds:
                    if ds.count != 4:
                        continue
                    descs = ds.descriptions
            except Exception:
                continue
            # a file mirrored into two roots is ONE orphan, not two
            found.setdefault(p.name, ([], descs))[0].append(str(root))
    return [(n, " + ".join(rs), d) for n, (rs, d) in sorted(found.items())]


# ── Target grid ───────────────────────────────────────────────────────────────

def target_grid():
    """City polygon bounds, padded >=PAD_M, snapped OUTWARD to the CHM lattice."""
    import geopandas as gpd
    from rasterio.transform import from_origin

    city = gpd.read_file(im.CITY_SHP).to_crs(DST_CRS)
    xmin, ymin, xmax, ymax = city.total_bounds
    xmin, ymin, xmax, ymax = xmin - PAD_M, ymin - PAD_M, xmax + PAD_M, ymax + PAD_M

    ox, oy = 0.0, 0.0
    snap_path, _ = _resolve(SNAP_RASTER)
    if snap_path is not None:
        with rasterio.open(snap_path) as ds:
            ox, oy = ds.transform.c, ds.transform.f    # the CHM pixel-edge lattice

    # snap OUTWARD so the >=100 m pad survives the snap
    xmin = ox + math.floor((xmin - ox) / DST_RES) * DST_RES
    ymin = oy + math.floor((ymin - oy) / DST_RES) * DST_RES
    xmax = ox + math.ceil((xmax - ox) / DST_RES) * DST_RES
    ymax = oy + math.ceil((ymax - oy) / DST_RES) * DST_RES

    width = int(round((xmax - xmin) / DST_RES))
    height = int(round((ymax - ymin) / DST_RES))
    return from_origin(xmin, ymax, DST_RES, DST_RES), width, height, \
        (xmin, ymin, xmax, ymax), (snap_path.name if snap_path else None), city


# ── Warp one acquisition ──────────────────────────────────────────────────────

def warp_rgbi(path, transform, width, height, resampling, threads, mem_mb):
    """All 4 bands of one source onto the target grid, as (4, H, W) uint8-ish.

    WarpedVRT streams the source through GDAL's warper block by block, so the
    peak footprint is the OUTPUT (4 x ~123 MB here), not the up-to-31 GB input.
    src_nodata is honoured where the file declares it (the NAIP mosaics declare
    0) so a bilinear kernel does not bleed fill into real pixels at the seams.

    num_threads / warp_mem_limit are a pure SPEED knob — the warper is
    deterministic, so a threaded run returns the same pixels as a serial one
    (verified 2026-08-25 on 2023n: identical band means, 152 s -> 34 s). Without
    them the full ten-band build is ~2 h of single-threaded warping.
    """
    with rasterio.open(path) as src:
        vrt_kw = dict(crs=DST_CRS, transform=transform, width=width,
                      height=height, resampling=resampling,
                      num_threads=threads, warp_mem_limit=mem_mb)
        if src.nodata is not None:
            vrt_kw["src_nodata"] = src.nodata
        vrt_kw["nodata"] = 0
        with WarpedVRT(src, **vrt_kw) as vrt:
            return vrt.read([1, 2, 3, 4]), src.dtypes[0]


def to_uint8(nir, dtype, scale_mode):
    """NIR -> uint8 for the visual stack. Records what it did.

    Every current source is already uint8 (measured 2026-08-25), so this is a
    no-op today; it exists so a future uint16/float source cannot silently
    wrap-around into garbage.
    """
    if dtype == "uint8":
        return nir.astype(np.uint8, copy=False), "native uint8 (no rescale)"
    valid = nir > 0
    if not valid.any():
        return np.zeros(nir.shape, np.uint8), f"{dtype}: empty"
    if scale_mode == "raw":
        return np.clip(nir, 0, 255).astype(np.uint8), f"{dtype}: clipped to 0-255"
    lo, hi = np.percentile(nir[valid], [2, 98])
    if hi <= lo:
        hi = lo + 1
    out = np.clip((nir.astype(np.float32) - lo) * (254.0 / (hi - lo)) + 1, 1, 255)
    return out.astype(np.uint8), f"{dtype}: p2-p98 stretch [{lo:.1f},{hi:.1f}] -> 1-255"


def ndvi_int16(red, nir, valid, chunk=2048):
    """NDVI x 1000 as int16, computed in row chunks so float32 never sees the
    whole 123 Mpx grid at once. Formula and epsilon are verbatim from
    qc/phase4_qc_ndvi.py: (nir - r) / (nir + r + 1e-6).
    """
    h, w = red.shape
    out = np.full((h, w), NDVI_NODATA, np.int16)
    for r0 in range(0, h, chunk):
        r1 = min(h, r0 + chunk)
        m = valid[r0:r1]
        if not m.any():
            continue
        r = red[r0:r1].astype(np.float32)
        n = nir[r0:r1].astype(np.float32)
        v = (n - r) / (n + r + 1e-6)
        np.clip(v, -1.0, 1.0, out=v)
        blk = out[r0:r1]
        blk[m] = np.round(v[m] * NDVI_SCALE).astype(np.int16)
    return out


# ── Reporting helpers ─────────────────────────────────────────────────────────

def _hist(arr, nodata, lo, hi, chunk=2048):
    """Exact integer histogram over valid pixels, accumulated in row chunks.

    Histogram rather than arr[mask]: a boolean index over 123 Mpx materialises a
    ~1 GB float64 copy, and we want percentiles anyway. Integer data means the
    histogram is EXACT, not an approximation.
    """
    h = np.zeros(hi - lo + 1, np.int64)
    for r0 in range(0, arr.shape[0], chunk):
        blk = arr[r0:min(arr.shape[0], r0 + chunk)]
        v = blk[blk != nodata]
        if v.size:
            h += np.bincount(v.astype(np.int32) - lo, minlength=h.size)
    return h


def band_stats(arr, nodata, lo, hi, frac_below=None):
    """min/max/mean/sd + p1/p50/p99 for one band, exactly, from its histogram.

    p1 is the one that matters here: it is the DARK-TARGET FLOOR. A NIR band
    whose p1 sits well above 0 — or an NDVI band with no negative tail — has a
    lifted black point, which biases NDVI upward and breaks cross-year
    comparison of absolute values (measured for NAIP 2015; see the README).
    """
    h = _hist(arr, nodata, lo, hi)
    vals = np.arange(lo, hi + 1, dtype=np.float64)
    n = int(h.sum())
    if n == 0:
        return dict(valid_px=0, pct=0.0, min=None, max=None, mean=None,
                    std=None, p1=None, p50=None, p99=None, frac_below=None)
    nz = np.nonzero(h)[0]
    mean = float((h * vals).sum() / n)
    var = float((h * (vals - mean) ** 2).sum() / n)
    cum = np.cumsum(h)

    def q(p):
        return float(vals[min(int(np.searchsorted(cum, p * n)), h.size - 1)])

    fb = None
    if frac_below is not None:
        fb = float(h[:max(0, int(frac_below) - lo)].sum() / n)
    return dict(valid_px=n, pct=100.0 * n / arr.size, min=float(vals[nz[0]]),
                max=float(vals[nz[-1]]), mean=mean, std=var ** 0.5,
                p1=q(0.01), p50=q(0.50), p99=q(0.99), frac_below=fb)


def _stat_tags(st):
    if not st["valid_px"]:
        return {}
    return {"STATISTICS_MINIMUM": f"{st['min']:.0f}", "STATISTICS_MAXIMUM": f"{st['max']:.0f}",
            "STATISTICS_MEAN": f"{st['mean']:.4f}", "STATISTICS_STDDEV": f"{st['std']:.4f}",
            "STATISTICS_VALID_PERCENT": f"{st['pct']:.2f}"}


def is_lifted(nir_st, ndvi_st):
    """True when this band's NIR black point is lifted (see the constants block).

    BOTH halves must hold: a high dark-target floor in the NIR band itself AND
    the absence of a negative NDVI tail. Either alone false-positives — the
    measured counter-examples are beside LIFTED_NIR_P1.
    """
    if not nir_st.get("valid_px") or not ndvi_st.get("valid_px"):
        return False
    return nir_st["p1"] >= LIFTED_NIR_P1 and ndvi_st["p1"] > LIFTED_NDVI_P1


def describe(rec):
    """Short band name for ArcGIS: label, date, sensor, native GSD."""
    return f"{rec['label']} {rec['date']} NIR {rec['gsd_cm']:.0f}cm {rec['src_short']}"


# ── Build ─────────────────────────────────────────────────────────────────────

def build(args):
    only = set(s.strip() for s in args.only.split(",")) if args.only else None
    inv, problems = build_inventory(only)
    if not inv:
        print("[nir-stack] nothing to stack — inventory is empty")
        return 1

    known = {e["native_file"] for e in C.YEAR_CATALOG}
    orphans = orphan_four_band(known)

    transform, width, height, bounds, snapped_to, city = target_grid()
    resamp = RESAMPLING[args.resampling]
    n = len(inv)

    print(f"[nir-stack] grid   : {DST_CRS} @ {DST_RES} unit px  {width} x {height}"
          f"  ({width * height / 1e6:.1f} Mpx/band)")
    print(f"[nir-stack] bounds : {bounds[0]:.1f} {bounds[1]:.1f} {bounds[2]:.1f} {bounds[3]:.1f}"
          f"   snapped to {snapped_to}")
    print(f"[nir-stack] bands  : {n}   resampling={args.resampling}")
    for i, rec in enumerate(inv, 1):
        print(f"    {i:2d}  {rec['label']:6s} {rec['date']:12s} {rec['file']:26s}"
              f" {rec['gsd_cm']:5.1f}cm  {rec['crs']:11s} root={rec['root']}")
    for lab, f, why in problems:
        print(f"    !!  {lab:6s} {f:26s} {why}")

    out_dir = Path(args.out_dir) if args.out_dir else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    nir_path, ndvi_path = out_dir / NIR_TIF, out_dir / NDVI_TIF

    # interleave="BAND" is LOAD-BEARING, not a style choice. GTiff defaults to
    # PIXEL interleave, where one tile holds all N bands' samples — so writing
    # band-by-band (which is the only way to build this: one acquisition warped
    # at a time) forces GDAL to read-modify-recompress every tile once per band.
    # Once the block cache fills, that thrashes: measured 2026-08-25, bands 1-3
    # took 15-65 s each and band 4 had not finished after 15 min at a pinned
    # 3.1 GB working set. BAND interleave stores each band contiguously, so the
    # write is sequential and no tile is ever revisited. ArcGIS reads it fine.
    common = dict(driver="GTiff", width=width, height=height, count=n,
                  crs=DST_CRS, transform=transform, tiled=True,
                  blockxsize=512, blockysize=512, compress="LZW", predictor=2,
                  interleave="BAND", photometric="MINISBLACK",
                  BIGTIFF="IF_SAFER", num_threads="ALL_CPUS")

    nir_stats, ndvi_stats, notes, t0 = [], [], [], time.time()

    dst_nir = rasterio.open(nir_path, "w", dtype="uint8", nodata=NIR_NODATA, **common)
    dst_ndvi = None
    if not args.skip_ndvi:
        dst_ndvi = rasterio.open(ndvi_path, "w", dtype="int16", nodata=NDVI_NODATA, **common)

    try:
        for i, rec in enumerate(inv, 1):
            t1 = time.time()
            print(f"[nir-stack] ({i}/{n}) {rec['label']:6s} warping "
                  f"{rec['file']} ({rec['bytes'] / 2**30:.1f} GB) …", flush=True)

            rgbi, src_dtype = warp_rgbi(rec["path"], transform, width, height, resamp,
                                        args.threads, args.warp_mem)
            # COVERAGE_NODATA convention (phase4seg/config.py): a pixel is "not
            # imaged" only when EVERY band is exactly the fill value.
            valid = (rgbi != 0).any(axis=0)
            red, nir_raw = rgbi[RED_BAND - 1], rgbi[NIR_BAND - 1]

            # Alpha-masquerading-as-NIR guard. Band 4 of a served export is
            # sometimes a constant alpha channel (the superseded 2023 NAIP
            # re-export, the 2015s pilot). A constant band 4 makes NDVI a pure
            # function of red — meaningless — so its NDVI band is SKIPPED.
            nir_valid = nir_raw[valid] if valid.any() else nir_raw.ravel()[:1]
            const_nir = bool(nir_valid.size and nir_valid.min() == nir_valid.max())
            if const_nir:
                notes.append(f"{rec['label']}: band 4 is CONSTANT "
                             f"(= {int(nir_valid.min())}) over the city grid — an alpha "
                             f"channel, not NIR. NIR band written as-is; NDVI SKIPPED.")
                print(f"    !! band 4 constant ({int(nir_valid.min())}) — NDVI skipped")

            nir8, how = to_uint8(nir_raw, src_dtype, args.scale_mode)
            nir8[~valid] = NIR_NODATA
            rec["scale_note"] = how

            st = band_stats(nir8, NIR_NODATA, 0, 255)
            nir_stats.append(st)
            dst_nir.write(nir8, i)
            dst_nir.set_band_description(i, describe(rec))
            dst_nir.update_tags(i, **_stat_tags(st), source_file=rec["file"],
                                acquired=rec["date"], native_gsd_cm=f"{rec['gsd_cm']}",
                                native_crs=rec["crs"], scaling=how)

            if dst_ndvi is not None:
                if const_nir:
                    nd = np.full((height, width), NDVI_NODATA, np.int16)
                    stn = dict(valid_px=0, pct=0.0, min=None, max=None,
                               mean=None, std=None, p1=None, p50=None, p99=None)
                else:
                    nd = ndvi_int16(red, nir_raw, valid)
                    stn = band_stats(nd, NDVI_NODATA, -NDVI_SCALE, NDVI_SCALE,
                                     frac_below=WATER_NDVI)
                    if is_lifted(st, stn):
                        notes.append(
                            f"{rec['label']}: NIR floor p1 = {st['p1']:.0f} DN (a healthy "
                            f"band floors near 0 over water) and NDVI p1 = "
                            f"{stn['p1'] / NDVI_SCALE:+.3f} (no negative tail; only "
                            f"{100 * (stn['frac_below'] or 0):.2f}% of the grid reads NDVI < "
                            f"{WATER_NDVI / NDVI_SCALE:+.1f}, though ~40% of it is Puget Sound). "
                            f"The BLACK POINT IS LIFTED — and it is in the SOURCE tiles, not "
                            f"introduced here. Relative vegetation contrast is fine, but "
                            f"ABSOLUTE NDVI is biased upward: do NOT compare this band's NDVI "
                            f"numbers against another year's, and do NOT apply a fixed "
                            f"0.2 / 0.3 vegetation cut to it.")
                        print(f"    !! LIFTED BLACK POINT: NIR p1={st['p1']:.0f} DN "
                              f"(>= {LIFTED_NIR_P1}), NDVI p1={stn['p1'] / NDVI_SCALE:+.3f} "
                              f"(> {LIFTED_NDVI_P1 / NDVI_SCALE:+.2f}), water tail "
                              f"{100 * (stn['frac_below'] or 0):.2f}%"
                              f" — absolute NDVI not cross-year comparable")
                ndvi_stats.append(stn)
                dst_ndvi.write(nd, i)
                lbl = describe(rec).replace(" NIR ", " NDVIx1000 ")
                dst_ndvi.set_band_description(i, lbl + (" [SKIPPED]" if const_nir else ""))
                dst_ndvi.update_tags(i, **_stat_tags(stn), source_file=rec["file"],
                                     acquired=rec["date"],
                                     formula="(b4-b1)/(b4+b1+1e-6) x1000, int16",
                                     skipped="constant band 4" if const_nir else "")
                del nd

            del rgbi, red, nir_raw, nir8
            summary = ("NO VALID PIXELS — does this source cover Edmonds?"
                       if not st["valid_px"] else
                       f"min/max/mean={st['min']:.0f}/{st['max']:.0f}/{st['mean']:.1f}")
            print(f"    valid={st['pct']:.1f}%  {summary}"
                  f"   {time.time() - t1:.0f}s", flush=True)

        for dst in (dst_nir, dst_ndvi):
            if dst is None:
                continue
            try:
                dst.colorinterp = [ColorInterp.undefined] * n
            except Exception:
                pass
            dst.update_tags(created=datetime.now().isoformat(timespec="seconds"),
                            generator="pipeline/make_nir_stack.py",
                            grid=f"{DST_CRS} @ {DST_RES} unit px, snapped to {snapped_to}",
                            resampling=args.resampling,
                            band_convention="source band1=RED band4=NIR (repo-wide RGBI)")
            if not args.no_overviews:
                print(f"[nir-stack] overviews for {Path(dst.name).name} …", flush=True)
                dst.build_overviews([2, 4, 8, 16], Resampling.average)
                dst.update_tags(ns="rio_overview", resampling="average")
    finally:
        dst_nir.close()
        if dst_ndvi is not None:
            dst_ndvi.close()

    write_readme(out_dir / README_TXT, inv, problems, orphans, nir_stats, ndvi_stats,
                 bounds, width, height, snapped_to, args, nir_path, ndvi_path, notes)

    report(nir_path, ndvi_path if not args.skip_ndvi else None, inv,
           nir_stats, ndvi_stats, city, transform, width, height)

    dt = time.time() - t0
    print(f"\n[nir-stack] done in {dt / 60:.1f} min")
    if write_step_log is not None:
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            write_step_log(script="make_nir_stack", step="build", logs_dir=LOGS_DIR,
                           bands=n, grid=f"{width}x{height}", resampling=args.resampling,
                           nir_tif=str(nir_path), ndvi_tif=str(ndvi_path),
                           errors=len(problems),
                           notes="; ".join(notes) or "clean")
        except Exception as exc:
            print(f"[nir-stack] WARN could not write step log: {exc}")
    return 0


# ── README ────────────────────────────────────────────────────────────────────

def write_readme(path, inv, problems, orphans, nir_stats, ndvi_stats,
                 bounds, width, height, snapped_to, args, nir_path, ndvi_path,
                 notes=()):
    L = []
    A = L.append
    A("NIR MEGA-STACK — every 4th (NIR) band of every 4-band Edmonds acquisition")
    A("=" * 78)
    A(f"generated  : {datetime.now().isoformat(timespec='seconds')}  "
      f"by Scripts/pipeline/make_nir_stack.py")
    A(f"bands      : {len(inv)} acquisitions, chronological (earliest known flight date)")
    A("")
    A("GRID (both products share it exactly)")
    A(f"  CRS      : {DST_CRS}")
    A(f"  pixel    : {DST_RES} CRS unit  ==  ~{DST_RES * math.cos(math.radians(47.81)):.2f} m of GROUND")
    A("             (Web Mercator inflates distance by 1/cos(lat)=1.49 at Edmonds;")
    A("              the same correction the YEAR_CATALOG gsd_cm note applies.)")
    A(f"  size     : {width} x {height} px  ({width * height / 1e6:.1f} Mpx per band)")
    A(f"  extent   : {bounds[0]:.1f}  {bounds[1]:.1f}  {bounds[2]:.1f}  {bounds[3]:.1f}")
    A(f"  origin   : Edmonds city polygon bounds padded >= {PAD_M:.0f} CRS units, then")
    A(f"             snapped OUTWARD to the {snapped_to} lattice, so this stack")
    A("             overlays the CHM / structure / hillshade rasters 1:1.")
    A(f"  city poly: {im.CITY_SHP}")
    A(f"  resample : {args.resampling}")
    if args.resampling == "bilinear":
        A("             NOTE: 2018s and 2021s (6-inch) are ~4.4x downsampled onto this")
        A("             grid, where bilinear SAMPLES rather than averages and can alias.")
        A("             Rebuild with --resampling average if you are reading fine texture")
        A("             rather than flickering years.")
    A("")
    A("PRODUCTS")
    A(f"  {nir_path.name:24s} uint8  — the NIR band DNs. nodata = {NIR_NODATA}.")
    A("                           Values are SOURCE DNs and are NOT radiometrically")
    A("                           cross-calibrated: different sensors, sun angles and")
    A("                           seasons. Compare WITHIN a band freely; compare")
    A("                           ACROSS bands only qualitatively (that is what the")
    A("                           NDVI product is for).")
    if not args.skip_ndvi:
        A(f"  {ndvi_path.name:24s} int16  — NDVI x 1000. nodata = {NDVI_NODATA}.")
        A("                           NDVI = (band4 - band1) / (band4 + band1 + 1e-6),")
        A("                           i.e. (NIR - RED)/(NIR + RED) — the formula and")
        A("                           epsilon are verbatim from qc/phase4_qc_ndvi.py and")
        A("                           pipeline/phase4_build_corrected_labels.py, which")
        A("                           both read [1,2,3,4] and take r=band1, nir=band4.")
        A("                           Computed from the NATIVE DNs, then resampled-")
        A("                           resampled inputs -> ratio (both bands warped with")
        A("                           the same kernel before the ratio is formed).")
        A("                           Divide by 1000 for true NDVI. 0.2 is the repo's")
        A("                           live-vegetation cut; 0.3 is its ADD-canopy cut.")
    A(f"  {README_TXT:24s} this file.")
    A("")
    A("BAND ORDER")
    A("-" * 78)
    hdr = (f"{'#':>2}  {'label':6s} {'date':13s} {'prec':5s} {'grade':9s} "
           f"{'nat.GSD':>8s} {'CRS':11s} {'valid%':>7s} {'mean':>7s}  source file")
    A(hdr)
    for i, rec in enumerate(inv, 1):
        st = nir_stats[i - 1] if i - 1 < len(nir_stats) else {}
        prec = (rec["date_prec"] or "")[:5]
        grade = (rec["grade"] or "")[:9]
        A(f"{i:2d}  {rec['label']:6s} {rec['date']:13s} {prec:5s} {grade:9s} "
          f"{rec['gsd_cm']:7.1f}c {rec['crs']:11s} "
          f"{st.get('pct', 0):6.1f}% {st.get('mean') or 0:7.1f}  {rec['file']}")
    A("")
    A("PER-BAND DETAIL")
    A("-" * 78)
    for i, rec in enumerate(inv, 1):
        st = nir_stats[i - 1]
        A(f"[{i}] {rec['label']}   {describe(rec)}")
        A(f"     source file : {rec['file']}")
        A(f"     resolved at : {rec['root']}")
        A(f"     provenance  : {rec['source']}")
        A(f"     native      : {rec['size'][0]} x {rec['size'][1]} px, {rec['crs']}, "
          f"{rec['dtype']}, res {rec['native_res'][0]:g}, "
          f"{rec['bytes'] / 2**30:.2f} GB")
        A(f"     band descs  : {rec['descs']}")
        A(f"     native GSD  : catalog {rec['gsd_cm']} cm   "
          f"true_ground {rec['true_cm']} cm")
        A(f"     effective   : {rec['eff_cm']}")
        A(f"     date shot   : {rec['date_full'] or '(not in the date CSV)'}")
        A(f"     precision   : {rec['date_prec']}   evidence: {rec['grade']}")
        A(f"     coverage    : {rec['coverage']}")
        A(f"     dtype        : {rec.get('scale_note', '')}")
        if st["valid_px"]:
            A(f"     NIR  on grid : valid {st['pct']:.2f}%  min {st['min']:.0f}  "
              f"max {st['max']:.0f}  mean {st['mean']:.2f}  sd {st['std']:.2f}")
            A(f"                    p1 {st['p1']:.0f}  p50 {st['p50']:.0f}  p99 {st['p99']:.0f}"
              f"   (p1 = the dark-target floor)")
        else:
            A("     NIR  on grid : NO VALID PIXELS — this source does not reach the "
              "city grid.")
        if ndvi_stats and i - 1 < len(ndvi_stats):
            sn = ndvi_stats[i - 1]
            if sn["valid_px"]:
                A(f"     NDVI on grid : valid {sn['pct']:.2f}%  "
                  f"min {sn['min'] / NDVI_SCALE:+.3f}  max {sn['max'] / NDVI_SCALE:+.3f}  "
                  f"mean {sn['mean'] / NDVI_SCALE:+.3f}  sd {sn['std'] / NDVI_SCALE:.3f}")
                A(f"                    p1 {sn['p1'] / NDVI_SCALE:+.3f}  "
                  f"p50 {sn['p50'] / NDVI_SCALE:+.3f}  p99 {sn['p99'] / NDVI_SCALE:+.3f}")
                A(f"                    water tail (NDVI < {WATER_NDVI / NDVI_SCALE:+.1f}): "
                  f"{100 * (sn['frac_below'] or 0):.2f}% of the grid"
                  + ("   <-- LIFTED BLACK POINT, see RADIOMETRY"
                     if is_lifted(st, sn) else ""))
            else:
                A("     NDVI on grid : SKIPPED (band 4 was constant — alpha, not NIR)")
        A("")
    A("RADIOMETRY — READ THIS BEFORE COMPARING NDVI ACROSS BANDS")
    A("-" * 78)
    A("  These are ten separate flights by four sensor programmes across nine years,")
    A("  with no cross-calibration between them. NDVI cancels most exposure and")
    A("  sun-angle difference, which is why it is the product to compare on — but it")
    A("  cannot fix a lifted BLACK POINT. A hazy or uncorrected delivery raises every")
    A("  band's floor, and because NDVI is a ratio the lift does not cancel: dark,")
    A("  NIR-absorbing targets (water, deep shade) stop reading negative.")
    A("")
    A("  The p1 rows above are the test. Open water absorbs NIR almost completely,")
    A("  so a healthy NIR band floors near 0 DN over Puget Sound (~40% of this")
    A("  extent) and its NDVI keeps a clear negative tail. A band is flagged only")
    A(f"  when BOTH fail: NIR p1 >= {LIFTED_NIR_P1} DN AND NDVI p1 > {LIFTED_NDVI_P1 / NDVI_SCALE:+.2f}.")
    A("")
    A("  Both halves are needed. A fixed water-NDVI cut alone is seasonally")
    A("  brittle: measured here, AUGUST water reads NDVI about -0.25 to -0.35")
    A("  while OCTOBER water reads -0.5 to -0.9, so a -0.3 cut condemns healthy")
    A("  August bands. And a partial-coverage band (2016 has a NW water gap) is")
    A("  missing an unknown share of the Sound from its denominator. The NIR")
    A("  floor is immune to both, and the NDVI tail confirms it.")
    A("")
    A("  Nothing is corrected for it. A per-band offset would be a guess, and the")
    A("  relative signal is still honest — so the bias is REPORTED and left in.")
    A("")
    if notes:
        A("  FLAGGED THIS BUILD:")
        for nt in notes:
            A(f"    * {nt}")
    else:
        A("  Nothing flagged this build: every band has a dark-target negative tail.")
    A("")
    A("  What is still safe on a flagged band: WHERE the vegetation is, and how it")
    A("  changed WITHIN that band. What is not: reading its NDVI number against")
    A("  another year's, or applying a fixed 0.2 / 0.3 threshold to it.")
    A("")
    A("SOURCE OF TRUTH")
    A("-" * 78)
    A("  which files exist / how many bands  -> Scripts/pipeline/phase4seg/config.py")
    A("                                         YEAR_CATALOG (entries with bands == 4)")
    A("  which root a filename resolves from -> config.imagery_roots() (D: mirror first)")
    A("  date shot + true pixel size          -> Scripts/qc/imagery_pixelsize_and_date.csv")
    A("  red/NIR band convention              -> qc/phase4_qc_ndvi.py (read [1,2,3,4],")
    A("                                          r=[0], nir=[3])")
    A("  city polygon                         -> qc/imagery_measure.py CITY_SHP")
    A("")
    if problems:
        A("CATALOG ENTRIES THAT DID NOT MAKE IT IN")
        A("-" * 78)
        for lab, f, why in problems:
            A(f"  {lab:8s} {f:28s} {why}")
        A("")
    if orphans:
        A("4-BAND FILES ON DISK THAT THE CATALOG DOES NOT LIST (reported, NOT included)")
        A("-" * 78)
        A("  An uncataloged raster has no provenance row, so it is never stacked.")
        A("  Most of these are SUPERSEDED_FILES (qc/phase4_catalog_check.py): the")
        A("  clipped / re-served exports the 2026-08-23 campaign replaced.")
        for name, root, descs in orphans:
            A(f"  {name:30s} {root}   descs={descs}")
        A("")
    A("HOW TO USE IT IN ARCGIS")
    A("-" * 78)
    A("  * Add nir_stack_1m.tif; in Symbology pick Stretched and step the Band")
    A("    dropdown down the list to flicker forward through time. Bright = high")
    A("    NIR return = live vegetation; dark = pavement, roof, water, bare soil.")
    A("  * A pixel bright in the early bands and dark in the late ones is a canopy-")
    A("    LOSS candidate; the reverse is growth/regrowth.")
    A("  * nir_stack_ndvi_1m.tif is the one to trust for cross-year comparison —")
    A("    the normalised ratio cancels most of the exposure/sun-angle difference")
    A("    that raw NIR DNs carry. Symbolise -200..800 (i.e. NDVI -0.2..0.8).")
    A("  * NDVI counts GRASS as vegetation. To read CANOPY, pair it with the CHM")
    A("    (lidar_snoh_chm.tif, DN x 0.2 = metres) — that is exactly the")
    A("    NDVI >= 0.2 AND height >= 2 m rule qc/phase4_qc_ndvi.py uses.")
    A("  * The date column is the flight date, not the calendar year: two bands can")
    A("    share a year (2017n / 2017s) and October bands (2019n/s, 2023n) are late-")
    A("    season, so deciduous NDVI runs lower there for phenology, not for loss.")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[nir-stack] wrote {path}")


# ── Validation report ─────────────────────────────────────────────────────────

def report(nir_path, ndvi_path, inv, nir_stats, ndvi_stats, city,
           transform, width, height):
    print("\n" + "=" * 78)
    print("VALIDATION")
    print("=" * 78)
    for p in (nir_path, ndvi_path):
        if p is None:
            continue
        with rasterio.open(p) as ds:
            print(f"\n{p}")
            print(f"  {ds.width} x {ds.height} x {ds.count}  {ds.dtypes[0]}  "
                  f"{ds.crs}  nodata={ds.nodata}  "
                  f"blocks={ds.block_shapes[0]}  ovr={ds.overviews(1)}")
            print(f"  size on disk: {p.stat().st_size / 2**20:,.1f} MiB")
            print(f"  {'#':>2}  {'band description':42s} {'valid%':>7s} "
                  f"{'min':>7s} {'max':>7s} {'mean':>8s} {'sd':>7s} "
                  f"{'p1':>7s} {'p50':>7s} {'p99':>7s}")
            stats = nir_stats if p == nir_path else ndvi_stats
            for i, d in enumerate(ds.descriptions, 1):
                st = stats[i - 1]
                if not st["valid_px"]:
                    print(f"  {i:2d}  {d or '':42s}    (no valid pixels)")
                    continue
                print(f"  {i:2d}  {d or '':42s} {st['pct']:6.2f}% "
                      f"{st['min']:7.0f} {st['max']:7.0f} {st['mean']:8.2f} "
                      f"{st['std']:7.2f} {st['p1']:7.0f} {st['p50']:7.0f} {st['p99']:7.0f}")

    cx, cy = city.geometry.iloc[0].centroid.x, city.geometry.iloc[0].centroid.y
    col = int((cx - transform.c) / transform.a)
    row = int((cy - transform.f) / transform.e)
    print(f"\n3x3 SAMPLE at the city centroid  ({cx:.1f}, {cy:.1f}) = px col {col}, row {row}")
    win = rasterio.windows.Window(col - 1, row - 1, 3, 3)
    for p in (nir_path, ndvi_path):
        if p is None:
            continue
        with rasterio.open(p) as ds:
            a = ds.read(window=win)
            print(f"\n  {p.name}")
            for i, d in enumerate(ds.descriptions, 1):
                blk = " | ".join(" ".join(f"{v:6d}" for v in r) for r in a[i - 1])
                print(f"    {i:2d} {(d or '')[:34]:34s}  {blk}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def inventory_only(args):
    only = set(s.strip() for s in args.only.split(",")) if args.only else None
    inv, problems = build_inventory(only)
    known = {e["native_file"] for e in C.YEAR_CATALOG}
    print(f"4-BAND ACQUISITIONS IN YEAR_CATALOG — {len(inv)} resolve and open\n")
    print(f"{'#':>2}  {'label':6s} {'date':13s} {'GSD':>7s} {'CRS':11s} {'dtype':7s} "
          f"{'size':>19s} {'GB':>6s}  file")
    for i, r in enumerate(inv, 1):
        print(f"{i:2d}  {r['label']:6s} {r['date']:13s} {r['gsd_cm']:6.1f}c "
              f"{r['crs']:11s} {r['dtype']:7s} "
              f"{r['size'][0]:>8d}x{r['size'][1]:<9d} {r['bytes'] / 2**30:6.2f}  {r['file']}")
        print(f"    descs={r['descs']}  root={r['root']}")
    for lab, f, why in problems:
        print(f"!!  {lab:6s} {f:28s} {why}")
    orph = orphan_four_band(known)
    if orph:
        print(f"\n4-BAND FILES NOT IN THE CATALOG ({len(orph)}) — reported, never stacked:")
        for name, root, descs in orph:
            print(f"    {name:30s} {root}  descs={descs}")
    transform, width, height, bounds, snapped_to, _ = target_grid()
    print(f"\nTARGET GRID  {DST_CRS} @ {DST_RES}  {width} x {height} px"
          f"  ({width * height / 1e6:.1f} Mpx)")
    print(f"  bounds {bounds}   snapped to {snapped_to}")
    return 0


def main():
    filtered = clean_argv()
    ap = argparse.ArgumentParser(
        description="Stack every 4-band acquisition's NIR band onto one aligned grid.")
    ap.add_argument("--step", default="build", choices=["build", "inventory"],
                    help="inventory = list what would be stacked and write nothing.")
    ap.add_argument("--only", default="",
                    help="Comma-separated year labels to include (default: all 4-band).")
    ap.add_argument("--resampling", default="bilinear", choices=sorted(RESAMPLING),
                    help="Warp kernel (default bilinear; 'average' is anti-aliased).")
    ap.add_argument("--scale-mode", default="auto", choices=["auto", "raw"],
                    help="Non-uint8 sources: percentile stretch (auto) or clip (raw).")
    ap.add_argument("--threads", type=int, default=8,
                    help="GDAL warp threads (speed only; output is identical).")
    ap.add_argument("--warp-mem", type=int, default=1024,
                    help="GDAL warp memory limit, MB (speed only).")
    ap.add_argument("--out-dir", default="",
                    help=f"Output directory (default {OUT_DIR}).")
    ap.add_argument("--skip-ndvi", action="store_true", help="NIR stack only.")
    ap.add_argument("--no-overviews", action="store_true", help="Skip pyramid build.")
    args = ap.parse_args(filtered)

    return inventory_only(args) if args.step == "inventory" else build(args)


if __name__ == "__main__":
    sys.exit(main())
