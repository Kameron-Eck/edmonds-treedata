r"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — QC: WHY is upland forest missed?  (under-prediction autopsy)
  Edmonds Temporal Active Learning Pipeline

  WHY
    The independent C-CAP score (phase4_qc_indep.py) puts upland-forest recall
    at ~0.68 — the model MISSES ~32% of real forest, the ~94% error component.
    This tool opens up those misses. Over every C-CAP upland-forest pixel it
    splits RECALLED (TP) vs MISSED (FN) and compares their distributions of:
      • model confidence (prob)  — are misses confident (structural / out-of-
        distribution) or near-threshold (a cheap threshold fix)?
      • RGB brightness + saturation — sensor / radiometric explanation (washed-
        out or dark stands the conifer-trained model never saw)
      • NDVI + GRVI (greenness)   — deciduous / senescent / off-spectral misses
      • CHM height                — are misses real tall trees, not scrub?
    It also writes a COARSE FN-density raster so the worst-missed stands can be
    located and staged as positive training sites (make_positive_site.py).

    C-CAP is EVALUATION ONLY here — it locates and characterises misses; it is
    never a training label. (Portability: elsewhere use hand-drawn forest polys.)

  PRODUCES (phase4/qc/):
    forest_miss_{year}.txt   TP-vs-FN stat table + auto-diagnosis
    forest_miss_{year}.csv   machine-readable stats (for the write-up)
    forest_miss_{year}.png   overlaid TP/FN histograms (prob, NDVI, brightness)
    forest_miss_density_{year}.tif   coarse FN-fraction raster (stand locator)

  USAGE (local Windows or Colab; torch-free; rasterio auto-installs):
    py -3.12 phase4_qc_forest_misses.py --year 2016 --ref D:\...\ccap_2016_hires_lc.tif
    py -3.12 phase4_qc_forest_misses.py --year 2016 --ref <ccap.tif> --thresh 0.30
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import csv
import datetime as _dt
import importlib
import subprocess
import sys
from pathlib import Path


def _pip(spec):
    print(f"  • installing {spec} …")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", spec], check=True)

for _imp, _spec in [("rasterio", "rasterio"), ("numpy", "numpy"), ("matplotlib", "matplotlib")]:
    try:
        importlib.import_module(_imp)
    except ImportError:
        _pip(_spec)

import numpy as np
import rasterio
import rasterio.warp
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.windows import Window
from rasterio.transform import Affine
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE

_LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")
_DRIVE_IMG = BASE / "Full_Image" / "Pipeline Imagery"
IMAGERY_DIRS = [d for d in (_LOCAL_IMG, _DRIVE_IMG) if d.exists()] or [_DRIVE_IMG]

QC_DIR   = BASE / "phase4" / "qc"
MASKS    = BASE / "phase4" / "masks"
EVAL_CSV = BASE / "phase4" / "eval" / "semantic_eval_report.csv"
LOGS_DIR = BASE / "phase4" / "logs"
CHM_NAME = "lidar_snoh_chm.tif"
CHM_DN_PER_M = 1.0 / 0.2

# year(label) → (imagery file, NIR band or None). NIR only on the _rgbi orthos.
IMG_CATALOG = {
    "2000":  ("2000_king_rgb.tif",  None),
    "2002":  ("2002_king_rgb.tif",  None),
    "2005":  ("2005_king_rgb.tif",  None),
    "2007":  ("2007_king_rgb.tif",  None),
    "2009":  ("2009_king_rgb.tif",  None),
    "2012":  ("2012_king_rgb.tif",  None),
    "2013":  ("2013_king_rgb.tif",  None),
    "2015":  ("2015_king_rgb.tif",  None),
    "2016":  ("2016_snoh_rgbi.tif", 4),
    "2017":  ("2017_king_rgb.tif",  None),
    "2019":  ("2019_king_rgb.tif",  None),
    # 2020 is the ANCHOR year. It was missing from this catalog, so any attempt to
    # autopsy the Phase-3 mask died on a KeyError and wrote nothing — a silent
    # failure of exactly the kind this workstream exists to remove.
    "2020":  ("2020_coe_rgb.tif",   None),
    "2019n": ("2019_naip_rgbi.tif", 4),
    "2021":  ("2021_king_rgb.tif",  None),
    "2021s": ("2021_snoh_rgbi.tif", 4),
    "2023n": ("2023_naip_rgbi.tif", 4),
    "2023":  ("2023_king_rgb.tif",  None),
}
# GSD (cm) + sensor per label — for the cross-sensor failure table.
GSD_CM = {"2000": 59.7, "2002": 59.7, "2005": 29.9, "2007": 29.9, "2009": 29.9,
          "2012": 14.9, "2013": 14.9, "2015": 14.9, "2016": 50.0, "2017": 7.5,
          "2019": 14.9, "2019n": 60.0, "2020": 7.5, "2021": 14.9, "2021s": 50.0, "2023n": 60.0,
          "2023": 14.9}
def sensor_of(label):
    return IMG_CATALOG[label][0].split("_")[1]   # king / snoh / naip

# default C-CAP upland-forest codes (hi-res: 11 Upland Forest; regional: 9/10/11)
DEFAULT_FOREST_CODES = [9, 10, 11]


def resolve_img(fname):
    for d in IMAGERY_DIRS:
        p = d / fname
        if p.exists():
            return p
    raise FileNotFoundError(f"{fname} not found in {[str(d) for d in IMAGERY_DIRS]}")


def resolve_chm():
    for d in IMAGERY_DIRS + [_DRIVE_IMG]:
        p = d / CHM_NAME
        if p.exists():
            return p
    return None


def deployed_threshold(year):
    if not EVAL_CSV.exists():
        return None
    rows = [r for r in csv.DictReader(open(EVAL_CSV, encoding="utf-8"))
            if r.get("year") == str(year) and r.get("scope", "").upper() == "OVERALL"]
    for ch in ("rgb+chm", "rgb+struct", "rgb"):
        for r in rows:
            if r.get("channels") == ch:
                for key in ("op_thresh", "best_f1_thresh"):
                    v = r.get(key, "").strip()
                    if v:
                        return float(v)
    return None


def dn_to_height_m(dn):
    h = (dn.astype(np.float32) - 1.0) / CHM_DN_PER_M
    h[dn == 0] = np.nan
    return h


# ── streaming accumulator (mean/std via sums; percentiles via histograms) ──────
# Height bands for the stratified-recall table (metres, CHM DN-derived).
# Deliberately narrow through 5-20 m, where the P1c miss concentrates.
HEIGHT_BINS = [0, 2, 5, 10, 15, 20, 25, 30, 100]

METRICS = ["prob", "R", "G", "B", "brightness", "saturation", "NDVI", "GRVI", "height_m"]
HIST_SPEC = {              # metric -> (lo, hi, nbins)
    "prob":       (0.0, 1.0, 50),
    "NDVI":       (-1.0, 1.0, 80),
    "brightness": (0.0, 255.0, 51),
    "height_m":   (0.0, 45.0, 45),
}


class Acc:
    def __init__(self):
        self.n = {m: 0 for m in METRICS}
        self.s = {m: 0.0 for m in METRICS}
        self.ss = {m: 0.0 for m in METRICS}
        self.hist = {m: np.zeros(HIST_SPEC[m][2] + 2, dtype=np.int64) for m in HIST_SPEC}

    def add(self, m, vals):
        v = vals[np.isfinite(vals)]
        if v.size == 0:
            return
        self.n[m] += v.size
        self.s[m] += float(v.sum())
        self.ss[m] += float((v.astype(np.float64) ** 2).sum())
        if m in HIST_SPEC:
            lo, hi, nb = HIST_SPEC[m]
            idx = np.clip(((v - lo) / (hi - lo) * nb).astype(np.int64) + 1, 0, nb + 1)
            self.hist[m] += np.bincount(idx, minlength=nb + 2)

    def mean(self, m):
        return self.s[m] / self.n[m] if self.n[m] else float("nan")

    def std(self, m):
        if not self.n[m]:
            return float("nan")
        mu = self.s[m] / self.n[m]
        return float(np.sqrt(max(self.ss[m] / self.n[m] - mu * mu, 0.0)))

    def pct(self, m, p):
        if m not in self.hist or self.hist[m].sum() == 0:
            return float("nan")
        lo, hi, nb = HIST_SPEC[m]
        h = self.hist[m][1:nb + 1]                    # drop under/overflow for centres
        c = np.cumsum(h)
        tot = c[-1] if c[-1] else 1
        i = int(np.searchsorted(c, p * tot))
        return lo + (i + 0.5) * (hi - lo) / nb


def analyse(year, ref_path, prob_path, thresh, forest_codes, block_rows, coarse,
            stable_path=None):
    img_file, nir_b = IMG_CATALOG[year]
    img_path = resolve_img(img_file)
    chm_path = resolve_chm()
    print(f"[forest-miss] year={year} thresh={thresh}")
    print(f"    imagery = {img_path}")
    print(f"    prob    = {prob_path}")
    print(f"    ref     = {ref_path}  (forest codes {forest_codes})")
    print(f"    chm     = {chm_path}")
    if stable_path:
        print(f"    stable  = {stable_path}  (forest must also be forest here → isolates sensor)")

    thr_u8 = thresh * 254.0
    tp, fn = Acc(), Acc()
    h_tp = np.zeros(len(HEIGHT_BINS) - 1, dtype=np.int64)
    h_fn = np.zeros(len(HEIGHT_BINS) - 1, dtype=np.int64)
    n_tp = n_fn = forest_total = 0

    with rasterio.open(img_path) as img, rasterio.open(prob_path) as prob:
        if (img.width, img.height) != (prob.width, prob.height):
            raise ValueError(f"imagery {img.width}x{img.height} != prob "
                             f"{prob.width}x{prob.height} — expected same grid")
        H, W = img.height, img.width
        # coarse FN-density grid
        ncr = (H + coarse - 1) // coarse
        ncc = (W + coarse - 1) // coarse
        c_forest = np.zeros((ncr, ncc), dtype=np.int64)
        c_fn = np.zeros((ncr, ncc), dtype=np.int64)
        col_starts = np.arange(0, W, coarse)

        ref_ds = rasterio.open(ref_path)
        chm_ds = rasterio.open(chm_path) if chm_path else None
        stable_ds = rasterio.open(stable_path) if stable_path else None
        ref_vrt = WarpedVRT(ref_ds, crs=prob.crs, transform=prob.transform,
                            width=W, height=H, resampling=Resampling.nearest)
        chm_vrt = (WarpedVRT(chm_ds, crs=prob.crs, transform=prob.transform,
                             width=W, height=H, resampling=Resampling.nearest,
                             src_nodata=0, nodata=0) if chm_ds else None)
        stable_vrt = (WarpedVRT(stable_ds, crs=prob.crs, transform=prob.transform,
                                width=W, height=H, resampling=Resampling.nearest)
                      if stable_ds else None)

        n_blocks = (H + block_rows - 1) // block_rows
        for bi, row0 in enumerate(range(0, H, block_rows)):
            rows = min(block_rows, H - row0)
            win = Window(0, row0, W, rows)

            bands = [1, 2, 3, nir_b] if nir_b else [1, 2, 3]
            arr = img.read(bands, window=win).astype(np.float32)
            r, g, b = arr[0], arr[1], arr[2]
            cover = (r + g + b) > 0
            pr = prob.read(1, window=win)
            rc = ref_vrt.read(1, window=win)

            forest = cover & (pr != 255) & np.isin(rc, forest_codes)
            if stable_vrt is not None:
                forest &= np.isin(stable_vrt.read(1, window=win), forest_codes)
            if not forest.any():
                if bi % 4 == 0 or bi == n_blocks - 1:
                    print(f"    block {bi+1}/{n_blocks}", flush=True)
                continue
            is_tp = forest & (pr >= thr_u8)
            is_fn = forest & (pr < thr_u8)

            bright = (r + g + b) / 3.0
            mx = np.maximum(np.maximum(r, g), b)
            mn = np.minimum(np.minimum(r, g), b)
            sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
            ndvi = ((arr[3] - r) / (arr[3] + r + 1e-6)) if nir_b else np.full_like(r, np.nan)
            grvi = (g - r) / (g + r + 1e-6)
            hgt = dn_to_height_m(chm_vrt.read(1, window=win)) if chm_vrt else np.full_like(r, np.nan)
            prob01 = pr.astype(np.float32) / 254.0

            for acc, mask in ((tp, is_tp), (fn, is_fn)):
                if not mask.any():
                    continue
                acc.add("prob", prob01[mask]); acc.add("R", r[mask]); acc.add("G", g[mask])
                acc.add("B", b[mask]); acc.add("brightness", bright[mask])
                acc.add("saturation", sat[mask]); acc.add("NDVI", ndvi[mask])
                acc.add("GRVI", grvi[mask]); acc.add("height_m", hgt[mask])

            # HEIGHT-STRATIFIED RECALL — the 2026-08-18 P1c result is that the
            # ONE thing invariant across every year/sensor/recipe is height:
            # recalled canopy ~24 m, missed ~12 m. Mean heights show that a gap
            # exists; recall PER HEIGHT BAND shows its SHAPE, and is the only
            # way to tell a genuine fix (the curve lifts at 5-15 m) from a model
            # that merely got more liberal (the curve lifts everywhere).
            for arr, mask in ((h_tp, is_tp), (h_fn, is_fn)):
                if not mask.any():
                    continue
                hv = hgt[mask]
                hv = hv[np.isfinite(hv)]
                if hv.size:
                    idx = np.clip(np.digitize(hv, HEIGHT_BINS) - 1,
                                  0, len(HEIGHT_BINS) - 2)
                    arr += np.bincount(idx, minlength=len(HEIGHT_BINS) - 1)

            n_tp += int(is_tp.sum()); n_fn += int(is_fn.sum())
            forest_total += int(forest.sum())

            # coarse FN density (block rows align to `coarse`; reduce by blocks)
            roff = row0 // coarse
            fint = forest.astype(np.int64)
            nint = is_fn.astype(np.int64)
            row_starts = np.arange(0, rows, coarse)
            cf = np.add.reduceat(np.add.reduceat(fint, row_starts, axis=0), col_starts, axis=1)
            cn = np.add.reduceat(np.add.reduceat(nint, row_starts, axis=0), col_starts, axis=1)
            c_forest[roff:roff + cf.shape[0], :cf.shape[1]] += cf
            c_fn[roff:roff + cn.shape[0], :cn.shape[1]] += cn

            if bi % 4 == 0 or bi == n_blocks - 1:
                print(f"    block {bi+1}/{n_blocks}", flush=True)

        # How many INDEPENDENT reference cells do those px represent? The ref is
        # nearest-warped onto the (much finer) prob grid, so each ref cell is
        # replicated across many px. Counts are px; the honest N is this.
        indep_cells = _indep_cells(forest_total, prob, ref_ds)

        ref_vrt.close(); ref_ds.close()
        if chm_vrt:
            chm_vrt.close(); chm_ds.close()
        if stable_vrt is not None:
            stable_vrt.close(); stable_ds.close()
        coarse_tf = prob.transform * Affine.scale(coarse)
        coarse_crs = prob.crs

    _write_density(year, c_forest, c_fn, coarse_tf, coarse_crs, coarse)
    _report(year, ref_path, prob_path, thresh, forest_codes,
            tp, fn, n_tp, n_fn, forest_total,
            stable_path=stable_path, chm_path=chm_path, indep_cells=indep_cells,
            h_tp=h_tp, h_fn=h_fn)
    return dict(year=year, tp=tp, fn=fn, n_tp=n_tp, n_fn=n_fn, forest_total=forest_total,
                recall=(n_tp / (n_tp + n_fn) if (n_tp + n_fn) else float("nan")))


def _write_density(year, c_forest, c_fn, tf, crs, coarse, min_forest=200):
    """Coarse FN-fraction raster; nodata where a cell holds too little forest."""
    frac = np.full(c_forest.shape, -1.0, dtype=np.float32)
    ok = c_forest >= min_forest
    frac[ok] = c_fn[ok] / c_forest[ok]
    out = QC_DIR / f"forest_miss_density_{year}.tif"
    QC_DIR.mkdir(parents=True, exist_ok=True)
    prof = dict(driver="GTiff", height=frac.shape[0], width=frac.shape[1], count=1,
                dtype="float32", crs=crs, transform=tf, nodata=-1.0,
                compress="deflate", tiled=True, blockxsize=256, blockysize=256)
    with rasterio.open(out, "w", **prof) as dst:
        dst.write(frac, 1)
    print(f"[forest-miss] wrote {out}  (cell ≈ {coarse} px; FN-fraction 0..1, "
          f"nodata=-1 where <{min_forest} forest px)")
    _top_stands(year, c_forest, c_fn, tf, crs, coarse, min_forest)


def _top_stands(year, c_forest, c_fn, tf, crs, coarse, min_forest, topn=12):
    """Rank coarse cells by missed-forest AREA → a site-staging shortlist."""
    ok = c_forest >= min_forest
    if not ok.any():
        print("[forest-miss] no cells with enough forest for a stand shortlist"); return
    rr, cc = np.where(ok)
    fn = c_fn[rr, cc]; fo = c_forest[rr, cc]
    order = np.argsort(fn)[::-1][:topn]
    xs = tf.c + (cc[order] + 0.5) * tf.a
    ys = tf.f + (rr[order] + 0.5) * tf.e
    lon, lat = rasterio.warp.transform(crs, "EPSG:4326", xs.tolist(), ys.tolist())
    cell_m = abs(tf.a)                      # tf is already the coarse transform
    try:
        from pyproj import CRS as _pyCRS
        c = _pyCRS.from_user_input(crs)
        if c.is_projected:
            cell_m *= float(c.axis_info[0].unit_conversion_factor)
    except Exception:
        pass
    rows = []
    print(f"\n  TOP {topn} MISSED-FOREST STANDS (cell ≈ {cell_m:.0f} m; stage these as positive sites):")
    print("     lon         lat        missed_px   forest_px   FN_frac")
    for i, k in enumerate(order):
        fr = fn[k] / fo[k]
        print(f"    {lon[i]:>10.5f}  {lat[i]:>9.5f}   {int(fn[k]):>9,}  {int(fo[k]):>9,}   {fr:>5.2f}")
        rows.append(dict(rank=i + 1, lon=round(lon[i], 6), lat=round(lat[i], 6),
                         missed_px=int(fn[k]), forest_px=int(fo[k]), fn_frac=round(float(fr), 4)))
    stands_csv = QC_DIR / f"forest_miss_stands_{year}.csv"
    with open(stands_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["rank", "lon", "lat", "missed_px", "forest_px", "fn_frac"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"[forest-miss] wrote {stands_csv}")


def _diagnosis(tp, fn):
    lines = []
    dp = fn.mean("prob") - tp.mean("prob")
    frac_conf = (fn.hist["prob"][1:1 + 6].sum() / max(fn.hist["prob"][1:-1].sum(), 1))  # prob<0.12
    if frac_conf > 0.5:
        lines.append(f"• {100*frac_conf:.0f}% of misses have prob<0.12 → CONFIDENT misses "
                     f"(structural / out-of-distribution, NOT a threshold fix).")
    else:
        lines.append(f"• only {100*frac_conf:.0f}% of misses are deep (prob<0.12) → a chunk sit "
                     f"near threshold; lowering the operating point recovers some.")
    dn = fn.mean("NDVI") - tp.mean("NDVI")
    if np.isfinite(dn) and dn < -0.03:
        lines.append(f"• missed forest is LESS green (ΔNDVI {dn:+.3f}) → deciduous / senescent / "
                     f"off-spectral canopy the conifer-trained model under-recognises.")
    db = fn.mean("brightness") - tp.mean("brightness")
    if abs(db) > 6:
        d = "BRIGHTER (washed-out / over-exposed)" if db > 0 else "DARKER (shadowed)"
        lines.append(f"• missed forest is {d} — Δbrightness {db:+.1f} DN → a radiometric/sensor "
                     f"signature separates the misses.")
    dh = fn.mean("height_m") - tp.mean("height_m")
    if np.isfinite(dh):
        lines.append(f"• missed forest mean height {fn.mean('height_m'):.1f} m (Δ {dh:+.1f} m vs "
                     f"recalled) → {'real tall trees, not scrub' if fn.mean('height_m')>5 else 'shorter stands'}.")
    return lines


def _px_area_m2(ds):
    """Pixel area in m², honouring non-metric CRS units (e.g. EPSG:2285 = US ft)."""
    try:
        f = ds.crs.linear_units_factor[1]
    except Exception:
        f = 1.0
    return abs(ds.transform.a * ds.transform.e) * f * f


def _indep_cells(px, prob_ds, ref_ds):
    """px on the prob grid → equivalent count of native reference cells."""
    try:
        a_prob, a_ref = _px_area_m2(prob_ds), _px_area_m2(ref_ds)
        if a_prob <= 0 or a_ref <= 0:
            return float("nan")
        return px * a_prob / a_ref
    except Exception:
        return float("nan")


def _report(year, ref_path, prob_path, thresh, forest_codes, tp, fn, n_tp, n_fn, forest_total,
            stable_path=None, chm_path=None, indep_cells=float("nan"),
            h_tp=None, h_fn=None):
    recall = n_tp / (n_tp + n_fn) if (n_tp + n_fn) else float("nan")
    L = [f"FOREST-MISS AUTOPSY — year {year}  (why upland forest is under-predicted)",
         f"  ref   : {ref_path}   (forest codes {forest_codes})",
         f"  prob  : {prob_path}",
         f"  thresh: {thresh}",
         "",
         "  DENOMINATOR (every mask that narrows what is scored — read before quoting):",
         f"    forest codes   : {forest_codes}",
         f"    imagery cover  : (R+G+B) > 0            [always on]",
         f"    prob valid     : prob != 255            [always on]",
         "    stable-with    : " + (f"{stable_path}\n"
                                    "                     ^^ FOREST MUST ALSO BE FOREST HERE — this is a"
                                    " SUBSET,\n                        NOT full-forest recall. NOT comparable"
                                    " to qc_indep."
                                    if stable_path else "(none — full forest, comparable to qc_indep)"),
         f"    chm (height)   : {chm_path or '(none — height_m is nan)'}",
         "",
         f"  upland-forest px : {forest_total:,}"
         + (f"   (≈ {indep_cells:,.0f} independent {Path(str(ref_path)).name} cells)"
            if indep_cells == indep_cells else ""),
         f"  recalled (TP) : {n_tp:,}   missed (FN) : {n_fn:,}   RECALL {recall:.4f}",
         "",
         "  NOTE: px counts are on the fine prob grid; the reference is nearest-warped up,",
         "        so px are NOT independent samples. Means are unbiased; any error bar",
         "        computed from the px count is not. Use the independent-cell count.",
         "",
         f"  metric          recalled(TP)         missed(FN)          Δ(FN−TP)      n(TP/FN)",
         f"                  mean ± std           mean ± std"]
    for m in METRICS:
        tm, ts, fm, fs = tp.mean(m), tp.std(m), fn.mean(m), fn.std(m)
        d = fm - tm
        L.append(f"  {m:<13}  {tm:>7.3f} ± {ts:<7.3f}   {fm:>7.3f} ± {fs:<7.3f}   {d:>+7.3f}"
                 f"   {tp.n[m]:,}/{fn.n[m]:,}")
    if chm_path and fn.n["height_m"] < n_fn:
        L.append(f"  ^ height_m is measured ONLY where the CHM has data "
                 f"({100*fn.n['height_m']/max(n_fn,1):.0f}% of FN, "
                 f"{100*tp.n['height_m']/max(n_tp,1):.0f}% of TP) — and the CHM is ~2016,")
        L.append(f"    so height for any non-2016 year compares that year's imagery to 2016 structure.")
    # prob-depth of misses
    ph = fn.hist["prob"]; nb = HIST_SPEC["prob"][2]; core = ph[1:nb + 1]; tot = max(core.sum(), 1)
    b1 = core[:3].sum() / tot; b2 = core[3:6].sum() / tot
    thr_bin = int(np.clip(thresh * nb, 0, nb))
    b3 = core[6:thr_bin].sum() / tot
    if h_tp is not None and h_fn is not None and (h_tp.sum() + h_fn.sum()) > 0:
        L += ["", "  RECALL BY CANOPY HEIGHT (the P1c invariant, made explicit):",
              "    band        recall     recalled / missed"]
        for i in range(len(HEIGHT_BINS) - 1):
            t, f = int(h_tp[i]), int(h_fn[i])
            if t + f == 0:
                continue
            lo, hi = HEIGHT_BINS[i], HEIGHT_BINS[i + 1]
            band = f"{lo:>2}-{hi:<3}m" if hi < 100 else f"{lo:>2}+   m"
            L.append(f"    {band:<11} {t/(t+f):.4f}    {t:>13,} / {f:<13,}")
        L.append("    ^ A REAL fix lifts the 5-15 m bands. A model that merely got more")
        L.append("      liberal lifts every band (and precision falls).")
    L += ["",
          "  MISS DEPTH (model confidence on missed forest):",
          f"    prob<0.06 : {100*b1:>5.1f}%     0.06–0.12 : {100*b2:>5.1f}%     "
          f"0.12–thr : {100*b3:>5.1f}%",
          "",
          "  AUTO-DIAGNOSIS:"]
    L += ["  " + s for s in _diagnosis(tp, fn)]
    txt = "\n".join(L)
    print("\n" + txt)
    QC_DIR.mkdir(parents=True, exist_ok=True)
    (QC_DIR / f"forest_miss_{year}.txt").write_text(txt, encoding="utf-8")

    # CSV
    csvp = QC_DIR / f"forest_miss_{year}.csv"
    with open(csvp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        # provenance FIRST — a denominator-narrowing flag must never be implicit
        w.writerow(["#param", "value"])
        w.writerow(["#ref", ref_path])
        w.writerow(["#prob", prob_path])
        w.writerow(["#thresh", thresh])
        w.writerow(["#forest_codes", " ".join(str(c) for c in forest_codes)])
        w.writerow(["#stable_with", stable_path or ""])
        w.writerow(["#denominator", "stable_subset" if stable_path else "full_forest"])
        w.writerow(["#chm", chm_path or ""])
        w.writerow([])
        w.writerow(["metric", "tp_mean", "tp_std", "fn_mean", "fn_std", "delta", "n_tp", "n_fn"])
        for m in METRICS:
            w.writerow([m, round(tp.mean(m), 4), round(tp.std(m), 4),
                        round(fn.mean(m), 4), round(fn.std(m), 4),
                        round(fn.mean(m) - tp.mean(m), 4), tp.n[m], fn.n[m]])
        w.writerow([])
        w.writerow(["forest_px", forest_total, "tp", n_tp, "fn", n_fn, "recall", round(recall, 4),
                    "indep_cells", (round(indep_cells) if indep_cells == indep_cells else ""),
                    "denominator", "stable_subset" if stable_path else "full_forest"])
    _plot(year, tp, fn)
    print(f"[forest-miss] wrote {QC_DIR / f'forest_miss_{year}.txt'}")
    print(f"[forest-miss] wrote {csvp}")


def _plot(year, tp, fn):
    try:
        panels = [("prob", "model confidence"), ("NDVI", "greenness (NDVI)"),
                  ("brightness", "RGB brightness (DN)")]
        fig, axes = plt.subplots(1, len(panels), figsize=(4.4 * len(panels), 4.0))
        for ax, (m, title) in zip(axes, panels):
            lo, hi, nb = HIST_SPEC[m]
            centres = lo + (np.arange(nb) + 0.5) * (hi - lo) / nb
            for acc, lab, c in ((tp, "recalled (TP)", "#2c7fb8"), (fn, "missed (FN)", "#d95f0e")):
                h = acc.hist[m][1:nb + 1].astype(float)
                if h.sum():
                    ax.plot(centres, h / h.sum(), label=lab, color=c, lw=1.8)
                    ax.fill_between(centres, h / h.sum(), alpha=0.2, color=c)
            ax.set_title(title, fontsize=10); ax.set_yticks([]); ax.legend(fontsize=8)
        fig.suptitle(f"Forest misses — {year}: recalled vs missed distributions", fontsize=12)
        fig.tight_layout()
        png = QC_DIR / f"forest_miss_{year}.png"
        fig.savefig(png, dpi=115, bbox_inches="tight"); plt.close(fig)
        print(f"[forest-miss] wrote {png}")
    except Exception as e:
        print(f"[forest-miss] WARN plot: {e}")


def write_step_log(year, n_tp, n_fn, stable_path=None):
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        rec = n_tp / (n_tp + n_fn) if (n_tp + n_fn) else float("nan")
        denom = "stable_subset" if stable_path else "full_forest"
        (LOGS_DIR / f"phase4_qc_forest_misses_{year}_{ts}.log").write_text(
            f"phase4_qc_forest_misses.py year={year} recall={rec:.4f} "
            f"tp={n_tp} fn={n_fn} denominator={denom} "
            f"stable_with={stable_path or ''}\n", encoding="utf-8")
    except Exception:
        pass


def _confident_frac(fn_acc, cut=0.12):
    """Fraction of missed-forest px whose model prob < cut (confident/OOD misses)."""
    nb = HIST_SPEC["prob"][2]
    core = fn_acc.hist["prob"][1:nb + 1]
    tot = core.sum()
    if not tot:
        return float("nan")
    ncut = int(round(cut * nb))
    return float(core[:ncut].sum()) / float(tot)


def _compare_row(R):
    """One cross-sensor row from an analyse() result."""
    y, tp, fn = R["year"], R["tp"], R["fn"]
    d = lambda m: fn.mean(m) - tp.mean(m)
    return dict(
        year=y, sensor=sensor_of(y), gsd_cm=GSD_CM.get(y, float("nan")),
        forest_px=R["forest_total"], tp=R["n_tp"], fn=R["n_fn"],
        recall=round(R["recall"], 4), confident_miss=round(_confident_frac(fn), 4),
        ndvi_tp=round(tp.mean("NDVI"), 4), ndvi_fn=round(fn.mean("NDVI"), 4), d_ndvi=round(d("NDVI"), 4),
        grvi_tp=round(tp.mean("GRVI"), 4), grvi_fn=round(fn.mean("GRVI"), 4), d_grvi=round(d("GRVI"), 4),
        bright_tp=round(tp.mean("brightness"), 2), bright_fn=round(fn.mean("brightness"), 2),
        d_bright=round(d("brightness"), 2),
        height_tp=round(tp.mean("height_m"), 2), height_fn=round(fn.mean("height_m"), 2))


def _write_compare(rows, ref_name, stable_path):
    rows = sorted(rows, key=lambda r: (r["gsd_cm"], r["year"]))
    QC_DIR.mkdir(parents=True, exist_ok=True)
    csvp = QC_DIR / "forest_miss_sensor_compare.csv"
    fields = ["year", "sensor", "gsd_cm", "recall", "confident_miss", "d_ndvi", "d_grvi",
              "d_bright", "ndvi_tp", "ndvi_fn", "grvi_tp", "grvi_fn", "bright_tp", "bright_fn",
              "height_tp", "height_fn", "forest_px", "tp", "fn"]
    with open(csvp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    L = [f"CROSS-SENSOR FOREST-MISS COMPARISON  (ref={ref_name}"
         + (f", stable∩{Path(stable_path).name}" if stable_path else "") + ")",
         "  recall = C-CAP upland-forest recall; conf = frac of misses with prob<0.12 (OOD);",
         "  Δgrvi/Δndvi = missed−recalled greenness (neg = misses less-green); Δbright = DN.",
         "",
         "  year    sensor   gsd_cm   recall   conf%   Δgrvi    Δndvi   Δbright   ht_fn/tp"]
    for r in rows:
        nd = "  n/a " if r["ndvi_tp"] != r["ndvi_tp"] else f"{r['d_ndvi']:+.3f}"
        L.append(f"  {r['year']:<7} {r['sensor']:<7} {r['gsd_cm']:>5.1f}   "
                 f"{r['recall']:>6.4f}  {100*r['confident_miss']:>5.1f}  {r['d_grvi']:>+6.3f}  "
                 f"{nd:>7}  {r['d_bright']:>+6.1f}   {r['height_fn']:>4.1f}/{r['height_tp']:<4.1f}")
    L += ["",
          "  Read: recall varying with gsd/sensor at similar Δgrvi = a RESOLUTION effect;",
          "  Δgrvi/Δbright shifting by sensor = a RADIOMETRIC (sensor) effect. Compare WITHIN",
          "  a training recipe (use --force-citywide rasters) to avoid the tier-recipe confound."]
    txt = "\n".join(L)
    print("\n" + txt)
    (QC_DIR / "forest_miss_sensor_compare.txt").write_text(txt, encoding="utf-8")
    print(f"\n[forest-miss] wrote {csvp}")
    print(f"[forest-miss] wrote {QC_DIR / 'forest_miss_sensor_compare.txt'}")


def run_compare(years, ref_path, stable_path, forest_codes, thresh_arg,
                block_rows, coarse, prob_suffix):
    rows = []
    for y in years:
        if y not in IMG_CATALOG:
            print(f"[compare] SKIP {y}: not in IMG_CATALOG"); continue
        prob_path = MASKS / f"edmonds_canopy_prob_{y}{prob_suffix}.tif"
        if not prob_path.exists():
            print(f"[compare] SKIP {y}: no prob raster {prob_path.name}"); continue
        thresh = thresh_arg if thresh_arg is not None else (deployed_threshold(y) or 0.5)
        print(f"\n{'='*60}\n[compare] {y}  ({sensor_of(y)}, {GSD_CM.get(y,'?')}cm, thresh {thresh})\n{'='*60}")
        try:
            R = analyse(y, ref_path, prob_path, thresh, forest_codes, block_rows, coarse, stable_path)
        except Exception as e:
            print(f"[compare] {y} FAILED: {e}"); continue
        rows.append(_compare_row(R))
    if rows:
        _write_compare(rows, ref_path.name, stable_path)
    else:
        print("[compare] no years scored (no matching prob rasters).")


def main():
    keep, skip = [], False
    for a in sys.argv[1:]:
        if skip:
            skip = False; continue
        if a == "-f":
            skip = True; continue
        keep.append(a)
    ap = argparse.ArgumentParser(description="Autopsy of missed upland-forest (under-prediction).")
    ap.add_argument("--year", default="2016", choices=sorted(IMG_CATALOG),
                    help="Single year to autopsy.")
    ap.add_argument("--years", default=None,
                    help="Comma list → CROSS-SENSOR compare mode (one row per year + a table).")
    ap.add_argument("--ref", required=True, help="C-CAP land-cover raster (any CRS/res).")
    ap.add_argument("--stable-with", default=None,
                    help="2nd C-CAP raster; forest must be forest in BOTH → isolates the sensor "
                         "effect from real canopy change (e.g. the other-vintage C-CAP).")
    ap.add_argument("--prob", default=None,
                    help="Single-year prob override (default masks/edmonds_canopy_prob_{year}{suffix}.tif).")
    ap.add_argument("--prob-suffix", default="",
                    help="Suffix for --run-tag'd prob rasters, e.g. _rgbonly.")
    ap.add_argument("--forest-codes", default=None,
                    help="Comma C-CAP codes = upland forest (default 9,10,11).")
    ap.add_argument("--thresh", type=float, default=None,
                    help="Fixed operating threshold (default = per-year deployed value; a FIXED "
                         "threshold is fairer for cross-sensor comparison).")
    ap.add_argument("--block-rows", type=int, default=2048, help="Must be a multiple of --coarse.")
    ap.add_argument("--coarse", type=int, default=256, help="FN-density cell size in prob px.")
    args = ap.parse_args(keep)

    ref_path = Path(args.ref)
    if not ref_path.exists():
        raise FileNotFoundError(f"--ref not found: {ref_path}")
    stable_path = None
    if args.stable_with:
        stable_path = Path(args.stable_with)
        if not stable_path.exists():
            raise FileNotFoundError(f"--stable-with not found: {stable_path}")
    forest_codes = ([int(x) for x in args.forest_codes.split(",")]
                    if args.forest_codes else DEFAULT_FOREST_CODES)
    if args.block_rows % args.coarse:
        raise SystemExit(f"--block-rows ({args.block_rows}) must be a multiple of --coarse ({args.coarse})")

    if args.years:
        years = [y.strip() for y in args.years.split(",") if y.strip()]
        run_compare(years, ref_path, stable_path, forest_codes, args.thresh,
                    args.block_rows, args.coarse, args.prob_suffix)
        return

    prob_path = (Path(args.prob) if args.prob
                 else MASKS / f"edmonds_canopy_prob_{args.year}{args.prob_suffix}.tif")
    if not prob_path.exists():
        raise FileNotFoundError(f"prob raster not found: {prob_path}")
    thresh = args.thresh
    if thresh is None:
        thresh = deployed_threshold(args.year)
        if thresh is None:
            print("  ! no eval-CSV threshold; defaulting to 0.5"); thresh = 0.5
        else:
            print(f"  deployed threshold {thresh} from eval CSV")

    R = analyse(args.year, ref_path, prob_path, thresh,
                forest_codes, args.block_rows, args.coarse, stable_path)
    write_step_log(R["year"], R["n_tp"], R["n_fn"], stable_path)


if __name__ == "__main__":
    main()
