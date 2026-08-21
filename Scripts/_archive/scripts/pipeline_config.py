"""
pipeline_config.py — LEGACY paths + FROZEN legacy catalog. NOT authoritative.
===============================================================================
DO NOT ADD YEARS HERE. The authoritative imagery catalog is

    phase4seg/config.py : YEAR_CATALOG          <-- one home for the catalog
    phase4seg/config.py : imagery_roots()       <-- one home for path resolution

This file used to call itself the "single source of truth" while omitting every
pre-2013 acquisition, so `raw_path(2000)` raised KeyError even though 2000 is a
catalog year the engine trains on. Two files claiming one fact is the bug the
repo's one-fact-one-home rule exists to prevent; demoted 2026-08-19 per
IMAGERY_PLAN.md A1.

WHAT IS STILL LIVE HERE
    The DIRECTORY constants (DRIVE_BASE, IMAGERY_DIR, SOURCE_DIRS, ...) — the
    Phase-0/1 download and registration scripts in `_archive/scripts/` import
    them. Those are the only remaining importers.

WHAT IS FROZEN
    IMAGERY_CATALOG / SOURCE_CODES / TARGET_YEARS / SUPPLEMENTAL_YEARS and the
    raw_path/registered_path/upsampled_path helpers. Kept verbatim so the
    archived scripts still parse. They cover 2013+ only and will not be updated.
    New code must read YEAR_CATALOG and resolve through config.imagery_roots();
    `phase4_catalog_check.py` tests that every entry there resolves and opens.

USAGE (paths only — for the catalog, import phase4seg.config):
    import sys
    sys.path.insert(0, "/content/drive/MyDrive/treedata/Scripts")
    from pipeline_config import (
        DRIVE_BASE, IMAGERY_DIR, REGISTERED_DIR, UPSAMPLE_DIR,
        IMAGERY_CATALOG, SOURCE_CODES, raw_path, registered_path,
        upsampled_path, get_available_registered,
    )
"""

from pathlib import Path

# ── Root paths ────────────────────────────────────────────────
DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")
FULL_IMAGE_DIR = DRIVE_BASE / "Full_Image"

# ── Pipeline working area ─────────────────────────────────────
IMAGERY_DIR    = FULL_IMAGE_DIR / "Pipeline Imagery"
REGISTERED_DIR = IMAGERY_DIR / "registered"
UPSAMPLE_DIR   = IMAGERY_DIR / "upsample"
COMPOSITES_DIR = IMAGERY_DIR / "composites"

# ── Source archive folders (read-only reference) ──────────────
SOURCE_DIRS = {
    "coe":  FULL_IMAGE_DIR / "Edmonds",
    "king": FULL_IMAGE_DIR / "KingCo",
    "snoh": FULL_IMAGE_DIR / "SnoCo" / "v2",
    "naip": FULL_IMAGE_DIR / "WA_NAIP",
}

# ── Other pipeline folders ────────────────────────────────────
BUILDINGS_JSON  = DRIVE_BASE / "building_footprints" / "data.json"
PHOTOS_DIR      = DRIVE_BASE / "photos"
POLYGONS_DIR    = DRIVE_BASE / "polygons"
LABELS_DIR      = DRIVE_BASE / "labels"
TILES_DIR       = DRIVE_BASE / "tiles"
CHECKPOINTS_DIR = DRIVE_BASE / "checkpoints"
INFERENCE_DIR   = DRIVE_BASE / "inference"
REVIEW_DIR      = DRIVE_BASE / "review_data"
CLIPS_DIR       = DRIVE_BASE / "clips"
SCRIPTS_DIR     = DRIVE_BASE / "Scripts"

# ── Imagery catalog — FROZEN LEGACY, 2013+ ONLY ───────────────
# NOT the catalog. See phase4seg/config.py:YEAR_CATALOG (18 acquisitions,
# 2000-2024, with measured gsd_cm / bands / crs / coverage). This dict is kept
# only so the archived Phase-0/1 scripts still import. Do not add years.
# Maps catalog key → filename in IMAGERY_DIR (Pipeline Imagery/)
# Keys:
#   int  = standard year, single source (CoE or King County)
#   str* = supplemental year with IR capability / multiple sources
#     "2016*" = Snohomish County 2016 — has NIR band
#     "2019*" = NAIP 2019           — has NIR band (vs int 2019 = King County RGB)
#     "2021*" = Snohomish County 2021 — has NIR band (vs int 2021 = King County RGB)
#     "2022*" = NAIP 2022           — has NIR band (vs int 2022 = CoE RGB)
#
# * in catalog keys = IR-capable year. Illegal in filenames — strip when
# building paths. Source code suffix handles disambiguation in filenames:
#   key "2019*" → file "2019_naip_rgbi.tif"  (not "2019_king_rgb.tif")
IMAGERY_CATALOG = {
    # ── King County (14.92 cm native → upsampled to 7.62 cm) ──
    2013:    "2013_king_rgb.tif",
    2015:    "2015_king_rgb.tif",
    2019:    "2019_king_rgb.tif",
    2021:    "2021_king_rgb.tif",
    2023:    "2023_king_rgb.tif",

    # ── City of Edmonds (7.62 cm native, no upsample needed) ──
    2017:    "2017_coe_rgb.tif",
    2020:    "2020_coe_rgb.tif",   # BASE YEAR
    2022:    "2022_coe_rgb.tif",
    2024:    "2024_coe_rgb.tif",

    # ── Snohomish County (50 cm native, 4-band RGBI) ──────────
    "2016*": "2016_snoh_rgbi.tif",   # merged RGB+IR
    "2021*": "2021_snoh_rgbi.tif",   # merged RGB+IR

    # ── Snohomish County standalone bands ─────────────────────
    "2016_ir":  "2016_snoh_ir.tif",
    "2016_rgb": "2016_snoh_rgb.tif",
    "2021_ir":  "2021_snoh_ir.tif",
    "2021_rgb": "2021_snoh_rgb.tif",

    # ── NAIP (1 m native, 4-band RGBI) ────────────────────────
    "2019*": "2019_naip_rgbi.tif",   # pending registration
    "2022*": "2022_naip_rgbi.tif",   # pending registration
}

# ── Source codes by catalog key ───────────────────────────────
SOURCE_CODES = {
    2013: "king", 2015: "king", 2019: "king", 2021: "king", 2023: "king",
    2017: "coe",  2020: "coe",  2022: "coe",  2024: "coe",
    "2016*": "snoh", "2021*": "snoh",
    "2016_ir": "snoh", "2016_rgb": "snoh",
    "2021_ir": "snoh", "2021_rgb": "snoh",
    "2019*": "naip", "2022*": "naip",
}

# ── Years used as active temporal stack ───────────────────────
# Standard single-source years (integer keys)
TARGET_YEARS = [2013, 2015, 2017, 2019, 2021, 2022, 2023, 2024]

# Supplemental multi-source years (string keys)
# * suffix = second source for a year that already has an int key,
#   or a source that needs disambiguation
SUPPLEMENTAL_YEARS = ["2016*", "2019*", "2021*", "2022*"]

# Base year — never co-registered, used as reference
REFERENCE_YEAR = 2020


# ── Path helpers ──────────────────────────────────────────────

def _catalog_key(year):
    """Normalize year to catalog key. Handles int, str, and star keys."""
    if year in IMAGERY_CATALOG:
        return year
    try:
        return int(year)
    except (ValueError, TypeError):
        return year


def raw_path(year) -> Path:
    """Full path to raw source file in Pipeline Imagery/."""
    key = _catalog_key(year)
    if key not in IMAGERY_CATALOG:
        raise KeyError(f"Year {year!r} not in IMAGERY_CATALOG")
    return IMAGERY_DIR / IMAGERY_CATALOG[key]


def _stem(year) -> str:
    """Filename stem (no .tif) for a given year, used for derived filenames."""
    return raw_path(year).stem   # e.g. "2019_king_rgb"


def upsampled_path(year) -> Path:
    """Full path to upsampled cache file."""
    return UPSAMPLE_DIR / f"{_stem(year)}_upsampled.tif"


def registered_path(year) -> Path:
    """Full path to registered output file."""
    return REGISTERED_DIR / f"{_stem(year)}_registered.tif"


def get_available_registered(include_supplemental=False) -> dict:
    """
    Return {year_key: Path} for all registered files that exist on Drive.
    Skips the base year (2020) — it is never registered.

    Parameters
    ----------
    include_supplemental : bool
        If True, also include string-keyed supplemental years.
    """
    years = list(TARGET_YEARS)
    if include_supplemental:
        years += SUPPLEMENTAL_YEARS

    available = {}
    for year in years:
        if year == REFERENCE_YEAR:
            # Base year uses raw path, not registered
            p = raw_path(REFERENCE_YEAR)
            if p.exists():
                available[REFERENCE_YEAR] = p
            continue
        p = registered_path(year)
        if p.exists():
            available[year] = p
        else:
            print(f"  ⚠ Missing registered: {p.name}")
    return available


def print_catalog_status():
    """Print the status of all catalog entries — exists / missing."""
    print("=" * 65)
    print("  IMAGERY CATALOG STATUS")
    print("=" * 65)
    print(f"  {'Key':<10} {'File':<35} {'Status':>12} {'Size':>8}")
    print(f"  {'-'*10} {'-'*35} {'-'*12} {'-'*8}")

    all_keys = list(IMAGERY_CATALOG.keys())
    for key in all_keys:
        p = raw_path(key)
        exists = p.exists()
        size   = f"{p.stat().st_size/1e9:.1f} GB" if exists else "—"
        status = "✓ exists" if exists else "✗ missing"
        print(f"  {str(key):<10} {p.name:<35} {status:>12} {size:>8}")

    print(f"\n  Registered outputs:")
    print(f"  {'-'*10} {'-'*35} {'-'*12} {'-'*8}")
    for year in TARGET_YEARS + SUPPLEMENTAL_YEARS:
        if year == REFERENCE_YEAR:
            continue
        p = registered_path(year)
        exists = p.exists()
        size   = f"{p.stat().st_size/1e9:.1f} GB" if exists else "—"
        status = "✓ exists" if exists else "✗ missing"
        print(f"  {str(year):<10} {p.name:<35} {status:>12} {size:>8}")


if __name__ == "__main__":
    print_catalog_status()