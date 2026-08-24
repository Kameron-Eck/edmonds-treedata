r"""
╔══════════════════════════════════════════════════════════════════╗
  IMAGERY QC SUITE — every held raster, measured, after the 2026-08-23/24
  acquisition campaign.
  Edmonds Temporal Active Learning Pipeline

  WHY THIS EXISTS
  ------------------------------------------------------------------
  The campaign took the catalog from 19 entries to 36 and replaced five
  years outright. `phase4_catalog_check.py` answers "does every entry
  resolve, open, and carry the bands/CRS it claims" — a HEADER check.
  It cannot answer the questions that decide whether the new stock is
  usable for temporal canopy work:

    A  Do two acquisitions OF THE SAME YEAR land on the same ground?
       (a georegistration offset between sources is invisible per-file
       and fatal to per-crown temporal work — it moves every crown.)
    B  Is any file radiometrically broken — clipped, saturated, flat,
       or served through a stretch that destroys the DN scale?
    C  Is every "NIR" band actually NIR (and in the band order the
       engine assumes)? A swapped or aliased band silently poisons NDVI.
    D  Which same-year pairs are genuinely independent acquisitions and
       which are the same pixels twice? (the S02-vs-U02 lesson: the
       plan predicted a duplicate and measurement said otherwise.)
    E  Where are the holes? Coverage percentages hide INTERIOR gaps —
       a doughnut and a full disc can score the same number.

  Every check writes a CSV of measured numbers to phase4/qc/ and prints
  a compact verdict table. Nothing here edits the catalog or the data;
  QC measures, humans decide.

  USAGE
    py -3.12 qc/imagery_qc_suite.py all            # everything (slow; ~40 files)
    py -3.12 qc/imagery_qc_suite.py integrity      # opens/bands/crs/fill/nodata
    py -3.12 qc/imagery_qc_suite.py radiometry     # DN stats + saturation
    py -3.12 qc/imagery_qc_suite.py ndvi           # NIR identity per 4-band file
    py -3.12 qc/imagery_qc_suite.py crossreg       # same-year spatial offsets  <-- the headline
    py -3.12 qc/imagery_qc_suite.py duplication    # same-year r / HF / PSNR
    py -3.12 qc/imagery_qc_suite.py coverage       # city coverage + interior gaps
      --workers N   parallel file reads (default 4)
      --box-m M     comparison box edge in ground metres (default 200)
      --only PAT    substring filter on the file name
      --outdir DIR  default: <repo>/phase4/qc

  EXIT CODE
    0 = every check ran. 1 = at least one FAIL-grade finding (see the
    summary table). Findings are reported, never auto-fixed.
╚══════════════════════════════════════════════════════════════════╝
"""
import argparse
import csv
import datetime as dt
import json
import math
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
from rasterio import Affine
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform as warp_xy, transform_bounds
from rasterio.windows import Window, from_bounds as win_from_bounds

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "pipeline"))
sys.path.insert(0, str(SCRIPTS / "qc"))

from phase4seg import config as C          # noqa: E402
import imagery_measure as im               # noqa: E402
import phase4_catalog_check as CK          # noqa: E402

TODAY = dt.date.today().isoformat()
SAT_HI, SAT_LO = 254, 1                    # DN treated as clipped high / low
MAX_WINDOW_EDGE = 3000                     # cap the native read edge; finer rasters decimate on read
PEAK_FLOOR = 5                             # cross-registration: garbage floor on the correlation peak/mean
                                           # ratio. NOT the confidence test — agreement between sites is
                                           # (see qc_crossreg); a soft peak is normal between seasons.


# ----------------------------------------------------------------------------- inventory
def inventory(only=None):
    """Every raster this project currently claims: catalog entries + the deliberate
    non-year holdings. Superseded files are NOT stock — they are provenance."""
    roots = C.imagery_roots()
    out = []
    for e in C.YEAR_CATALOG:
        hits = [d / e["native_file"] for d in roots if (d / e["native_file"]).exists()]
        out.append(dict(key=str(e["key"]), label=e["label"], file=e["native_file"],
                        path=hits[0] if hits else None, bands_cat=e.get("bands"),
                        crs_cat=e.get("crs_epsg"), gsd_cat=e.get("gsd_cm"), kind="catalog"))
    for name, why in CK.ADOPTED_NON_YEAR.items():
        hits = [d / name for d in roots if (d / name).exists()]
        out.append(dict(key="-", label=name[:4], file=name, path=hits[0] if hits else None,
                        bands_cat=None, crs_cat=None, gsd_cat=None, kind="non-year"))
    if only:
        out = [r for r in out if only.lower() in r["file"].lower()]
    return out


def local_only(inv):
    """Drop records whose file resolves to the Drive mount.

    Reading a Drive-resident raster does not just cost time: Google Drive for desktop caches
    every byte it serves into its LOCAL cache directory, which lives on D: — the same disk that
    holds every imagery original and the repo. Measured 2026-08-24: a full-extent integrity pass
    over the four CoE 5 cm orthos (11-48 GB each, no overviews, so a decimated read touches all
    of it) drove D: free down 0.4-0.6 GB/min, about an hour from filling the disk. Those files
    are pre-campaign holdings and carry none of the new-copy risk, so the honest trade is to
    measure what is on local disk and SAY which files were skipped.

    The hazard is specific to FULL-EXTENT reads (integrity, coverage). The windowed checks —
    crossreg, duplication, ndvi, radiometry, separability — touch a few hundred MB per file and
    are safe on Drive-resident rasters; killing the integrity pass alone took D: free from
    24.8 GB back to 36.2 GB in minutes. So use this flag for the full-extent checks, not as a
    blanket rule."""
    keep = [r for r in inv if r["path"] is not None and str(r["path"]).upper().startswith("D:")]
    skipped = [r["file"] for r in inv if r not in keep]
    if skipped:
        print(f"  --local-only: skipping {len(skipped)} file(s) resolving to the Drive mount "
              f"(cache pressure on D:): {', '.join(sorted(skipped)[:8])}"
              + (" ..." if len(skipped) > 8 else ""))
    return keep


def year_of(key: str) -> str:
    return key[:4] if key[:4].isdigit() else "-"


def same_year_pairs(inv):
    """[(a, b)] for every pair of CATALOG entries sharing a calendar year."""
    by = {}
    for r in inv:
        if r["kind"] != "catalog" or r["path"] is None:
            continue
        by.setdefault(year_of(r["key"]), []).append(r)
    pairs = []
    for y, rows in sorted(by.items()):
        rows = sorted(rows, key=lambda r: r["file"])
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                pairs.append((rows[i], rows[j]))
    return pairs


# ----------------------------------------------------------------------------- shared sampling
def _read_retry(src, band, window, out_shape, attempts=4):
    """Windowed read with backoff. The data plane is a FUSE mount (Google Drive): under
    concurrent load a read can fail transiently with RasterioIOError even though the file is
    perfectly good — observed 2026-08-24 with several QC jobs reading G: at once. Retrying is
    correct here; failing the measurement would report a data problem that does not exist."""
    import time
    for i in range(attempts):
        try:
            return src.read(band, window=window, out_shape=out_shape)
        except Exception:
            if i == attempts - 1:
                raise
            time.sleep(1.5 * (i + 1))


def common_grid_pair(pa: Path, pb: Path, lon: float, lat: float, box_m: float, band=1):
    """Both files resampled onto ONE grid (the coarser true GSD, in B's CRS) so anything
    measured between them is measured on common footing — the campaign's standing lesson
    (IMAGERY_FACTS 10.1 / 10.14: metrics read on processed copies flatter the copy)."""
    with rasterio.open(pa) as a, rasterio.open(pb) as b:
        ga, _ = im.true_gsd_cm(a)
        gb, _ = im.true_gsd_cm(b)
        g = max(ga, gb) / 100.0                        # common ground metres/px
        px_b = float(b.res[0]) * (g / (gb / 100.0))    # that ground size in B's CRS units
        xs, ys = warp_xy("EPSG:4326", b.crs, [lon], [lat])
        n = int(box_m / g)
        n -= n % 16
        if n < 64:
            return None, None, g
        tr = from_origin(xs[0] - n * px_b / 2, ys[0] + n * px_b / 2, px_b, px_b)
        bounds = (tr.c, tr.f - n * px_b, tr.c + n * px_b, tr.f)

        def grab(src):
            # Window-read THEN reproject the array. Handing rasterio.band() straight to
            # reproject lets GDAL choose the source extent, and on a 100k x 140k ortho read
            # over the Drive mount that raises "Chunk and warp failed" (2026-08-24). Reading
            # the ~n-pixel window first bounds the work to the box we actually asked for.
            sb = transform_bounds(b.crs, src.crs, *bounds)
            win = win_from_bounds(*sb, transform=src.transform).round_offsets().round_lengths()
            c0, r0 = int(win.col_off) - 2, int(win.row_off) - 2
            cw, rh = int(win.width) + 4, int(win.height) + 4
            c0, r0 = max(0, c0), max(0, r0)
            cw, rh = min(cw, src.width - c0), min(rh, src.height - r0)
            if cw < 2 or rh < 2:
                return None
            w2 = Window(c0, r0, cw, rh)
            dec = max(1, int(max(cw, rh) / MAX_WINDOW_EDGE))
            oh, ow = max(1, rh // dec), max(1, cw // dec)
            A = _read_retry(src, min(band, src.count), w2, (oh, ow)).astype(np.float32)
            src_tr = src.window_transform(w2) * Affine.scale(cw / ow, rh / oh)
            dst = np.zeros((n, n), dtype=np.float32)
            reproject(A, dst, src_transform=src_tr, src_crs=src.crs,
                      dst_transform=tr, dst_crs=b.crs, resampling=Resampling.average)
            return dst
        ga_, gb_ = grab(a), grab(b)
        if ga_ is None or gb_ is None:
            return None, None, g
        return ga_, gb_, g


def phase_shift(a: np.ndarray, b: np.ndarray):
    """Sub-pixel (dx, dy) of a relative to b, plus the correlation peak sharpness.
    Same estimator as imagery_measure.band_registration_px — reused so a cross-FILE
    offset and a cross-BAND offset are never measured two different ways."""
    a = a.astype(np.float32) - a.mean()
    b = b.astype(np.float32) - b.mean()
    if a.std() < 1e-6 or b.std() < 1e-6:
        return None
    win = np.hanning(a.shape[0])[:, None] * np.hanning(a.shape[1])[None, :]
    F = np.fft.fft2(a * win) * np.conj(np.fft.fft2(b * win))
    F /= np.maximum(np.abs(F), 1e-9)
    c = np.fft.ifft2(F).real
    py, px = np.unravel_index(np.argmax(c), c.shape)
    h, w = c.shape

    def par(v_m, v_0, v_p):
        d = v_m - 2 * v_0 + v_p
        return 0.0 if abs(d) < 1e-12 else 0.5 * (v_m - v_p) / d
    dy = py + par(c[(py - 1) % h, px], c[py, px], c[(py + 1) % h, px])
    dx = px + par(c[py, (px - 1) % w], c[py, px], c[py, (px + 1) % w])
    if dy > h / 2:
        dy -= h
    if dx > w / 2:
        dx -= w
    peak = float(c[py, px])
    ring = float(np.mean(np.abs(c))) + 1e-12
    return float(dx), float(dy), round(peak / ring, 1)


def write_csv(rows, path: Path, cols=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    cols = cols or list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return path


def _run(fn, items, workers):
    out = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for r in pool.map(fn, items):
            if isinstance(r, list):
                out.extend(r)
            elif r:
                out.append(r)
    return out


# ----------------------------------------------------------------------------- QC 1: integrity
def qc_integrity(inv, args):
    """Header truth + payload truth: does the file open, carry what the catalog claims,
    and contain data that varies? Extends catalog_check with nodata/zero fraction and a
    dtype/overview census (a missing overview pyramid is a silent 10x cost at tiling time)."""
    def one(r):
        row = dict(file=r["file"], key=r["key"], kind=r["kind"], status="OK", problems="")
        if r["path"] is None:
            row.update(status="FAIL", problems="NOT FOUND in any imagery root")
            return row
        p = r["path"]
        probs = []
        try:
            with rasterio.open(p) as ds:
                gsd, unit = im.true_gsd_cm(ds)
                row.update(bytes=p.stat().st_size, width=ds.width, height=ds.height,
                           bands=ds.count, dtype=ds.dtypes[0], epsg=ds.crs.to_epsg(),
                           units=unit, true_gsd_cm=round(gsd, 3),
                           overviews=len(ds.overviews(1)), nodata=ds.nodata)
                if r["bands_cat"] and ds.count != r["bands_cat"]:
                    probs.append(f"bands {ds.count} != catalog {r['bands_cat']}")
                if r["crs_cat"] and ds.crs.to_epsg() != r["crs_cat"]:
                    probs.append(f"EPSG {ds.crs.to_epsg()} != catalog {r['crs_cat']}")
                if r["gsd_cat"] and abs(gsd - r["gsd_cat"]) > max(0.6, 0.03 * r["gsd_cat"]):
                    probs.append(f"true GSD {gsd:.2f} != catalog {r['gsd_cat']}")
                if not ds.overviews(1):
                    probs.append("NO OVERVIEWS (decimated reads will touch every byte)")
                flat, val, how = CK._constant_fill(ds)
                row["fill"] = f"constant={val}" if flat else "varies"
                if flat:
                    probs.append(f"CONSTANT FILL ({val}) [{how}]")
                # payload census on a decimated full-extent read of band 1
                dec = max(1, int(max(ds.width, ds.height) / 2048))
                a = ds.read(1, out_shape=(max(1, ds.height // dec), max(1, ds.width // dec)))
                row["zero_frac"] = round(float((a == 0).mean()), 4)
                row["unique_b1"] = int(np.unique(a).size)
                if row["unique_b1"] < 16:
                    probs.append(f"only {row['unique_b1']} distinct DNs in band 1")
        except Exception as ex:
            probs.append(f"OPEN/READ FAILED: {type(ex).__name__}: {ex}")
        row["problems"] = "; ".join(probs)
        row["status"] = "FAIL" if any("FAILED" in x or "CONSTANT" in x or "!=" in x for x in probs) else ("WARN" if probs else "OK")
        return row
    rows = _run(one, inv, args.workers)
    write_csv(rows, args.outdir / f"imagery_qc_integrity_{TODAY}.csv")
    for r in rows:
        if r["status"] != "OK":
            print(f"  {r['status']:4s} {r['file']:30s} {r['problems'][:110]}")
    print(f"  integrity: {sum(1 for r in rows if r['status']=='OK')}/{len(rows)} clean")
    return rows


# ----------------------------------------------------------------------------- QC 2: radiometry
def qc_radiometry(inv, args):
    """DN health at the five Method_Provenance sites: per-band mean/std, clipped-high and
    clipped-low fractions, and distribution entropy. A served stretch (or a JPEG-cache
    re-encode) shows up as saturation at both ends and collapsed entropy."""
    def one(r):
        if r["path"] is None:
            return []
        out = []
        try:
            with rasterio.open(r["path"]) as ds:
                for site, (lon, lat) in im.SITES.items():
                    win = im._window_at(ds, lon, lat, 512)
                    if win is None:
                        continue
                    A = ds.read(window=win)
                    if A.size == 0:
                        continue
                    row = dict(file=r["file"], key=r["key"], site=site, bands=ds.count)
                    for b in range(min(4, A.shape[0])):
                        x = A[b].astype(np.float32)
                        h = np.bincount(A[b].ravel().astype(np.uint8), minlength=256).astype(np.float64)
                        p = h / max(h.sum(), 1)
                        ent = float(-(p[p > 0] * np.log2(p[p > 0])).sum())
                        row[f"b{b+1}_mean"] = round(float(x.mean()), 2)
                        row[f"b{b+1}_std"] = round(float(x.std()), 2)
                        row[f"b{b+1}_sat_hi"] = round(float((A[b] >= SAT_HI).mean()), 4)
                        row[f"b{b+1}_sat_lo"] = round(float((A[b] <= SAT_LO).mean()), 4)
                        row[f"b{b+1}_entropy"] = round(ent, 2)
                    flags = []
                    for b in range(min(4, A.shape[0])):
                        if row.get(f"b{b+1}_sat_hi", 0) > 0.05:
                            flags.append(f"b{b+1} {row[f'b{b+1}_sat_hi']*100:.0f}% clipped high")
                        if row.get(f"b{b+1}_entropy", 8) < 3.0:
                            flags.append(f"b{b+1} entropy {row[f'b{b+1}_entropy']}")
                    row["flags"] = "; ".join(flags)
                    out.append(row)
        except Exception as ex:
            out.append(dict(file=r["file"], key=r["key"], site="-", flags=f"ERROR {type(ex).__name__}: {ex}"))
        return out
    rows = _run(one, inv, args.workers)
    write_csv(rows, args.outdir / f"imagery_qc_radiometry_{TODAY}.csv")
    flagged = [r for r in rows if r.get("flags")]
    for r in flagged[:25]:
        print(f"  FLAG {r['file']:30s} {r['site']:14s} {r['flags'][:80]}")
    print(f"  radiometry: {len(rows)} file-site rows, {len(flagged)} flagged")
    return rows


# ----------------------------------------------------------------------------- QC 3: NIR identity
def qc_ndvi(inv, args):
    """Is band 4 NIR, and is the band ORDER what the engine assumes (R,G,B,NIR)?
    Test: NDVI at a forest site must exceed NDVI at parking, and healthy conifer NDVI
    must be high. If bands are swapped the ordering collapses or inverts."""
    rows = []
    for r in inv:
        if r["path"] is None:
            continue
        try:
            with rasterio.open(r["path"]) as ds:
                if ds.count < 4:
                    continue
                row = dict(file=r["file"], key=r["key"], bands=ds.count)
                vals = {}
                for site in ("S1_forest_nw", "S4_forest_s", "S2_parking", "S3_residential"):
                    lon, lat = im.SITES[site]
                    win = im._window_at(ds, lon, lat, 512)
                    if win is None:
                        continue
                    A = ds.read(window=win).astype(np.float32)
                    red, nir = A[0], A[3]
                    ndvi = (nir - red) / np.maximum(nir + red, 1e-6)
                    vals[site] = float(np.median(ndvi))
                    row[f"ndvi_{site}"] = round(vals[site], 3)
                    row[f"corr_b4_b1_{site}"] = round(float(np.corrcoef(A[3].ravel(), A[0].ravel())[0, 1]), 3)
                fo = [vals[s] for s in ("S1_forest_nw", "S4_forest_s") if s in vals]
                pk = [vals[s] for s in ("S2_parking",) if s in vals]
                probs = []
                if fo and pk and min(fo) <= max(pk):
                    probs.append(f"forest NDVI {min(fo):.2f} NOT above parking {max(pk):.2f} — band order suspect")
                if fo and max(fo) < 0.25:
                    probs.append(f"forest NDVI only {max(fo):.2f} — band 4 may not be NIR")
                row["verdict"] = "FAIL" if probs else "OK"
                row["problems"] = "; ".join(probs)
                rows.append(row)
        except Exception as ex:
            rows.append(dict(file=r["file"], key=r["key"], verdict="ERROR", problems=f"{type(ex).__name__}: {ex}"))
    write_csv(rows, args.outdir / f"imagery_qc_ndvi_{TODAY}.csv")
    for r in rows:
        mark = " <-- " + r["problems"][:70] if r["verdict"] != "OK" else ""
        print(f"  {r['verdict']:5s} {r['file']:30s} forest {r.get('ndvi_S1_forest_nw','-')}/"
              f"{r.get('ndvi_S4_forest_s','-')} parking {r.get('ndvi_S2_parking','-')}{mark}")
    return rows


# ----------------------------------------------------------------------------- QC 4: cross-registration
def qc_crossreg(inv, args):
    """THE HEADLINE CHECK. For every pair of acquisitions sharing a calendar year, measure
    the spatial offset between them on a common grid at each site. Per-crown temporal work
    assumes a crown polygon drawn on 2020 lands on the same trees in 2016 and 2024; an
    inter-source offset breaks that silently and is invisible in any single-file metric.
    Reported in ground metres, with the correlation peak ratio as a confidence guard."""
    pairs = same_year_pairs(inv)

    def one(pr):
        a, b = pr
        out = []
        for site, (lon, lat) in im.SITES.items():
            try:
                A, B, g = common_grid_pair(a["path"], b["path"], lon, lat, args.box_m)
                if A is None or A.std() < 1e-6 or B.std() < 1e-6:
                    continue
                ok = (A > 0) & (B > 0)
                if ok.mean() < 0.5:
                    continue
                sh = phase_shift(A, B)
                if sh is None:
                    continue
                dx, dy, peak = sh
                out.append(dict(year=year_of(a["key"]), a=a["file"], b=b["file"], site=site,
                                common_px_cm=round(g * 100, 2), dx_px=round(dx, 3), dy_px=round(dy, 3),
                                offset_px=round(math.hypot(dx, dy), 3),
                                offset_m=round(math.hypot(dx, dy) * g, 3), peak_ratio=peak,
                                overlap=round(float(ok.mean()), 3)))
            except Exception as ex:
                out.append(dict(year=year_of(a["key"]), a=a["file"], b=b["file"], site=site,
                                note=f"ERROR {type(ex).__name__}: {ex}"))
        return out
    rows = _run(one, pairs, args.workers)
    write_csv(rows, args.outdir / f"imagery_qc_crossreg_{TODAY}.csv")

    # Per-pair summary. CONFIDENCE COMES FROM AGREEMENT BETWEEN SITES, not from the peak
    # height alone (2026-08-24, learned the hard way):
    #   * A first pass gated on peak ratio >= 50 and threw away 54 of 100 measurements —
    #     including parking and residential sites, whose peaks are legitimately soft whenever
    #     the two acquisitions differ in season or resolution. Peak height measures how ALIKE
    #     two images are; it does not measure whether the offset is right.
    #   * What actually separates signal from garbage is whether the five sites AGREE. A real
    #     georeferencing offset is systematic: 2024 read dx -14.31/-14.37/-14.67/-14.71/-14.73
    #     px at five scattered sites (MAD 0.03 m). A wrong correlation peak is idiosyncratic:
    #     the 18-24 m forest outliers agreed with nothing.
    # So: keep every measurement above a garbage floor, report the median offset AND the spread,
    # and let the spread decide whether the pair gets a verdict at all.
    summ = {}
    for r in rows:
        if r.get("offset_m") is None or (r.get("peak_ratio") or 0) < PEAK_FLOOR:
            continue
        summ.setdefault((r["year"], r["a"], r["b"]), []).append(r)

    def mad(v):
        v = np.asarray(v, dtype=float)
        return float(np.median(np.abs(v - np.median(v))))

    out = []
    for (y, a, b), rs in sorted(summ.items()):
        offs = [r["offset_m"] for r in rs]
        med = float(np.median(offs))
        # spread of the OFFSET VECTOR across sites, in ground metres
        gm = float(np.median([r["common_px_cm"] for r in rs])) / 100.0
        sx, sy = mad([r["dx_px"] for r in rs]) * gm, mad([r["dy_px"] for r in rs]) * gm
        spread = round(max(sx, sy), 3)
        n = len(rs)
        if n < 3:
            grade = "THIN"                       # not enough sites to tell systematic from noise
        elif spread > max(0.30, 0.25 * med):     # sites disagree -> no reliable offset to report
            grade = "NOISY"
        else:
            grade = "OK" if med <= 1.0 else ("WARN" if med <= 3.0 else "FAIL")
        out.append(dict(year=y, a=a, b=b, n_sites=n, median_offset_m=round(med, 3),
                        site_spread_m=spread, max_offset_m=round(max(offs), 3),
                        median_peak=round(float(np.median([r["peak_ratio"] for r in rs])), 1),
                        grade=grade))
        print(f"  {grade:5s} {y}  {a[:26]:26s} vs {b[:26]:26s}  median {med:6.2f} m  "
              f"spread {spread:5.2f} m  (n={n})")
    write_csv(out, args.outdir / f"imagery_qc_crossreg_summary_{TODAY}.csv")
    ng = sum(1 for r in out if r["grade"] in ("NOISY", "THIN"))
    print(f"  cross-registration: {len(out)} same-year pairs; {len(out)-ng} with a verdict, "
          f"{ng} inconclusive (reported, not averaged away)")
    return out


# ----------------------------------------------------------------------------- QC 5: duplication
def qc_duplication(inv, args):
    """Which same-year pairs are two views and which are the same pixels twice?
    r > 0.99 on a common grid = the same acquisition served twice (the campaign measured
    0.98-0.997 for known same-flight pairs and 0.847 for the genuinely distinct 2002s)."""
    pairs = same_year_pairs(inv)

    def one(pr):
        a, b = pr
        try:
            vals = []
            for site, (lon, lat) in im.SITES.items():
                c = im.compare_to_held_arrays(a["path"], b["path"], lon, lat, args.box_m)
                if c.get("pearson_r") is not None:
                    vals.append(c)
            if not vals:
                return None
            r_ = float(np.median([v["pearson_r"] for v in vals]))
            hf = float(np.median([v["hf_ratio_new_over_held"] for v in vals]))
            ps = float(np.median([v["psnr_db"] for v in vals]))
            verdict = ("SAME PIXELS (duplicate)" if r_ > 0.99 else
                       "same flight, different serving" if r_ > 0.96 else
                       "INDEPENDENT acquisitions")
            print(f"  {year_of(a['key'])}  {a['file'][:26]:26s} vs {b['file'][:26]:26s}  r={r_:.3f}  HF={hf:.2f}  {verdict}")
            return dict(year=year_of(a["key"]), a=a["file"], b=b["file"], n_sites=len(vals),
                        pearson_r=round(r_, 4), hf_ratio_a_over_b=round(hf, 3),
                        psnr_db=round(ps, 2), verdict=verdict)
        except Exception as ex:
            return dict(year=year_of(a["key"]), a=a["file"], b=b["file"], verdict=f"ERROR {type(ex).__name__}: {ex}")
    rows = _run(one, pairs, args.workers)
    write_csv(rows, args.outdir / f"imagery_qc_duplication_{TODAY}.csv")
    print(f"  duplication: {len(rows)} pairs")
    return rows


# ----------------------------------------------------------------------------- QC 6: coverage + interior gaps
def qc_coverage(inv, args):
    """Coverage percentages hide INTERIOR holes. This walks a decimated valid-data mask and
    reports the largest hole that is NOT connected to the raster edge — an interior gap is a
    served-tile failure; an edge gap is geography (Puget Sound)."""
    def one(r):
        if r["path"] is None:
            return None
        try:
            with rasterio.open(r["path"]) as ds:
                dec = max(1, int(max(ds.width, ds.height) / 1500))
                a = ds.read(1, out_shape=(max(1, ds.height // dec), max(1, ds.width // dec)))
                # "valid" cannot just mean non-zero. Scanned historical mosaics pad with WHITE,
                # not black: 1936_king_pan.tif is 37% value 0, 38% value 253 and 15% value 255 —
                # only ~10% real photographic content — and a >0 test scores it a near-perfect
                # pass (found by QC, 2026-08-24). Treat any value that dominates the frame as
                # padding: a real ortho does not spend a quarter of its pixels on one DN.
                # Padding is an EXTREME value that dominates, not merely a common one. A first
                # cut flagged any DN over 20% of the frame and promptly mis-read 2009_snoh, whose
                # most common DN is 40 — a legitimate dark-vegetation tone, 20.3% of pixels —
                # inventing a 41 ha "interior gap" that does not exist. Requiring near-black or
                # near-white keeps 1936's white padding (253/255) and ordinary nodata (0) while
                # leaving real mid-tones alone.
                counts = np.bincount(a.ravel().astype(np.uint8), minlength=256)
                dominant = np.flatnonzero(counts > 0.20 * a.size).tolist()
                pad = {v for v in dominant if v <= 2 or v >= 250}
                pad.add(0)
                valid = ~np.isin(a, list(pad))
                row_pad = sorted(pad)
                px_m = im.true_gsd_cm(ds)[0] / 100.0 * dec
                # flood-fill the invalid region from the border: what remains is interior
                inv_mask = ~valid
                h, w = inv_mask.shape
                seen = np.zeros_like(inv_mask)
                stack = [(0, c) for c in range(w) if inv_mask[0, c]] + \
                        [(h - 1, c) for c in range(w) if inv_mask[h - 1, c]] + \
                        [(r_, 0) for r_ in range(h) if inv_mask[r_, 0]] + \
                        [(r_, w - 1) for r_ in range(h) if inv_mask[r_, w - 1]]
                for p in stack:
                    seen[p] = True
                while stack:
                    y, x = stack.pop()
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < h and 0 <= nx < w and inv_mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
                interior = inv_mask & ~seen
                n_int = int(interior.sum())
                row = dict(file=r["file"], key=r["key"], valid_frac=round(float(valid.mean()), 4),
                           padding_values=";".join(str(v) for v in row_pad),
                           edge_gap_frac=round(float((inv_mask & seen).mean()), 4),
                           interior_gap_frac=round(float(interior.mean()), 5),
                           interior_gap_ha=round(n_int * px_m * px_m / 1e4, 2),
                           decimation=dec)
                row["grade"] = "OK" if row["interior_gap_ha"] < 1.0 else ("WARN" if row["interior_gap_ha"] < 25 else "FAIL")
                return row
        except Exception as ex:
            return dict(file=r["file"], key=r["key"], grade="ERROR", note=f"{type(ex).__name__}: {ex}")
    rows = _run(one, inv, args.workers)
    write_csv(rows, args.outdir / f"imagery_qc_coverage_{TODAY}.csv")
    for r in sorted(rows, key=lambda x: -(x.get("interior_gap_ha") or 0))[:12]:
        print(f"  {r.get('grade','?'):5s} {r['file']:30s} valid {r.get('valid_frac','-')} "
              f"interior gap {r.get('interior_gap_ha','-')} ha")
    return rows


CHECKS = {"integrity": qc_integrity, "radiometry": qc_radiometry, "ndvi": qc_ndvi,
          "crossreg": qc_crossreg, "duplication": qc_duplication, "coverage": qc_coverage}


def main():
    argv = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("check", choices=list(CHECKS) + ["all"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--box-m", type=float, default=200.0)
    ap.add_argument("--only")
    ap.add_argument("--local-only", action="store_true",
                    help="measure only files on local disk; skip Drive-resident ones (see local_only)")
    ap.add_argument("--outdir", type=Path, default=SCRIPTS.parent / "phase4" / "qc")
    args = ap.parse_args(argv)
    args.outdir = Path(args.outdir)
    args.outdir.mkdir(parents=True, exist_ok=True)

    inv = inventory(args.only)
    if args.local_only:
        inv = local_only(inv)
    print(f"IMAGERY QC SUITE — {len(inv)} rasters "
          f"({sum(1 for r in inv if r['kind']=='catalog')} catalog, "
          f"{sum(1 for r in inv if r['kind']=='non-year')} non-year), outdir {args.outdir}")
    missing = [r["file"] for r in inv if r["path"] is None]
    if missing:
        print(f"  NOT ON THIS MACHINE ({len(missing)}): {', '.join(missing[:6])}")

    todo = list(CHECKS) if args.check == "all" else [args.check]
    results = {}
    for name in todo:
        print(f"\n--- {name} " + "-" * (60 - len(name)))
        try:
            results[name] = CHECKS[name](inv, args)
        except Exception:
            traceback.print_exc()
            results[name] = [{"grade": "ERROR"}]
    bad = sum(1 for rows in results.values() for r in rows
              if str(r.get("status") or r.get("grade") or r.get("verdict") or "").startswith(("FAIL", "ERROR")))
    (args.outdir / f"imagery_qc_run_{TODAY}.json").write_text(json.dumps(
        {"date": TODAY, "checks": todo, "n_rasters": len(inv),
         "fail_or_error_rows": bad}, indent=1), encoding="utf-8")
    print(f"\n{'=' * 66}\nQC complete — {bad} FAIL/ERROR rows across {len(todo)} checks. CSVs in {args.outdir}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
