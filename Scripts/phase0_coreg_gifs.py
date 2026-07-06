"""
make_coreg_gif.py — Co-registration QC visualizer (side-by-side)
=================================================================
Produces a side-by-side flicker GIF comparing unregistered (left)
and registered (right) imagery against the 2020 reference, with
building edge overlays to make alignment quality immediately obvious.

Usage (Colab):
    %run make_coreg_gif.py --year 2017 --patch 400

Arguments:
    --year      Target year to compare against reference (required)
    --cx        Patch center X in full-image pixel coords (default: auto)
    --cy        Patch center Y in full-image pixel coords (default: auto)
    --patch     Patch half-width in pixels (default: 400)
    --fps       GIF frames per second (default: 2)
    --output    Output GIF path (default: /registered/coreg_before_after_{year}.gif)

Modes:
    Auto mode (no --cx/--cy): Picks the tile with the highest building
    density — usually the most informative patch for alignment QC.

    Manual mode (--cx and --cy): Centers the patch on a known landmark
    or problem area you want to inspect.

GIF layout (1 row, 2 columns):
    LEFT  — BEFORE: reference flickering against the UNREGISTERED target
    RIGHT — AFTER:  reference flickering against the REGISTERED target

    Both sides show the same building edges (from reference) overlaid
    in cyan. Residual offset between edges and building boundaries
    immediately communicates alignment quality.

Frame sequence (loops):
    1. Reference / Reference        (both panels — shared anchor)
    2. Unregistered / Registered    (the money shot)
    3. Reference / Reference
    4. Unregistered / Registered
    5. Diff x4 BEFORE / Diff x4 AFTER (held 1.2 s — bright vs dark)

COLAB SETUP
-----------
    from google.colab import drive
    drive.mount('/content/drive')
    !pip install rasterio geopandas numpy Pillow scikit-image -q

Then:
    %run make_coreg_gif.py --year 2017

    # Inspect inline:
    from IPython.display import Image as IPImage
    IPImage('/content/drive/MyDrive/treedata/registered/coreg_before_after_2017.gif')

    # Target a specific area you know well:
    %run make_coreg_gif.py --year 2017 --cx 28000 --cy 45000 --patch 600
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

# ── Config (mirrors coregister_imagery.py) ───────────────────
DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")
from pipeline_config import (
    DRIVE_BASE, IMAGERY_DIR, REGISTERED_DIR, BUILDINGS_JSON,
    IMAGERY_CATALOG, raw_path, registered_path, REFERENCE_YEAR,
)
OUTPUT_DIR = REGISTERED_DIR
REFERENCE_YEAR = 2020

HEADER  = 38    # px — label bar height above each panel
FOOTER  = 22    # px — section label bar height below panels
DIVIDER = 6     # px — gap between left and right panels


# ── Patch loading ────────────────────────────────────────────

def load_patch(tif_path, cx, cy, half):
    """
    Read a square RGB patch from a GeoTIFF.
    Returns (rgb_array [H,W,3 uint8], window, window_transform).
    Clamps to image bounds automatically.
    """
    import rasterio
    import rasterio.windows

    with rasterio.open(tif_path) as src:
        col_off = max(0, min(cx - half, src.width  - 2 * half))
        row_off = max(0, min(cy - half, src.height - 2 * half))
        win     = rasterio.windows.Window(col_off, row_off, 2 * half, 2 * half)
        data    = src.read(window=win)
        t       = src.window_transform(win)

    if data.shape[0] >= 3:
        rgb = np.stack([data[0], data[1], data[2]], axis=-1)
    else:
        rgb = np.stack([data[0]] * 3, axis=-1)

    return rgb.astype(np.uint8), win, t


# ── Building edge overlay ─────────────────────────────────────

def burn_edges(transform, shape, buildings_gdf, color=(0, 235, 205)):
    """
    Rasterize building footprint edges into an RGBA overlay.
    Returns (H, W, 4) uint8 — transparent background, cyan edges.
    Uses the reference-year transform so both panels see identical edges.
    """
    import rasterio.features
    from skimage.filters import gaussian
    from skimage.feature import canny

    h, w   = shape
    shapes = [(g.__geo_interface__, 1)
              for g in buildings_gdf.geometry
              if g is not None and not g.is_empty]

    if not shapes:
        return np.zeros((h, w, 4), dtype=np.uint8)

    mask    = rasterio.features.rasterize(
        shapes, out_shape=(h, w), transform=transform,
        fill=0, dtype=np.uint8,
    )
    from skimage.filters import gaussian
    from skimage.feature import canny
    blurred = gaussian(mask.astype(float), sigma=1.0)
    edges   = canny(blurred, sigma=0.5).astype(np.uint8)

    overlay = np.zeros((h, w, 4), dtype=np.uint8)
    overlay[edges > 0] = (*color, 230)
    return overlay


def composite(rgb, overlay):
    """Alpha-blend RGBA overlay onto RGB base."""
    out   = rgb.copy().astype(np.float32)
    alpha = overlay[:, :, 3:4] / 255.0
    color = overlay[:, :, :3].astype(np.float32)
    return np.clip(out * (1 - alpha) + color * alpha, 0, 255).astype(np.uint8)


def diff_frame(ref, tgt, scale=4):
    """Amplified absolute difference — bright pixels = misalignment."""
    d = np.abs(ref.astype(np.int16) - tgt.astype(np.int16))
    return np.clip(d * scale, 0, 255).astype(np.uint8)


# ── Auto patch selection ──────────────────────────────────────

def find_best_patch(ref_path, buildings_gdf, tile_size=2048, half=400):
    """
    Scan the reference image in coarse tiles.
    Returns (cx, cy) of the tile with the highest building pixel count.
    This is almost always the most informative area for alignment QC.
    """
    import rasterio
    import rasterio.windows
    import rasterio.features

    print("  Auto-selecting patch — scanning building density...")
    best_cx, best_cy, best_count = 0, 0, 0

    with rasterio.open(ref_path) as src:
        W, H = src.width, src.height
        for row_off in range(0, H, tile_size):
            for col_off in range(0, W, tile_size):
                tw  = min(tile_size, W - col_off)
                th  = min(tile_size, H - row_off)
                win = rasterio.windows.Window(col_off, row_off, tw, th)
                t   = src.window_transform(win)
                shapes = [(g.__geo_interface__, 1)
                          for g in buildings_gdf.geometry
                          if g is not None and not g.is_empty]
                if not shapes:
                    continue
                mask  = rasterio.features.rasterize(
                    shapes, out_shape=(th, tw), transform=t,
                    fill=0, dtype=np.uint8,
                )
                count = int(mask.sum())
                if count > best_count:
                    best_count = count
                    best_cx    = col_off + tw // 2
                    best_cy    = row_off + th // 2

    print(f"  Best patch centre: ({best_cx}, {best_cy})  "
          f"building coverage: {best_count:,} px")
    return best_cx, best_cy


# ── Frame compositor ──────────────────────────────────────────

def build_frame(left_img, right_img,
                left_label, left_sub, left_badge, left_badge_col,
                right_label, right_sub, right_badge, right_badge_col,
                left_hdr_bg, right_hdr_bg,
                pw, ph):
    """
    Compose one full GIF frame:
      [ HEADER  left panel  ] [ DIVIDER ] [ HEADER  right panel ]
      [ -------- FOOTER --------------------------------- ]
    """
    total_w = pw * 2 + DIVIDER
    total_h = ph + HEADER + FOOTER

    canvas = Image.new("RGB", (total_w, total_h), (18, 18, 22))
    draw   = ImageDraw.Draw(canvas)

    # Left panel
    canvas.paste(Image.fromarray(left_img), (0, HEADER))
    draw.rectangle([0, 0, pw, HEADER], fill=left_hdr_bg)
    draw.text((10, 8),  left_label, fill=(255, 255, 255))
    draw.text((10, 22), left_sub,   fill=(175, 175, 175))
    if left_badge:
        bw = len(left_badge) * 7 + 16
        draw.rectangle([pw - bw - 6, 7, pw - 6, HEADER - 7], fill=left_badge_col)
        draw.text((pw - bw, 11), left_badge, fill=(255, 255, 255))

    # Divider
    draw.rectangle([pw, 0, pw + DIVIDER, total_h], fill=(28, 28, 32))

    # Right panel
    rx = pw + DIVIDER
    canvas.paste(Image.fromarray(right_img), (rx, HEADER))
    draw.rectangle([rx, 0, rx + pw, HEADER], fill=right_hdr_bg)
    draw.text((rx + 10, 8),  right_label, fill=(255, 255, 255))
    draw.text((rx + 10, 22), right_sub,   fill=(175, 175, 175))
    if right_badge:
        bw = len(right_badge) * 7 + 16
        draw.rectangle([rx + pw - bw - 6, 7, rx + pw - 6, HEADER - 7], fill=right_badge_col)
        draw.text((rx + pw - bw, 11), right_badge, fill=(255, 255, 255))

    # Footer
    fy = HEADER + ph
    draw.rectangle([0, fy, total_w, total_h], fill=(18, 18, 22))
    draw.text((10,      fy + 5), "BEFORE  co-registration", fill=(210, 110, 70))
    draw.text((rx + 10, fy + 5), "AFTER   co-registration", fill=(80, 200, 120))

    return canvas


# ── Main GIF builder ──────────────────────────────────────────

def make_gif(ref_path, unregistered_path, registered_path,
             buildings_gdf, cx, cy, half, fps, out_path):

    print(f"\n  Loading patches  (centre={cx},{cy}  half={half}px)...")

    ref_rgb, ref_win, ref_t = load_patch(ref_path,          cx, cy, half)
    unr_rgb, _,       _     = load_patch(unregistered_path, cx, cy, half)
    reg_rgb, _,       _     = load_patch(registered_path,   cx, cy, half)

    ph, pw = ref_rgb.shape[:2]
    print(f"  Patch size: {pw}x{ph} px")

    # Clip buildings to patch footprint
    import rasterio
    import rasterio.windows
    import geopandas as gpd
    from shapely.geometry import box

    with rasterio.open(ref_path) as src:
        ref_bounds = rasterio.windows.bounds(ref_win, src.transform)
    patch_box  = box(*ref_bounds)
    bldgs_clip = buildings_gdf[buildings_gdf.intersects(patch_box)].copy()
    print(f"  Buildings in patch: {len(bldgs_clip)}")

    if len(bldgs_clip) == 0:
        print("  Warning: no buildings in patch — edges will be empty. "
              "Try different --cx/--cy or larger --patch.")

    print("  Burning building edges (reference transform)...")
    edges = burn_edges(ref_t, (ph, pw), bldgs_clip)

    ref_comp = composite(ref_rgb, edges)
    unr_comp = composite(unr_rgb, edges)
    reg_comp = composite(reg_rgb, edges)
    diff_unr = diff_frame(ref_rgb, unr_rgb)
    diff_reg = diff_frame(ref_rgb, reg_rgb)

    BHB = (42, 22, 16)   # before header bg (warm dark)
    AHB = (16, 38, 24)   # after header bg  (cool dark)

    unr_stem = unregistered_path.stem
    reg_stem = registered_path.stem

    frame_spec = [
        # left_img, right_img, ll, ls, lb, lbc, rl, rs, rb, rbc, lhb, rhb, ms
        (ref_comp, ref_comp,
         f"Reference ({REFERENCE_YEAR})", "building edges in cyan",   "REF",    (50, 80, 130),
         f"Reference ({REFERENCE_YEAR})", "building edges in cyan",   "REF",    (50, 80, 130),
         BHB, AHB, int(1000 / fps)),

        (unr_comp, reg_comp,
         unr_stem, "GPS drift visible",          "BEFORE", (165, 60, 30),
         reg_stem, "edges snap to buildings",    "AFTER",  (30, 120, 70),
         BHB, AHB, int(1000 / fps)),

        (ref_comp, ref_comp,
         f"Reference ({REFERENCE_YEAR})", "building edges in cyan",   "REF",    (50, 80, 130),
         f"Reference ({REFERENCE_YEAR})", "building edges in cyan",   "REF",    (50, 80, 130),
         BHB, AHB, int(800 / fps)),

        (unr_comp, reg_comp,
         unr_stem, "GPS drift visible",          "BEFORE", (165, 60, 30),
         reg_stem, "edges snap to buildings",    "AFTER",  (30, 120, 70),
         BHB, AHB, int(800 / fps)),

        (diff_unr, diff_reg,
         "Difference x4 — BEFORE", "bright = misalignment",   "DIFF", (140, 50, 20),
         "Difference x4 — AFTER",  "dark = tight alignment",  "DIFF", (20, 90, 55),
         BHB, AHB, 1200),
    ]

    print("  Compositing frames...")
    gif_frames    = []
    gif_durations = []

    for spec in frame_spec:
        (li, ri, ll, ls, lb, lbc, rl, rs, rb, rbc, lhb, rhb, ms) = spec
        frame = build_frame(li, ri, ll, ls, lb, lbc,
                            rl, rs, rb, rbc, lhb, rhb, pw, ph)
        gif_frames.append(frame)
        gif_durations.append(ms)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    gif_frames[0].save(
        out_path,
        save_all=True,
        append_images=gif_frames[1:],
        loop=0,
        duration=gif_durations,
        optimize=False,
    )

    size_kb = out_path.stat().st_size // 1024
    w, h    = gif_frames[0].size
    print(f"\n  GIF written: {out_path}")
    print(f"  Size: {size_kb:,} KB  |  {w}x{h} px  |  {len(gif_frames)} frames")
    print(f"\n  View inline in Colab:")
    print(f"    from IPython.display import Image as IPImage")
    print(f"    IPImage('{out_path}')")


# ── CLI ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Side-by-side co-registration QC GIF — BEFORE vs AFTER")
    parser.add_argument("--year",   type=int, required=True,
                        help="Target year (must have both raw and registered TIFs)")
    parser.add_argument("--cx",     type=int, default=None,
                        help="Patch centre X in full-image pixels (default: auto)")
    parser.add_argument("--cy",     type=int, default=None,
                        help="Patch centre Y in full-image pixels (default: auto)")
    parser.add_argument("--patch",  type=int, default=400,
                        help="Patch half-width in pixels (default: 400)")
    parser.add_argument("--fps",    type=int, default=2,
                        help="Flicker speed in frames per second (default: 2)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output path (default: /registered/coreg_before_after_{year}.gif)")
    args = parser.parse_args()

    ref_path          = raw_path(REFERENCE_YEAR)
    unregistered_path = raw_path(args.year)
    registered_path   = OUTPUT_DIR  / f"{args.year}_edmonds_registered.tif"
    out_path          = Path(args.output) if args.output else \
                        OUTPUT_DIR / f"coreg_before_after_{args.year}.gif"

    print("=" * 60)
    print(f"  Co-reg QC GIF — side-by-side BEFORE / AFTER")
    print(f"  Reference : {REFERENCE_YEAR}")
    print(f"  Target    : {args.year}")
    print("=" * 60)

    for label, p in [("Reference",          ref_path),
                     ("Unregistered source", unregistered_path),
                     ("Registered output",   registered_path)]:
        if not p.exists():
            print(f"  Not found — {label}: {p}")
            sys.exit(1)
        print(f"  Found — {label}: {p.name}")

    import geopandas as gpd
    import rasterio

    print("\n-- Loading building footprints --")
    if not BUILDINGS_JSON.exists():
        print(f"  Not found: {BUILDINGS_JSON}")
        sys.exit(1)

    gdf = gpd.read_file(BUILDINGS_JSON)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    with rasterio.open(ref_path) as src:
        ref_crs = src.crs
    if gdf.crs != ref_crs:
        print(f"  Reprojecting buildings {gdf.crs} -> {ref_crs}")
        gdf = gdf.to_crs(ref_crs)
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    gdf = gdf[gdf.geometry.is_valid]
    print(f"  {len(gdf):,} valid buildings loaded")

    cx, cy = args.cx, args.cy
    if cx is None or cy is None:
        cx, cy = find_best_patch(ref_path, gdf, half=args.patch)

    make_gif(ref_path, unregistered_path, registered_path,
             gdf, cx, cy, args.patch, args.fps, out_path)


if __name__ == "__main__":
    main()