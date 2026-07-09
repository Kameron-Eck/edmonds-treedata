"""
King County Aerial Imagery — Service Inspector (v4)
Finds true max cached zoom by probing tile sizes at descending zoom levels.
A real imagery tile is >3KB. Blank/error tiles are tiny (<1KB).
Uses 3 sample points across Edmonds to avoid false positives.
"""

import math
import requests
from pathlib import Path

XMIN = -13625091.384
YMIN =   6069864.416
XMAX = -13616492.219
YMAX =   6083584.863
EARTH = 20037508.342789244
TIMEOUT = 15
MIN_TILE_BYTES = 3000   # real imagery tile threshold

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    "Referer":    "https://experience.arcgis.com/",
    "Accept":     "*/*",
}

BASE = "https://gismaps.kingcounty.gov/arcgis/rest/services/BaseMaps"
YEARS = {
    1936: f"{BASE}/KingCo_Aerial_1936/MapServer",
    1998: f"{BASE}/KingCo_Aerial_1998/MapServer",
    2000: f"{BASE}/KingCo_Aerial_2000/MapServer",
    2002: f"{BASE}/KingCo_Aerial_2002/MapServer",
    2005: f"{BASE}/KingCo_Aerial_2005/MapServer",
    2007: f"{BASE}/KingCo_Aerial_2007/MapServer",
    2009: f"{BASE}/KingCo_Aerial_2009/MapServer",
    2012: f"{BASE}/KingCo_Aerial_2012/MapServer",
    2013: f"{BASE}/KingCo_Aerial_2013/MapServer",
    2015: f"{BASE}/KingCo_Aerial_2015/MapServer",
    2017: f"{BASE}/KingCo_Aerial_2017/MapServer",
    2019: f"{BASE}/KingCo_Aerial_2019/MapServer",
    2021: f"{BASE}/KingCo_Aerial_2021/MapServer",
    2023: f"{BASE}/KingCo_Aerial_2023/MapServer",
}

def merc_to_lon_lat(x, y):
    lon = x / EARTH * 180.0
    lat = math.degrees(2 * math.atan(math.exp(y / EARTH * math.pi)) - math.pi / 2)
    return lon, lat

def lon_lat_to_tile(lon, lat, level):
    n = 2 ** level
    col = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    row = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return row, col

def tile_range_for_edmonds(level):
    lon_min, lat_max = merc_to_lon_lat(XMIN, YMAX)
    lon_max, lat_min = merc_to_lon_lat(XMAX, YMIN)
    row_min, col_min = lon_lat_to_tile(lon_min, lat_max, level)
    row_max, col_max = lon_lat_to_tile(lon_max, lat_min, level)
    return row_min, row_max, col_min, col_max

def tile_has_imagery(session, url, level, row, col):
    """Return tile size in bytes, or 0 on failure."""
    try:
        r = session.get(f"{url}/tile/{level}/{row}/{col}", timeout=TIMEOUT)
        if r.status_code == 200:
            return len(r.content)
        return 0
    except Exception:
        return 0

def find_max_zoom(session, url, lods):
    """
    Descend from highest LOD to lowest.
    At each level, probe 3 tiles spread across the Edmonds extent.
    First level where ALL 3 probes return >MIN_TILE_BYTES = true max.
    """
    # 3 sample points: NW corner, centre, SE corner
    sample_points = [
        (XMIN + (XMAX-XMIN)*0.2, YMIN + (YMAX-YMIN)*0.8),
        (XMIN + (XMAX-XMIN)*0.5, YMIN + (YMAX-YMIN)*0.5),
        (XMIN + (XMAX-XMIN)*0.8, YMIN + (YMAX-YMIN)*0.2),
    ]

    for lod in sorted(lods, key=lambda l: l["level"], reverse=True):
        level = lod["level"]
        hits = 0
        for mx, my in sample_points:
            lon, lat = merc_to_lon_lat(mx, my)
            row, col = lon_lat_to_tile(lon, lat, level)
            size = tile_has_imagery(session, url, level, row, col)
            if size >= MIN_TILE_BYTES:
                hits += 1

        if hits >= 2:   # at least 2 of 3 probes hit real imagery
            return lod["level"], lod["resolution"]

    return lods[0]["level"], lods[0]["resolution"]

def inspect_year(year, url, session):
    try:
        r = session.get(url, params={"f": "json"}, timeout=TIMEOUT)
        r.raise_for_status()
        info = r.json()
    except Exception as e:
        return {"year": year, "error": str(e)}

    lods = info.get("tileInfo", {}).get("lods", [])
    if not lods:
        return {"year": year, "error": "No tile info"}

    max_level, max_res_m = find_max_zoom(session, url, lods)
    max_res_cm = max_res_m * 100
    max_res_in = max_res_m * 39.3701

    row_min, row_max, col_min, col_max = tile_range_for_edmonds(max_level)
    n_tiles = (row_max - row_min + 1) * (col_max - col_min + 1)

    desc = info.get("serviceDescription") or info.get("description") or ""
    source = "Unknown"
    for kw in ["Pictometry", "EagleView", "Emerge", "Space Imaging",
               "Pacific Meridian", "Aerials Express", "scanned"]:
        if kw.lower() in desc.lower():
            source = kw
            break

    return {
        "year": year, "url": url,
        "max_zoom": max_level, "res_cm": round(max_res_cm, 2),
        "res_in": round(max_res_in, 1),
        "row_min": row_min, "row_max": row_max,
        "col_min": col_min, "col_max": col_max,
        "n_tiles": n_tiles, "source": source, "error": None,
    }

def main():
    try:
        from google.colab import drive as _drive
        import os
        if not os.path.exists("/content/drive/MyDrive"):
            _drive.mount("/content/drive")
    except ImportError:
        pass

    results = []
    with requests.Session() as session:
        session.headers.update(BROWSER_HEADERS)
        for year, url in sorted(YEARS.items()):
            print(f"  Checking {year}...", end=" ", flush=True)
            result = inspect_year(year, url, session)
            results.append(result)
            if result["error"]:
                print(f"ERROR: {result['error']}")
            else:
                print(f"zoom {result['max_zoom']}  "
                      f"{result['res_cm']} cm/px  "
                      f"{result['n_tiles']:,} tiles")

    lines = []
    lines.append("=" * 100)
    lines.append("  King County Aerial Imagery — Service Report (v4)")
    lines.append(f"  Edmonds extent: ({XMIN:.0f}, {YMIN:.0f}, {XMAX:.0f}, {YMAX:.0f})")
    lines.append("=" * 100)
    lines.append(f"\n{'Year':<6} {'Max Zoom':<10} {'Res (cm)':<11} {'Res (in)':<11}"
                 f" {'Tiles':>10}  {'Source':<18}  Status")
    lines.append("-" * 100)

    for r in results:
        if r["error"]:
            lines.append(f"{r['year']:<6} ERROR: {r['error']}")
        else:
            compat = "✓ pipeline" if r["res_cm"] <= 8.0 else f"⚠  coarser ({r['res_cm']} cm)"
            lines.append(
                f"{r['year']:<6} {r['max_zoom']:<10} {r['res_cm']:<11} "
                f"{r['res_in']:<11} {r['n_tiles']:>10,}  {r['source']:<18}  {compat}"
            )

    lines.append("")
    lines.append("=" * 100)
    lines.append("  Per-year tile ranges at max zoom (for download_tiles.py)")
    lines.append("=" * 100)
    for r in results:
        if not r["error"]:
            lines.append(
                f"  {r['year']}: zoom={r['max_zoom']}  "
                f"rows {r['row_min']}–{r['row_max']}  "
                f"cols {r['col_min']}–{r['col_max']}  "
                f"({r['n_tiles']:,} tiles)"
            )

    report = "\n".join(lines)
    print("\n\n" + report)

    out = Path("/content/drive/MyDrive/treedata/kc_imagery_report.txt")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report)
        print(f"\n  Saved: {out}")
    except Exception as e:
        print(f"\n  Could not save: {e}")

if __name__ == "__main__":
    main()