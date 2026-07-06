"""
HIGH_RES_ORTHO File Investigator
=================================
One-off diagnostic script to understand why HIGH_RES_ORTHO images
failed to load in the QA tool.

Checks each file for:
  - Actual file format (magic bytes)
  - If ZIP: lists contents and tries to extract + open the inner TIF
  - If TIF: tries to open with rasterio and reports band/dtype/CRS info
  - Reports any errors in full

Run in Colab:
    %run /content/drive/MyDrive/treedata/Scripts/investigate_high_res_ortho.py
"""

import os
import struct
import zipfile
from io import BytesIO
from pathlib import Path

import numpy as np

# ── Config ───────────────────────────────────────────────────────────────────

DOWNLOAD_DIR  = Path('/content/edmonds_session/imagery')
DATASET_NAME  = 'HIGH_RES_ORTHO'
MAX_FILES     = 5          # How many files to inspect in detail (0 = all)
EXTRACT_DIR   = Path('/content/edmonds_session/ortho_extracted')

# ── Helpers ──────────────────────────────────────────────────────────────────

MAGIC = {
    b'\x49\x49\x2a\x00': 'TIFF (little-endian)',
    b'\x4d\x4d\x00\x2a': 'TIFF (big-endian)',
    b'\x50\x4b\x03\x04': 'ZIP',
    b'\x50\x4b\x05\x06': 'ZIP (empty)',
    b'\x1f\x8b\x08':     'GZIP',
    b'\x25\x50\x44\x46': 'PDF',
}

def detect_format(path: Path) -> str:
    with open(path, 'rb') as f:
        header = f.read(4)
    for magic, fmt in MAGIC.items():
        if header[:len(magic)] == magic:
            return fmt
    return f'Unknown (hex: {header.hex()})'


def inspect_zip(path: Path) -> dict:
    """Open ZIP and report contents."""
    result = {'format': 'ZIP', 'members': [], 'tif_members': [], 'errors': []}
    try:
        with zipfile.ZipFile(path) as zf:
            result['members'] = zf.namelist()
            result['tif_members'] = [
                m for m in zf.namelist()
                if m.lower().endswith(('.tif', '.tiff', '.img', '.jp2'))
            ]
    except Exception as e:
        result['errors'].append(str(e))
    return result


def inspect_tif(path: Path, data: bytes | None = None) -> dict:
    """Open TIF with rasterio and report metadata."""
    import rasterio
    result = {'format': 'TIF', 'errors': []}
    try:
        src_arg = BytesIO(data) if data else path
        with rasterio.open(src_arg) as src:
            result.update({
                'width':    src.width,
                'height':   src.height,
                'bands':    src.count,
                'dtype':    src.dtypes[0],
                'crs':      str(src.crs),
                'driver':   src.driver,
                'nodata':   src.nodata,
                'transform': str(src.transform),
            })
    except Exception as e:
        result['errors'].append(str(e))
    return result


def try_extract_and_open(zip_path: Path, member: str) -> dict:
    """Extract one member from a ZIP and try to open it with rasterio."""
    import rasterio
    result = {'member': member, 'errors': []}
    try:
        with zipfile.ZipFile(zip_path) as zf:
            data = zf.read(member)
        result['size_mb'] = len(data) / 1024**2
        tif_info = inspect_tif(zip_path, data=data)
        result.update(tif_info)
    except Exception as e:
        result['errors'].append(str(e))
    return result


# ── Main investigation ────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("HIGH_RES_ORTHO FILE INVESTIGATION")
    print("=" * 70)

    # Find all files for this dataset
    dataset_dir = None
    for year_dir in sorted(DOWNLOAD_DIR.iterdir()):
        candidate = year_dir / DATASET_NAME
        if candidate.exists():
            dataset_dir = candidate
            break

    if dataset_dir is None:
        # Try searching recursively
        matches = list(DOWNLOAD_DIR.rglob(f"*{DATASET_NAME}*"))
        if matches:
            dataset_dir = matches[0].parent
        else:
            print(f"\n✗ No files found for {DATASET_NAME} under {DOWNLOAD_DIR}")
            print("  Directory tree:")
            for p in sorted(DOWNLOAD_DIR.rglob('*'))[:30]:
                print(f"    {p.relative_to(DOWNLOAD_DIR)}")
            return

    files = sorted(dataset_dir.rglob('*'))
    files = [f for f in files if f.is_file()]
    print(f"\nFound {len(files)} file(s) in {dataset_dir}")

    inspect_targets = files if MAX_FILES == 0 else files[:MAX_FILES]

    # ── Per-file inspection ──────────────────────────────────────────────────
    format_counts: dict[str, int] = {}
    zip_member_extensions: set[str] = set()

    for i, fpath in enumerate(inspect_targets, 1):
        size_mb = fpath.stat().st_size / 1024**2
        fmt = detect_format(fpath)
        format_counts[fmt] = format_counts.get(fmt, 0) + 1

        print(f"\n[{i}/{len(inspect_targets)}] {fpath.name}")
        print(f"  Size   : {size_mb:.1f} MB")
        print(f"  Format : {fmt}")

        if fmt == 'ZIP':
            zip_info = inspect_zip(fpath)
            print(f"  Members ({len(zip_info['members'])}):")
            for m in zip_info['members']:
                ext = Path(m).suffix.lower()
                zip_member_extensions.add(ext)
                print(f"    {m}")

            if zip_info['errors']:
                print(f"  ZIP errors: {zip_info['errors']}")

            if zip_info['tif_members']:
                print(f"\n  Trying to open inner TIF: {zip_info['tif_members'][0]}")
                tif_info = try_extract_and_open(fpath, zip_info['tif_members'][0])
                if tif_info['errors']:
                    print(f"  ✗ Error: {tif_info['errors']}")
                else:
                    print(f"  ✓ Opened successfully:")
                    for k, v in tif_info.items():
                        if k not in ('errors', 'member'):
                            print(f"    {k:12s}: {v}")

        elif 'TIFF' in fmt:
            tif_info = inspect_tif(fpath)
            if tif_info['errors']:
                print(f"  ✗ Error: {tif_info['errors']}")
            else:
                print(f"  ✓ Opened successfully:")
                for k, v in tif_info.items():
                    if k != 'errors':
                        print(f"    {k:12s}: {v}")

        elif fmt == 'PDF':
            print("  ⚠ This is a PDF — likely a metadata/report file, not imagery")

        else:
            print(f"  ⚠ Unrecognised format — cannot open")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"\nTotal files inspected : {len(inspect_targets)} of {len(files)}")
    print(f"Format breakdown      :")
    for fmt, count in sorted(format_counts.items()):
        print(f"  {fmt:30s}: {count}")
    if zip_member_extensions:
        print(f"ZIP inner file types  : {sorted(zip_member_extensions)}")

    print("\nConclusion:")
    if 'ZIP' in format_counts:
        print("  Files are ZIP archives. The QA tool needs to extract them")
        print("  before rasterio can open them. Run extract_ortho_zips() below")
        print("  to unpack all ZIPs, then re-run stage 5 (QA).")
    elif all('TIFF' in f for f in format_counts):
        print("  Files are valid TIFFs — the issue is likely a rasterio driver")
        print("  or CRS problem. Check the error messages above.")
    else:
        print("  Mixed or unexpected formats — see per-file output above.")


def extract_ortho_zips(dry_run: bool = False):
    """Extract all HIGH_RES_ORTHO ZIPs in-place.

    After extraction, the original ZIP is left alongside the extracted TIF
    so you can verify before deleting. Re-run stage 5 once complete.

    Parameters
    ----------
    dry_run : if True, print what would be extracted without doing it.
    """
    print("\n" + "=" * 70)
    print("EXTRACTING HIGH_RES_ORTHO ZIPs")
    print("=" * 70)

    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    zips = list(DOWNLOAD_DIR.rglob(f"**/{DATASET_NAME}/*.tif"))
    # Also check files that are actually ZIPs saved as .tif (common USGS pattern)
    zip_tifs = [f for f in zips if detect_format(f) == 'ZIP']

    if not zip_tifs:
        print("  No ZIP-format .tif files found — nothing to extract.")
        return

    print(f"  Found {len(zip_tifs)} ZIP file(s) saved as .tif")
    extracted = 0

    for zip_path in sorted(zip_tifs):
        with zipfile.ZipFile(zip_path) as zf:
            tif_members = [m for m in zf.namelist()
                           if m.lower().endswith(('.tif', '.tiff'))]
            if not tif_members:
                print(f"  ⚠ {zip_path.name}: no TIF inside ZIP")
                continue

            for member in tif_members:
                out_path = zip_path.parent / Path(member).name
                if out_path.exists():
                    print(f"  ○ {out_path.name} already extracted")
                    continue
                if dry_run:
                    print(f"  [dry-run] would extract: {member} → {out_path}")
                else:
                    data = zf.read(member)
                    out_path.write_bytes(data)
                    size_mb = out_path.stat().st_size / 1024**2
                    print(f"  ✓ Extracted {out_path.name} ({size_mb:.1f} MB)")
                    extracted += 1

    if not dry_run:
        print(f"\n✓ Extracted {extracted} file(s) to their original directories")
        print("  You can now re-run stage 5 (QA tool) — it will find the extracted TIFs.")
        print("  Original ZIPs are still present if you want to verify before deleting.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    main()

    print("\n" + "─" * 70)
    print("To extract ZIP files, run:")
    print("  from investigate_high_res_ortho import extract_ortho_zips")
    print("  extract_ortho_zips(dry_run=True)   # preview first")
    print("  extract_ortho_zips()               # then actually extract")
