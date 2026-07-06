#!/usr/bin/env python3
"""
SINGLE BATCH DOWNLOADER — Complete process isolation
=====================================================
Downloads ONE batch then exits. Run multiple times for multiple batches.
Complete memory reset between batches (new Python process each time).

Usage:
  import os
  os.environ["YEAR"] = "2020"
  os.environ["BATCH_NUM"] = "0"  # which batch to download
  %run edmonds_single_batch.py
"""

import os, io, math, time, gc
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
from PIL import Image
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS

# ============================================================
#  CONFIG
# ============================================================
BATCH_DIR  = "/content/tmp_batches"
XMIN, YMIN, XMAX, YMAX = -13625876.424, 6068463.621, -13614805.955, 6084271.153

YEAR = os.environ.get("YEAR", "2020")
BATCH_NUM = int(os.environ.get("BATCH_NUM", "0"))
BATCH_SIZE = 500

EDM_URL = f"https://maps.edmondswa.gov/gis/rest/services/Basemap/{YEAR}_Aerial_Cached/ImageServer"
CHUNK_PX = 2048
RES_M = 0.075
NATIVE_EPSG = 3857
BANDS = 4
TIMEOUT = 180

# Coverage filter
COL_MIN, COL_MAX = 18, 54
ROW_MIN, ROW_MAX = 0, 102

# ============================================================
#  HTTP SESSION
# ============================================================
def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": "EdmondsBatch/1.0"})
    retry = Retry(total=6, backoff_factor=3.0, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry, pool_connections=5, pool_maxsize=5)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s

_session = make_session()

# ============================================================
#  CHUNK FETCHER
# ============================================================
def fetch_chunk(export_url, params, row, col):
    for attempt in range(3):
        try:
            resp = _session.get(export_url, params=params, timeout=TIMEOUT)
            ct = resp.headers.get("Content-Type", "")
            
            if "json" in ct or "html" in ct or len(resp.content) < 500:
                return None
            
            img = Image.open(io.BytesIO(resp.content))
            arr = np.array(img)
            if arr.size == 0 or arr.max() == 0:
                img.close()
                return None
            img.close()
            
            return (row, col, resp.content)
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
    return None

# ============================================================
#  MAIN
# ============================================================
def main():
    print("="*72)
    print(f"  SINGLE BATCH DOWNLOADER — {YEAR} — Batch {BATCH_NUM}")
    print("="*72)
    
    # Calculate grid
    px_unit = RES_M
    chunk_ext = CHUNK_PX * px_unit
    width = XMAX - XMIN
    height = YMAX - YMIN
    ncols = max(1, math.ceil(width / chunk_ext))
    nrows = max(1, math.ceil(height / chunk_ext))
    
    # Build filtered chunk list
    all_chunks = []
    for row in range(nrows):
        for col in range(ncols):
            if col < COL_MIN or col > COL_MAX:
                continue
            if row < ROW_MIN or row > ROW_MAX:
                continue
            all_chunks.append((row, col))
    
    # Get this batch's chunk list
    start_idx = BATCH_NUM * BATCH_SIZE
    end_idx = start_idx + BATCH_SIZE
    chunk_list = all_chunks[start_idx:end_idx]
    
    if not chunk_list:
        print(f"  Batch {BATCH_NUM} is empty (out of range)")
        return
    
    print(f"  Total chunks in coverage area: {len(all_chunks)}")
    print(f"  This batch: chunks {start_idx}-{end_idx-1} ({len(chunk_list)} chunks)")
    
    # Check if already done
    batch_path = os.path.join(BATCH_DIR, f"batch_{BATCH_NUM:04d}.tif")
    if os.path.exists(batch_path):
        sz_mb = os.path.getsize(batch_path) / 1e6
        print(f"  Batch {BATCH_NUM} already exists ({sz_mb:.1f} MB), skipping")
        return
    
    # Calculate batch bounding box
    min_row = min(r for r, c in chunk_list)
    max_row = max(r for r, c in chunk_list)
    min_col = min(c for r, c in chunk_list)
    max_col = max(c for r, c in chunk_list)
    
    batch_ncols = max_col - min_col + 1
    batch_nrows = max_row - min_row + 1
    
    full_w = batch_ncols * CHUNK_PX
    full_h = batch_nrows * CHUNK_PX
    
    geo_xmin = XMIN + min_col * chunk_ext
    geo_ymax = YMAX - min_row * chunk_ext
    geo_xmax = geo_xmin + batch_ncols * chunk_ext
    geo_ymin = geo_ymax - batch_nrows * chunk_ext
    
    transform = from_bounds(geo_xmin, geo_ymin, geo_xmax, geo_ymax, full_w, full_h)
    
    profile = {
        "driver": "GTiff", "dtype": "uint8",
        "width": full_w, "height": full_h, "count": BANDS,
        "crs": CRS.from_epsg(NATIVE_EPSG), "transform": transform,
        "compress": "deflate", "predictor": 2,
        "tiled": True, "blockxsize": 512, "blockysize": 512,
        "BIGTIFF": "YES",
    }
    
    # Create batch file
    os.makedirs(BATCH_DIR, exist_ok=True)
    tmp_path = batch_path + ".partial"
    dst = rasterio.open(tmp_path, "w", **profile)
    
    # Build work list
    export_url = EDM_URL + "/exportImage"
    work = []
    
    for row, col in chunk_list:
        cx0 = XMIN + col * chunk_ext
        cx1 = cx0 + chunk_ext
        cy1 = YMAX - row * chunk_ext
        cy0 = cy1 - chunk_ext
        
        params = {
            "bbox": f"{cx0},{cy0},{cx1},{cy1}",
            "bboxSR": NATIVE_EPSG,
            "imageSR": NATIVE_EPSG,
            "size": f"{CHUNK_PX},{CHUNK_PX}",
            "format": "tiff",
            "pixelType": "U8",
            "interpolation": "RSP_BilinearInterpolation",
            "f": "image",
        }
        work.append((export_url, params, row, col))
    
    ok_count = 0
    pbar = tqdm(total=len(work), desc=f"  Batch {BATCH_NUM}", unit="chunk")
    
    with ThreadPoolExecutor(max_workers=1) as pool:
        futures = {pool.submit(fetch_chunk, *w): w for w in work}
        
        for fut in as_completed(futures):
            result = fut.result()
            
            if result is not None:
                row, col, img_bytes = result
                
                try:
                    img = Image.open(io.BytesIO(img_bytes))
                    arr = np.array(img).astype(np.uint8)
                    
                    py = (row - min_row) * CHUNK_PX
                    px = (col - min_col) * CHUNK_PX
                    
                    window = rasterio.windows.Window(px, py, CHUNK_PX, CHUNK_PX)
                    
                    if arr.ndim == 3:
                        h, w = min(CHUNK_PX, arr.shape[0]), min(CHUNK_PX, arr.shape[1])
                        nb = min(BANDS, arr.shape[2])
                        for b in range(nb):
                            padded = np.zeros((CHUNK_PX, CHUNK_PX), dtype=np.uint8)
                            padded[:h, :w] = arr[:h, :w, b]
                            dst.write(padded, b + 1, window=window)
                            del padded
                    
                    ok_count += 1
                    img.close()
                    del img, arr, img_bytes
                    
                except Exception as e:
                    pass
            
            pbar.update(1)
    
    pbar.close()
    dst.close()
    
    os.rename(tmp_path, batch_path)
    
    sz_mb = os.path.getsize(batch_path) / 1e6
    print(f"  SUCCESS: {ok_count}/{len(work)} chunks, {sz_mb:.1f} MB")
    print(f"  Saved: {batch_path}")

if __name__ == "__main__":
    main()
