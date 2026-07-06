"""
color_burn_composite.py — Multi-year overlap color burn composite
"""
from pathlib import Path
import numpy as np

DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")
REGISTERED_DIR = DRIVE_BASE / "Full_Image/Pipeline Imagery/registered"
HICKMAN_PIXEL_COL = 45467
HICKMAN_PIXEL_ROW = 176989
CLIP_SIZE_PX      = 10000


def _apply_ramp(mean_brightness, overlap_frac):
    h, w        = mean_brightness.shape
    rgba        = np.zeros((h, w, 4), dtype=np.uint8)
    bright_norm = np.clip(mean_brightness / 255.0, 0.0, 1.0)
    color_stops = np.array([
        [0.00,  10,   4,   2],
        [0.15,  55,  10,   5],
        [0.30, 110,  25,  10],
        [0.45, 160,  55,  15],
        [0.60, 195,  95,  30],
        [0.75, 215, 145,  55],
        [0.88, 230, 190,  95],
        [1.00, 245, 230, 160],
    ], dtype=np.float32)
    for i in range(len(color_stops) - 1):
        b0, b1 = color_stops[i, 0], color_stops[i + 1, 0]
        mask   = (bright_norm >= b0) & (bright_norm < b1)
        if not mask.any():
            continue
        t = (bright_norm[mask] - b0) / (b1 - b0)
        for c in range(3):
            rgba[mask, c] = np.clip(
                color_stops[i, c+1] + t * (color_stops[i+1, c+1] - color_stops[i, c+1]),
                0, 255).astype(np.uint8)
    top = bright_norm >= color_stops[-1, 0]
    if top.any():
        rgba[top, :3] = color_stops[-1, 1:].astype(np.uint8)
    alpha_stops = np.array([
        [0.00,   0], [0.11,  80], [0.33, 160],
        [0.56, 210], [0.78, 240], [1.00, 255],
    ], dtype=np.float32)
    alpha = np.zeros((h, w), dtype=np.float32)
    for i in range(len(alpha_stops) - 1):
        a0, a1 = alpha_stops[i, 0], alpha_stops[i + 1, 0]
        mask   = (overlap_frac >= a0) & (overlap_frac < a1)
        if not mask.any():
            continue
        t = (overlap_frac[mask] - a0) / (a1 - a0)
        alpha[mask] = alpha_stops[i, 1] + t * (alpha_stops[i+1, 1] - alpha_stops[i, 1])
    alpha[overlap_frac >= 1.0] = 255.0
    rgba[:, :, 3] = np.clip(alpha, 0, 255).astype(np.uint8)
    return rgba


def run(registered_dir=None, out_path=None,
        centre_col=HICKMAN_PIXEL_COL, centre_row=HICKMAN_PIXEL_ROW,
        clip_size=CLIP_SIZE_PX):
    import rasterio, rasterio.windows
    reg_dir = Path(registered_dir) if registered_dir else REGISTERED_DIR
    out_tif = Path(out_path) if out_path else reg_dir / "hickman_overlap_composite.tif"
    out_png = out_tif.with_suffix(".png")
    print("=" * 60)
    print("  COLOR BURN OVERLAP COMPOSITE — Hickman Park")
    print("=" * 60)
    files = sorted([f for f in reg_dir.glob("*_registered.tif")
                    if "_ir_registered" not in f.name
                    and "overlap_composite" not in f.name])
    if not files:
        print(f"  No files found in: {reg_dir}"); return
    print(f"\n  {len(files)} files:")
    for f in files:
        print(f"    {f.name}  ({f.stat().st_size/1e9:.1f} GB)")
    with rasterio.open(files[0]) as ref:
        ref_transform = ref.transform
        ref_crs = ref.crs
        ref_w, ref_h = ref.width, ref.height
    half    = clip_size // 2
    col_off = max(0, centre_col - half)
    row_off = max(0, centre_row - half)
    col_end = min(ref_w, col_off + clip_size)
    row_end = min(ref_h, row_off + clip_size)
    actual_w = col_end - col_off
    actual_h = row_end - row_off
    window   = rasterio.windows.Window(col_off, row_off, actual_w, actual_h)
    print(f"\n  Clip: col {col_off}-{col_end}, row {row_off}-{row_end}  "
          f"({actual_w}x{actual_h} px)")
    n_years = len(files)
    stack   = np.zeros((n_years, actual_h, actual_w), dtype=np.float32)
    print(f"\n  Reading clips...")
    for yi, fpath in enumerate(files):
        try:
            with rasterio.open(fpath) as src:
                src_win = rasterio.windows.Window(
                    col_off, row_off,
                    min(actual_w, src.width - col_off),
                    min(actual_h, src.height - row_off))
                if src_win.width <= 0 or src_win.height <= 0:
                    print(f"    {fpath.name}: outside bounds"); continue
                # Read all RGB bands and compute perceptual luminance.
                # Weights: R=0.299 G=0.587 B=0.114 (ITU-R BT.601).
                # RGBI files have 4 bands — NIR (band 4) excluded here.
                n_rgb  = min(src.count, 3)
                bands  = src.read(list(range(1, n_rgb + 1)), window=src_win)
                w8     = np.array([0.299, 0.587, 0.114][:n_rgb], dtype=np.float32)
                w8    /= w8.sum()
                lum    = (bands.astype(np.float32) * w8[:, None, None]).sum(axis=0)
                h, w   = lum.shape
                stack[yi, :h, :w] = lum
                print(f"    {fpath.name}  bands={n_rgb}  "
                      f"lum_max={lum.max():.0f}  non-zero={int((lum>0).sum()):,}")
        except Exception as e:
            print(f"    {fpath.name}: {e}")
    has_data      = (stack > 0)
    overlap_count = has_data.sum(axis=0).astype(np.float32)
    overlap_frac  = np.where(overlap_count > 0, overlap_count / n_years, 0.0)
    mean_bright   = np.where(overlap_count > 0,
                             stack.sum(axis=0) / np.maximum(overlap_count, 1), 0.0)
    valid = mean_bright[overlap_count > 0]
    print(f"\n  Brightness: min={valid.min():.1f} max={valid.max():.1f} "
          f"mean={valid.mean():.1f} p5={np.percentile(valid,5):.1f} "
          f"p95={np.percentile(valid,95):.1f}")
    print(f"  Applying ramp...")
    rgba = _apply_ramp(mean_bright, overlap_frac)
    clip_transform = rasterio.windows.transform(window, ref_transform)
    profile = {"driver":"GTiff","dtype":"uint8","width":actual_w,"height":actual_h,
               "count":4,"crs":ref_crs,"transform":clip_transform,
               "compress":"lzw","predictor":2,"tiled":True,
               "blockxsize":256,"blockysize":256}
    out_tif.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_tif, "w", **profile) as dst:
        for band_i, channel in enumerate([0,1,2,3], start=1):
            dst.write(rgba[:,:,channel], band_i)
    print(f"  GeoTIFF: {out_tif.name}  ({out_tif.stat().st_size/1e6:.0f} MB)")
    from PIL import Image
    img = Image.fromarray(rgba, mode="RGBA")
    img.save(out_png, dpi=(150,150))
    print(f"  PNG    : {out_png.name}  ({out_png.stat().st_size/1e6:.1f} MB)")
    try:
        from IPython.display import Image as IPImage, display
        display(IPImage(str(out_png)))
    except Exception:
        pass
    print(f"\n  Done.")
    return out_tif, out_png


if __name__ == "__main__":
    import sys; sys.argv = sys.argv[:1]; run()