"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 QA — Canopy-mask overlay viewer (visual check)
  Edmonds Temporal Active Learning Pipeline

  Overlays a year's Phase 4 canopy MASK (and probability raster) on its
  NATIVE ortho so you can eyeball what the model is doing — built for
  diagnosing the year-2000 over-prediction, but works for any year.

  Produces, per year:
    1. Full-city overview  — decimated RGB | mask overlay | prob heatmap
    2. Native-res crops    — zoomed windows at the training sites
                             (Negative_Parking / Negative_Water / a Forest),
                             so you can see false positives on pavement/water
    3. Probability histogram over the imaged (non-nodata) area
    4. Printed canopy fraction over imaged area

  Nothing is ever read at full size — the ortho is ~500 MP. The overview
  uses a decimated read; crops use small native-resolution windows.

  USAGE (Colab)
  ─────────────
  %run phase4_qa_overlay.py                       # year 2000, sites + overview
  %run phase4_qa_overlay.py --year 2000 --max-dim 2600
  %run phase4_qa_overlay.py --year 2005 --crop-size-m 250
  %run phase4_qa_overlay.py --year 2000 --crop "custom:-1.36e7,6.05e6"
  %run phase4_qa_overlay.py --year 2000 --no-overview   # crops only
  Figures are shown inline (Colab) AND saved to phase4/qa/{year}/.
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
from pathlib import Path


# ── Dependency bootstrap (same pattern as the phase scripts) ──────────────────


# Dep bootstrap: mechanism in phase4seg/deps.py (refactor 2.3); the LIST stays
# per-file — nine distinct sets exist and one shared list would over-install.
from phase4seg.deps import ensure_deps as _ensure_deps  # noqa: E402
_ensure_deps([("rasterio", "rasterio"), ("matplotlib", "matplotlib"),
                    ("numpy", "numpy")])

import numpy as np
import rasterio
import rasterio.warp
import rasterio.windows
from rasterio.enums import Resampling

import matplotlib
import matplotlib.pyplot as plt
from phase4seg.names import clean_argv  # noqa: E402


# ── Paths (Edmonds Drive layout; falls back gracefully) ───────────────────────
BASE        = Path("/content/drive/MyDrive/treedata")
IMAGERY_DIR = BASE / "Full_Image/Pipeline Imagery"
NATIVE_DIR  = IMAGERY_DIR / "native"
MASKS_DIR   = BASE / "phase4" / "masks"
PHOTOS_DIR  = BASE / "photos"          # training-site footprints (for crop centres)
QA_DIR      = BASE / "phase4" / "qa"

# Native ortho filename per the phase4 catalog (glob fallback if renamed).
NATIVE_FILE = {
    "2000": "2000_king_rgb.tif",  "2002": "2002_king_rgb.tif",
    "2005": "2005_king_rgb.tif",  "2007": "2007_king_rgb.tif",
    "2009": "2009_king_rgb.tif",  "2013": "2013_king_rgb.tif",
    "2015": "2015_king_rgb.tif",  "2016": "2016_snoh_rgbi.tif",
    "2017": "2017_coe_rgb.tif",   "2019": "2019_king_rgb.tif",
    "2019n": "2019_naip_rgbi.tif", "2020": "2020_coe_rgb.tif",
    "2021": "2021_king_rgb.tif",  "2021s": "2021_snoh_rgbi.tif",
    "2022": "2022_coe_rgb.tif",   "2023n": "2023_naip_rgbi.tif",
    "2023": "2023_king_rgb.tif",  "2024": "2024_coe_rgb.tif",
}

CANOPY_COLOR = (255, 45, 45)   # overlay colour for predicted canopy (red → false positives pop)
OVERLAY_ALPHA = 0.45


# ── File resolution ───────────────────────────────────────────────────────────
def resolve_ortho(year):
    fname = NATIVE_FILE.get(year)
    cands = []
    if fname:
        cands += [NATIVE_DIR / fname, IMAGERY_DIR / fname]
    # glob fallback (e.g. file renamed)
    for d in (NATIVE_DIR, IMAGERY_DIR):
        cands += sorted(d.glob(f"*{year}*rgb*.tif")) + sorted(d.glob(f"{year}_*.tif"))
    for c in cands:
        if c.exists():
            return c
    raise FileNotFoundError(
        f"Native ortho for {year} not found. Looked in {NATIVE_DIR} and {IMAGERY_DIR}.")


def resolve_mask(year):
    p = MASKS_DIR / f"edmonds_canopy_mask_{year}.tif"
    return p if p.exists() else None


def resolve_prob(year):
    p = MASKS_DIR / f"edmonds_canopy_prob_{year}.tif"
    return p if p.exists() else None


# ── Readers (always decimated or windowed — never the full 500 MP) ────────────
def _rgb_first3(arr):
    """arr is (bands, h, w); return (h, w, 3) uint8 using the first 3 bands."""
    arr = arr[:3]
    if arr.shape[0] == 1:                      # single-band ortho → grey to RGB
        arr = np.repeat(arr, 3, axis=0)
    return np.transpose(arr, (1, 2, 0)).astype(np.uint8)


def read_decimated_rgb(path, max_dim):
    with rasterio.open(path) as src:
        scale = max(src.width, src.height) / float(max_dim)
        scale = max(scale, 1.0)
        out_w = max(1, int(round(src.width / scale)))
        out_h = max(1, int(round(src.height / scale)))
        n = min(3, src.count)
        arr = src.read(list(range(1, n + 1)),
                       out_shape=(n, out_h, out_w),
                       resampling=Resampling.average)
        return _rgb_first3(arr), (src.width, src.height), src.crs, src.transform


def read_decimated_band(path, out_h, out_w, resampling=Resampling.nearest):
    with rasterio.open(path) as src:
        a = src.read(1, out_shape=(out_h, out_w), resampling=resampling)
        return a, src.nodata, (src.width, src.height)


def read_window_rgb(src, cx, cy, size_m):
    """Native-resolution RGB window centred on (cx, cy) in the ortho CRS."""
    half = size_m / 2.0
    win = rasterio.windows.from_bounds(
        cx - half, cy - half, cx + half, cy + half, transform=src.transform)
    win = win.round_offsets(op="floor").round_lengths(op="ceil")
    full = rasterio.windows.Window(0, 0, src.width, src.height)
    win = win.intersection(full)
    if win.width <= 0 or win.height <= 0:
        return None, None
    arr = src.read([1, 2, 3] if src.count >= 3 else [1], window=win,
                   boundless=True, fill_value=0)
    return _rgb_first3(arr), win


def read_window_band(path, win, ortho_wh):
    """Read the same geographic window from a mask/prob raster of the same grid."""
    with rasterio.open(path) as src:
        # If the raster shares the ortho grid, the window indices line up directly.
        if (src.width, src.height) != ortho_wh:
            # Different grid → reproject the window by bounds instead of indices.
            return None, src.nodata
        a = src.read(1, window=win, boundless=True, fill_value=255)
        return a, src.nodata


# ── Overlay + helpers ─────────────────────────────────────────────────────────
def canopy_bool(mask_arr, nodata):
    valid = mask_arr != (255 if nodata is None else nodata)
    canopy = (mask_arr >= 1) & valid
    return canopy, valid


def overlay(rgb_hw3, canopy, color=CANOPY_COLOR, alpha=OVERLAY_ALPHA):
    out = rgb_hw3.astype(np.float32).copy()
    for c in range(3):
        ch = out[..., c]
        ch[canopy] = (1 - alpha) * ch[canopy] + alpha * color[c]
    return out.clip(0, 255).astype(np.uint8)


def prob_to_display(prob_arr, nodata):
    p = prob_arr.astype(np.float32)
    nd = 255 if nodata is None else nodata
    p[prob_arr == nd] = np.nan
    return p / 254.0     # uint8 prob raster stores 0–254, 255 = nodata


def discover_site_centres(ortho_crs):
    """Centres (in ortho CRS) of each training-site footprint, from photos/*_rgb.tif."""
    centres = []
    if not PHOTOS_DIR.exists():
        return centres
    for photo in sorted(PHOTOS_DIR.glob("*_rgb.tif")):
        name = photo.stem.replace("_rgb", "")
        with rasterio.open(photo) as src:
            b, pcrs = src.bounds, src.crs
        if pcrs is not None and ortho_crs is not None and pcrs != ortho_crs:
            b = rasterio.coords.BoundingBox(
                *rasterio.warp.transform_bounds(pcrs, ortho_crs, *b))
        centres.append((name, (b.left + b.right) / 2.0, (b.bottom + b.top) / 2.0))
    return centres


# ── Figures ───────────────────────────────────────────────────────────────────
def fig_overview(year, ortho_path, mask_path, prob_path, max_dim, out_dir, show):
    rgb, ortho_wh, crs, _ = read_decimated_rgb(ortho_path, max_dim)
    h, w = rgb.shape[:2]
    print(f"  Overview: ortho {ortho_wh[0]}×{ortho_wh[1]}px → decimated {w}×{h}")

    panels = [("Imagery", rgb)]
    canopy = valid = None
    if mask_path:
        m, m_nd, m_wh = read_decimated_band(mask_path, h, w, Resampling.nearest)
        if m_wh != ortho_wh:
            print(f"  ⚠ mask grid {m_wh} ≠ ortho grid {ortho_wh}; overlay may be "
                  f"slightly misaligned (still useful for a gestalt check).")
        canopy, valid = canopy_bool(m, m_nd)
        panels.append(("Mask overlay", overlay(rgb, canopy)))
        frac = float(canopy.sum()) / max(int(valid.sum()), 1)
        print(f"  Canopy over imaged area (decimated): {frac*100:.1f}%")
    if prob_path:
        p, p_nd, _ = read_decimated_band(prob_path, h, w, Resampling.average)
        panels.append(("Probability", prob_to_display(p, p_nd)))

    n = len(panels)
    fig, axes = plt.subplots(1, n, figsize=(7 * n, 7 * h / w + 1))
    if n == 1:
        axes = [axes]
    for ax, (title, img) in zip(axes, panels):
        if title == "Probability":
            im = ax.imshow(img, cmap="RdYlGn", vmin=0, vmax=1)
            fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        else:
            ax.imshow(img)
        ax.set_title(f"{year} — {title}", fontsize=12)
        ax.axis("off")
    fig.tight_layout()
    out = out_dir / f"{year}_overview.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    print(f"  ✓ {out}")
    if show:
        plt.show()
    plt.close(fig)
    return canopy, valid


def fig_prob_hist(year, prob_path, out_dir, show):
    if not prob_path:
        return
    # Decimated read is plenty for a histogram.
    p, p_nd, _ = read_decimated_band(prob_path, 1200, 1200, Resampling.nearest)
    vals = prob_to_display(p, p_nd)
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(vals, bins=50, color="#3a7", edgecolor="white")
    ax.axvline(0.5, color="k", ls="--", lw=1, label="threshold 0.5")
    ax.set_xlabel("predicted canopy probability")
    ax.set_ylabel("pixel count (decimated)")
    ax.set_title(f"{year} — probability distribution over imaged area")
    ax.legend()
    fig.tight_layout()
    out = out_dir / f"{year}_prob_hist.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")
    print(f"  ✓ {out}")
    if show:
        plt.show()
    plt.close(fig)


def fig_crops(year, ortho_path, mask_path, crops, size_m, out_dir, show):
    """crops: list of (name, cx, cy) in ortho CRS."""
    if not crops:
        return
    with rasterio.open(ortho_path) as src:
        ortho_wh = (src.width, src.height)
        rows = []
        for name, cx, cy in crops:
            rgb, win = read_window_rgb(src, cx, cy, size_m)
            if rgb is None:
                print(f"  {name:<20} outside ortho extent — skipped")
                continue
            ov = rgb
            if mask_path:
                m, m_nd = read_window_band(mask_path, win, ortho_wh)
                if m is not None and m.shape == rgb.shape[:2]:
                    canopy, _ = canopy_bool(m, m_nd)
                    ov = overlay(rgb, canopy)
            rows.append((name, rgb, ov))

    if not rows:
        return
    fig, axes = plt.subplots(len(rows), 2, figsize=(10, 5 * len(rows)))
    if len(rows) == 1:
        axes = np.array([axes])
    for i, (name, rgb, ov) in enumerate(rows):
        axes[i, 0].imshow(rgb); axes[i, 0].set_title(f"{name} — imagery", fontsize=11)
        axes[i, 1].imshow(ov);  axes[i, 1].set_title(f"{name} — mask overlay", fontsize=11)
        for j in (0, 1):
            axes[i, j].axis("off")
    fig.suptitle(f"{year} — native-resolution crops ({size_m:.0f} m)", fontsize=13)
    fig.tight_layout()
    out = out_dir / f"{year}_crops.png"
    fig.savefig(out, dpi=120, bbox_inches="tight")
    print(f"  ✓ {out}")
    if show:
        plt.show()
    plt.close(fig)


# ── main ──────────────────────────────────────────────────────────────────────
def _parse_custom_crops(items, crs):
    out = []
    for it in items or []:
        try:
            name, coords = it.split(":")
            x, y = (float(v) for v in coords.split(","))
            out.append((name, x, y))
        except Exception:
            print(f"  ⚠ could not parse --crop {it!r} (expected name:x,y in ortho CRS)")
    return out


def main():
    filtered = clean_argv()
    p = argparse.ArgumentParser(description="Phase 4 QA — canopy mask overlay viewer")
    p.add_argument("--year", default="2000")
    p.add_argument("--max-dim", type=int, default=2400,
                   help="longest side (px) of the decimated full-city overview")
    p.add_argument("--crop-size-m", type=float, default=300.0,
                   help="side length (m) of each native-resolution crop")
    p.add_argument("--crop", action="append", default=None,
                   help="custom crop 'name:x,y' (x,y in the ortho CRS); repeatable")
    p.add_argument("--no-sites", action="store_true",
                   help="don't auto-crop the training-site footprints")
    p.add_argument("--no-overview", action="store_true")
    p.add_argument("--no-show", action="store_true",
                   help="save figures but don't display (headless)")
    p.add_argument("--out-dir", default=None)
    args = p.parse_args(filtered)

    year = args.year
    show = not args.no_show
    if args.no_show:
        matplotlib.use("Agg")

    ortho_path = resolve_ortho(year)
    mask_path = resolve_mask(year)
    prob_path = resolve_prob(year)
    out_dir = Path(args.out_dir) if args.out_dir else (QA_DIR / year)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n── Phase 4 QA overlay — {year} ──")
    print(f"  Ortho: {ortho_path}")
    print(f"  Mask : {mask_path if mask_path else 'NOT FOUND — overlay skipped'}")
    print(f"  Prob : {prob_path if prob_path else 'NOT FOUND — heatmap/hist skipped'}")
    print(f"  Out  : {out_dir}")

    with rasterio.open(ortho_path) as src:
        ortho_crs = src.crs

    if not args.no_overview:
        fig_overview(year, ortho_path, mask_path, prob_path, args.max_dim, out_dir, show)
        fig_prob_hist(year, prob_path, out_dir, show)

    crops = []
    if not args.no_sites:
        crops += discover_site_centres(ortho_crs)
    crops += _parse_custom_crops(args.crop, ortho_crs)
    if crops:
        print(f"  Crops: {', '.join(n for n, _, _ in crops)}")
        fig_crops(year, ortho_path, mask_path, crops, args.crop_size_m, out_dir, show)
    else:
        print("  (no crop centres — pass --crop name:x,y or place photos/*_rgb.tif)")

    print("  ✓ done")


if __name__ == "__main__":
    main()