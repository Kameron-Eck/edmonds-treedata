"""
NHAP Scene Finder and Coverage Optimizer for Edmonds, WA
Queries USGS M2M API for NHAP 1980 imagery and calculates optimal coverage

Requirements:
- USGS EarthExplorer account with M2M API access
- Google Colab with Google Drive mounted
- Edmonds boundary shapefile in Google Drive

Author: Kam Eck
Date: 2026-05-13
"""

import requests
import json
import geopandas as gpd
from shapely.geometry import Polygon, box
import pandas as pd
from datetime import datetime
import getpass
import time

# ============================================================================
# Configuration
# ============================================================================

BOUNDARY_PATH = '/content/drive/MyDrive/treedata/City Boundry/Edmonds Boundry.shp'
OUTPUT_EXCEL = '/content/drive/MyDrive/treedata/NHAP_1980_Edmonds_Tracking.xlsx'
OUTPUT_IMAGE_BASE = '/content/drive/MyDrive/treedata/Full_Image'

M2M_API_URL = 'https://m2m.cr.usgs.gov/api/api/json/stable/'

# NHAP dataset identifier in M2M API
NHAP_DATASET = 'NHAP'  # May need to verify exact dataset name

# Target year
TARGET_YEAR = 1980

# Download settings
DOWNLOAD_IMAGES = True  # Set to False to only generate scene list without downloading
DOWNLOAD_PRODUCT = 'Full Resolution Browse'  # or 'Standard' for full resolution scan

# ============================================================================
# M2M API Functions
# ============================================================================

class USGSM2M:
    """Interface to USGS M2M API"""
    
    def __init__(self, username, password):
        self.api_url = M2M_API_URL
        self.session = requests.Session()
        self.api_key = None
        self.login(username, password)
    
    def login(self, username, password):
        """Authenticate and get API key"""
        url = f"{self.api_url}login"
        payload = {
            "username": username,
            "password": password
        }
        
        print("Logging in to USGS M2M API...")
        response = self.session.post(url, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('errorCode'):
                raise Exception(f"Login failed: {result.get('errorMessage')}")
            
            self.api_key = result.get('data')
            print("✓ Login successful")
            return self.api_key
        else:
            raise Exception(f"Login request failed: {response.status_code}")
    
    def search_scenes(self, dataset, bbox, start_date, end_date, max_results=100):
        """Search for scenes within a bounding box and date range"""
        url = f"{self.api_url}scene-search"
        
        payload = {
            "datasetName": dataset,
            "maxResults": max_results,
            "startingNumber": 1,
            "sceneFilter": {
                "spatialFilter": {
                    "filterType": "mbr",  # Minimum bounding rectangle
                    "lowerLeft": {
                        "latitude": bbox['south'],
                        "longitude": bbox['west']
                    },
                    "upperRight": {
                        "latitude": bbox['north'],
                        "longitude": bbox['east']
                    }
                },
                "acquisitionFilter": {
                    "start": start_date,
                    "end": end_date
                }
            }
        }
        
        headers = {"X-Auth-Token": self.api_key}
        
        print(f"Searching for {dataset} scenes...")
        response = self.session.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('errorCode'):
                print(f"Warning: {result.get('errorMessage')}")
                return []
            
            scenes = result.get('data', {}).get('results', [])
            print(f"✓ Found {len(scenes)} scenes")
            return scenes
        else:
            raise Exception(f"Search request failed: {response.status_code}")
    
    def get_scene_metadata(self, dataset, entity_ids):
        """Get detailed metadata for specific scenes"""
        url = f"{self.api_url}scene-metadata"
        
        payload = {
            "datasetName": dataset,
            "entityIds": entity_ids
        }
        
        headers = {"X-Auth-Token": self.api_key}
        
        print(f"Fetching metadata for {len(entity_ids)} scenes...")
        response = self.session.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('errorCode'):
                raise Exception(f"Metadata request failed: {result.get('errorMessage')}")
            
            return result.get('data', [])
        else:
            raise Exception(f"Metadata request failed: {response.status_code}")
    
    def get_download_options(self, dataset, entity_ids):
        """Get available download options for scenes"""
        url = f"{self.api_url}download-options"
        
        payload = {
            "datasetName": dataset,
            "entityIds": entity_ids
        }
        
        headers = {"X-Auth-Token": self.api_key}
        
        print(f"Getting download options for {len(entity_ids)} scenes...")
        response = self.session.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('errorCode'):
                raise Exception(f"Download options failed: {result.get('errorMessage')}")
            
            return result.get('data', [])
        else:
            raise Exception(f"Download options request failed: {response.status_code}")
    
    def request_download(self, dataset, entity_ids, product_id):
        """Request download URLs for scenes"""
        url = f"{self.api_url}download-request"
        
        payload = {
            "datasetName": dataset,
            "entityIds": entity_ids,
            "products": [product_id]
        }
        
        headers = {"X-Auth-Token": self.api_key}
        
        print(f"Requesting download URLs...")
        response = self.session.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('errorCode'):
                raise Exception(f"Download request failed: {result.get('errorMessage')}")
            
            return result.get('data', {})
        else:
            raise Exception(f"Download request failed: {response.status_code}")
    
    def download_file(self, url, output_path):
        """Download a file from URL to local path"""
        print(f"  Downloading: {output_path.split('/')[-1]}")
        
        response = self.session.get(url, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        block_size = 8192
        downloaded = 0
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(block_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size:
                        percent = (downloaded / total_size) * 100
                        print(f"\r    Progress: {percent:.1f}%", end='', flush=True)
        
        print(f"\r    ✓ Complete: {downloaded / (1024*1024):.1f} MB")
        return output_path
    
    def logout(self):
        """Logout and invalidate API key"""
        url = f"{self.api_url}logout"
        headers = {"X-Auth-Token": self.api_key}
        
        response = self.session.post(url, headers=headers)
        print("✓ Logged out from M2M API")

# ============================================================================
# Download and File Organization Functions
# ============================================================================

def determine_organization(scene_metadata):
    """
    Determine the organization that captured/scanned the imagery
    Returns organization folder name
    """
    # Check various metadata fields for organization info
    
    # Check data owner field
    data_owner = scene_metadata.get('dataOwner', '').upper()
    if 'USDA' in data_owner or 'APFO' in data_owner:
        return 'USDA-APFO'
    elif 'USGS' in data_owner:
        return 'USGS'
    
    # Check publisher field
    publisher = scene_metadata.get('publisher', '').upper()
    if 'USDA' in publisher or 'APFO' in publisher:
        return 'USDA-APFO'
    elif 'USGS' in publisher:
        return 'USGS'
    
    # Check source field
    source = scene_metadata.get('source', '').upper()
    if 'USDA' in source or 'APFO' in source:
        return 'USDA-APFO'
    elif 'USGS' in source:
        return 'USGS'
    
    # Default to USGS for NHAP (most common)
    print(f"  Warning: Could not determine organization, defaulting to USGS")
    return 'USGS'

def create_output_directory(base_path, organization):
    """Create output directory structure and return full path"""
    import os
    
    full_path = os.path.join(base_path, organization)
    os.makedirs(full_path, exist_ok=True)
    
    return full_path

def get_output_filepath(base_path, organization, display_id, extension='tif'):
    """
    Generate output filepath following the structure:
    /content/drive/MyDrive/treedata/Full_Image/[organization]/[filename]
    """
    import os
    
    # Clean up display_id to be filesystem-safe
    safe_filename = display_id.replace('/', '_').replace('\\', '_')
    filename = f"{safe_filename}.{extension}"
    
    # Create organization subdirectory
    org_dir = create_output_directory(base_path, organization)
    
    # Return full path
    return os.path.join(org_dir, filename)

# ============================================================================
# Coverage Analysis Functions
# ============================================================================

def load_edmonds_boundary(shapefile_path):
    """Load Edmonds city boundary from shapefile"""
    print(f"Loading Edmonds boundary from: {shapefile_path}")
    
    gdf = gpd.read_file(shapefile_path)
    
    # Ensure it's in WGS84 (EPSG:4326) for consistency with M2M API
    if gdf.crs != 'EPSG:4326':
        print(f"Reprojecting from {gdf.crs} to EPSG:4326")
        gdf = gdf.to_crs('EPSG:4326')
    
    # Get the boundary polygon
    boundary = gdf.unary_union
    
    print(f"✓ Boundary loaded")
    print(f"  Bounds: {boundary.bounds}")
    print(f"  Area: {gdf.geometry.area.sum():.6f} sq degrees")
    
    return boundary, gdf

def create_footprint_polygon(scene_metadata):
    """Extract footprint polygon from scene metadata"""
    # M2M API provides corner coordinates
    # Structure varies by dataset - need to extract corner coordinates
    
    try:
        # Try to get spatialBounds or spatialCoverage
        spatial = scene_metadata.get('spatialBounds') or scene_metadata.get('spatialCoverage')
        
        if spatial:
            # Extract corner coordinates
            coords = [
                (spatial.get('west'), spatial.get('north')),
                (spatial.get('east'), spatial.get('north')),
                (spatial.get('east'), spatial.get('south')),
                (spatial.get('west'), spatial.get('south'))
            ]
            return Polygon(coords)
        
        # Alternative: look for corner coordinate fields
        # NHAP typically has: centerLatitude, centerLongitude, and corner coordinates
        # This may need adjustment based on actual API response structure
        
        return None
    
    except Exception as e:
        print(f"Warning: Could not create footprint polygon - {e}")
        return None

def calculate_coverage(boundary_polygon, scene_footprint):
    """Calculate what percentage of the boundary is covered by the scene"""
    if scene_footprint is None:
        return 0.0
    
    try:
        intersection = boundary_polygon.intersection(scene_footprint)
        coverage_pct = (intersection.area / boundary_polygon.area) * 100
        return coverage_pct
    except Exception as e:
        print(f"Warning: Coverage calculation failed - {e}")
        return 0.0

def select_optimal_scenes(scenes_with_coverage, target_coverage=100.0):
    """
    Select minimum number of scenes to achieve target coverage
    Uses a greedy algorithm: iteratively select scene with highest additional coverage
    """
    
    # Sort by coverage percentage (descending)
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
        if footprint is None:
            continue
        
        # Calculate additional coverage this scene would provide
        if total_coverage_geom is None:
            additional_coverage = scene['coverage_pct']
            total_coverage_geom = footprint
        else:
            # Only count the NEW area this scene adds
            new_area = footprint.difference(total_coverage_geom)
            boundary = scene['boundary']
            additional_coverage = (new_area.area / boundary.area) * 100
            total_coverage_geom = total_coverage_geom.union(footprint)
        
        if additional_coverage > 0.1:  # Only add if it provides meaningful coverage
            selected.append(scene)
            current_coverage = (total_coverage_geom.area / scene['boundary'].area) * 100
            print(f"  Selected: {scene['display_id']} (+{additional_coverage:.1f}% → {current_coverage:.1f}% total)")
    
    print(f"\n✓ Selected {len(selected)} scenes for {current_coverage:.1f}% coverage")
    
    return selected

# ============================================================================
# Main Workflow
# ============================================================================

def main():
    """Main workflow"""
    
    print("="*70)
    print("NHAP Scene Finder and Coverage Optimizer")
    print("="*70)
    
    # Step 1: Load Edmonds boundary
    print("\n[1/8] Loading Edmonds city boundary...")
    boundary_polygon, boundary_gdf = load_edmonds_boundary(BOUNDARY_PATH)
    
    # Get bounding box from boundary
    bounds = boundary_polygon.bounds  # (minx, miny, maxx, maxy)
    bbox = {
        'west': bounds[0],
        'south': bounds[1],
        'east': bounds[2],
        'north': bounds[3]
    }
    
    print(f"Study area bounding box: {bbox}")
    
    # Step 2: Connect to M2M API
    print("\n[2/8] Connecting to USGS M2M API...")
    username = input("USGS EarthExplorer username: ")
    password = getpass.getpass("USGS EarthExplorer password: ")
    
    api = USGSM2M(username, password)
    
    # Step 3: Search for NHAP scenes
    print(f"\n[3/8] Searching for NHAP {TARGET_YEAR} scenes...")
    
    scenes = api.search_scenes(
        dataset=NHAP_DATASET,
        bbox=bbox,
        start_date=f"{TARGET_YEAR}-01-01",
        end_date=f"{TARGET_YEAR}-12-31",
        max_results=100
    )
    
    if not scenes:
        print("No scenes found! Check dataset name or date range.")
        api.logout()
        return
    
    print(f"Found {len(scenes)} potential scenes")
    
    # Step 4: Get detailed metadata and calculate coverage
    print("\n[4/8] Analyzing scene coverage...")
    
    scenes_with_coverage = []
    
    for scene in scenes:
        entity_id = scene.get('entityId')
        display_id = scene.get('displayId')
        
        # Create footprint from scene bounds
        spatial = scene.get('spatialBounds') or scene.get('spatialCoverage')
        
        if spatial:
            footprint = create_footprint_polygon(spatial)
            coverage_pct = calculate_coverage(boundary_polygon, footprint)
            
            scenes_with_coverage.append({
                'entity_id': entity_id,
                'display_id': display_id,
                'scene_data': scene,
                'footprint': footprint,
                'coverage_pct': coverage_pct,
                'boundary': boundary_polygon
            })
            
            print(f"  {display_id}: {coverage_pct:.1f}% coverage")
    
    # Step 5: Select optimal scene set
    print("\n[5/8] Selecting optimal scene set...")
    optimal_scenes = select_optimal_scenes(scenes_with_coverage, target_coverage=95.0)
    
    # Step 6: Prepare scene records
    print("\n[6/8] Preparing scene records...")
    
    # Create DataFrame with scene information
    records = []
    for scene_info in optimal_scenes:
        scene = scene_info['scene_data']
        spatial = scene.get('spatialBounds') or scene.get('spatialCoverage')
        
        # Determine organization
        organization = determine_organization(scene)
        
        # Generate output path
        display_id = scene_info['display_id']
        output_path = get_output_filepath(OUTPUT_IMAGE_BASE, organization, display_id)
        
        record = {
            'Entity_ID': scene_info['entity_id'],
            'Display_ID': display_id,
            'Acquisition_Date': scene.get('temporalCoverage', {}).get('startDate', 'Unknown'),
            'Coverage_Pct': f"{scene_info['coverage_pct']:.2f}%",
            'Organization': organization,
            'Center_Lat': spatial.get('centerLatitude', '') if spatial else '',
            'Center_Lon': spatial.get('centerLongitude', '') if spatial else '',
            'NW_Corner_Lat': spatial.get('north', '') if spatial else '',
            'NW_Corner_Lon': spatial.get('west', '') if spatial else '',
            'NE_Corner_Lat': spatial.get('north', '') if spatial else '',
            'NE_Corner_Lon': spatial.get('east', '') if spatial else '',
            'SW_Corner_Lat': spatial.get('south', '') if spatial else '',
            'SW_Corner_Lon': spatial.get('west', '') if spatial else '',
            'SE_Corner_Lat': spatial.get('south', '') if spatial else '',
            'SE_Corner_Lon': spatial.get('east', '') if spatial else '',
            'Download_Status': 'Pending' if DOWNLOAD_IMAGES else 'Not Started',
            'Local_Filename': output_path,
            'Georeferenced': 'No',
            'Notes': 'Selected for optimal coverage'
        }
        
        records.append(record)
    
    df = pd.DataFrame(records)
    print(f"✓ Prepared {len(records)} scene records")
    
    # Step 7: Download imagery (if enabled)
    if DOWNLOAD_IMAGES:
        import os
        print("\n[7/8] Downloading imagery...")
        print(f"Output directory: {OUTPUT_IMAGE_BASE}")
        
        entity_ids = [scene_info['entity_id'] for scene_info in optimal_scenes]
        
        # Get download options
        try:
            download_options = api.get_download_options(NHAP_DATASET, entity_ids)
            
            # Find appropriate product
            available_products = []
            for option in download_options:
                if option.get('available'):
                    products = option.get('downloadOptions', [])
                    for product in products:
                        product_name = product.get('productName', '')
                        if product_name and product_name not in available_products:
                            available_products.append(product_name)
            
            if available_products:
                print(f"  Available products: {', '.join(available_products)}")
                
                # Select best product
                selected_product = None
                for pref in ['Full Resolution', 'High Resolution', 'Standard']:
                    for prod in available_products:
                        if pref.lower() in prod.lower():
                            selected_product = prod
                            break
                    if selected_product:
                        break
                
                if not selected_product:
                    selected_product = available_products[0]
                
                print(f"  Selected product: {selected_product}")
                
                # Request download URLs
                download_data = api.request_download(NHAP_DATASET, entity_ids, selected_product)
                
                # Download each file
                available_downloads = download_data.get('availableDownloads', [])
                
                if available_downloads:
                    for i, download in enumerate(available_downloads):
                        entity_id = download.get('entityId')
                        download_url = download.get('url')
                        
                        if download_url:
                            # Find corresponding record
                            record_idx = df[df['Entity_ID'] == entity_id].index
                            if len(record_idx) > 0:
                                idx = record_idx[0]
                                output_path = df.loc[idx, 'Local_Filename']
                                
                                print(f"\n  [{i+1}/{len(available_downloads)}] {df.loc[idx, 'Display_ID']}")
                                print(f"    Organization: {df.loc[idx, 'Organization']}")
                                
                                try:
                                    # Download file
                                    api.download_file(download_url, output_path)
                                    
                                    # Update status
                                    df.loc[idx, 'Download_Status'] = 'Downloaded'
                                    file_size_mb = os.path.getsize(output_path) / (1024*1024)
                                    df.loc[idx, 'Notes'] = f"Downloaded {file_size_mb:.1f} MB"
                                    
                                except Exception as e:
                                    print(f"    ✗ Download failed: {e}")
                                    df.loc[idx, 'Download_Status'] = 'Failed'
                                    df.loc[idx, 'Notes'] = f"Download error: {str(e)}"
                        else:
                            print(f"  Warning: No download URL for {entity_id}")
                    
                    success_count = len(df[df['Download_Status'] == 'Downloaded'])
                    print(f"\n✓ Downloaded {success_count} of {len(available_downloads)} scenes")
                else:
                    print("  Warning: No downloads available")
                    df['Download_Status'] = 'Needs Processing'
                
            else:
                print("  Warning: No downloadable products available")
                df['Download_Status'] = 'No Products Available'
                
        except Exception as e:
            print(f"  Download error: {e}")
            df['Download_Status'] = 'Manual Download Required'
    else:
        print("\n[7/8] Skipping downloads (DOWNLOAD_IMAGES = False)")
    
    # Step 8: Save to Excel
    print("\n[8/8] Saving to Excel...")
    with pd.ExcelWriter(OUTPUT_EXCEL, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='NHAP_1980_Edmonds_WA', index=False)
        
        # Add summary sheet
        summary_data = {
            'Metric': ['Total Scenes Found', 'Scenes Selected', 'Target Coverage', 
                      'Download Status', 'Search Date'],
            'Value': [
                len(scenes),
                len(optimal_scenes),
                f"{sum(s['coverage_pct'] for s in optimal_scenes):.1f}%",
                'Downloaded' if DOWNLOAD_IMAGES else 'Not Started',
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ]
        }
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
    
    print(f"✓ Results saved to: {OUTPUT_EXCEL}")
    
    # Logout
    api.logout()
    
    print("\n" + "="*70)
    print("COMPLETE!")
    print("="*70)
    print(f"Selected {len(optimal_scenes)} optimal scenes for Edmonds coverage")
    print(f"Tracking spreadsheet: {OUTPUT_EXCEL}")
    if DOWNLOAD_IMAGES:
        print(f"Downloaded imagery: {OUTPUT_IMAGE_BASE}")
        print(f"  Organizations: {df['Organization'].unique().tolist()}")

if __name__ == "__main__":
    main()
