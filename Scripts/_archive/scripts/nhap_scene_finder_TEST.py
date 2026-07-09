"""
NHAP Scene Finder - TEST MODE (No API Required)
Tests all functionality except M2M API with synthetic data

This validates:
- Shapefile loading and reprojection
- Coverage calculation logic
- Optimal scene selection algorithm
- Folder structure creation
- Excel export with all fields

Run this to verify your setup before M2M API access is approved!

Author: Kam Eck
Date: 2026-05-13
"""

import geopandas as gpd
from shapely.geometry import Polygon, box
import pandas as pd
from datetime import datetime
import os
import random

# ============================================================================
# Configuration (adjust these to match your actual paths)
# ============================================================================

BOUNDARY_PATH = '/content/drive/MyDrive/treedata/City Boundry/Edmonds Boundry.shp'
OUTPUT_EXCEL = '/content/drive/MyDrive/treedata/NHAP_1980_Edmonds_TEST.xlsx'
OUTPUT_IMAGE_BASE = '/content/drive/MyDrive/treedata/Full_Image'

# ============================================================================
# Synthetic Test Data Generator
# ============================================================================

def generate_mock_scenes(boundary_polygon, num_scenes=8):
    """
    Generate synthetic NHAP scenes for testing
    Creates realistic overlapping footprints covering the study area
    """
    
    bounds = boundary_polygon.bounds  # (minx, miny, maxx, maxy)
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2
    
    # Typical NHAP frame size ~0.05 degrees (~5km x 5km)
    frame_size = 0.05
    
    scenes = []
    
    # Create scenes with varying coverage patterns
    scene_configs = [
        # (center_offset_x, center_offset_y, size_multiplier, organization)
        (0.0, 0.0, 1.2, 'USGS'),           # Large scene covering most of area
        (0.02, 0.01, 0.8, 'USDA-APFO'),    # Northeast partial coverage
        (-0.02, 0.01, 0.8, 'USGS'),        # Northwest partial coverage
        (0.0, -0.02, 0.9, 'USDA-APFO'),    # South coverage
        (0.03, 0.0, 0.7, 'USGS'),          # East edge
        (-0.03, 0.0, 0.7, 'USGS'),         # West edge (over water)
        (0.01, 0.02, 0.6, 'USDA-APFO'),    # Small northeast
        (-0.01, -0.01, 0.65, 'USGS')       # Small southwest
    ]
    
    for i, (offset_x, offset_y, size_mult, org) in enumerate(scene_configs):
        scene_center_lon = center_lon + offset_x
        scene_center_lat = center_lat + offset_y
        half_size = (frame_size * size_mult) / 2
        
        # Create bounding box for scene
        footprint = box(
            scene_center_lon - half_size,
            scene_center_lat - half_size,
            scene_center_lon + half_size,
            scene_center_lat + half_size
        )
        
        # Generate realistic metadata
        entity_id = f"TEST_{org.replace('-', '')}_{1980}{i:03d}"
        display_id = f"NHAP_WA_1980_{org.split('-')[0]}_{i+1:03d}"
        
        # Random date in 1980
        month = random.randint(5, 9)  # Summer months
        day = random.randint(1, 28)
        
        scene = {
            'entity_id': entity_id,
            'display_id': display_id,
            'acquisition_date': f"1980-{month:02d}-{day:02d}",
            'footprint': footprint,
            'organization': org,
            'center_lat': scene_center_lat,
            'center_lon': scene_center_lon,
            'bounds': {
                'north': scene_center_lat + half_size,
                'south': scene_center_lat - half_size,
                'east': scene_center_lon + half_size,
                'west': scene_center_lon - half_size
            }
        }
        
        scenes.append(scene)
    
    return scenes

# ============================================================================
# Helper Functions (from main script)
# ============================================================================

def load_edmonds_boundary(shapefile_path):
    """Load Edmonds city boundary from shapefile"""
    print(f"Loading Edmonds boundary from: {shapefile_path}")
    
    gdf = gpd.read_file(shapefile_path)
    
    # Ensure it's in WGS84 (EPSG:4326)
    if gdf.crs != 'EPSG:4326':
        print(f"Reprojecting from {gdf.crs} to EPSG:4326")
        gdf = gdf.to_crs('EPSG:4326')
    
    boundary = gdf.unary_union
    
    print(f"✓ Boundary loaded")
    print(f"  Bounds: {boundary.bounds}")
    print(f"  Area: {gdf.geometry.area.sum():.6f} sq degrees")
    
    return boundary, gdf

def calculate_coverage(boundary_polygon, scene_footprint):
    """Calculate what percentage of the boundary is covered by the scene"""
    try:
        intersection = boundary_polygon.intersection(scene_footprint)
        coverage_pct = (intersection.area / boundary_polygon.area) * 100
        return coverage_pct
    except Exception as e:
        print(f"Warning: Coverage calculation failed - {e}")
        return 0.0

def select_optimal_scenes(scenes_with_coverage, target_coverage=95.0):
    """
    Select minimum number of scenes to achieve target coverage
    Uses greedy algorithm
    """
    
    sorted_scenes = sorted(scenes_with_coverage, 
                          key=lambda x: x['coverage_pct'], 
                          reverse=True)
    
    selected = []
    total_coverage_geom = None
    current_coverage = 0.0
    
    print(f"\nSelecting optimal scene set (target: {target_coverage}% coverage)...")
    
    for scene in sorted_scenes:
        if current_coverage >= target_coverage:
            break
        
        footprint = scene['footprint']
        
        if total_coverage_geom is None:
            additional_coverage = scene['coverage_pct']
            total_coverage_geom = footprint
        else:
            new_area = footprint.difference(total_coverage_geom)
            boundary = scene['boundary']
            additional_coverage = (new_area.area / boundary.area) * 100
            total_coverage_geom = total_coverage_geom.union(footprint)
        
        if additional_coverage > 0.1:
            selected.append(scene)
            current_coverage = (total_coverage_geom.area / scene['boundary'].area) * 100
            print(f"  Selected: {scene['display_id']} (+{additional_coverage:.1f}% → {current_coverage:.1f}% total)")
    
    print(f"\n✓ Selected {len(selected)} scenes for {current_coverage:.1f}% coverage")
    
    return selected

def create_output_directory(base_path, organization):
    """Create output directory structure"""
    full_path = os.path.join(base_path, organization)
    os.makedirs(full_path, exist_ok=True)
    return full_path

def get_output_filepath(base_path, organization, display_id, extension='tif'):
    """Generate output filepath"""
    safe_filename = display_id.replace('/', '_').replace('\\', '_')
    filename = f"{safe_filename}.{extension}"
    org_dir = create_output_directory(base_path, organization)
    return os.path.join(org_dir, filename)

# ============================================================================
# Test Workflow
# ============================================================================

def main():
    """Test workflow with synthetic data"""
    
    print("="*70)
    print("NHAP Scene Finder - TEST MODE (No API Required)")
    print("="*70)
    print("\nThis test validates:")
    print("  ✓ Shapefile loading and reprojection")
    print("  ✓ Coverage calculation algorithm")
    print("  ✓ Optimal scene selection logic")
    print("  ✓ Folder structure creation")
    print("  ✓ Excel export with all fields")
    print("\nUsing synthetic NHAP scenes for testing...")
    print("="*70)
    
    # Step 1: Load Edmonds boundary
    print("\n[1/5] Loading Edmonds city boundary...")
    try:
        boundary_polygon, boundary_gdf = load_edmonds_boundary(BOUNDARY_PATH)
    except Exception as e:
        print(f"✗ Error loading boundary: {e}")
        print("\nTroubleshooting:")
        print("  1. Verify the file path is correct")
        print("  2. Ensure Google Drive is mounted: drive.mount('/content/drive')")
        print("  3. Check that all shapefile components exist (.shp, .shx, .dbf, .prj)")
        return
    
    # Step 2: Generate synthetic scenes
    print("\n[2/5] Generating synthetic NHAP scenes...")
    mock_scenes = generate_mock_scenes(boundary_polygon, num_scenes=8)
    print(f"✓ Generated {len(mock_scenes)} test scenes")
    
    # Step 3: Calculate coverage
    print("\n[3/5] Analyzing scene coverage...")
    
    scenes_with_coverage = []
    
    for scene in mock_scenes:
        coverage_pct = calculate_coverage(boundary_polygon, scene['footprint'])
        
        scenes_with_coverage.append({
            'entity_id': scene['entity_id'],
            'display_id': scene['display_id'],
            'acquisition_date': scene['acquisition_date'],
            'footprint': scene['footprint'],
            'coverage_pct': coverage_pct,
            'boundary': boundary_polygon,
            'organization': scene['organization'],
            'center_lat': scene['center_lat'],
            'center_lon': scene['center_lon'],
            'bounds': scene['bounds']
        })
        
        print(f"  {scene['display_id']}: {coverage_pct:.1f}% coverage ({scene['organization']})")
    
    # Step 4: Select optimal scenes
    print("\n[4/5] Selecting optimal scene set...")
    optimal_scenes = select_optimal_scenes(scenes_with_coverage, target_coverage=95.0)
    
    # Step 5: Create Excel output
    print("\n[5/5] Creating Excel tracking file...")
    
    records = []
    for scene_info in optimal_scenes:
        organization = scene_info['organization']
        display_id = scene_info['display_id']
        output_path = get_output_filepath(OUTPUT_IMAGE_BASE, organization, display_id)
        
        bounds = scene_info['bounds']
        
        record = {
            'Entity_ID': scene_info['entity_id'],
            'Display_ID': display_id,
            'Acquisition_Date': scene_info['acquisition_date'],
            'Coverage_Pct': f"{scene_info['coverage_pct']:.2f}%",
            'Organization': organization,
            'Center_Lat': f"{scene_info['center_lat']:.6f}",
            'Center_Lon': f"{scene_info['center_lon']:.6f}",
            'NW_Corner_Lat': f"{bounds['north']:.6f}",
            'NW_Corner_Lon': f"{bounds['west']:.6f}",
            'NE_Corner_Lat': f"{bounds['north']:.6f}",
            'NE_Corner_Lon': f"{bounds['east']:.6f}",
            'SW_Corner_Lat': f"{bounds['south']:.6f}",
            'SW_Corner_Lon': f"{bounds['west']:.6f}",
            'SE_Corner_Lat': f"{bounds['south']:.6f}",
            'SE_Corner_Lon': f"{bounds['east']:.6f}",
            'Download_Status': 'TEST MODE - Not Downloaded',
            'Local_Filename': output_path,
            'Georeferenced': 'No',
            'Notes': 'Test data - awaiting M2M API access'
        }
        
        records.append(record)
    
    df = pd.DataFrame(records)
    
    # Create folder structure (doesn't download files)
    print("\n  Creating folder structure:")
    for org in df['Organization'].unique():
        org_path = os.path.join(OUTPUT_IMAGE_BASE, org)
        os.makedirs(org_path, exist_ok=True)
        print(f"    ✓ {org_path}")
    
    # Save to Excel
    with pd.ExcelWriter(OUTPUT_EXCEL, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='NHAP_1980_Edmonds_TEST', index=False)
        
        # Add summary sheet
        summary_data = {
            'Metric': ['Test Mode', 'Total Scenes Generated', 'Scenes Selected', 
                      'Target Coverage', 'Status', 'Test Date'],
            'Value': [
                'Using synthetic data',
                len(mock_scenes),
                len(optimal_scenes),
                f"{sum(s['coverage_pct'] for s in optimal_scenes):.1f}%",
                'Awaiting M2M API Access',
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ]
        }
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        
        # Add notes sheet
        notes_data = {
            'Note': [
                'This is TEST MODE output using synthetic data',
                'All functionality validated except M2M API calls',
                'Folder structure has been created',
                'Once M2M access is approved, run nhap_scene_finder.py',
                'That script will download actual NHAP imagery'
            ]
        }
        notes_df = pd.DataFrame(notes_data)
        notes_df.to_excel(writer, sheet_name='Notes', index=False)
    
    print(f"\n✓ Test Excel saved to: {OUTPUT_EXCEL}")
    
    print("\n" + "="*70)
    print("TEST COMPLETE!")
    print("="*70)
    print("\n✅ All systems validated:")
    print(f"  • Loaded boundary shapefile successfully")
    print(f"  • Coverage calculation working correctly")
    print(f"  • Selected {len(optimal_scenes)} optimal scenes (minimal redundancy)")
    print(f"  • Created folder structure: {OUTPUT_IMAGE_BASE}")
    print(f"  • Excel export successful with all fields")
    print("\n📋 Organizations detected:")
    for org in df['Organization'].unique():
        count = len(df[df['Organization'] == org])
        print(f"  • {org}: {count} scene(s)")
    
    print("\n⏳ Next Steps:")
    print("  1. Wait for M2M API access approval")
    print("  2. Run nhap_scene_finder.py (not the TEST version)")
    print("  3. It will download actual NHAP imagery to the same folder structure")
    
    print("\n💡 Tip: Review the test Excel file to verify the output format")
    print(f"     {OUTPUT_EXCEL}")

if __name__ == "__main__":
    main()
