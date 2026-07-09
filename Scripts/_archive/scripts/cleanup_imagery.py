"""
cleanup_imagery.py — Full_Image folder cleanup & rename
========================================================
Standardizes all imagery filenames to {year}_{source}_{bands}.tif
across all source folders and the Pipeline Imagery working area.

Run in Colab:
    %run /content/drive/MyDrive/treedata/Scripts/cleanup_imagery.py

Set DRY_RUN = False to execute changes. Always run dry first.

WHAT THIS DOES:
  1. Pipeline Imagery/          — fix 2023_naip_rgbn → 2023_naip_rgbi
  2. Pipeline Imagery/registered/ — strip _v1 from 2013; move composite out
  3. Pipeline Imagery/upsample/  — delete old-style duplicates with illegal chars
  4. Edmonds/                    — rename 'Copy of edmonds_...' → {year}_coe_rgb.tif
  5. KingCo/                     — rename kingco_{year}_image → {year}_king_rgb.tif
  6. SnoCo/v2/                   — rename snoco_{year}_{band} → {year}_snoh_{bands}.tif
  7. SnoCo/ root                 — delete old-generation files (v2 is canonical)
  8. WA_NAIP/2019/               — rename + move 2023 files to WA_NAIP/2023/
"""

from pathlib import Path
import shutil

# ── Configuration ─────────────────────────────────────────────
DRY_RUN = True   # Set False to execute. Always verify dry run first.

BASE     = Path("/content/drive/MyDrive/treedata/Full_Image")
PI       = BASE / "Pipeline Imagery"
REG      = PI / "registered"
UPS      = PI / "upsample"
COMP_DIR = PI / "composites"   # new home for composite outputs

# ── Helpers ───────────────────────────────────────────────────
actions = []   # log of all planned operations

def rename(src, dst):
    src, dst = Path(src), Path(dst)
    if not src.exists():
        actions.append(f"  SKIP (not found): {src.name}")
        return
    if dst.exists():
        actions.append(f"  SKIP (dst exists): {dst.name}")
        return
    actions.append(f"  RENAME  {src.relative_to(BASE)}")
    actions.append(f"       →  {dst.relative_to(BASE)}")
    if not DRY_RUN:
        src.rename(dst)

def move(src, dst_dir):
    src, dst_dir = Path(src), Path(dst_dir)
    if not src.exists():
        actions.append(f"  SKIP (not found): {src.name}")
        return
    dst = dst_dir / src.name
    if dst.exists():
        actions.append(f"  SKIP (dst exists): {dst.name}")
        return
    actions.append(f"  MOVE    {src.relative_to(BASE)}")
    actions.append(f"       →  {dst.relative_to(BASE)}")
    if not DRY_RUN:
        dst_dir.mkdir(parents=True, exist_ok=True)
        src.rename(dst)

def delete(path):
    path = Path(path)
    if not path.exists():
        actions.append(f"  SKIP (not found): {path.name}")
        return
    size_gb = path.stat().st_size / 1e9
    actions.append(f"  DELETE  {path.relative_to(BASE)}  ({size_gb:.2f} GB)")
    if not DRY_RUN:
        path.unlink()

def mkdir(path):
    path = Path(path)
    actions.append(f"  MKDIR   {path.relative_to(BASE)}")
    if not DRY_RUN:
        path.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════
# 1. Pipeline Imagery/ root — fix naip band label
# ══════════════════════════════════════════════════════════════
actions.append("\n── 1. Pipeline Imagery/ root ──")

rename(PI / "2023_naip_rgbn.tif",
       PI / "2023_naip_rgbi.tif")


# ══════════════════════════════════════════════════════════════
# 2. Pipeline Imagery/registered/ — strip _v1, move composite
# ══════════════════════════════════════════════════════════════
actions.append("\n── 2. Pipeline Imagery/registered/ ──")

rename(REG / "2013_king_rgb_registered_v1.tif",
       REG / "2013_king_rgb_registered.tif")

mkdir(COMP_DIR)
move(REG / "hickman_overlap_composite.tif", COMP_DIR)


# ══════════════════════════════════════════════════════════════
# 3. Pipeline Imagery/upsample/ — delete old-style duplicates
#    These have illegal chars (* **) or old _edmonds_ naming
#    and are confirmed duplicates of the correctly named files.
# ══════════════════════════════════════════════════════════════
actions.append("\n── 3. Pipeline Imagery/upsample/ — delete old duplicates ──")

OLD_UPSAMPLE = [
    "2013_edmonds_upsampled.tif",
    "2015_edmonds_upsampled.tif",
    "2016*_edmonds_upsampled.tif",
    "2019**_edmonds_upsampled.tif",
    "2021*_edmonds_upsampled.tif",
]

for fname in OLD_UPSAMPLE:
    # glob to handle literal * in filename on filesystem
    matches = list(UPS.glob(fname.replace("*", "[*]")))
    # also try exact match for safety
    exact = UPS / fname
    candidates = matches + ([exact] if exact.exists() and exact not in matches else [])
    if candidates:
        for c in candidates:
            delete(c)
    else:
        actions.append(f"  SKIP (not found): {fname}")


# ══════════════════════════════════════════════════════════════
# 4. Edmonds/ source — rename 'Copy of' → {year}_coe_rgb.tif
#    Kept as source backups per decision.
# ══════════════════════════════════════════════════════════════
actions.append("\n── 4. Edmonds/ source folder ──")

EDMONDS = BASE / "Edmonds"
EDMONDS_RENAMES = {
    "Copy of edmonds_2015_image.tif": "2015_coe_rgb.tif",
    "Copy of edmonds_2017_image.tif": "2017_coe_rgb.tif",
    "Copy of edmonds_2020_image.tif": "2020_coe_rgb.tif",
    "Copy of edmonds_2022_image.tif": "2022_coe_rgb.tif",
    "Copy of edmonds_2024_image.tif": "2024_coe_rgb.tif",
}

for old, new in EDMONDS_RENAMES.items():
    rename(EDMONDS / old, EDMONDS / new)


# ══════════════════════════════════════════════════════════════
# 5. KingCo/ source — kingco_{year}_image → {year}_king_rgb
# ══════════════════════════════════════════════════════════════
actions.append("\n── 5. KingCo/ source folder ──")

KINGCO = BASE / "KingCo"
KINGCO_YEARS = [
    1936, 1998, 2000, 2002, 2005, 2007, 2009,
    2012, 2013, 2015, 2017, 2019, 2021, 2023,
]

for year in KINGCO_YEARS:
    rename(KINGCO / f"kingco_{year}_image.tif",
           KINGCO / f"{year}_king_rgb.tif")


# ══════════════════════════════════════════════════════════════
# 6. SnoCo/v2/ — snoco_{year}_{band} → {year}_snoh_{bands}
#    nir → ir to match convention
# ══════════════════════════════════════════════════════════════
actions.append("\n── 6. SnoCo/v2/ source folder ──")

SNOCO_V2 = BASE / "SnoCo" / "v2"
SNOCO_V2_RENAMES = {
    "snoco_2012_rgb.tif":  "2012_snoh_rgb.tif",
    "snoco_2016_nir.tif":  "2016_snoh_ir.tif",    # nir → ir
    "snoco_2016_rgb.tif":  "2016_snoh_rgb.tif",
    "snoco_2018_rgb.tif":  "2018_snoh_rgb.tif",
    "snoco_2020_rgb.tif":  "2020_snoh_rgb.tif",
    "snoco_2021_nir.tif":  "2021_snoh_ir.tif",    # nir → ir
    "snoco_2021_rgb.tif":  "2021_snoh_rgb.tif",
    "snoco_2022_rgb.tif":  "2022_snoh_rgb.tif",
    "snoco_2024_rgb.tif":  "2024_snoh_rgb.tif",
}

for old, new in SNOCO_V2_RENAMES.items():
    rename(SNOCO_V2 / old, SNOCO_V2 / new)


# ══════════════════════════════════════════════════════════════
# 7. SnoCo/ root — delete old-generation files
#    v2/ is canonical; root files confirmed for deletion.
# ══════════════════════════════════════════════════════════════
actions.append("\n── 7. SnoCo/ root — delete old files ──")

SNOCO_ROOT = BASE / "SnoCo"
SNOCO_ROOT_DELETE = [
    "snoco_1990_image.tif",
    "snoco_1996_image.tif",
    "snoco_1998_image.tif",
    "snoco_2001_image.tif",
    "snoco_2002_image.tif",
    "snoco_2003_image.tif",
    "snoco_2006_image.tif",
    "snoco_2009_image.tif",
    "snoco_2011_image.tif",
    "snoco_2012_image.tif",
    "snoco_2013_image.tif",
    "snoco_2015_image.tif",
    "snoco_2016_image.tif",
    "snoco_2017_image.tif",
    "snoco_2018_image.tif",
]

for fname in SNOCO_ROOT_DELETE:
    delete(SNOCO_ROOT / fname)


# ══════════════════════════════════════════════════════════════
# 8. WA_NAIP/ — rename files and fix misplaced 2023 files
# ══════════════════════════════════════════════════════════════
actions.append("\n── 8. WA_NAIP/ ──")

NAIP_2019_DIR = BASE / "WA_NAIP" / "2019"
NAIP_2023_DIR = BASE / "WA_NAIP" / "2023"

mkdir(NAIP_2023_DIR)

# Rename 2019 files in place
rename(NAIP_2019_DIR / "rgb_2019.tif", NAIP_2019_DIR / "2019_naip_rgb.tif")
rename(NAIP_2019_DIR / "ir_2019.tif",  NAIP_2019_DIR / "2019_naip_ir.tif")

# Move + rename misplaced 2023 files
# Need to rename then move since rename() keeps same folder
actions.append("  NOTE: 2023 NAIP files — rename then move to 2023/")
if not DRY_RUN:
    for old, new_name in [("rgb_2023.tif", "2023_naip_rgb.tif"),
                           ("ir_2023.tif",  "2023_naip_ir.tif")]:
        src = NAIP_2019_DIR / old
        if src.exists():
            NAIP_2023_DIR.mkdir(parents=True, exist_ok=True)
            src.rename(NAIP_2023_DIR / new_name)
else:
    actions.append(f"  MOVE+RENAME  WA_NAIP/2019/rgb_2023.tif")
    actions.append(f"           →  WA_NAIP/2023/2023_naip_rgb.tif")
    actions.append(f"  MOVE+RENAME  WA_NAIP/2019/ir_2023.tif")
    actions.append(f"           →  WA_NAIP/2023/2023_naip_ir.tif")


# ══════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════
print("=" * 65)
print(f"  IMAGERY CLEANUP  —  {'DRY RUN (no changes made)' if DRY_RUN else '*** LIVE RUN — CHANGES APPLIED ***'}")
print("=" * 65)

for line in actions:
    print(line)

# Counts
deletes = sum(1 for a in actions if "DELETE" in a)
renames = sum(1 for a in actions if "RENAME" in a)
moves   = sum(1 for a in actions if "MOVE" in a)
skips   = sum(1 for a in actions if "SKIP" in a)

print(f"\n  Renames : {renames}")
print(f"  Deletes : {deletes}")
print(f"  Moves   : {moves}")
print(f"  Skips   : {skips}")

if DRY_RUN:
    print(f"\n  ✓ Dry run complete. Set DRY_RUN = False and rerun to apply.")
else:
    print(f"\n  ✓ All changes applied.")

print(f"\n  Post-cleanup state reference:")
print(f"  Pipeline Imagery/           — {year}_{{source}}_{{bands}}.tif (active working files)")
print(f"  Pipeline Imagery/registered/ — {year}_{{source}}_{{bands}}_registered.tif")
print(f"  Pipeline Imagery/upsample/  — {year}_{{source}}_{{bands}}_upsampled.tif")
print(f"  Pipeline Imagery/composites/ — named outputs (burn composites etc)")
print(f"  Edmonds/                     — {year}_coe_rgb.tif (source backups)")
print(f"  KingCo/                      — {year}_king_rgb.tif (source archive)")
print(f"  SnoCo/v2/                    — {year}_snoh_{{rgb|ir}}.tif (source archive)")
print(f"  WA_NAIP/{{year}}/             — {year}_naip_{{rgb|ir}}.tif (source archive)")
