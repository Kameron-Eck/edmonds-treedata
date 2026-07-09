"""
Collect Detailed Metadata for Discovered Imagery
Queries M2M API for comprehensive scene information

Input: Edmonds_Imagery_Inventory.xlsx
Output: Enhanced Excel with full metadata
"""

import requests
import pandas as pd
import getpass
import json
from datetime import datetime

# ============================================================================
# Configuration
# ============================================================================

INVENTORY_FILE = '/content/drive/MyDrive/treedata/Full_Image/USGS/Edmonds_Imagery_Inventory.xlsx'
OUTPUT_FILE = '/content/drive/MyDrive/treedata/Full_Image/USGS/Edmonds_Imagery_Metadata.xlsx'
M2M_API_URL = 'https://m2m.cr.usgs.gov/api/api/json/stable/'

# Edmonds bounding box
EDMONDS_BBOX = {
    'west': -122.40,
    'south': 47.78,
    'east': -122.32,
    'north': 47.86
}

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
    
    def get_scene_metadata(self, dataset, entity_id):
        """Get detailed metadata for a specific scene"""
        url = f"{self.api_url}scene-metadata"
        payload = {
            "datasetName": dataset,
            "entityId": entity_id
        }
        headers = {"X-Auth-Token": self.api_key}
        
        response = self.session.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            return result.get('data')
        return None
    
    def get_download_options(self, dataset, entity_ids):
        """Get available download options"""
        url = f"{self.api_url}download-options"
        payload = {
            "datasetName": dataset,
            "entityIds": entity_ids
        }
        headers = {"X-Auth-Token": self.api_key}
        
        response = self.session.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            return result.get('data', [])
        return []
    
    def get_scene_list_add(self, dataset, entity_ids):
        """Get full scene details including metadata fields"""
        url = f"{self.api_url}scene-list-add"
        payload = {
            "datasetName": dataset,
            "entityIds": entity_ids,
            "listId": "temp_list"
        }
        headers = {"X-Auth-Token": self.api_key}
        
        response = self.session.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            return result.get('data')
        return None
    
    def logout(self):
        """Logout"""
        url = f"{self.api_url}logout"
        headers = {"X-Auth-Token": self.api_key}
        self.session.post(url, headers=headers)

# ============================================================================
# Metadata Collection
# ============================================================================

def collect_metadata(api, inventory_df):
    """Collect detailed metadata for all scenes"""
    
    print("\n" + "="*70)
    print("COLLECTING DETAILED METADATA")
    print("="*70)
    
    all_metadata = []
    
    # Group by dataset
    datasets = inventory_df['Dataset'].unique()
    
    for dataset in datasets:
        dataset_scenes = inventory_df[inventory_df['Dataset'] == dataset]
        scene_count = dataset_scenes['Scene_Count'].iloc[0]
        
        print(f"\n[{dataset}] {scene_count} scenes")
        
        # For now, we'll get download options in batches
        # (scene-search already gave us basic info)
        # Let's focus on download options which shows file sizes
        
        # We'll need to re-search to get entity IDs
        # For this initial version, let's get download options for each dataset
        
        print(f"  Querying download options...")
        
        # We need entity IDs - let's search again to get them
        entity_ids = search_scenes_for_dataset(api, dataset)
        
        if not entity_ids:
            print(f"  ✗ Could not retrieve entity IDs")
            continue
        
        # Get download options (shows file sizes, formats)
        download_opts = api.get_download_options(dataset, entity_ids[:100])  # Max 100 at a time
        
        if download_opts:
            print(f"  ✓ Retrieved download options for {len(download_opts)} scenes")
            
            for opt in download_opts:
                metadata = {
                    'Dataset': dataset,
                    'Entity_ID': opt.get('entityId'),
                    'Display_ID': opt.get('displayId', 'N/A'),
                    'Product_Name': opt.get('productName', 'N/A'),
                    'Product_Code': opt.get('productCode', 'N/A'),
                    'Available': opt.get('available', False),
                    'File_Size_MB': opt.get('filesize', 0) / 1024 / 1024 if opt.get('filesize') else None,
                    'Download_System': opt.get('downloadSystem', 'N/A'),
                    'Secondary_Downloads': len(opt.get('secondaryDownloads', []))
                }
                all_metadata.append(metadata)
        else:
            print(f"  ○ No download options available")
    
    return pd.DataFrame(all_metadata)

def search_scenes_for_dataset(api, dataset):
    """Re-search to get entity IDs"""
    
    url = f"{api.api_url}scene-search"
    
    payload = {
        "datasetName": dataset,
        "maxResults": 100,  # Limit for now
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
    
    headers = {"X-Auth-Token": api.api_key}
    response = api.session.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        scenes = result.get('data', {}).get('results', [])
        return [s.get('entityId') for s in scenes if s.get('entityId')]
    
    return []

# ============================================================================
# Main
# ============================================================================

def main():
    """Main metadata collection workflow"""
    
    print("="*70)
    print("EDMONDS IMAGERY - METADATA COLLECTION")
    print("="*70)
    
    # Load inventory
    print(f"\n[1/4] Loading inventory...")
    inventory_df = pd.read_excel(INVENTORY_FILE, sheet_name='Inventory')
    print(f"  ✓ Loaded {len(inventory_df)} datasets")
    
    # Login
    print(f"\n[2/4] Authenticating...")
    
    # Check if credentials are defined in calling environment
    import sys
    user = None
    token = None
    
    # Try to get from calling module (notebook)
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
    
    # Collect metadata
    print(f"\n[3/4] Collecting metadata...")
    metadata_df = collect_metadata(api, inventory_df)
    
    # Save results
    print(f"\n[4/4] Saving results...")
    
    with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
        # Original inventory
        inventory_df.to_excel(writer, sheet_name='Inventory', index=False)
        
        # Detailed metadata
        metadata_df.to_excel(writer, sheet_name='Download_Options', index=False)
        
        # Summary by dataset
        summary = metadata_df.groupby('Dataset').agg({
            'File_Size_MB': ['count', 'sum', 'mean', 'min', 'max'],
            'Available': 'sum'
        }).round(2)
        summary.to_excel(writer, sheet_name='Size_Summary')
    
    print(f"✓ Saved: {OUTPUT_FILE}")
    
    # Print summary
    print("\n" + "="*70)
    print("METADATA SUMMARY")
    print("="*70)
    
    total_size = metadata_df['File_Size_MB'].sum()  # sum() ignores None/NaN
    total_scenes = len(metadata_df)
    available = metadata_df['Available'].sum()
    
    print(f"\nTotal scenes: {total_scenes}")
    print(f"Available for download: {available}")
    print(f"Total size: {total_size:.1f} MB ({total_size/1024:.1f} GB)")
    print(f"\nBy dataset:")
    
    for dataset in metadata_df['Dataset'].unique():
        dataset_data = metadata_df[metadata_df['Dataset'] == dataset]
        count = len(dataset_data)
        size = dataset_data['File_Size_MB'].sum()  # sum() ignores None/NaN
        avail = dataset_data['Available'].sum()
        print(f"  {dataset}: {count} scenes, {size:.1f} MB, {avail} available")
    
    # Logout
    api.logout()
    print("\n✓ Complete")

if __name__ == "__main__":
    main()