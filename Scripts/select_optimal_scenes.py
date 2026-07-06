"""
Select Optimal Scenes Based on Edmonds Coverage
Queries spatial footprints and selects 1-3 best scenes per year

Input: M2M API scene data
Output: Prioritized download list + coverage map
"""

import requests
import pandas as pd
import geopandas as gpd
import getpass
from shapely.geometry import box, Polygon
from shapely.ops import unary_union
from datetime import datetime
import folium
from collections import defaultdict

# ============================================================================
# Configuration
# ============================================================================

BOUNDARY_FILE = '/content/drive/MyDrive/treedata/City Boundry/Edmonds Boundry.shp'
OUTPUT_EXCEL = '/content/drive/MyDrive/treedata/Full_Image/USGS/Edmonds_Optimal_Scenes.xlsx'
OUTPUT_MAP = '/content/drive/MyDrive/treedata/Full_Image/USGS/Edmonds_Coverage_Map.html'
M2M_API_URL = 'https://m2m.cr.usgs.gov/api/api/json/stable/'

# Edmonds bounding box
EDMONDS_BBOX = {
    'west': -122.40,
    'south': 47.78,
    'east': -122.32,
    'north': 47.86
}

# Datasets to search
AERIAL_DATASETS = [
    'NHAP',
    'NAPP', 
    'NAIP',
    'AERIAL_COMBIN',
    'HIGH_RES_ORTHO'
]

# ============================================================================
# M2M API Class
# ============================================================================

class USGSM2M:
    def __init__(self, username, token):
        self.api_url = M2M_API_URL
        self.session = requests.Session()
        self.api_key = None
        self.login(username, token)
    
    def login(self, username, token):
        """Authenticate"""
        url = f"{self.api_url}login-token"
        payload = {"username": username, "token": token}
        headers = {"Content-Type": "application/json"}
        
        response = self.session.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            self.api_key = result.get('data')
            print("✓ Logged in")
            return self.api_key
        else:
            raise Exception(f"Login failed: {response.status_code}")
    
    def search_scenes_with_footprints(self, dataset):
        """Search scenes and get spatial footprints"""
        url = f"{self.api_url}scene-search"
        
        payload = {
            "datasetName": dataset,
            "maxResults": 250,  # Increased limit
            "startingNumber": 1,
            "sceneFilter": {
                "spatialFilter": {
                    "filterType": "mbr",
                    "lowerLeft": {
                        "latitude": EDMONDS_BBOX['south'],
                        "longitude": EDMONDS_BBOX['west']
                    },
                    "upperRight": {
                        "latitude": EDMONDS_BBOX['north'],
                        "longitude": EDMONDS_BBOX['east']
                    }
                }
            }
        }
        
        headers = {"X-Auth-Token": self.api_key}
        response = self.session.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            return result.get('data', {}).get('results', [])
        
        return []
    
    def logout(self):
        """Logout"""
        url = f"{self.api_url}logout"
        headers = {"X-Auth-Token": self.api_key}
        self.session.post(url, headers=headers)

# ============================================================================
# Footprint Analysis
# ============================================================================

def parse_scene_footprint(scene):
    """Extract spatial footprint from scene metadata"""
    
    # spatialCoverage is a GeoJSON Polygon with coordinates
    if 'spatialCoverage' in scene and scene['spatialCoverage']:
        try:
            spatial = scene['spatialCoverage']
            
            # GeoJSON format: {"type": "Polygon", "coordinates": [[[lon, lat], ...]]}
            if 'coordinates' in spatial:
                coords = spatial['coordinates']
                if coords and len(coords) > 0:
                    # First element is the outer ring
                    ring = coords[0]
                    return Polygon(ring)
        except Exception as e:
            print(f"    Warning: Failed to parse spatialCoverage: {e}")
    
    # Fallback to spatialBounds if available
    if 'spatialBounds' in scene and scene['spatialBounds']:
        try:
            bounds = scene['spatialBounds']
            
            # Extract coordinates with multiple fallback field names
            west = bounds.get('west') or bounds.get('longitudeMin')
            south = bounds.get('south') or bounds.get('latitudeMin')
            east = bounds.get('east') or bounds.get('longitudeMax')
            north = bounds.get('north') or bounds.get('latitudeMax')
            
            # Check all coordinates are present
            if all(coord is not None for coord in [west, south, east, north]):
                return box(float(west), float(south), float(east), float(north))
        except Exception as e:
            print(f"    Warning: Failed to parse spatialBounds: {e}")
    
    return None

def calculate_coverage(scene_footprint, edmonds_boundary):
    """Calculate percentage of Edmonds covered by scene"""
    if scene_footprint is None:
        return 0.0
    
    try:
        intersection = scene_footprint.intersection(edmonds_boundary)
        coverage = (intersection.area / edmonds_boundary.area) * 100
        return coverage
    except:
        return 0.0

def select_optimal_scenes(scenes_df, edmonds_boundary, max_per_year=3):
    """Select 1-3 scenes per year with best Edmonds coverage"""
    
    selected = []
    
    # Group by year
    for year in sorted(scenes_df['Year'].unique()):
        year_scenes = scenes_df[scenes_df['Year'] == year].copy()
        
        # Sort by coverage descending
        year_scenes = year_scenes.sort_values('Coverage_Percent', ascending=False)
        
        # Strategy: greedy selection for maximum cumulative coverage
        selected_for_year = []
        covered_area = None
        
        for idx, scene in year_scenes.iterrows():
            if len(selected_for_year) >= max_per_year:
                break
            
            scene_geom = scene['Geometry']
            
            if covered_area is None:
                # First scene - take highest coverage
                selected_for_year.append(scene)
                covered_area = scene_geom.intersection(edmonds_boundary)
            else:
                # Additional scenes - check if they add coverage
                new_coverage = scene_geom.intersection(edmonds_boundary)
                additional = new_coverage.difference(covered_area)
                
                additional_percent = (additional.area / edmonds_boundary.area) * 100
                
                # Add if provides >5% additional coverage
                if additional_percent > 5.0:
                    selected_for_year.append(scene)
                    covered_area = covered_area.union(new_coverage)
        
        selected.extend(selected_for_year)
        
        # Calculate final coverage for year
        if covered_area:
            final_coverage = (covered_area.area / edmonds_boundary.area) * 100
        else:
            final_coverage = 0.0
        
        print(f"  {year}: {len(selected_for_year)} scenes, {final_coverage:.1f}% coverage")
    
    return pd.DataFrame(selected)

# ============================================================================
# Visualization
# ============================================================================

def create_coverage_map(selected_scenes, edmonds_boundary):
    """Create interactive folium map showing scene footprints"""
    
    # Center on Edmonds
    center_lat = (EDMONDS_BBOX['south'] + EDMONDS_BBOX['north']) / 2
    center_lon = (EDMONDS_BBOX['west'] + EDMONDS_BBOX['east']) / 2
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=13)
    
    # Add Edmonds boundary
    folium.GeoJson(
        edmonds_boundary,
        name='Edmonds Boundary',
        style_function=lambda x: {'fillColor': 'transparent', 'color': 'red', 'weight': 3}
    ).add_to(m)
    
    # Color by dataset
    colors = {
        'NHAP': 'blue',
        'NAPP': 'green',
        'NAIP': 'purple',
        'AERIAL_COMBIN': 'orange',
        'HIGH_RES_ORTHO': 'darkblue'
    }
    
    # Add scene footprints
    for idx, scene in selected_scenes.iterrows():
        color = colors.get(scene['Dataset'], 'gray')
        
        folium.GeoJson(
            scene['Geometry'],
            style_function=lambda x, c=color: {'fillColor': c, 'color': c, 'weight': 2, 'fillOpacity': 0.3},
            tooltip=f"{scene['Dataset']} - {scene['Year']} - {scene['Display_ID']}<br>Coverage: {scene['Coverage_Percent']:.1f}%"
        ).add_to(m)
    
    folium.LayerControl().add_to(m)
    
    return m

# ============================================================================
# Main
# ============================================================================

def main():
    """Main selection workflow"""
    
    print("="*70)
    print("EDMONDS IMAGERY - OPTIMAL SCENE SELECTION")
    print("="*70)
    
    # Load Edmonds boundary
    print(f"\n[1/5] Loading Edmonds boundary...")
    edmonds_gdf = gpd.read_file(BOUNDARY_FILE)
    
    # Check and reproject to EPSG:4326 (WGS84) to match API coordinates
    original_crs = edmonds_gdf.crs
    print(f"  Original CRS: {original_crs}")
    
    if edmonds_gdf.crs != 'EPSG:4326':
        print(f"  Reprojecting to EPSG:4326 (WGS84)...")
        edmonds_gdf = edmonds_gdf.to_crs('EPSG:4326')
    
    edmonds_boundary = edmonds_gdf.geometry.iloc[0]
    print(f"  ✓ Boundary area: {edmonds_boundary.area:.6f} sq degrees")
    print(f"  ✓ Bounds: {edmonds_boundary.bounds}")
    
    # Login
    print(f"\n[2/5] Authenticating...")
    
    import sys
    user = None
    token = None
    
    if '__main__' in sys.modules:
        main_dict = sys.modules['__main__'].__dict__
        user = main_dict.get('username')
        token = main_dict.get('api_token')
    
    if user and token:
        print("  Using credentials from variables")
    else:
        user = input("USGS username: ")
        token = getpass.getpass("M2M Application Token: ")
    
    api = USGSM2M(user, token)
    
    # Query scenes with footprints
    print(f"\n[3/5] Querying scene footprints...")
    
    all_scenes = []
    
    for dataset in AERIAL_DATASETS:
        print(f"\n[{dataset}]")
        scenes = api.search_scenes_with_footprints(dataset)
        
        if not scenes:
            print(f"  ✗ No scenes found")
            continue
        
        print(f"  ✓ Retrieved {len(scenes)} scenes")
        print(f"  Processing spatial footprints...")
        
        # Track footprint success
        valid_footprints = 0
        no_footprint = 0
        
        # Process each scene
        for scene in scenes:
            # Extract metadata
            entity_id = scene.get('entityId')
            display_id = scene.get('displayId', 'N/A')
            
            # Parse date
            temporal = scene.get('temporalCoverage', {})
            start_date = temporal.get('startDate', 'Unknown')
            try:
                year = int(start_date.split('-')[0]) if start_date != 'Unknown' else None
            except:
                year = None
            
            if not year:
                continue
            
            # Parse footprint
            footprint = parse_scene_footprint(scene)
            
            if footprint is None:
                no_footprint += 1
                continue
            
            valid_footprints += 1
            
            # Calculate coverage
            coverage = calculate_coverage(footprint, edmonds_boundary)
            
            all_scenes.append({
                'Dataset': dataset,
                'Entity_ID': entity_id,
                'Display_ID': display_id,
                'Year': year,
                'Acquisition_Date': start_date,
                'Coverage_Percent': coverage,
                'Geometry': footprint
            })
        
        print(f"  ✓ Valid footprints: {valid_footprints}/{len(scenes)}")
        if no_footprint > 0:
            print(f"  ⚠ Scenes without footprints: {no_footprint}")
    
    scenes_df = pd.DataFrame(all_scenes)
    print(f"\n  Total valid scenes: {len(scenes_df)}")
    
    if len(scenes_df) == 0:
        print("\n✗ No scenes with valid footprints found!")
        print("Check that datasets have spatial metadata.")
        api.logout()
        return
    
    # Select optimal scenes
    print(f"\n[4/5] Selecting optimal scenes (1-3 per year)...")
    selected = select_optimal_scenes(scenes_df, edmonds_boundary, max_per_year=3)
    
    print(f"\n  ✓ Selected {len(selected)} scenes across {selected['Year'].nunique()} years")
    
    # Save results
    print(f"\n[5/5] Saving results...")
    
    # Excel export (drop geometry for Excel)
    selected_export = selected.drop(columns=['Geometry']).copy()
    
    with pd.ExcelWriter(OUTPUT_EXCEL, engine='openpyxl') as writer:
        selected_export.to_excel(writer, sheet_name='Optimal_Scenes', index=False)
        
        # Summary by year
        summary = selected_export.groupby('Year').agg({
            'Dataset': 'first',
            'Coverage_Percent': 'sum',
            'Entity_ID': 'count'
        }).rename(columns={'Entity_ID': 'Scene_Count'})
        summary.to_excel(writer, sheet_name='Year_Summary')
        
        # Summary by dataset
        dataset_summary = selected_export.groupby('Dataset').agg({
            'Year': ['min', 'max', 'count'],
            'Coverage_Percent': 'mean'
        })
        dataset_summary.to_excel(writer, sheet_name='Dataset_Summary')
    
    print(f"  ✓ Excel: {OUTPUT_EXCEL}")
    
    # Create map
    coverage_map = create_coverage_map(selected, edmonds_boundary)
    coverage_map.save(OUTPUT_MAP)
    print(f"  ✓ Map: {OUTPUT_MAP}")
    
    # Print summary
    print("\n" + "="*70)
    print("SELECTION SUMMARY")
    print("="*70)
    
    print(f"\nTotal selected: {len(selected)} scenes")
    print(f"Year range: {selected['Year'].min()}-{selected['Year'].max()}")
    print(f"Years covered: {selected['Year'].nunique()}")
    
    print(f"\nBy dataset:")
    for dataset in selected['Dataset'].unique():
        dataset_scenes = selected[selected['Dataset'] == dataset]
        count = len(dataset_scenes)
        years = f"{dataset_scenes['Year'].min()}-{dataset_scenes['Year'].max()}"
        avg_coverage = dataset_scenes['Coverage_Percent'].mean()
        print(f"  {dataset}: {count} scenes ({years}), avg {avg_coverage:.1f}% coverage")
    
    # Logout
    api.logout()
    print("\n✓ Complete")

if __name__ == "__main__":
    main()