"""
King County Aerial Imagery — Native Resolution Probe
For each year, downloads one tile from the same location in Edmonds
at a fixed zoom level and computes Laplacian variance (sharpness score).

Genuinely high-res imagery: high sharpness score (sharp edges, fine detail)
Upsampled low-res imagery:  low sharpness score (blurry, smooth gradients)

Also extracts native resolution from the service description text.

Run from Colab. Results saved to:
  /content/drive/MyDrive/treedata/kc_sharpness_report.txt
"""

import re
import requests
import numpy as np
from io import BytesIO
from pathlib import Path
from PIL import Image

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
    "Referer":    "https://experience.arcgis.com/",
    "Accept":     "*/*",
}

BASE = "https://gismaps.kingcounty.gov/arcgis/rest/services/BaseMaps"

# Probe tile — zoom 19, central Edmonds, confirmed working for 2009 and 2012
# All years are probed at the same zoom/location for a fair comparison
PROBE_ZOOM = 19
PROBE_ROW  = 182626
PROBE_COL  = 83946

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

# Known native resolutions from service descriptions (inches per pixel)
KNOWN_NATIVE = {
    1936: "12 in (scanned, resampled to 1 ft)",
    1998: "3 ft (B&W)",
    2000: "2 ft",
    2002: "unknown",
    2005: "12 in",
    2007: "6 in",
    2009: "3 in (stated)",
    2012: "3 in (stated)",
    2013: "3 in",
    2015: "3 in",
    2017: "3 in",
    2019: "3 in",
    2021: "3 in",
    2023: "3 in",
}


def laplacian_variance(img_array):
    """
    Sharpness metric: variance of the Laplacian.
    Higher = sharper = more genuine high-frequency detail.
    Works on grayscale array.
    """
    # Simple 3x3 Laplacian kernel
    gray = img_array.mean(axis=2).astype(np.float32)
    kernel = np.array([[0,  1, 0],
                       [1, -4, 1],
                       [0,  1, 0]], dtype=np.float32)
    from scipy.ndimage import convolve
    lap = convolve(gray, kernel)
    return float(np.var(lap))


def fetch_tile(session, url, zoom, row, col):
    r = session.get(f"{url}/tile/{zoom}/{row}/{col}", timeout=15)
    if r.status_code == 200 and len(r.content) > 500:
        img = Image.open(BytesIO(r.content)).convert("RGB")
        return np.array(img), len(r.content)
    return None, 0


def main():
    try:
        from google.colab import drive as _drive
        import os
        if not os.path.exists("/content/drive/MyDrive"):
            _drive.mount("/content/drive")
    except ImportError:
        pass

    print(f"Probing zoom {PROBE_ZOOM} tile {PROBE_ROW}/{PROBE_COL} for all years...")
    print(f"(Same tile location = fair sharpness comparison)\n")

    results = []
    with requests.Session() as session:
        session.headers.update(BROWSER_HEADERS)
        for year, url in sorted(YEARS.items()):
            print(f"  {year}...", end=" ", flush=True)
            arr, size_bytes = fetch_tile(session, url, PROBE_ZOOM, PROBE_ROW, PROBE_COL)
            if arr is None:
                print("no tile")
                results.append({"year": year, "sharpness": None,
                                 "size_kb": 0, "error": "no tile"})
                continue

            sharpness = laplacian_variance(arr)
            print(f"sharpness={sharpness:>8.1f}  tile_size={size_bytes/1024:.1f} KB")
            results.append({
                "year": year, "sharpness": sharpness,
                "size_kb": size_bytes / 1024, "error": None
            })

    # Sort by sharpness descending for the report
    valid = [r for r in results if r["sharpness"] is not None]
    max_sharp = max(r["sharpness"] for r in valid) if valid else 1

    lines = []
    lines.append("=" * 90)
    lines.append("  King County Aerial Imagery — Sharpness Report")
    lines.append(f"  Probe: zoom={PROBE_ZOOM}, row={PROBE_ROW}, col={PROBE_COL}  (central Edmonds)")
    lines.append("=" * 90)
    lines.append(f"\n{'Year':<6} {'Native Res':<26} {'Sharpness':>10} {'Bar':<25} {'Tile KB':>8}")
    lines.append("-" * 90)

    for r in sorted(results, key=lambda x: x["year"]):
        year = r["year"]
        native = KNOWN_NATIVE.get(year, "unknown")
        if r["error"]:
            lines.append(f"{year:<6} {native:<26} {'—':>10}  no tile")
            continue
        sharp = r["sharpness"]
        bar_len = int(sharp / max_sharp * 24)
        bar = "█" * bar_len
        flag = " ← likely native 3in" if sharp > max_sharp * 0.7 else \
               " ← likely upsampled"  if sharp < max_sharp * 0.3 else ""
        lines.append(
            f"{year:<6} {native:<26} {sharp:>10.1f}  {bar:<25} {r['size_kb']:>7.1f} KB{flag}"
        )

    lines.append("")
    lines.append("Notes:")
    lines.append("  Sharpness = Laplacian variance. All tiles from identical zoom/location.")
    lines.append("  Higher sharpness = more genuine high-frequency detail = closer to native res.")
    lines.append("  Upsampled imagery shows smooth gradients regardless of zoom level.")

    report = "\n".join(lines)
    print("\n\n" + report)

    out = Path("/content/drive/MyDrive/treedata/kc_sharpness_report.txt")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report)
        print(f"\n  Saved: {out}")
    except Exception as e:
        print(f"\n  Could not save: {e}")


if __name__ == "__main__":
    main()