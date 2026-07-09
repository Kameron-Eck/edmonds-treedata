#!/usr/bin/env python3
"""
Visualize all 4 bands from Edmonds 2020 aerial TIFF chunks.
Displays RGB composite + individual bands (R, G, B, Band4/NIR).

Usage:
  pip install rasterio matplotlib numpy
  python visualize_bands.py
  python visualize_bands.py --tile edmonds_2020_tiles/tile_r1_c0.tif
"""

import sys
import argparse
from pathlib import Path

try:
    import rasterio
except ImportError:
    sys.exit("ERROR: Install rasterio: pip install rasterio")

try:
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
except ImportError:
    sys.exit("ERROR: Install matplotlib: pip install matplotlib")

try:
    import numpy as np
except ImportError:
    sys.exit("ERROR: Install numpy: pip install numpy")


def visualize_tile(filepath: str):
    """Visualize all bands of a single GeoTIFF tile."""
    path = Path(filepath)
    if not path.exists():
        print(f"File not found: {path}")
        return

    with rasterio.open(path) as src:
        n_bands = src.count
        width = src.width
        height = src.height
        crs = src.crs
        transform = src.transform
        pixel_size_x = abs(transform[0])
        pixel_size_y = abs(transform[4])
        bounds = src.bounds
        dtypes = [src.dtypes[i] for i in range(n_bands)]

        print(f"{'=' * 60}")
        print(f"File:        {path.name}")
        print(f"Size:        {width} x {height} px")
        print(f"Bands:       {n_bands}")
        print(f"CRS:         {crs}")
        print(f"Pixel Size:  {pixel_size_x:.6f} x {pixel_size_y:.6f}")
        print(f"Bounds:      xmin={bounds.left:.2f}  ymin={bounds.bottom:.2f}")
        print(f"             xmax={bounds.right:.2f}  ymax={bounds.top:.2f}")
        print(f"Dtypes:      {dtypes}")

        # Read all bands
        bands = []
        for i in range(1, n_bands + 1):
            band = src.read(i)
            bmin, bmax = band.min(), band.max()
            bmean = band.mean()
            bstd = band.std()
            print(f"Band {i}:      min={bmin}  max={bmax}  mean={bmean:.1f}  std={bstd:.1f}")
            bands.append(band)

        print(f"{'=' * 60}")

    # --- Determine band roles ---
    band_labels = []
    if n_bands >= 3:
        band_labels = ["Red", "Green", "Blue"]
    if n_bands == 4:
        # Check if band 4 is NIR or Alpha based on stats
        b4 = bands[3]
        unique_vals = np.unique(b4)
        if len(unique_vals) <= 2 and set(unique_vals).issubset({0, 255}):
            band_labels.append("Alpha (mask)")
            is_alpha = True
        else:
            band_labels.append("NIR / Band 4")
            is_alpha = False
    elif n_bands > 4:
        band_labels.extend([f"Band {i+1}" for i in range(3, n_bands)])
        is_alpha = False

    # --- Build figure ---
    if n_bands == 4:
        fig = plt.figure(figsize=(20, 16))
        gs = gridspec.GridSpec(3, 2, height_ratios=[1.2, 1, 1], hspace=0.3, wspace=0.2)

        # Row 1: RGB composite + Band 4
        ax_rgb = fig.add_subplot(gs[0, 0])
        ax_b4 = fig.add_subplot(gs[0, 1])

        # Row 2: Red + Green
        ax_r = fig.add_subplot(gs[1, 0])
        ax_g = fig.add_subplot(gs[1, 1])

        # Row 3: Blue + NDVI or histogram
        ax_b = fig.add_subplot(gs[2, 0])
        ax_extra = fig.add_subplot(gs[2, 1])

        # RGB composite
        rgb = np.stack(bands[:3], axis=-1)
        ax_rgb.imshow(rgb)
        ax_rgb.set_title("RGB Composite", fontsize=14, fontweight="bold")
        ax_rgb.axis("off")

        # Band 4
        cmap_b4 = "gray" if is_alpha else "RdYlGn"
        im4 = ax_b4.imshow(bands[3], cmap=cmap_b4)
        ax_b4.set_title(f"Band 4: {band_labels[3]}", fontsize=14, fontweight="bold")
        ax_b4.axis("off")
        plt.colorbar(im4, ax=ax_b4, fraction=0.046, pad=0.04)

        # Individual RGB bands
        for ax, band, label, cmap in [
            (ax_r, bands[0], "Band 1: Red", "Reds"),
            (ax_g, bands[1], "Band 2: Green", "Greens"),
            (ax_b, bands[2], "Band 3: Blue", "Blues"),
        ]:
            im = ax.imshow(band, cmap=cmap)
            ax.set_title(label, fontsize=13)
            ax.axis("off")
            plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

        # Extra panel: NDVI if Band 4 is NIR, histogram if Alpha
        if not is_alpha:
            nir = bands[3].astype(np.float32)
            red = bands[0].astype(np.float32)
            denom = nir + red
            ndvi = np.where(denom > 0, (nir - red) / denom, 0)
            im_ndvi = ax_extra.imshow(ndvi, cmap="RdYlGn", vmin=-0.2, vmax=0.8)
            ax_extra.set_title("NDVI (if Band 4 = NIR)", fontsize=13, fontweight="bold")
            ax_extra.axis("off")
            plt.colorbar(im_ndvi, ax=ax_extra, fraction=0.046, pad=0.04)
        else:
            # Histogram of all bands
            colors = ["red", "green", "blue", "gray"]
            for i, (band, color, label) in enumerate(zip(bands, colors, band_labels)):
                ax_extra.hist(
                    band.ravel(), bins=256, range=(0, 255),
                    alpha=0.5, color=color, label=label,
                )
            ax_extra.set_title("Band Histograms", fontsize=13)
            ax_extra.set_xlabel("Pixel Value")
            ax_extra.set_ylabel("Count")
            ax_extra.legend(fontsize=9)

    elif n_bands == 3:
        fig, axes = plt.subplots(2, 2, figsize=(16, 14))

        rgb = np.stack(bands[:3], axis=-1)
        axes[0, 0].imshow(rgb)
        axes[0, 0].set_title("RGB Composite", fontsize=14, fontweight="bold")
        axes[0, 0].axis("off")

        for ax, band, label, cmap in [
            (axes[0, 1], bands[0], "Band 1: Red", "Reds"),
            (axes[1, 0], bands[1], "Band 2: Green", "Greens"),
            (axes[1, 1], bands[2], "Band 3: Blue", "Blues"),
        ]:
            im = ax.imshow(band, cmap=cmap)
            ax.set_title(label, fontsize=13)
            ax.axis("off")
            plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    else:
        fig, ax = plt.subplots(1, 1, figsize=(10, 10))
        ax.imshow(bands[0], cmap="gray")
        ax.set_title(f"Single Band ({n_bands} total)", fontsize=14)
        ax.axis("off")

    fig.suptitle(
        f"{path.name}  |  {width}×{height} px  |  {n_bands} bands  |  {crs}",
        fontsize=11, y=0.98, color="gray",
    )

    out_path = path.with_suffix(".png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"\nSaved visualization: {out_path}")
    plt.show()


def main():
    parser = argparse.ArgumentParser(
        description="Visualize bands from Edmonds 2020 aerial TIFF tiles."
    )
    parser.add_argument(
        "--tile", type=str, default=None,
        help="Path to a specific tile. If not set, visualizes the first valid tile found.",
    )
    parser.add_argument(
        "--dir", type=str, default="edmonds_2020_tiles",
        help="Directory containing tiles (default: edmonds_2020_tiles)",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Visualize ALL tiles in the directory",
    )

    args = parser.parse_args()

    if args.tile:
        visualize_tile(args.tile)
    elif args.all:
        tile_dir = Path(args.dir)
        tiles = sorted(tile_dir.glob("tile_r*_c*.tif"))
        if not tiles:
            print(f"No tiles found in {tile_dir}")
            return
        print(f"Found {len(tiles)} tiles. Visualizing all...\n")
        for t in tiles:
            visualize_tile(str(t))
    else:
        tile_dir = Path(args.dir)
        tiles = sorted(tile_dir.glob("tile_r*_c*.tif"))
        if not tiles:
            print(f"No tiles found in {tile_dir}")
            return
        # Pick the first tile that's large enough to be real data
        for t in tiles:
            if t.stat().st_size > 5000:
                visualize_tile(str(t))
                return
        print("No valid tiles found (all too small)")


if __name__ == "__main__":
    main()
