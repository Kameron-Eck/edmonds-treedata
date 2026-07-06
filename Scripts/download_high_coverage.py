"""
Download High-Coverage Imagery for Edmonds
Downloads scenes from years with ≥95% coverage

Input: Edmonds_Optimal_Scenes.xlsx
Output: Downloaded imagery organized by year/dataset
"""

import requests
import pandas as pd
import getpass
import time
import os
from pathlib import Path

# ============================================================================
# Configuration
# ============================================================================

SCENES_FILE = '/content/drive/MyDrive/treedata/Full_Image/USGS/Edmonds_Optimal_Scenes.xlsx'
DOWNLOAD_DIR = '/content/edmonds_imagery'  # Colab local storage for speed
TRACKING_FILE = '/content/drive/MyDrive/treedata/Full_Image/USGS/Download_Tracking.xlsx'
M2M_API_URL = 'https://m2m.cr.usgs.gov/api/api/json/stable/'

# Coverage threshold for download
MIN_COVERAGE = 95.0
MAX_YEAR = 2012  # Pre-2013 only

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
    
    def get_download_options(self, dataset, entity_ids):
        """Get available download options for scenes"""
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
    
    def download_request(self, downloads):
        """Submit download request"""
        url = f"{self.api_url}download-request"
        payload = {"downloads": downloads}
        headers = {"X-Auth-Token": self.api_key}
        
        response = self.session.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            return result.get('data', {})
        return {}
    
    def download_retrieve(self, label):
        """Retrieve download URLs"""
        url = f"{self.api_url}download-retrieve"
        payload = {"label": label}
        headers = {"X-Auth-Token": self.api_key}
        
        response = self.session.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            return result.get('data', {})
        return {}
    
    def logout(self):
        """Logout"""
        url = f"{self.api_url}logout"
        headers = {"X-Auth-Token": self.api_key}
        self.session.post(url, headers=headers)

# ============================================================================
# Download Functions
# ============================================================================

def download_file(url, filepath):
    """Download file from URL with progress"""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        
        with open(filepath, 'wb') as f:
            if total_size == 0:
                f.write(response.content)
            else:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    progress = (downloaded / total_size) * 100
                    print(f"    {progress:.1f}%", end='\r')
        
        print(f"    ✓ {os.path.basename(filepath)}")
        return True
    except Exception as e:
        print(f"    ✗ Error: {e}")
        return False

def process_dataset_downloads(api, scenes_df, dataset):
    """Process downloads for a specific dataset"""
    
    dataset_scenes = scenes_df[scenes_df['Dataset'] == dataset]
    
    if len(dataset_scenes) == 0:
        return []
    
    print(f"\n[{dataset}] {len(dataset_scenes)} scenes")
    
    # Get entity IDs
    entity_ids = dataset_scenes['Entity_ID'].tolist()
    
    # Get download options
    print(f"  Querying download options...")
    options = api.get_download_options(dataset, entity_ids)
    
    if not options:
        print(f"  ✗ No download options available")
        return []
    
    print(f"  ✓ Found {len(options)} download products")
    
    # Select best product per scene (prefer full resolution)
    download_requests = []
    
    for opt in options:
        entity_id = opt.get('entityId')
        
        # Find scene info
        scene_info = dataset_scenes[dataset_scenes['Entity_ID'] == entity_id]
        if len(scene_info) == 0:
            continue
        
        year = scene_info.iloc[0]['Year']
        display_id = scene_info.iloc[0]['Display_ID']
        
        # Check if available for direct download
        if not opt.get('available', False):
            print(f"  ⚠ {display_id} not available for download")
            continue
        
        # Get product ID (not code)
        product_id = opt.get('id')  # This is the actual product ID
        product_name = opt.get('productName', 'Unknown')
        
        if not product_id:
            print(f"  ⚠ {display_id} - no product ID")
            continue
        
        print(f"  ✓ {display_id} - {product_name}")
        
        download_requests.append({
            'entityId': entity_id,
            'productId': product_id,  # Use 'id' not 'productCode'
            'year': year,
            'display_id': display_id,
            'dataset': dataset,
            'product_name': product_name
        })
    
    return download_requests

def execute_downloads(api, download_requests, download_dir):
    """Execute actual downloads"""
    
    if not download_requests:
        print("\nNo downloads to execute")
        return []
    
    print(f"\n{'='*70}")
    print(f"EXECUTING DOWNLOADS")
    print(f"{'='*70}")
    print(f"\nTotal: {len(download_requests)} files")
    
    # Group into batches (API limit)
    batch_size = 100
    batches = [download_requests[i:i+batch_size] for i in range(0, len(download_requests), batch_size)]
    
    download_results = []
    
    for batch_num, batch in enumerate(batches, 1):
        print(f"\n[Batch {batch_num}/{len(batches)}] {len(batch)} scenes")
        
        # Prepare download request
        downloads = [
            {
                'entityId': req['entityId'],
                'productId': req['productId']  # Use productId not productCode
            }
            for req in batch
        ]
        
        print(f"  Sample request: {downloads[0] if downloads else 'none'}")
        
        # Submit download request
        print("  Submitting download request...")
        result = api.download_request(downloads)
        
        print(f"  Response keys: {list(result.keys()) if result else 'none'}")
        
        if 'preparingDownloads' in result:
            preparing = result['preparingDownloads']
            print(f"  Preparing {len(preparing)} downloads...")
        
        if 'availableDownloads' in result:
            available_now = result['availableDownloads']
            print(f"  ✓ {len(available_now)} downloads available immediately")
            
            # Process immediately available downloads
            for item in available_now:
                url = item.get('url')
                entity_id = item.get('entityId')
                
                # Find matching request
                req_info = next((r for r in batch if r['entityId'] == entity_id), None)
                
                if not req_info:
                    continue
                
                # Create directory structure
                year_dir = os.path.join(download_dir, str(req_info['year']), req_info['dataset'])
                os.makedirs(year_dir, exist_ok=True)
                
                # Download
                filename = item.get('displayId', entity_id) + '.tif'
                filepath = os.path.join(year_dir, filename)
                
                print(f"\n  [{req_info['year']}] {req_info['display_id']}")
                success = download_file(url, filepath)
                
                download_results.append({
                    'Year': req_info['year'],
                    'Dataset': req_info['dataset'],
                    'Display_ID': req_info['display_id'],
                    'Entity_ID': entity_id,
                    'Filepath': filepath,
                    'Status': 'Success' if success else 'Failed',
                    'File_Size_MB': os.path.getsize(filepath) / 1024 / 1024 if success else 0
                })
        
        if 'preparingDownloads' in result and len(result['preparingDownloads']) > 0:
            preparing = result['preparingDownloads']
            print(f"  Preparing {len(preparing)} downloads...")
            
            # Debug: show structure
            print(f"  newRecords type: {type(result.get('newRecords'))}")
            print(f"  newRecords content: {result.get('newRecords')}")
            
            # Try to get label from preparingDownloads or newRecords
            label = None
            
            # Check if preparing downloads has a label
            if preparing and len(preparing) > 0:
                first_preparing = preparing[0]
                label = first_preparing.get('downloadId') or first_preparing.get('label')
            
            # Fallback to newRecords
            if not label and result.get('newRecords'):
                new_records = result.get('newRecords')
                if isinstance(new_records, list) and len(new_records) > 0:
                    label = new_records[0].get('downloadId') or new_records[0].get('label')
                elif isinstance(new_records, dict):
                    label = new_records.get('downloadId') or new_records.get('label')
            
            print(f"  Download label: {label}")
            
            if not label:
                print(f"  ⚠ Could not find download label - downloads may be queued")
                print(f"  Check EarthExplorer for prepared downloads")
                continue
            
            # Wait for preparation
            time.sleep(5)
            if label:
                # Retrieve download URLs
                download_data = api.download_retrieve(label)
                available = download_data.get('available', [])
                
                print(f"  ✓ {len(available)} downloads ready")
                
                # Download each file
                for item in available:
                    url = item.get('url')
                    
                    # Find matching request
                    entity_id = item.get('entityId')
                    req_info = next((r for r in batch if r['entityId'] == entity_id), None)
                    
                    if not req_info:
                        continue
                    
                    # Create directory structure
                    year_dir = os.path.join(download_dir, str(req_info['year']), req_info['dataset'])
                    os.makedirs(year_dir, exist_ok=True)
                    
                    # Download
                    filename = item.get('displayId', entity_id) + '.tif'
                    filepath = os.path.join(year_dir, filename)
                    
                    print(f"\n  [{req_info['year']}] {req_info['display_id']}")
                    success = download_file(url, filepath)
                    
                    download_results.append({
                        'Year': req_info['year'],
                        'Dataset': req_info['dataset'],
                        'Display_ID': req_info['display_id'],
                        'Entity_ID': entity_id,
                        'Filepath': filepath,
                        'Status': 'Success' if success else 'Failed',
                        'File_Size_MB': os.path.getsize(filepath) / 1024 / 1024 if success else 0
                    })
        
        # Rate limiting
        if batch_num < len(batches):
            print("\n  Waiting 10s before next batch...")
            time.sleep(10)
    
    return download_results

# ============================================================================
# Main
# ============================================================================

def main():
    """Main download workflow"""
    
    print("="*70)
    print("EDMONDS IMAGERY - DOWNLOAD PRE-2013 HIGH-COVERAGE YEARS")
    print("="*70)
    
    # Load selected scenes
    print(f"\n[1/4] Loading selected scenes...")
    scenes_df = pd.read_excel(SCENES_FILE, sheet_name='Optimal_Scenes')
    
    # Filter to high-coverage years before 2013
    year_summary = scenes_df.groupby('Year')['Coverage_Percent'].sum()
    high_coverage_years = year_summary[year_summary >= MIN_COVERAGE].index.tolist()
    
    # Filter to pre-2013 only
    pre_2013_years = [y for y in high_coverage_years if y <= MAX_YEAR]
    
    high_coverage_scenes = scenes_df[scenes_df['Year'].isin(pre_2013_years)]
    
    print(f"  ✓ Total scenes: {len(scenes_df)}")
    print(f"  ✓ High-coverage years (≥{MIN_COVERAGE}%): {len(high_coverage_years)}")
    print(f"  ✓ Pre-2013 high-coverage years: {len(pre_2013_years)}")
    print(f"  ✓ Scenes to download: {len(high_coverage_scenes)}")
    print(f"  Years: {sorted(pre_2013_years)}")
    
    # Create download directory
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    # Login
    print(f"\n[2/4] Authenticating...")
    
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
    
    # Process downloads by dataset
    print(f"\n[3/4] Preparing downloads...")
    
    all_download_requests = []
    
    for dataset in high_coverage_scenes['Dataset'].unique():
        requests = process_dataset_downloads(api, high_coverage_scenes, dataset)
        all_download_requests.extend(requests)
    
    print(f"\n  Total download requests: {len(all_download_requests)}")
    
    # Execute downloads
    print(f"\n[4/4] Downloading imagery...")
    
    results = execute_downloads(api, all_download_requests, DOWNLOAD_DIR)
    
    # Save tracking
    if results:
        results_df = pd.DataFrame(results)
        results_df.to_excel(TRACKING_FILE, index=False)
        print(f"\n✓ Tracking saved: {TRACKING_FILE}")
    
    # Summary
    print("\n" + "="*70)
    print("DOWNLOAD SUMMARY")
    print("="*70)
    
    if results:
        results_df = pd.DataFrame(results)
        success = len(results_df[results_df['Status'] == 'Success'])
        failed = len(results_df[results_df['Status'] == 'Failed'])
        total_size = results_df['File_Size_MB'].sum()
        
        print(f"\nTotal downloads: {len(results)}")
        print(f"Successful: {success}")
        print(f"Failed: {failed}")
        print(f"Total size: {total_size:.1f} MB ({total_size/1024:.1f} GB)")
        
        print(f"\nBy year:")
        year_summary = results_df.groupby('Year').agg({
            'Status': lambda x: (x == 'Success').sum(),
            'File_Size_MB': 'sum'
        })
        for year, row in year_summary.iterrows():
            print(f"  {year}: {int(row['Status'])} scenes, {row['File_Size_MB']:.1f} MB")
        
        print(f"\nDownloads saved to: {DOWNLOAD_DIR}")
    
    # Logout
    api.logout()
    print("\n✓ Complete")

if __name__ == "__main__":
    main()