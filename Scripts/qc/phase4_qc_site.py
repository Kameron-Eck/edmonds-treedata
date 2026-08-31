"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — QC: point/window diagnostic (attribute the under-prediction)
  Edmonds Temporal Active Learning Pipeline

  WHY
    phase4_qc_score.py showed 2016 recall vs the independent NDVI+CHM
    reference is only ~0.60 (40% of real canopy missed) while precision is
    ~0.97. This tool zooms into a lat/lon window (e.g. the Edmonds marsh
    deciduous stand the model misses) and ATTRIBUTES the misses:

      • cross-tabs the FN (missed-canopy) pixels by CHM height + NDVI →
        proves the missed pixels are TALL and GREEN (real trees the model
        confidently rejects = out-of-distribution / deciduous), not
        reference noise or short scrub.
      • saves an RGB | NDVI | CHM | prob | FN-map panel.

    Works for years WITH an NDVI ref (2016, 2019n, 2023n) and, in prob-only
    mode, for years WITHOUT NIR (2000) — there it reports model canopy vs
    CHM height only (no independent veg truth).

  PRODUCES (phase4/qc/sites/):
    {name}_{year}.png    RGB | (NDVI) | CHM | model-prob | (FN map)
    {name}_{year}.txt    window confusion + FN-by-height/NDVI cross-tab

  USAGE (local or Colab):
    py -3.12 phase4_qc_site.py --year 2016 --lon -122.3837 --lat 47.8027 --name marsh
    py -3.12 phase4_qc_site.py --year 2000 --lon -122.3837 --lat 47.8027 --name marsh
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import datetime as _dt
import importlib
import subprocess
import sys
from pathlib import Path



# Dep bootstrap: mechanism in phase4seg/deps.py (refactor 2.3); the LIST stays
# per-file — nine distinct sets exist and one shared list would over-install.
from phase4seg.deps import ensure_deps as _ensure_deps  # noqa: E402
_ensure_deps([("rasterio", "rasterio"), ("numpy", "numpy"),
                    ("matplotlib", "matplotlib")])

import numpy as np
import rasterio
import rasterio.warp
import rasterio.windows
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from phase4seg.names import clean_argv  # noqa: E402


# Lake paths: ONE home (pipeline/lake.py, refactor 2.4). The strict probe it
# carries is the correct one — the bare .exists() this file used was true
# whenever the mount POINT existed, mounted or not.
from lake import BASE  # noqa: E402

_LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")
_DRIVE_IMG = BASE / "Full_Image" / "Pipeline Imagery"
IMAGERY_DIRS = [d for d in (_LOCAL_IMG, _DRIVE_IMG) if d.exists()] or [_DRIVE_IMG]

QC_DIR    = BASE / "phase4" / "qc"
SITES_DIR = QC_DIR / "sites"
MASKS     = BASE / "phase4" / "masks"
LOGS_DIR  = BASE / "phase4" / "logs"
CHM_NAME  = "lidar_snoh_chm.tif"
CHM_DN_PER_M = 1.0 / 0.2

# year -> (imagery file, nir band or None)
IMG_CATALOG = {
    "2000": ("2000_king_rgb.tif", None),
    "2015": ("2015_king_rgb.tif", None),
    "2016": ("2016_snoh_rgbi.tif", 4),
    "2019n": ("2019_naip_rgbi.tif", 4),
    "2023n": ("2023_naip_rgbi.tif", 4),
}


def resolve(fname, extra=()):
    for d in list(IMAGERY_DIRS) + list(extra):
        p = d / fname
        if p.exists():
            return p
    raise FileNotFoundError(f"{fname} not found in {[str(d) for d in IMAGERY_DIRS]}")


def read_window(path, bounds_wgs84, bands=None, resamp=Resampling.nearest):
    """Read a WGS84-bounded window from a raster in any CRS. Returns (arr, ) or None."""
    with rasterio.open(path) as src:
        b = rasterio.warp.transform_bounds("EPSG:4326", src.crs, *bounds_wgs84)
        win = rasterio.windows.from_bounds(*b, transform=src.transform)
        win = win.round_offsets(op="floor").round_lengths(op="ceil")
        win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
        if win.width <= 0 or win.height <= 0:
            return None
        idx = bands if bands is not None else list(range(1, src.count + 1))
        arr = src.read(idx, window=win, resampling=resamp)
        return arr


def read_chm_window(bounds_wgs84, ref_crs):
    """CHM (EPSG:3857) reprojected/read for a WGS84 window, returned in metres."""
    chm_path = resolve(CHM_NAME, extra=[_DRIVE_IMG])
    with rasterio.open(chm_path) as src:
        b = rasterio.warp.transform_bounds("EPSG:4326", src.crs, *bounds_wgs84)
        win = rasterio.windows.from_bounds(*b, transform=src.transform)
        win = win.round_offsets(op="floor").round_lengths(op="ceil")
        win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
        if win.width <= 0 or win.height <= 0:
            return None
        dn = src.read(1, window=win)
    h = (dn.astype(np.float32) - 1.0) / CHM_DN_PER_M
    h[dn == 0] = np.nan
    return h


def _resize_to(a, shape):
    """Nearest-neighbour resize a 2-D array to shape (for panel alignment)."""
    yi = np.clip((np.arange(shape[0]) * a.shape[0] / shape[0]).astype(int), 0, a.shape[0]-1)
    xi = np.clip((np.arange(shape[1]) * a.shape[1] / shape[1]).astype(int), 0, a.shape[1]-1)
    return a[yi][:, xi]


def diagnose(year, lon, lat, radius_m, name, thresh):
    meta = IMG_CATALOG[year]
    img_file, nir_b = meta
    # WGS84 bbox from a metres radius (approx: 1 deg lat ~111.32 km)
    dlat = radius_m / 111320.0
    dlon = radius_m / (111320.0 * np.cos(np.radians(lat)))
    bounds = (lon - dlon, lat - dlat, lon + dlon, lat + dlat)
    print(f"[qc-site] {name} year={year} lon={lon} lat={lat} r={radius_m}m")
    print(f"    bbox(wgs84) = {tuple(round(x,5) for x in bounds)}")

    img_path  = resolve(img_file)
    prob_path = MASKS / f"edmonds_canopy_prob_{year}.tif"
    ref_path  = QC_DIR / f"ndvi_ref_{year}.tif"

    # RGB (+NIR) window
    read_bands = [1, 2, 3, nir_b] if nir_b else [1, 2, 3]
    rgbi = read_window(img_path, bounds, bands=read_bands)
    if rgbi is None:
        print(f"    ! window OUTSIDE {year} imagery extent — no coverage here.")
        return
    rgb = np.transpose(rgbi[:3], (1, 2, 0)).astype(np.uint8)
    shp = rgb.shape[:2]
    ndvi = None
    if nir_b:
        r = rgbi[0].astype(np.float32); nir = rgbi[3].astype(np.float32)
        ndvi = (nir - r) / (nir + r + 1e-6)

    prob_a = read_window(prob_path, bounds, bands=[1])
    prob = None
    if prob_a is not None:
        p = prob_a[0].astype(np.float32); p[prob_a[0] == 255] = np.nan
        prob = _resize_to(p / 254.0, shp)
    chm = read_chm_window(bounds, None)
    chm = _resize_to(chm, shp) if chm is not None else None
    ref_a = read_window(ref_path, bounds, bands=[1]) if ref_path.exists() else None
    ref = _resize_to(ref_a[0], shp) if ref_a is not None else None

    _stats_and_panel(year, name, lon, lat, radius_m, thresh, rgb, ndvi, chm, prob, ref)


def _crosstab_fn(fn_mask, chm, ndvi):
    """Distribution of missed-canopy pixels over CHM height bins (+ mean NDVI)."""
    bins = [(-0.1, 2), (2, 5), (5, 10), (10, 20), (20, 100)]
    labels = ["<2m", "2-5m", "5-10m", "10-20m", "20m+"]
    out = []
    tot = int(fn_mask.sum())
    for (lo, hi), lab in zip(bins, labels):
        m = fn_mask & (chm >= lo) & (chm < hi) if chm is not None else np.zeros_like(fn_mask)
        n = int(m.sum())
        mnd = float(np.nanmean(ndvi[m])) if (ndvi is not None and n) else float("nan")
        out.append((lab, n, 100*n/tot if tot else 0.0, mnd))
    return out, tot


def _stats_and_panel(year, name, lon, lat, radius_m, thresh, rgb, ndvi, chm, prob, ref):
    L = [f"QC site diagnostic — {name} — year {year}",
         f"  center lon/lat : {lon}, {lat}   radius {radius_m} m",
         f"  threshold      : {thresh}", ""]
    fn_mask = None
    if prob is not None and ref is not None:
        valid = ~np.isnan(prob) & (ref != 255)
        rc = valid & (ref == 2)
        mc = valid & (prob >= thresh)
        tp = int((rc & mc).sum()); fn = int((rc & ~mc).sum())
        fp = int((~rc & mc & valid).sum())
        recall = tp/(tp+fn) if (tp+fn) else float("nan")
        prec = tp/(tp+fp) if (tp+fp) else float("nan")
        L.append(f"  ref canopy px  : {int(rc.sum()):,}")
        L.append(f"  model canopy px: {int(mc.sum()):,}")
        L.append(f"  RECALL (window): {recall:.4f}   precision: {prec:.4f}")
        L.append(f"  TP={tp:,}  FN(missed)={fn:,}  FP={fp:,}")
        fn_mask = rc & ~mc
        if chm is not None:
            xt, tot = _crosstab_fn(fn_mask, chm, ndvi)
            L.append("")
            L.append(f"  MISSED-CANOPY (FN) by CHM height  [{tot:,} px]:")
            L.append("    height     px      share   meanNDVI")
            for lab, n, pct, mnd in xt:
                L.append(f"    {lab:<7}  {n:>8,}  {pct:>5.1f}%   {mnd:>6.3f}")
            tall = sum(n for lab, n, _, _ in xt if lab in ("5-10m", "10-20m", "20m+"))
            L.append(f"  → {100*tall/tot if tot else 0:.1f}% of misses are >5 m tall"
                     f" (real trees, not scrub)")
    elif prob is not None:
        valid = ~np.isnan(prob)
        mc = valid & (prob >= thresh)
        L.append(f"  (no NDVI ref for {year} — prob-only mode)")
        L.append(f"  model canopy px: {int(mc.sum()):,}  ({100*mc.sum()/max(valid.sum(),1):.1f}% of valid)")
        if chm is not None:
            tallveg = valid & (chm >= 2)
            miss = tallveg & ~mc
            L.append(f"  CHM-tall (>=2m) px: {int(tallveg.sum()):,}")
            L.append(f"  tall-but-not-called-canopy: {int(miss.sum()):,}"
                     f"  ({100*miss.sum()/max(tallveg.sum(),1):.1f}% of tall px)")

    txt = "\n".join(L)
    print("\n" + txt)
    SITES_DIR.mkdir(parents=True, exist_ok=True)
    (SITES_DIR / f"{name}_{year}.txt").write_text(txt, encoding="utf-8")

    # panel
    cols = [("RGB", rgb, None)]
    if ndvi is not None:
        cols.append(("NDVI", _resize_to(ndvi, rgb.shape[:2]), "RdYlGn"))
    if chm is not None:
        cols.append(("CHM (m)", chm, "viridis"))
    if prob is not None:
        cols.append((f"prob (thr {thresh})", prob, "magma"))
    if fn_mask is not None:
        cols.append(("MISSED canopy (FN)", fn_mask.astype(float), "Reds"))
    n = len(cols)
    fig, axes = plt.subplots(1, n, figsize=(4*n, 4.4))
    if n == 1:
        axes = [axes]
    for ax, (title, data, cmap) in zip(axes, cols):
        if cmap is None:
            ax.imshow(data)
        elif title == "NDVI":
            ax.imshow(data, cmap=cmap, vmin=-0.3, vmax=0.8)
        elif title.startswith("prob"):
            ax.imshow(data, cmap=cmap, vmin=0, vmax=1)
        else:
            ax.imshow(data, cmap=cmap)
        ax.set_title(title, fontsize=10); ax.axis("off")
    fig.suptitle(f"{name} — {year}", fontsize=12)
    fig.tight_layout()
    png = SITES_DIR / f"{name}_{year}.png"
    fig.savefig(png, dpi=110, bbox_inches="tight"); plt.close(fig)
    print(f"[qc-site] wrote {png}")
    print(f"[qc-site] wrote {SITES_DIR / f'{name}_{year}.txt'}")
    _log(name, year)


def _log(name, year):
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"phase4_qc_site_{name}_{year}_{ts}.log").write_text(
            f"phase4_qc_site.py {name} {year}\n", encoding="utf-8")
    except Exception:
        pass


def main():
    filtered = clean_argv()
    ap = argparse.ArgumentParser(description="Point/window QC diagnostic.")
    ap.add_argument("--year", default="2016", choices=sorted(IMG_CATALOG))
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--radius-m", type=float, default=400.0)
    ap.add_argument("--name", default="site")
    ap.add_argument("--thresh", type=float, default=0.3767)
    args = ap.parse_args(filtered)
    diagnose(args.year, args.lon, args.lat, args.radius_m, args.name, args.thresh)


if __name__ == "__main__":
    main()
