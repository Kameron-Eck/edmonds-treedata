"""
cleanup_registration.py — Delete all files from previous registration runs
===========================================================================
Clears local Colab scratch and Drive outputs so the next registration
run starts completely fresh. Run this before re-running coregister_imagery.py.

USAGE:
------
Option 1 — from a Colab cell (recommended):
    import sys
    sys.path.insert(0, "/content/drive/MyDrive/treedata/Scripts")
    if "cleanup_registration" in sys.modules:
        del sys.modules["cleanup_registration"]
    import cleanup_registration
    cleanup_registration.run(confirm=True)

Option 2 — dry run first to see what would be deleted:
    cleanup_registration.run(confirm=False)

Option 3 — delete only Drive upsample cache (most common need):
    cleanup_registration.delete_upsample_cache()

Option 4 — %run with flag (also works):
    %run /content/.../cleanup_registration.py --confirm

What gets deleted:
    Local /content/source_imagery/   — raw source copies
    Local /content/upsampled/        — local upsample scratch
    Local /content/registered/       — local registered scratch
    Drive .../upsample/*.tif         — upsampled King County cache
    Drive .../registered/*.tif       — registered output files
    Drive .../registered/*.csv       — registration log

What is NOT touched:
    Drive .../Full_Image/Pipeline Imagery/{year}_{source}_{bands}.tif  — raw sources
    Drive .../clips/                 — clip test files
    Drive .../building_footprints/   — building footprints
"""

import sys
from pathlib import Path

DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")
from pipeline_config import (
    DRIVE_BASE, IMAGERY_DIR, REGISTERED_DIR, UPSAMPLE_DIR,
)
DRIVE_OUTPUT   = REGISTERED_DIR
DRIVE_UPSAMPLE = UPSAMPLE_DIR

LOCAL_SRC_DIR    = Path("/content/source_imagery")
LOCAL_UPSAMPLE   = Path("/content/upsampled")
LOCAL_REGISTERED = Path("/content/registered")


def delete_upsample_cache(confirm: bool = True):
    """
    Delete only the Drive upsample cache files.
    Use this when upsampled files were written by the old concurrent
    writer and are corrupt — forces a clean rebuild on next run.
    """
    print("── Drive upsample cache ──")
    if not DRIVE_UPSAMPLE.exists():
        print("  Directory does not exist — nothing to delete")
        return
    files = list(DRIVE_UPSAMPLE.glob("*.tif"))
    if not files:
        print("  Already empty")
        return
    for f in sorted(files):
        size_gb = f.stat().st_size / 1e9
        if confirm:
            f.unlink()
            print(f"  Deleted: {f.name}  ({size_gb:.1f} GB)")
        else:
            print(f"  Would delete: {f.name}  ({size_gb:.1f} GB)")

    # Also clear local upsample scratch
    for f in LOCAL_UPSAMPLE.glob("*.tif") if LOCAL_UPSAMPLE.exists() else []:
        if confirm:
            f.unlink()
            print(f"  Deleted local: {f.name}")
        else:
            print(f"  Would delete local: {f.name}")

    if confirm:
        print("  Done — upsample cache cleared")
    else:
        print("  Dry run — pass confirm=True to actually delete")


def run(confirm: bool = False):
    """
    Delete all registration outputs for a fresh run.

    Parameters
    ----------
    confirm : bool
        Set True to actually delete. Default False = dry run.
    """
    mode = "LIVE DELETE" if confirm else "DRY RUN — pass confirm=True to actually delete"
    print("=" * 60)
    print(f"  CLEANUP REGISTRATION  [{mode}]")
    print("=" * 60)
    print()

    targets = [
        (LOCAL_SRC_DIR,    "*.tif", "Local source copies"),
        (LOCAL_UPSAMPLE,   "*.tif", "Local upsampled scratch"),
        (LOCAL_REGISTERED, "*.tif", "Local registered scratch"),
        (DRIVE_UPSAMPLE,   "*.tif", "Drive upsample cache"),
        (DRIVE_OUTPUT,     "*.tif", "Drive registered outputs"),
        (DRIVE_OUTPUT,     "*.csv", "Drive registration log"),
    ]

    total_size_gb = 0.0
    total_files   = 0

    for path, pattern, label in targets:
        print(f"  [{label}]")
        print(f"  {path}")
        if not path.exists():
            print(f"    Does not exist — skipping")
            print()
            continue
        files = list(path.glob(pattern))
        if not files:
            print(f"    Empty — nothing to delete")
            print()
            continue
        for f in sorted(files):
            size_gb = f.stat().st_size / 1e9
            total_size_gb += size_gb
            total_files   += 1
            if confirm:
                f.unlink()
                print(f"    Deleted: {f.name}  ({size_gb:.2f} GB)")
            else:
                print(f"    Would delete: {f.name}  ({size_gb:.2f} GB)")
        print()

    print(f"  Total: {total_files} files  {total_size_gb:.1f} GB")
    print()

    if not confirm:
        print("  Dry run complete. To actually delete:")
        print()
        print("    import sys")
        print("    sys.path.insert(0, '/content/drive/MyDrive/treedata/Scripts')")
        print("    if 'cleanup_registration' in sys.modules:")
        print("        del sys.modules['cleanup_registration']")
        print("    import cleanup_registration")
        print("    cleanup_registration.run(confirm=True)")
    else:
        print("  Cleanup complete — safe to re-run coregister_imagery.py")


# ── CLI entry point ───────────────────────────────────────────
# NOTE: sys.argv is NOT stripped here — --confirm must survive
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Delete registration outputs for a fresh run")
    parser.add_argument(
        "--confirm", action="store_true",
        help="Actually delete files (default is dry run)")

    # Strip only the Colab kernel launcher arg (-f /path/to/kernel.json)
    # but preserve --confirm and any other user args
    filtered = [a for a in sys.argv[1:]
                if not (a == "-f" or a.endswith(".json"))]
    args = parser.parse_args(filtered)
    run(confirm=args.confirm)