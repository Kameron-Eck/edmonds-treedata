#!/usr/bin/env python3
"""
UNIFIED AERIAL IMAGERY DOWNLOADER v2 — Edmonds WA
===================================================
65 GeoTIFFs from 9 organizations. Two engines: tile_cache + exportImage.

v2 FIXES:
 - Parallel tile downloads (16 threads) — 10-15x faster for KingCo/Edmonds
 - Edmonds 2015/2017 switched to exportImage (was 481K tiles, now ~1800 chunks)
 - CRS transform via pyproj for non-3857 servers (fixes black images)

Run in Google Colab:
  pip install rasterio pyproj tqdm
  %run unified_downloader_v2.py
"""

import os, io, math, time, traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
from PIL import Image
import requests
from tqdm import tqdm

# ============================================================
#  CONFIG
# ============================================================
from pipeline_config import FULL_IMAGE_DIR
BASE_DIR   = str(FULL_IMAGE_DIR)
XMIN, YMIN, XMAX, YMAX = -13625876.424, 6068463.621, -13614805.955, 6084271.153

CHUNK_PX   = 4096
TILE_SZ    = 256
MAX_RETRY  = 3
SKIP_MB    = 1
TIMEOUT    = 120
TILE_WORKERS = 16    # parallel threads for tile downloads

ORIGIN = 20037508.342789244
def _res(z): return 2 * ORIGIN / (TILE_SZ * (2 ** z))

# ============================================================
#  CRS TRANSFORM
# ============================================================
_xf = {}
def get_bbox(to_epsg):
    if to_epsg == 3857:
        return (XMIN, YMIN, XMAX, YMAX)
    if to_epsg not in _xf:
        from pyproj import Transformer
        _xf[to_epsg] = Transformer.from_crs(3857, to_epsg, always_xy=True)
    t = _xf[to_epsg]
    x1, y1 = t.transform(XMIN, YMIN)
    x2, y2 = t.transform(XMAX, YMAX)
    return (min(x1,x2), min(y1,y2), max(x1,x2), max(y1,y2))

# ============================================================
#  SOURCE CATALOG
# ============================================================
EDM = "https://maps.edmondswa.gov/gis/rest/services/Basemap"
KC  = "https://gismaps.kingcounty.gov/arcgis/rest/services/BaseMaps"
SC  = "https://gis.snoco.org/img/rest/services/Imagery"
WT  = "https://imagery-public.watech.wa.gov/arcgis/rest/services/NAIP"
NOA = "https://coast.noaa.gov/arcgis/rest/services/Imagery"

# (group, name, method, url, bands, res_m, native_epsg, zoom, extra)
SOURCES = [
    # ── Edmonds ───────────────────────────────────────────────
    # 2015/2017: switched to exportImage (was tiles z21 = 481K requests)
    ("Edmonds","edmonds_2015","export",f"{EDM}/2015_Aerial_Cached/ImageServer",3,0.075,3857,0,{}),
    ("Edmonds","edmonds_2017","export",f"{EDM}/2017_Aerial_Cached/ImageServer",3,0.075,3857,0,{}),
    ("Edmonds","edmonds_2020","export",f"{EDM}/2020_Aerial_Cached/ImageServer",4,0.075,3857,0,{}),
    ("Edmonds","edmonds_2022","export",f"{EDM}/2022_Aerial_Cached/ImageServer",4,0.075,3857,0,{}),
    # 2024 is MapServer — must use tiles, but parallel now
    ("Edmonds","edmonds_2024","tiles",f"{EDM}/2024_Aerial_Cached/MapServer",3,0,3857,21,{}),

    # ── King County (tile cache, parallel) ────────────────────
    ("KingCo","kingco_1936","tiles",f"{KC}/KingCo_Aerial_1936/MapServer",3,0,3857,18,{}),
    ("KingCo","kingco_1998","tiles",f"{KC}/KingCo_Aerial_1998/MapServer",3,0,3857,18,{}),
    ("KingCo","kingco_2000","tiles",f"{KC}/KingCo_Aerial_2000/MapServer",3,0,3857,18,{}),
    ("KingCo","kingco_2002","tiles",f"{KC}/KingCo_Aerial_2002/MapServer",3,0,3857,18,{}),
    ("KingCo","kingco_2005","tiles",f"{KC}/KingCo_Aerial_2005/MapServer",3,0,3857,19,{}),
    ("KingCo","kingco_2007","tiles",f"{KC}/KingCo_Aerial_2007/MapServer",3,0,3857,19,{}),
    ("KingCo","kingco_2009","tiles",f"{KC}/KingCo_Aerial_2009/MapServer",3,0,3857,19,{}),
    ("KingCo","kingco_2012","tiles",f"{KC}/KingCo_Aerial_2012/MapServer",3,0,3857,19,{}),
    ("KingCo","kingco_2013","tiles",f"{KC}/KingCo_Aerial_2013/MapServer",3,0,3857,20,{}),
    ("KingCo","kingco_2015","tiles",f"{KC}/KingCo_Aerial_2015/MapServer",3,0,3857,20,{}),
    ("KingCo","kingco_2017","tiles",f"{KC}/KingCo_Aerial_2017/MapServer",3,0,3857,20,{}),
    ("KingCo","kingco_2019","tiles",f"{KC}/KingCo_Aerial_2019/MapServer",3,0,3857,20,{}),
    ("KingCo","kingco_2021","tiles",f"{KC}/KingCo_Aerial_2021/MapServer",3,0,3857,20,{}),
    ("KingCo","kingco_2023","tiles",f"{KC}/KingCo_Aerial_2023/MapServer",3,0,3857,20,{}),

    # ── Snohomish County (exportImage) ────────────────────────
    ("SnoCo","snoco_1990","export",f"{SC}/Aerial_1990/ImageServer",1,3.048,2285,0,{}),
    ("SnoCo","snoco_1996","export",f"{SC}/Aerial_1996/ImageServer",3,1.0,2285,0,{}),
    ("SnoCo","snoco_1998","export",f"{SC}/Aerial_1998/ImageServer",1,0.9144,2285,0,{}),
    ("SnoCo","snoco_2001","export",f"{SC}/Aerial_2001/ImageServer",1,0.3048,2285,0,{}),
    ("SnoCo","snoco_2002","export",f"{SC}/Aerial_2002/ImageServer",3,0.3048,2285,0,{}),
    ("SnoCo","snoco_2003","export",f"{SC}/Aerial_2003/ImageServer",3,0.3048,2285,0,{}),
    ("SnoCo","snoco_2006","export",f"{SC}/Aerial_2006/ImageServer",3,1.0,2285,0,{}),
    ("SnoCo","snoco_2007","export",f"{SC}/Aerial_2007/ImageServer",3,0.3048,32148,0,{}),
    ("SnoCo","snoco_2009","export",f"{SC}/Aerial_2009/ImageServer",3,0.3048,2285,0,{}),
    ("SnoCo","snoco_2011","export",f"{SC}/Aerial_2011/ImageServer",3,0.3048,2926,0,{}),
    ("SnoCo","snoco_2012","export",f"{SC}/Aerial_2012/ImageServer",3,0.2286,2285,0,{}),
    ("SnoCo","snoco_2013","export",f"{SC}/Aerial_2013/ImageServer",3,1.0,2285,0,{}),
    ("SnoCo","snoco_2015","export",f"{SC}/Aerial_2015/ImageServer",4,0.3048,2285,0,{}),
    ("SnoCo","snoco_2016","export",f"{SC}/Aerial_2016/ImageServer",4,0.1524,2285,0,{}),
    ("SnoCo","snoco_2017","export",f"{SC}/Aerial_2017/ImageServer",4,0.3048,2285,0,{}),
    ("SnoCo","snoco_2018","export",f"{SC}/Aerial_2018/ImageServer",4,0.1524,2285,0,{}),
    ("SnoCo","snoco_2019","export",f"{SC}/Aerial_2019/ImageServer",4,0.3048,2285,0,{}),
    ("SnoCo","snoco_2020","export",f"{SC}/Aerial_2020/ImageServer",3,0.0762,2285,0,{}),
    ("SnoCo","snoco_2021","export",f"{SC}/Aerial_2021/ImageServer",4,0.1524,2285,0,{}),
    ("SnoCo","snoco_2022","export",f"{SC}/Aerial_2022/ImageServer",3,0.0762,2285,0,{}),
    ("SnoCo","snoco_2024","export",f"{SC}/Aerial_2024/ImageServer",3,0.0762,2285,0,{}),

    # ── WA NAIP (exportImage, EPSG:2927) ──────────────────────
    ("WA_NAIP","wa_naip_1989_2000_bw","export",
     f"{WT}/Statewide_1989_2000_3ft_bw_wsps_83h/ImageServer",1,0.9144,2927,0,{}),
    ("WA_NAIP","wa_naip_2003","export",f"{WT}/NAIP_2003_2m_color_wsps_83h_img/ImageServer",3,2.0,2927,0,{}),
    ("WA_NAIP","wa_naip_2004","export",f"{WT}/NAIP_2004_2m_color_wsps_83h_img/ImageServer",3,2.0,2927,0,{}),
    ("WA_NAIP","wa_naip_2005","export",f"{WT}/NAIP_2005_2m_color_wsps_83h_img/ImageServer",3,2.0,2927,0,{}),
    ("WA_NAIP","wa_naip_2006","export",
     f"{WT}/Statewide_NAIP_2006_18in_color_wsps_83h_img/ImageServer",3,0.4572,2927,0,{}),
    ("WA_NAIP","wa_naip_2009","export",
     f"{WT}/Statewide_NAIP_2009_3ft_4band_wsps_83h_img/ImageServer",4,0.9144,2927,0,{}),
    ("WA_NAIP","wa_naip_2011","export",
     f"{WT}/Statewide_NAIP_2011_3ft_4band_wsps_83h_img/ImageServer",4,0.9144,2927,0,{}),
    ("WA_NAIP","wa_naip_2013","export",
     f"{WT}/Statewide_NAIP_2013_3ft_4band_wsps_83h_img/ImageServer",4,0.9144,2927,0,{}),
    ("WA_NAIP","wa_naip_2015","export",
     f"{WT}/Statewide_NAIP_2015_3ft_4band_wsps_83h_img/ImageServer",4,0.9144,2927,0,{}),
    ("WA_NAIP","wa_naip_2017","export",
     f"{WT}/Statewide_NAIP_2017_3ft_4band_wsps_83h_img/ImageServer",4,0.9144,2927,0,{}),
    ("WA_NAIP","wa_naip_2019","export",
     "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer",
     4,0.6,3857,0,{"mosaic_rule":'{"mosaicMethod":"esriMosaicAttribute","where":"Year=2019","sortField":"Year","ascending":false}'}),
    ("WA_NAIP","wa_naip_2023","export",
     "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer",
     4,0.6,3857,0,{"mosaic_rule":'{"mosaicMethod":"esriMosaicAttribute","where":"Year=2023","sortField":"Year","ascending":false}'}),

    # ── NOAA (EPSG:3857) ─────────────────────────────────────
    ("NOAA","noaa_rgb_8bit","export",f"{NOA}/rgb_8bit/ImageServer",3,0.3,3857,0,{}),
    ("NOAA","noaa_rgb_16bit","export",f"{NOA}/rgb_16bit/ImageServer",3,0.3,3857,0,{}),
    ("NOAA","noaa_cir_8bit","export",f"{NOA}/cir_8bit/ImageServer",3,0.3,3857,0,{}),
    ("NOAA","noaa_cir_16bit","export",f"{NOA}/cir_16bit/ImageServer",3,0.3,3857,0,{}),
    ("NOAA","noaa_4band_8bit","export",f"{NOA}/4band_8bit/ImageServer",4,0.3,3857,0,{}),
    ("NOAA","noaa_4band_16bit","export",f"{NOA}/4band_16bit/ImageServer",4,0.3,3857,0,{}),
    ("NOAA","noaa_ir_8bit","export",f"{NOA}/ir_8bit/ImageServer",1,0.3,3857,0,{}),

    # ── USGS ──────────────────────────────────────────────────
    ("USGS","usgs_naip_plus","export",
     "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer",4,0.6,3857,0,{}),
    ("USGS","usgs_naip_imagery","export",
     "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer",4,0.6,3857,0,{}),

    # ── Esri NAIP ─────────────────────────────────────────────
    ("Esri_NAIP","esri_naip_latest","export",
     "https://naip.imagery1.arcgis.com/arcgis/rest/services/NAIP/ImageServer",4,0.6,3857,0,{}),

    # ── USDA NRCS ─────────────────────────────────────────────
    ("USDA_NRCS","nrcs_nhap_1980s","export",
     "https://nrcsgeoservices.sc.egov.usda.gov/arcgis/rest/services/ortho_imagery/nhap_All/ImageServer",3,0.75,3857,0,{}),
    ("USDA_NRCS","nrcs_nhap_colorbal","export",
     "https://nrcsgeoservices.sc.egov.usda.gov/arcgis/rest/services/ortho_imagery/nhap_colorbalance/ImageServer",3,0.75,3857,0,{}),

    # ── WA DNR Nearshore ──────────────────────────────────────
    ("WA_DNR","dnr_nearshore_npugetsound_2022","export",
     "https://gis.dnr.wa.gov/image/rest/services/Aquatics/Nearshore_img__NPugetSound_2022/ImageServer",4,0.1524,2927,0,{}),
]

# ============================================================
#  HTTP
# ============================================================
_session = requests.Session()
_session.headers.update({"User-Agent": "EdmondsAerialDownloader/2.0"})

def fetch(url, params=None, retries=MAX_RETRY):
    for attempt in range(retries):
        try:
            r = _session.get(url, params=params, timeout=TIMEOUT)
            r.raise_for_status()
            return r
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
            else:
                raise

# ============================================================
#  ENGINE 1: PARALLEL TILE DOWNLOADER
# ============================================================
def _fetch_one_tile(args):
    """Worker for ThreadPoolExecutor. Returns (row, col, rgb_array) or None."""
    url, z, r, c = args
    tile_url = f"{url}/tile/{z}/{r}/{c}"
    try:
        resp = _session.get(tile_url, timeout=TIMEOUT)
        ct = resp.headers.get("Content-Type", "")
        if len(resp.content) < 200 or "image" not in ct:
            return None
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        return (r, c, np.array(img))
    except:
        return None

def download_tiles(group, name, url, bands, zoom, out_path):
    res = _res(zoom)
    col_min = int(math.floor((XMIN + ORIGIN) / (TILE_SZ * res)))
    col_max = int(math.floor((XMAX + ORIGIN) / (TILE_SZ * res)))
    row_min = int(math.floor((ORIGIN - YMAX) / (TILE_SZ * res)))
    row_max = int(math.floor((ORIGIN - YMIN) / (TILE_SZ * res)))

    ncols = col_max - col_min + 1
    nrows = row_max - row_min + 1
    total = ncols * nrows
    pw = ncols * TILE_SZ
    ph = nrows * TILE_SZ

    print(f"  z={zoom} res={res:.4f}m  grid={ncols}x{nrows}={total:,}  "
          f"output={pw}x{ph}px  workers={TILE_WORKERS}")

    canvas = np.zeros((3, ph, pw), dtype=np.uint8)
    ok = 0

    # Build work list
    work = [(url, zoom, r, c)
            for r in range(row_min, row_max + 1)
            for c in range(col_min, col_max + 1)]

    pbar = tqdm(total=total, desc=f"  {name}", unit="tile")
    with ThreadPoolExecutor(max_workers=TILE_WORKERS) as pool:
        futures = {pool.submit(_fetch_one_tile, w): w for w in work}
        for fut in as_completed(futures):
            result = fut.result()
            if result is not None:
                r, c, arr = result
                py = (r - row_min) * TILE_SZ
                px = (c - col_min) * TILE_SZ
                h = min(TILE_SZ, arr.shape[0])
                w = min(TILE_SZ, arr.shape[1])
                for b in range(3):
                    canvas[b, py:py+h, px:px+w] = arr[:h, :w, b]
                ok += 1
            pbar.update(1)
    pbar.close()

    if ok == 0:
        print(f"  NO TILES received — skipping"); return False

    print(f"  {ok:,}/{total:,} tiles with data")

    geo_xmin = col_min * TILE_SZ * res - ORIGIN
    geo_ymax = ORIGIN - row_min * TILE_SZ * res
    geo_xmax = geo_xmin + pw * res
    geo_ymin = geo_ymax - ph * res

    _save_geotiff(canvas, 3, pw, ph, geo_xmin, geo_ymin, geo_xmax, geo_ymax, 3857, out_path)
    return True

# ============================================================
#  ENGINE 2: EXPORTIMAGE DOWNLOADER
# ============================================================
def download_export(group, name, url, bands, res_m, native_epsg, extra, out_path):
    bbox = get_bbox(native_epsg)
    bx0, by0, bx1, by1 = bbox

    if native_epsg in (2285, 2926, 2927):
        FT = 0.3048006096012192
        px_unit = res_m / FT
    elif native_epsg == 32148:
        px_unit = res_m
    else:
        px_unit = res_m

    chunk_ext = CHUNK_PX * px_unit
    width  = bx1 - bx0
    height = by1 - by0
    ncols = max(1, math.ceil(width / chunk_ext))
    nrows = max(1, math.ceil(height / chunk_ext))
    total = ncols * nrows

    print(f"  EPSG:{native_epsg}  px={px_unit:.4f}  chunks={ncols}x{nrows}={total}")

    full_w = ncols * CHUNK_PX
    full_h = nrows * CHUNK_PX
    canvas = np.zeros((bands, full_h, full_w), dtype=np.uint8)
    ok = 0
    export_url = url + "/exportImage"

    pbar = tqdm(total=total, desc=f"  {name}", unit="chunk")
    for row in range(nrows):
        for col in range(ncols):
            cx0 = bx0 + col * chunk_ext
            cx1 = cx0 + chunk_ext
            cy1 = by1 - row * chunk_ext
            cy0 = cy1 - chunk_ext

            params = {
                "bbox": f"{cx0},{cy0},{cx1},{cy1}",
                "bboxSR": native_epsg,
                "imageSR": native_epsg,
                "size": f"{CHUNK_PX},{CHUNK_PX}",
                "format": "tiff",
                "pixelType": "U8",
                "interpolation": "RSP_BilinearInterpolation",
                "f": "image",
            }
            if "mosaic_rule" in extra:
                params["mosaicRule"] = extra["mosaic_rule"]

            try:
                resp = fetch(export_url, params)
                ct = resp.headers.get("Content-Type", "")
                if len(resp.content) < 500 or ("image" not in ct and "tiff" not in ct):
                    pbar.update(1); continue

                img = Image.open(io.BytesIO(resp.content))
                arr = np.array(img)
                py = row * CHUNK_PX
                px_off = col * CHUNK_PX

                if arr.ndim == 2:
                    h = min(CHUNK_PX, arr.shape[0])
                    w = min(CHUNK_PX, arr.shape[1])
                    canvas[0, py:py+h, px_off:px_off+w] = arr[:h, :w]
                elif arr.ndim == 3:
                    h = min(CHUNK_PX, arr.shape[0])
                    w = min(CHUNK_PX, arr.shape[1])
                    nb = min(bands, arr.shape[2])
                    for b in range(nb):
                        canvas[b, py:py+h, px_off:px_off+w] = arr[:h, :w, b]

                if canvas[0, py:py+min(64, full_h-py),
                          px_off:px_off+min(64, full_w-px_off)].max() > 0:
                    ok += 1
            except:
                pass
            pbar.update(1)
    pbar.close()

    if ok == 0:
        print(f"  NO DATA — skipping"); return False

    print(f"  {ok}/{total} chunks with data")

    geo_xmin = bx0
    geo_ymax = by1
    geo_xmax = bx0 + ncols * chunk_ext
    geo_ymin = by1 - nrows * chunk_ext

    if native_epsg == 3857:
        _save_geotiff(canvas, bands, full_w, full_h,
                      geo_xmin, geo_ymin, geo_xmax, geo_ymax, 3857, out_path)
    else:
        tmp = out_path + ".native.tif"
        _save_geotiff(canvas, bands, full_w, full_h,
                      geo_xmin, geo_ymin, geo_xmax, geo_ymax, native_epsg, tmp)
        _warp_to_3857(tmp, out_path)
        try: os.remove(tmp)
        except: pass

    return True

# ============================================================
#  GEOTIFF IO
# ============================================================
def _save_geotiff(arr, bands, w, h, xmin, ymin, xmax, ymax, epsg, path):
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS

    transform = from_bounds(xmin, ymin, xmax, ymax, w, h)
    profile = {
        "driver": "GTiff", "dtype": "uint8",
        "width": w, "height": h, "count": bands,
        "crs": CRS.from_epsg(epsg), "transform": transform,
        "compress": "deflate", "predictor": 2,
        "tiled": True, "blockxsize": 512, "blockysize": 512,
        "BIGTIFF": "YES",
    }
    with rasterio.open(path, "w", **profile) as dst:
        for b in range(bands):
            dst.write(arr[b], b + 1)
    sz = os.path.getsize(path) / 1e6
    print(f"  Saved: {os.path.basename(path)} ({sz:.1f} MB, {bands}b, EPSG:{epsg})")

def _warp_to_3857(src_path, dst_path):
    import rasterio
    from rasterio.warp import calculate_default_transform, reproject, Resampling
    from rasterio.crs import CRS

    dst_crs = CRS.from_epsg(3857)
    with rasterio.open(src_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds)
        meta = src.meta.copy()
        meta.update({
            "crs": dst_crs, "transform": transform,
            "width": width, "height": height,
            "compress": "deflate", "predictor": 2,
            "tiled": True, "blockxsize": 512, "blockysize": 512,
            "BIGTIFF": "YES",
        })
        with rasterio.open(dst_path, "w", **meta) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform, src_crs=src.crs,
                    dst_transform=transform, dst_crs=dst_crs,
                    resampling=Resampling.bilinear)
    sz = os.path.getsize(dst_path) / 1e6
    print(f"  Warped → EPSG:3857: {os.path.basename(dst_path)} ({sz:.1f} MB)")

# ============================================================
#  MAIN
# ============================================================
def main():
    # ── Multi-Colab support ──────────────────────────────────
    # Set env var DL_GROUPS to run only specific groups, e.g.:
    #   os.environ["DL_GROUPS"] = "Edmonds,KingCo"
    # Leave unset to run all 65 sources.
    filter_groups = os.environ.get("DL_GROUPS", "")
    if filter_groups:
        allowed = set(g.strip() for g in filter_groups.split(","))
        run_sources = [s for s in SOURCES if s[0] in allowed]
    else:
        allowed = None
        run_sources = list(SOURCES)

    print("=" * 70)
    print("  UNIFIED AERIAL IMAGERY DOWNLOADER v2 — Edmonds WA")
    print(f"  Sources: {len(run_sources)}/{len(SOURCES)}  |  Output: {BASE_DIR}")
    if allowed:
        print(f"  Filter: {', '.join(sorted(allowed))}")
    print(f"  Tile workers: {TILE_WORKERS}  |  Skip threshold: >{SKIP_MB} MB")
    print("=" * 70)

    groups = {}
    for s in run_sources:
        groups[s[0]] = groups.get(s[0], 0) + 1
    for g, n in groups.items():
        print(f"  {g}: {n}")

    completed, skipped, failed = 0, 0, 0

    for i, src in enumerate(run_sources):
        group, name, method, url, bands, res_m, native_epsg, zoom, extra = src
        out_dir = os.path.join(BASE_DIR, group)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{name}_image.tif")

        print(f"\n[{i+1}/{len(run_sources)}] {group}/{name}  ({method})")

        if os.path.exists(out_path):
            sz = os.path.getsize(out_path) / 1e6
            if sz > SKIP_MB:
                print(f"  SKIP ({sz:.1f} MB exists)")
                skipped += 1; continue

        try:
            if method == "tiles":
                ok = download_tiles(group, name, url, bands, zoom, out_path)
            else:
                ok = download_export(group, name, url, bands, res_m,
                                     native_epsg, extra, out_path)
            if ok: completed += 1
            else: failed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 70)
    print(f"  DONE: {completed} downloaded, {skipped} skipped, {failed} failed")
    print(f"  Total: {completed + skipped + failed}/{len(run_sources)}")
    print("=" * 70)

if __name__ == "__main__":
    main()
