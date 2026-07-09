#!/usr/bin/env python3
"""
Edmonds 2020 Aerial - Server Diagnostic Script
================================================
Tests what the exportImage endpoint actually supports.
Run this and paste the output back to Claude.
"""

import requests
import json

BASE = "https://maps.edmondswa.gov/gis/rest/services/Basemap/2020_Aerial_Cached/ImageServer"
EXPORT = f"{BASE}/exportImage"

# Small test bbox in downtown Edmonds (EPSG:3857)
BBOX = "-13620000,6076000,-13619500,6075500"

print("=" * 60)
print("Edmonds 2020 Aerial - Server Diagnostics")
print("=" * 60)

# ------------------------------------------------------------------
# Test 1: Service info (JSON)
# ------------------------------------------------------------------
print("\n[Test 1] Service metadata (key fields)...")
try:
    r = requests.get(BASE, params={"f": "json"}, timeout=30)
    r.raise_for_status()
    info = r.json()
    print(f"  Name:              {info.get('name')}")
    print(f"  Cache:             {info.get('singleFusedMapCache')}")
    print(f"  Bands:             {info.get('bandCount')}")
    print(f"  Pixel Type:        {info.get('pixelType')}")
    print(f"  Pixel Size X:      {info.get('pixelSizeX')}")
    print(f"  Pixel Size Y:      {info.get('pixelSizeY')}")
    print(f"  Max Image Width:   {info.get('maxImageWidth')}")
    print(f"  Max Image Height:  {info.get('maxImageHeight')}")
    print(f"  Service Data Type: {info.get('serviceDataType')}")
    
    # Check allowed formats from capabilities
    caps = info.get('capabilities', '')
    print(f"  Capabilities:      {caps}")
    
    # Check if there's format info in tile info
    tile_info = info.get('tileInfo', {})
    if tile_info:
        print(f"  Tile Format:       {tile_info.get('format')}")
        print(f"  Tile Width:        {tile_info.get('cols')}")
        print(f"  Tile Height:       {tile_info.get('rows')}")
        lods = tile_info.get('lods', [])
        if lods:
            z20 = [l for l in lods if l.get('level') == 20]
            if z20:
                print(f"  Zoom 20 res:       {z20[0].get('resolution')}")
                print(f"  Zoom 20 scale:     {z20[0].get('scale')}")
    
    # Check allowed fields  
    af = info.get('allowedFormats', info.get('supportedImageFormatTypes', ''))
    if af:
        print(f"  Allowed Formats:   {af}")
        
except Exception as e:
    print(f"  ERROR: {e}")

# ------------------------------------------------------------------
# Test 2: Export as TIFF (f=json to see error/response)
# ------------------------------------------------------------------
print("\n[Test 2] Export as TIFF (f=json)...")
try:
    params = {
        "bbox": BBOX,
        "bboxSR": "102100",
        "imageSR": "102100",
        "size": "256,256",
        "format": "tiff",
        "pixelType": "U8",
        "bandIds": "0,1,2,3",
        "f": "json",
    }
    r = requests.get(EXPORT, params=params, timeout=30)
    print(f"  Status: {r.status_code}")
    try:
        j = r.json()
        print(f"  Response: {json.dumps(j, indent=2)[:1000]}")
    except:
        print(f"  Response (text): {r.text[:500]}")
except Exception as e:
    print(f"  ERROR: {e}")

# ------------------------------------------------------------------
# Test 3: Export as TIFF (f=image to see what we get)
# ------------------------------------------------------------------
print("\n[Test 3] Export as TIFF (f=image)...")
try:
    params = {
        "bbox": BBOX,
        "bboxSR": "102100",
        "imageSR": "102100",
        "size": "256,256",
        "format": "tiff",
        "pixelType": "U8",
        "bandIds": "0,1,2,3",
        "f": "image",
    }
    r = requests.get(EXPORT, params=params, timeout=30)
    ct = r.headers.get("Content-Type", "?")
    print(f"  Status: {r.status_code}")
    print(f"  Content-Type: {ct}")
    print(f"  Content-Length: {len(r.content)} bytes")
    print(f"  First 4 bytes: {r.content[:4]}")
    if r.content[:2] in (b'II', b'MM'):
        print("  ✅ TIFF header detected!")
    elif b'html' in r.content[:200].lower() or b'json' in ct.lower().encode():
        print("  ❌ Got HTML/JSON error instead of image")
        print(f"  Body preview: {r.content[:300].decode('utf-8', errors='replace')}")
    else:
        print(f"  ⚠️  Unknown format. Body preview: {r.content[:100]}")
except Exception as e:
    print(f"  ERROR: {e}")

# ------------------------------------------------------------------
# Test 4: Export as JPGPNG (f=json) - baseline that should work
# ------------------------------------------------------------------
print("\n[Test 4] Export as jpgpng (f=json) - baseline...")
try:
    params = {
        "bbox": BBOX,
        "bboxSR": "102100",
        "imageSR": "102100",
        "size": "256,256",
        "format": "jpgpng",
        "f": "json",
    }
    r = requests.get(EXPORT, params=params, timeout=30)
    print(f"  Status: {r.status_code}")
    try:
        j = r.json()
        print(f"  Response: {json.dumps(j, indent=2)[:1000]}")
    except:
        print(f"  Response (text): {r.text[:500]}")
except Exception as e:
    print(f"  ERROR: {e}")

# ------------------------------------------------------------------
# Test 5: Direct tile fetch at zoom 20
# ------------------------------------------------------------------
print("\n[Test 5] Direct tile fetch (zoom 20)...")
try:
    tile_url = f"{BASE}/tile/20/365200/167900"
    r = requests.get(tile_url, timeout=30)
    ct = r.headers.get("Content-Type", "?")
    print(f"  URL: {tile_url}")
    print(f"  Status: {r.status_code}")
    print(f"  Content-Type: {ct}")
    print(f"  Content-Length: {len(r.content)} bytes")
    if r.content[:2] == b'\xff\xd8':
        print("  ✅ JPEG tile received!")
    elif r.content[:4] == b'\x89PNG':
        print("  ✅ PNG tile received!")
    elif r.content[:2] in (b'II', b'MM'):
        print("  ✅ TIFF tile received!")
    else:
        print(f"  ⚠️  Unknown. First bytes: {r.content[:10]}")
except Exception as e:
    print(f"  ERROR: {e}")

# ------------------------------------------------------------------
# Test 6: Export as TIFF with different params (no bandIds, no pixelType)
# ------------------------------------------------------------------
print("\n[Test 6] Export as TIFF (minimal params, f=image)...")
try:
    params = {
        "bbox": BBOX,
        "bboxSR": "102100",
        "imageSR": "102100",
        "size": "256,256",
        "format": "tiff",
        "f": "image",
    }
    r = requests.get(EXPORT, params=params, timeout=30)
    ct = r.headers.get("Content-Type", "?")
    print(f"  Status: {r.status_code}")
    print(f"  Content-Type: {ct}")
    print(f"  Content-Length: {len(r.content)} bytes")
    if r.content[:2] in (b'II', b'MM'):
        print("  ✅ TIFF header detected!")
    elif b'html' in r.content[:200].lower():
        print("  ❌ Got HTML error")
    else:
        print(f"  First 10 bytes: {r.content[:10]}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n" + "=" * 60)
print("Done! Paste this entire output back to Claude.")
print("=" * 60)
