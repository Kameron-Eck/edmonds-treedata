#!/usr/bin/env python3
"""
QUICK COVERAGE TEST
===================
Sample 25 points across the entire bbox grid to find where imagery exists.
This will tell us if the problem is:
1. Geographic (first 100 chunks are outside coverage)
2. Systematic (entire bbox is wrong)
3. Server-wide (all requests fail)
"""

import requests, io, time
import numpy as np
from PIL import Image
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Config
XMIN, YMIN, XMAX, YMAX = -13625876.424, 6068463.621, -13614805.955, 6084271.153
EDM_URL = "https://maps.edmondswa.gov/gis/rest/services/Basemap/2020_Aerial_Cached/ImageServer"
CHUNK_PX = 2048
RES_M = 0.075
NATIVE_EPSG = 3857

# Calculate grid
chunk_ext = CHUNK_PX * RES_M
width = XMAX - XMIN
height = YMAX - YMIN
ncols = int(np.ceil(width / chunk_ext))
nrows = int(np.ceil(height / chunk_ext))

print("="*60)
print("EDMONDS COVERAGE TEST")
print("="*60)
print(f"Full grid: {ncols}x{nrows} = {ncols*nrows} chunks")
print(f"Testing 25 sample points across entire bbox...")
print()

# Sample points: 5x5 grid covering entire area
sample_rows = [0, nrows//4, nrows//2, 3*nrows//4, nrows-1]
sample_cols = [0, ncols//4, ncols//2, 3*ncols//4, ncols-1]

session = requests.Session()
retry = Retry(total=2, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retry, pool_connections=5, pool_maxsize=5)
session.mount("http://", adapter)
session.mount("https://", adapter)

export_url = EDM_URL + "/exportImage"

results = []
success_count = 0
fail_count = 0

for row in sample_rows:
    for col in sample_cols:
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
        
        try:
            resp = session.get(export_url, params=params, timeout=30)
            size_kb = len(resp.content) / 1024
            
            # Try to decode
            try:
                img = Image.open(io.BytesIO(resp.content))
                arr = np.array(img)
                
                if arr.size > 0 and arr.max() > 0:
                    status = "✓ SUCCESS"
                    success_count += 1
                else:
                    status = "✗ EMPTY"
                    fail_count += 1
            except Exception as e:
                if "truncated" in str(e).lower():
                    status = "✗ TRUNCATED"
                else:
                    status = f"✗ ERROR: {e}"
                fail_count += 1
            
            result = f"[{row:3d},{col:2d}]  {size_kb:7.0f} KB  {status}"
            print(result)
            results.append((row, col, size_kb, status))
            
        except Exception as e:
            result = f"[{row:3d},{col:2d}]  FETCH FAILED: {e}"
            print(result)
            results.append((row, col, 0, "✗ FETCH ERROR"))
            fail_count += 1
        
        time.sleep(0.5)  # gentle on server

print()
print("="*60)
print("SUMMARY")
print("="*60)
print(f"Success: {success_count}/25")
print(f"Failed:  {fail_count}/25")
print()

if success_count > 0:
    print("✓ GOOD NEWS: Some chunks have valid imagery!")
    print("  Problem: You're starting from a coverage gap")
    print("  Solution: Skip to chunks that have data")
    print()
    print("  Successful chunks (row, col):")
    for row, col, size, status in results:
        if "SUCCESS" in status:
            print(f"    [{row},{col}] - {size:.0f} KB")
elif fail_count == 25:
    print("✗ BAD NEWS: No valid imagery anywhere in bbox")
    print("  Possible causes:")
    print("    1. Wrong bbox coordinates for this imagery layer")
    print("    2. Wrong year (2020 imagery might not cover this area)")
    print("    3. Server issue affecting all requests")
    print()
    print("  Try:")
    print("    - Check Edmonds GIS portal for actual coverage extent")
    print("    - Try a different year (2015, 2017, 2022, 2024)")
    print("    - Verify bbox in QGIS/ArcGIS")

print("="*60)