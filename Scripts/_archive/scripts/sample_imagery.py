"""
sample_imagery.py — Multi-year imagery sampler
===============================================
Pulls a patch from the same geographic location across all pipeline
years and renders a tiled comparison PNG. Useful for verifying
upsampling quality, co-registration alignment, and color consistency
before running DDT inference.

Reads from the REGISTERED directory by default so you are inspecting
the actual data that DDT inference will see. Falls back to upsampled
then raw if a registered file is not yet available for a year.

USAGE (Colab cell — avoids argparse/kernel conflict):
----------------------------------------------------
    import sys, importlib
    sys.path.insert(0, "/content/drive/MyDrive/treedata/Scripts")
    if "sample_imagery" in sys.modules: del sys.modules["sample_imagery"]
    import sample_imagery

    # Auto patch centre (uses image centre — fast, no memory spike)
    sample_imagery.run()

    # Specific location
    sample_imagery.run(cx=74368, cy=105984, patch=400)

    # Compare raw original files instead of registered outputs
    sample_imagery.run(cx=74368, cy=105984, patch=400, raw=True)

PARAMETERS:
-----------
    cx, cy  : Patch centre in reference (2020) pixel coordinates.
              Default: image centre. Use QGIS to find pixel coords of
              a location you want to inspect.

    patch   : Half-width of the patch in reference pixels.
              patch=300  =>  600x600 px crop  =>  ~45m x 45m at 7.62cm/px
              patch=600  =>  1200x1200 px crop => ~90m x 90m
              patch=1000 =>  2000x2000 px crop => ~150m x 150m
              All patches are resampled to 400x400 in the output grid
              regardless of patch size.

    raw     : If True, reads original source files from
              /Full_Image/Pipeline Imagery/ instead of registered outputs.
"""

from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

# ── Config ────────────────────────────────────────────────────
DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")
from pipeline_config import (
    DRIVE_BASE, IMAGERY_DIR, REGISTERED_DIR, UPSAMPLE_DIR,
    raw_path, registered_path, upsampled_path, REFERENCE_YEAR,
)

REFERENCE_YEAR = 2020

ALL_YEARS = [2013, 2015, 2017, 2019, 2020, 2021, 2022, 2023, 2024]

SOURCE = {
    2013: "King Co.",  2015: "King Co.",  2017: "Edmonds",
    2019: "King Co.",  2020: "Edmonds",   2021: "King Co.",
    2022: "Edmonds",   2023: "King Co.",  2024: "Edmonds",
}

PANEL_W = 400
PANEL_H = 400
HEADER  = 44
PADDING = 4
COLS    = 3

HDR_COLORS = {
    "Edmonds":  (16, 38, 24),
    "King Co.": (22, 30, 50),
}
BADGE_COLORS = {
    "registered":               (30, 120, 70),
    "base (raw)":               (50, 80, 130),
    "upsampled":                (100, 70, 20),
    "raw":                      (70, 40, 10),
    "raw — not yet registered": (130, 50, 20),
    "missing":                  (100, 20, 20),
}


# ── Path resolution ───────────────────────────────────────────

def best_path(year, use_raw):
    registered = registered_path(year)
    upsampled  = upsampled_path(year)
    raw        = raw_path(year)

    if use_raw:
        return (raw, "raw") if raw.exists() else (None, "missing")
    if year == REFERENCE_YEAR:
        return (raw, "base (raw)") if raw.exists() else (None, "missing")
    if registered.exists():
        return registered, "registered"
    if upsampled.exists():
        return upsampled, "upsampled"
    if raw.exists():
        return raw, "raw — not yet registered"
    return None, "missing"


# ── Patch loading ─────────────────────────────────────────────

def load_patch(path, cx, cy, half, ref_res):
    import rasterio
    import rasterio.windows

    try:
        with rasterio.open(path) as src:
            tgt_res  = abs(src.transform.a)
            scale    = ref_res / tgt_res
            tgt_cx   = int(cx * scale)
            tgt_cy   = int(cy * scale)
            tgt_half = max(1, int(half * scale))
            col_off  = max(0, min(tgt_cx - tgt_half, src.width  - 2 * tgt_half))
            row_off  = max(0, min(tgt_cy - tgt_half, src.height - 2 * tgt_half))
            win      = rasterio.windows.Window(col_off, row_off,
                                               2 * tgt_half, 2 * tgt_half)
            data     = src.read(window=win)

        rgb = np.stack([data[0], data[1], data[2]], axis=-1).astype(np.float32) \
              if data.shape[0] >= 3 \
              else np.stack([data[0]] * 3, axis=-1).astype(np.float32)

        lo, hi = np.percentile(rgb, (1, 99))
        rgb    = np.clip((rgb - lo) / (hi - lo) * 255.0, 0, 255) if hi > lo \
                 else np.zeros_like(rgb)

        return np.array(Image.fromarray(rgb.astype(np.uint8)).resize(
            (PANEL_W, PANEL_H), Image.LANCZOS))

    except Exception as e:
        print(f"    Could not load {path.name}: {e}")
        return None


# ── Panel rendering ───────────────────────────────────────────

def make_panel(year, img_arr, status):
    canvas = Image.new("RGB", (PANEL_W, PANEL_H + HEADER), (18, 18, 22))
    draw   = ImageDraw.Draw(canvas)
    src    = SOURCE.get(year, "")

    draw.rectangle([0, 0, PANEL_W, HEADER],
                   fill=HDR_COLORS.get(src, (28, 28, 32)))
    draw.text((10, 7),  str(year), fill=(255, 255, 255))
    draw.text((10, 23), src,       fill=(160, 160, 160))

    b_col = BADGE_COLORS.get(status, (60, 60, 60))
    bw    = len(status) * 7 + 14
    draw.rectangle([PANEL_W - bw - 6, 7, PANEL_W - 6, HEADER - 7], fill=b_col)
    draw.text((PANEL_W - bw, 11), status, fill=(255, 255, 255))

    if img_arr is not None:
        canvas.paste(Image.fromarray(img_arr), (0, HEADER))
    else:
        draw.rectangle([0, HEADER, PANEL_W, PANEL_H + HEADER], fill=(30, 20, 20))
        draw.text((PANEL_W // 2 - 30, HEADER + PANEL_H // 2 - 8),
                  "NOT FOUND", fill=(180, 60, 60))

    return canvas


# ── Grid assembly ─────────────────────────────────────────────

def assemble_grid(panels):
    import math
    rows    = math.ceil(len(panels) / COLS)
    total_w = COLS * PANEL_W + (COLS - 1) * PADDING
    total_h = rows * (PANEL_H + HEADER) + (rows - 1) * PADDING
    grid    = Image.new("RGB", (total_w, total_h), (10, 10, 12))
    for i, panel in enumerate(panels):
        grid.paste(panel, (i % COLS * (PANEL_W + PADDING),
                           i // COLS * (PANEL_H + HEADER + PADDING)))
    return grid


# ── Public entry point ────────────────────────────────────────

def run(cx=None, cy=None, patch=400, raw=False):
    """
    Generate the multi-year imagery sample grid.

    Parameters
    ----------
    cx, cy : int, optional
        Patch centre in reference (2020) pixel coordinates.
        Defaults to image centre if not provided.
    patch : int
        Half-width of patch in reference pixels (default 400).
    raw : bool
        Read original source files instead of registered outputs.
    """
    import rasterio

    print("=" * 60)
    print("  IMAGERY SAMPLE — Multi-year visual QC")
    print("=" * 60)

    ref_path = raw_path(REFERENCE_YEAR)
    if not ref_path.exists():
        print(f"  Reference not found: {ref_path}")
        return

    with rasterio.open(ref_path) as src:
        ref_res = abs(src.transform.a)
        ref_w, ref_h = src.width, src.height

    if cx is None: cx = ref_w  // 2
    if cy is None: cy = ref_h  // 2

    ground_m = patch * ref_res * 2
    print(f"  Reference : {REFERENCE_YEAR}  res={ref_res:.4f} m  "
          f"dims={ref_w}x{ref_h}")
    print(f"  Patch     : centre=({cx}, {cy})  half={patch} px  "
          f"~{ground_m:.0f}m x {ground_m:.0f}m on ground")
    print(f"  Mode      : {'raw source files' if raw else 'registered outputs'}")
    print()

    panels = []
    for year in ALL_YEARS:
        path, status = best_path(year, raw)
        print(f"  {year}  [{SOURCE.get(year,''):9s}]  {status}")
        img = load_patch(path, cx, cy, patch, ref_res) \
              if path is not None else None
        panels.append(make_panel(year, img, status))

    print()
    grid     = assemble_grid(panels)
    mode     = "raw" if raw else "registered"
    out_path = REGISTERED_DIR / f"imagery_sample_{cx}_{cy}_{mode}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    grid.save(out_path, dpi=(150, 150))

    size_kb = out_path.stat().st_size // 1024
    print(f"  Saved : {out_path.name}  "
          f"({size_kb:,} KB  {grid.size[0]}x{grid.size[1]} px)")

    try:
        from IPython.display import Image as IPImage, display
        display(IPImage(str(out_path)))
    except Exception:
        pass


# ── Allow %run as fallback ────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.argv = sys.argv[:1]   # strip Colab kernel launcher args
    run()