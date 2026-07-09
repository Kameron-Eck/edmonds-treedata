"""
Imagery Statistics — Source Imagery Characterisation
═════════════════════════════════════════════════════
Extracts per-image and summary statistics from the source
(non-upsampled) imagery stack for use in a literature review
and methods section.

OUTPUT
──────
  treedata/imagery_stats/imagery_catalog.csv     Per-image stats table
  treedata/imagery_stats/imagery_summary.txt     Formatted summary report

USAGE
─────
  %run imagery_stats.py
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from shapely.geometry import box

warnings.filterwarnings("ignore")

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE       = Path("/content/drive/MyDrive/treedata")
IMG_DIR    = BASE / "Full_Image/Pipeline Imagery"
OUT_DIR    = BASE / "imagery_stats"
BOUNDARY   = BASE / "City Boundry/Edmonds Boundry.shp"
TARGET_CRS = "EPSG:3857"

YEAR_CATALOG = [
    {"key": 2000,    "file": "2000_king_rgb.tif",      "label": "2000",  "source": "King County",   "season": "summer"},
    {"key": 2002,    "file": "2002_king_rgb.tif",     "label": "2002",  "source": "King County",   "season": "summer"},
    {"key": 2005,    "file": "2005_king_rgb.tif",      "label": "2005",  "source": "King County",   "season": "summer"},
    {"key": 2007,    "file": "2007_king_rgb.tif",      "label": "2007",  "source": "King County",   "season": "summer"},
    {"key": "2009",  "file": "2009_king_rgb.tif",      "label": "2009",  "source": "King County",   "season": "summer"},
    {"key": 2013,    "file": "2013_king_rgb.tif",      "label": "2013",  "source": "King County",   "season": "summer"},
    {"key": 2015,    "file": "2015_king_rgb.tif",      "label": "2015",  "source": "King County",   "season": "summer"},
    {"key": 2016,    "file": "2016_snoh_rgbi.tif",     "label": "2016",  "source": "Snohomish Co.", "season": "summer"},
    {"key": 2017,    "file": "2017_coe_rgb.tif",       "label": "2017",  "source": "City of Edmonds", "season": "summer"},
    {"key": 2019,    "file": "2019_king_rgb.tif",      "label": "2019",  "source": "King County",   "season": "summer"},
    {"key": "2019n", "file": "2019_naip_rgbi.tif",     "label": "2019n", "source": "NAIP",          "season": "summer"},
    {"key": 2020,    "file": "2020_coe_rgb.tif",       "label": "2020",  "source": "City of Edmonds", "season": "summer"},
    {"key": 2021,    "file": "2021_king_rgb.tif",      "label": "2021",  "source": "King County",   "season": "summer"},
    {"key": "2021s", "file": "2021_snoh_rgbi.tif",     "label": "2021s", "source": "Snohomish Co.", "season": "summer"},
    {"key": 2022,    "file": "2022_coe_rgb.tif",       "label": "2022",  "source": "City of Edmonds", "season": "summer"},
    {"key": "2022n", "file": "2022_naip_rgbi.tif",     "label": "2022n", "source": "NAIP",          "season": "summer"},
    {"key": 2023,    "file": "2023_king_rgb.tif",      "label": "2023",  "source": "King County",   "season": "summer"},
    {"key": 2024,    "file": "2024_coe_rgb.tif",       "label": "2024",  "source": "City of Edmonds", "season": "summer"},
]


def extract_stats(entry, edmonds_geom=None):
    """Extract comprehensive statistics from a single raster."""
    path = IMG_DIR / entry["file"]
    if not path.exists():
        return None

    with rasterio.open(path) as src:
        bounds    = src.bounds
        epsg      = src.crs.to_epsg() if src.crs else None
        res_x     = abs(src.transform.a)
        res_y     = abs(src.transform.e)
        width_px  = src.width
        height_px = src.height
        n_bands   = src.count
        dtype     = src.dtypes[0]
        nodata    = src.nodata
        compress  = src.compression

        # Determine if resolution is in degrees or meters
        if epsg == 4326 or (res_x < 0.01 and res_y < 0.01):
            # Geographic CRS — approximate GSD at Edmonds latitude (~47.8°N)
            lat_rad  = np.radians(47.8)
            gsd_x_m  = res_x * 111320 * np.cos(lat_rad)
            gsd_y_m  = res_y * 111320
            gsd_unit = "degrees (converted)"
        else:
            gsd_x_m = res_x
            gsd_y_m = res_y
            gsd_unit = "meters"

        gsd_cm = (gsd_x_m + gsd_y_m) / 2 * 100

        # Ground extent
        if epsg == 4326:
            lat_rad   = np.radians(47.8)
            extent_w  = (bounds.right - bounds.left) * 111320 * np.cos(lat_rad)
            extent_h  = (bounds.top - bounds.bottom) * 111320
        else:
            extent_w = bounds.right - bounds.left
            extent_h = bounds.top   - bounds.bottom

        area_km2 = (extent_w * extent_h) / 1e6

        # Spectral config
        if n_bands == 4:
            spectral = "RGBI (4-band)"
        elif n_bands == 3:
            spectral = "RGB (3-band)"
        else:
            spectral = f"{n_bands}-band"

        # Coverage overlap with Edmonds
        overlap_pct = None
        if edmonds_geom is not None:
            try:
                import geopandas as gpd
                img_box = box(*bounds)
                if epsg and epsg != 3857:
                    from shapely.ops import transform
                    import pyproj
                    proj = pyproj.Transformer.from_crs(
                        f"EPSG:{epsg}", "EPSG:3857", always_xy=True)
                    img_box = transform(proj.transform, img_box)
                inter = edmonds_geom.intersection(img_box)
                overlap_pct = round(100 * inter.area / edmonds_geom.area, 1)
            except Exception:
                overlap_pct = None

        # Band statistics (sample if image is very large)
        band_stats = {}
        sample_frac = min(1.0, 2000 / max(width_px, height_px))
        out_w = max(1, int(width_px * sample_frac))
        out_h = max(1, int(height_px * sample_frac))

        for b in range(1, min(n_bands + 1, 5)):
            data = src.read(b, out_shape=(out_h, out_w)).astype(np.float32)
            if nodata is not None:
                data = np.where(data == nodata, np.nan, data)
            valid = data[~np.isnan(data)]
            if len(valid) > 0:
                band_stats[f"band{b}_min"]  = float(np.min(valid))
                band_stats[f"band{b}_mean"] = round(float(np.mean(valid)), 1)
                band_stats[f"band{b}_max"]  = float(np.max(valid))
                band_stats[f"band{b}_std"]  = round(float(np.std(valid)), 1)

        file_mb = path.stat().st_size / 1e6

    row = {
        "label":         entry["label"],
        "year":          str(entry["key"]).rstrip("ns"),
        "source":        entry["source"],
        "filename":      entry["file"],
        "spectral":      spectral,
        "n_bands":       n_bands,
        "dtype":         dtype,
        "epsg":          epsg,
        "native_res_x":  round(res_x, 8),
        "native_res_y":  round(res_y, 8),
        "gsd_cm":        round(gsd_cm, 2),
        "width_px":      width_px,
        "height_px":     height_px,
        "extent_w_m":    round(extent_w, 1),
        "extent_h_m":    round(extent_h, 1),
        "area_km2":      round(area_km2, 3),
        "edmonds_coverage_pct": overlap_pct,
        "nodata":        nodata,
        "compression":   compress,
        "file_mb":       round(file_mb, 1),
    }
    row.update(band_stats)
    return row


def write_summary(df, out_path):
    """Write a formatted text report for literature review use."""
    lines = []
    lines.append("=" * 70)
    lines.append("  IMAGERY CATALOG — Edmonds Tree Canopy Study")
    lines.append("  Source imagery characterisation (pre-upsampling)")
    lines.append("=" * 70)

    lines.append(f"\n  Temporal span:     {df['year'].min()} – {df['year'].max()}")
    lines.append(f"  Unique years:      {df['year'].nunique()}")
    lines.append(f"  Total images:      {len(df)}")

    lines.append(f"\n  GSD range:         "
                 f"{df['gsd_cm'].min():.1f} – {df['gsd_cm'].max():.1f} cm")
    lines.append(f"  GSD median:        {df['gsd_cm'].median():.1f} cm")

    rgb_count  = (df["n_bands"] == 3).sum()
    rgbi_count = (df["n_bands"] == 4).sum()
    lines.append(f"\n  Spectral config:   "
                 f"{rgb_count} RGB + {rgbi_count} RGBI")

    lines.append(f"\n  Acquisition sources:")
    for src, count in df["source"].value_counts().sort_index().items():
        yrs = sorted(df[df["source"] == src]["label"].tolist())
        lines.append(f"    {src:<20} {count} images  ({', '.join(yrs)})")

    epsg_counts = df["epsg"].value_counts()
    lines.append(f"\n  Coordinate reference systems:")
    for epsg, count in epsg_counts.items():
        lines.append(f"    EPSG:{epsg:<10} {count} images")

    dtype_counts = df["dtype"].value_counts()
    lines.append(f"\n  Bit depth:")
    for dt, count in dtype_counts.items():
        lines.append(f"    {dt:<15} {count} images")

    if "edmonds_coverage_pct" in df.columns:
        cov = df["edmonds_coverage_pct"].dropna()
        if len(cov) > 0:
            full = (cov >= 99).sum()
            partial = (cov < 99).sum()
            lines.append(f"\n  Edmonds coverage:")
            lines.append(f"    Full (≥99%):     {full} images")
            lines.append(f"    Partial (<99%):  {partial} images")
            if partial > 0:
                for _, r in df[df["edmonds_coverage_pct"] < 99].iterrows():
                    lines.append(f"      {r['label']:<10} {r['edmonds_coverage_pct']:.1f}%")

    lines.append(f"\n  Total disk usage:  {df['file_mb'].sum():.0f} MB")

    lines.append(f"\n{'─' * 70}")
    lines.append(f"  PER-IMAGE DETAIL")
    lines.append(f"{'─' * 70}")
    lines.append(f"  {'Label':<8} {'Source':<18} {'GSD':>7} {'Bands':>6} "
                 f"{'Dims (px)':>16} {'Area':>9} {'EPSG':>7} {'MB':>7}")
    lines.append(f"  {'─'*8} {'─'*18} {'─'*7} {'─'*6} "
                 f"{'─'*16} {'─'*9} {'─'*7} {'─'*7}")

    for _, r in df.iterrows():
        dims = f"{r['width_px']}×{r['height_px']}"
        lines.append(
            f"  {r['label']:<8} {r['source']:<18} "
            f"{r['gsd_cm']:>5.1f}cm {r['n_bands']:>5} "
            f"{dims:>16} {r['area_km2']:>7.1f}km² "
            f"{r['epsg']:>7} {r['file_mb']:>6.1f}")

    lines.append(f"\n{'─' * 70}")
    lines.append(f"  BAND STATISTICS (sampled)")
    lines.append(f"{'─' * 70}")

    for _, r in df.iterrows():
        lines.append(f"\n  {r['label']} ({r['spectral']}):")
        band_names = ["Red", "Green", "Blue", "NIR"]
        for b in range(1, r["n_bands"] + 1):
            mn = r.get(f"band{b}_min", "—")
            mu = r.get(f"band{b}_mean", "—")
            mx = r.get(f"band{b}_max", "—")
            sd = r.get(f"band{b}_std", "—")
            name = band_names[b-1] if b <= len(band_names) else f"Band{b}"
            if isinstance(mu, float):
                lines.append(f"    {name:<6} min={mn:.0f}  mean={mu:.1f}  "
                             f"max={mx:.0f}  std={sd:.1f}")

    lines.append(f"\n{'=' * 70}")
    lines.append(f"  Use this table in your methods section to describe")
    lines.append(f"  the multi-temporal imagery stack.")
    lines.append(f"{'=' * 70}")

    text = "\n".join(lines)
    out_path.write_text(text)
    return text


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  Imagery Statistics — Source Characterisation")
    print("=" * 60)

    # Load Edmonds boundary for coverage calculation
    edmonds_geom = None
    try:
        import geopandas as gpd
        edmonds = gpd.read_file(BOUNDARY)
        if edmonds.crs and edmonds.crs.to_epsg() != 3857:
            edmonds = edmonds.to_crs("EPSG:3857")
        edmonds_geom = edmonds.unary_union
        print(f"  ✓ Edmonds boundary loaded for coverage calculation")
    except Exception as e:
        print(f"  ⚠ Boundary not loaded ({e}) — skipping coverage")

    # Extract stats for each image
    rows = []
    for entry in YEAR_CATALOG:
        path = IMG_DIR / entry["file"]
        status = "✓" if path.exists() else "✗ MISSING"
        print(f"  {status}  {entry['label']:<8} {entry['file']}")

        stats = extract_stats(entry, edmonds_geom)
        if stats:
            rows.append(stats)

    if not rows:
        print("\n  ERROR: no imagery found")
        return

    df = pd.DataFrame(rows)

    # Save CSV
    csv_path = OUT_DIR / "imagery_catalog.csv"
    df.to_csv(csv_path, index=False)
    print(f"\n  ✓ CSV:    {csv_path}")

    # Save summary report
    txt_path = OUT_DIR / "imagery_summary.txt"
    report   = write_summary(df, txt_path)
    print(f"  ✓ Report: {txt_path}")

    # Print report to console
    print(f"\n{report}")


if __name__ == "__main__":
    main()
