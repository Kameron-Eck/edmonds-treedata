"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — Year 2000 Label Review Preparation (one-time)
  Edmonds Temporal Active Learning Pipeline

  Extracts expanded training regions from the 2000 ortho, overlays
  2020 crown polygons, and produces a QGIS-ready review package.

  The reviewer opens each site's GeoTIFF + crown GeoPackage in QGIS
  and marks each crown as approved / rejected / uncertain for 2000.
  Everything in the expanded region NOT marked as an approved crown
  becomes labeled background — fixing the negative scarcity.

  WHAT IT PRODUCES (per site):
    {site}_2000_crop.tif          Native-res 2000 imagery
    {site}_crowns_review.gpkg     2020 crowns with review fields
    {site}_regions.gpkg           Reviewed-extent polygon (background vs ignore)
    {site}_preview.png            Quick-look overlay image

  Plus:
    review_regions.gpkg           Expanded bounding boxes (all sites)
    review_summary.txt            Tile counts, crown counts, area
    all_crowns_review.gpkg        Combined crowns across all sites

  USAGE (Colab — run once):
    %run phase4_label_review_prep.py
    %run phase4_label_review_prep.py --buffer 250
    %run phase4_label_review_prep.py --sites Forest_3,Negative_Parking

  Then download phase4/review/2000/ and open in QGIS.
╚══════════════════════════════════════════════════════════════════╝
"""

from phase4seg.names import clean_argv
import argparse
import importlib
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# ── Dependency bootstrap ──────────────────────────────────────────────────────
def _pip(spec):
    print(f"  • installing {spec} …")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", spec], check=True)

for _imp, _spec in [("rasterio", "rasterio"), ("geopandas", "geopandas"),
                     ("matplotlib", "matplotlib"), ("numpy", "numpy"),
                     ("shapely", "shapely"), ("fiona", "fiona")]:
    try:
        importlib.import_module(_imp)
    except ImportError:
        _pip(_spec)

import numpy as np
import geopandas as gpd
import rasterio
import rasterio.mask
import rasterio.warp
import rasterio.windows
from rasterio.enums import Resampling
from shapely.geometry import box
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch


# ── Paths ─────────────────────────────────────────────────────────────────────
BASE          = Path("/content/drive/MyDrive/treedata")
PHOTOS_DIR    = BASE / "photos"
POLYGONS_DIR  = BASE / "polygons"
IMAGERY_DIR   = BASE / "Full_Image/Pipeline Imagery"
NATIVE_DIR    = IMAGERY_DIR / "native"
INFERENCE_DIR = BASE / "inference"
OUT_DIR       = BASE / "phase4" / "review" / "2000"

ORTHO_2000    = "2000_king_rgb.tif"
CITY_CROWNS   = INFERENCE_DIR / "edmonds_crowns_2020.gpkg"
CROWN_CRS     = "EPSG:3857"

# Tiling params (from phase4_semantic_finetune.py, coarse tier)
TILE_SIZE     = 512
COARSE_STRIDE = 128
GSD_2000      = 0.597   # metres per pixel


# ── Site discovery ────────────────────────────────────────────────────────────
def discover_sites(filter_sites=None):
    """Read training-site footprints from photos/*_rgb.tif bounds."""
    sites = []
    for photo in sorted(PHOTOS_DIR.glob("*_rgb.tif")):
        name = photo.stem.replace("_rgb", "")
        if filter_sites and name not in filter_sites:
            continue
        with rasterio.open(photo) as src:
            b = src.bounds
            crs = src.crs
        if crs is not None and str(crs) != CROWN_CRS:
            b = rasterio.coords.BoundingBox(
                *rasterio.warp.transform_bounds(crs, CROWN_CRS, *b))
        sites.append(dict(
            name=name,
            bounds=b,
            is_negative="Negative" in name,
            photo_path=photo,
        ))
    return sites


def expand_bounds(bounds, buffer_m):
    """Expand a BoundingBox by buffer_m on each side (CRS must be in metres)."""
    return rasterio.coords.BoundingBox(
        bounds.left   - buffer_m,
        bounds.bottom - buffer_m,
        bounds.right  + buffer_m,
        bounds.top    + buffer_m,
    )


def bounds_to_shapely(bounds):
    return box(bounds.left, bounds.bottom, bounds.right, bounds.top)


def _gpkg_safe(gdf):
    """Drop FID + Esri auto-fields (Shape_Length/Area, often truncated to
    SHAPE_Leng/SHAPE_Area) and case-duplicate columns; reset index."""
    geom_name = gdf.geometry.name
    drop_lower = {"fid", "shape_leng", "shape_length", "shape_area",
                  "shape_le_1", "shape_ar_1"}
    keep, seen = [], {geom_name.lower()}
    for c in gdf.columns:
        if c == geom_name:
            continue
        lc = str(c).lower()
        if lc in drop_lower or lc in seen:
            continue
        seen.add(lc)
        keep.append(c)
    return gdf[keep + [geom_name]].reset_index(drop=True)


# ── Crown loading ─────────────────────────────────────────────────────────────
def load_hand_traced_crowns(site_name):
    """Load hand-traced crown polygons for a single training site."""
    shp = POLYGONS_DIR / f"{site_name}.shp"
    if not shp.exists():
        return None
    gdf = gpd.read_file(shp)
    if gdf.crs is None:
        gdf = gdf.set_crs(CROWN_CRS)
    elif str(gdf.crs) != CROWN_CRS:
        gdf = gdf.to_crs(CROWN_CRS)
    gdf["source"] = "hand_traced"
    return gdf


def load_city_crowns_in_bbox(bounds):
    """Load model-predicted 2020 crowns within a bounding box."""
    if not CITY_CROWNS.exists():
        print(f"  ⚠ City-wide crowns not found at {CITY_CROWNS}")
        return None
    bbox = (bounds.left, bounds.bottom, bounds.right, bounds.top)
    try:
        gdf = gpd.read_file(CITY_CROWNS, bbox=bbox)
    except Exception as e:
        print(f"  ⚠ Could not read city crowns: {e}")
        return None
    if gdf.crs is not None and str(gdf.crs) != CROWN_CRS:
        gdf = gdf.to_crs(CROWN_CRS)
    gdf["source"] = "model_predicted"
    return gdf


def merge_crown_sources(hand_traced, city_crowns, original_bounds):
    """
    Within the original site footprint: use hand-traced crowns only.
    In the expanded buffer: use model-predicted crowns.
    This avoids duplicates where both sources overlap.
    """
    parts = []
    orig_poly = bounds_to_shapely(original_bounds)

    if hand_traced is not None and len(hand_traced) > 0:
        parts.append(hand_traced)

    if city_crowns is not None and len(city_crowns) > 0:
        # Only keep model predictions OUTSIDE the original footprint
        # (hand-traced crowns are the authority inside it)
        if hand_traced is not None and len(hand_traced) > 0:
            outside = city_crowns[~city_crowns.geometry.intersects(orig_poly)]
            if len(outside) > 0:
                parts.append(outside)
        else:
            # No hand-traced crowns (negative site) — use all model predictions
            parts.append(city_crowns)

    if not parts:
        return gpd.GeoDataFrame(columns=["geometry", "source"],
                                geometry="geometry", crs=CROWN_CRS)
    merged = gpd.GeoDataFrame(
        __import__("pandas").concat(parts, ignore_index=True),
        geometry="geometry", crs=CROWN_CRS
    )
    return merged


def add_review_fields(gdf, site_name):
    """Add the temporal-anchor review fields."""
    gdf = gdf.copy()
    # Assign sequential crown IDs within this site
    if "crown_id" not in gdf.columns:
        gdf["crown_id"] = [f"{site_name}_{i:04d}" for i in range(len(gdf))]
    gdf["site"]       = site_name
    gdf["status"]     = "pending"   # pending / approved / rejected / uncertain
    gdf["valid_from"] = None        # year (int) — filled by reviewer
    gdf["valid_to"]   = None        # year (int) — filled by reviewer
    gdf["notes"]      = ""          # free text for reviewer
    return gdf


# ── Ortho cropping ────────────────────────────────────────────────────────────
def resolve_ortho():
    for p in (NATIVE_DIR / ORTHO_2000, IMAGERY_DIR / ORTHO_2000):
        if p.exists():
            return p
    raise FileNotFoundError(
        f"2000 ortho '{ORTHO_2000}' not found in {NATIVE_DIR} or {IMAGERY_DIR}")


def crop_ortho(ortho_path, bounds, out_path):
    """Crop the 2000 ortho to the expanded bounds at native resolution."""
    crop_poly = bounds_to_shapely(bounds)
    with rasterio.open(ortho_path) as src:
        # Check CRS match
        if str(src.crs) != CROWN_CRS:
            xbounds = rasterio.warp.transform_bounds(
                CROWN_CRS, src.crs, *bounds)
            crop_poly = bounds_to_shapely(
                rasterio.coords.BoundingBox(*xbounds))

        out_image, out_transform = rasterio.mask.mask(
            src, [crop_poly.__geo_interface__],
            crop=True, filled=True, nodata=0)
        out_meta = src.meta.copy()
        out_meta.update({
            "height": out_image.shape[1],
            "width":  out_image.shape[2],
            "transform": out_transform,
            "compress": "deflate",
        })
        with rasterio.open(out_path, "w", **out_meta) as dst:
            dst.write(out_image)
    h, w = out_image.shape[1], out_image.shape[2]
    return w, h, out_image


# ── Tile count estimation ─────────────────────────────────────────────────────
def estimate_tiles(w_px, h_px, tile_size=TILE_SIZE, stride=COARSE_STRIDE):
    if w_px < tile_size or h_px < tile_size:
        return 1   # undersized → padded to one tile
    rows = len(range(0, h_px - tile_size + 1, stride))
    cols = len(range(0, w_px - tile_size + 1, stride))
    return max(rows * cols, 1)


# ── Preview rendering ─────────────────────────────────────────────────────────
def render_preview(crop_image, crowns_gdf, site_name, original_bounds,
                   expanded_bounds, out_path, gsd):
    """Render a preview image: 2000 crop + crown outlines + original footprint."""
    # Downsample for display if large
    bands, h, w = crop_image.shape
    max_dim = 1800
    scale = max(w, h) / max_dim
    if scale > 1:
        dw, dh = int(w / scale), int(h / scale)
    else:
        dw, dh = w, h
        scale = 1.0

    rgb = np.transpose(crop_image[:3], (1, 2, 0))
    if scale > 1:
        from PIL import Image
        rgb = np.array(Image.fromarray(rgb).resize((dw, dh), Image.LANCZOS))

    fig, ax = plt.subplots(1, 1, figsize=(12, 12 * dh / dw + 1))
    ax.imshow(rgb, extent=[expanded_bounds.left, expanded_bounds.right,
                           expanded_bounds.bottom, expanded_bounds.top])

    # Draw original footprint as dashed rectangle
    ob = original_bounds
    rect = plt.Rectangle((ob.left, ob.bottom), ob.right - ob.left,
                          ob.top - ob.bottom,
                          linewidth=2, edgecolor="cyan", facecolor="none",
                          linestyle="--", label="Original footprint")
    ax.add_patch(rect)

    # Draw crowns
    n_ht = n_mp = 0
    if len(crowns_gdf) > 0:
        for _, row in crowns_gdf.iterrows():
            color = "#FFD700" if row.get("source") == "hand_traced" else "#FF4444"
            if row.get("source") == "hand_traced":
                n_ht += 1
            else:
                n_mp += 1
            geom = row.geometry
            if geom.geom_type == "Polygon":
                xs, ys = geom.exterior.xy
                ax.plot(xs, ys, color=color, linewidth=0.8, alpha=0.8)
            elif geom.geom_type == "MultiPolygon":
                for part in geom.geoms:
                    xs, ys = part.exterior.xy
                    ax.plot(xs, ys, color=color, linewidth=0.8, alpha=0.8)

    legend_items = [
        Patch(edgecolor="cyan", facecolor="none", linestyle="--",
              label="Original footprint"),
    ]
    if n_ht > 0:
        legend_items.append(
            Patch(edgecolor="#FFD700", facecolor="none",
                  label=f"Hand-traced ({n_ht})"))
    if n_mp > 0:
        legend_items.append(
            Patch(edgecolor="#FF4444", facecolor="none",
                  label=f"Model-predicted ({n_mp})"))

    ax.legend(handles=legend_items, loc="upper right", fontsize=9)
    ax.set_title(f"{site_name} — 2000 expanded region "
                 f"({w}×{h} px, ~{w*gsd:.0f}×{h*gsd:.0f} m)",
                 fontsize=12)
    ax.set_xlabel("easting (m)")
    ax.set_ylabel("northing (m)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return n_ht, n_mp


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    filtered = clean_argv()
    p = argparse.ArgumentParser(
        description="Phase 4 — Extract expanded 2000 training regions for review")
    p.add_argument("--buffer", type=float, default=200.0,
                   help="Expansion buffer around each site in metres (default 200)")
    p.add_argument("--sites", default=None,
                   help="Comma-separated site names (default: all)")
    p.add_argument("--out-dir", default=None,
                   help="Output directory (default: phase4/review/2000/)")
    p.add_argument("--neg-buffer", type=float, default=None,
                   help="Separate buffer for negative sites (default: 1.5× main buffer)")
    args = p.parse_args(filtered)

    buffer_m = args.buffer
    neg_buffer = args.neg_buffer or buffer_m * 1.5
    filter_sites = set(args.sites.split(",")) if args.sites else None
    out_dir = Path(args.out_dir) if args.out_dir else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    from pipeline_log import StepLogger
    LOGS_DIR = BASE / "phase4" / "logs"
    SCRIPT_NAME = "phase4_label_review_prep"

    print(f"\n{'='*65}")
    print(f"  PHASE 4 — Year 2000 Label Review Preparation")
    print(f"{'='*65}")
    print(f"  Buffer:      {buffer_m:.0f} m (positive sites)")
    print(f"               {neg_buffer:.0f} m (negative sites)")
    print(f"  Output:      {out_dir}")

    # ── Discover sites + resolve ortho ────────────────────────────────────────
    with StepLogger(SCRIPT_NAME, "discover", LOGS_DIR) as log:
        sites = discover_sites(filter_sites)
        print(f"  Sites:       {len(sites)}")
        for s in sites:
            tag = "(negative)" if s["is_negative"] else "(positive)"
            print(f"    {s['name']:<20} {tag}")

        # ── Resolve 2000 ortho ────────────────────────────────────────────────
        ortho_path = resolve_ortho()
        print(f"  Ortho:       {ortho_path}")
        log.finish(sites=len(sites), errors=0)

    # ── Process each site ─────────────────────────────────────────────────────
    all_crowns = []
    region_rows = []
    summary_lines = [
        f"Phase 4 — Year 2000 Label Review Preparation",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Buffer: {buffer_m:.0f}m (positive), {neg_buffer:.0f}m (negative)",
        f"Ortho: {ortho_path.name}",
        f"GSD: {GSD_2000*100:.1f} cm",
        "",
        f"{'Site':<20} {'Orig px':<14} {'Expanded px':<14} {'Tiles':>6} "
        f"{'Hand':>5} {'Model':>6} {'Total':>6}",
        "-" * 80,
    ]

    log_extract = StepLogger(SCRIPT_NAME, "extract", LOGS_DIR)
    log_extract.start()
    for site in sites:
        name = site["name"]
        orig_bounds = site["bounds"]
        buf = neg_buffer if site["is_negative"] else buffer_m
        exp_bounds = expand_bounds(orig_bounds, buf)

        print(f"\n── {name} (buffer {buf:.0f}m) ──")

        # Check if site is within ortho coverage
        with rasterio.open(ortho_path) as src:
            ortho_bounds = src.bounds
        exp_poly = bounds_to_shapely(exp_bounds)
        ortho_poly = bounds_to_shapely(ortho_bounds)
        if not exp_poly.intersects(ortho_poly):
            print(f"  ⚠ Expanded region outside ortho extent — skipping")
            continue

        # Clip expanded bounds to ortho extent
        clipped = rasterio.coords.BoundingBox(
            max(exp_bounds.left, ortho_bounds.left),
            max(exp_bounds.bottom, ortho_bounds.bottom),
            min(exp_bounds.right, ortho_bounds.right),
            min(exp_bounds.top, ortho_bounds.top),
        )
        if clipped.right <= clipped.left or clipped.top <= clipped.bottom:
            print(f"  ⚠ No overlap after clipping — skipping")
            continue

        # Crop ortho
        crop_path = out_dir / f"{name}_2000_crop.tif"
        w, h, crop_img = crop_ortho(ortho_path, clipped, crop_path)
        print(f"  Crop: {w}×{h} px ({w*GSD_2000:.0f}×{h*GSD_2000:.0f} m)")

        # Check for nodata (all-black)
        nonzero = np.any(crop_img > 0, axis=0).sum()
        total = w * h
        coverage = nonzero / total if total > 0 else 0
        if coverage < 0.05:
            print(f"  ⚠ {coverage*100:.1f}% non-zero pixels — likely nodata, skipping")
            crop_path.unlink(missing_ok=True)
            continue
        print(f"  Coverage: {coverage*100:.1f}% non-zero pixels")

        # Load crowns
        ht = load_hand_traced_crowns(name)
        n_ht_loaded = len(ht) if ht is not None else 0
        city = load_city_crowns_in_bbox(clipped)
        n_city_loaded = len(city) if city is not None else 0
        print(f"  Crowns loaded: {n_ht_loaded} hand-traced, "
              f"{n_city_loaded} model-predicted in bbox")

        # Merge: hand-traced inside original footprint, model elsewhere
        merged = merge_crown_sources(ht, city, orig_bounds)
        merged = add_review_fields(merged, name)

        # Clip to expanded bounds
        clip_poly = bounds_to_shapely(clipped)
        if len(merged) > 0:
            merged = merged[merged.geometry.intersects(clip_poly)]

        print(f"  Crowns for review: {len(merged)} "
              f"({(merged['source']=='hand_traced').sum()} hand-traced, "
              f"{(merged['source']=='model_predicted').sum()} model-predicted)")

        # Estimate tiles
        tiles = estimate_tiles(w, h)
        print(f"  Estimated tiles (stride {COARSE_STRIDE}): {tiles}")

        # Save per-site crown GeoPackage
        crown_path = out_dir / f"{name}_crowns_review.gpkg"
        if len(merged) > 0:
            _gpkg_safe(merged).to_file(crown_path, driver="GPKG")
        print(f"  ✓ {crown_path.name}")

        # Save per-site reviewed-extent polygon. This is the file
        # phase4_semantic_finetune.py reads as polygons/{site}_regions.gpkg:
        # inside it → confirmed background; outside it → IGNORE. The reviewer
        # may shrink/redraw this in QGIS to mark only the area they verified.
        region_path = out_dir / f"{name}_regions.gpkg"
        gpd.GeoDataFrame(
            {"site": [name], "reviewed": [1]},
            geometry=[bounds_to_shapely(clipped)], crs=CROWN_CRS
        ).to_file(region_path, driver="GPKG")
        print(f"  ✓ {region_path.name}")

        # Preview
        preview_path = out_dir / f"{name}_preview.png"
        n_ht_drawn, n_mp_drawn = render_preview(
            crop_img, merged, name, orig_bounds, clipped,
            preview_path, GSD_2000)
        print(f"  ✓ {preview_path.name}")

        # Accumulate
        all_crowns.append(merged)
        region_rows.append({
            "site": name,
            "is_negative": site["is_negative"],
            "buffer_m": buf,
            "geometry": clip_poly,
            "orig_w_m": (orig_bounds.right - orig_bounds.left),
            "orig_h_m": (orig_bounds.top - orig_bounds.bottom),
            "exp_w_m": (clipped.right - clipped.left),
            "exp_h_m": (clipped.top - clipped.bottom),
            "w_px": w, "h_px": h,
            "tiles": tiles,
            "n_hand_traced": n_ht_drawn,
            "n_model_predicted": n_mp_drawn,
        })

        orig_w = int((orig_bounds.right - orig_bounds.left) / GSD_2000)
        orig_h = int((orig_bounds.top - orig_bounds.bottom) / GSD_2000)
        summary_lines.append(
            f"{name:<20} {orig_w:>5}×{orig_h:<5}  {w:>5}×{h:<5}  "
            f"{tiles:>6} {n_ht_drawn:>5} {n_mp_drawn:>6} "
            f"{n_ht_drawn+n_mp_drawn:>6}")

    log_extract.finish(sites=len(region_rows),
                       crowns=sum(len(c) for c in all_crowns), errors=0)

    # ── Save combined outputs ─────────────────────────────────────────────────
    log_write = StepLogger(SCRIPT_NAME, "write", LOGS_DIR)
    log_write.start()
    print(f"\n── Combined outputs ──")

    # Review regions GeoPackage
    if region_rows:
        regions_gdf = gpd.GeoDataFrame(region_rows, geometry="geometry",
                                       crs=CROWN_CRS)
        regions_path = out_dir / "review_regions.gpkg"
        _gpkg_safe(regions_gdf).to_file(regions_path, driver="GPKG")
        print(f"  ✓ {regions_path.name} ({len(regions_gdf)} regions)")

    # Combined crowns
    if all_crowns:
        import pandas as pd
        combined = gpd.GeoDataFrame(
            pd.concat(all_crowns, ignore_index=True),
            geometry="geometry", crs=CROWN_CRS)
        combined_path = out_dir / "all_crowns_review.gpkg"
        _gpkg_safe(combined).to_file(combined_path, driver="GPKG")
        print(f"  ✓ {combined_path.name} ({len(combined)} crowns total)")

    # Summary
    total_tiles = sum(r["tiles"] for r in region_rows)
    total_crowns = sum(len(c) for c in all_crowns)
    summary_lines += [
        "-" * 80,
        f"{'TOTAL':<20} {'':14} {'':14} {total_tiles:>6} "
        f"{sum(r['n_hand_traced'] for r in region_rows):>5} "
        f"{sum(r['n_model_predicted'] for r in region_rows):>6} "
        f"{total_crowns:>6}",
        "",
        "REVIEW WORKFLOW:",
        "  1. Download phase4/review/2000/ to your local machine",
        "  2. Open each {site}_2000_crop.tif in QGIS",
        "  3. Add {site}_crowns_review.gpkg as a vector layer on top",
        "  4. For each crown polygon, set the 'status' field:",
        "       approved  — tree visibly present in 2000 imagery",
        "       rejected  — bare ground, not planted yet, or removed",
        "       uncertain — can't tell at this resolution",
        "  5. Set valid_from / valid_to years for approved crowns",
        "       (e.g., valid_from=2000, valid_to=2020 for a tree confirmed",
        "        in both years)",
        "  6. (optional) Edit {site}_regions.gpkg to shrink the reviewed extent",
        "       to only the area you actually verified. Inside it = labeled",
        "       background; outside it = IGNORE (excluded from training).",
        "  7. Copy the edited {site}_crowns_review.gpkg and {site}_regions.gpkg",
        "       into  /content/drive/MyDrive/treedata/polygons/  on Drive.",
        "  8. Re-run:  %run phase4_semantic_finetune.py --year 2000",
        "       It auto-detects the review files, burns only approved/in-interval",
        "       crowns as canopy, marks reviewed non-crown area as background,",
        "       and ignores everything else.",
        "",
        f"  At {GSD_2000*100:.0f}cm with stride {COARSE_STRIDE}, "
        f"the expanded regions yield ~{total_tiles} tiles",
        f"  (vs ~48 tiles from the original footprints).",
    ]

    summary_path = out_dir / "review_summary.txt"
    summary_path.write_text("\n".join(summary_lines))
    print(f"  ✓ {summary_path.name}")

    log_write.finish(regions=len(region_rows), crowns=total_crowns, errors=0)

    print(f"\n{'='*65}")
    print(f"  Ready for review: {out_dir}")
    print(f"  {len(region_rows)} sites, ~{total_tiles} tiles, "
          f"{total_crowns} crowns to review")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
