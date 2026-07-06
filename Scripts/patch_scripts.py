"""
patch_scripts.py — Updates all pipeline scripts to use pipeline_config.py
==========================================================================
Replaces hardcoded paths and old {year}_edmonds naming with canonical
pipeline_config imports and {year}_{source}_{bands} convention.

Run in Colab:
    DRY_RUN = True  (default) — shows diffs, makes no changes
    DRY_RUN = False            — applies all patches

    %run /content/drive/MyDrive/treedata/Scripts/patch_scripts.py
"""

from pathlib import Path
import re

DRY_RUN = True

SCRIPTS_DIR = Path("/content/drive/MyDrive/treedata/Scripts")

# ── Config import header injected at top of each script ──────
CONFIG_IMPORT = '''import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent) if "__file__" in dir() else "/content/drive/MyDrive/treedata/Scripts")
from pipeline_config import (
    DRIVE_BASE, IMAGERY_DIR, REGISTERED_DIR, UPSAMPLE_DIR, COMPOSITES_DIR,
    BUILDINGS_JSON, PHOTOS_DIR, POLYGONS_DIR, LABELS_DIR, TILES_DIR,
    CHECKPOINTS_DIR, INFERENCE_DIR, REVIEW_DIR, CLIPS_DIR,
    IMAGERY_CATALOG, SOURCE_CODES, TARGET_YEARS, REFERENCE_YEAR,
    raw_path, registered_path, upsampled_path, get_available_registered,
)
'''

# ── Per-script patch definitions ─────────────────────────────
# Each entry: (script_name, [(old_string, new_string), ...])
# Strings are exact — no regex. Order matters within a script.

PATCHES = {

    # ── coregister_imagery.py ─────────────────────────────────
    "coregister_imagery.py": [
        # Fix docstring reference to old output name
        (
            "/registered/{year}_edmonds_registered.tif  warped imagery in 2020 space",
            "/registered/{year}_{source}_{bands}_registered.tif  warped imagery in 2020 space",
        ),
        # Replace the entire config block with config import
        (
            'DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")\n'
            'BUILDINGS_JSON = DRIVE_BASE / "building_footprints" / "data.json"\n'
            'IMAGERY_DIR    = DRIVE_BASE / "Full_Image/Pipeline Imagery"',
            'DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")\n'
            'from pipeline_config import (\n'
            '    DRIVE_BASE, IMAGERY_DIR, REGISTERED_DIR, UPSAMPLE_DIR,\n'
            '    BUILDINGS_JSON, IMAGERY_CATALOG, raw_path, registered_path,\n'
            '    upsampled_path, TARGET_YEARS, REFERENCE_YEAR, SOURCE_CODES,\n'
            ')\n'
            '# Paths from pipeline_config — do not redefine here',
        ),
        # Remove the duplicate path definitions that follow
        (
            'DRIVE_OUTPUT   = IMAGERY_DIR / "registered"\n'
            'DRIVE_UPSAMPLE = IMAGERY_DIR / "upsample"',
            'DRIVE_OUTPUT   = REGISTERED_DIR\n'
            'DRIVE_UPSAMPLE = UPSAMPLE_DIR',
        ),
        # Fix clips dir reference
        (
            'CLIPS_DIR = DRIVE_BASE / "clips"',
            'from pipeline_config import CLIPS_DIR',
        ),
    ],

    # ── phase0_coreg_gifs.py ──────────────────────────────────
    "phase0_coreg_gifs.py": [
        (
            'DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")\n'
            'BUILDINGS_JSON = DRIVE_BASE / "building_footprints" / "data.json"\n'
            'IMAGERY_DIR    = DRIVE_BASE / "Full_Image/Pipeline Imagery"\n'
            'OUTPUT_DIR     = DRIVE_BASE / "registered"',
            'DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")\n'
            'from pipeline_config import (\n'
            '    DRIVE_BASE, IMAGERY_DIR, REGISTERED_DIR, BUILDINGS_JSON,\n'
            '    IMAGERY_CATALOG, raw_path, registered_path, REFERENCE_YEAR,\n'
            ')\n'
            'OUTPUT_DIR = REGISTERED_DIR',
        ),
        # Old reference image path
        (
            'ref_path          = IMAGERY_DIR / f"{REFERENCE_YEAR}_edmonds.tif"',
            'ref_path          = raw_path(REFERENCE_YEAR)',
        ),
        # Old unregistered path
        (
            'unregistered_path = IMAGERY_DIR / f"{args.year}_edmonds.tif"',
            'unregistered_path = raw_path(args.year)',
        ),
    ],

    # ── sample_imagery.py ─────────────────────────────────────
    "sample_imagery.py": [
        (
            'DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")\n'
            'IMAGERY_DIR    = DRIVE_BASE / "Full_Image/Pipeline Imagery"\n'
            'REGISTERED_DIR = DRIVE_BASE / "registered"',
            'DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")\n'
            'from pipeline_config import (\n'
            '    DRIVE_BASE, IMAGERY_DIR, REGISTERED_DIR, UPSAMPLE_DIR,\n'
            '    raw_path, registered_path, upsampled_path, REFERENCE_YEAR,\n'
            ')',
        ),
        (
            'registered = REGISTERED_DIR / f"{year}_edmonds_registered.tif"',
            'registered = registered_path(year)',
        ),
        (
            'upsampled  = IMAGERY_DIR / "upsampled" / f"{year}_edmonds_upsampled.tif"',
            'upsampled  = upsampled_path(year)',
        ),
        (
            'raw        = IMAGERY_DIR / f"{year}_edmonds.tif"',
            'raw        = raw_path(year)',
        ),
        (
            'ref_path = IMAGERY_DIR / f"{REFERENCE_YEAR}_edmonds.tif"',
            'ref_path = raw_path(REFERENCE_YEAR)',
        ),
        (
            'out_path = REGISTERED_DIR / f"imagery_sample_{cx}_{cy}_{mode}.png"',
            'out_path = REGISTERED_DIR / f"imagery_sample_{cx}_{cy}_{mode}.png"',  # unchanged but correct
        ),
    ],

    # ── clip_study_area.py ────────────────────────────────────
    "clip_study_area.py": [
        (
            'DRIVE_BASE   = Path("/content/drive/MyDrive/treedata")\n'
            'IMAGERY_DIR  = DRIVE_BASE / "Full_Image/Pipeline Imagery"\n'
            'CLIPS_DIR    = DRIVE_BASE / "clips"',
            'DRIVE_BASE   = Path("/content/drive/MyDrive/treedata")\n'
            'from pipeline_config import (\n'
            '    DRIVE_BASE, IMAGERY_DIR, CLIPS_DIR,\n'
            '    raw_path, registered_path, REFERENCE_YEAR,\n'
            ')',
        ),
        (
            'src_path = IMAGERY_DIR / f"{year}_edmonds.tif"',
            'src_path = raw_path(year)',
        ),
        (
            'ref_path = IMAGERY_DIR / f"{REFERENCE_YEAR}_edmonds.tif"',
            'ref_path = raw_path(REFERENCE_YEAR)',
        ),
    ],

    # ── build_clip_viewer.py ──────────────────────────────────
    "build_clip_viewer.py": [
        (
            'DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")\n'
            'CLIPS_DIR      = DRIVE_BASE / "clips"\n'
            'REGISTERED_DIR = CLIPS_DIR / "registered"',
            'DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")\n'
            'from pipeline_config import DRIVE_BASE, CLIPS_DIR\n'
            'REGISTERED_DIR = CLIPS_DIR / "registered"',
        ),
        (
            'tgt_path = REGISTERED_DIR / f"{year}_edmonds_clip_registered.tif"',
            'tgt_path = REGISTERED_DIR / f"{year}_clip_registered.tif"',
        ),
    ],

    # ── visualize_clips.py ────────────────────────────────────
    "visualize_clips.py": [
        (
            'DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")\n'
            'CLIPS_DIR      = DRIVE_BASE / "clips"\n'
            'REGISTERED_DIR = CLIPS_DIR / "registered"\n'
            'IMAGERY_DIR    = DRIVE_BASE / "Full_Image/Pipeline Imagery"',
            'DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")\n'
            'from pipeline_config import DRIVE_BASE, CLIPS_DIR, IMAGERY_DIR\n'
            'REGISTERED_DIR = CLIPS_DIR / "registered"',
        ),
        (
            'reg_clip = REGISTERED_DIR / f"{year}_edmonds_clip_registered.tif"',
            'reg_clip = REGISTERED_DIR / f"{year}_clip_registered.tif"',
        ),
    ],

    # ── merge_rgb_ir.py ───────────────────────────────────────
    "merge_rgb_ir.py": [
        (
            'DRIVE_BASE  = Path("/content/drive/MyDrive/treedata")\n'
            'IMAGERY_DIR = DRIVE_BASE / "Full_Image/Pipeline Imagery"',
            'DRIVE_BASE  = Path("/content/drive/MyDrive/treedata")\n'
            'from pipeline_config import DRIVE_BASE, IMAGERY_DIR',
        ),
        # Fix old snohomish naming
        (
            '"rgb_path": IMAGERY_DIR / "2021_snohomish_rgb.tif"',
            '"rgb_path": IMAGERY_DIR / "2021_snoh_rgb.tif"',
        ),
        (
            '"ir_path":  IMAGERY_DIR / "2021_snohomish_ir.tif"',
            '"ir_path":  IMAGERY_DIR / "2021_snoh_ir.tif"',
        ),
        (
            '"out_path": IMAGERY_DIR / "2021_snohomish_rgbi.tif"',
            '"out_path": IMAGERY_DIR / "2021_snoh_rgbi.tif"',
        ),
        (
            '"rgb_path": IMAGERY_DIR / "2016_edmonds.tif"',
            '"rgb_path": IMAGERY_DIR / "2016_snoh_rgb.tif"',
        ),
        (
            '"ir_path":  IMAGERY_DIR / "2016_snohomish_ir.tif"',
            '"ir_path":  IMAGERY_DIR / "2016_snoh_ir.tif"',
        ),
        (
            '"out_path": IMAGERY_DIR / "2016_snohomish_rgbi.tif"',
            '"out_path": IMAGERY_DIR / "2016_snoh_rgbi.tif"',
        ),
    ],

    # ── phase1_preprocess.py ──────────────────────────────────
    "phase1_preprocess.py": [
        (
            'IMAGERY     = BASE / "Full_Image/edmonds_2021_image.tif"',
            'from pipeline_config import IMAGERY_DIR, registered_path\n'
            'IMAGERY     = registered_path(2021)',
        ),
    ],

    # ── prepare_review_data_colab.py ──────────────────────────
    "prepare_review_data_colab.py": [
        (
            'IMAGERY_TIF = DRIVE_BASE / "Full_Image" / "edmonds_2020_image.tif"',
            'from pipeline_config import IMAGERY_DIR, raw_path\n'
            'IMAGERY_TIF = raw_path(2020)',
        ),
        (
            'DRIVE_BASE = Path("/content/drive/MyDrive/treedata")',
            'DRIVE_BASE = Path("/content/drive/MyDrive/treedata")\n'
            'from pipeline_config import DRIVE_BASE, INFERENCE_DIR, REVIEW_DIR',
        ),
    ],

    # ── run_registration.py ───────────────────────────────────
    "run_registration.py": [
        (
            'DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")\n'
            'IMAGERY_DIR    = DRIVE_BASE / "Full_Image/Pipeline Imagery"\n'
            'DRIVE_OUTPUT   = IMAGERY_DIR / "registered"\n'
            'DRIVE_UPSAMPLE = IMAGERY_DIR / "upsample"',
            'DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")\n'
            'from pipeline_config import (\n'
            '    DRIVE_BASE, IMAGERY_DIR, REGISTERED_DIR, UPSAMPLE_DIR,\n'
            ')\n'
            'DRIVE_OUTPUT   = REGISTERED_DIR\n'
            'DRIVE_UPSAMPLE = UPSAMPLE_DIR',
        ),
    ],

    # ── cleanup_registration.py ───────────────────────────────
    "cleanup_registration.py": [
        (
            'DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")\n'
            'IMAGERY_DIR    = DRIVE_BASE / "Full_Image/Pipeline Imagery"\n'
            'DRIVE_OUTPUT   = IMAGERY_DIR / "registered"\n'
            'DRIVE_UPSAMPLE = IMAGERY_DIR / "upsample"',
            'DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")\n'
            'from pipeline_config import (\n'
            '    DRIVE_BASE, IMAGERY_DIR, REGISTERED_DIR, UPSAMPLE_DIR,\n'
            ')\n'
            'DRIVE_OUTPUT   = REGISTERED_DIR\n'
            'DRIVE_UPSAMPLE = UPSAMPLE_DIR',
        ),
        (
            'Drive .../Full_Image/Pipeline Imagery/{year}_edmonds.tif  — raw sources',
            'Drive .../Full_Image/Pipeline Imagery/{year}_{source}_{bands}.tif  — raw sources',
        ),
    ],

    # ── downloader scripts — update output folder + naming ────
    "download_tiles.py": [
        (
            'OUTPUT_DIR  = "/content/drive/MyDrive/treedata/Full_Image"',
            'from pipeline_config import IMAGERY_DIR\n'
            'OUTPUT_DIR  = str(IMAGERY_DIR)',
        ),
        (
            'output_path = Path(OUTPUT_DIR) / f"edmonds_{year}_image.tif"',
            '# Naming: {year}_{source}_{bands}.tif — set source/bands per downloader call\n'
            'output_path = Path(OUTPUT_DIR) / f"{year}_coe_rgb.tif"',
        ),
        (
            'pipeline naming convention: edmonds_{year}_image.tif',
            'pipeline naming convention: {year}_{source}_{bands}.tif',
        ),
    ],

    "batch.py": [
        (
            'BASE_DIR   = "/content/drive/MyDrive/treedata/Full_Image/Edmonds"',
            'from pipeline_config import IMAGERY_DIR\n'
            'BASE_DIR   = str(IMAGERY_DIR)',
        ),
        (
            'out_path = os.path.join(BASE_DIR, f"edmonds_{YEAR}_image.tif")',
            'out_path = os.path.join(BASE_DIR, f"{YEAR}_coe_rgb.tif")',
        ),
    ],

    "edmonds_batch_orchestrator.py": [
        (
            'OUTPUT_DIR = "/content/drive/MyDrive/treedata/Full_Image/Edmonds"',
            'from pipeline_config import IMAGERY_DIR\n'
            'OUTPUT_DIR = str(IMAGERY_DIR)',
        ),
        (
            'out_path = os.path.join(OUTPUT_DIR, f"edmonds_{YEAR}_image.tif")',
            'out_path = os.path.join(OUTPUT_DIR, f"{YEAR}_coe_rgb.tif")',
        ),
    ],

    "master_imagery_downloader.py": [
        (
            'BASE_DIR = "/content/drive/MyDrive/treedata/Full_Image"',
            'from pipeline_config import FULL_IMAGE_DIR\n'
            'BASE_DIR = str(FULL_IMAGE_DIR)',
        ),
        (
            'Edmonds/          edmonds_{year}_image.tif',
            'Edmonds/          {year}_coe_rgb.tif',
        ),
    ],

    "unified_downloader.py": [
        (
            'BASE_DIR   = "/content/drive/MyDrive/treedata/Full_Image"',
            'from pipeline_config import FULL_IMAGE_DIR\n'
            'BASE_DIR   = str(FULL_IMAGE_DIR)',
        ),
    ],

    "unified_downloader_v2.py": [
        (
            'BASE_DIR   = "/content/drive/MyDrive/treedata/Full_Image"',
            'from pipeline_config import FULL_IMAGE_DIR\n'
            'BASE_DIR   = str(FULL_IMAGE_DIR)',
        ),
    ],

    "king_county.py": [
        (
            'OUTPUT_DIR  = "/content/drive/MyDrive/treedata/Full_Image"',
            'from pipeline_config import FULL_IMAGE_DIR\n'
            'OUTPUT_DIR  = str(FULL_IMAGE_DIR / "KingCo")',
        ),
    ],

    "Snoco_tiles.py": [
        (
            'OUTPUT_DIR  = "/content/drive/MyDrive/treedata/Full_Image/SnoCo"',
            'from pipeline_config import FULL_IMAGE_DIR\n'
            'OUTPUT_DIR  = str(FULL_IMAGE_DIR / "SnoCo" / "v2")',
        ),
    ],

    "diagnostic.py": [
        (
            'BASE_DIR   = "/content/drive/MyDrive/treedata/Full_Image"',
            'from pipeline_config import FULL_IMAGE_DIR\n'
            'BASE_DIR   = str(FULL_IMAGE_DIR)',
        ),
    ],
}


# ── Patch engine ──────────────────────────────────────────────

def apply_patches(script_name, patches):
    path = SCRIPTS_DIR / script_name
    if not path.exists():
        print(f"  SKIP (not found): {script_name}")
        return 0

    original = path.read_text(encoding="utf-8")
    patched  = original

    applied = 0
    missed  = 0

    for old, new in patches:
        if old in patched:
            patched = patched.replace(old, new, 1)
            applied += 1
        else:
            print(f"    ⚠ Pattern not found in {script_name}:")
            # Show first 60 chars for debugging
            print(f"      {repr(old[:80])}")
            missed += 1

    if patched == original:
        print(f"  ✓ {script_name}  (no changes needed)")
        return 0

    if DRY_RUN:
        print(f"  {'→'} {script_name}  ({applied} patches, {missed} missed)")
    else:
        path.write_text(patched, encoding="utf-8")
        print(f"  ✓ {script_name}  ({applied} patches applied, {missed} missed)")

    return applied


# ── Run all patches ───────────────────────────────────────────

print("=" * 65)
print(f"  SCRIPT PATH PATCHING  —  "
      f"{'DRY RUN' if DRY_RUN else '*** LIVE — CHANGES APPLIED ***'}")
print("=" * 65)

total = 0
for script_name, patches in PATCHES.items():
    total += apply_patches(script_name, patches)

# ── Copy pipeline_config.py to Scripts if not already there ──
config_src  = SCRIPTS_DIR / "pipeline_config.py"
if not config_src.exists():
    print(f"\n  ⚠ pipeline_config.py not yet in Scripts/ — copy it manually:")
    print(f"    Upload pipeline_config.py to {SCRIPTS_DIR}")
else:
    print(f"\n  ✓ pipeline_config.py present in Scripts/")

print(f"\n  Total patches {'planned' if DRY_RUN else 'applied'}: {total}")

if DRY_RUN:
    print(f"\n  Set DRY_RUN = False and rerun to apply all changes.")
else:
    print(f"\n  All scripts updated. Run this to verify catalog status:")
    print(f"    %run /content/drive/MyDrive/treedata/Scripts/pipeline_config.py")
