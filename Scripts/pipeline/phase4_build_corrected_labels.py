"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — build a CORRECTED-LABEL additions raster from NIR + LiDAR
  Edmonds Temporal Active Learning Pipeline

  WHY
    The per-year model UNDER-predicts canopy (2016 honest recall ~0.60):
    it misses tall green DECIDUOUS stands (the Edmonds marsh) the conifer-
    only labels never taught it. phase4_qc_* uses the independent 2016
    NIR+CHM signal to MEASURE those misses. This script inverts that
    instrument to LABEL them: where NDVI says vegetation AND the CHM says
    tall (high-confidence), that is independently-confirmed real canopy.

    It does NOT rewrite the 148k×212k 7.5 cm 2020 mask. It writes a small
    ADDITIONS raster on the 2016 grid that the coarse tiler layers on top
    of the 2020 mask at train time (ADD-ONLY):

        canopy_additions_2016.tif  (uint8, on the 2016 imagery grid)
          0   = no change   (keep whatever the 2020 mask says here)
          1   = ADD canopy  (NDVI>=veg_thresh AND height>=min_height)
          2   = IGNORE       (uncertain: green but only moderately tall)
          255 = nodata       (outside 2016 imagery coverage)

    Because most trees are static, the SAME additions raster is reused for
    2000 (the coarse tiler reprojects it onto 2000's grid; outside the 2016
    strip there are no additions, so 2000 falls back to the plain 2020 mask).

  PRINCIPLE
    ADD-ONLY. This never turns a 2020-canopy pixel into background, and it
    marks the uncertain boundary band IGNORE rather than forcing it — so a
    recall lift cannot come at the cost of teaching against real trees.
    Thresholds default TIGHTER than the QC reference (0.3 / 3 m vs 0.2 / 2 m)
    to keep tall shrubs/hedges out and protect precision. All swept + logged.

  MEASUREMENT CAVEAT
    Once NDVI+CHM makes labels it is no longer an INDEPENDENT yardstick on
    the corrected pixels. Use --holdout-frac to leave a column strip
    UNCORRECTED (additions suppressed there) so recall can still be scored
    honestly on ground the labels never touched; default 0.0 (correct all —
    honest number then comes from photo-interp / the precision guard).

  USAGE (local Windows or Colab; rasterio auto-installs; torch-free)
    py -3.12 phase4_build_corrected_labels.py                    # 2016 defaults
    py -3.12 phase4_build_corrected_labels.py --veg-thresh 0.3 --min-height-m 3.0
    py -3.12 phase4_build_corrected_labels.py --holdout-frac 0.2 --holdout-side east
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import datetime as _dt
import importlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# ── Dependency bootstrap ──────────────────────────────────────────────────────

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
from rasterio.windows import Window
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ── Environment / paths ───────────────────────────────────────────────────────
# Lake paths: ONE home (pipeline/lake.py, refactor 2.4). The strict probe it
# carries is the correct one — the bare .exists() this file used was true
# whenever the mount POINT existed, mounted or not.
from lake import BASE  # noqa: E402

_LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")
_DRIVE_IMG = BASE / "Full_Image" / "Pipeline Imagery"
IMAGERY_DIRS = [d for d in (_LOCAL_IMG, _DRIVE_IMG) if d.exists()] or [_DRIVE_IMG]

OUT_DIR  = BASE / "phase4" / "labels_corrected"
EVAL_DIR = BASE / "phase4" / "eval"
LOGS_DIR = BASE / "phase4" / "logs"
CHM_NAME = "lidar_snoh_chm.tif"          # 3DEP HAG, U8 DN, 0.2 m/DN, 0 = nodata
CHM_DN_PER_M = 1.0 / 0.2

# NIR-bearing years: imagery filename + 1-based NIR band index (all R,G,B,NIR)
# DERIVED from config.YEAR_CATALOG, never restated. Until 2026-08-31 this was a
# literal dict whose four filenames had all lost their resolution token
# ("2016_snoh_rgbi.tif" for "2016_snoh_1ft_rgbi.tif", and three more). Both names
# exist on disk, so every .exists() passed while the stale files covered 39.6-67%
# of the authoritative extent. Deriving fixes the instance AND the class, and picks
# up all 10 NIR-bearing acquisitions instead of 4. See names.py::nir_years.
from phase4seg import config
from phase4seg import config as _C            # noqa: E402
from phase4seg.config import resolve_imagery as _resolve_imagery  # noqa: E402
from phase4seg.names import clean_argv, nir_years as _nir_years
from pipeline_log import write_step_log

NIR_CATALOG = {k: {"file": e["native_file"], "nir": int(e["bands"])}
               for k, e in _nir_years(_C.YEAR_CATALOG).items()}

# Marsh test window (the standing deciduous-miss case) for the preview.
MARSH_LON, MARSH_LAT = -122.3837, 47.8027


def resolve_img(fname):
    """Delegates to config.resolve_imagery — the ONE resolution order (refactor 2.5).
    Same contract as the loop it replaces: returns the path, raises
    FileNotFoundError when no root answers. The (path, root) pair is available at
    the shared home for callers that need to record which root answered."""
    p, _root = _resolve_imagery(fname)
    return p


def resolve_chm():
    for d in IMAGERY_DIRS + [_DRIVE_IMG]:
        p = d / CHM_NAME
        if p.exists():
            return p
    raise FileNotFoundError(f"{CHM_NAME} not found in {[str(d) for d in IMAGERY_DIRS]}")


def dn_to_height_m(dn):
    """CHM uint8 DN → height in metres. DN 0 = nodata → NaN."""
    h = (dn.astype(np.float32) - 1.0) / CHM_DN_PER_M
    h[dn == 0] = np.nan
    return h


# ── Core build ────────────────────────────────────────────────────────────────
def build_additions(year, veg_thresh, min_height_m, uncertain_lo_m,
                    ignore_nochm_green, holdout_frac, holdout_side,
                    block_rows):
    meta = NIR_CATALOG[year]
    img_path = resolve_img(meta["file"])
    chm_path = resolve_chm()
    nir_b = meta["nir"]

    print(f"[corrected-labels] year={year}")
    print(f"    imagery = {img_path}")
    print(f"    chm     = {chm_path}")
    print(f"    ADD canopy where NDVI>={veg_thresh} AND height>={min_height_m} m")
    print(f"    IGNORE band: green AND {uncertain_lo_m} m <= height < {min_height_m} m"
          f"{' (+ green w/o CHM)' if ignore_nochm_green else ''}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        tmp_tif = Path(td) / f"canopy_additions_{year}.tif"
        with rasterio.open(img_path) as img:
            prof = img.profile.copy()
            prof.update(count=1, dtype="uint8", nodata=255,
                        compress="deflate", predictor=2, zlevel=9,
                        tiled=True, blockxsize=512, blockysize=512,
                        BIGTIFF="IF_SAFER")
            H, W = img.height, img.width

            # Hold-out: suppress additions in a column strip so recall can be
            # scored honestly on ground the labels never touched.
            hstrip = int(round(holdout_frac * W)) if holdout_frac > 0 else 0
            if hstrip and holdout_side == "east":
                holdout_cols = slice(W - hstrip, W)
            elif hstrip:                                   # west
                holdout_cols = slice(0, hstrip)
            else:
                holdout_cols = None

            tot = dict(nodata=0, imaged=0, add=0, ignore=0, nochange=0,
                       holdout_suppressed=0)

            with WarpedVRT(rasterio.open(chm_path), crs=img.crs,
                           transform=img.transform, width=W, height=H,
                           resampling=Resampling.nearest,
                           src_nodata=0, nodata=0) as chm_vrt, \
                 rasterio.open(tmp_tif, "w", **prof) as dst:

                n_blocks = (H + block_rows - 1) // block_rows
                for bi, row0 in enumerate(range(0, H, block_rows)):
                    rows = min(block_rows, H - row0)
                    win = Window(0, row0, W, rows)

                    rgbi = img.read([1, 2, 3, nir_b], window=win).astype(np.float32)
                    r, nir = rgbi[0], rgbi[3]
                    coverage = rgbi.sum(0) > 0
                    ndvi = (nir - r) / (nir + r + 1e-6)

                    height = dn_to_height_m(chm_vrt.read(1, window=win))
                    has_chm = ~np.isnan(height)
                    h_fill = np.nan_to_num(height, nan=-1.0)

                    green = coverage & (ndvi >= veg_thresh)
                    add = green & has_chm & (h_fill >= min_height_m)
                    ign = green & has_chm & (h_fill >= uncertain_lo_m) & (h_fill < min_height_m)
                    if ignore_nochm_green:
                        ign = ign | (green & ~has_chm)

                    out = np.zeros((rows, W), dtype=np.uint8)       # 0 = nochange
                    out[~coverage] = 255                            # nodata
                    out[ign] = 2
                    out[add] = 1                                    # add wins over ignore

                    if holdout_cols is not None:
                        col0 = holdout_cols.start or 0
                        col1 = holdout_cols.stop or W
                        sup = np.zeros((rows, W), dtype=bool)
                        sup[:, col0:col1] = True
                        changed = sup & np.isin(out, (1, 2))
                        tot["holdout_suppressed"] += int(changed.sum())
                        out[changed] = 0                            # revert to nochange

                    dst.write(out, 1, window=win)
                    tot["nodata"]   += int((out == 255).sum())
                    tot["imaged"]   += int((out != 255).sum())
                    tot["add"]      += int((out == 1).sum())
                    tot["ignore"]   += int((out == 2).sum())
                    tot["nochange"] += int((out == 0).sum())

                    if bi % 5 == 0 or bi == n_blocks - 1:
                        print(f"    block {bi+1}/{n_blocks} (row {row0}/{H})", flush=True)

        # local NVMe → validate → copy to Drive (CLAUDE.md rule 3)
        out_tif = OUT_DIR / f"canopy_additions_{year}.tif"
        shutil.copy2(tmp_tif, out_tif)

    _write_summary(year, out_tif, veg_thresh, min_height_m, uncertain_lo_m,
                   ignore_nochm_green, holdout_frac, holdout_side, tot,
                   img_path, chm_path)
    return out_tif, tot


def _pct(n, d):
    return 100.0 * n / d if d else 0.0


def _write_summary(year, out_tif, veg_thresh, min_height_m, uncertain_lo_m,
                   ignore_nochm_green, holdout_frac, holdout_side, tot,
                   img_path, chm_path):
    imaged = tot["imaged"]
    L = [f"Corrected-label ADDITIONS raster — year {year}",
         f"  imagery      : {img_path}",
         f"  chm          : {chm_path}",
         f"  output       : {out_tif}",
         f"  rule         : ADD canopy where NDVI>={veg_thresh} AND height>={min_height_m} m",
         f"  ignore band  : green AND {uncertain_lo_m}<=height<{min_height_m} m"
         f"{' + green w/o CHM' if ignore_nochm_green else ''}",
         f"  holdout      : frac={holdout_frac} side={holdout_side}"
         f"  ({tot['holdout_suppressed']:,} px suppressed → left at baseline)",
         "",
         f"  imaged px    : {imaged:,}",
         f"  ADD canopy(1): {tot['add']:,}  ({_pct(tot['add'],imaged):.2f}% of imaged)  <-- new positives",
         f"  IGNORE   (2) : {tot['ignore']:,}  ({_pct(tot['ignore'],imaged):.2f}%)",
         f"  no change(0) : {tot['nochange']:,}  ({_pct(tot['nochange'],imaged):.2f}%)",
         f"  nodata (255) : {tot['nodata']:,}",
         "",
         "  NEXT (Colab): retile+retrain the coarse years with this as the",
         "  add-only overlay on the 2020 mask:",
         f"    phase4_semantic_finetune.py --year 2016 --step tile "
         f"--add-canopy-mask {out_tif}",
         f"    phase4_semantic_finetune.py --year 2016 --step train --hs-source chm",
         "    ... then --step inference postproc evaluate; score vs 2016 NDVI",
         "    (phase4_qc_score.py) — precision/grass-rejection must hold."]
    txt = out_tif.with_suffix(".txt")
    txt.write_text("\n".join(L), encoding="utf-8")
    print("\n" + "\n".join(L))
    print(f"\n[corrected-labels] wrote {out_tif}\n[corrected-labels] wrote {txt}")
    # E06b: machine-readable lineage sidecar — future overlays are born stamped.
    # (The 2016 artifact predates this; qc/instruments/stamp_label_lineage.py backfills it
    # READ-ONLY — never re-run this builder for lineage: the fixed filename +
    # mtime bump would spuriously invalidate the overlay's tile-signature key.)
    import datetime as _dt
    import hashlib as _hl
    import json as _json
    h = _hl.sha256()
    with open(out_tif, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    lineage = {
        "source_year": year, "imagery": str(img_path), "chm": str(chm_path),
        "veg_thresh": veg_thresh, "min_height_m": min_height_m,
        "uncertain_lo_m": uncertain_lo_m,
        "holdout": {"frac": holdout_frac, "side": holdout_side},
        "pixel_counts": dict(tot),
        "size": out_tif.stat().st_size, "sha256": h.hexdigest(),
        "build_date": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "builder_script": "phase4_build_corrected_labels.py",
    }
    lj = out_tif.with_suffix(".lineage.json")
    lj.write_text(_json.dumps(lineage, indent=2), encoding="utf-8")
    print(f"[corrected-labels] wrote {lj}")


# ── Marsh preview ─────────────────────────────────────────────────────────────
def _read_window_any(path, bounds_wgs84, bands, resamp=Resampling.nearest):
    with rasterio.open(path) as src:
        b = rasterio.warp.transform_bounds("EPSG:4326", src.crs, *bounds_wgs84)
        win = rasterio.windows.from_bounds(*b, transform=src.transform)
        win = win.round_offsets(op="floor").round_lengths(op="ceil")
        win = win.intersection(Window(0, 0, src.width, src.height))
        if win.width <= 0 or win.height <= 0:
            return None
        return src.read(bands, window=win, resampling=resamp)


def _resize_to(a, shape):
    yi = np.clip((np.arange(shape[0]) * a.shape[0] / shape[0]).astype(int), 0, a.shape[0]-1)
    xi = np.clip((np.arange(shape[1]) * a.shape[1] / shape[1]).astype(int), 0, a.shape[1]-1)
    return a[yi][:, xi]


def preview(year, out_tif, lon, lat, radius_m):
    meta = NIR_CATALOG[year]
    dlat = radius_m / 111320.0
    dlon = radius_m / (111320.0 * np.cos(np.radians(lat)))
    bounds = (lon - dlon, lat - dlat, lon + dlon, lat + dlat)

    rgbi = _read_window_any(resolve_img(meta["file"]), bounds, [1, 2, 3, meta["nir"]])
    if rgbi is None:
        print("    ! marsh window outside imagery — skipping preview")
        return None
    rgb = np.transpose(rgbi[:3], (1, 2, 0)).astype(np.uint8)
    shp = rgb.shape[:2]
    r = rgbi[0].astype(np.float32); nir = rgbi[3].astype(np.float32)
    ndvi = _resize_to((nir - r) / (nir + r + 1e-6), shp)

    chm = _read_window_any(resolve_chm(), bounds, [1])
    chm = _resize_to(dn_to_height_m(chm[0]), shp) if chm is not None else None
    add = _read_window_any(out_tif, bounds, [1])
    add = _resize_to(add[0], shp) if add is not None else None

    cols = [("RGB (2016)", rgb, None), ("NDVI", ndvi, "RdYlGn"),
            ("CHM height (m)", chm, "viridis"), ("additions", add, None)]
    fig, axes = plt.subplots(1, len(cols), figsize=(4 * len(cols), 4.4))
    for ax, (title, data, cmap) in zip(axes, cols):
        if data is None:
            ax.axis("off"); continue
        if title == "additions":                       # 0 grey,1 green add,2 amber ign
            disp = np.stack([np.transpose(rgbi[:3], (1, 2, 0)).astype(np.uint8)] * 1)[0]
            over = disp.copy()
            over[data == 1] = [0, 224, 160]
            over[data == 2] = [240, 190, 60]
            ax.imshow(over)
        elif title == "NDVI":
            ax.imshow(data, cmap=cmap, vmin=-0.3, vmax=0.8)
        elif cmap is None:
            ax.imshow(data)
        else:
            ax.imshow(data, cmap=cmap)
        ax.set_title(title, fontsize=10); ax.axis("off")
    fig.suptitle(f"Corrected labels — marsh @ ({lon},{lat}) — {year}\n"
                 f"green = ADDED canopy, amber = IGNORE band", fontsize=12)
    fig.tight_layout()
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out = EVAL_DIR / f"corrected_labels_preview_{year}.png"
    fig.savefig(out, dpi=115, bbox_inches="tight"); plt.close(fig)
    print(f"[corrected-labels] wrote {out}")
    return out



def main():
    filtered = clean_argv()
    ap = argparse.ArgumentParser(
        description="Build an ADD-ONLY corrected-label raster from NIR+CHM.")
    ap.add_argument("--year", default="2016", choices=sorted(NIR_CATALOG))
    ap.add_argument("--veg-thresh", type=float, default=0.3,
                    help="NDVI cutoff for the ADD stratum (default 0.3; QC ref uses 0.2).")
    ap.add_argument("--min-height-m", type=float, default=3.0,
                    help="CHM height (m) to ADD canopy (default 3.0; QC ref uses 2.0).")
    ap.add_argument("--uncertain-lo-m", type=float, default=2.0,
                    help="Lower height (m) of the IGNORE band (default 2.0).")
    ap.add_argument("--ignore-nochm-green", action="store_true",
                    help="Also IGNORE green pixels with no CHM coverage (default off: "
                         "leave them to the 2020 mask).")
    ap.add_argument("--holdout-frac", type=float, default=0.0,
                    help="Fraction of columns left UNCORRECTED for honest scoring "
                         "(default 0.0 = correct everything).")
    ap.add_argument("--holdout-side", choices=["east", "west"], default="east")
    ap.add_argument("--radius-m", type=float, default=400.0, help="marsh preview radius")
    ap.add_argument("--block-rows", type=int, default=2048)
    ap.add_argument("--no-preview", action="store_true")
    args = ap.parse_args(filtered)

    out_tif, tot = build_additions(
        args.year, args.veg_thresh, args.min_height_m, args.uncertain_lo_m,
        args.ignore_nochm_green, args.holdout_frac, args.holdout_side,
        args.block_rows)
    if not args.no_preview:
        preview(args.year, out_tif, MARSH_LON, MARSH_LAT, args.radius_m)
    write_step_log("phase4_build_corrected_labels", step=str(args.year), logs_dir=LOGS_DIR,
                   output=str(out_tif), veg_thresh=args.veg_thresh,
                   min_height_m=args.min_height_m, add_px=tot["add"],
                   ignore_px=tot["ignore"], holdout_suppressed=tot["holdout_suppressed"])


if __name__ == "__main__":
    main()
