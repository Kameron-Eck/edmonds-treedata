"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — QC: independent NDVI canopy reference (model-independent)
  Edmonds Temporal Active Learning Pipeline

  WHY
    Every recall number to date is scored against the 2020 crown mask
    reprojected onto other years — CIRCULAR (real pre-2020 change counts
    as model "error"). To tell whether the model UNDER-predicts we need a
    reference that never saw the model or the 2020 labels.

    The NIR-bearing years (2016 snoh, 2019n/2023n NAIP) give us that for
    free: NDVI = (NIR - R) / (NIR + R) flags live vegetation independently.
    But raw NDVI counts GRASS as vegetation — the model rejects grass on
    purpose — so an honest CANOPY reference is:

        canopy = (NDVI >= veg_thresh) AND (CHM height >= min_height)

    i.e. vegetation that is also TALL. For 2016 the CHM is temporally
    matched (both ~2016), so 2016 is the cleanest instrument; NAIP years
    pair with the 2016 CHM with a temporal caveat (see --note).

  PRODUCES (phase4/qc/):
    ndvi_ref_{year}.tif   uint8 categorical, aligned to the year's imagery
                            0 = non-vegetation
                            1 = grass  (vegetated, short / no CHM height)
                            2 = canopy (vegetated AND tall) — the recall ref
                          255 = nodata (no imagery coverage)
    ndvi_ref_{year}.txt   class fractions + NDVI distribution + a threshold
                          sweep so the veg/height cutoffs are transparent

  NOTE
    This is a QC REFERENCE, not a model input. veg_thresh / min_height are
    QC design choices (defaults below), NOT model hyperparameters — they
    are swept and reported so the choice is auditable.

  USAGE (local Windows or Colab; rasterio auto-installs):
    py -3.12 phase4_qc_ndvi.py --year 2016
    py -3.12 phase4_qc_ndvi.py --year 2016 --veg-thresh 0.2 --min-height-m 2.0
    py -3.12 phase4_qc_ndvi.py --year 2019n
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import datetime as _dt
import importlib
import subprocess
import sys
from pathlib import Path


# ── Dependency bootstrap ──────────────────────────────────────────────────────
def _pip(spec):
    print(f"  • installing {spec} …")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", spec], check=True)

for _imp, _spec in [("rasterio", "rasterio"), ("numpy", "numpy")]:
    try:
        importlib.import_module(_imp)
    except ImportError:
        _pip(_spec)

import numpy as np
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.windows import Window


# ── Environment / paths ───────────────────────────────────────────────────────
# Runs LOCALLY (Windows, imagery on D:) or on Colab (Drive mount). Detect.
_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE

# Imagery: prefer the fast local mirror on D:, fall back to the Drive originals.
_LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")
_DRIVE_IMG = BASE / "Full_Image" / "Pipeline Imagery"
IMAGERY_DIRS = [d for d in (_LOCAL_IMG, _DRIVE_IMG) if d.exists()] or [_DRIVE_IMG]

QC_DIR   = BASE / "phase4" / "qc"
LOGS_DIR = BASE / "phase4" / "logs"
CHM_NAME = "lidar_snoh_chm.tif"          # 3DEP HAG, U8 DN, 0.2 m/DN, 0 = nodata
CHM_DN_PER_M = 1.0 / 0.2                  # DN = 1 + round(height_m / 0.2)

# NIR-bearing years: imagery filename + 1-based NIR band index (all are R,G,B,NIR)
NIR_CATALOG = {
    "2016":  {"file": "2016_snoh_rgbi.tif", "nir": 4, "chm_matched": True},
    "2019n": {"file": "2019_naip_rgbi.tif", "nir": 4, "chm_matched": False},
    "2023n": {"file": "2023_naip_rgbi.tif", "nir": 4, "chm_matched": False},
    "2021s": {"file": "2021_snoh_rgbi.tif", "nir": 4, "chm_matched": False},
}


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
    raise FileNotFoundError(f"{CHM_NAME} not found in {[str(d) for d in IMAGERY_DIRS]}")


# ── Core ──────────────────────────────────────────────────────────────────────
def dn_to_height_m(dn):
    """CHM uint8 DN → height in metres. DN 0 = nodata → NaN."""
    h = (dn.astype(np.float32) - 1.0) / CHM_DN_PER_M
    h[dn == 0] = np.nan
    return h


def build_reference(year, veg_thresh, min_height_m, block_rows, sweep):
    meta = NIR_CATALOG[year]
    img_path = resolve_img(meta["file"])
    chm_path = resolve_chm()
    nir_b = meta["nir"]

    print(f"[qc-ndvi] year={year}")
    print(f"    imagery = {img_path}")
    print(f"    chm     = {chm_path}  (matched={meta['chm_matched']})")
    print(f"    veg_thresh(NDVI) = {veg_thresh}   min_height = {min_height_m} m")

    QC_DIR.mkdir(parents=True, exist_ok=True)
    out_tif = QC_DIR / f"ndvi_ref_{year}.tif"

    with rasterio.open(img_path) as img:
        prof = img.profile.copy()
        prof.update(count=1, dtype="uint8", nodata=255,
                    compress="deflate", predictor=2, zlevel=6,
                    tiled=True, blockxsize=512, blockysize=512,
                    BIGTIFF="IF_SAFER")
        H, W = img.height, img.width

        # accumulators for the summary
        tot = dict(nonveg=0, grass=0, canopy=0, nodata=0)
        ndvi_hist = np.zeros(201, dtype=np.int64)         # -1.00..1.00 @0.01
        # sweep accumulators: veg-only px and canopy px for each (vt, hm) combo
        sweep_veg = {round(v, 2): 0 for v in sweep["veg"]}
        sweep_can = {(round(v, 2), round(h, 1)): 0
                     for v in sweep["veg"] for h in sweep["height"]}

        # CHM reprojected onto the imagery grid, read window-by-window
        with WarpedVRT(rasterio.open(chm_path), crs=img.crs, transform=img.transform,
                       width=W, height=H, resampling=Resampling.nearest,
                       src_nodata=0, nodata=0) as chm_vrt, \
             rasterio.open(out_tif, "w", **prof) as dst:

            n_blocks = (H + block_rows - 1) // block_rows
            for bi, row0 in enumerate(range(0, H, block_rows)):
                rows = min(block_rows, H - row0)
                win = Window(0, row0, W, rows)

                rgbi = img.read([1, 2, 3, nir_b], window=win).astype(np.float32)
                r, nir = rgbi[0], rgbi[3]
                coverage = rgbi.sum(0) > 0                 # all-zero = no imagery
                ndvi = (nir - r) / (nir + r + 1e-6)

                chm_dn = chm_vrt.read(1, window=win)
                height = dn_to_height_m(chm_dn)            # NaN where no CHM

                veg = coverage & (ndvi >= veg_thresh)
                has_chm = np.isfinite(height)                    # CHM covers ~60% of the city
                tall = has_chm & (height >= min_height_m)
                canopy = veg & tall

                out = np.full((rows, W), 255, dtype=np.uint8)   # nodata
                out[coverage] = 0                                # non-veg
                out[veg] = 1                                     # grass (veg, short)
                out[veg & ~has_chm] = 255                        # veg but NO CHM → can't confirm tall → IGNORE (was wrongly 'grass', biasing recall/precision)
                out[canopy] = 2                                 # canopy (veg + CHM-confirmed tall)
                dst.write(out, 1, window=win)

                # tallies (count from out so the new IGNORE class is reflected)
                tot["nodata"] += int((out == 255).sum())         # nodata OR veg-without-CHM (excluded)
                tot["nonveg"] += int((out == 0).sum())
                tot["grass"]  += int((out == 1).sum())
                tot["canopy"] += int((out == 2).sum())
                nv = ndvi[coverage]
                if nv.size:
                    idx = np.clip(((nv + 1.0) * 100).astype(np.int32), 0, 200)
                    ndvi_hist += np.bincount(idx, minlength=201)
                for vt in sweep_veg:
                    vmask = coverage & (ndvi >= vt)
                    sweep_veg[vt] += int(vmask.sum())
                    for hm in sweep["height"]:
                        cm = vmask & (np.nan_to_num(height, nan=-1.0) >= hm)
                        sweep_can[(vt, round(hm, 1))] += int(cm.sum())

                if bi % 5 == 0 or bi == n_blocks - 1:
                    print(f"    block {bi+1}/{n_blocks} (row {row0}/{H})", flush=True)

    _write_summary(year, out_tif, veg_thresh, min_height_m, tot, ndvi_hist,
                   sweep, sweep_veg, sweep_can, img_path, chm_path, meta)
    return out_tif, tot


def _pct(n, d):
    return 100.0 * n / d if d else 0.0


def _write_summary(year, out_tif, veg_thresh, min_height_m, tot, ndvi_hist,
                   sweep, sweep_veg, sweep_can, img_path, chm_path, meta):
    total = sum(tot.values())
    imaged = total - tot["nodata"]
    edges = np.linspace(-1, 1, 201)
    cum = np.cumsum(ndvi_hist)
    n = cum[-1] if cum[-1] else 1
    def q(p):
        i = int(np.searchsorted(cum, p * n))
        return edges[min(i, 200)]

    lines = []
    lines.append(f"NDVI canopy reference — year {year}")
    lines.append(f"  imagery      : {img_path}")
    lines.append(f"  chm          : {chm_path}  (temporally matched = {meta['chm_matched']})")
    lines.append(f"  output       : {out_tif}")
    lines.append(f"  veg_thresh   : NDVI >= {veg_thresh}")
    lines.append(f"  min_height   : {min_height_m} m  (canopy = vegetated AND tall)")
    if not meta["chm_matched"]:
        lines.append("  CAVEAT       : CHM is the 2016 snapshot; height for this year is")
        lines.append("                 temporally offset — canopy class is approximate.")
    lines.append("")
    lines.append(f"  total px     : {total:,}")
    lines.append(f"  imaged px    : {imaged:,}  ({_pct(imaged,total):.1f}% of raster)")
    lines.append(f"  nodata px    : {tot['nodata']:,}  ({_pct(tot['nodata'],total):.1f}%)")
    lines.append("  — over imaged pixels —")
    lines.append(f"  non-veg (0)  : {tot['nonveg']:,}  ({_pct(tot['nonveg'],imaged):.1f}%)")
    lines.append(f"  grass   (1)  : {tot['grass']:,}  ({_pct(tot['grass'],imaged):.1f}%)")
    lines.append(f"  canopy  (2)  : {tot['canopy']:,}  ({_pct(tot['canopy'],imaged):.1f}%)  <-- recall reference")
    lines.append("")
    lines.append(f"  NDVI over imaged px: p10={q(.10):.3f} p50={q(.50):.3f} "
                 f"p90={q(.90):.3f}")
    lines.append("")
    lines.append("  THRESHOLD SWEEP (canopy % of imaged px):")
    lines.append("    veg_thr \\ height  " + "  ".join(f"{h:>5.1f}m" for h in sweep["height"]))
    for vt in sweep["veg"]:
        vt = round(vt, 2)
        row = [f"    NDVI>={vt:<4}      "]
        for hm in sweep["height"]:
            row.append(f"{_pct(sweep_can[(vt, round(hm,1))], imaged):>6.2f}")
        lines.append("  ".join(row))
    lines.append("")
    lines.append(f"  (veg-only % of imaged, by NDVI thr: " +
                 ", ".join(f"{round(vt,2)}={_pct(sweep_veg[round(vt,2)],imaged):.1f}%"
                           for vt in sweep["veg"]) + ")")

    txt = out_tif.with_suffix(".txt")
    txt.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n[qc-ndvi] wrote {out_tif}\n[qc-ndvi] wrote {txt}")


def write_step_log(year, out_tif, tot, args):
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        p = LOGS_DIR / f"phase4_qc_ndvi_ref_{ts}.log"
        imaged = sum(tot.values()) - tot["nodata"]
        p.write_text(
            f"phase4_qc_ndvi.py --step ref  year={year}\n"
            f"veg_thresh={args.veg_thresh} min_height_m={args.min_height_m}\n"
            f"output={out_tif}\n"
            f"canopy_px={tot['canopy']:,} grass_px={tot['grass']:,} "
            f"nonveg_px={tot['nonveg']:,} nodata_px={tot['nodata']:,}\n"
            f"canopy_pct_of_imaged={_pct(tot['canopy'], imaged):.2f}\n",
            encoding="utf-8")
        print(f"[qc-ndvi] log → {p}")
    except Exception as e:
        print(f"[qc-ndvi] WARN could not write log: {e}")


def main():
    filtered = [a for a in sys.argv[1:]
                if not (a == "-f" or a.endswith(".json"))]
    ap = argparse.ArgumentParser(description="Build an independent NDVI canopy reference.")
    ap.add_argument("--year", default="2016", choices=sorted(NIR_CATALOG),
                    help="NIR-bearing year to build a reference for.")
    ap.add_argument("--veg-thresh", type=float, default=0.2,
                    help="NDVI cutoff for live vegetation (default 0.2).")
    ap.add_argument("--min-height-m", type=float, default=2.0,
                    help="CHM height (m) separating canopy from grass (default 2.0).")
    ap.add_argument("--block-rows", type=int, default=2048,
                    help="Rows per streaming block (memory control).")
    args = ap.parse_args(filtered)

    sweep = {"veg": [0.10, 0.15, 0.20, 0.25, 0.30],
             "height": [1.0, 2.0, 3.0, 5.0]}
    out_tif, tot = build_reference(args.year, args.veg_thresh, args.min_height_m,
                                   args.block_rows, sweep)
    write_step_log(args.year, out_tif, tot, args)


if __name__ == "__main__":
    main()
