"""
╔══════════════════════════════════════════════════════════════════╗
  Stage a POSITIVE (canopy) training site — labels derived from the
  Phase-3 2020 canopy mask.  Edmonds Temporal Active Learning Pipeline

  WHY
    phase4_qc_score.py proved the per-year model UNDER-predicts canopy,
    and phase4_qc_site.py localised the worst misses to the Edmonds marsh:
    tall, green, DECIDUOUS crowns the conifer-only training sites never
    taught the model. The FIX is a deciduous positive training site.

    BUT a positive site is NOT a drop-in crop. phase4_semantic_finetune.py
    demotes any site WITHOUT a crown-polygon file to a pure NEGATIVE — it
    would burn the real marsh canopy as background and make things worse.
    A positive site needs crown polygons (EPSG:3857, status='approved',
    valid_from/valid_to). This script DERIVES those polygons by
    polygonising the Phase-3 2020 canopy mask (which already labels the
    marsh at ~35% canopy) inside the site footprint — no hand-tracing.

  SCOPE
    Benefits the FINE/MEDIUM years (2015, 2013, 2017, 2019 …) whose labels
    come from per-site crowns — including the 2015 flagship that stands in
    for ~2016. The coarse 2016 model itself trains on the citywide 2020
    mask and ignores curated positive sites (handle separately if needed).

  SAFE STAGED FLOW (mirrors make_grass_negatives.py)
    default : write crop + derived crowns + a verification preview into
              photos/_positive_staging/ and polygons/_positive_staging/.
              NOTHING enters the training set. Review the preview first.
    --commit: copy the named site's {name}_rgb.tif -> photos/ and
              {name}_crowns_review.gpkg -> polygons/. THEN retile+train.

  USAGE (local; rasterio/geopandas/shapely auto-install)
    py -3.12 make_positive_site.py --name Positive_Marsh \
        --lon -122.3837 --lat 47.8027 --half-m 350
    py -3.12 make_positive_site.py --name Positive_Marsh --commit
╚══════════════════════════════════════════════════════════════════╝
"""

from phase4seg.names import clean_argv
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
import rasterio.features
import geopandas as gpd
from shapely.geometry import shape, box
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


_COLAB_BASE = Path("/content/drive/MyDrive/treedata")
_LOCAL_BASE = Path(r"G:\My Drive\treedata")
BASE = _COLAB_BASE if _COLAB_BASE.exists() else _LOCAL_BASE

_LOCAL_IMG = Path(r"D:\edmonds-pipeline\Imagery")
_DRIVE_IMG = BASE / "Full_Image" / "Pipeline Imagery"
IMAGERY_DIRS = [d for d in (_LOCAL_IMG, _DRIVE_IMG) if d.exists()] or [_DRIVE_IMG]

PHOTOS_DIR   = BASE / "photos"
POLY_DIR     = BASE / "polygons"
PHOTOS_STAGE = PHOTOS_DIR / "_positive_staging"
POLY_STAGE   = POLY_DIR / "_positive_staging"
EVAL_DIR     = BASE / "phase4" / "eval"
MASK_2020    = BASE / "phase3" / "edmonds_canopy_mask_2020.tif"
CROWN_CRS    = "EPSG:3857"

# Footprint crop source (content is for VISUAL verification; bounds are what
# the pipeline uses). 2015 = the flagship year, local, full-city, hi-res.
CROP_SRC_CANDIDATES = ["2015_king_rgb.tif", "2020_coe_rgb.tif", "2016_snoh_rgbi.tif"]


def resolve(names):
    names = [names] if isinstance(names, str) else names
    for n in names:
        for d in IMAGERY_DIRS:
            p = d / n
            if p.exists():
                return p
    raise FileNotFoundError(f"none of {names} in {[str(d) for d in IMAGERY_DIRS]}")


def crop_footprint(name, lon, lat, half_m):
    src = resolve(CROP_SRC_CANDIDATES)
    with rasterio.open(src) as s:
        cx, cy = rasterio.warp.transform("EPSG:4326", s.crs, [lon], [lat])
        cx, cy = cx[0], cy[0]
        b = (cx - half_m, cy - half_m, cx + half_m, cy + half_m)
        win = rasterio.windows.from_bounds(*b, transform=s.transform)
        win = win.round_offsets(op="floor").round_lengths(op="ceil")
        win = win.intersection(rasterio.windows.Window(0, 0, s.width, s.height))
        arr = s.read([1, 2, 3], window=win)
        tf = s.window_transform(win)
        prof = s.profile.copy()
        prof.update(count=3, height=arr.shape[1], width=arr.shape[2],
                    transform=tf, compress="lzw", dtype="uint8")
        footprint_bounds = rasterio.windows.bounds(win, s.transform)
    PHOTOS_STAGE.mkdir(parents=True, exist_ok=True)
    out = PHOTOS_STAGE / f"{name}_rgb.tif"
    with rasterio.open(out, "w", **prof) as dst:
        dst.write(arr)
    print(f"  crop  → {out}  ({arr.shape[2]}x{arr.shape[1]} px from {src.name})")
    return out, arr, footprint_bounds, str(rasterio.open(src).crs)


def derive_crowns(name, footprint_bounds, src_crs, min_area_m2, valid_from, valid_to):
    """Polygonise the 2020 canopy mask inside the footprint → approved crowns."""
    if not MASK_2020.exists():
        raise FileNotFoundError(f"2020 mask not found: {MASK_2020}")
    with rasterio.open(MASK_2020) as m:
        b = footprint_bounds
        if str(m.crs) != str(src_crs):
            b = rasterio.warp.transform_bounds(src_crs, m.crs, *footprint_bounds)
        win = rasterio.windows.from_bounds(*b, transform=m.transform)
        win = win.round_offsets(op="floor").round_lengths(op="ceil")
        win = win.intersection(rasterio.windows.Window(0, 0, m.width, m.height))
        arr = m.read(1, window=win)
        tf = m.window_transform(win)
        canopy = (arr == 1).astype(np.uint8)         # 0 bg, 1 canopy, 255 ignore
        geoms = [shape(g) for g, v in
                 rasterio.features.shapes(canopy, mask=canopy == 1, transform=tf)
                 if v == 1]
        mask_crs = m.crs
    if not geoms:
        raise RuntimeError("no canopy polygons found in footprint — check location")
    gdf = gpd.GeoDataFrame(geometry=geoms, crs=mask_crs).to_crs(CROWN_CRS)
    # CRS-UNIT TRAP (2026-08-27): CROWN_CRS is EPSG:3857 (Web Mercator), which is
    # conformal, not equal-area — at Edmonds (47.81°N) `.area` is inflated
    # 1/cos²(lat) = 2.215x. `area_m2` below is kept in that inflated form ONLY to
    # stay schema-compatible with polygons/*_crowns_review.gpkg and with
    # phase0_instance_seg's crowns, which carry the same inflation (measured
    # 2.2215x). `area_m2_true` is the honest number and is what gets REPORTED.
    # NOTE the --min-area-m2 filter therefore still selects on inflated area:
    # a "2.0 m²" floor is really ~0.9 m² of ground.
    gdf["area_m2"] = gdf.geometry.area
    gdf["area_m2_true"] = gdf.to_crs("EPSG:26910").geometry.area
    gdf = gdf[gdf["area_m2"] >= float(min_area_m2)].reset_index(drop=True)
    gdf["geometry"] = gdf.geometry.buffer(0)          # repair
    # schema matching polygons/Forest_*_crowns_review.gpkg
    gdf["id"] = None
    gdf["source"] = "derived_2020mask"
    gdf["crown_id"] = [f"{name}_{i:05d}" for i in range(len(gdf))]
    gdf["diameter_m"] = np.nan
    gdf["size_class"] = None
    gdf["dtm_peak"] = np.nan
    gdf["dtm_mean"] = np.nan
    gdf["site"] = name
    gdf["status"] = "approved"
    gdf["valid_from"] = int(valid_from)
    gdf["valid_to"] = int(valid_to)
    gdf["notes"] = "auto-derived from phase3 2020 canopy mask; REVIEW before commit"
    cols = ["id", "source", "crown_id", "area_m2", "diameter_m", "size_class",
            "dtm_peak", "dtm_mean", "site", "status", "valid_from", "valid_to",
            "notes", "geometry"]
    # keep the TRUE total as a scalar before the schema-fixing column select —
    # area_m2_true is deliberately NOT written, so the staged GPKG stays
    # schema-identical to polygons/Forest_*_crowns_review.gpkg
    true_ha = float(gdf["area_m2_true"].sum()) / 1e4
    gdf = gdf[cols]
    POLY_STAGE.mkdir(parents=True, exist_ok=True)
    out = POLY_STAGE / f"{name}_crowns_review.gpkg"
    gdf.to_file(out, driver="GPKG")
    print(f"  crowns→ {out}  ({len(gdf)} polygons ≥{min_area_m2} m² [3857-inflated], "
          f"canopy area {true_ha:.2f} ha TRUE, "
          f"valid {valid_from}-{valid_to})")
    return out, gdf, footprint_bounds, true_ha


def preview(name, rgb, gdf, footprint_bounds, src_crs, true_ha=None):
    """RGB crop with derived crown outlines overlaid — verify the labels."""
    img = np.transpose(rgb, (1, 2, 0))
    x0, y0, x1, y1 = footprint_bounds
    g = gdf.to_crs(src_crs) if str(gdf.crs) != str(src_crs) else gdf
    fig, ax = plt.subplots(1, 2, figsize=(13, 6.4))
    for a in ax:
        a.imshow(img, extent=[x0, x1, y0, y1]); a.set_xticks([]); a.set_yticks([])
    ax[0].set_title(f"{name} — footprint (2015 imagery)", fontsize=11)
    for geom in g.geometry:
        polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        for p in polys:
            xs, ys = p.exterior.xy
            ax[1].plot(xs, ys, color="#00E0A0", lw=0.6)
    ax[1].set_title(f"derived canopy crowns  (n={len(gdf)}, "
                    f"{true_ha:.1f} ha true)" if true_ha is not None
                    else f"derived canopy crowns  (n={len(gdf)})", fontsize=11)
    ax[1].set_xlim(x0, x1); ax[1].set_ylim(y0, y1)
    fig.suptitle(f"{name} — REVIEW: do the green outlines match real tree canopy?",
                 fontsize=12)
    fig.tight_layout()
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out = EVAL_DIR / f"positive_site_preview_{name}.png"
    fig.savefig(out, dpi=115, bbox_inches="tight"); plt.close(fig)
    print(f"  preview→ {out}")
    return out


def commit(name):
    rgb = PHOTOS_STAGE / f"{name}_rgb.tif"
    crn = POLY_STAGE / f"{name}_crowns_review.gpkg"
    if not (rgb.exists() and crn.exists()):
        raise FileNotFoundError(f"staged files missing for {name}; run the default step first")
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True); POLY_DIR.mkdir(parents=True, exist_ok=True)
    d1 = PHOTOS_DIR / f"{name}_rgb.tif"; d2 = POLY_DIR / f"{name}_crowns_review.gpkg"
    shutil.copy2(rgb, d1); shutil.copy2(crn, d2)
    print(f"  committed → {d1}\n  committed → {d2}")
    print("  NEXT (Colab): phase4_semantic_finetune.py --year 2015 --step labels → tile "
          "→ train → inference → postproc → evaluate; then phase4_qc_score.py vs 2016 NDVI.")


def main():
    filtered = clean_argv()
    ap = argparse.ArgumentParser(description="Stage a positive canopy training site.")
    ap.add_argument("--name", default="Positive_Marsh")
    ap.add_argument("--lon", type=float, default=-122.3837)
    ap.add_argument("--lat", type=float, default=47.8027)
    ap.add_argument("--half-m", type=float, default=350.0, help="half box width (m)")
    ap.add_argument("--min-area-m2", type=float, default=3.0,
                    help="drop canopy polygons smaller than this")
    ap.add_argument("--valid-from", type=int, default=2005)
    ap.add_argument("--valid-to", type=int, default=2020)
    ap.add_argument("--commit", action="store_true",
                    help="copy the staged site into photos/ and polygons/")
    args = ap.parse_args(filtered)

    if args.commit:
        commit(args.name)
        return
    print(f"[positive-site] staging {args.name} @ ({args.lon},{args.lat}) half={args.half_m}m")
    crop_out, rgb, fbounds, src_crs = crop_footprint(args.name, args.lon, args.lat, args.half_m)
    crn_out, gdf, _, true_ha = derive_crowns(args.name, fbounds, src_crs, args.min_area_m2,
                                    args.valid_from, args.valid_to)
    preview(args.name, rgb, gdf, fbounds, src_crs, true_ha)
    print("\n[positive-site] STAGED — review the preview PNG, then re-run with --commit.")
    print("  labels are AUTO-DERIVED from the 2020 mask; confirm they match real crowns.")


if __name__ == "__main__":
    main()
