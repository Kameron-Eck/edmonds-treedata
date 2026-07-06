"""
inspect_anchor_labels.py — one-off QA of the 2020 anchor labels for one site.

Builds the SAME mask the fine-tune would burn under --anchor-labels (reads
phase3/edmonds_canopy_prob_2020.tif, thresholds canopy≥hi / bg≤lo / else IGNORE)
over a training site's 2020 footprint, then renders RGB | probability | label
overlay and prints the canopy / background / IGNORE percentages.

This is a read-only diagnostic — it writes nothing except a QA PNG.

Usage (Colab):
    %run /content/drive/MyDrive/treedata/Scripts/inspect_anchor_labels.py
    %run .../inspect_anchor_labels.py --site Negative_Parking --prob-hi 0.6 --prob-lo 0.4
    %run .../inspect_anchor_labels.py --site Forest_1
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import rasterio
import rasterio.warp
import rasterio.windows
from rasterio.enums import Resampling
import matplotlib.pyplot as plt

BASE       = Path("/content/drive/MyDrive/treedata")
PHOTOS_DIR = BASE / "photos"
PROB_2020  = BASE / "phase3" / "edmonds_canopy_prob_2020.tif"
OUT_DIR    = BASE / "phase4" / "qa"
IGNORE     = 255


def main():
    filtered = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
    p = argparse.ArgumentParser(description="QA the 2020 anchor labels for a site")
    p.add_argument("--site", default="Negative_Parking",
                   help="Site stem (matches photos/{site}_rgb.tif).")
    p.add_argument("--prob-hi", type=float, default=0.6,
                   help="prob ≥ this → canopy (1). Match your training run.")
    p.add_argument("--prob-lo", type=float, default=0.4,
                   help="prob ≤ this → background (0); between → IGNORE.")
    args = p.parse_args(filtered)

    photo = PHOTOS_DIR / f"{args.site}_rgb.tif"
    if not photo.exists():
        print(f"ERROR: site photo not found: {photo}"); sys.exit(1)
    if not PROB_2020.exists():
        print(f"ERROR: 2020 prob raster not found: {PROB_2020}"); sys.exit(1)

    print("=" * 60)
    print(f"  Anchor-label QA — {args.site}")
    print(f"  thresholds:  canopy ≥ {args.prob_hi}   background ≤ {args.prob_lo}")
    print("=" * 60)

    # ── 2020 RGB footprint (this is the site photo the pipeline crops from) ──
    with rasterio.open(photo) as ps:
        rgb = ps.read([1, 2, 3])
        H, W = ps.height, ps.width
        tf, crs, b = ps.transform, ps.crs, ps.bounds
    rgb_disp = np.transpose(rgb, (1, 2, 0))
    print(f"  footprint: {W}×{H}px   CRS {crs.to_string()}")

    # ── 2020 canopy probability, resampled onto the photo grid ──
    prob = np.full((H, W), np.nan, dtype=np.float32)
    with rasterio.open(PROB_2020) as pp:
        pcrs, pnod = pp.crs, pp.nodata
        pb = rasterio.warp.transform_bounds(crs, pcrs, b.left, b.bottom,
                                            b.right, b.top)
        win = rasterio.windows.from_bounds(*pb, transform=pp.transform)
        win = win.round_offsets(op="floor").round_lengths(op="ceil")
        win = win.intersection(rasterio.windows.Window(0, 0, pp.width, pp.height))
        if win.width <= 0 or win.height <= 0:
            print("  ERROR: site falls outside the 2020 prob coverage"); sys.exit(1)
        out_h = max(1, min(int(win.height), H))
        out_w = max(1, min(int(win.width),  W))
        arr = pp.read(1, window=win, out_shape=(out_h, out_w),
                      resampling=Resampling.average).astype(np.float32)
        wtf = pp.window_transform(win)
        stf = wtf * wtf.scale(win.width / out_w, win.height / out_h)
    if pnod is not None:
        arr[arr == pnod] = np.nan
    rasterio.warp.reproject(
        source=arr, destination=prob,
        src_transform=stf, src_crs=pcrs,
        dst_transform=tf, dst_crs=crs,
        src_nodata=np.nan, dst_nodata=np.nan,
        resampling=Resampling.average)

    # ── Threshold into the 0 / 1 / 255 training mask ──
    mask = np.full((H, W), IGNORE, dtype=np.uint8)
    mask[prob <= args.prob_lo] = 0
    mask[prob >= args.prob_hi] = 1

    tot = H * W
    n_can = int((mask == 1).sum())
    n_bg  = int((mask == 0).sum())
    n_ig  = int((mask == IGNORE).sum())
    print(f"\n  canopy  : {n_can / tot * 100:5.1f}%   ({n_can:,} px)")
    print(f"  backgrd : {n_bg  / tot * 100:5.1f}%   ({n_bg:,} px)")
    print(f"  IGNORE  : {n_ig  / tot * 100:5.1f}%   ({n_ig:,} px)")
    pv = prob[~np.isnan(prob)]
    if pv.size:
        print(f"  prob    : min {pv.min():.2f}  mean {pv.mean():.2f}  "
              f"max {pv.max():.2f}")
    if args.site.lower().startswith("negative") and n_can > 0:
        print(f"\n  ⚠ {n_can:,} canopy pixels in a NEGATIVE site — "
              f"the 2020 model is calling pavement/water canopy here.")

    # ── Figure: RGB | probability | label overlay ──
    fig, ax = plt.subplots(1, 3, figsize=(18, 6))

    ax[0].imshow(rgb_disp)
    ax[0].set_title(f"{args.site} — 2020 RGB")
    ax[0].axis("off")

    im = ax[1].imshow(prob, cmap="viridis", vmin=0, vmax=1)
    ax[1].set_title("2020 canopy probability")
    ax[1].axis("off")
    fig.colorbar(im, ax=ax[1], fraction=0.046, pad=0.04)

    ax[2].imshow(rgb_disp)
    overlay = np.zeros((H, W, 4), dtype=np.float32)
    overlay[mask == 1]      = [1.0, 0.0, 0.0, 0.45]   # canopy → red
    overlay[mask == IGNORE] = [0.5, 0.5, 0.5, 0.35]   # IGNORE → gray
    ax[2].imshow(overlay)                              # background → see-through
    ax[2].set_title(f"labels: canopy≥{args.prob_hi} (red) · "
                    f"IGNORE (gray) · bg (clear)")
    ax[2].axis("off")

    fig.suptitle(f"Anchor-label QA — {args.site}  "
                 f"(canopy {n_can/tot*100:.1f}%)", fontsize=14)
    fig.tight_layout()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_png = OUT_DIR / f"anchor_label_qa_{args.site}.png"
    fig.savefig(out_png, dpi=110, bbox_inches="tight")
    print(f"\n  ✓ saved: {out_png}")
    try:
        plt.show()
    except Exception:
        pass


if __name__ == "__main__":
    main()
