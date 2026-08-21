r"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — SENTINEL SNAPSHOTS (visual model progress through time)
  Edmonds Temporal Active Learning Pipeline

  WHY
    Metrics say WHAT changed; sentinels show WHERE. After each run this
    renders the SAME fixed windows (Scripts/sentinel_sites.json: forest
    training sites, the deciduous marsh miss, grass negatives, controls)
    as RGB | RGB+mask-overlay panels, filed per run. Flip a site across
    runs (--filmstrip) to SEE recall filling in or grass-FP creeping back.
    Registry row for the run lives in Scripts/run_registry.csv (rule 9).

  PRODUCES
    phase4/runs/{run_id}/sentinels/{site}_{year}.png     per-site panel
    phase4/runs/_filmstrips/{site}_{year}.png            one site x all runs

  USAGE (local preferred — reads D:\edmonds-pipeline\Imagery, no torch):
    py -3.12 phase4_sentinel_snap.py --year 2016 --run-id 20260706_2016_v044_corrected-full
    py -3.12 phase4_sentinel_snap.py --year 2016 --run-id ... --mask path\to\prob.tif --thresh 0.4615
    py -3.12 phase4_sentinel_snap.py --filmstrip marsh_deciduous --year 2016
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import datetime as _dt
import importlib
import json
import subprocess
import sys
from pathlib import Path


def _pip(spec):
    print(f"  • installing {spec} …")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", spec], check=True)

for _imp, _spec in [("rasterio", "rasterio"), ("numpy", "numpy"),
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
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
# require a real tree, not just the dir: an empty stray C:\content\... exists locally
# (probe a DATA-plane landmark: Scripts/ left Drive for the D: git repo, 2026-08-20)
BASE = _COLAB_BASE if (_COLAB_BASE / "Full_Image").exists() else _LOCAL_BASE

_LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")
_DRIVE_IMG = BASE / "Full_Image" / "Pipeline Imagery"
IMAGERY_DIRS = [d for d in (_LOCAL_IMG, _DRIVE_IMG) if d.exists()] or [_DRIVE_IMG]

SITES_JSON = Path(__file__).resolve().parents[1] / "sentinel_sites.json"  # config travels with code
MASKS      = BASE / "phase4" / "masks"
RUNS_DIR   = BASE / "phase4" / "runs"
LOGS_DIR   = BASE / "phase4" / "logs"

# year -> imagery file (native ortho; NIR years end _rgbi)
IMG_CATALOG = {
    "2000": "2000_king_rgb.tif",
    "2015": "2015_king_rgb.tif",
    "2016": "2016_snoh_rgbi.tif",
    "2019n": "2019_naip_rgbi.tif",
    "2021s": "2021_snoh_rgbi.tif",
    "2022n": "2022_naip_rgbi.tif",
}


def resolve(fname):
    for d in IMAGERY_DIRS:
        p = d / fname
        if p.exists():
            return p
    raise FileNotFoundError(f"{fname} not found in {[str(d) for d in IMAGERY_DIRS]}")


def site_bounds(site):
    """WGS84 (W,S,E,N) for a site entry — explicit bounds or lon/lat/radius."""
    if "bounds_wgs84" in site:
        return tuple(site["bounds_wgs84"])
    lon, lat, r = site["lon"], site["lat"], site.get("radius_m", 250.0)
    dlat = r / 111320.0
    dlon = r / (111320.0 * np.cos(np.radians(lat)))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def read_window(path, bounds_wgs84, bands=None):
    """Window read across CRSs (same approach as phase4_qc_site.read_window)."""
    with rasterio.open(path) as src:
        b = rasterio.warp.transform_bounds("EPSG:4326", src.crs, *bounds_wgs84)
        win = rasterio.windows.from_bounds(*b, transform=src.transform)
        win = win.round_offsets(op="floor").round_lengths(op="ceil")
        try:
            win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
        except rasterio.errors.WindowError:   # window entirely outside raster
            return None
        if win.width <= 0 or win.height <= 0:
            return None
        idx = bands if bands is not None else list(range(1, src.count + 1))
        return src.read(idx, window=win, resampling=Resampling.nearest)


def _resize_to(a, shape):
    yi = np.clip((np.arange(shape[0]) * a.shape[0] / shape[0]).astype(int), 0, a.shape[0]-1)
    xi = np.clip((np.arange(shape[1]) * a.shape[1] / shape[1]).astype(int), 0, a.shape[1]-1)
    return a[yi][:, xi]


def canopy_from_mask(path, bounds, shape, thresh):
    """Boolean canopy layer from a prob raster (0-254, 255 nodata) or binary mask."""
    a = read_window(path, bounds, bands=[1])
    if a is None:
        return None
    a = a[0]
    if "prob" in Path(path).name.lower():
        p = a.astype(np.float32)
        p[a == 255] = np.nan
        return _resize_to(p / 254.0, shape) >= thresh
    m = a.astype(np.float32)
    m[a == 255] = np.nan
    return _resize_to(m, shape) == 1


def snap(year, run_id, mask_path, thresh, only_sites):
    sites = json.loads(SITES_JSON.read_text(encoding="utf-8"))["sites"]
    if only_sites:
        sites = [s for s in sites if s["name"] in only_sites]
    img_path = resolve(IMG_CATALOG[year])
    out_dir = RUNS_DIR / run_id / "sentinels"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[sentinel] year={year} run={run_id}\n  imagery={img_path}\n  mask={mask_path}")

    n_ok = 0
    for site in sites:
        name = site["name"]
        bounds = site_bounds(site)
        rgbi = read_window(img_path, bounds, bands=[1, 2, 3])
        if rgbi is None:
            print(f"  ! {name}: outside {year} imagery extent — skipped")
            continue
        rgb = np.transpose(rgbi, (1, 2, 0)).astype(np.uint8)
        canopy = canopy_from_mask(mask_path, bounds, rgb.shape[:2], thresh)

        overlay = rgb.copy()
        pct = float("nan")
        if canopy is not None:
            green = np.array([0, 220, 60], dtype=np.float32)
            sel = canopy.astype(bool)
            overlay[sel] = (0.55 * overlay[sel].astype(np.float32)
                            + 0.45 * green).astype(np.uint8)
            pct = 100.0 * sel.mean()

        fig, axes = plt.subplots(1, 2, figsize=(9, 4.6))
        axes[0].imshow(rgb); axes[0].set_title("RGB", fontsize=10)
        axes[1].imshow(overlay)
        axes[1].set_title(f"model canopy ({pct:.1f}% of window)", fontsize=10)
        for ax in axes:
            ax.axis("off")
        fig.suptitle(f"{name} — {year} — {run_id}", fontsize=11)
        fig.tight_layout()
        png = out_dir / f"{name}_{year}.png"
        fig.savefig(png, dpi=110, bbox_inches="tight"); plt.close(fig)
        n_ok += 1
        print(f"  ✓ {name}: canopy {pct:.1f}%  → {png.name}")
    print(f"[sentinel] {n_ok}/{len(sites)} sites written → {out_dir}")
    _log(f"snap_{run_id}", year)


def filmstrip(site_name, year):
    """Stitch one site's panel across all runs (sorted by run_id) into a strip."""
    frames = sorted(RUNS_DIR.glob(f"*/sentinels/{site_name}_{year}.png"))
    frames = [f for f in frames if f.parts[-3] != "_filmstrips"]
    if not frames:
        sys.exit(f"no frames found for {site_name}_{year} under {RUNS_DIR}")
    imgs = [plt.imread(f) for f in frames]
    fig, axes = plt.subplots(len(imgs), 1, figsize=(9, 4.8 * len(imgs)))
    if len(imgs) == 1:
        axes = [axes]
    for ax, img, f in zip(axes, imgs, frames):
        ax.imshow(img); ax.axis("off")
        ax.set_title(f.parts[-3], fontsize=9, loc="left")
    fig.tight_layout()
    out = RUNS_DIR / "_filmstrips"
    out.mkdir(parents=True, exist_ok=True)
    png = out / f"{site_name}_{year}.png"
    fig.savefig(png, dpi=110, bbox_inches="tight"); plt.close(fig)
    print(f"[sentinel] filmstrip ({len(imgs)} runs) → {png}")
    _log(f"filmstrip_{site_name}", year)


def _log(step, year):
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (LOGS_DIR / f"phase4_sentinel_snap_{step}_{ts}.log").write_text(
            f"phase4_sentinel_snap.py {step} {year}\n", encoding="utf-8")
    except Exception:
        pass


def main():
    filtered = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
    ap = argparse.ArgumentParser(description="Fixed-site visual progress snapshots.")
    ap.add_argument("--year", default="2016", choices=sorted(IMG_CATALOG))
    ap.add_argument("--run-id", help="registry run_id; names phase4/runs/{run_id}/")
    ap.add_argument("--mask", help="prob or binary mask raster "
                    "(default: masks/edmonds_canopy_prob_{year}.tif, else _mask_)")
    ap.add_argument("--thresh", type=float, default=0.4615,
                    help="canopy threshold when --mask is a prob raster")
    ap.add_argument("--sites", nargs="*", help="subset of site names")
    ap.add_argument("--filmstrip", metavar="SITE",
                    help="stitch SITE across all runs instead of snapping")
    args = ap.parse_args(filtered)

    if args.filmstrip:
        filmstrip(args.filmstrip, args.year)
        return
    if not args.run_id:
        sys.exit("--run-id is required (use the run_registry.csv run_id)")
    mask = Path(args.mask) if args.mask else None
    if mask is None:
        for cand in (MASKS / f"edmonds_canopy_prob_{args.year}.tif",
                     MASKS / f"edmonds_canopy_mask_{args.year}.tif"):
            if cand.exists():
                mask = cand
                break
    if mask is None or not mask.exists():
        sys.exit(f"no mask found for {args.year} — pass --mask")
    snap(args.year, args.run_id, mask, args.thresh, args.sites)


if __name__ == "__main__":
    main()
