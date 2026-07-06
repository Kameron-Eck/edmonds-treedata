"""
API Response Inspector
Shows raw structure of M2M API responses to understand available fields
"""

import requests
import json
import getpass

M2M_API_URL = 'https://m2m.cr.usgs.gov/api/api/json/stable/'

EDMONDS_BBOX = {
    'west': -122.40,
    'south': 47.78,
    'east': -122.32,
    'north': 47.86
}

def login(username, token):
    """Authenticate"""
    url = f"{M2M_API_URL}login-token"
    payload = {"username": username, "token": token}
    
    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        result = response.json()
        return result.get('data')
    else:
        print(f"Login failed: {response.status_code}")
        return None

def inspect_scene_search(api_key, dataset='NAIP'):
    """Query scene-search and show raw response"""
    url = f"{M2M_API_URL}scene-search"
    
    payload = {
        "datasetName": dataset,
        "maxResults": 5,  # Just get a few
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
    
    headers = {"X-Auth-Token": api_key}
    response = requests.post(url, json=payload, headers=headers)
    
    print(f"\n{'='*70}")
    print(f"DATASET: {dataset}")
    print(f"{'='*70}")
    
    print(f"\nStatus Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        
        # Show top-level structure
        print(f"\nTop-level keys: {list(result.keys())}")
        
        if 'data' in result:
            data = result['data']
            print(f"Data keys: {list(data.keys())}")
            
            if 'results' in data:
                results = data['results']
                print(f"\nNumber of results: {len(results)}")
                
                if len(results) > 0:
                    print(f"\n{'='*70}")
                    print("FIRST SCENE STRUCTURE:")
                    print(f"{'='*70}")
                    
                    first_scene = results[0]
                    
                    # Print all top-level keys
                    print(f"\nScene keys ({len(first_scene)}):")
                    for key in sorted(first_scene.keys()):
                        value = first_scene[key]
                        if isinstance(value, dict):
                            print(f"  {key}: dict with keys {list(value.keys())}")
                        elif isinstance(value, list):
                            print(f"  {key}: list with {len(value)} items")
                        else:
                            print(f"  {key}: {type(value).__name__} = {value}")
                    
                    # Show spatial fields in detail
                    print(f"\n{'='*70}")
                    print("SPATIAL FIELDS:")
                    print(f"{'='*70}")
                    
                    spatial_keys = ['spatialBounds', 'spatialCoverage', 'spatialFootprint', 
                                   'boundingBox', 'coordinates']
                    
                    for key in spatial_keys:
                        if key in first_scene:
                            print(f"\n{key}:")
                            print(json.dumps(first_scene[key], indent=2))
                    
                    # Show temporal fields
                    print(f"\n{'='*70}")
                    print("TEMPORAL FIELDS:")
                    print(f"{'='*70}")
                    
                    temporal_keys = ['temporalCoverage', 'acquisitionDate', 'publishDate']
                    
                    for key in temporal_keys:
                        if key in first_scene:
                            print(f"\n{key}:")
                            print(json.dumps(first_scene[key], indent=2))
                    
                    # Print full scene for reference
                    print(f"\n{'='*70}")
                    print("FULL SCENE JSON (first result):")
                    print(f"{'='*70}")
                    print(json.dumps(first_scene, indent=2))
                else:
                    print("\nNo results returned!")
        
        if 'errorCode' in result:
            print(f"\nError: {result.get('errorMessage')}")
    else:
        print(f"\nError response: {response.text}")

def main():
    print("="*70)
    print("M2M API RESPONSE INSPECTOR")
    print("="*70)
    
    # Login
    import sys
    user = None
    token = None
    
    if '__main__' in sys.modules:
        main_dict = sys.modules['__main__'].__dict__
        user = main_dict.get('username')
        token = main_dict.get('api_token')
    
    if user and token:
        print("\nUsing credentials from variables")
    else:
        user = input("\nUSGS username: ")
        token = getpass.getpass("M2M Application Token: ")
    
    api_key = login(user, token)
    
    if not api_key:
        print("Login failed!")
        return
    
    print("✓ Logged in")
    
    # Inspect each dataset
    datasets = ['NAIP', 'NHAP', 'NAPP', 'AERIAL_COMBIN', 'HIGH_RES_ORTHO']
    
    for dataset in datasets:
        inspect_scene_search(api_key, dataset)
        print("\n")

if __name__ == "__main__":
    main()
