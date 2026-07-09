"""
Google Colab Test Cell - Georeference NB1NHAP800100076.tif
o
Run this in Google Colab to test georeferencing with your real NHAP scene

Prerequisites:
1. Upload NB1NHAP800100076.tif to Colab
2. Have the nhap_georeference.py script available
"""

# ============================================================================
# CELL 1: Install GDAL
# ============================================================================
!apt-get update -qq
!apt-get install -y gdal-bin python3-gdal
!pip install -q GDAL==$(gdal-config --version)

print("✓ GDAL installed")

# ============================================================================
# CELL 2: Test Georeferencing with Your NHAP Scene
# ============================================================================

import subprocess
import os
from pathlib import Path

print("="*70)
print("NHAP Georeferencing Test - NB1NHAP800100076.tif")
print("="*70)

# Scene metadata (from your EarthExplorer metadata)
input_file = '/content/drive/MyDrive/treedata/NB1NHAP800100076.tif'  # Adjust path if needed
corners = {
    'nw_lat': 47.89546,  'nw_lon': -122.43365,
    'ne_lat': 47.89399,  'ne_lon': -122.18901,
    'se_lat': 47.72946,  'se_lon': -122.19156,
    'sw_lat': 47.73092,  'sw_lon': -122.43544
}

# Output files
output_dir = '/content/drive/MyDrive/treedata/Georeferenced_Test'
os.makedirs(output_dir, exist_ok=True)

gcp_file = f"{output_dir}/NB1NHAP800100076_gcp.tif"
georef_file = f"{output_dir}/NB1NHAP800100076_georef.tif"

print(f"\nInput: {input_file}")
print(f"Output: {georef_file}")

# ============================================================================
# Step 1: Get image dimensions
# ============================================================================
print("\n[Step 1/3] Getting image info...")
result = subprocess.run(['gdalinfo', input_file], 
                       capture_output=True, text=True)

width = None
height = None
for line in result.stdout.split('\n'):
    if 'Size is' in line:
        parts = line.split()
        width = int(parts[2].rstrip(','))
        height = int(parts[3])
        break

print(f"  Image size: {width} x {height} pixels")

# ============================================================================
# Step 2: Apply GCPs using gdal_translate
# ============================================================================
print("\n[Step 2/3] Applying Ground Control Points...")

# Define GCPs: -gcp pixel line easting northing
# Corners: NW=(0,0), NE=(width,0), SE=(width,height), SW=(0,height)
cmd = [
    'gdal_translate',
    '-a_srs', 'EPSG:4326',  # GCPs are in WGS84
    '-gcp', '0', '0', str(corners['nw_lon']), str(corners['nw_lat']),
    '-gcp', str(width), '0', str(corners['ne_lon']), str(corners['ne_lat']),
    '-gcp', str(width), str(height), str(corners['se_lon']), str(corners['se_lat']),
    '-gcp', '0', str(height), str(corners['sw_lon']), str(corners['sw_lat']),
    '-co', 'TILED=YES',
    input_file,
    gcp_file
]

result = subprocess.run(cmd, capture_output=True, text=True)

if result.returncode == 0:
    print("  ✓ GCPs applied successfully")
else:
    print(f"  ✗ Error: {result.stderr}")
    exit(1)

# ============================================================================
# Step 3: Warp to georeferenced GeoTIFF
# ============================================================================
print("\n[Step 3/3] Warping to State Plane Washington North...")

cmd = [
    'gdalwarp',
    '-t_srs', 'EPSG:2927',  # State Plane Washington North (feet)
    '-r', 'cubic',          # Cubic resampling for quality
    '-co', 'COMPRESS=LZW',  # Compress output
    '-co', 'TILED=YES',
    '-co', 'BIGTIFF=IF_SAFER',
    gcp_file,
    georef_file
]

result = subprocess.run(cmd, capture_output=True, text=True)

if result.returncode == 0:
    size_mb = os.path.getsize(georef_file) / (1024 * 1024)
    print(f"  ✓ Georeferenced: {size_mb:.1f} MB")
else:
    print(f"  ✗ Error: {result.stderr}")
    exit(1)

# ============================================================================
# Step 4: Verify output
# ============================================================================
print("\n[Verification] Checking georeferenced output...")

result = subprocess.run(['gdalinfo', georef_file], 
                       capture_output=True, text=True)

# Extract key info
for line in result.stdout.split('\n'):
    if 'Coordinate System' in line or 'Origin' in line or 'Pixel Size' in line:
        print(f"  {line.strip()}")

print("\n" + "="*70)
print("✓ GEOREFERENCING TEST COMPLETE!")
print("="*70)
print(f"\nOutput files:")
print(f"  GCP intermediate: {gcp_file}")
print(f"  Georeferenced:    {georef_file}")
print(f"\nYou can now load {georef_file} into QGIS or ArcGIS")
print("It should align perfectly with your Edmonds boundary shapefile!")

# ============================================================================
# Optional: Visualize extent in lat/lon
# ============================================================================
print("\n[Optional] Getting geographic extent...")
result = subprocess.run(['gdalinfo', '-json', georef_file], 
                       capture_output=True, text=True)

import json
try:
    info = json.loads(result.stdout)
    if 'wgs84Extent' in info:
        extent = info['wgs84Extent']['coordinates'][0]
        print("  WGS84 Extent (lon, lat):")
        for i, coord in enumerate(extent):
            corners_names = ['SW', 'SE', 'NE', 'NW', 'SW (closed)']
            print(f"    {corners_names[i]}: {coord[0]:.5f}, {coord[1]:.5f}")
except:
    print("  (Could not parse extent)")

print("\nNext: Use this workflow in batch mode for all downloaded NHAP scenes!")
