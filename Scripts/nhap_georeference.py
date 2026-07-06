"""
NHAP Imagery Georeferencing Script
Applies Ground Control Points (GCPs) from corner coordinates to un-georeferenced TIFFs

This script:
1. Reads corner coordinates from Excel tracking file or manual input
2. Applies GCPs to raw TIFF images using gdal_translate
3. Warps images to create properly georeferenced GeoTIFFs
4. Supports batch processing of multiple scenes

Author: Kam Eck
Date: 2026-05-13
"""

import subprocess
import os
import pandas as pd
from pathlib import Path
import sys

# ============================================================================
# Configuration
# ============================================================================

# Input/Output paths (adjust for your setup)
TRACKING_EXCEL = '/content/drive/MyDrive/treedata/NHAP_1980_Edmonds_Tracking.xlsx'
INPUT_IMAGE_BASE = '/content/drive/MyDrive/treedata/Full_Image'
OUTPUT_GEOREF_BASE = '/content/drive/MyDrive/treedata/Georeferenced'

# Coordinate Reference System for output
# Options: 'EPSG:4326' (WGS84), 'EPSG:2927' (State Plane WA North), 'EPSG:2926' (State Plane WA South)
OUTPUT_CRS = 'EPSG:2927'  # State Plane Washington North (feet)

# Resampling method for warping
# Options: 'bilinear', 'cubic', 'cubicspline', 'lanczos', 'near'
RESAMPLING = 'cubic'  # Good for aerial photography

# Compression for output GeoTIFF
# Options: 'LZW', 'DEFLATE', 'PACKBITS', 'JPEG', 'NONE'
COMPRESSION = 'LZW'

# ============================================================================
# Helper Functions
# ============================================================================

def check_gdal_installed():
    """Check if GDAL tools are available"""
    try:
        subprocess.run(['gdalinfo', '--version'], 
                      capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def dms_to_decimal(degrees, minutes, seconds, direction):
    """Convert DMS (Degrees Minutes Seconds) to decimal degrees"""
    decimal = degrees + minutes/60 + seconds/3600
    if direction in ['S', 'W']:
        decimal = -decimal
    return decimal

def parse_corner_coordinate(coord_str):
    """
    Parse corner coordinate string from EarthExplorer metadata
    Examples: 
      "47°53'43.66\"N" -> 47.89546
      "122°26'01.14\"W" -> -122.43365
    """
    import re
    
    # Try decimal format first (e.g., "47.89546")
    try:
        return float(coord_str)
    except ValueError:
        pass
    
    # Parse DMS format
    pattern = r"(\d+)°(\d+)'([\d.]+)\"([NSEW])"
    match = re.match(pattern, coord_str.strip())
    
    if match:
        degrees = int(match.group(1))
        minutes = int(match.group(2))
        seconds = float(match.group(3))
        direction = match.group(4)
        return dms_to_decimal(degrees, minutes, seconds, direction)
    
    raise ValueError(f"Could not parse coordinate: {coord_str}")

def apply_gcps_to_image(input_tiff, output_gcp_tiff, corners):
    """
    Apply Ground Control Points to an image using gdal_translate
    
    Args:
        input_tiff: Path to un-georeferenced TIFF
        output_gcp_tiff: Path for output TIFF with GCPs
        corners: Dict with keys 'nw_lat', 'nw_lon', 'ne_lat', 'ne_lon', etc.
    
    Returns:
        True if successful, False otherwise
    """
    
    # Get image dimensions to determine pixel coordinates for corners
    info_cmd = ['gdalinfo', input_tiff]
    result = subprocess.run(info_cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error getting image info: {result.stderr}")
        return False
    
    # Parse image size from gdalinfo output
    width = None
    height = None
    for line in result.stdout.split('\n'):
        if 'Size is' in line:
            parts = line.split()
            width = int(parts[2].rstrip(','))
            height = int(parts[3])
            break
    
    if width is None or height is None:
        print(f"Could not determine image dimensions")
        return False
    
    print(f"  Image size: {width} x {height} pixels")
    
    # Define GCPs: pixel, line, easting, northing
    # Corners in image pixel coordinates:
    #   NW = (0, 0)           NE = (width, 0)
    #   SW = (0, height)      SE = (width, height)
    
    gcps = [
        # Northwest corner
        f"-gcp 0 0 {corners['nw_lon']} {corners['nw_lat']}",
        # Northeast corner  
        f"-gcp {width} 0 {corners['ne_lon']} {corners['ne_lat']}",
        # Southeast corner
        f"-gcp {width} {height} {corners['se_lon']} {corners['se_lat']}",
        # Southwest corner
        f"-gcp 0 {height} {corners['sw_lon']} {corners['sw_lat']}"
    ]
    
    # Build gdal_translate command
    cmd = [
        'gdal_translate',
        '-a_srs', 'EPSG:4326',  # GCPs are in WGS84
    ] + gcps + [
        '-co', 'TILED=YES',
        input_tiff,
        output_gcp_tiff
    ]
    
    print(f"  Applying GCPs...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"  Error applying GCPs: {result.stderr}")
        return False
    
    print(f"  ✓ GCPs applied")
    return True

def warp_to_georeferenced(gcp_tiff, output_georef_tiff, target_crs='EPSG:2927', 
                          resampling='cubic', compression='LZW'):
    """
    Warp image with GCPs to create properly georeferenced GeoTIFF
    
    Args:
        gcp_tiff: Path to TIFF with GCPs
        output_georef_tiff: Path for final georeferenced output
        target_crs: Target coordinate reference system
        resampling: Resampling method
        compression: Output compression
    
    Returns:
        True if successful, False otherwise
    """
    
    cmd = [
        'gdalwarp',
        '-t_srs', target_crs,
        '-r', resampling,
        '-co', f'COMPRESS={compression}',
        '-co', 'TILED=YES',
        '-co', 'BIGTIFF=IF_SAFER',
        gcp_tiff,
        output_georef_tiff
    ]
    
    print(f"  Warping to {target_crs}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"  Error warping image: {result.stderr}")
        return False
    
    # Get output file size
    size_mb = os.path.getsize(output_georef_tiff) / (1024 * 1024)
    print(f"  ✓ Georeferenced: {size_mb:.1f} MB")
    
    return True

# ============================================================================
# Main Georeferencing Functions
# ============================================================================

def georeference_single_scene(scene_data, input_dir, output_dir, keep_gcp_file=False):
    """
    Georeference a single scene
    
    Args:
        scene_data: Dict or pandas Series with scene metadata
        input_dir: Directory containing input TIFF
        output_dir: Directory for output georeferenced TIFF
        keep_gcp_file: If True, keep intermediate GCP file
    
    Returns:
        True if successful, False otherwise
    """
    
    display_id = scene_data.get('Display_ID') or scene_data.get('display_id')
    organization = scene_data.get('Organization') or scene_data.get('organization')
    
    print(f"\n{'='*70}")
    print(f"Georeferencing: {display_id}")
    print(f"{'='*70}")
    
    # Construct file paths
    input_file = os.path.join(input_dir, organization, f"{display_id}.tif")
    
    # Check if input file exists
    if not os.path.exists(input_file):
        print(f"✗ Input file not found: {input_file}")
        return False
    
    # Create output directory structure
    output_org_dir = os.path.join(output_dir, organization)
    os.makedirs(output_org_dir, exist_ok=True)
    
    # Output files
    gcp_file = os.path.join(output_org_dir, f"{display_id}_gcp.tif")
    georef_file = os.path.join(output_org_dir, f"{display_id}_georef.tif")
    
    # Extract corner coordinates
    try:
        corners = {
            'nw_lat': float(scene_data.get('NW_Corner_Lat')),
            'nw_lon': float(scene_data.get('NW_Corner_Lon')),
            'ne_lat': float(scene_data.get('NE_Corner_Lat')),
            'ne_lon': float(scene_data.get('NE_Corner_Lon')),
            'se_lat': float(scene_data.get('SE_Corner_Lat')),
            'se_lon': float(scene_data.get('SE_Corner_Lon')),
            'sw_lat': float(scene_data.get('SW_Corner_Lat')),
            'sw_lon': float(scene_data.get('SW_Corner_Lon'))
        }
        
        print(f"Corner coordinates:")
        print(f"  NW: {corners['nw_lat']:.5f}, {corners['nw_lon']:.5f}")
        print(f"  NE: {corners['ne_lat']:.5f}, {corners['ne_lon']:.5f}")
        print(f"  SE: {corners['se_lat']:.5f}, {corners['se_lon']:.5f}")
        print(f"  SW: {corners['sw_lat']:.5f}, {corners['sw_lon']:.5f}")
        
    except (KeyError, ValueError, TypeError) as e:
        print(f"✗ Error extracting corner coordinates: {e}")
        return False
    
    # Step 1: Apply GCPs
    if not apply_gcps_to_image(input_file, gcp_file, corners):
        return False
    
    # Step 2: Warp to create georeferenced image
    success = warp_to_georeferenced(gcp_file, georef_file, 
                                    target_crs=OUTPUT_CRS,
                                    resampling=RESAMPLING,
                                    compression=COMPRESSION)
    
    # Clean up intermediate GCP file if not needed
    if not keep_gcp_file and os.path.exists(gcp_file):
        os.remove(gcp_file)
        print(f"  Removed intermediate GCP file")
    
    if success:
        print(f"\n✓ SUCCESS: {georef_file}")
    
    return success

def georeference_from_excel(excel_path, input_dir, output_dir):
    """
    Georeference all scenes listed in Excel tracking file
    
    Args:
        excel_path: Path to Excel tracking file
        input_dir: Base directory containing input TIFFs
        output_dir: Base directory for output georeferenced TIFFs
    
    Returns:
        Number of successfully georeferenced scenes
    """
    
    print("="*70)
    print("NHAP Batch Georeferencing from Excel")
    print("="*70)
    
    # Read Excel file
    print(f"\nReading Excel: {excel_path}")
    df = pd.read_excel(excel_path, sheet_name=0)
    
    print(f"Found {len(df)} scenes in tracking file")
    
    # Filter for downloaded scenes only
    downloaded = df[df['Download_Status'] == 'Downloaded']
    print(f"  {len(downloaded)} scenes marked as 'Downloaded'")
    
    if len(downloaded) == 0:
        print("\n⚠️  No downloaded scenes to georeference!")
        print("   Download imagery first using nhap_scene_finder.py")
        return 0
    
    # Georeference each scene
    success_count = 0
    failed_scenes = []
    
    for idx, row in downloaded.iterrows():
        try:
            if georeference_single_scene(row, input_dir, output_dir):
                success_count += 1
            else:
                failed_scenes.append(row['Display_ID'])
        except Exception as e:
            print(f"\n✗ Unexpected error: {e}")
            failed_scenes.append(row['Display_ID'])
    
    # Summary
    print("\n" + "="*70)
    print("GEOREFERENCING COMPLETE")
    print("="*70)
    print(f"✓ Successfully georeferenced: {success_count}/{len(downloaded)} scenes")
    
    if failed_scenes:
        print(f"\n✗ Failed scenes:")
        for scene in failed_scenes:
            print(f"    {scene}")
    
    return success_count

# ============================================================================
# Test Mode with Manual Coordinates
# ============================================================================

def test_single_file(input_tiff, corners_dict):
    """
    Test georeferencing on a single file with manually provided corners
    
    Args:
        input_tiff: Path to input TIFF
        corners_dict: Dictionary with corner coordinates
    
    Example:
        corners = {
            'nw_lat': 47.89546, 'nw_lon': -122.43365,
            'ne_lat': 47.89399, 'ne_lon': -122.18901,
            'se_lat': 47.72946, 'se_lon': -122.19156,
            'sw_lat': 47.73092, 'sw_lon': -122.43544
        }
        test_single_file('NB1NHAP800100076.tif', corners)
    """
    
    print("="*70)
    print("NHAP Georeferencing - TEST MODE")
    print("="*70)
    
    # Create scene data dict
    scene_data = {
        'Display_ID': Path(input_tiff).stem,
        'Organization': 'USGS',
        **{k.upper().replace('_', '_CORNER_'): v 
           for k, v in corners_dict.items() 
           if k.endswith('_lat') or k.endswith('_lon')}
    }
    
    # Rename keys to match expected format
    scene_data['NW_Corner_Lat'] = corners_dict['nw_lat']
    scene_data['NW_Corner_Lon'] = corners_dict['nw_lon']
    scene_data['NE_Corner_Lat'] = corners_dict['ne_lat']
    scene_data['NE_Corner_Lon'] = corners_dict['ne_lon']
    scene_data['SE_Corner_Lat'] = corners_dict['se_lat']
    scene_data['SE_Corner_Lon'] = corners_dict['se_lon']
    scene_data['SW_Corner_Lat'] = corners_dict['sw_lat']
    scene_data['SW_Corner_Lon'] = corners_dict['sw_lon']
    
    # Get input directory
    input_dir = str(Path(input_tiff).parent)
    output_dir = os.path.join(input_dir, 'georeferenced_test')
    
    print(f"\nInput: {input_tiff}")
    print(f"Output: {output_dir}/USGS/")
    
    # Georeference
    success = georeference_single_scene(scene_data, input_dir, output_dir, keep_gcp_file=True)
    
    if success:
        output_file = os.path.join(output_dir, 'USGS', f"{scene_data['Display_ID']}_georef.tif")
        gcp_file = os.path.join(output_dir, 'USGS', f"{scene_data['Display_ID']}_gcp.tif")
        
        print("\n" + "="*70)
        print("✓ TEST SUCCESSFUL!")
        print("="*70)
        print(f"\nOutput files created:")
        print(f"  GCP file: {gcp_file}")
        print(f"  Georeferenced: {output_file}")
        print(f"\nVerify with: gdalinfo {output_file}")
    else:
        print("\n✗ TEST FAILED")
    
    return success

# ============================================================================
# Main
# ============================================================================

def main():
    """Main execution"""
    
    # Check GDAL installation
    if not check_gdal_installed():
        print("ERROR: GDAL tools not found!")
        print("\nInstall GDAL:")
        print("  Ubuntu: sudo apt-get install gdal-bin")
        print("  Mac: brew install gdal")
        print("  Conda: conda install -c conda-forge gdal")
        sys.exit(1)
    
    # Check if running in batch mode or test mode
    if len(sys.argv) > 1:
        # Test mode with command line arguments
        print("Test mode not implemented via CLI yet")
        print("Use test_single_file() function in Python")
        sys.exit(1)
    else:
        # Batch mode from Excel
        success = georeference_from_excel(
            TRACKING_EXCEL,
            INPUT_IMAGE_BASE,
            OUTPUT_GEOREF_BASE
        )
        
        sys.exit(0 if success > 0 else 1)

if __name__ == "__main__":
    main()
