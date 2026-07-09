"""
merge_rgb_ir.py — Merge RGB and IR TIFs into a single 4-band GeoTIFF
=====================================================================
Stacks a 3-band RGB orthophoto and a 1-band IR orthophoto into a single
4-band file (R, G, B, NIR) for use in co-registration and downstream
pipeline steps.

Both input files must be co-registered to each other (same pixel grid).
The script verifies CRS, dimensions, and transform before merging.

USAGE (Colab cell):
    %run /content/drive/MyDrive/treedata/Scripts/merge_rgb_ir.py

    # Or with explicit paths:
    import merge_rgb_ir
    merge_rgb_ir.merge(
        rgb_path = "/content/drive/.../2021_snohomish_rgb.tif",
        ir_path  = "/content/drive/.../2021_snohomish_ir.tif",
        out_path = "/content/drive/.../2021_snohomish_rgbi.tif",
    )

OUTPUT FILE NAMING CONVENTION:
    {year}_{source}_rgbi.tif    — 4-band RGB+NIR
    {year}_{source}_rgb.tif     — 3-band RGB only
    {year}_{source}_ir.tif      — 1-band NIR only

    Examples:
        2021_snohomish_rgb.tif      → Snohomish County 2021 RGB
        2021_snohomish_ir.tif       → Snohomish County 2021 NIR
        2021_snohomish_rgbi.tif     → merged 4-band output
        2016_snohomish_ir.tif       → Snohomish County 2016 NIR
        2016_snohomish_rgbi.tif     → merged 4-band output (uses existing 2016 RGB)

BAND ORDER IN OUTPUT:
    Band 1 — Red
    Band 2 — Green
    Band 3 — Blue
    Band 4 — NIR (near-infrared)

NOTE ON REGISTRATION STRATEGY:
    The 4-band merged file is used as input to coregister_imagery.py.
    NCC matching uses band 1 (Red) only — same as for RGB-only files.
    The derived affine/TPS transform is then applied identically to the
    standalone IR file, since RGB and IR are co-acquired and share the
    same geometric distortion.
"""

import sys
from pathlib import Path
import numpy as np

DRIVE_BASE  = Path("/content/drive/MyDrive/treedata")
from pipeline_config import DRIVE_BASE, IMAGERY_DIR

# Default merge jobs — edit or call merge() directly
DEFAULT_JOBS = [
    {
        "rgb_path": IMAGERY_DIR / "2021_snoh_rgb.tif",
        "ir_path":  IMAGERY_DIR / "2021_snoh_ir.tif",
        "out_path": IMAGERY_DIR / "2021_snoh_rgbi.tif",
        "label":    "Snohomish County 2021",
    },
    {
        "rgb_path": IMAGERY_DIR / "2016_snoh_rgb.tif",   # existing registered RGB
        "ir_path":  IMAGERY_DIR / "2016_snoh_ir.tif",
        "out_path": IMAGERY_DIR / "2016_snoh_rgbi.tif",
        "label":    "Snohomish County 2016",
    },
]


def check_compatibility(rgb_ds, ir_ds, label: str = "") -> bool:
    """
    Verify RGB and IR datasets are compatible for merging.
    Checks CRS, dimensions, and transform.
    Returns True if compatible, False otherwise.
    """
    tag = f"[{label}] " if label else ""
    ok  = True

    # CRS
    if rgb_ds.crs != ir_ds.crs:
        print(f"  {tag}CRS MISMATCH:")
        print(f"    RGB: {rgb_ds.crs}")
        print(f"    IR:  {ir_ds.crs}")
        ok = False
    else:
        print(f"  {tag}CRS: {rgb_ds.crs}  ✓")

    # Dimensions
    if rgb_ds.width != ir_ds.width or rgb_ds.height != ir_ds.height:
        print(f"  {tag}DIMENSION MISMATCH:")
        print(f"    RGB: {rgb_ds.width}x{rgb_ds.height}")
        print(f"    IR:  {ir_ds.width}x{ir_ds.height}")
        ok = False
    else:
        print(f"  {tag}Dimensions: {rgb_ds.width}x{rgb_ds.height}  ✓")

    # Transform (pixel grid alignment)
    rt = rgb_ds.transform
    it = ir_ds.transform
    tol = 1e-6
    if (abs(rt.a - it.a) > tol or abs(rt.e - it.e) > tol or
            abs(rt.c - it.c) > tol or abs(rt.f - it.f) > tol):
        print(f"  {tag}TRANSFORM MISMATCH:")
        print(f"    RGB: {rt}")
        print(f"    IR:  {it}")
        ok = False
    else:
        res = abs(rt.a)
        print(f"  {tag}Resolution: {res:.4f} m/px  ✓")
        print(f"  {tag}Origin: ({rt.c:.2f}, {rt.f:.2f})  ✓")

    # Band counts
    if rgb_ds.count != 3:
        print(f"  {tag}WARNING: RGB file has {rgb_ds.count} bands (expected 3)")
    if ir_ds.count != 1:
        print(f"  {tag}WARNING: IR file has {ir_ds.count} bands (expected 1)")

    return ok


def merge(rgb_path, ir_path, out_path, label: str = "", chunk_rows: int = 1024):
    """
    Merge a 3-band RGB TIF and 1-band IR TIF into a 4-band RGBI GeoTIFF.

    Processed in horizontal strips to keep RAM usage flat — reads
    chunk_rows rows at a time from each input and writes to output.
    Peak RAM = chunk_rows * width * 4 bands * dtype_bytes (~500 MB at 1024 rows).

    Parameters
    ----------
    rgb_path  : path to 3-band RGB input
    ir_path   : path to 1-band IR input
    out_path  : path for 4-band RGBI output
    label     : human-readable label for progress output
    chunk_rows: number of rows to process per strip (controls peak RAM)
    """
    import rasterio
    import rasterio.windows

    rgb_path = Path(rgb_path)
    ir_path  = Path(ir_path)
    out_path = Path(out_path)

    tag = f"[{label}] " if label else ""

    print(f"\n{'─'*60}")
    print(f"  {tag}Merging RGB + IR → 4-band RGBI")
    print(f"{'─'*60}")
    print(f"  RGB : {rgb_path.name}  ({rgb_path.stat().st_size/1e9:.1f} GB)")
    print(f"  IR  : {ir_path.name}  ({ir_path.stat().st_size/1e9:.1f} GB)")
    print(f"  Out : {out_path.name}")

    if out_path.exists():
        print(f"  Output already exists — skipping")
        print(f"  Delete {out_path.name} to force rebuild")
        return out_path

    if not rgb_path.exists():
        print(f"  RGB file not found: {rgb_path}")
        return None
    if not ir_path.exists():
        print(f"  IR file not found: {ir_path}")
        return None

    with rasterio.open(rgb_path) as rgb_ds, rasterio.open(ir_path) as ir_ds:

        print(f"\n  Checking compatibility...")
        if not check_compatibility(rgb_ds, ir_ds, label):
            print(f"\n  Cannot merge — fix mismatches above first")
            return None

        width  = rgb_ds.width
        height = rgb_ds.height
        dtype  = rgb_ds.dtypes[0]

        profile = rgb_ds.profile.copy()
        profile.pop("photometric", None)
        profile.update(
            count      = 4,
            dtype      = dtype,
            compress   = "lzw",
            predictor  = 2,
            bigtiff    = "IF_SAFER",
            tiled      = True,
            blockxsize = 512,
            blockysize = 512,
        )

        n_strips = (height + chunk_rows - 1) // chunk_rows
        est_gb   = width * height * 4 / 1e9   # uint8 uncompressed estimate
        print(f"\n  Writing {width}x{height} px  4 bands  "
              f"~{est_gb:.0f} GB uncompressed")
        print(f"  Processing {n_strips} strips of {chunk_rows} rows each")
        print(f"  Peak RAM per strip: ~{width * chunk_rows * 4 / 1e6:.0f} MB")

        from tqdm import tqdm
        import ctypes, gc

        with rasterio.open(out_path, "w", **profile) as out_ds:
            # Set band descriptions
            out_ds.update_tags(1, name="Red")
            out_ds.update_tags(2, name="Green")
            out_ds.update_tags(3, name="Blue")
            out_ds.update_tags(4, name="NIR")

            for strip_i in tqdm(range(n_strips), desc=f"  {label or 'Merging'} strips"):
                row_off = strip_i * chunk_rows
                rows    = min(chunk_rows, height - row_off)
                win     = rasterio.windows.Window(0, row_off, width, rows)

                # Read RGB bands
                rgb_data = rgb_ds.read(window=win)   # (3, rows, width)

                # Read IR band
                ir_data  = ir_ds.read(1, window=win)  # (rows, width)
                ir_data  = ir_data[np.newaxis, :, :]  # (1, rows, width)

                # Stack to 4-band array
                out_data = np.concatenate([rgb_data, ir_data], axis=0)

                # Write strip
                out_ds.write(out_data, window=win)

                # Free strip memory
                del rgb_data, ir_data, out_data
                gc.collect()

                # Drop page cache every 10 strips
                if strip_i % 10 == 0:
                    try:
                        libc = ctypes.CDLL("libc.so.6", use_errno=True)
                        with open(out_path, "rb") as fh:
                            libc.posix_fadvise(fh.fileno(), 0, 0, 4)
                    except Exception:
                        pass

    size_gb = out_path.stat().st_size / 1e9
    print(f"\n  Written: {out_path.name}  ({size_gb:.2f} GB)")

    # Quick validation
    with rasterio.open(out_path) as check:
        assert check.count  == 4,      f"Expected 4 bands, got {check.count}"
        assert check.width  == width,  f"Width mismatch"
        assert check.height == height, f"Height mismatch"
        cx  = check.width  // 2
        cy  = check.height // 2
        win = rasterio.windows.Window(cx-256, cy-256, 512, 512)
        s   = check.read(window=win)
        for b in range(4):
            assert s[b].max() > 0, f"Band {b+1} centre sample is all zeros"
    print(f"  Validated: 4 bands, centre sample non-zero ✓")

    return out_path


def run():
    """Run all default merge jobs defined in DEFAULT_JOBS."""
    print("=" * 60)
    print("  MERGE RGB + IR → 4-BAND RGBI")
    print("=" * 60)
    print(f"  Jobs: {len(DEFAULT_JOBS)}")
    print()

    results = []
    for job in DEFAULT_JOBS:
        result = merge(
            rgb_path = job["rgb_path"],
            ir_path  = job["ir_path"],
            out_path = job["out_path"],
            label    = job["label"],
        )
        results.append((job["label"], result))

    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    for label, path in results:
        if path and path.exists():
            print(f"  ✓ {label}  {path.name}  ({path.stat().st_size/1e9:.1f} GB)")
        else:
            print(f"  ✗ {label}  FAILED")


if __name__ == "__main__":
    sys.argv = sys.argv[:1]
    run()
