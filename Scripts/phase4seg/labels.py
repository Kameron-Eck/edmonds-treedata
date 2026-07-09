from phase4seg.config import *
from phase4seg import config
from phase4seg.common import (
    read_rgb_window, _site_window, _year_int, _load_review_regions,
    _load_coverage_overrides, _stage_imagery_local, _unstage_imagery_local,
    entry_for, resolve_native_path,
)

import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
import rasterio.features
import rasterio.transform
import rasterio.warp
import rasterio.windows
from rasterio.coords import BoundingBox
from rasterio.enums import Resampling


def anchor_mask_from_2020(dst_crs, dst_transform, h, w, prob_hi, prob_lo):
    """Build a 0/1/255 training mask for one crop from the 2020 full-city canopy
    probability raster (phase3/edmonds_canopy_prob_2020.tif).

    The crop's geographic footprint is read from the 2020 prob raster (decimated
    on read so the ~110 GB source never lands in RAM), aligned to the crop grid,
    then thresholded:  p >= prob_hi -> canopy (1),  p <= prob_lo -> background
    (0),  in-between or no 2020 coverage -> IGNORE (255).
    """
    if not PROB_2020.exists():
        raise FileNotFoundError(
            f"2020 canopy prob raster not found: {PROB_2020}\n"
            f"  --anchor-labels needs phase3/edmonds_canopy_prob_2020.tif")
    ignore = np.full((h, w), IGNORE_LABEL, dtype=np.uint8)
    dst_bounds = rasterio.transform.array_bounds(h, w, dst_transform)  # l,b,r,t
    with rasterio.open(PROB_2020) as psrc:
        pcrs, pnod = psrc.crs, psrc.nodata
        pb = rasterio.warp.transform_bounds(dst_crs, pcrs, *dst_bounds)
        src_win = rasterio.windows.from_bounds(*pb, transform=psrc.transform)
        src_win = src_win.round_offsets(op="floor").round_lengths(op="ceil")
        try:
            src_win = src_win.intersection(
                rasterio.windows.Window(0, 0, psrc.width, psrc.height))
        except rasterio.windows.WindowError:
            return ignore                   # crop fully outside 2020 coverage
        if src_win.width <= 0 or src_win.height <= 0:
            return ignore                       # crop outside 2020 coverage
        out_h = max(1, min(int(src_win.height), h))
        out_w = max(1, min(int(src_win.width),  w))
        src = psrc.read(1, window=src_win, out_shape=(out_h, out_w),
                        resampling=Resampling.average).astype(np.float32)
        win_tf = psrc.window_transform(src_win)
        src_tf = win_tf * win_tf.scale(src_win.width / out_w,
                                       src_win.height / out_h)
    if pnod is not None:
        src[src == pnod] = np.nan
    prob = np.full((h, w), np.nan, dtype=np.float32)
    rasterio.warp.reproject(
        source=src, destination=prob,
        src_transform=src_tf, src_crs=pcrs,
        dst_transform=dst_transform, dst_crs=dst_crs,
        src_nodata=np.nan, dst_nodata=np.nan,
        resampling=Resampling.average)
    mask = np.full((h, w), IGNORE_LABEL, dtype=np.uint8)
    mask[prob <= prob_lo] = 0
    mask[prob >= prob_hi] = 1
    return mask


def canopy_label_from_2020_mask(msrc, dst_crs, dst_transform, h, w):
    """Reproject the OPEN Phase 3 2020 binary canopy mask (``msrc``) onto a crop
    grid. Used by the coarse city-wide tiler (Fix 3) — the 2020 canopy mask is
    the label source for coarse years.

    Returns a 0/1/255 uint8 label: 1 = 2020 canopy, 0 = 2020 background,
    255 = IGNORE (mask nodata or outside the 2020 footprint). Nearest-neighbour
    throughout because the mask is categorical; the fine 7.5 cm source is
    decimated toward the coarse crop size on read. ``msrc`` is passed in already
    open so the city-wide loop reuses one handle for thousands of crops.
    """
    out = np.full((h, w), IGNORE_LABEL, dtype=np.uint8)
    dst_bounds = rasterio.transform.array_bounds(h, w, dst_transform)  # l,b,r,t
    mcrs, mnod = msrc.crs, msrc.nodata
    mb = rasterio.warp.transform_bounds(dst_crs, mcrs, *dst_bounds)
    src_win = rasterio.windows.from_bounds(*mb, transform=msrc.transform)
    src_win = src_win.round_offsets(op="floor").round_lengths(op="ceil")
    try:
        src_win = src_win.intersection(
            rasterio.windows.Window(0, 0, msrc.width, msrc.height))
    except rasterio.windows.WindowError:
        return out                                   # crop fully outside 2020 coverage
    if src_win.width <= 0 or src_win.height <= 0:
        return out                                   # crop outside 2020 coverage
    out_h = max(1, min(int(src_win.height), h))
    out_w = max(1, min(int(src_win.width),  w))
    raw = msrc.read(1, window=src_win, out_shape=(out_h, out_w),
                    resampling=Resampling.nearest).astype(np.uint8)
    win_tf = msrc.window_transform(src_win)
    src_tf = win_tf * win_tf.scale(src_win.width / out_w, src_win.height / out_h)
    dst_arr = np.full((h, w), 255, dtype=np.uint8)
    rasterio.warp.reproject(
        source=raw, destination=dst_arr,
        src_transform=src_tf, src_crs=mcrs,
        dst_transform=dst_transform, dst_crs=dst_crs,
        src_nodata=(mnod if mnod is not None else 255), dst_nodata=255,
        resampling=Resampling.nearest)
    out[dst_arr == 0] = 0
    out[dst_arr == 1] = 1
    return out


def additions_from_mask(asrc, dst_crs, dst_transform, h, w):
    """Reproject the OPEN corrected-label additions raster (``asrc``) onto a crop
    grid. Mirrors ``canopy_label_from_2020_mask`` (nearest, categorical). Returns
    a uint8 code per pixel: 0 = no change, 1 = ADD canopy, 2 = IGNORE. Anything
    outside the additions coverage (nodata / off-footprint) → 0 (no change), so
    2000 crops outside the 2016 strip simply keep the plain 2020 label.
    """
    out = np.zeros((h, w), dtype=np.uint8)               # 0 = no change (default)
    dst_bounds = rasterio.transform.array_bounds(h, w, dst_transform)  # l,b,r,t
    acrs, anod = asrc.crs, (asrc.nodata if asrc.nodata is not None else 255)
    ab = rasterio.warp.transform_bounds(dst_crs, acrs, *dst_bounds)
    src_win = rasterio.windows.from_bounds(*ab, transform=asrc.transform)
    src_win = src_win.round_offsets(op="floor").round_lengths(op="ceil")
    try:
        src_win = src_win.intersection(
            rasterio.windows.Window(0, 0, asrc.width, asrc.height))
    except rasterio.windows.WindowError:
        return out                                       # crop outside additions
    if src_win.width <= 0 or src_win.height <= 0:
        return out
    out_h = max(1, min(int(src_win.height), h))
    out_w = max(1, min(int(src_win.width),  w))
    raw = asrc.read(1, window=src_win, out_shape=(out_h, out_w),
                    resampling=Resampling.nearest).astype(np.uint8)
    win_tf = asrc.window_transform(src_win)
    src_tf = win_tf * win_tf.scale(src_win.width / out_w, src_win.height / out_h)
    dst_arr = np.full((h, w), anod, dtype=np.uint8)
    rasterio.warp.reproject(
        source=raw, destination=dst_arr,
        src_transform=src_tf, src_crs=acrs,
        dst_transform=dst_transform, dst_crs=dst_crs,
        src_nodata=anod, dst_nodata=anod,
        resampling=Resampling.nearest)
    out[dst_arr == 1] = 1
    out[dst_arr == 2] = 2
    return out


def apply_additions(mask_tile, add_tile):
    """Layer an additions code array onto a 0/1/255 label tile, ADD-ONLY:
    code 1 → force canopy (1); code 2 → force IGNORE (255) unless already canopy.
    Never turns canopy into background."""
    mask_tile[add_tile == 1] = 1
    mask_tile[(add_tile == 2) & (mask_tile != 1)] = IGNORE_LABEL
    return mask_tile


def project_and_rasterise_site(src, src_nodata, native_crs, label, site_label,
                               site_bounds_3857, crowns_3857, year_dir,
                               dry_run=False, anchor_labels=False,
                               prob_hi=0.6, prob_lo=0.4):
    """Crop one site from the year's native ortho and build its binary mask.

    Returns (img_path, mask_path, covered, canopy_frac) or (None, None, False, 0)
    if the site is not covered by this year's imagery.
    """
    # Reproject the site footprint into the ortho's native CRS.
    if native_crs is not None and native_crs.to_epsg() != 3857:
        bn = BoundingBox(*rasterio.warp.transform_bounds(
            CROWN_CRS, native_crs,
            site_bounds_3857.left, site_bounds_3857.bottom,
            site_bounds_3857.right, site_bounds_3857.top))
    else:
        bn = site_bounds_3857

    win = _site_window(src, bn)
    if win.width <= 0 or win.height <= 0:
        return None, None, False, 0.0  # footprint outside this ortho entirely

    rgb = read_rgb_window(src, win)                       # 3×h×w
    win_tf = rasterio.windows.transform(win, src.transform)

    # Coverage: a pixel is "no data" if all 3 bands equal the nodata fill (or 0).
    if src_nodata is not None:
        nod = np.all(rgb == src_nodata, axis=0)
    else:
        nod = np.all(rgb == 0, axis=0)
    nod_frac = float(nod.mean())
    if nod_frac > COVERAGE_NODATA_MAX:
        print(f"    {site_label:<22} not covered ({nod_frac*100:.0f}% nodata) — skip")
        return None, None, False, 0.0

    h, w = rgb.shape[1], rgb.shape[2]

    # ── Build the training mask: 0 = background, 1 = canopy, 255 = IGNORE ──────
    if anchor_labels:
        # Import labels from the 2020 full-city canopy probability raster
        # (labels the whole crop; crowns/regions are not used).
        mask = anchor_mask_from_2020(native_crs, win_tf, h, w, prob_hi, prob_lo)
        is_review = False
        regions = None
    else:
        # Review mode (interval-tagged crowns) vs legacy (all crowns = canopy).
        is_review = (crowns_3857 is not None and "status" in crowns_3857.columns)
        year_int  = _year_int(label)

        def _to_native(gdf):
            if gdf is None or len(gdf) == 0:
                return gdf
            return (gdf if (native_crs is None or native_crs.to_epsg() == 3857)
                    else gdf.to_crs(native_crs))

        # Which crowns to burn as canopy this year.
        if is_review:
            sel = crowns_3857
            st = sel["status"].astype(str).str.lower()
            sel = sel[st.eq("approved")]
            if "valid_from" in sel.columns and year_int is not None:
                vf = pd.to_numeric(sel["valid_from"], errors="coerce")
                sel = sel[vf.isna() | (vf <= year_int)]
            if "valid_to" in sel.columns and year_int is not None:
                vt = pd.to_numeric(sel["valid_to"], errors="coerce")
                sel = sel[vt.isna() | (vt >= year_int)]
            burn = sel
        else:
            burn = crowns_3857

        # Guard: a Negative_* site must never contribute canopy, even if its
        # review gpkg was corrupted with 'approved' crowns (e.g. the accept-all
        # overwrite). Mirrors _is_negative_site's name check in the citywide
        # tiling path — the fine/medium per-site path previously lacked it.
        if str(site_label).lower().startswith("negative") and burn is not None:
            burn = burn.iloc[0:0]

        regions = _load_review_regions(site_label) if is_review else None

        def _rasterise(gdf):
            if gdf is None or len(gdf) == 0:
                return np.zeros((h, w), dtype=np.uint8)
            return rasterio.features.rasterize(
                ((g, 1) for g in _to_native(gdf).geometry),
                out_shape=(h, w), transform=win_tf, fill=0, dtype=np.uint8,
                all_touched=False)

        if regions is not None:
            # Outside the reviewed regions → IGNORE; inside → background, then canopy.
            mask = np.full((h, w), IGNORE_LABEL, dtype=np.uint8)
            mask[_rasterise(regions) == 1] = 0
            mask[_rasterise(burn) == 1] = 1
        else:
            # Legacy / true-negative / review-without-regions: whole crop reviewed.
            mask = _rasterise(burn)

    # Imagery nodata is never a valid label → mark it IGNORE (don't train "nodata
    # is background"). For fully-covered legacy years `nod` is empty → no change.
    mask[nod] = IGNORE_LABEL

    labeled      = mask != IGNORE_LABEL
    n_labeled    = int(labeled.sum())
    canopy_frac  = float((mask == 1).sum()) / n_labeled if n_labeled else 0.0
    labeled_frac = n_labeled / (h * w) if h * w else 0.0

    rev = (" [anchor2020]" if anchor_labels
           else (" [review]" if is_review or regions is not None else ""))
    lab = (f"  labeled {labeled_frac*100:4.1f}%"
           if (anchor_labels or is_review or regions is not None) else "")

    if dry_run:
        print(f"    {site_label:<22} {w}×{h}px  canopy {canopy_frac*100:4.1f}%{lab}{rev}  "
              f"(dry run)")
        return None, None, True, canopy_frac

    year_dir.mkdir(parents=True, exist_ok=True)
    img_path  = year_dir / f"{site_label.lower()}_img.tif"
    mask_path = year_dir / f"{site_label.lower()}_mask.tif"

    img_profile = {
        "driver": "GTiff", "dtype": "uint8", "count": 3,
        "width": w, "height": h, "crs": native_crs, "transform": win_tf,
        "compress": "lzw",
    }
    mask_profile = {
        "driver": "GTiff", "dtype": "uint8", "count": 1,
        "width": w, "height": h, "crs": native_crs, "transform": win_tf,
        "compress": "lzw", "nodata": 255,
    }
    with rasterio.open(img_path, "w", **img_profile) as dst:
        dst.write(rgb)
    with rasterio.open(mask_path, "w", **mask_profile) as dst:
        dst.write(mask, 1)

    print(f"    {site_label:<22} {w}×{h}px  canopy {canopy_frac*100:4.1f}%{lab}{rev}")
    return img_path, mask_path, True, canopy_frac


def step_labels(label, sites, dry_run=False, anchor_labels=False,
                prob_hi=0.6, prob_lo=0.4, citywide=False):
    """Step 1 for one year: build native-GSD site crops + binary masks."""
    entry = entry_for(label)
    tier  = tier_of(entry["gsd_cm"])
    if citywide:
        # Coarse city-wide path (Fix 3) builds its labels from the 2020 mask
        # during Step 2 (tiling), straight off the full ortho — no site crops.
        print(f"\n── [{label}] Step 1: Label projection — SKIPPED "
              f"(coarse city-wide tiling labels tiles from the 2020 mask in "
              f"Step 2) ──")
        return None
    print(f"\n── [{label}] Step 1: Label projection "
          f"({entry['gsd_cm']:.1f} cm, {tier}, EPSG:{entry['crs_epsg']}) ──")

    native = resolve_native_path(entry)
    if not native.exists():
        print(f"  ERROR: native ortho not found: {native}")
        return None

    overrides = _load_coverage_overrides()
    year_dir  = SITE_DIR / label
    local = _stage_imagery_local(native) if not dry_run else native

    cov_rows = []
    try:
        with rasterio.open(local) as src:
            native_crs = src.crs
            src_nodata = src.nodata
            print(f"  Ortho: {src.width}×{src.height}px  nodata={src_nodata}")
            for site_label, b3857, crowns in sites:
                # Honour an explicit phase2 exclusion if present.
                if overrides.get((label, site_label)) is False:
                    print(f"    {site_label:<22} excluded by phase2 coverage matrix")
                    cov_rows.append(dict(year=label, site=site_label,
                                         covered=False, canopy_frac=0.0))
                    continue
                ip, mp, covered, frac = project_and_rasterise_site(
                    src, src_nodata, native_crs, label, site_label, b3857,
                    crowns, year_dir, dry_run=dry_run,
                    anchor_labels=anchor_labels, prob_hi=prob_hi, prob_lo=prob_lo)
                cov_rows.append(dict(year=label, site=site_label,
                                     covered=covered, canopy_frac=round(frac, 4)))
    finally:
        if not dry_run:
            _unstage_imagery_local(local)

    n_cov = sum(r["covered"] for r in cov_rows)
    print(f"  Covered sites: {n_cov}/{len(cov_rows)}")
    if n_cov == 0:
        print(f"  WARNING: no covered training sites for {label} — cannot fine-tune.")
    return cov_rows

