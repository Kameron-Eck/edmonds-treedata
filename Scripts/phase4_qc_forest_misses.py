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
LOGS_DIR = BASE / "Scripts" / "logs"
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
    "2019n": ("2019_naip_rgbi.tif", 4),
    "2021":  ("2021_king_rgb.tif",  None),
    "2021s": ("2021_snoh_rgbi.tif", 4),
    "2022n": ("2022_naip_rgbi.tif", 4),
    "2023":  ("2023_king_rgb.tif",  None),
}
# GSD (cm) + sensor per label — for the cross-sensor failure table.
GSD_CM = {"2000": 59.7, "2002": 59.7, "2005": 29.9, "2007": 29.9, "2009": 29.9,
          "2012": 14.9, "2013": 14.9, "2015": 14.9, "2016": 50.0, "2017": 7.5,
          "2019": 14.9, "2019n": 60.0, "2021": 14.9, "2021s": 50.0, "2022n": 60.0,
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

        ref_vrt.close(); ref_ds.close()
        if chm_vrt:
            chm_vrt.close(); chm_ds.close()
        if stable_vrt is not None:
            stable_vrt.close(); stable_ds.close()
        coarse_tf = prob.transform * Affine.scale(coarse)
        coarse_crs = prob.crs

    _write_density(year, c_forest, c_fn, coarse_tf, coarse_crs, coarse)
    _report(year, ref_path, prob_path, thresh, forest_codes,
            tp, fn, n_tp, n_fn, forest_total)
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


def _report(year, ref_path, prob_path, thresh, forest_codes, tp, fn, n_tp, n_fn, forest_total):
    recall = n_tp / (n_tp + n_fn) if (n_tp + n_fn) else float("nan")
    L = [f"FOREST-MISS AUTOPSY — year {year}  (why upland forest is under-predicted)",
         f"  ref   : {ref_path}   (forest codes {forest_codes})",
         f"  prob  : {prob_path}",
         f"  thresh: {thresh}",
         "",
         f"  C-CAP upland-forest px : {forest_total:,}",
         f"  recalled (TP) : {n_tp:,}   missed (FN) : {n_fn:,}   RECALL {recall:.4f}",
         "",
         f"  metric          recalled(TP)         missed(FN)          Δ(FN−TP)",
         f"                  mean ± std           mean ± std"]
    for m in METRICS:
        tm, ts, fm, fs = tp.mean(m), tp.std(m), fn.mean(m), fn.std(m)
        d = fm - tm
        L.append(f"  {m:<13}  {tm:>7.3f} ± {ts:<7.3f}   {fm:>7.3f} ± {fs:<7.3f}   {d:>+7.3f}")
    # prob-depth of misses
    ph = fn.hist["prob"]; nb = HIST_SPEC["prob"][2]; core = ph[1:nb + 1]; tot = max(core.sum(), 1)
    b1 = core[:3].sum() / tot; b2 = core[3:6].sum() / tot
    thr_bin = int(np.clip(thresh * nb, 0, nb))
    b3 = core[6:thr_bin].sum() / tot
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
        w.writerow(["metric", "tp_mean", "tp_std", "fn_mean", "fn_std", "delta"])
        for m in METRICS:
            w.writerow([m, round(tp.mean(m), 4), round(tp.std(m), 4),
                        round(fn.mean(m), 4), round(fn.std(m), 4),
                        round(fn.mean(m) - tp.mean(m), 4)])
        w.writerow([])
        w.writerow(["forest_px", forest_total, "tp", n_tp, "fn", n_fn, "recall", round(recall, 4)])
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


def write_step_log(year, n_tp, n_fn):
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        rec = n_tp / (n_tp + n_fn) if (n_tp + n_fn) else float("nan")
        (LOGS_DIR / f"phase4_qc_forest_misses_{year}_{ts}.log").write_text(
            f"phase4_qc_forest_misses.py year={year} recall={rec:.4f} "
            f"tp={n_tp} fn={n_fn}\n", encoding="utf-8")
    except Exception:
        pass


def main():
    keep, skip = [], False
    for a in sys.argv[1:]:
        if skip:
            skip = False; continue
        if a == "-f":
            skip = True; continue
        keep.append(a)
    ap = argparse.ArgumentParser(description="Autopsy of missed upland-forest (under-prediction).")
    ap.add_argument("--year", default="2016", choices=sorted(IMG_CATALOG))
    ap.add_argument("--ref", required=True, help="C-CAP land-cover raster (any CRS/res).")
    ap.add_argument("--prob", default=None, help="Prob raster (default masks/edmonds_canopy_prob_{year}.tif).")
    ap.add_argument("--forest-codes", default=None,
                    help="Comma C-CAP codes = upland forest (default 9,10,11).")
    ap.add_argument("--thresh", type=float, default=None,
                    help="Operating threshold (default = deployed value from eval CSV).")
    ap.add_argument("--block-rows", type=int, default=2048, help="Must be a multiple of --coarse.")
    ap.add_argument("--coarse", type=int, default=256, help="FN-density cell size in prob px.")
    args = ap.parse_args(keep)

    ref_path = Path(args.ref)
    if not ref_path.exists():
        raise FileNotFoundError(f"--ref not found: {ref_path}")
    prob_path = Path(args.prob) if args.prob else MASKS / f"edmonds_canopy_prob_{args.year}.tif"
    if not prob_path.exists():
        raise FileNotFoundError(f"prob raster not found: {prob_path}")
    forest_codes = ([int(x) for x in args.forest_codes.split(",")]
                    if args.forest_codes else DEFAULT_FOREST_CODES)
    if args.block_rows % args.coarse:
        raise SystemExit(f"--block-rows ({args.block_rows}) must be a multiple of --coarse ({args.coarse})")
    thresh = args.thresh
    if thresh is None:
        thresh = deployed_threshold(args.year)
        if thresh is None:
            print("  ! no eval-CSV threshold; defaulting to 0.5"); thresh = 0.5
        else:
            print(f"  deployed threshold {thresh} from eval CSV")

    n_tp, n_fn, _ = analyse(args.year, ref_path, prob_path, thresh,
                            forest_codes, args.block_rows, args.coarse)
    write_step_log(args.year, n_tp, n_fn)


if __name__ == "__main__":
    main()
