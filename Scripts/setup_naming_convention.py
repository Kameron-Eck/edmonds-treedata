"""
setup_naming_convention.py — One-time file renaming and RGB+IR merge
=====================================================================
Performs two tasks:

1. RENAME — Updates all files in Pipeline Imagery/, upsample/, and
   registered/ to use the new consistent naming convention:
       {year}_{source}_{bands}.tif
   where source = king | coe | snoh
   and   bands  = rgb | ir | rgbi

2. MERGE — Merges the Snohomish County RGB and IR files into 4-band
   RGBI GeoTIFFs for 2016 and 2021.

NAMING CONVENTION:
    {year}_{source}_{bands}.tif

    Sources:
        king  — King County
        coe   — City of Edmonds
        snoh  — Snohomish County

    Bands:
        rgb   — 3-band RGB
        ir    — 1-band near-infrared
        rgbi  — 4-band RGB + NIR (merged output)

RENAME MAP (old → new):
    Pipeline Imagery/:
        2013_king_rgb.tif         (already correct)
        2015_king_rgb.tif         (already correct)
        2016_coe_snoco_i.tif   →  2016_snoh_ir.tif
        2016_snoh_rgb.tif         (already correct)
        2017_coe_rgb.tif          (already correct)
        2019_king_rgb.tif         (already correct)
        2020_coe_rgb.tif          (already correct)
        2021_king_rgb.tif         (already correct)
        2021_snoh_i.tif        →  2021_snoh_ir.tif
        2021_snoh_rgb.tif         (already correct)
        2022_coe_rgb.tif          (already correct)
        2023_king_rgb.tif         (already correct)
        2024_coe_rgb.tif          (already correct)

    upsample/ and registered/ — rename any files using old convention
    to match the new source-tagged names.

USAGE (Colab cell):
    %run /content/drive/MyDrive/treedata/Scripts/setup_naming_convention.py

    # Dry run first (default) — shows what would be renamed/merged:
    %run /content/drive/MyDrive/treedata/Scripts/setup_naming_convention.py --dry-run

    # Confirm and execute:
    %run /content/drive/MyDrive/treedata/Scripts/setup_naming_convention.py --confirm
"""

import argparse
import gc
import sys
import ctypes
from pathlib import Path
import numpy as np

DRIVE_BASE   = Path("/content/drive/MyDrive/treedata")
IMAGERY_DIR  = DRIVE_BASE / "Full_Image/Pipeline Imagery"
UPSAMPLE_DIR = IMAGERY_DIR / "upsample"
REGISTERED_DIR = IMAGERY_DIR / "registered"

# ── Rename map ────────────────────────────────────────────────
# Maps old filename → new filename for Pipeline Imagery directory
IMAGERY_RENAMES = {
    "2016_coe_snoco_i.tif":  "2016_snoh_ir.tif",
    "2021_snoh_i.tif":       "2021_snoh_ir.tif",
    # Old _edmonds.tif convention → new source-tagged convention
    "2013_edmonds.tif":      "2013_king_rgb.tif",
    "2015_edmonds.tif":      "2015_king_rgb.tif",
    "2016_edmonds.tif":      "2016_snoh_rgb.tif",
    "2017_edmonds.tif":      "2017_coe_rgb.tif",
    "2019_edmonds.tif":      "2019_king_rgb.tif",
    "2020_edmonds.tif":      "2020_coe_rgb.tif",
    "2021_edmonds.tif":      "2021_king_rgb.tif",
    "2022_edmonds.tif":      "2022_coe_rgb.tif",
    "2023_edmonds.tif":      "2023_king_rgb.tif",
    "2024_edmonds.tif":      "2024_coe_rgb.tif",
}

# Upsample and registered dirs use {year}_edmonds_upsampled.tif
# and {year}_edmonds_registered.tif — remap to new convention
UPSAMPLE_RENAMES = {
    "2013_edmonds_upsampled.tif": "2013_king_rgb_upsampled.tif",
    "2015_edmonds_upsampled.tif": "2015_king_rgb_upsampled.tif",
    "2019_edmonds_upsampled.tif": "2019_king_rgb_upsampled.tif",
    "2021_edmonds_upsampled.tif": "2021_king_rgb_upsampled.tif",
    "2023_edmonds_upsampled.tif": "2023_king_rgb_upsampled.tif",
}

REGISTERED_RENAMES = {
    "2013_edmonds_registered.tif": "2013_king_rgb_registered.tif",
    "2015_edmonds_registered.tif": "2015_king_rgb_registered.tif",
    "2017_edmonds_registered.tif": "2017_coe_rgb_registered.tif",
    "2019_edmonds_registered.tif": "2019_king_rgb_registered.tif",
    "2021_edmonds_registered.tif": "2021_king_rgb_registered.tif",
    "2022_edmonds_registered.tif": "2022_coe_rgb_registered.tif",
    "2023_edmonds_registered.tif": "2023_king_rgb_registered.tif",
    "2024_edmonds_registered.tif": "2024_coe_rgb_registered.tif",
}

# ── Merge jobs ────────────────────────────────────────────────
MERGE_JOBS = [
    {
        "label":    "2016 Snohomish County",
        "rgb_path": IMAGERY_DIR / "2016_snoh_rgb.tif",
        "ir_path":  IMAGERY_DIR / "2016_snoh_ir.tif",
        "out_path": IMAGERY_DIR / "2016_snoh_rgbi.tif",
    },
    {
        "label":    "2021 Snohomish County",
        "rgb_path": IMAGERY_DIR / "2021_snoh_rgb.tif",
        "ir_path":  IMAGERY_DIR / "2021_snoh_ir.tif",
        "out_path": IMAGERY_DIR / "2021_snoh_rgbi.tif",
    },
]


# ── Rename helpers ────────────────────────────────────────────

def do_renames(directory: Path, rename_map: dict, confirm: bool, label: str):
    """Apply rename_map to files in directory."""
    print(f"\n  [{label}]  {directory}")
    if not directory.exists():
        print(f"    Directory does not exist — skipping")
        return 0

    done = 0
    for old_name, new_name in rename_map.items():
        old_path = directory / old_name
        new_path = directory / new_name
        if not old_path.exists():
            continue
        if new_path.exists():
            print(f"    Already renamed: {new_name}")
            continue
        size_gb = old_path.stat().st_size / 1e9
        if confirm:
            old_path.rename(new_path)
            print(f"    Renamed: {old_name} → {new_name}  ({size_gb:.1f} GB)")
        else:
            print(f"    Would rename: {old_name} → {new_name}  ({size_gb:.1f} GB)")
        done += 1

    if done == 0:
        print(f"    Nothing to rename")
    return done


# ── Merge helper ──────────────────────────────────────────────

def merge_rgbi(rgb_path: Path, ir_path: Path, out_path: Path,
               label: str, confirm: bool, chunk_rows: int = 1024):
    """Merge 3-band RGB + 1-band IR into 4-band RGBI GeoTIFF."""
    import rasterio
    import rasterio.windows
    from tqdm import tqdm

    print(f"\n  [{label}]")

    if out_path.exists():
        size_gb = out_path.stat().st_size / 1e9
        print(f"    Output already exists: {out_path.name}  ({size_gb:.1f} GB) — skipping")
        return True

    if not rgb_path.exists():
        print(f"    RGB not found: {rgb_path.name}")
        return False
    if not ir_path.exists():
        print(f"    IR not found: {ir_path.name}")
        return False

    rgb_gb = rgb_path.stat().st_size / 1e9
    ir_gb  = ir_path.stat().st_size / 1e9
    print(f"    RGB : {rgb_path.name}  ({rgb_gb:.1f} GB)")
    print(f"    IR  : {ir_path.name}  ({ir_gb:.1f} GB)")
    print(f"    Out : {out_path.name}")

    # Compatibility check — handles undefined IR CRS by inheriting from RGB
    with rasterio.open(rgb_path) as rgb_ds, rasterio.open(ir_path) as ir_ds:
        ok = True
        if rgb_ds.width != ir_ds.width or rgb_ds.height != ir_ds.height:
            print(f"    DIMENSION MISMATCH: RGB={rgb_ds.width}x{rgb_ds.height} "
                  f"IR={ir_ds.width}x{ir_ds.height}")
            ok = False
        rt, it = rgb_ds.transform, ir_ds.transform
        if abs(rt.a - it.a) > 1e-6 or abs(rt.c - it.c) > 1e-6:
            print(f"    TRANSFORM MISMATCH")
            ok = False

        # CRS check — warn but don't fail if IR has undefined/local CRS
        # (common with county IR deliveries). We inherit RGB CRS for the merge.
        rgb_crs = rgb_ds.crs
        ir_crs  = ir_ds.crs
        if rgb_crs == ir_crs:
            print(f"    CRS: {rgb_crs}  ✓")
            assign_crs = False
        elif ir_crs is None or "LOCAL_CS" in str(ir_crs):
            print(f"    IR has undefined CRS — will assign RGB CRS: {rgb_crs}")
            assign_crs = True
        else:
            print(f"    CRS MISMATCH: RGB={rgb_crs}  IR={ir_crs}")
            print(f"    Proceeding with RGB CRS — verify output in QGIS")
            assign_crs = True

        if not ok:
            print(f"    Cannot merge — fix dimension/transform mismatches first")
            return False

        width, height = rgb_ds.width, rgb_ds.height
        dtype = rgb_ds.dtypes[0]
        res   = abs(rt.a)
        print(f"    {width}x{height} px  {res:.4f} m/px  dtype={dtype}  ✓ compatible")

        if not confirm:
            print(f"    Dry run — would merge {width}x{height} px into 4-band RGBI")
            return True

        profile = rgb_ds.profile.copy()
        profile.pop("photometric", None)
        profile.update(count=4, dtype=dtype, compress="lzw", predictor=2,
                       bigtiff="IF_SAFER", tiled=True,
                       blockxsize=512, blockysize=512,
                       crs=rgb_crs)   # always use RGB CRS for output

        n_strips = (height + chunk_rows - 1) // chunk_rows

        with rasterio.open(out_path, "w", **profile) as out_ds:
            out_ds.update_tags(1, name="Red")
            out_ds.update_tags(2, name="Green")
            out_ds.update_tags(3, name="Blue")
            out_ds.update_tags(4, name="NIR")

            for strip_i in tqdm(range(n_strips), desc=f"    {label}"):
                row_off = strip_i * chunk_rows
                rows    = min(chunk_rows, height - row_off)
                win     = rasterio.windows.Window(0, row_off, width, rows)

                rgb_data = rgb_ds.read(window=win)
                ir_data  = ir_ds.read(1, window=win)[np.newaxis, :, :]
                out_ds.write(np.concatenate([rgb_data, ir_data], axis=0), window=win)

                del rgb_data, ir_data
                gc.collect()
                if strip_i % 10 == 0:
                    try:
                        libc = ctypes.CDLL("libc.so.6", use_errno=True)
                        with open(out_path, "rb") as fh:
                            libc.posix_fadvise(fh.fileno(), 0, 0, 4)
                    except Exception:
                        pass

    size_gb = out_path.stat().st_size / 1e9
    print(f"    Written: {out_path.name}  ({size_gb:.2f} GB)")

    # Validate
    with rasterio.open(out_path) as check:
        assert check.count == 4
        cx, cy = check.width // 2, check.height // 2
        win = rasterio.windows.Window(cx-256, cy-256, 512, 512)
        s = check.read(window=win)
        for b in range(4):
            assert s[b].max() > 0, f"Band {b+1} centre is all zeros"
    print(f"    Validated: 4 bands, centre sample non-zero ✓")
    return True


# ── Main ──────────────────────────────────────────────────────

def run(confirm: bool = False):
    mode = "LIVE" if confirm else "DRY RUN — pass --confirm to execute"
    print("=" * 60)
    print(f"  SETUP NAMING CONVENTION  [{mode}]")
    print("=" * 60)

    # Pre-flight: show all snoh files to confirm filenames
    print("\n── Pre-flight: snoh files in Pipeline Imagery ──────────")
    for f in sorted(IMAGERY_DIR.glob("*snoh*")):
        print(f"  {f.name}  ({f.stat().st_size/1e9:.1f} GB)")
    print()

    # ── Step 1: Renames ───────────────────────────────────────
    print("\n── Step 1: Rename files to new convention ──────────────")
    total_renames = 0
    total_renames += do_renames(IMAGERY_DIR,    IMAGERY_RENAMES,    confirm, "Pipeline Imagery")
    total_renames += do_renames(UPSAMPLE_DIR,   UPSAMPLE_RENAMES,   confirm, "upsample")
    total_renames += do_renames(REGISTERED_DIR, REGISTERED_RENAMES, confirm, "registered")
    print(f"\n  Total: {total_renames} files {'renamed' if confirm else 'to rename'}")

    # ── Step 2: Merge RGB + IR ────────────────────────────────
    print("\n── Step 2: Merge RGB + IR → 4-band RGBI ───────────────")
    merge_results = []
    for job in MERGE_JOBS:
        ok = merge_rgbi(
            rgb_path = job["rgb_path"],
            ir_path  = job["ir_path"],
            out_path = job["out_path"],
            label    = job["label"],
            confirm  = confirm,
        )
        merge_results.append((job["label"], job["out_path"], ok))

    # ── Summary ───────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    for label, path, ok in merge_results:
        icon = "✓" if ok else "✗"
        status = path.stat().st_size/1e9 if (ok and path.exists()) else "failed"
        size_str = f"{status:.1f} GB" if isinstance(status, float) else status
        print(f"  {icon} {label}  {path.name}  {size_str}")

    if not confirm:
        print(f"\n  Dry run complete. Run with --confirm to execute:")
        print(f"  %run .../setup_naming_convention.py --confirm")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true",
                        help="Actually rename files and merge (default is dry run)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without doing it (default)")

    filtered = [a for a in sys.argv[1:]
                if not (a == "-f" or a.endswith(".json"))]
    args = parser.parse_args(filtered)

    run(confirm=args.confirm)