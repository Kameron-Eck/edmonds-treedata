"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — QC: VISUAL EXAMPLES of MISSED TREES  (understand-first)

  WHY
    Before staging the 2020 suburban/ornamental annotation package we want
    to SEE the missed-tree population on evidence, not assume it. The
    hypothesis (3-agent review, 2026-07-10): the RGB semantic model
    under-detects scattered suburban/ornamental trees — many purple-leaf,
    LOW-NDVI. This tool extracts real example chips, stratified by NDVI,
    so we can eyeball the pattern (and any OTHER miss circumstance).

  WHAT "MISSED TREE" MEANS  (single-year 2020, greenness-independent)
    tree population = Phase-0 instance crowns (edmonds_crowns_2020.gpkg,
      222k, EPSG:3857) — DTM/height-driven, so it FINDS low-NDVI trees a
      spectral model misses. Kept only where CHM >= --chm-min-m (real trees).
    miss = crown NOT covered by the 2020 semantic prediction
      (phase3/edmonds_canopy_mask_2020.tif, 1=canopy) — model_frac < --miss-frac.
    NDVI = zonal mean from a NIR ortho (default 2021_snoh_rgbi, band4=NIR).
    height = lidar_snoh_chm.tif, height_m = (DN-1)*0.2.

  STRATA (missed crowns), --n each:
    low_ndvi         NDVI < --ndvi-lo             (the ornamental hypothesis)
    mid_ndvi         --ndvi-lo <= NDVI < --ndvi-hi
    other_highndvi   NDVI >= --ndvi-hi            (green yet missed → OTHER cause)

  OUTPUT  phase4/qc/miss_examples/
    {stratum}_montage.png   4x5 contact sheet of 20 annotated chips
    chips/{stratum}/*.png   individual chips (zoom)
    miss_examples.csv       every pooled missed crown + metrics
    summary.txt             per-stratum counts + median NDVI/CHM/area/brightness

  USAGE (local; rasterio/geopandas/shapely/matplotlib auto-install)
    py -3.12 phase4_miss_examples.py --dry-run          # counts only, no render
    py -3.12 phase4_miss_examples.py                    # full run
    py -3.12 phase4_miss_examples.py --n 20 --miss-frac 0.20 --ndvi-year 2021s
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import importlib
import shutil
import subprocess
import sys
from pathlib import Path


def _pip(spec):
    print(f"  • installing {spec} …")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", spec], check=True)

for _imp, _spec in [("rasterio", "rasterio"), ("numpy", "numpy"),
                    ("geopandas", "geopandas"), ("shapely", "shapely"),
                    ("matplotlib", "matplotlib")]:
    try:
        importlib.import_module(_imp)
    except ImportError:
        _pip(_spec)

import numpy as np
import rasterio
import rasterio.warp
import rasterio.windows
from rasterio.enums import Resampling
from rasterio.transform import Affine
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon


_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE

_LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")
_DRIVE_IMG = BASE / "Full_Image" / "Pipeline Imagery"
IMAGERY_DIRS = [d for d in (_LOCAL_IMG, _DRIVE_IMG) if d.exists()] or [_DRIVE_IMG]

CROWNS   = BASE / "inference" / "edmonds_crowns_2020.gpkg"
MASK2020 = BASE / "phase3" / "edmonds_canopy_mask_2020.tif"
ORTHO    = "2020_coe_rgb.tif"                 # 7.5 cm CoE, EPSG:3857 (resolve in IMAGERY_DIRS)
CHM_NAME = "lidar_snoh_chm.tif"
CHM_DN_PER_M = 1.0 / 0.2                       # DN = metres / 0.2   (height_m = (DN-1)*0.2)
OUT_DRIVE = BASE / "phase4" / "qc" / "miss_examples"
# large intermediate writes go to local NVMe first, then copy to Drive (CLAUDE rule 3)
OUT_LOCAL = Path(r"D:\edmonds-pipeline\annotate\miss_examples") if _LOCAL_IMG.exists() else OUT_DRIVE

# NIR-bearing orthos usable for NDVI (label -> file, NIR band). Matches phase4_qc_forest_misses.
# DERIVED from config.YEAR_CATALOG, never restated. Until 2026-08-31 this was a
# literal dict whose four filenames had all lost their resolution token
# ("2016_snoh_rgbi.tif" for "2016_snoh_1ft_rgbi.tif", and three more). Both names
# exist on disk, so every .exists() passed while the stale files covered 39.6-67%
# of the authoritative extent. Deriving fixes the instance AND the class, and picks
# up all 10 NIR-bearing acquisitions instead of 4. See names.py::nir_years.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "pipeline"))
from phase4seg import config as _C            # noqa: E402
from phase4seg.names import clean_argv, nir_years as _nir_years   # noqa: E402
NIR_CATALOG = {k: (e["native_file"], int(e["bands"]))
               for k, e in _nir_years(_C.YEAR_CATALOG).items()}
# "2021" kept as an alias for 2021s, as before.
if "2021s" in NIR_CATALOG:
    NIR_CATALOG.setdefault("2021", NIR_CATALOG["2021s"])

STRATA = ("low_ndvi", "mid_ndvi", "other_highndvi")


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
    raise FileNotFoundError("lidar_snoh_chm.tif not found")


def decimated_read(path, target_m, bands, resampling):
    """Read a raster downsampled to ~target_m ground resolution, fully into RAM.
    Returns (array [bands,H,W] or [H,W], scaled_transform, crs, (src_res)).
    Cheap even on a striped file: one sequential decimated pass."""
    with rasterio.open(path) as s:
        native = abs(s.res[0])
        scale = max(1, int(round(target_m / native)))
        out_h = max(1, s.height // scale)
        out_w = max(1, s.width // scale)
        single = isinstance(bands, int)
        arr = s.read(bands, out_shape=((out_h, out_w) if single else (len(bands), out_h, out_w)),
                     resampling=resampling)
        # transform that maps the decimated grid back to world coords
        tf = s.transform * Affine.scale(s.width / out_w, s.height / out_h)
        return arr, tf, s.crs, native


def world_to_rc(transform, xs, ys):
    inv = ~transform
    cols, rows = inv * (np.asarray(xs), np.asarray(ys))
    return np.floor(rows).astype(np.int64), np.floor(cols).astype(np.int64)


def bbox_model_frac(mask, tf, bounds):
    """Fraction of a crown's bbox pixels predicted canopy (==1), ignoring nodata(255)."""
    minx, miny, maxx, maxy = bounds
    r0, c0 = world_to_rc(tf, [minx], [maxy]); r1, c1 = world_to_rc(tf, [maxx], [miny])
    r0, c0, r1, c1 = int(r0[0]), int(c0[0]), int(r1[0]), int(c1[0])
    r0, r1 = max(0, min(r0, r1)), min(mask.shape[0], max(r0, r1) + 1)
    c0, c1 = max(0, min(c0, c1)), min(mask.shape[1], max(c0, c1) + 1)
    if r1 <= r0 or c1 <= c0:
        return np.nan
    win = mask[r0:r1, c0:c1]
    valid = win != 255
    nv = int(valid.sum())
    if nv == 0:
        return np.nan
    return float((win == 1).sum()) / nv


def _clamp_window(win, W, H):
    """Manual intersection with the full raster; returns a Window or None (never throws)."""
    c0 = max(0, int(np.floor(win.col_off)));  r0 = max(0, int(np.floor(win.row_off)))
    c1 = min(W, int(np.ceil(win.col_off + win.width)))
    r1 = min(H, int(np.ceil(win.row_off + win.height)))
    if r1 <= r0 or c1 <= c0:
        return None
    return rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)


def read_window(ds, x, y, half_m, bands):
    """Read a small (~2*half_m) window around world point (x,y) from an open dataset.
    Point is given in the DATASET's CRS. Returns array [b,h,w] (or [h,w]) or None
    (None when the point lies outside the raster's coverage)."""
    b = (x - half_m, y - half_m, x + half_m, y + half_m)
    win = _clamp_window(rasterio.windows.from_bounds(*b, transform=ds.transform),
                        ds.width, ds.height)
    if win is None:
        return None
    return ds.read(bands, window=win)


def main():
    filtered = clean_argv()
    ap = argparse.ArgumentParser(description="Extract visual examples of missed trees.")
    ap.add_argument("--n", type=int, default=20, help="examples per stratum")
    ap.add_argument("--chm-min-m", type=float, default=5.0, help="min tree height (m)")
    ap.add_argument("--miss-frac", type=float, default=0.20,
                    help="crown is MISSED if model canopy coverage < this")
    ap.add_argument("--ndvi-year", default="2021s", choices=list(NIR_CATALOG),
                    help="NIR ortho for NDVI")
    ap.add_argument("--ndvi-lo", type=float, default=0.30)
    ap.add_argument("--ndvi-hi", type=float, default=0.50)
    ap.add_argument("--pool", type=int, default=20000,
                    help="random CHM-passing candidates to test (bounds runtime)")
    ap.add_argument("--min-sep-m", type=float, default=100.0,
                    help="min spacing between chosen examples within a stratum")
    ap.add_argument("--chip-half-m", type=float, default=20.0, help="chip half-box (m)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dry-run", action="store_true", help="counts only; no render/write")
    args = ap.parse_args(filtered)
    rng = np.random.default_rng(args.seed)

    ortho_path = resolve_img(ORTHO)
    chm_path = resolve_chm()
    ndvi_file, nir_band = NIR_CATALOG[args.ndvi_year]
    ndvi_path = resolve_img(ndvi_file)
    print(f"[miss-examples] crowns   = {CROWNS}")
    print(f"    mask   = {MASK2020}")
    print(f"    ortho  = {ortho_path}")
    print(f"    chm    = {chm_path}")
    print(f"    ndvi   = {ndvi_path}  (NIR band {nir_band}, year {args.ndvi_year})")
    print(f"    thresh = miss<{args.miss_frac}  CHM>={args.chm_min_m}m  "
          f"NDVI lo/hi {args.ndvi_lo}/{args.ndvi_hi}  n/stratum={args.n}")

    # ── 1. crowns + centroids ────────────────────────────────────────────────
    print("  reading crowns (222k; slow over FUSE) …")
    gdf = gpd.read_file(CROWNS, columns=["crown_id", "area_m2"])
    if str(gdf.crs) != "EPSG:3857":
        gdf = gdf.to_crs("EPSG:3857")
    cent = gdf.geometry.centroid
    cx, cy = cent.x.values, cent.y.values
    bnds = gdf.geometry.bounds.values          # minx,miny,maxx,maxy per crown
    print(f"  crowns: {len(gdf):,}")

    # ── 2. CHM height filter (load decimated to native 1 m — CHM IS 1 m) ─────
    chm_arr, chm_tf, chm_crs, _ = decimated_read(chm_path, 1.0, 1, Resampling.nearest)
    rr, cc = world_to_rc(chm_tf, cx, cy)
    ok = (rr >= 0) & (rr < chm_arr.shape[0]) & (cc >= 0) & (cc < chm_arr.shape[1])
    dn = np.zeros(len(gdf), dtype=np.uint8)
    dn[ok] = chm_arr[rr[ok], cc[ok]]
    height_m = (dn.astype(np.float32) - 1.0) / CHM_DN_PER_M
    height_m[dn == 0] = np.nan
    tall = np.where(height_m >= args.chm_min_m)[0]
    print(f"  CHM >= {args.chm_min_m}m : {len(tall):,} candidate trees")

    # sub-sample the candidate pool to bound the per-crown work
    if len(tall) > args.pool:
        tall = rng.choice(tall, size=args.pool, replace=False)
        tall.sort()
    print(f"  testing pool     : {len(tall):,}")

    # ── 3. miss test against the 2020 semantic mask (decimated to 1 m in RAM) ─
    print("  reading 2020 mask (decimated 1 m) …")
    mask1, mask_tf, mask_crs, _ = decimated_read(MASK2020, 1.0, 1, Resampling.nearest)
    model_frac = np.array([bbox_model_frac(mask1, mask_tf, bnds[i]) for i in tall])
    missed_local = np.where(np.isfinite(model_frac) & (model_frac < args.miss_frac))[0]
    missed = tall[missed_local]
    mfrac = model_frac[missed_local]
    print(f"  missed (model_frac < {args.miss_frac}) : {len(missed):,}")

    # ── 4. NDVI + brightness on the missed subset (per-crown windowed reads) ──
    #  small subset (hundreds) → windowed reads beat decimating the 30 GB ortho.
    print(f"  sampling NDVI + brightness for {len(missed):,} missed crowns …")
    mx, my = cx[missed], cy[missed]
    ndvi = np.full(len(missed), np.nan, np.float32)
    bright = np.full(len(missed), np.nan, np.float32)
    HALF_M = 4.0
    with rasterio.open(ndvi_path) as nd, rasterio.open(ortho_path) as ob:
        nx, ny = rasterio.warp.transform("EPSG:3857", nd.crs, list(mx), list(my))
        nx, ny = np.array(nx), np.array(ny)
        for k in range(len(missed)):
            w = read_window(nd, nx[k], ny[k], HALF_M, [1, nir_band])   # [R, NIR]
            if w is not None:
                R = w[0].astype(np.float32); N = w[1].astype(np.float32)
                den = N + R
                v = (N - R) / np.where(den > 0, den, np.nan)
                v = v[np.isfinite(v)]
                if v.size:
                    ndvi[k] = float(v.mean())
            wb = read_window(ob, mx[k], my[k], HALF_M, [1, 2, 3])       # tiled → cheap
            if wb is not None:
                bright[k] = float(wb.mean())

    valid = np.isfinite(ndvi)
    print(f"  with NDVI        : {int(valid.sum()):,} / {len(missed):,}")

    # stratum assignment
    stratum = np.full(len(missed), "", dtype=object)
    stratum[valid & (ndvi < args.ndvi_lo)] = "low_ndvi"
    stratum[valid & (ndvi >= args.ndvi_lo) & (ndvi < args.ndvi_hi)] = "mid_ndvi"
    stratum[valid & (ndvi >= args.ndvi_hi)] = "other_highndvi"

    # lon/lat for reporting
    lon, lat = rasterio.warp.transform("EPSG:3857", "EPSG:4326", mx, my)
    lon, lat = np.array(lon), np.array(lat)
    area = gdf["area_m2"].values[missed]
    cids = gdf["crown_id"].values[missed]
    hgt = height_m[missed]

    print("\n  stratum counts (pooled missed):")
    for s in STRATA:
        print(f"    {s:15s} {int((stratum == s).sum()):>6,}")

    if args.dry_run:
        print("\n[dry-run] no render. re-run without --dry-run to build montages.")
        return

    # ── 5. sample n per stratum, spatially spread ────────────────────────────
    def spread_pick(idx, n, min_sep):
        order = rng.permutation(idx)
        chosen, cxs, cys = [], [], []
        for i in order:
            if all((mx[i] - px) ** 2 + (my[i] - py) ** 2 >= min_sep ** 2
                   for px, py in zip(cxs, cys)):
                chosen.append(i); cxs.append(mx[i]); cys.append(my[i])
                if len(chosen) >= n:
                    break
        if len(chosen) < n:          # relax spacing if too few
            for i in order:
                if i not in chosen:
                    chosen.append(i)
                    if len(chosen) >= n:
                        break
        return chosen

    picks = {}
    for s in STRATA:
        idx = np.where(stratum == s)[0]
        picks[s] = spread_pick(idx, args.n, args.min_sep_m)
        print(f"  picked {len(picks[s]):>2d} for {s}")

    OUT_LOCAL.mkdir(parents=True, exist_ok=True)
    (OUT_LOCAL / "chips").mkdir(exist_ok=True)

    # ── 6. render chips + montages ───────────────────────────────────────────
    def render_chip(ax, i):
        x, y = mx[i], my[i]
        h = args.chip_half_m
        b = (x - h, y - h, x + h, y + h)
        with rasterio.open(ortho_path) as o:
            win = _clamp_window(rasterio.windows.from_bounds(*b, transform=o.transform),
                                o.width, o.height)
            rgb = o.read([1, 2, 3], window=win)
            ext_b = rasterio.windows.bounds(win, o.transform)
        img = np.transpose(rgb, (1, 2, 0))
        x0, y0, x1, y1 = ext_b
        ax.imshow(img, extent=[x0, x1, y0, y1])
        # model-canopy overlay from the in-RAM 1 m mask
        r0, c0 = world_to_rc(mask_tf, [x0], [y1]); r1, c1 = world_to_rc(mask_tf, [x1], [y0])
        r0, c0, r1, c1 = int(r0[0]), int(c0[0]), int(r1[0]), int(c1[0])
        r0, r1 = max(0, r0), min(mask1.shape[0], r1 + 1)
        c0, c1 = max(0, c0), min(mask1.shape[1], c1 + 1)
        if r1 > r0 and c1 > c0:
            sub = mask1[r0:r1, c0:c1]
            over = np.zeros((*sub.shape, 4), np.float32)
            over[sub == 1] = (1, 0, 0, 0.35)         # model said canopy → red
            mb = rasterio.windows.bounds(rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0), mask_tf)
            ax.imshow(over, extent=[mb[0], mb[2], mb[1], mb[3]])
        # crown outline (yellow)
        geom = gdf.geometry.values[missed[i]]
        polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        for p in polys:
            xs, ys = p.exterior.xy
            ax.add_patch(MplPolygon(np.column_stack([xs, ys]), closed=True,
                                    fill=False, edgecolor="yellow", lw=1.3))
        ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)
        ax.set_xticks([]); ax.set_yticks([])
        nd = ndvi[i]
        ax.set_title(f"{cids[i]}\nNDVI {nd:.2f} · {hgt[i]:.0f}m · {area[i]:.0f}m² · "
                     f"cov {mfrac[i]:.2f}", fontsize=7)

    for s in STRATA:
        chips_dir = OUT_LOCAL / "chips" / s
        chips_dir.mkdir(parents=True, exist_ok=True)
        sel = picks[s]
        ncol, nrow = 5, int(np.ceil(args.n / 5))
        fig, axes = plt.subplots(nrow, ncol, figsize=(ncol * 2.6, nrow * 2.9))
        axes = np.atleast_1d(axes).ravel()
        for a in axes:
            a.axis("off")
        for j, i in enumerate(sel):
            axes[j].axis("on")
            render_chip(axes[j], i)
            # also save the individual chip
            f1, a1 = plt.subplots(figsize=(3.2, 3.4))
            render_chip(a1, i)
            f1.tight_layout(); f1.savefig(chips_dir / f"{cids[i]}.png", dpi=120,
                                          bbox_inches="tight"); plt.close(f1)
        fig.suptitle(f"MISSED TREES — {s}  (yellow=Phase-0 crown, red=model canopy)  "
                     f"n={len(sel)}", fontsize=11)
        fig.tight_layout(rect=(0, 0, 1, 0.97))
        out = OUT_LOCAL / f"{s}_montage.png"
        fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)
        print(f"  montage → {out}")

    # ── 7. CSV + summary ─────────────────────────────────────────────────────
    import csv as _csv
    sel_set = {i for s in STRATA for i in picks[s]}
    csv_path = OUT_LOCAL / "miss_examples.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = _csv.writer(fh)
        w.writerow(["crown_id", "lon", "lat", "stratum", "ndvi", "chm_m",
                    "area_m2", "brightness", "model_frac", "selected"])
        for i in range(len(missed)):
            if not stratum[i]:
                continue
            w.writerow([cids[i], f"{lon[i]:.6f}", f"{lat[i]:.6f}", stratum[i],
                        f"{ndvi[i]:.3f}", f"{hgt[i]:.1f}", f"{area[i]:.1f}",
                        f"{bright[i]:.1f}" if np.isfinite(bright[i]) else "",
                        f"{mfrac[i]:.3f}", int(i in sel_set)])
    print(f"  csv     → {csv_path}")

    def med(vals):
        v = np.asarray(vals, float); v = v[np.isfinite(v)]
        return float(np.median(v)) if v.size else float("nan")

    sm_path = OUT_LOCAL / "summary.txt"
    with open(sm_path, "w", encoding="utf-8") as fh:
        fh.write(f"MISSED-TREE EXAMPLES — {args.ndvi_year} NDVI, miss<{args.miss_frac}, "
                 f"CHM>={args.chm_min_m}m, pool={args.pool}\n")
        fh.write(f"candidate tall crowns tested: {len(tall):,}\n")
        fh.write(f"missed (model_frac<{args.miss_frac}): {len(missed):,}\n\n")
        fh.write(f"{'stratum':16s}{'count':>8s}{'med_NDVI':>10s}{'med_CHM':>9s}"
                 f"{'med_area':>10s}{'med_bright':>11s}\n")
        for s in STRATA:
            m = stratum == s
            fh.write(f"{s:16s}{int(m.sum()):>8,}{med(ndvi[m]):>10.3f}{med(hgt[m]):>9.1f}"
                     f"{med(area[m]):>10.1f}{med(bright[m]):>11.1f}\n")
    print(f"  summary → {sm_path}")
    print(open(sm_path, encoding="utf-8").read())

    # ── copy lightweight products to Drive (rule 3) ──────────────────────────
    if OUT_LOCAL != OUT_DRIVE:
        OUT_DRIVE.mkdir(parents=True, exist_ok=True)
        for s in STRATA:
            shutil.copy2(OUT_LOCAL / f"{s}_montage.png", OUT_DRIVE / f"{s}_montage.png")
        shutil.copy2(csv_path, OUT_DRIVE / "miss_examples.csv")
        shutil.copy2(sm_path, OUT_DRIVE / "summary.txt")
        drv_chips = OUT_DRIVE / "chips"
        if drv_chips.exists():
            shutil.rmtree(drv_chips)
        shutil.copytree(OUT_LOCAL / "chips", drv_chips)
        print(f"  copied montages+csv+chips → {OUT_DRIVE}")

    print("\n[miss-examples] DONE — review the 3 montages before staging annotation sites.")


if __name__ == "__main__":
    main()
