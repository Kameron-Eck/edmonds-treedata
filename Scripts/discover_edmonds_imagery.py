"""
Discover All Aerial Imagery for Edmonds, Washington
Searches M2M API across all aerial photography datasets

Output: Inventory of available imagery (any year, any program)
"""

import requests
import pandas as pd
from datetime import datetime
import getpass
import json

# ============================================================================
# Configuration
# ============================================================================

BOUNDARY_PATH = '/content/drive/MyDrive/treedata/City Boundry/Edmonds Boundry.shp'
OUTPUT_INVENTORY = '/content/drive/MyDrive/treedata/Full_Image/USGS/Edmonds_Imagery_Inventory.xlsx'

M2M_API_URL = 'https://m2m.cr.usgs.gov/api/api/json/stable/'

# Edmonds bounding box (approximate)
EDMONDS_BBOX = {
    'west': -122.40,
    'south': 47.78,
    'east': -122.32,
    'north': 47.86
}

# Aerial photography datasets to search
AERIAL_DATASETS = [
    'NHAP',           # 1980-1989
    'NAPP',           # 1987-2007  
    'DOQQ',           # Digital Orthophoto Quarter Quads
    'NAIP',           # 2003-present
    'AERIAL_COMBIN',  # Combined aerial
    'HIGH_RES_ORTHO'  # High resolution orthophotography
]

# ============================================================================
# M2M API Functions
# ============================================================================

class USGSM2M:
    def __init__(self, username, token):
        self.api_url = M2M_API_URL
        self.session = requests.Session()
        self.api_key = None
        self.login(username, token)
    
    def login(self, username, token):
        """Authenticate with username and application token"""
        url = f"{self.api_url}login-token"
        payload = {"username": username, "token": token}
        headers = {"Content-Type": "application/json"}
        
        response = self.session.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('errorCode'):
                raise Exception(f"Login failed: {result.get('errorMessage')}")
            
            self.api_key = result.get('data')
            print("✓ Logged in to M2M API")
            return self.api_key
        else:
            # Print response for debugging
            try:
                error_detail = response.json()
                raise Exception(f"Login failed ({response.status_code}): {error_detail}")
            except:
                raise Exception(f"Login failed ({response.status_code}): {response.text[:200]}")
    
    def dataset_exists(self, dataset_name):
        """Check if dataset exists in M2M"""
        url = f"{self.api_url}dataset-search"
        payload = {"datasetName": dataset_name}
        headers = {"X-Auth-Token": self.api_key}
        
        response = self.session.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            data = result.get('data')
            return data is not None and len(data) > 0
        return False
    
    def search_scenes(self, dataset, bbox, max_results=1000):
        """Search for scenes within bounding box"""
        url = f"{self.api_url}scene-search"
        
        payload = {
            "datasetName": dataset,
            "maxResults": max_results,
            "startingNumber": 1,
            "sceneFilter": {
                "spatialFilter": {
                    "filterType": "mbr",
                    "lowerLeft": {
                        "latitude": bbox['south'],
                        "longitude": bbox['west']
                    },
                    "upperRight": {
                        "latitude": bbox['north'],
                        "longitude": bbox['east']
                    }
                }
            }
        }
        
        headers = {"X-Auth-Token": self.api_key}
        response = self.session.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('errorCode'):
                return None  # Dataset not found or error
            
            scenes = result.get('data', {}).get('results', [])
            return scenes
        return None
    
    def logout(self):
        """Logout and invalidate API key"""
        url = f"{self.api_url}logout"
        headers = {"X-Auth-Token": self.api_key}
        self.session.post(url, headers=headers)

# ============================================================================
# Discovery Functions
# ============================================================================

def discover_all_datasets(api):
    """Search all aerial photography datasets for Edmonds coverage"""
    
    print("\n" + "="*70)
    print("DISCOVERING AERIAL IMAGERY FOR EDMONDS, WA")
    print("="*70)
    
    inventory = []
    
    for dataset_name in AERIAL_DATASETS:
        print(f"\n[Searching] {dataset_name}...", end=" ")
        
        # Check if dataset exists
        if not api.dataset_exists(dataset_name):
            print("✗ Not found")
            continue
        
        # Search for scenes
        scenes = api.search_scenes(dataset_name, EDMONDS_BBOX)
        
        if scenes is None:
            print("✗ Error or no access")
            continue
        
        if len(scenes) == 0:
            print("○ No scenes")
            continue
        
        print(f"✓ {len(scenes)} scenes found")
        
        # Extract date range
        dates = []
        for scene in scenes:
            temporal = scene.get('temporalCoverage', {})
            start_date = temporal.get('startDate')
            if start_date:
                try:
                    dates.append(datetime.strptime(start_date[:10], '%Y-%m-%d'))
                except:
                    pass
        
        if dates:
            min_date = min(dates)
            max_date = max(dates)
            date_range = f"{min_date.year}-{max_date.year}"
        else:
            date_range = "Unknown"
        
        # Add to inventory
        inventory.append({
            'Dataset': dataset_name,
            'Scene_Count': len(scenes),
            'Date_Range': date_range,
            'Earliest': min(dates).strftime('%Y-%m-%d') if dates else 'Unknown',
            'Latest': max(dates).strftime('%Y-%m-%d') if dates else 'Unknown',
            'Status': 'Available'
        })
        
        # Show sample scene IDs
        print(f"    Date range: {date_range}")
        if len(scenes) > 0:
            print(f"    Sample: {scenes[0].get('displayId', 'N/A')}")
    
    return inventory

def save_inventory(inventory, output_path):
    """Save inventory to Excel"""
    
    if not inventory:
        print("\n✗ No imagery found!")
        return
    
    df = pd.DataFrame(inventory)
    
    # Create summary
    total_scenes = df['Scene_Count'].sum()
    datasets_found = len(df)
    
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # Main inventory
        df.to_excel(writer, sheet_name='Inventory', index=False)
        
        # Summary
        summary = pd.DataFrame({
            'Metric': [
                'Total Datasets Found',
                'Total Scenes Available',
                'Earliest Date',
                'Latest Date',
                'Search Date'
            ],
            'Value': [
                datasets_found,
                total_scenes,
                df['Earliest'].min(),
                df['Latest'].max(),
                datetime.now().strftime('%Y-%m-%d %H:%M')
            ]
        })
        summary.to_excel(writer, sheet_name='Summary', index=False)
    
    print(f"\n✓ Inventory saved: {output_path}")
    print(f"\n📊 SUMMARY:")
    print(f"   Datasets found: {datasets_found}")
    print(f"   Total scenes: {total_scenes}")
    print(f"   Date range: {df['Earliest'].min()} to {df['Latest'].max()}")

# ============================================================================
# Main
# ============================================================================

def main():
    """Main discovery workflow"""
    
    print("="*70)
    print("EDMONDS AERIAL IMAGERY DISCOVERY")
    print("="*70)
    print(f"\nSearch area: {EDMONDS_BBOX}")
    print(f"Datasets to search: {len(AERIAL_DATASETS)}")
    
    # Login with username and application token
    print("\n[Authentication]")
    
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
        print("Using credentials from variables")
    else:
        print("Generate token at: https://ers.cr.usgs.gov/profile/access")
        user = input("USGS username: ")
        token = getpass.getpass("M2M Application Token: ")
    
    api = USGSM2M(user, token)
    
    # Discover imagery
    inventory = discover_all_datasets(api)
    
    # Save results
    if inventory:
        save_inventory(inventory, OUTPUT_INVENTORY)
    else:
        print("\n✗ No aerial imagery found for Edmonds")
    
    # Logout
    api.logout()
    print("\n✓ Complete")

if __name__ == "__main__":
    main()