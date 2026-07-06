"""
burn_annotations.py — Color burn composites for all annotation extents
======================================================================
For each hand-annotated photo in /treedata/photos/, clips that exact
bounding box from all registered RGB/RGBI imagery and produces a color
burn composite showing multi-year mean brightness and overlap.

One output PNG + GeoTIFF per annotation file, written to:
    /treedata/photos/burned/

USAGE (Colab):
    import sys
    sys.path.insert(0, "/content/drive/MyDrive/treedata/Scripts")
    if "burn_annotations" in sys.modules:
        del sys.modules["burn_annotations"]
    import burn_annotations
    burn_annotations.run()

COLOR ENCODING:
    Dark charcoal-red  = persistently dark (dense canopy, deep shadow)
    Rust / crimson     = mid-tone (rooftops, mixed surfaces)
    Amber / cream-gold = bright (open grass, light rooftops)
    Opacity            = overlap count — more years = more opaque
"""

from pathlib import Path
import numpy as np

DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")
PHOTOS_DIR     = DRIVE_BASE / "photos"
REGISTERED_DIR = DRIVE_BASE / "Full_Image/Pipeline Imagery/registered"
OUTPUT_DIR     = PHOTOS_DIR / "burned"


def _apply_ramp(mean_brightness, overlap_frac):
    """Mean brightness (0-255) → warm color burn RGBA. Overlap → alpha."""
    h, w        = mean_brightness.shape
    rgba        = np.zeros((h, w, 4), dtype=np.uint8)
    bright_norm = np.clip(mean_brightness / 255.0, 0.0, 1.0)

    color_stops = np.array([
        [0.00,  10,   4,   2],
        [0.15,  55,  10,   5],
        [0.30, 110,  25,  10],
        [0.45, 160,  55,  15],
        [0.60, 195,  95,  30],
        [0.75, 215, 145,  55],
        [0.88, 230, 190,  95],
        [1.00, 245, 230, 160],
    ], dtype=np.float32)

    for i in range(len(color_stops) - 1):
        b0, b1 = color_stops[i, 0], color_stops[i + 1, 0]
        mask   = (bright_norm >= b0) & (bright_norm < b1)
        if not mask.any():
            continue
        t = (bright_norm[mask] - b0) / (b1 - b0)
        for c in range(3):
            rgba[mask, c] = np.clip(
                color_stops[i, c+1] + t * (color_stops[i+1, c+1] - color_stops[i, c+1]),
                0, 255).astype(np.uint8)

    top = bright_norm >= color_stops[-1, 0]
    if top.any():
        rgba[top, :3] = color_stops[-1, 1:].astype(np.uint8)

    alpha_stops = np.array([
        [0.00,   0], [0.11,  80], [0.33, 160],
        [0.56, 210], [0.78, 240], [1.00, 255],
    ], dtype=np.float32)

    alpha = np.zeros((h, w), dtype=np.float32)
    for i in range(len(alpha_stops) - 1):
        a0, a1 = alpha_stops[i, 0], alpha_stops[i + 1, 0]
        mask   = (overlap_frac >= a0) & (overlap_frac < a1)
        if not mask.any():
            continue
        t = (overlap_frac[mask] - a0) / (a1 - a0)
        alpha[mask] = alpha_stops[i, 1] + t * (alpha_stops[i+1, 1] - alpha_stops[i, 1])
    alpha[overlap_frac >= 1.0] = 255.0
    rgba[:, :, 3] = np.clip(alpha, 0, 255).astype(np.uint8)
    return rgba


def burn_extent(photo_path, registered_files, ref_transform, ref_crs,
                ref_w, ref_h, output_dir):
    """
    Produce a color burn composite for one annotation file's extent.
    Returns output PNG path, or None on failure.
    """
    import rasterio
    import rasterio.windows

    stem    = photo_path.stem                          # e.g. "Forest_1_rgb"
    out_tif = output_dir / f"{stem}_burned.tif"
    out_png = output_dir / f"{stem}_burned.png"

    if out_png.exists():
        print(f"  {stem}: already exists — skipping")
        return out_png

    # Read the annotation file's bounds
    try:
        with rasterio.open(photo_path) as ann:
            b        = ann.bounds
            ann_w    = ann.width
            ann_h    = ann.height
            ann_crs  = ann.crs
    except Exception as e:
        print(f"  {stem}: could not open — {e}")
        return None

    # Convert geographic bounds to pixel window in the reference image
    # bounds are in EPSG:3857; ref_transform maps pixel → map coords
    res = abs(ref_transform.a)   # m/px

    col_min = int((b.left  - ref_transform.c) / ref_transform.a)
    col_max = int((b.right - ref_transform.c) / ref_transform.a)
    row_min = int((b.top   - ref_transform.f) / ref_transform.e)
    row_max = int((b.bottom- ref_transform.f) / ref_transform.e)

    # Clamp to reference image bounds
    col_off  = max(0, col_min)
    row_off  = max(0, row_min)
    col_end  = min(ref_w, col_max)
    row_end  = min(ref_h, row_max)
    actual_w = col_end - col_off
    actual_h = row_end - row_off

    if actual_w <= 0 or actual_h <= 0:
        print(f"  {stem}: extent outside reference image — skipping")
        return None

    window = rasterio.windows.Window(col_off, row_off, actual_w, actual_h)
    ground_w = actual_w * res
    ground_h = actual_h * res

    print(f"\n  {stem}")
    print(f"    Annotation : {ann_w}×{ann_h} px")
    print(f"    Clip window: col {col_off}–{col_end}, row {row_off}–{row_end}"
          f"  ({actual_w}×{actual_h} px, ~{ground_w:.0f}m×{ground_h:.0f}m)")

    # Stack Red band from every registered year
    n_years = len(registered_files)
    stack   = np.zeros((n_years, actual_h, actual_w), dtype=np.float32)

    for yi, fpath in enumerate(registered_files):
        try:
            with rasterio.open(fpath) as src:
                src_win = rasterio.windows.Window(
                    col_off, row_off,
                    min(actual_w, src.width  - col_off),
                    min(actual_h, src.height - row_off),
                )
                if src_win.width <= 0 or src_win.height <= 0:
                    continue
                band = src.read(1, window=src_win)
                h, w = band.shape
                stack[yi, :h, :w] = band
        except Exception as e:
            print(f"    {fpath.name}: {e}")

    # Compute statistics
    has_data      = (stack > 0)
    overlap_count = has_data.sum(axis=0).astype(np.float32)
    overlap_frac  = np.where(overlap_count > 0, overlap_count / n_years, 0.0)
    mean_bright   = np.where(
        overlap_count > 0,
        stack.sum(axis=0) / np.maximum(overlap_count, 1),
        0.0)

    valid = mean_bright[overlap_count > 0]
    if valid.size:
        print(f"    Brightness : min={valid.min():.0f}  max={valid.max():.0f}"
              f"  mean={valid.mean():.0f}"
              f"  p5={np.percentile(valid,5):.0f}"
              f"  p95={np.percentile(valid,95):.0f}")

    covered_pct = 100 * (overlap_count > 0).sum() / (actual_h * actual_w)
    mean_overlap = overlap_count[overlap_count > 0].mean() if (overlap_count > 0).any() else 0
    print(f"    Coverage   : {covered_pct:.1f}% of extent  "
          f"avg {mean_overlap:.1f}/{n_years} years per pixel")

    # Render and write
    rgba = _apply_ramp(mean_bright, overlap_frac)

    clip_transform = rasterio.windows.transform(window, ref_transform)
    profile = {
        "driver": "GTiff", "dtype": "uint8",
        "width": actual_w, "height": actual_h,
        "count": 4, "crs": ref_crs, "transform": clip_transform,
        "compress": "lzw", "predictor": 2,
        "tiled": True, "blockxsize": 256, "blockysize": 256,
    }
    with rasterio.open(out_tif, "w", **profile) as dst:
        for band_i, channel in enumerate([0, 1, 2, 3], start=1):
            dst.write(rgba[:, :, channel], band_i)

    from PIL import Image
    img = Image.fromarray(rgba, mode="RGBA")
    img.save(out_png, dpi=(150, 150))

    tif_mb = out_tif.stat().st_size / 1e6
    png_mb = out_png.stat().st_size / 1e6
    print(f"    Written    : {out_png.name}  ({png_mb:.1f} MB PNG, {tif_mb:.1f} MB GeoTIFF)")
    return out_png


def run(photos_dir=None, registered_dir=None, output_dir=None):
    """
    Generate color burn composites for every annotation file in photos_dir.

    Parameters
    ----------
    photos_dir    : folder containing annotation TIF files (default: PHOTOS_DIR)
    registered_dir: folder containing *_registered.tif files (default: REGISTERED_DIR)
    output_dir    : folder for burned outputs (default: photos_dir/burned/)
    """
    import rasterio

    ph_dir  = Path(photos_dir)    if photos_dir    else PHOTOS_DIR
    reg_dir = Path(registered_dir) if registered_dir else REGISTERED_DIR
    out_dir = Path(output_dir)    if output_dir    else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  BATCH COLOR BURN — Annotation Extents")
    print("=" * 60)

    # Discover annotation files
    ann_files = sorted([
        f for f in ph_dir.glob("*.tif")
        if "burned" not in f.name
    ])
    if not ann_files:
        print(f"  No .tif files found in: {ph_dir}")
        return
    print(f"\n  Annotation files ({len(ann_files)}):")
    for f in ann_files:
        print(f"    {f.name}  ({f.stat().st_size/1e6:.1f} MB)")

    # Discover registered files — skip IR and composites
    reg_files = sorted([
        f for f in reg_dir.glob("*_registered.tif")
        if "_ir_registered" not in f.name
        and "composite" not in f.name
    ])
    if not reg_files:
        print(f"  No registered files found in: {reg_dir}")
        return
    print(f"\n  Registered years ({len(reg_files)}):")
    for f in reg_files:
        print(f"    {f.name}  ({f.stat().st_size/1e9:.1f} GB)")

    # Reference transform from first registered file
    with rasterio.open(reg_files[0]) as ref:
        ref_transform = ref.transform
        ref_crs       = ref.crs
        ref_w         = ref.width
        ref_h         = ref.height
    print(f"\n  Reference: {ref_w}×{ref_h} px  {abs(ref_transform.a):.4f} m/px  {ref_crs}")

    # Process each annotation
    print(f"\n  Output dir: {out_dir}")
    results = []
    for ann_path in ann_files:
        result = burn_extent(
            ann_path, reg_files,
            ref_transform, ref_crs, ref_w, ref_h,
            out_dir,
        )
        results.append((ann_path.stem, result))

    # Summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    passed = 0
    for stem, path in results:
        if path and path.exists():
            print(f"  ✓ {stem}  →  {path.name}")
            passed += 1
        else:
            print(f"  ✗ {stem}  →  failed")
    print(f"\n  {passed}/{len(results)} completed")
    print(f"  Output: {out_dir}")
    return results


if __name__ == "__main__":
    import sys
    sys.argv = sys.argv[:1]
    run()
