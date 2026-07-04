"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — Stage dedicated GRASS negative sites (grass-FP fix)
  Edmonds Temporal Active Learning Pipeline
╚══════════════════════════════════════════════════════════════════╝

WHY
───
The model calls grass "canopy" (grass = 64% of all false positives). The pipeline
already supports curated negative sites: any `photos/Negative_*_rgb.tif` is
auto-discovered (discover_site_footprints), tiled ALL-BACKGROUND, force-kept, and
pinned to train. Parking + water are the only ones so far — this adds lawns / sports
fields / the cemetery so the model sees plenty of "green but flat = NOT a tree".

CRITICAL: a negative site labels EVERY pixel background. If a footprint clips a
bordering tree, that tree becomes an injected false-negative. So footprints must sit
over PURE TURF. This script therefore writes to a STAGING dir and renders a preview
montage — you VERIFY turf-only, then move the good ones into photos/.

WORKFLOW (Colab, Drive mounted)
───────────────────────────────
  %cd /content/drive/MyDrive/treedata/Scripts
  !python make_grass_negatives.py                      # crop + montage → staging
  # open phase4/eval/grass_neg_preview.png, keep only turf-only boxes, tighten as needed
  !python make_grass_negatives.py --commit Cemetery Civic_Field Edmonds_Stadium
  #   ^ copies just the named, verified sites into photos/  (then run step tile)

COORDINATES ARE APPROXIMATE — confirm every box in the montage before --commit.
Edit SITES below (lon, lat, half-width m) to nudge/resize. Boxes are square.
"""

import argparse
import shutil
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform as warp_transform
from rasterio.windows import from_bounds

BASE = None
for cand in (Path("/content/drive/MyDrive/treedata"),
             Path(r"G:\My Drive\treedata")):
    if cand.exists():
        BASE = cand
        break
if BASE is None:
    sys.exit("ERROR: treedata not found (Colab mount or G:\\ drive)")

PHOTOS_DIR = BASE / "photos"
STAGE_DIR  = BASE / "photos" / "_grass_neg_staging"
PREVIEW    = BASE / "phase4" / "eval" / "grass_neg_preview.png"
# Source ortho for the crops — 2020 CoE 7.5 cm is clearest for turf verification.
SRC_ORTHO  = BASE / "Full_Image/Pipeline Imagery/2020_coe_rgb.tif"

# name -> (lon, lat, half_width_m).  APPROXIMATE centres — verify in the montage.
# Safest (uniform turf, no tree borders): Cemetery, the stadium/HS fields.
# Parks have tree edges — keep boxes small/interior.
SITES = {
    "Cemetery":        (-122.3835, 47.7987, 90),   # Edmonds Memorial Cemetery — uniform lawn
    "Civic_Field":     (-122.3822, 47.8125, 90),   # Civic Center Playfield
    "Edmonds_Stadium": (-122.3600, 47.8069, 110),  # Edmonds Stadium / EW HS fields
    "Meadowdale_PF":   (-122.3435, 47.8478, 110),  # Meadowdale Playfields
    "Seaview_PF":      (-122.3892, 47.8120, 70),   # Seaview Park ballfields (tight — tree borders)
    "Hickman_PF":      (-122.3300, 47.7940, 70),   # Hickman Park playfield (tight — tree borders)
}


def crop_site(src, lon, lat, half_m):
    """Crop a square box (± half_m metres) around (lon,lat) from the ortho →
    (rgb uint8 HWC, window_transform, crs) or None if out of the ortho extent."""
    xs, ys = warp_transform("EPSG:4326", src.crs, [lon], [lat])
    cx, cy = xs[0], ys[0]
    # ortho is EPSG:3857 (metres); half_m ≈ metres directly at this latitude.
    left, right = cx - half_m, cx + half_m
    bottom, top = cy - half_m, cy + half_m
    if not (src.bounds.left < cx < src.bounds.right
            and src.bounds.bottom < cy < src.bounds.top):
        return None
    win = from_bounds(left, bottom, right, top, src.transform)
    rgb = src.read((1, 2, 3), window=win, boundless=True, fill_value=0)
    wtf = src.window_transform(win)
    return rgb.transpose(1, 2, 0), wtf, src.crs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", nargs="*", default=None,
                    help="copy these verified site names from staging into photos/")
    ap.add_argument("--src", default=str(SRC_ORTHO), help="source ortho for crops")
    args = ap.parse_args()

    if args.commit is not None:
        n = 0
        for name in args.commit:
            s = STAGE_DIR / f"Negative_{name}_rgb.tif"
            if not s.exists():
                print(f"  !! {s.name} not in staging — skipped"); continue
            shutil.copy2(s, PHOTOS_DIR / s.name)
            print(f"  ✓ committed {s.name} → photos/"); n += 1
        print(f"Committed {n} grass negative site(s). Now run `step tile`.")
        return

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW.parent.mkdir(parents=True, exist_ok=True)
    crops = []
    with rasterio.open(args.src) as src:
        prof0 = src.profile
        for name, (lon, lat, half_m) in SITES.items():
            got = crop_site(src, lon, lat, half_m)
            if got is None:
                print(f"  – {name}: OUTSIDE ortho extent — skipped")
                continue
            rgb, wtf, crs = got
            out = STAGE_DIR / f"Negative_{name}_rgb.tif"
            prof = prof0.copy()
            prof.update(count=3, height=rgb.shape[0], width=rgb.shape[1],
                        transform=wtf, crs=crs, dtype="uint8", compress="lzw")
            with rasterio.open(out, "w", **prof) as w:
                w.write(rgb.transpose(2, 0, 1))
            crops.append((name, rgb, half_m))
            print(f"  ✓ {name}: {rgb.shape[1]}x{rgb.shape[0]} px → staging/{out.name}")

    if not crops:
        sys.exit("No sites cropped — all outside extent? Check SITES / --src.")
    ncol = min(3, len(crops))
    nrow = (len(crops) + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(4 * ncol, 4 * nrow))
    axes = np.atleast_1d(axes).ravel()
    for ax, (name, rgb, half_m) in zip(axes, crops):
        ax.imshow(rgb)
        ax.set_title(f"{name}  (±{half_m} m)", fontsize=9)
        ax.set_xticks([]); ax.set_yticks([])
    for ax in axes[len(crops):]:
        ax.axis("off")
    fig.suptitle("Grass negative candidates — KEEP only pure-turf boxes "
                 "(no tree borders)", fontsize=11)
    fig.tight_layout()
    fig.savefig(PREVIEW, dpi=110, bbox_inches="tight")
    print(f"\nPreview → {PREVIEW}")
    print("Inspect it, then: python make_grass_negatives.py --commit "
          "<Name> <Name> ...  (only the turf-only ones).")


if __name__ == "__main__":
    main()
