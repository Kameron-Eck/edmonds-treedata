"""
Temporal Polygon Overlay — Training Sites × Multi-Year Imagery
══════════════════════════════════════════════════════════════════
Overlays phase 0 hand-drawn crown polygons onto every available
year of imagery from the phase 1 upsample folder.

Produces one full-resolution PNG per training site, saved to Drive.
Each PNG is a 4×4 grid (13 years + 3 empty cells).
Polygons are anchored to 2020 — so you can visually check:
  • Trees present in 2020 but missing in earlier years (new growth)
  • Trees removed between years
  • Crown expansion / contraction over time
  • Alignment quality across different imagery sources

OUTPUT
──────
  treedata/temporal_overlays/<SiteName>_temporal.png

USAGE
─────
  %run temporal_overlay.py                     # all sites
  %run temporal_overlay.py --site Forest_1     # single site
"""

import argparse
import math
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
import rasterio.windows

warnings.filterwarnings("ignore")

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE         = Path("/content/drive/MyDrive/treedata")
PHOTOS_DIR   = BASE / "photos"
POLYGONS_DIR = BASE / "polygons"
UPSAMPLE_DIR = BASE / "Full_Image/Pipeline Imagery"
OUT_DIR      = BASE / "temporal_overlays"
TARGET_CRS   = "EPSG:3857"

GRID_COLS = 4

YEAR_CATALOG = [
    {"key": 2000,    "file": "2000_king_rgb.tif",   "label": "2000"},
    {"key": 2002,    "file": "2002_king_rgbi.tif",  "label": "2002"},
    {"key": 2005,    "file": "2005_king_rgb.tif",              "label": "2005"},
    {"key": 2007,    "file": "2007_king_rgb.tif",   "label": "2007"},
    {"key": "2009", "file": "2009_king_rgb.tif",  "label": "2009"},
    
    {"key": 2013,    "file": "2013_king_rgb.tif",   "label": "2013"},
    {"key": 2015,    "file": "2015_king_rgb.tif",   "label": "2015"},
    {"key": 2016,    "file": "2016_snoh_rgbi.tif",  "label": "2016"},
    {"key": 2017,    "file": "2017_coe_rgb.tif",              "label": "2017"},
    {"key": 2019,    "file": "2019_king_rgb.tif",   "label": "2019"},
    {"key": "2019n", "file": "2019_naip_rgbi.tif",  "label": "2019n"},
    {"key": 2020,    "file": "2020_coe_rgb.tif",    "label": "2020"},
    {"key": 2021,    "file": "2021_king_rgb",       "label": "2021"},
    {"key": "2021s", "file": "2021_snoh_rgbi",  "label": "2021s"},
    {"key": 2022,    "file": "2022_coe_rgb.tif","label": "2022"},
    {"key": "2022n", "file": "2022_naip_rgbi",  "label": "2022n"},
    {"key": 2023,    "file": "2023_king_rgb",   "label": "2023"},
    {"key": 2024,    "file": "2024_coe_rgb.tif","label": "2024"},
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def stretch_rgb(r, g, b, pct=(2, 98)):
    def clip(band):
        lo, hi = np.nanpercentile(band, pct)
        return np.clip((band - lo) / (hi - lo + 1e-8), 0, 1)
    return np.dstack([clip(r), clip(g), clip(b)])


def read_extent_fullres(src, bounds):
    """Read the region of src that overlaps bounds at native resolution."""
    win = rasterio.windows.from_bounds(
        bounds.left, bounds.bottom, bounds.right, bounds.top,
        transform=src.transform)

    win = win.intersection(rasterio.windows.Window(
        0, 0, src.width, src.height))

    if win.width < 1 or win.height < 1:
        return None, None

    out_h = int(round(win.height))
    out_w = int(round(win.width))

    r = src.read(1, window=win, out_shape=(out_h, out_w)).astype(np.float32)
    g = src.read(2, window=win, out_shape=(out_h, out_w)).astype(np.float32)
    b = src.read(3, window=win, out_shape=(out_h, out_w)).astype(np.float32)

    rgb = stretch_rgb(r, g, b)
    extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]
    return rgb, extent


def render_site(site, years, out_path):
    """Render a grid for one site, full resolution, saved to disk."""

    # Load polygons
    gdf = gpd.read_file(site["shp"])
    if gdf.crs and gdf.crs.to_epsg() != 3857:
        gdf = gdf.to_crs(TARGET_CRS)

    # Site bounds from the training photo
    with rasterio.open(site["photo"]) as src:
        site_bounds = src.bounds
        site_w_px   = src.width
        site_h_px   = src.height

    n_cells  = GRID_COLS * GRID_COLS
    n_years  = len(years)
    n_rows   = math.ceil(n_years / GRID_COLS)
    # Pad to full 4×4
    n_rows   = max(n_rows, GRID_COLS)

    # Scale figure so each cell is proportional to the site's pixel dimensions
    cell_w_in = 8.0
    cell_h_in = cell_w_in * (site_h_px / site_w_px)
    fig_w     = cell_w_in * GRID_COLS
    fig_h     = cell_h_in * n_rows

    fig, axes = plt.subplots(
        n_rows, GRID_COLS,
        figsize=(fig_w, fig_h),
        squeeze=False)
    fig.suptitle(
        f"{site['label']} — Training Polygons (2020 anchor) × Multi-Year Imagery",
        fontsize=16, fontweight="bold", y=1.005, color="white")
    fig.patch.set_facecolor("#0d1117")

    for cell_idx in range(n_rows * GRID_COLS):
        row_idx = cell_idx // GRID_COLS
        col_idx = cell_idx % GRID_COLS
        ax = axes[row_idx, col_idx]

        if cell_idx < n_years:
            year     = years[cell_idx]
            img_path = UPSAMPLE_DIR / year["file"]

            try:
                with rasterio.open(img_path) as src:
                    rgb, extent = read_extent_fullres(src, site_bounds)

                if rgb is not None:
                    ax.imshow(rgb, extent=extent, origin="upper",
                              interpolation="none")
                    gdf.boundary.plot(
                        ax=ax, edgecolor="yellow", linewidth=0.4, alpha=0.85)
                else:
                    ax.text(0.5, 0.5, "No overlap",
                            transform=ax.transAxes, ha="center",
                            va="center", color="gray", fontsize=10)
            except Exception as e:
                ax.text(0.5, 0.5, f"Error:\n{str(e)[:80]}",
                        transform=ax.transAxes, ha="center",
                        va="center", color="red", fontsize=8, wrap=True)

            is_anchor = year["label"] == "2020"
            title_color = "#ffd700" if is_anchor else "#c9d1d9"
            title_weight = "bold" if is_anchor else "normal"
            border_color = "#ffd700" if is_anchor else "#30363d"
            ax.set_title(year["label"], fontsize=12,
                         fontweight=title_weight, color=title_color,
                         pad=4)
            for spine in ax.spines.values():
                spine.set_edgecolor(border_color)
                spine.set_linewidth(2 if is_anchor else 0.5)
        else:
            # Empty cell
            for spine in ax.spines.values():
                spine.set_visible(False)

        ax.set_xlim(site_bounds.left, site_bounds.right)
        ax.set_ylim(site_bounds.bottom, site_bounds.top)
        ax.set_aspect("equal")
        ax.set_facecolor("#0d1117")
        ax.tick_params(labelbottom=False, labelleft=False,
                       bottom=False, left=False)

    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor(), pad_inches=0.3)
    plt.close(fig)

    file_mb = out_path.stat().st_size / 1e6
    print(f"  ✓ {out_path.name}  ({file_mb:.1f} MB)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    filtered = [a for a in sys.argv[1:]
                if not (a == "-f" or a.endswith(".json"))]
    parser = argparse.ArgumentParser(
        description="Temporal polygon overlay — full-res to Drive")
    parser.add_argument("--site", type=str, default=None,
                        help="Single site to render (e.g. Forest_1)")
    args = parser.parse_args(filtered)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Discover positive sites
    photo_files = sorted(PHOTOS_DIR.glob("*_rgb.tif"))
    sites = []
    for pf in photo_files:
        label = pf.stem.replace("_rgb", "")
        shp   = POLYGONS_DIR / f"{label}.shp"
        if shp.exists():
            sites.append({"label": label, "photo": pf, "shp": shp})

    if args.site:
        sites = [s for s in sites if s["label"] == args.site]
        if not sites:
            print(f"  ERROR: site '{args.site}' not found")
            return

    # Filter to years that exist on disk
    years = [y for y in YEAR_CATALOG if (UPSAMPLE_DIR / y["file"]).exists()]
    if not years:
        print("  ERROR: no imagery found in upsample folder")
        return

    n_rows = math.ceil(len(years) / GRID_COLS)

    print(f"  Sites:   {[s['label'] for s in sites]}")
    print(f"  Years:   {[y['label'] for y in years]}")
    print(f"  Layout:  {n_rows}×{GRID_COLS}  "
          f"({len(years)} years + {n_rows * GRID_COLS - len(years)} empty)")
    print(f"  Output:  {OUT_DIR}\n")

    for site in sites:
        out_path = OUT_DIR / f"{site['label']}_temporal.png"
        print(f"  Rendering {site['label']}...")
        render_site(site, years, out_path)

    print(f"\n  ✓ All done — {len(sites)} images saved to:")
    print(f"    {OUT_DIR}")


if __name__ == "__main__":
    main()