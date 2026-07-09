"""
Edmonds Aerial Imagery Pipeline
================================
Unified script combining all five stages:
  1. discover   – Find all aerial imagery datasets covering Edmonds
  2. metadata   – Collect download options and file-size metadata
  3. select     – Pick 1-3 optimal scenes per year by spatial coverage
  4. download   – Download pre-2013 years with ≥95% coverage
  5. qa         – Launch interactive browser-based QA review tool

Usage in Google Colab
─────────────────────
    # Run the full pipeline (stages 1-4, then QA)
    from edmonds_imagery_pipeline import Pipeline
    p = Pipeline(username="your_usgs_user", api_token="your_token")
    p.run_all()

    # Or run individual stages
    p.run_discover()
    p.run_metadata()
    p.run_select()
    p.run_download()
    p.run_qa()

    # Or run from __main__ with stage selection (mirrors your old %run workflow)
    # Just execute this file directly and choose stages interactively.
"""

# ============================================================================
# Imports
# ============================================================================

import csv
import getpass
import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from PIL import Image

# Spatial libraries (optional for stages 1-2/4-5, required for stage 3)
try:
    import geopandas as gpd
    import folium
    from shapely.geometry import box, Polygon
    from shapely.ops import unary_union
    SPATIAL_AVAILABLE = True
except ImportError:
    SPATIAL_AVAILABLE = False

# ============================================================================
# Configuration
# ============================================================================

# Persistent input only — shapefile lives on Google Drive
BOUNDARY_FILE = Path('/content/drive/MyDrive/treedata/City Boundry/Edmonds Boundry.shp')

# Session storage — all outputs live in Colab ephemeral storage.
# Everything here is wiped when the runtime disconnects, which is intentional:
# logs and downloads are for this session only.
SESSION_DIR    = Path('/content/edmonds_session')
DOWNLOAD_DIR   = SESSION_DIR / 'imagery'
LOCAL_QA_DIR   = SESSION_DIR / 'qa'

INVENTORY_FILE = SESSION_DIR / 'Edmonds_Imagery_Inventory.xlsx'
METADATA_FILE  = SESSION_DIR / 'Edmonds_Imagery_Metadata.xlsx'
SCENES_FILE    = SESSION_DIR / 'Edmonds_Optimal_Scenes.xlsx'
COVERAGE_MAP   = SESSION_DIR / 'Edmonds_Coverage_Map.html'
TRACKING_FILE  = SESSION_DIR / 'Download_Tracking.xlsx'
QA_CSV         = SESSION_DIR / 'Image_QA_Results.csv'
FID_JSON       = SESSION_DIR / 'Fiducial_Marks.json'

M2M_API_URL = 'https://m2m.cr.usgs.gov/api/api/json/stable/'

EDMONDS_BBOX = {
    'west': -122.40, 'south': 47.78,
    'east': -122.32, 'north': 47.86,
}

AERIAL_DATASETS = [
    'NHAP',           # 1980-1989
    'NAPP',           # 1987-2007
    'DOQQ',           # Digital Orthophoto Quarter Quads
    'NAIP',           # 2003-present
    'AERIAL_COMBIN',  # Combined aerial
    'HIGH_RES_ORTHO', # High resolution orthophotography
]

MIN_COVERAGE = 85.0   # % coverage threshold for download
MAX_YEAR     = 2012   # Only download pre-2013

QA_PORT = 8889
CSV_FIELDS = ["filepath", "year", "dataset", "filename", "status",
              "rotation", "num_fiducials", "timestamp", "reviewer"]

# ============================================================================
# USGS M2M API Client (single shared class for all stages)
# ============================================================================

class USGSM2M:
    """Thin wrapper around the USGS Machine-to-Machine (M2M) REST API."""

    def __init__(self, username: str, token: str):
        self.api_url = M2M_API_URL
        self.session = requests.Session()
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        _retry = Retry(
            total=3, backoff_factor=2,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=['POST', 'GET'],
            raise_on_status=False,
        )
        self.session.mount('https://', HTTPAdapter(max_retries=_retry))
        self.api_key: str | None = None
        self._login(username, token)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _login(self, username: str, token: str) -> str:
        url = f"{self.api_url}login-token"
        resp = self.session.post(
            url,
            json={"username": username, "token": token},
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code != 200:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text[:200]
            raise RuntimeError(f"Login failed ({resp.status_code}): {detail}")

        result = resp.json()
        if result.get('errorCode'):
            raise RuntimeError(f"Login failed: {result.get('errorMessage')}")

        self.api_key = result['data']
        self._username = username
        self._token    = token
        print("✓ Logged in to M2M API")
        return self.api_key

    def logout(self):
        self.session.post(
            f"{self.api_url}logout",
            headers={"X-Auth-Token": self.api_key},
        )

    # ------------------------------------------------------------------
    # Resilient POST — retries and re-authenticates on connection drop
    # ------------------------------------------------------------------

    def _post(self, endpoint: str, payload: dict) -> dict:
        """POST to M2M API, transparently re-authenticating if the
        session was dropped (e.g. after a long stage 1-3 run)."""
        url     = f"{self.api_url}{endpoint}"
        headers = {"X-Auth-Token": self.api_key}
        for attempt in range(3):
            try:
                resp = self.session.post(url, json=payload, headers=headers)
                if resp.status_code == 401:
                    print("  ⚠ Session expired — re-authenticating...")
                    self._login(self._username, self._token)
                    headers = {"X-Auth-Token": self.api_key}
                    continue
                if resp.status_code == 200:
                    result = resp.json()
                    return result.get('data') if 'data' in result else result
                return {}
            except requests.exceptions.ConnectionError:
                print(f"  ⚠ Connection error (attempt {attempt+1}/3) — "
                      f"re-authenticating...")
                time.sleep(5 * (attempt + 1))
                self._login(self._username, self._token)
                headers = {"X-Auth-Token": self.api_key}
        return {}

    # ------------------------------------------------------------------
    # Dataset helpers
    # ------------------------------------------------------------------

    def dataset_exists(self, dataset_name: str) -> bool:
        data = self._post('dataset-search', {"datasetName": dataset_name})
        return bool(data)

    # ------------------------------------------------------------------
    # Scene search
    # ------------------------------------------------------------------

    def search_scenes(self, dataset: str, max_results: int = 1000) -> list:
        """Return scene results for Edmonds bounding box."""
        resp = self.session.post(
            f"{self.api_url}scene-search",
            json={
                "datasetName": dataset,
                "maxResults": max_results,
                "startingNumber": 1,
                "sceneFilter": {
                    "spatialFilter": {
                        "filterType": "mbr",
                        "lowerLeft":  {"latitude": EDMONDS_BBOX['south'],
                                       "longitude": EDMONDS_BBOX['west']},
                        "upperRight": {"latitude": EDMONDS_BBOX['north'],
                                       "longitude": EDMONDS_BBOX['east']},
                    }
                },
            },
            headers={"X-Auth-Token": self.api_key},
        )
        if resp.status_code == 200:
            result = resp.json()
            if result.get('errorCode'):
                return []
            return result.get('data', {}).get('results', [])
        return []

    def get_entity_ids(self, dataset: str, max_results: int = 100) -> list[str]:
        scenes = self.search_scenes(dataset, max_results)
        return [s['entityId'] for s in scenes if s.get('entityId')]

    # ------------------------------------------------------------------
    # Download helpers
    # ------------------------------------------------------------------

    def get_download_options(self, dataset: str, entity_ids: list) -> list:
        result = self._post('download-options',
                            {"datasetName": dataset, "entityIds": entity_ids})
        return result if isinstance(result, list) else []

    def download_request(self, downloads: list) -> dict:
        result = self._post('download-request', {"downloads": downloads})
        return result if isinstance(result, dict) else {}

    def download_retrieve(self, label: str) -> dict:
        result = self._post('download-retrieve', {"label": label})
        return result if isinstance(result, dict) else {}


# ============================================================================
# Stage 1 – Discover
# ============================================================================

def stage_discover(api: USGSM2M) -> pd.DataFrame:
    """Search all aerial datasets for Edmonds coverage.

    Returns a DataFrame saved to INVENTORY_FILE.
    """
    print("\n" + "=" * 70)
    print("STAGE 1 · DISCOVER AERIAL IMAGERY FOR EDMONDS, WA")
    print("=" * 70)

    inventory = []

    for dataset in AERIAL_DATASETS:
        print(f"\n[Searching] {dataset}...", end=" ")

        if not api.dataset_exists(dataset):
            print("✗ Not found")
            continue

        scenes = api.search_scenes(dataset)
        if scenes is None:
            print("✗ Error / no access")
            continue
        if not scenes:
            print("○ No scenes")
            continue

        print(f"✓ {len(scenes)} scenes")

        dates = []
        for s in scenes:
            start = s.get('temporalCoverage', {}).get('startDate')
            if start:
                try:
                    dates.append(datetime.strptime(start[:10], '%Y-%m-%d'))
                except ValueError:
                    pass

        if dates:
            date_range = f"{min(dates).year}–{max(dates).year}"
            earliest   = min(dates).strftime('%Y-%m-%d')
            latest     = max(dates).strftime('%Y-%m-%d')
        else:
            date_range = earliest = latest = 'Unknown'

        inventory.append({
            'Dataset':    dataset,
            'Scene_Count': len(scenes),
            'Date_Range':  date_range,
            'Earliest':    earliest,
            'Latest':      latest,
            'Status':      'Available',
        })
        print(f"    Date range: {date_range}")
        print(f"    Sample ID : {scenes[0].get('displayId', 'N/A')}")

    if not inventory:
        print("\n✗ No imagery found for Edmonds!")
        return pd.DataFrame()

    df = pd.DataFrame(inventory)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(INVENTORY_FILE, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Inventory', index=False)
        pd.DataFrame({
            'Metric': ['Total Datasets', 'Total Scenes', 'Earliest', 'Latest', 'Run Date'],
            'Value':  [len(df), int(df['Scene_Count'].sum()),
                       df['Earliest'].min(), df['Latest'].max(),
                       datetime.now().strftime('%Y-%m-%d %H:%M')],
        }).to_excel(writer, sheet_name='Summary', index=False)

    print(f"\n✓ Inventory saved → {INVENTORY_FILE}")
    print(f"  Datasets: {len(df)} · Scenes: {df['Scene_Count'].sum()}")
    return df


# ============================================================================
# Stage 2 – Metadata
# ============================================================================

def stage_metadata(api: USGSM2M, inventory_df: pd.DataFrame) -> pd.DataFrame:
    """Collect download options (file sizes, availability) for all scenes.

    Returns a DataFrame saved to METADATA_FILE.
    """
    print("\n" + "=" * 70)
    print("STAGE 2 · COLLECT SCENE METADATA")
    print("=" * 70)

    all_rows = []

    for dataset in inventory_df['Dataset'].unique():
        count = inventory_df.loc[inventory_df['Dataset'] == dataset, 'Scene_Count'].iloc[0]
        print(f"\n[{dataset}] {count} scenes – querying download options...")

        entity_ids = api.get_entity_ids(dataset, max_results=100)
        if not entity_ids:
            print("  ✗ Could not retrieve entity IDs")
            continue

        opts = api.get_download_options(dataset, entity_ids)
        if not opts:
            print("  ○ No download options available")
            continue

        print(f"  ✓ {len(opts)} products")
        for opt in opts:
            filesize = opt.get('filesize')
            all_rows.append({
                'Dataset':           dataset,
                'Entity_ID':         opt.get('entityId'),
                'Display_ID':        opt.get('displayId', 'N/A'),
                'Product_Name':      opt.get('productName', 'N/A'),
                'Product_Code':      opt.get('productCode', 'N/A'),
                'Available':         opt.get('available', False),
                'File_Size_MB':      filesize / 1024 / 1024 if filesize else None,
                'Download_System':   opt.get('downloadSystem', 'N/A'),
                'Secondary_Downloads': len(opt.get('secondaryDownloads', [])),
            })

    if not all_rows:
        print("\n✗ No metadata collected.")
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    size_summary = df.groupby('Dataset').agg(
        Count=('File_Size_MB', 'count'),
        Total_MB=('File_Size_MB', 'sum'),
        Mean_MB=('File_Size_MB', 'mean'),
        Min_MB=('File_Size_MB', 'min'),
        Max_MB=('File_Size_MB', 'max'),
        Available=('Available', 'sum'),
    ).round(2)

    with pd.ExcelWriter(METADATA_FILE, engine='openpyxl') as writer:
        inventory_df.to_excel(writer, sheet_name='Inventory', index=False)
        df.to_excel(writer, sheet_name='Download_Options', index=False)
        size_summary.to_excel(writer, sheet_name='Size_Summary')

    total_mb = df['File_Size_MB'].sum()
    print(f"\n✓ Metadata saved → {METADATA_FILE}")
    print(f"  Total: {len(df)} products · {total_mb:.1f} MB ({total_mb/1024:.1f} GB)")
    return df


# ============================================================================
# Stage 3 – Select optimal scenes
# ============================================================================

def _parse_footprint(scene: dict):
    """Return a Shapely geometry from scene spatial metadata, or None."""
    spatial = scene.get('spatialCoverage')
    if spatial and 'coordinates' in spatial:
        try:
            ring = spatial['coordinates'][0]
            return Polygon(ring)
        except Exception as e:
            print(f"    Warning: spatialCoverage parse error: {e}")

    bounds = scene.get('spatialBounds')
    if bounds:
        try:
            w = bounds.get('west')  or bounds.get('longitudeMin')
            s = bounds.get('south') or bounds.get('latitudeMin')
            e = bounds.get('east')  or bounds.get('longitudeMax')
            n = bounds.get('north') or bounds.get('latitudeMax')
            if all(v is not None for v in [w, s, e, n]):
                return box(float(w), float(s), float(e), float(n))
        except Exception as ex:
            print(f"    Warning: spatialBounds parse error: {ex}")

    return None


def _coverage_pct(footprint, boundary) -> float:
    if footprint is None:
        return 0.0
    try:
        return (footprint.intersection(boundary).area / boundary.area) * 100
    except Exception:
        return 0.0


def _greedy_select(scenes_df: pd.DataFrame, boundary,
                   min_gain_pct: float = 1.0) -> pd.DataFrame:
    """Greedy coverage-maximising tile selection per year.

    Keeps adding scenes from the same year as long as each additional tile
    contributes at least min_gain_pct new coverage of the Edmonds boundary.
    There is no hard cap on scene count — if a year needs 8 tiles to cover
    the city, all 8 are selected.

    Parameters
    ----------
    min_gain_pct : minimum additional coverage (%) a tile must contribute to
                   be worth including.  Default 1.0% — low enough to pick up
                   small gap-fillers at city edges, high enough to skip tiles
                   that are pure duplicates of already-covered ground.
    """
    selected = []
    for year in sorted(scenes_df['Year'].unique()):
        year_df = scenes_df[scenes_df['Year'] == year].sort_values(
            'Coverage_Percent', ascending=False
        )
        picked, covered = [], None
        for _, row in year_df.iterrows():
            geom = row['Geometry']
            if covered is None:
                # Always take the highest-coverage tile as the anchor
                picked.append(row)
                covered = geom.intersection(boundary)
            else:
                new_area  = geom.intersection(boundary)
                extra_pct = (new_area.difference(covered).area
                             / boundary.area) * 100
                if extra_pct >= min_gain_pct:
                    picked.append(row)
                    covered = covered.union(new_area)

        final_cov = (covered.area / boundary.area * 100) if covered else 0.0
        print(f"  {year}: {len(picked)} tile(s) → {final_cov:.1f}% coverage")
        selected.extend(picked)

    return pd.DataFrame(selected)


def stage_select(api: USGSM2M) -> pd.DataFrame:
    """Query spatial footprints, select 1-3 best scenes per year.

    Returns a DataFrame saved to SCENES_FILE.
    """
    if not SPATIAL_AVAILABLE:
        raise ImportError(
            "geopandas / shapely / folium are required for stage_select. "
            "Install with: pip install geopandas shapely folium"
        )

    print("\n" + "=" * 70)
    print("STAGE 3 · SELECT OPTIMAL SCENES")
    print("=" * 70)

    # Load boundary
    print("\n[1/3] Loading Edmonds boundary...")
    gdf = gpd.read_file(BOUNDARY_FILE)
    if gdf.crs and str(gdf.crs) != 'EPSG:4326':
        print(f"  Reprojecting from {gdf.crs} → EPSG:4326")
        gdf = gdf.to_crs('EPSG:4326')
    boundary = gdf.geometry.iloc[0]
    print(f"  ✓ Bounds: {boundary.bounds}")

    # Query footprints
    print("\n[2/3] Querying scene footprints...")
    all_scenes = []

    for dataset in AERIAL_DATASETS:
        print(f"\n[{dataset}]")
        scenes = api.search_scenes(dataset, max_results=250)
        if not scenes:
            print("  ✗ No scenes")
            continue

        valid = skipped = 0
        for s in scenes:
            start = s.get('temporalCoverage', {}).get('startDate', '')
            try:
                year = int(start[:4])
            except (ValueError, TypeError):
                continue

            fp = _parse_footprint(s)
            if fp is None:
                skipped += 1
                continue

            valid += 1
            all_scenes.append({
                'Dataset':          dataset,
                'Entity_ID':        s.get('entityId'),
                'Display_ID':       s.get('displayId', 'N/A'),
                'Year':             year,
                'Acquisition_Date': start[:10] if start else 'Unknown',
                'Coverage_Percent': _coverage_pct(fp, boundary),
                'Geometry':         fp,
            })

        print(f"  ✓ Valid footprints: {valid} / {len(scenes)}"
              + (f"  ⚠ No footprint: {skipped}" if skipped else ""))

    if not all_scenes:
        print("\n✗ No valid scene footprints found.")
        return pd.DataFrame()

    scenes_df = pd.DataFrame(all_scenes)
    print(f"\n  Total valid scenes: {len(scenes_df)}")

    # Select
    print("\n[3/3] Selecting optimal scenes (up to 3/year)...")
    selected = _greedy_select(scenes_df, boundary, min_gain_pct=0.5)
    print(f"\n  ✓ Selected {len(selected)} scenes across {selected['Year'].nunique()} years")

    # Save
    export = selected.drop(columns=['Geometry']).copy()

    # Compute true unioned coverage per year (no double-counting overlaps)
    year_true_cov = {}
    for year in selected['Year'].unique():
        year_geoms = selected[selected['Year'] == year]['Geometry']
        union = unary_union(list(year_geoms.apply(lambda g: g.intersection(boundary))))
        year_true_cov[year] = (union.area / boundary.area) * 100
    export['True_Coverage_Percent'] = export['Year'].map(year_true_cov)

    with pd.ExcelWriter(SCENES_FILE, engine='openpyxl') as writer:
        export.to_excel(writer, sheet_name='Optimal_Scenes', index=False)
        pd.DataFrame({
            'Year': sorted(year_true_cov),
            'True_Coverage_Pct': [year_true_cov[y] for y in sorted(year_true_cov)],
            'Tile_Count': [export[export['Year']==y].shape[0] for y in sorted(year_true_cov)],
            'Dataset': [export[export['Year']==y]['Dataset'].iloc[0] for y in sorted(year_true_cov)],
        }).to_excel(writer, sheet_name='Year_Summary', index=False)
        export.groupby('Dataset').agg(
            Year_Min=('Year', 'min'), Year_Max=('Year', 'max'),
            Count=('Year', 'count'), Avg_Coverage=('Coverage_Percent', 'mean'),
        ).to_excel(writer, sheet_name='Dataset_Summary')

    # Coverage map
    cx = (EDMONDS_BBOX['south'] + EDMONDS_BBOX['north']) / 2
    cy = (EDMONDS_BBOX['west']  + EDMONDS_BBOX['east'])  / 2
    m  = folium.Map(location=[cx, cy], zoom_start=13)
    folium.GeoJson(
        boundary, name='Edmonds Boundary',
        style_function=lambda _: {'fillColor': 'transparent', 'color': 'red', 'weight': 3},
    ).add_to(m)
    colors = {'NHAP': 'blue', 'NAPP': 'green', 'NAIP': 'purple',
              'AERIAL_COMBIN': 'orange', 'HIGH_RES_ORTHO': 'darkblue'}
    for _, row in selected.iterrows():
        c = colors.get(row['Dataset'], 'gray')
        folium.GeoJson(
            row['Geometry'],
            style_function=lambda _, c=c: {'fillColor': c, 'color': c,
                                           'weight': 2, 'fillOpacity': 0.3},
            tooltip=(f"{row['Dataset']} – {row['Year']} – {row['Display_ID']}"
                     f"<br>Coverage: {row['Coverage_Percent']:.1f}%"),
        ).add_to(m)
    folium.LayerControl().add_to(m)
    m.save(str(COVERAGE_MAP))

    print(f"✓ Scenes saved → {SCENES_FILE}")
    print(f"✓ Map saved    → {COVERAGE_MAP}")
    return selected


# ============================================================================
# Stage 4 – Download
# ============================================================================

def _download_file(url: str, filepath: Path) -> bool:
    try:
        resp = requests.get(url, stream=True)
        resp.raise_for_status()
        total = int(resp.headers.get('content-length', 0))
        with open(filepath, 'wb') as f:
            if total == 0:
                f.write(resp.content)
            else:
                done = 0
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
                    done += len(chunk)
                    print(f"    {done/total*100:.1f}%", end='\r')
        print(f"    ✓ {filepath.name}")
        return True
    except Exception as e:
        print(f"    ✗ {e}")
        return False


def _prepare_download_requests(api: USGSM2M, scenes_df: pd.DataFrame) -> list[dict]:
    """Build the list of {entityId, productId, ...} dicts to submit.

    Rules applied per scene:
    - Camera calibration files are always skipped.
    - When multiple imagery products exist for the same scene, only the
      highest-priority one is kept (Full Resolution > High Resolution >
      Medium Resolution > Compressed > anything else).
    """
    # Keywords that identify non-imagery ancillary files to skip entirely
    SKIP_KEYWORDS = ('camera calibration', 'calibration report', 'cal report')

    # Preferred product name keywords, highest priority first.
    # The first match for a given scene wins.
    PRODUCT_PRIORITY = (
        'full resolution',
        'high resolution',
        'medium resolution',
        'compressed',
    )

    def _product_rank(name: str) -> int:
        """Lower = higher priority. Unrecognised products rank last."""
        n = name.lower()
        for rank, keyword in enumerate(PRODUCT_PRIORITY):
            if keyword in n:
                return rank
        return len(PRODUCT_PRIORITY)

    reqs = []
    for dataset in scenes_df['Dataset'].unique():
        ds_scenes = scenes_df[scenes_df['Dataset'] == dataset]
        print(f"\n[{dataset}] {len(ds_scenes)} scenes – querying options...")

        entity_ids = ds_scenes['Entity_ID'].tolist()
        opts = api.get_download_options(dataset, entity_ids)
        if not opts:
            print("  ✗ No download options")
            continue

        # Group available, non-calibration products by entityId so we can
        # pick only the best one per scene.
        by_entity: dict[str, list[dict]] = {}
        skipped_cal = 0
        for opt in opts:
            if not opt.get('available', False):
                continue
            if not opt.get('id'):
                continue
            name = opt.get('productName', '')
            if any(kw in name.lower() for kw in SKIP_KEYWORDS):
                skipped_cal += 1
                continue
            eid = opt.get('entityId')
            by_entity.setdefault(eid, []).append(opt)

        if skipped_cal:
            print(f"  ⊘ Skipped {skipped_cal} camera calibration file(s)")

        for eid, candidates in by_entity.items():
            match = ds_scenes[ds_scenes['Entity_ID'] == eid]
            if match.empty:
                continue

            # Pick the highest-priority product for this scene
            best = min(candidates, key=lambda o: _product_rank(o.get('productName', '')))
            row = match.iloc[0]
            reqs.append({
                'entityId':    eid,
                'productId':   best['id'],
                'year':        row['Year'],
                'display_id':  row['Display_ID'],
                'dataset':     dataset,
                'product_name': best.get('productName', 'Unknown'),
            })
            print(f"  ✓ {row['Display_ID']} – {best.get('productName', '')}")

    return reqs


def _poll_for_downloads(api: USGSM2M, label: str,
                        expected: int,
                        poll_interval: int = 15,
                        max_wait: int = 600) -> list[dict]:
    """Poll download-retrieve until all expected files are ready or timeout.

    Parameters
    ----------
    label         : download label returned by download-request
    expected      : number of files we are waiting on
    poll_interval : seconds between polls (default 15)
    max_wait      : total seconds before giving up (default 600 = 10 min)
    """
    elapsed = 0
    collected: list[dict] = []
    seen_ids: set = set()

    print(f"  Polling for {expected} file(s) (label={label}, "
          f"up to {max_wait//60} min)...")

    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval

        dl_data = api.download_retrieve(label)
        available = dl_data.get('available', [])
        queued    = dl_data.get('queued', [])

        # On first poll log the full response structure so we can verify
        # USGS is acknowledging the request correctly
        if elapsed == poll_interval:
            keys = {k: (len(v) if isinstance(v, list) else v)
                    for k, v in dl_data.items()}
            print(f"    [first poll response] {keys}")
            if not available and not queued:
                print(f"    [full dump] {json.dumps(dl_data, indent=4)[:800]}")

        # Accumulate newly ready items
        for item in available:
            key = item.get('entityId') or item.get('url')
            if key and key not in seen_ids:
                seen_ids.add(key)
                collected.append(item)

        ready_count = len(collected)
        still_queued = len(queued)
        print(f"    {elapsed:>4}s elapsed · {ready_count}/{expected} ready"
              f"{f' · {still_queued} still queued' if still_queued else ''}")

        if ready_count >= expected:
            break

        # Only exit early when we've received *some* files AND the queue
        # is now drained — that means USGS has delivered everything it will.
        # Do NOT exit when queued=[] with 0 ready: USGS regularly omits the
        # queued list while files are still being prepared server-side.
        if ready_count > 0 and not queued and ready_count >= expected:
            break

    if collected:
        print(f"  ✓ Polling complete: {len(collected)}/{expected} retrieved")
    else:
        print(f"  ⚠ Polling timed out after {max_wait}s with 0 files ready. "
              "Re-run stage 4 to retry the remaining files.")
    return collected


def _execute_downloads(api: USGSM2M, download_reqs: list[dict]) -> list[dict]:
    if not download_reqs:
        print("No downloads to execute.")
        return []

    results = []
    batch_size = 25   # smaller batches reduce USGS cold-storage queue pressure
    batches = [download_reqs[i:i+batch_size]
               for i in range(0, len(download_reqs), batch_size)]

    for batch_num, batch in enumerate(batches, 1):
        print(f"\n[Batch {batch_num}/{len(batches)}] {len(batch)} file(s)")

        api_batch = [{'entityId': r['entityId'], 'productId': r['productId']}
                     for r in batch]
        result = api.download_request(api_batch)
        avail_now = len(result.get('availableDownloads', []))
        preparing = len(result.get('preparingDownloads', []))
        failed_now = len(result.get('failed', []))
        print(f"  Request result: {avail_now} immediate · "
              f"{preparing} preparing · {failed_now} failed")
        if result.get('failed'):
            for f in result['failed'][:3]:
                print(f"    failed: {f}")

        # Track which entityIds have already been saved in this batch so
        # that duplicate items in the USGS response (one per product variant)
        # never cause the same scene to be downloaded more than once.
        saved_entities: set[str] = set()

        def _save_items(items: list[dict]):
            """Download each item, skipping duplicates and already-saved files."""
            for item in items:
                url = item.get('url')
                eid = item.get('entityId')
                if not url or not eid:
                    continue
                if eid in saved_entities:
                    continue  # duplicate in USGS response
                req = next((r for r in batch if r['entityId'] == eid), None)
                if not req:
                    continue
                saved_entities.add(eid)
                dest = DOWNLOAD_DIR / str(req['year']) / req['dataset']
                dest.mkdir(parents=True, exist_ok=True)
                # Use our own display_id as the filename — it's the stable
                # human-readable ID. The 'displayId' in the USGS response can
                # be a numeric surrogate key (e.g. "932437") that is not useful.
                fp = dest / f"{req['display_id']}.tif"
                if fp.exists() and fp.stat().st_size > 0:
                    print(f"\n  [{req['year']}] {req['display_id']} → already exists, skipping")
                    results.append({
                        'Year':         req['year'],
                        'Dataset':      req['dataset'],
                        'Display_ID':   req['display_id'],
                        'Product':      req['product_name'],
                        'Entity_ID':    eid,
                        'Filepath':     str(fp),
                        'Status':       'Skipped (exists)',
                        'File_Size_MB': fp.stat().st_size / 1024**2,
                    })
                    continue
                print(f"\n  [{req['year']}] {req['display_id']} → {fp.name}")
                ok = _download_file(url, fp)
                results.append({
                    'Year':         req['year'],
                    'Dataset':      req['dataset'],
                    'Display_ID':   req['display_id'],
                    'Product':      req['product_name'],
                    'Entity_ID':    eid,
                    'Filepath':     str(fp),
                    'Status':       'Success' if ok else 'Failed',
                    'File_Size_MB': fp.stat().st_size / 1024**2 if ok else 0,
                })

        # ── Immediately available files ──────────────────────────────────
        available_now = result.get('availableDownloads', [])
        if available_now:
            print(f"  ✓ {len(available_now)} available immediately")
            _save_items(available_now)

        # ── Files that need server-side preparation ──────────────────────
        preparing = result.get('preparingDownloads', [])
        if preparing:
            # Extract the label USGS uses to track this batch.
        # Log the full preparingDownloads structure so we can see every
        # field USGS returns — the label field name varies by dataset.
            print(f"  [preparing[0]] {preparing[0] if preparing else 'empty'}")
            print(f"  [result keys] { {k: (len(v) if isinstance(v, list) else v) for k, v in result.items()} }")

            # newRecords is a dict of {downloadId: batch_label}.
            # All entries share the same batch label — that is what
            # download-retrieve expects, NOT the individual downloadId.
            label = None
            new_records = result.get('newRecords')
            if isinstance(new_records, dict) and new_records:
                label = next(iter(new_records.values()))  # e.g. 'm2m_2267045480_20260516141035'
            if not label and isinstance(new_records, list) and new_records:
                label = (new_records[0].get('label')
                         or new_records[0].get('downloadId'))
            # Fallback: individual downloadId from preparingDownloads item
            if not label:
                for candidate in preparing:
                    label = candidate.get('downloadId') or candidate.get('label')
                    if label:
                        break

            print(f"  [extracted label] {label}")

            if label:
                ready_items = _poll_for_downloads(
                    api, label,
                    expected=len(preparing),
                    poll_interval=20,   # USGS typically needs 1-5 min to prepare
                    max_wait=1800,      # wait up to 30 min for large batches
                )
                if ready_items:
                    print(f"  ✓ {len(ready_items)} file(s) ready – downloading")
                    _save_items(ready_items)
                else:
                    print("  ⚠ Timed out waiting for prepared downloads. "
                          "Re-run stage 4 later or check EarthExplorer.")
            else:
                print("  ⚠ Could not determine download label. "
                      "Check EarthExplorer for prepared downloads.")

        failed = result.get('failed', [])
        if failed:
            print(f"  ✗ {len(failed)} request(s) failed at USGS side:")
            for f in failed[:5]:
                print(f"    {f}")

        if batch_num < len(batches):
            print("\n  Waiting 10 s before next batch...")
            time.sleep(10)

    return results


def stage_download(api: USGSM2M) -> pd.DataFrame:
    """Download scenes for pre-MAX_YEAR years where tiles from a single flight
    collectively cover >= MIN_COVERAGE of Edmonds.

    Years that don't reach the threshold from their own tiles are skipped —
    cross-year mosaics are not valid for temporal analysis.

    Returns a tracking DataFrame saved to TRACKING_FILE.
    """
    print("\n" + "=" * 70)
    print("STAGE 4 · DOWNLOAD HIGH-COVERAGE PRE-2013 IMAGERY")
    print("=" * 70)

    print(f"\n[1/3] Loading optimal scenes from {SCENES_FILE}...")
    scenes_df = pd.read_excel(SCENES_FILE, sheet_name='Optimal_Scenes')

    pre = scenes_df[scenes_df['Year'] <= MAX_YEAR]

    # Use True_Coverage_Percent (unioned footprint, no double-counting).
    # Fall back to summed Coverage_Percent if the column isn't present
    # (e.g. Excel written by an older version of this script).
    if 'True_Coverage_Percent' in pre.columns:
        year_cov = pre.groupby('Year')['True_Coverage_Percent'].first()
        cov_label = "true unioned"
    else:
        year_cov = pre.groupby('Year')['Coverage_Percent'].sum()
        cov_label = "summed (re-run stage 3 for accurate values)"

    print(f"\n  Coverage by year (pre-{MAX_YEAR + 1}, {cov_label}):")
    for yr in sorted(year_cov.index):
        meets = year_cov[yr] >= MIN_COVERAGE
        flag = "✓" if meets else "✗"
        print(f"    {flag} {yr}: {year_cov[yr]:.1f}%"
              + ("" if meets else f"  (below {MIN_COVERAGE:.0f}% threshold — skipped)"))

    qualifying_years = year_cov[year_cov >= MIN_COVERAGE].index
    target = pre[pre['Year'].isin(qualifying_years)]

    print(f"\n  Qualifying years : {sorted(qualifying_years)}")
    print(f"  Scenes to download: {len(target)}")

    if target.empty:
        print("\n✗ No years meet the single-flight coverage threshold. "
              "Consider lowering MIN_COVERAGE.")
        return pd.DataFrame()

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[2/3] Preparing download requests...")
    dl_reqs = _prepare_download_requests(api, target)
    print(f"\n  Total requests: {len(dl_reqs)}")

    print("\n[3/3] Executing downloads...")
    results = _execute_downloads(api, dl_reqs)

    if results:
        new_df = pd.DataFrame(results)

        # Merge with any existing log so re-runs don't create duplicate rows.
        # Entity_ID is the stable key — a later run's record overwrites the
        # earlier one (e.g. a previously-failed file that now succeeded).
        if TRACKING_FILE.exists():
            existing = pd.read_excel(TRACKING_FILE)
            combined = (
                pd.concat([existing, new_df])
                .drop_duplicates(subset=['Entity_ID'], keep='last')
                .reset_index(drop=True)
            )
        else:
            combined = new_df

        combined.to_excel(TRACKING_FILE, index=False)

        success  = (combined['Status'] == 'Success').sum()
        skipped  = combined['Status'].str.startswith('Skipped').sum()
        failed   = (combined['Status'] == 'Failed').sum()
        total_mb = combined.loc[combined['Status'] == 'Success', 'File_Size_MB'].sum()
        print(f"\n✓ Tracking log: {len(combined)} total entries")
        print(f"  Success: {success}  ·  Skipped: {skipped}  ·  Failed: {failed}")
        print(f"  Downloaded: {total_mb:.1f} MB  ·  log → {TRACKING_FILE}")
        return combined

    print("\n○ No downloads completed.")
    return pd.DataFrame()


# ============================================================================
# Stage 5 – QA Server
# ============================================================================

# ── HTML for the QA browser app ─────────────────────────────────────────────

QA_APP_HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Aerial Imagery QA Tool</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body {
  background:#0d1117; color:#c9d1d9;
  font-family:monospace,sans-serif; font-size:12px;
  height:100vh; overflow:hidden; display:flex; flex-direction:column;
}
.topbar {
  display:flex; align-items:center; justify-content:space-between;
  padding:10px 16px; background:#161b22; border-bottom:1px solid #21262d;
}
.topbar .title { font-size:14px; font-weight:700; color:#58a6ff; }
.fid-badge {
  padding:4px 10px; border-radius:4px; font-size:11px; font-weight:700;
  background:#1a3a2a; color:#00e676; border:1px solid #2e7d32; display:none;
}
.fid-badge.active { display:inline-block; }
.main { display:flex; flex:1; overflow:hidden; }
.canvas-area {
  flex:1; display:flex; flex-direction:column;
  align-items:center; justify-content:center; position:relative;
}
#imgCanvas { border:2px solid #21262d; border-radius:8px; max-width:90%; max-height:70vh; cursor:default; }
#imgCanvas.fid-mode { cursor:crosshair; border-color:#2e7d32; }
.ctrls { display:flex; gap:8px; margin-top:12px; flex-wrap:wrap; align-items:center; justify-content:center; }
.btn {
  background:#21262d; border:1px solid #30363d; color:#c9d1d9;
  padding:8px 16px; border-radius:5px; cursor:pointer;
  font-family:inherit; font-size:11px; font-weight:600;
}
.btn-accept { background:#2e7d32; color:#fff; }
.btn-reject { background:#c62828; color:#fff; }
.btn-fid    { background:#1a3a2a; color:#00e676; border-color:#2e7d32; }
.btn-fid.active { background:#2e7d32; color:#fff; }
.slider-wrap { display:flex; align-items:center; gap:8px; }
.slider { width:200px; }
.rot-val { color:#58a6ff; min-width:45px; text-align:right; }
.panel {
  width:260px; background:#161b22; border-left:1px solid #21262d;
  padding:16px; display:flex; flex-direction:column; gap:14px; overflow-y:auto;
}
.sec-title { color:#484f58; font-size:9px; text-transform:uppercase; letter-spacing:0.8px; margin-bottom:8px; }
.row { display:flex; justify-content:space-between; margin-bottom:4px; }
.row .lbl { color:#484f58; }
.row .val { color:#c9d1d9; font-weight:600; }
.fid-list { font-size:10px; color:#484f58; line-height:2; }
.fid-list .placed { color:#00e676; font-weight:700; }
.dot-grid { display:flex; flex-wrap:wrap; gap:2px; }
.dot { width:6px; height:6px; border-radius:1px; background:#21262d; transition:background 0.1s; }
.dot.cur { background:#58a6ff; }
.dot.accept { background:#2e7d32; }
.dot.reject { background:#c62828; }
.setup-ov {
  position:fixed; inset:0; background:rgba(0,0,0,0.85);
  display:flex; align-items:center; justify-content:center; z-index:100;
}
.setup-box {
  background:#161b22; border:1px solid #30363d; border-radius:10px;
  padding:24px 28px; max-width:360px; width:90%;
}
.setup-box h2 { color:#58a6ff; font-size:15px; margin-bottom:16px; }
.setup-box input {
  width:100%; background:#0d1117; border:1px solid #30363d;
  color:#c9d1d9; padding:8px; border-radius:5px;
  font-family:inherit; font-size:12px; margin-bottom:14px;
}
.btn-start {
  width:100%; background:#2e7d32; border:none; color:#fff;
  padding:10px; border-radius:6px; cursor:pointer;
  font-family:inherit; font-size:12px; font-weight:700;
}
</style>
</head>
<body>

<div class="setup-ov" id="setupOv">
  <div class="setup-box">
    <h2>Aerial Imagery QA</h2>
    <label style="color:#484f58;font-size:10px;display:block;margin-bottom:5px">Your name or ID</label>
    <input type="text" id="reviewerInput" placeholder="e.g. Kam"
           onkeydown="if(event.key==='Enter'&&this.value.trim())startSession()">
    <button class="btn-start" onclick="startSession()">Start QA</button>
  </div>
</div>

<div class="topbar">
  <span class="title">AERIAL IMAGERY QA</span>
  <div style="display:flex;gap:8px;align-items:center">
    <span class="fid-badge" id="fidBadge">FIDUCIAL MODE — click all marks, F to finish</span>
    <span id="zoomVal" style="color:#484f58;font-size:10px">100%</span>
    <span id="navPos">— / —</span>
  </div>
</div>

<div class="main">
  <div class="canvas-area">
    <canvas id="imgCanvas" width="800" height="800"></canvas>
    <div class="ctrls">
      <div class="slider-wrap">
        <button class="btn" onclick="rotate(-90)">CCW 90</button>
        <input type="range" id="rotSlider" class="slider" min="0" max="360" value="0" step="1"
               oninput="rotation=parseInt(this.value);render()">
        <span class="rot-val" id="rotVal">0</span>
        <button class="btn" onclick="rotate(90)">CW 90</button>
      </div>
    </div>
    <div class="ctrls">
      <button class="btn btn-reject" onclick="mark('REJECT')">Reject [R]</button>
      <button class="btn" onclick="mark('SKIP')">Skip [S]</button>
      <button class="btn btn-fid" id="fidBtn" onclick="toggleFidMode()">Fiducials [F]</button>
      <button class="btn btn-accept" onclick="mark('ACCEPT')">Accept [A]</button>
    </div>
    <div style="color:#484f58;font-size:10px;margin-top:8px;text-align:center" id="hintText">
      Scroll=zoom · Ctrl+drag=pan · DblClick=reset · Arrows=rotate · F=fiducials · A/R/S=accept/reject/skip
    </div>
  </div>

  <div class="panel">
    <div>
      <div class="sec-title">Image</div>
      <div class="row"><span class="lbl">Year</span>    <span class="val" id="iYear">—</span></div>
      <div class="row"><span class="lbl">Dataset</span> <span class="val" id="iDataset">—</span></div>
      <div class="row"><span class="lbl">File</span>    <span class="val" id="iFile" style="font-size:10px">—</span></div>
    </div>
    <div>
      <div class="sec-title">Fiducial Marks <span id="fidCount" style="color:#484f58">(0)</span></div>
      <div class="fid-list" id="fidList" style="max-height:140px;overflow-y:auto"></div>
      <button class="btn" style="font-size:10px;padding:4px 8px;margin-top:6px"
              onclick="clearFiducials()">Clear</button>
    </div>
    <div>
      <div class="sec-title">Session</div>
      <div class="row"><span class="lbl">Reviewer</span> <span class="val" id="sReviewer">—</span></div>
      <div class="row"><span class="lbl">Reviewed</span> <span class="val" id="sReviewed">0 / 0</span></div>
      <div class="row"><span class="lbl">Accepted</span> <span class="val" style="color:#4CAF50" id="sAccept">0</span></div>
      <div class="row"><span class="lbl">Rejected</span> <span class="val" style="color:#f44336" id="sReject">0</span></div>
    </div>
    <div>
      <div class="sec-title">Progress</div>
      <div class="dot-grid" id="dotGrid"></div>
    </div>
  </div>
</div>

<script>
var images=[], currentIdx=0, rotation=0, fiducials=[], fidMode=false;
var qa={}, reviewer="", imgCache={};
var zoom=1.0, panX=0, panY=0, isPanning=false, panStart={x:0,y:0};

function projectToCanvas(p) {
  // Project an image-space point to canvas pixel coords
  var canvas = document.getElementById('imgCanvas');
  var rad = rotation * Math.PI / 180;
  var rx = p.x * Math.cos(rad) - p.y * Math.sin(rad);
  var ry = p.x * Math.sin(rad) + p.y * Math.cos(rad);
  return {
    x: canvas.width/2  + panX + rx * zoom,
    y: canvas.height/2 + panY + ry * zoom
  };
}

function labelFiducials(pts) {
  var canvas = document.getElementById('imgCanvas');
  var cx = canvas.width/2, cy = canvas.height/2;
  var usedLabels = {};
  return pts.map(function(p) {
    var cp = projectToCanvas(p);
    var dx = cp.x - cx, dy = cp.y - cy;
    var adx = Math.abs(dx), ady = Math.abs(dy);
    var base;
    if (adx / (ady + 1) > 1.8) {
      base = dx < 0 ? 'ML' : 'MR';
    } else if (ady / (adx + 1) > 1.8) {
      base = dy < 0 ? 'MT' : 'MB';
    } else {
      base = (dy < 0 ? 'T' : 'B') + (dx < 0 ? 'L' : 'R');
    }
    usedLabels[base] = (usedLabels[base] || 0) + 1;
    var label = usedLabels[base] > 1 ? base + usedLabels[base] : base;
    return {label: label, x: p.x, y: p.y};
  });
}

function toggleFidMode() {
  fidMode = !fidMode;
  var btn    = document.getElementById('fidBtn');
  var badge  = document.getElementById('fidBadge');
  var canvas = document.getElementById('imgCanvas');
  var hint   = document.getElementById('hintText');
  if (fidMode) {
    btn.classList.add('active');
    badge.classList.add('active');
    canvas.className = 'fid-mode';
    hint.textContent = 'Click each fiducial mark (' + (fiducials.length+1) + ' so far). Right-click to undo last. F to finish.';
  } else {
    btn.classList.remove('active');
    badge.classList.remove('active');
    canvas.className = '';
    hint.textContent = 'Scroll=zoom · Ctrl+drag=pan · DblClick=reset · Arrows=rotate · F=fiducials · A/R/S=accept/reject/skip';
  }
  render();
}

function clearFiducials() { fiducials=[]; render(); updateFidPanel(); }

function updateFidPanel() {
  var labeled = fiducials.length > 0 ? labelFiducials(fiducials) : [];
  var list       = document.getElementById('fidList');
  var countEl    = document.getElementById('fidCount');
  var restoredEl = document.getElementById('fidRestored');
  if(countEl) countEl.textContent = '(' + fiducials.length + ')';
  if(restoredEl && images[currentIdx]){
    var fp = images[currentIdx].filepath;
    var hasSaved = serverFiducials[fp] && (
      Array.isArray(serverFiducials[fp]) ? serverFiducials[fp].length > 0
      : (serverFiducials[fp].fiducials||[]).length > 0);
    restoredEl.style.display = (hasSaved && fiducials.length > 0) ? 'block' : 'none';
  }
  list.innerHTML = labeled.map(function(pt) {
    return '<div><span class="placed">' + pt.label + '</span>'
      + ': (' + Math.round(pt.x) + ', ' + Math.round(pt.y) + ')</div>';
  }).join('') || '<div style="color:#484f58">None placed</div>';
}

function startSession(){
  reviewer = document.getElementById("reviewerInput").value.trim();
  if(!reviewer) return;
  document.getElementById("setupOv").style.display="none";
  var key = "img_qa_" + reviewer.replace(/\s+/g,"_");
  var saved = localStorage.getItem(key);
  if(saved){try{qa=JSON.parse(saved);}catch(e){}}
  loadManifest();
}

async function loadManifest(){
  try{
    var resp = await fetch("manifest.json");
    var data = await resp.json();
    images = data.images;
    try{
      var sresp = await fetch('/session_state');
      var sdata = await sresp.json();
      serverQA        = sdata.qa        || {};
      serverFiducials = sdata.fiducials || {};
      images.forEach(function(img, idx){
        var entry = serverQA[img.filepath];
        if(entry && entry.status){
          qa[idx] = {status:entry.status, rotation:entry.rotation, fiducials:entry.num_fiducials};
        }
      });
    }catch(e){ console.warn('Could not load session state:', e); }
    buildDots(); updateUI(); await render();
  }catch(e){ alert("Failed to load manifest: "+e); }
}

async function loadImg(idx){
  if(imgCache[idx]) return imgCache[idx];
  var img = new Image();
  return new Promise(function(res,rej){
    img.onload = function(){ imgCache[idx]=img; res(img); };
    img.onerror = function(e){ rej(e); };
    img.src = "/thumb/"+idx;
  });
}

async function render(){
  if(!images.length) return;
  var canvas = document.getElementById("imgCanvas");
  var ctx = canvas.getContext("2d");
  ctx.fillStyle="#0d1117"; ctx.fillRect(0,0,canvas.width,canvas.height);
  ctx.fillStyle="#484f58"; ctx.font="12px monospace"; ctx.textAlign="center";
  ctx.fillText("Loading...", canvas.width/2, canvas.height/2);
  try{
    var imgObj = await loadImg(currentIdx);
    ctx.fillStyle="#0d1117"; ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.save();
    // Pan offset then zoom around canvas centre
    ctx.translate(canvas.width/2 + panX, canvas.height/2 + panY);
    ctx.scale(zoom, zoom);
    ctx.rotate(rotation*Math.PI/180);
    var scale = Math.min(canvas.width/imgObj.width, canvas.height/imgObj.height)*0.9;
    var w=imgObj.width*scale, h=imgObj.height*scale;
    ctx.drawImage(imgObj, -w/2, -h/2, w, h);
    ctx.restore();

    // Draw fiducials — project image-space coords back to canvas space
    var labeled = fiducials.length===4 ? labelFiducials(fiducials) : null;
    fiducials.forEach(function(f, i){
      var lbl = labeled ? labeled[i].label : String(i+1);
      // Rotate image-space point by current rotation
      var rad = rotation * Math.PI / 180;
      var rx = f.x * Math.cos(rad) - f.y * Math.sin(rad);
      var ry = f.x * Math.sin(rad) + f.y * Math.cos(rad);
      // Apply zoom and pan to get canvas pixel position
      var cx = canvas.width/2  + panX + rx * zoom;
      var cy = canvas.height/2 + panY + ry * zoom;
      // Crosshair arms stay fixed size in screen space regardless of zoom
      var arm = 22, gap = 5;
      ctx.strokeStyle="#00e676"; ctx.lineWidth=0.8;
      ctx.beginPath();
      ctx.moveTo(cx-arm, cy); ctx.lineTo(cx-gap, cy);
      ctx.moveTo(cx+gap, cy); ctx.lineTo(cx+arm, cy);
      ctx.moveTo(cx, cy-arm); ctx.lineTo(cx, cy-gap);
      ctx.moveTo(cx, cy+gap); ctx.lineTo(cx, cy+arm);
      ctx.stroke();
      ctx.beginPath(); ctx.arc(cx, cy, 1.5, 0, 2*Math.PI);
      ctx.fillStyle="#00e676"; ctx.fill();
      ctx.font="bold 11px monospace"; ctx.textAlign="left";
      ctx.strokeStyle="#000"; ctx.lineWidth=3; ctx.lineJoin="round";
      ctx.strokeText(lbl, cx+8, cy-6);
      ctx.fillStyle="#00e676";
      ctx.fillText(lbl, cx+8, cy-6);
    });

    // Fiducial mode overlay
    if(fidMode){
      ctx.fillStyle="rgba(0,230,118,0.05)";
      ctx.fillRect(0,0,canvas.width,canvas.height);
      ctx.fillStyle="#00e676"; ctx.font="12px monospace"; ctx.textAlign="center";
      ctx.fillText("Mark "+(fiducials.length+1)+" — F to finish when done",
                   canvas.width/2, canvas.height-18);
    }
  }catch(e){
    ctx.fillStyle="#0d1117"; ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.fillStyle="#c62828"; ctx.font="12px monospace"; ctx.textAlign="center";
    ctx.fillText("Failed to load image", canvas.width/2, canvas.height/2-10);
  }
  updateUI();
}

function updateUI(){
  if(!images.length) return;
  var img = images[currentIdx];
  document.getElementById("rotVal").textContent = rotation+"°";
  document.getElementById("rotSlider").value = rotation;
  document.getElementById("navPos").textContent = (currentIdx+1)+" / "+images.length;
  document.getElementById("iYear").textContent = img.year;
  document.getElementById("iDataset").textContent = img.dataset;
  document.getElementById("iFile").textContent = img.filename;
  document.getElementById("sReviewer").textContent = reviewer;
  var total   = Object.keys(qa).length;
  var accept  = Object.values(qa).filter(function(v){return v.status==="ACCEPT";}).length;
  var reject  = Object.values(qa).filter(function(v){return v.status==="REJECT";}).length;
  document.getElementById("sReviewed").textContent = total+" / "+images.length;
  document.getElementById("sAccept").textContent  = accept;
  document.getElementById("sReject").textContent  = reject;
  updateFidPanel();
  updateDots();
}

function rotate(deg){
  rotation = (rotation+deg)%360;
  if(rotation<0) rotation+=360;
  render();
}

function mark(status){
  var img = images[currentIdx];
  var labeled = fiducials.length===4 ? labelFiducials(fiducials) : [];
  qa[currentIdx] = {status:status, rotation:rotation,
                    fiducials:fiducials.length, labeled:labeled};
  fetch("/save_qa", {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({filepath:img.filepath, year:img.year,
      dataset:img.dataset, filename:img.filename, status:status,
      rotation:rotation, num_fiducials:fiducials.length, reviewer:reviewer})});
  if(labeled.length > 0){
    fetch("/save_fiducials", {method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({filepath:img.filepath, rotation:rotation,
                            fiducials:labeled})});
  }
  localStorage.setItem("img_qa_"+reviewer.replace(/\s+/g,"_"), JSON.stringify(qa));
  fiducials=[]; rotation=0; zoom=1; panX=0; panY=0;
  document.getElementById("zoomVal").textContent="100%";
  if(fidMode) toggleFidMode();
  currentIdx++;
  if(currentIdx<images.length) render();
  else alert("All images reviewed!");
}

document.getElementById("imgCanvas").addEventListener("click", function(e){
  if(!fidMode) return;
  var rect = this.getBoundingClientRect();
  // Canvas pixel position of click
  var cx = (e.clientX - rect.left) * (this.width  / rect.width);
  var cy = (e.clientY - rect.top)  * (this.height / rect.height);
  // Convert from canvas px → image space by undoing zoom/pan/rotation
  var ix = (cx - this.width/2  - panX) / zoom;
  var iy = (cy - this.height/2 - panY) / zoom;
  var rad = -rotation * Math.PI / 180;
  var imgX =  ix * Math.cos(rad) - iy * Math.sin(rad);
  var imgY =  ix * Math.sin(rad) + iy * Math.cos(rad);
  fiducials.push({x: imgX, y: imgY});
  render();
});

document.getElementById("imgCanvas").addEventListener("contextmenu", function(e){
  e.preventDefault();
  if(fiducials.length>0){ fiducials.pop(); render(); }
});

// Scroll to zoom
document.getElementById("imgCanvas").addEventListener("wheel", function(e){
  e.preventDefault();
  var delta = e.deltaY > 0 ? 0.9 : 1.1;
  var newZoom = Math.max(0.5, Math.min(20, zoom * delta));
  // Zoom towards cursor: keep the pixel under cursor stationary
  var rect = this.getBoundingClientRect();
  var mx = (e.clientX - rect.left) * (this.width / rect.width);
  var my = (e.clientY - rect.top)  * (this.height / rect.height);
  var cx = this.width/2, cy = this.height/2;
  panX = mx - cx - (mx - cx - panX) * (newZoom / zoom);
  panY = my - cy - (my - cy - panY) * (newZoom / zoom);
  zoom = newZoom;
  render();
  document.getElementById("zoomVal").textContent = Math.round(zoom*100)+"%";
}, {passive:false});

// Middle-mouse or Ctrl+drag to pan
document.getElementById("imgCanvas").addEventListener("mousedown", function(e){
  if(e.button===1 || (e.button===0 && e.ctrlKey)){
    e.preventDefault();
    isPanning=true;
    var rect=this.getBoundingClientRect();
    panStart={x:e.clientX-panX, y:e.clientY-panY};
  }
});
document.addEventListener("mousemove", function(e){
  if(!isPanning) return;
  panX = e.clientX - panStart.x;
  panY = e.clientY - panStart.y;
  render();
});
document.addEventListener("mouseup", function(e){
  if(e.button===1 || e.button===0) isPanning=false;
});

// Double-click to reset zoom/pan
document.getElementById("imgCanvas").addEventListener("dblclick", function(e){
  if(fidMode) return;  // don't reset while placing fiducials
  zoom=1; panX=0; panY=0;
  render();
  document.getElementById("zoomVal").textContent="100%";
});

document.addEventListener("keydown", function(e){
  if(e.target.tagName==="INPUT") return;
  if(e.key==="a"||e.key==="A")      { mark("ACCEPT"); }
  else if(e.key==="r"||e.key==="R") { mark("REJECT"); }
  else if(e.key==="s"||e.key==="S") { mark("SKIP"); }
  else if(e.key==="f"||e.key==="F") { toggleFidMode(); }
  else if(e.key==="ArrowLeft")  { rotate(-10); }
  else if(e.key==="ArrowRight") { rotate(10); }
  else if(e.key==="ArrowUp")    { rotate(90); }
  else if(e.key==="ArrowDown")  { rotate(-90); }
});

function buildDots(){
  var grid = document.getElementById("dotGrid");
  grid.innerHTML = "";
  var n = Math.min(100, images.length);
  for(var i=0; i<n; i++){
    var d = document.createElement("div"); d.className="dot"; d.dataset.i=i;
    d.onclick = (function(idx){ return function(){
      currentIdx=idx; fiducials=[]; zoom=1; panX=0; panY=0;
      document.getElementById("zoomVal").textContent="100%";
      if(fidMode) toggleFidMode();
      render();
    }; })(i);
    grid.appendChild(d);
  }
}

function updateDots(){
  document.querySelectorAll(".dot").forEach(function(d){
    var i = parseInt(d.dataset.i); d.className="dot";
    if(i===currentIdx) d.classList.add("cur");
    else if(qa[i]&&qa[i].status==="ACCEPT") d.classList.add("accept");
    else if(qa[i]&&qa[i].status==="REJECT") d.classList.add("reject");
  });
}
</script>
</body>
</html>
"""


def _inner_tif_member(zip_path: Path) -> str | None:
    """Return the path of the first TIF member inside a ZIP, or None."""
    import zipfile
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for m in zf.namelist():
                if m.lower().endswith(('.tif', '.tiff')):
                    return m
    except Exception:
        pass
    return None


def _scan_images() -> list[dict]:
    """Find all valid TIF images under DOWNLOAD_DIR.

    Handles two cases transparently:
      - Plain TIF files
      - ZIP archives (USGS HIGH_RES_ORTHO Standard ZIP format) containing
        a TIF nested at an arbitrary path inside the archive
    """
    import zipfile
    print("\n── Scanning images ──")
    images, skipped = [], 0

    for fpath in sorted(DOWNLOAD_DIR.rglob("*.tif")):
        size = fpath.stat().st_size
        if size < 1_048_576:
            skipped += 1
            continue

        with open(fpath, 'rb') as f:
            magic = f.read(4)

        if magic == b'%PDF':
            skipped += 1
            continue

        # ZIP saved as .tif (USGS Standard ZIP products)
        if magic == b'PK\x03\x04':
            member = _inner_tif_member(fpath)
            if member is None:
                skipped += 1
                continue
            filepath_str = f"{fpath}::{member}"
            filename     = Path(member).name
        elif magic[:2] == b'\x1f\x8b':
            # Gzip-compressed TIF (AERIAL_COMBIN High Resolution Product)
            filepath_str = str(fpath)
            filename     = fpath.name
        else:
            # Plain TIF — skip if a ZIP in the same dir contains a member
            # with the same stem (means this is an already-extracted copy).
            stem_lower = fpath.stem.lower()
            has_zip_twin = False
            for sibling in fpath.parent.glob('*.tif'):
                if sibling == fpath:
                    continue
                try:
                    with open(sibling, 'rb') as _sf:
                        if _sf.read(4) != b'PK\x03\x04':
                            continue
                    inner = _inner_tif_member(sibling) or ''
                    if Path(inner).stem.lower() == stem_lower:
                        has_zip_twin = True
                        break
                except Exception:
                    pass
            if has_zip_twin:
                skipped += 1
                continue  # prefer ZIP version; skip extracted duplicate
            filepath_str = str(fpath)
            filename     = fpath.name

        rel = fpath.relative_to(DOWNLOAD_DIR)
        images.append({
            "id":       len(images),
            "filepath": filepath_str,
            "rel_path": str(rel),
            "year":     fpath.parent.parent.name,
            "dataset":  fpath.parent.name,
            "filename": filename,
        })

    print(f"  Found {len(images)} images" +
          (f", skipped {skipped} PDFs/small/unreadable files" if skipped else ""))
    return images


def _open_rasterio_src(filepath_str: str):
    """Open a rasterio dataset from either a plain path or a 'zip::member' path."""
    import rasterio
    import zipfile

    if '::' in filepath_str:
        zip_path, member = filepath_str.split('::', 1)
        with zipfile.ZipFile(zip_path) as zf:
            data = zf.read(member)
        return rasterio.open(BytesIO(data))
    # Check magic bytes for gzip (AERIAL_COMBIN files)
    with open(filepath_str, 'rb') as _mf:
        _magic = _mf.read(2)
    if _magic == b'\x1f\x8b':
        import gzip
        with gzip.open(filepath_str, 'rb') as gz:
            _data = gz.read()
        return rasterio.open(BytesIO(_data))
    return rasterio.open(filepath_str)


def _generate_thumbnail(filepath_str: str, max_size: int = 800) -> bytes | None:
    label = Path(filepath_str.split('::')[-1]).name
    print(f"  Thumbnail: {label}...", end=" ", flush=True)
    try:
        with _open_rasterio_src(filepath_str) as src:
            out_shape = (min(src.height, max_size), min(src.width, max_size))
            data = src.read(
                [1, 2, 3] if src.count >= 3 else [1],
                out_shape=out_shape,
            )
            if data.dtype != np.uint8:
                data = np.clip(data, 0, 255).astype(np.uint8)
            arr = (np.transpose(data, (1, 2, 0)) if data.shape[0] == 3
                   else np.stack([data[0]] * 3, axis=-1))
            img = Image.fromarray(arr, mode='RGB')
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                img = img.resize(tuple(int(d * ratio) for d in img.size),
                                 Image.Resampling.LANCZOS)
            buf = BytesIO()
            img.save(buf, format='JPEG', quality=82)
            result = buf.getvalue()
            print(f"✓ {len(result)//1024} KB")
            return result
    except Exception as e:
        import traceback
        print(f"✗ {e}")
        traceback.print_exc()
        return None


def _make_qa_handler(images: list[dict], static_dir: Path):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(static_dir), **kwargs)

        def do_GET(self):
            if self.path.startswith("/thumb/"):
                try:
                    idx = int(self.path.split("/")[-1])
                    jpeg = _generate_thumbnail(images[idx]["filepath"])
                    if jpeg:
                        self.send_response(200)
                        self.send_header("Content-Type", "image/jpeg")
                        self.send_header("Content-Length", str(len(jpeg)))
                        self.send_header("Cache-Control", "public, max-age=3600")
                        self.end_headers()
                        self.wfile.write(jpeg)
                    else:
                        self.send_error(500, "Thumbnail failed")
                except Exception as e:
                    self.send_error(500, str(e))
                return
            super().do_GET()

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))

            if self.path == "/save_qa":
                row = {k: payload.get(k, "") for k in CSV_FIELDS}
                row["timestamp"] = datetime.now().isoformat()
                file_exists = QA_CSV.exists()
                with open(QA_CSV, 'a', newline='') as f:
                    w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                    if not file_exists:
                        w.writeheader()
                    w.writerow(row)
                self._json({"status": "ok"})

            elif self.path == "/save_fiducials":
                fpath = payload.get("filepath")
                fids  = payload.get("fiducials", [])
                all_fids = {}
                if FID_JSON.exists():
                    with open(FID_JSON) as f:
                        all_fids = json.load(f)
                all_fids[fpath] = fids
                with open(FID_JSON, 'w') as f:
                    json.dump(all_fids, f, indent=2)
                self._json({"status": "ok"})
            else:
                self.send_error(404)

        def _json(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            try:
                msg = fmt % args
                if "/save" in msg:
                    print(f"  [{datetime.now().strftime('%H:%M:%S')}] {msg}")
            except Exception:
                pass

    return Handler


def stage_qa():
    """Kill any existing server on QA_PORT, then start the QA tool."""
    print("\n" + "=" * 60)
    print("  STAGE 5 · AERIAL IMAGERY QA TOOL")
    print("=" * 60)

    images = _scan_images()
    if not images:
        print(f"\n✗ No images found in {DOWNLOAD_DIR}")
        return None

    LOCAL_QA_DIR.mkdir(exist_ok=True)
    (LOCAL_QA_DIR / "manifest.json").write_text(json.dumps({"images": images}))
    (LOCAL_QA_DIR / "qa_app.html").write_text(QA_APP_HTML)
    print(f"\n✓ Manifest: {len(images)} images")

    # Port cleanup
    print(f"\n── Cleaning up port {QA_PORT} ──")
    os.system(f'fuser -k {QA_PORT}/tcp 2>/dev/null')
    os.system(f'pkill -f "port {QA_PORT}" 2>/dev/null')
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('', QA_PORT))
        s.close()
        print(f"✓ Port {QA_PORT} available")
    except Exception as e:
        print(f"⚠ Port may still be in use: {e}")
    time.sleep(2)

    # Start server
    print(f"\n── Starting server on port {QA_PORT} ──")
    Handler = _make_qa_handler(images, LOCAL_QA_DIR)
    try:
        server = socketserver.ThreadingTCPServer(("", QA_PORT), Handler)
        server.allow_reuse_address = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        time.sleep(2)
        print("✓ Server started")
    except Exception as e:
        print(f"✗ Server startup failed: {e}")
        return None

    # Colab proxy URL
    try:
        from google.colab.output import eval_js
        from IPython.display import display, HTML

        proxy_url = eval_js(f"google.colab.kernel.proxyPort({QA_PORT})")
        qa_url = proxy_url + "/qa_app.html"

        print(f"\n{'='*60}")
        print(f"✓ QA TOOL READY  →  {qa_url}")
        print(f"{'='*60}")

        display(HTML(
            f'<div style="background:#161b22;padding:20px;border:1px solid #30363d;'
            f'border-radius:8px;margin:10px 0">'
            f'<div style="color:#58a6ff;font-size:16px;font-weight:700;margin-bottom:10px">'
            f'🗺️ Image QA Tool Ready</div>'
            f'<a href="{qa_url}" target="_blank" '
            f'style="display:inline-block;background:#2e7d32;color:#fff;'
            f'padding:12px 24px;text-decoration:none;border-radius:6px;'
            f'font-family:monospace;font-size:14px;font-weight:700">'
            f'→ Open QA Tool</a>'
            f'<div style="color:#484f58;font-size:11px;margin-top:12px;line-height:1.6">'
            f'<b>Controls:</b> Arrow keys rotate · A=accept · R=reject · '
            f'Click to mark fiducials<br>'
            f'<b>Output:</b> {QA_CSV.name}</div>'
            f'</div>'
        ))

        print(f"\n✓ Reviewing {len(images)} images  (keep this cell running)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n✓ Server stopped")
            server.shutdown()

    except Exception as e:
        print(f"\n✗ Could not generate Colab URL: {e}")

    return server



# ============================================================================
# Fresh start helper
# ============================================================================

def fresh_start():
    """Delete all session outputs and downloaded imagery, then recreate the
    session directory structure. Call this at the top of a new Colab session
    to guarantee a clean slate before running the pipeline.
    """
    import shutil
    print("=" * 60)
    print("  FRESH START — clearing session data")
    print("=" * 60)
    if SESSION_DIR.exists():
        shutil.rmtree(SESSION_DIR)
        print(f"  ✓ Deleted {SESSION_DIR}")
    else:
        print(f"  ○ {SESSION_DIR} did not exist — nothing to delete")
    for d in [SESSION_DIR, DOWNLOAD_DIR, LOCAL_QA_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    print(f"  ✓ Created fresh session directory: {SESSION_DIR}")
    print("  Ready to run pipeline.\n")



# ============================================================================
# Stage 6 – Process QA results (rotate accepted images, build year mosaics)
# ============================================================================

def stage_process() -> pd.DataFrame:
    """Apply approved rotations to accepted TIFs and mosaic tiles by year.

    Reads Image_QA_Results.csv, skips rejected/skipped images, rotates each
    accepted TIF by the reviewer-specified angle, then merges all tiles for
    the same year into a single GeoTIFF mosaic saved under:
        SESSION_DIR/mosaics/<year>/<year>_mosaic.tif

    Returns a summary DataFrame.
    """
    try:
        import rasterio
        from rasterio.merge import merge as rio_merge
        from rasterio.transform import from_bounds
        import scipy.ndimage as ndi
    except ImportError:
        raise ImportError(
            "rasterio and scipy are required for stage_process.\n"
            "Install with: pip install rasterio scipy"
        )

    print("\n" + "=" * 70)
    print("STAGE 6 · PROCESS QA RESULTS — ROTATE & MOSAIC")
    print("=" * 70)

    # ── Load QA results ──────────────────────────────────────────────────────
    if not QA_CSV.exists():
        raise FileNotFoundError(f"QA results not found: {QA_CSV}\nRun stage 5 first.")

    qa_df = pd.read_csv(QA_CSV)

    # Keep only the most recent decision per file (reviewer may have changed mind)
    qa_df = (qa_df.sort_values('timestamp')
                  .drop_duplicates(subset=['filepath'], keep='last')
                  .reset_index(drop=True))

    total     = len(qa_df)
    accepted  = qa_df[qa_df['status'] == 'ACCEPT']
    rejected  = (qa_df['status'] == 'REJECT').sum()
    skipped   = (qa_df['status'] == 'SKIP').sum()

    print(f"\n  QA results: {total} total · {len(accepted)} accepted · "
          f"{rejected} rejected · {skipped} skipped")

    if accepted.empty:
        print("\n✗ No accepted images to process.")
        return pd.DataFrame()

    # ── Rotate accepted TIFs ─────────────────────────────────────────────────
    MOSAIC_DIR = SESSION_DIR / 'mosaics'
    ROTATED_DIR = SESSION_DIR / 'rotated'
    ROTATED_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n[1/2] Rotating {len(accepted)} accepted image(s)...")
    rotated_paths: dict[str, Path] = {}   # original filepath → rotated path

    for _, row in accepted.iterrows():
        src_path = Path(row['filepath'])
        rotation = float(row['rotation'])
        out_path = ROTATED_DIR / src_path.parent.relative_to(DOWNLOAD_DIR) / src_path.name

        filepath_str = str(row['filepath'])
        is_zip = '::' in filepath_str
        if is_zip:
            zip_path, member = filepath_str.split('::', 1)
            physical_path = Path(zip_path)
            display_name  = Path(member).name
        else:
            physical_path = src_path
            display_name  = src_path.name

        if not physical_path.exists():
            print(f"  ⚠ Missing: {display_name} — skipping")
            continue

        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"  ○ {display_name} already rotated — skipping")
            rotated_paths[filepath_str] = out_path
            continue

        out_path.parent.mkdir(parents=True, exist_ok=True)

        if rotation == 0:
            import shutil, zipfile as _zf
            if is_zip:
                with _zf.ZipFile(zip_path) as zf:
                    out_path.write_bytes(zf.read(member))
            else:
                # Check if source is gzip — must decompress to plain TIF
                with open(physical_path, 'rb') as _mf:
                    _magic = _mf.read(2)
                if _magic == b'\x1f\x8b':
                    import gzip
                    with gzip.open(physical_path, 'rb') as gz:
                        out_path.write_bytes(gz.read())
                else:
                    shutil.copy2(src_path, out_path)
            print(f"  ✓ {display_name} (0° — copied)")
        else:
            with _open_rasterio_src(filepath_str) as src:
                data     = src.read()
                profile  = src.profile.copy()
                n_bands, h, w = data.shape

                # Rotate each band; reshape=True expands canvas to fit
                rotated_bands = []
                for b in range(n_bands):
                    rotated_bands.append(
                        ndi.rotate(data[b], angle=-rotation,
                                   reshape=True, order=1,
                                   mode='constant', cval=0)
                    )
                rotated = np.stack(rotated_bands)
                new_h, new_w = rotated.shape[1], rotated.shape[2]

                # Adjust transform to account for new canvas size
                bounds   = src.bounds
                cx       = (bounds.left + bounds.right)  / 2
                cy       = (bounds.bottom + bounds.top) / 2
                px_w     = (bounds.right - bounds.left)  / w
                px_h     = (bounds.top   - bounds.bottom) / h
                new_left = cx - (new_w / 2) * px_w
                new_top  = cy + (new_h / 2) * px_h

                profile.update(
                    width=new_w, height=new_h,
                    transform=rasterio.transform.from_origin(
                        new_left, new_top, px_w, px_h
                    )
                )
                with rasterio.open(out_path, 'w', **profile) as dst:
                    dst.write(rotated.astype(data.dtype))

            print(f"  ✓ {src_path.name} rotated {rotation}°")

        rotated_paths[filepath_str] = out_path

    # ── Mosaic by year ────────────────────────────────────────────────────────
    print(f"\n[2/2] Building year mosaics...")
    MOSAIC_DIR.mkdir(parents=True, exist_ok=True)

    summary_rows = []
    for year, group in accepted.groupby('year'):
        year = int(year)

        # ── Select tiles: prefer single-dataset mosaic ───────────────────
        # Group tiles by dataset and pick the dataset with the most tiles
        # (proxy for best coverage). Only mix datasets if a single dataset
        # has no valid rotated tiles at all.
        by_dataset = {}
        for _, row in group.iterrows():
            fp = row['filepath']
            ds = row['dataset']
            rp = rotated_paths.get(fp)
            if rp and rp.exists():
                by_dataset.setdefault(ds, []).append(rp)

        if not by_dataset:
            print(f"  ✗ {year}: no rotated tiles available")
            continue

        if len(by_dataset) == 1:
            # Only one dataset — straightforward
            chosen_dataset, tiles = next(iter(by_dataset.items()))
        else:
            # Multiple datasets — pick the one with the most tiles.
            # Tie-break: prefer NAIP (4-band NIR) > HIGH_RES_ORTHO > others.
            DATASET_PREF = ['NAIP', 'HIGH_RES_ORTHO', 'NAPP', 'NHAP', 'AERIAL_COMBIN']
            best = max(
                by_dataset.items(),
                key=lambda kv: (len(kv[1]),
                                -DATASET_PREF.index(kv[0])
                                 if kv[0] in DATASET_PREF else -99)
            )
            chosen_dataset, tiles = best
            other_datasets = [d for d in by_dataset if d != chosen_dataset]
            print(f"  {year}: multiple datasets {list(by_dataset.keys())} "
                  f"— using {chosen_dataset} ({len(tiles)} tile(s)), "
                  f"skipping {other_datasets}")

        mosaic_path = MOSAIC_DIR / str(year) / f"{year}_mosaic.tif"
        mosaic_path.parent.mkdir(parents=True, exist_ok=True)

        if mosaic_path.exists() and mosaic_path.stat().st_size > 0:
            print(f"  ○ {year}: mosaic already exists — skipping")
        else:
            print(f"  {year}: merging {len(tiles)} tile(s)...", end=" ", flush=True)
            datasets = []
            for t in tiles:
                try:
                    datasets.append(rasterio.open(t))
                except Exception as _te:
                    print(f"\n    ⚠ Could not open {t.name}: {_te} — skipping")
            # Normalise any upside-down tiles (positive pixel height)
            # by flipping pixel data and correcting the transform.
            normalised = []
            mem_files = []  # keep MemoryFile objects alive until merge done
            for ds in datasets:
                if ds.transform.e > 0:  # positive e = upside-down
                    data = ds.read()
                    data = data[:, ::-1, :]  # flip rows
                    t = ds.transform
                    # New origin: top-left moves to what was bottom-left
                    new_origin_y = t.f + t.e * ds.height
                    new_t = rasterio.transform.from_origin(
                        t.c, new_origin_y, t.a, abs(t.e)
                    )
                    prof = ds.profile.copy()
                    prof.update(transform=new_t)
                    ds.close()
                    mf = rasterio.io.MemoryFile()
                    mem_files.append(mf)
                    with mf.open(**prof) as m:
                        m.write(data)
                    normalised.append(mf.open())
                else:
                    normalised.append(ds)
            try:
                # Harmonise band counts — use the minimum across all tiles
                # (e.g. NAIP tiles may have 4 bands, others 3)
                band_counts = [ds.count for ds in normalised]
                min_bands = min(band_counts)
                indexes = list(range(1, min_bands + 1))
                if len(set(band_counts)) > 1:
                    print(f"  ⚠ Band count mismatch {band_counts} — using first {min_bands} band(s)")
                mosaic, transform = rio_merge(normalised, indexes=indexes)
                profile = normalised[0].profile.copy()
                profile.update(
                    width=mosaic.shape[2],
                    height=mosaic.shape[1],
                    count=min_bands,
                    transform=transform,
                    compress='lzw',
                )
                with rasterio.open(mosaic_path, 'w', **profile) as dst:
                    dst.write(mosaic)
                size_mb = mosaic_path.stat().st_size / 1024**2
                print(f"✓ {size_mb:.1f} MB")
            finally:
                for ds in normalised:
                    try: ds.close()
                    except Exception: pass
                for mf in mem_files:
                    try: mf.close()
                    except Exception: pass

        summary_rows.append({
            'Year':       year,
            'Tiles':      len(tiles),
            'Mosaic':     str(mosaic_path),
            'Size_MB':    mosaic_path.stat().st_size / 1024**2,
            'Status':     'Ready',
        })

    summary_df = pd.DataFrame(summary_rows)
    summary_path = SESSION_DIR / 'Mosaic_Summary.xlsx'
    summary_df.to_excel(summary_path, index=False)

    print(f"\n✓ {len(summary_df)} mosaic(s) built")
    print(f"  Output: {MOSAIC_DIR}")
    print(f"  Summary: {summary_path}")
    return summary_df



# ============================================================================
# Stage 7 – Georeference historical imagery using USGS scene metadata
# ============================================================================

def _parse_dms(val: str) -> float:
    """Parse a DMS string like 47deg47min26.39secN to decimal degrees."""
    import re
    val = val.replace('&deg;', '°').replace('&amp;', '&')
    m = re.match(r'(\d+)[°d]\s*(\d+)[\'m]\s*([\d.]+)["s]?\s*([NSEW])', val.strip())
    if not m:
        return float(val)
    deg, mn, sec, hemi = m.groups()
    dd = float(deg) + float(mn)/60 + float(sec)/3600
    if hemi in ('S', 'W'):
        dd = -dd
    return dd


def _meta_val(metadata: list, field: str):
    """Extract a value from M2M metadata list by field name (case-insensitive)."""
    field_lower = field.lower()
    for item in metadata:
        if item.get('fieldName', '').lower() == field_lower:
            return item.get('value')
    return None


def _fetch_scene_metadata(api, dataset: str, entity_id: str) -> dict:
    """Fetch full scene metadata from M2M."""
    result = api._post('scene-metadata', {
        "datasetName": dataset,
        "entityId":    entity_id,
        "metadataType": "full",
    })
    return result or {}


def _build_pixel_world_pairs(meta: dict, fiducials: list, **kwargs) -> tuple:
    """Build matched pixel and world coordinate arrays from fiducials + USGS metadata.

    Returns (pixel_coords, world_coords) as numpy arrays, shape (N,2) each.
    pixel_coords: [[col, row], ...] in image pixel space
    world_coords: [[lon, lat], ...] in WGS84 decimal degrees

    Mid-edge fiducials (ML/MR/MT/MB) are mapped to the midpoint between
    the two adjacent corners, giving a more accurate world position than
    mapping them to a single corner.
    """
    metadata = meta.get('metadata', [])

    # Parse all corner + centre coordinates
    C = {}
    for usgs_field, key in [
        ('NW Corner Lat dec', 'NW_lat'), ('NW Corner Long dec', 'NW_lon'),
        ('NE Corner Lat dec', 'NE_lat'), ('NE Corner Long dec', 'NE_lon'),
        ('SE Corner Lat dec', 'SE_lat'), ('SE Corner Long dec', 'SE_lon'),
        ('SW Corner Lat dec', 'SW_lat'), ('SW Corner Long dec', 'SW_lon'),
        ('Center Latitude dec', 'C_lat'), ('Center Longitude dec', 'C_lon'),
    ]:
        v = _meta_val(metadata, usgs_field)
        if v is not None:
            C[key] = float(v)

    if not C:
        return np.array([]), np.array([])

    # World coordinate for each fiducial label.
    # Corner marks → exact corner; mid-edge marks → midpoint of that edge.
    def mid(lat1, lon1, lat2, lon2):
        return ((lat1 + lat2) / 2, (lon1 + lon2) / 2)

    # Ignore stored labels — derive world coords from canvas position via
    # bilinear interpolation across the four USGS corner coordinates.
    #
    # Canvas space: negative Y = screen top = geographic north (Y axis inverted)
    #               positive Y = screen bottom = geographic south
    #               negative X = left = west,  positive X = right = east
    # Corners in normalised -1..+1 space:
    #   NW=(-1,-1)  NE=(+1,-1)  SW=(-1,+1)  SE=(+1,+1)

    img_w = kwargs.get('img_w', 800)
    img_h = kwargs.get('img_h', 800)
    canvas_size = 800.0
    scale_x = img_w / canvas_size
    scale_y = img_h / canvas_size

    def canvas_to_world(cx, cy):
        nx = cx / (canvas_size / 2)   # -1=west .. +1=east
        ny = cy / (canvas_size / 2)   # -1=north .. +1=south
        w_nw = (1 - nx) * (1 - ny) / 4
        w_ne = (1 + nx) * (1 - ny) / 4
        w_sw = (1 - nx) * (1 + ny) / 4
        w_se = (1 + nx) * (1 + ny) / 4
        lat = (w_nw * C.get('NW_lat', 0) + w_ne * C.get('NE_lat', 0) +
               w_sw * C.get('SW_lat', 0) + w_se * C.get('SE_lat', 0))
        lon = (w_nw * C.get('NW_lon', 0) + w_ne * C.get('NE_lon', 0) +
               w_sw * C.get('SW_lon', 0) + w_se * C.get('SE_lon', 0))
        return lat, lon

    pixels, worlds = [], []
    for fid in fiducials:
        cx = fid.get('x', 0)
        cy = fid.get('y', 0)
        img_col = cx * scale_x + img_w / 2.0
        img_row = cy * scale_y + img_h / 2.0
        lat, lon = canvas_to_world(cx, cy)
        pixels.append([img_col, img_row])
        worlds.append([lon, lat])

    return np.array(pixels, dtype=float), np.array(worlds, dtype=float)


def _fit_affine(pixels: np.ndarray, worlds: np.ndarray):
    """Fit a 2D affine transform from pixel (col,row) to world (lon,lat)
    using least-squares.  Returns a rasterio.Affine transform.
    """
    from rasterio.transform import Affine
    # Solve [lon] = A * [col] + [tx]
    #       [lat]   B   [row]   [ty]
    # Rewrite as Ax = b for each coord.
    N = len(pixels)
    # Build design matrix [col, row, 1] for each point
    D = np.hstack([pixels, np.ones((N, 1))])
    # Solve for lon coefficients: [a, b, tx]
    lon_coeffs, _, _, _ = np.linalg.lstsq(D, worlds[:, 0], rcond=None)
    # Solve for lat coefficients: [c, d, ty]
    lat_coeffs, _, _, _ = np.linalg.lstsq(D, worlds[:, 1], rcond=None)
    # Affine(a, b, c, d, e, f) where:
    #   lon = a*col + b*row + c
    #   lat = d*col + e*row + f
    a, b, tx = lon_coeffs   # lon = a*col + b*row + tx
    d, e, ty = lat_coeffs   # lat = d*col + e*row + ty
    # rasterio Affine(a, b, c, d, e, f):
    #   x_geo = a*col + b*row + c
    #   y_geo = d*col + e*row + f
    return Affine(a, b, tx, d, e, ty)


def stage_georeference(api) -> pd.DataFrame:
    """Georeference pre-2002 historical images using USGS scene metadata.

    For each AERIAL_COMBIN/NHAP/NAPP image:
      1. Fetch NW/NE/SE/SW corner coordinates from M2M scene-metadata
      2. Match to fiducial pixel positions from Fiducial_Marks.json
      3. Fit an affine transform from those GCP pairs
      4. Warp the rotated TIF to a clean EPSG:4326 GeoTIFF

    Output: SESSION_DIR/georeferenced/<display_id>_georef.tif
    """
    try:
        import rasterio
        import rasterio.control
        import rasterio.crs
        pass  # rasterio already imported above
    except ImportError:
        raise ImportError('rasterio is required.  pip install rasterio')

    print("\n" + "=" * 70)
    print("STAGE 7 · GEOREFERENCE HISTORICAL IMAGERY")
    print("=" * 70)

    if not FID_JSON.exists():
        raise FileNotFoundError(f'Fiducial marks not found: {FID_JSON}\nRun stage 5 first.')
    with open(FID_JSON) as f:
        fid_data = json.load(f)
    print(f'\n  Fiducial mark records: {len(fid_data)}')

    if not QA_CSV.exists():
        raise FileNotFoundError(f'QA results not found: {QA_CSV}')
    qa_df = pd.read_csv(QA_CSV)
    qa_df = (qa_df.sort_values('timestamp')
                  .drop_duplicates(subset=['filepath'], keep='last'))

    if not TRACKING_FILE.exists():
        raise FileNotFoundError(f'Tracking log not found: {TRACKING_FILE}')
    tracking_df = pd.read_excel(TRACKING_FILE)

    GEO_DATASETS = {'AERIAL_COMBIN', 'NHAP', 'NAPP'}
    historical = tracking_df[tracking_df['Dataset'].isin(GEO_DATASETS)]
    print(f'  Historical scenes to georeference: {len(historical)}')

    GEOREF_DIR = SESSION_DIR / 'georeferenced'
    GEOREF_DIR.mkdir(exist_ok=True)

    summary_rows = []

    for _, track_row in historical.iterrows():
        entity_id  = track_row['Entity_ID']
        dataset    = track_row['Dataset']
        display_id = track_row['Display_ID']
        year       = int(track_row['Year'])

        print(f'\n[{year}] {display_id}')

        # Find rotated file
        rotated_dir  = SESSION_DIR / 'rotated' / str(year) / dataset
        rotated_file = rotated_dir / f'{display_id}.tif'
        if not rotated_file.exists():
            candidates = list(rotated_dir.glob('*.tif')) if rotated_dir.exists() else []
            if not candidates:
                print('  ⚠ Rotated file not found — skipping')
                continue
            rotated_file = candidates[0]

        # Match fiducials — key may be filepath string containing display_id
        fid_entry = None
        for k, v in fid_data.items():
            if display_id in k:
                fid_entry = v
                break
        if fid_entry is None:
            print('  ⚠ No fiducial marks recorded — skipping')
            continue

        fiducials = fid_entry if isinstance(fid_entry, list) else fid_entry.get('fiducials', [])
        if len(fiducials) < 3:
            print(f'  ⚠ Need ≥ 3 fiducial marks, found {len(fiducials)} — skipping')
            continue

        print(f'  Fiducials: {[f["label"] for f in fiducials]}')

        # Fetch USGS metadata
        print('  Fetching M2M metadata...', end=' ', flush=True)
        meta = _fetch_scene_metadata(api, dataset, entity_id)
        if not meta:
            print('✗ No metadata returned')
            continue
        print('✓')

        # Build pixel<->world pairs — pass actual image dimensions
        # so canvas-space fiducial coords are correctly scaled
        with rasterio.open(rotated_file) as _ds:
            _img_w, _img_h = _ds.width, _ds.height
        pixels, worlds = _build_pixel_world_pairs(
            meta, fiducials, img_w=_img_w, img_h=_img_h
        )
        if len(pixels) < 3:
            print(f'  ⚠ Only {len(pixels)} unique usable pairs (need ≥ 3) — skipping')
            for item in meta.get('metadata', []):
                fn = item.get('fieldName', '')
                if 'corner' in fn.lower() or 'center' in fn.lower():
                    print(f'    {fn}: {item["value"]}')
            continue

        print(f'  Control points: {len(pixels)}')

        dst_path = GEOREF_DIR / f'{display_id}_georef.tif'
        if dst_path.exists() and dst_path.stat().st_size > 0:
            print('  ○ Already georeferenced — skipping')
            summary_rows.append({'Year': year, 'Dataset': dataset,
                'Display_ID': display_id, 'Control_Points': len(pixels),
                'Output': str(dst_path), 'Status': 'Exists'})
            continue

        try:
            # Fit affine directly via least-squares — avoids GDAL homography issues
            affine = _fit_affine(pixels, worlds)
            crs    = rasterio.crs.CRS.from_epsg(4326)

            # Compute residuals for quality check
            pred_lon = affine.a * pixels[:,0] + affine.b * pixels[:,1] + affine.c
            pred_lat = affine.d * pixels[:,0] + affine.e * pixels[:,1] + affine.f
            rmse_lon = float(np.sqrt(np.mean((pred_lon - worlds[:,0])**2)))
            rmse_lat = float(np.sqrt(np.mean((pred_lat - worlds[:,1])**2)))
            # Convert to metres approx (1 deg lat ~ 111 km)
            rmse_m = np.sqrt(rmse_lon**2 + rmse_lat**2) * 111_000
            print(f'  Affine RMSE: {rmse_m:.1f} m')

            # Write georeferenced TIF with the fitted affine transform
            with rasterio.open(rotated_file) as src_ds:
                profile = src_ds.profile.copy()
                data    = src_ds.read()
            profile.update(crs=crs, transform=affine, compress='lzw')
            with rasterio.open(dst_path, 'w', **profile) as dst_ds:
                dst_ds.write(data)

            size_mb = dst_path.stat().st_size / 1024**2
            print(f'  ✓ {dst_path.name}  ({size_mb:.1f} MB)')
            summary_rows.append({'Year': year, 'Dataset': dataset,
                'Display_ID': display_id, 'Control_Points': len(pixels),
                'RMSE_m': round(rmse_m, 1),
                'Output': str(dst_path), 'Status': 'Success'})

        except Exception as e:
            import traceback
            print(f'  ✗ {e}')
            traceback.print_exc()
            summary_rows.append({'Year': year, 'Dataset': dataset,
                'Display_ID': display_id, 'Control_Points': len(pixels),
                'Output': '', 'Status': f'Failed: {e}'})

    summary_df = pd.DataFrame(summary_rows)
    if not summary_df.empty:
        summary_path = SESSION_DIR / 'Georef_Summary.xlsx'
        summary_df.to_excel(summary_path, index=False)
        success = (summary_df['Status'] == 'Success').sum()
        print(f'\n✓ {success}/{len(summary_df)} images georeferenced')
        print(f'  Output: {SESSION_DIR / "georeferenced"}')
    else:
        print('\n○ No images were georeferenced.')

    return summary_df



# ============================================================================
# Stage 8 – Export all outputs to Google Drive
# ============================================================================

# Edmonds city centre — used as fallback georeference for ungeoreferenced images
EDMONDS_CENTER_LAT =  47.8107
EDMONDS_CENTER_LON = -122.3774

# Approximate extent of Edmonds in degrees
# Used to assign a rough affine transform to ungeoreferenced images
EDMONDS_APPROX_SPAN_DEG = 0.08  # ~8 km, covers the city comfortably


def _assign_edmonds_georeference(src_path: Path, dst_path: Path):
    """Copy a TIF and assign a rough affine transform centred on Edmonds.

    This places the image geographically near Edmonds so ArcGIS opens it
    in the right area rather than at 0,0. The transform is intentionally
    approximate — the user will refine it in ArcGIS.
    """
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.crs import CRS

    with rasterio.open(src_path) as src:
        data    = src.read()
        profile = src.profile.copy()
        h, w    = src.height, src.width

    # Build a square bounding box centred on Edmonds
    span = EDMONDS_APPROX_SPAN_DEG
    west  = EDMONDS_CENTER_LON - span / 2
    east  = EDMONDS_CENTER_LON + span / 2
    south = EDMONDS_CENTER_LAT - span / 2
    north = EDMONDS_CENTER_LAT + span / 2
    transform = from_bounds(west, south, east, north, w, h)

    profile.update(
        crs=CRS.from_epsg(4326),
        transform=transform,
        compress='lzw',
    )
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(dst_path, 'w', **profile) as dst:
        dst.write(data)


def stage_export() -> pd.DataFrame:
    """Copy all pipeline outputs to Google Drive.

    For each year:
      - If a georeferenced mosaic exists (2002+), copy it as-is.
      - If individual georeferenced TIFs exist (historical, stage 7),
        copy them to a per-year subfolder.
      - If an image has no georeference, assign a rough Edmonds-centred
        affine transform so ArcGIS places it in the right area.

    Output structure on Drive:
        treedata/Edmonds_Imagery/
            mosaics/<year>/<year>_mosaic.tif   (georeferenced)
            historical/<year>/<display_id>.tif  (rough or refined georeference)
    """
    import shutil
    import rasterio

    print("\n" + "=" * 70)
    print("STAGE 8 · EXPORT TO GOOGLE DRIVE")
    print("=" * 70)

    DRIVE_ROOT  = Path('/content/drive/MyDrive/treedata/Edmonds_Imagery')
    DRIVE_MOSAIC = DRIVE_ROOT / 'mosaics'
    DRIVE_HIST   = DRIVE_ROOT / 'historical'
    DRIVE_ROOT.mkdir(parents=True, exist_ok=True)
    DRIVE_MOSAIC.mkdir(exist_ok=True)
    DRIVE_HIST.mkdir(exist_ok=True)

    GEOREF_DIR = SESSION_DIR / 'georeferenced'
    MOSAIC_DIR = SESSION_DIR / 'mosaics'
    ROTATED_DIR = SESSION_DIR / 'rotated'

    # Build lookup: display_id -> georef file
    georef_by_id = {}
    if GEOREF_DIR.exists():
        for gf in GEOREF_DIR.glob('*_georef.tif'):
            did = gf.stem.replace('_georef', '')
            georef_by_id[did] = gf

    summary_rows = []

    # ── Mosaics (2002+, already georeferenced) ────────────────────────────
    print('\n[1/2] Exporting mosaics...')
    if MOSAIC_DIR.exists():
        for year_dir in sorted(MOSAIC_DIR.iterdir()):
            if not year_dir.is_dir():
                continue
            year = year_dir.name
            src_mosaic = year_dir / f'{year}_mosaic.tif'
            if not src_mosaic.exists():
                continue
            dst_dir = DRIVE_MOSAIC / year
            dst_dir.mkdir(exist_ok=True)
            dst_mosaic = dst_dir / src_mosaic.name
            if dst_mosaic.exists():
                print(f'  ○ {year} mosaic already on Drive — skipping')
                summary_rows.append({'Year': year, 'Type': 'mosaic',
                    'File': src_mosaic.name, 'Status': 'Exists',
                    'Georeference': 'original'})
                continue
            # Check if mosaic has a CRS
            with rasterio.open(src_mosaic) as s:
                has_crs = s.crs is not None
            if has_crs:
                print(f'  Copying {year} mosaic ({src_mosaic.stat().st_size/1024**2:.0f} MB)...', end=' ', flush=True)
                shutil.copy2(src_mosaic, dst_mosaic)
                print('✓')
                georef_status = 'georeferenced'
            else:
                print(f'  Assigning Edmonds georeference to {year} mosaic...', end=' ', flush=True)
                _assign_edmonds_georeference(src_mosaic, dst_mosaic)
                print('✓')
                georef_status = 'edmonds_approx'
            summary_rows.append({'Year': year, 'Type': 'mosaic',
                'File': src_mosaic.name, 'Status': 'Copied',
                'Georeference': georef_status})

    # ── Historical images (pre-2002) ──────────────────────────────────────
    print('\n[2/2] Exporting historical images...')
    if not TRACKING_FILE.exists():
        print('  ⚠ No tracking log found — skipping historical export')
    else:
        tracking_df = pd.read_excel(TRACKING_FILE)
        GEO_DATASETS = {'AERIAL_COMBIN', 'NHAP', 'NAPP'}
        historical = tracking_df[tracking_df['Dataset'].isin(GEO_DATASETS)]

        for _, row in historical.iterrows():
            display_id = row['Display_ID']
            dataset    = row['Dataset']
            year       = str(int(row['Year']))

            dst_dir = DRIVE_HIST / year
            dst_dir.mkdir(exist_ok=True)
            dst_file = dst_dir / f'{display_id}.tif'

            if dst_file.exists():
                print(f'  ○ {display_id} already on Drive — skipping')
                summary_rows.append({'Year': year, 'Type': 'historical',
                    'File': dst_file.name, 'Status': 'Exists', 'Georeference': 'unknown'})
                continue

            # Priority: stage-7 georef > rotated TIF
            if display_id in georef_by_id:
                src_file = georef_by_id[display_id]
                with rasterio.open(src_file) as s:
                    has_crs = s.crs is not None
                if has_crs:
                    print(f'  Copying {display_id} (georeferenced)...', end=' ', flush=True)
                    shutil.copy2(src_file, dst_file)
                    print('✓')
                    georef_status = 'georeferenced'
                else:
                    print(f'  Assigning Edmonds georeference to {display_id}...', end=' ', flush=True)
                    _assign_edmonds_georeference(src_file, dst_file)
                    print('✓')
                    georef_status = 'edmonds_approx'
            else:
                # No georef — find rotated TIF and assign Edmonds position
                rotated_file = ROTATED_DIR / year / dataset / f'{display_id}.tif'
                if not rotated_file.exists():
                    candidates = list((ROTATED_DIR / year / dataset).glob('*.tif')) \
                        if (ROTATED_DIR / year / dataset).exists() else []
                    if not candidates:
                        print(f'  ⚠ {display_id}: no rotated file found — skipping')
                        continue
                    rotated_file = candidates[0]
                print(f'  Assigning Edmonds georeference to {display_id} (no georef)...', end=' ', flush=True)
                _assign_edmonds_georeference(rotated_file, dst_file)
                print('✓')
                georef_status = 'edmonds_approx'

            summary_rows.append({'Year': year, 'Type': 'historical',
                'File': dst_file.name, 'Status': 'Copied',
                'Georeference': georef_status})

    summary_df = pd.DataFrame(summary_rows)
    if not summary_df.empty:
        summary_path = SESSION_DIR / 'Export_Summary.xlsx'
        summary_df.to_excel(summary_path, index=False)
        copied  = (summary_df['Status'] == 'Copied').sum()
        skipped = (summary_df['Status'] == 'Exists').sum()
        georef  = (summary_df['Georeference'] == 'georeferenced').sum()
        approx  = (summary_df['Georeference'] == 'edmonds_approx').sum()
        print(f'\n✓ {copied} file(s) exported, {skipped} already on Drive')
        print(f'  Georeferenced: {georef}  ·  Edmonds approx: {approx}')
        print(f'  Drive path: {DRIVE_ROOT}')
    return summary_df


# ============================================================================
# Pipeline orchestrator
# ============================================================================

class Pipeline:
    """
    Orchestrates all five stages of the Edmonds imagery workflow.

    Parameters
    ----------
    username  : USGS ERS username
    api_token : M2M application token (generate at https://ers.cr.usgs.gov/profile/access)
    """

    def __init__(self, username: str | None = None, api_token: str | None = None):
        self._username  = username
        self._api_token = api_token
        self._api: USGSM2M | None = None

    # ------------------------------------------------------------------
    # Credential helpers
    # ------------------------------------------------------------------

    def _get_credentials(self) -> tuple[str, str]:
        """Return (username, token), prompting if not already set."""
        if not self._username or not self._api_token:
            # Try notebook-level variables first (mirrors old %run behaviour)
            frame = sys.modules.get('__main__')
            if frame:
                self._username  = self._username  or getattr(frame, 'username',  None)
                self._api_token = self._api_token or getattr(frame, 'api_token', None)

        if not self._username:
            self._username = input("USGS username: ")
        if not self._api_token:
            print("Generate token at: https://ers.cr.usgs.gov/profile/access")
            self._api_token = getpass.getpass("M2M Application Token: ")

        return self._username, self._api_token

    def _ensure_api(self) -> USGSM2M:
        if self._api is None:
            user, token = self._get_credentials()
            self._api = USGSM2M(user, token)
        return self._api

    def _close_api(self):
        if self._api:
            self._api.logout()
            self._api = None
            print("✓ Logged out")

    # ------------------------------------------------------------------
    # Individual stage runners
    # ------------------------------------------------------------------

    def run_discover(self) -> pd.DataFrame:
        api = self._ensure_api()
        result = stage_discover(api)
        self._close_api()
        return result

    def run_metadata(self) -> pd.DataFrame:
        print(f"\n[Loading inventory] {INVENTORY_FILE}")
        inventory_df = pd.read_excel(INVENTORY_FILE, sheet_name='Inventory')
        api = self._ensure_api()
        result = stage_metadata(api, inventory_df)
        self._close_api()
        return result

    def run_select(self) -> pd.DataFrame:
        api = self._ensure_api()
        result = stage_select(api)
        self._close_api()
        return result

    def run_download(self) -> pd.DataFrame:
        api = self._ensure_api()
        result = stage_download(api)
        self._close_api()
        return result

    def run_qa(self):
        """Stage 5 does not use the M2M API."""
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        stage_qa()

    def run_process(self) -> pd.DataFrame:
        """Stage 6 does not use the M2M API."""
        return stage_process()

    def run_georeference(self) -> pd.DataFrame:
        """Stage 7 — georeference historical imagery via USGS M2M metadata."""
        api = self._ensure_api()
        result = stage_georeference(api)
        self._close_api()
        return result

    def run_export(self) -> pd.DataFrame:
        """Stage 8 — export all outputs to Google Drive."""
        return stage_export()

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def run_all(self, stages: list[int] | None = None):
        """
        Run the complete pipeline (or a subset).

        Parameters
        ----------
        stages : list of ints, e.g. [1, 2, 3].  None = all five stages.
        """
        stages = stages or [1, 2, 3, 4, 5, 6, 7, 8]
        SESSION_DIR.mkdir(parents=True, exist_ok=True)

        try:
            if 1 in stages:
                self._ensure_api()
                stage_discover(self._api)

            if 2 in stages:
                inventory_df = pd.read_excel(INVENTORY_FILE, sheet_name='Inventory')
                self._ensure_api()
                stage_metadata(self._api, inventory_df)

            if 3 in stages:
                self._ensure_api()
                stage_select(self._api)

            if 4 in stages:
                self._ensure_api()
                stage_download(self._api)

        finally:
            self._close_api()

        if 5 in stages:
            self.run_qa()

        if 6 in stages:
            self.run_process()

        if 7 in stages:
            self.run_georeference()

        if 8 in stages:
            self.run_export()


# ============================================================================
# __main__ entry point  (mirrors the original %run workflow)
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("EDMONDS AERIAL IMAGERY PIPELINE")
    print("=" * 70)
    print(f"\nSession directory: {SESSION_DIR}")
    print("\nFresh start? Wipes all existing session data (logs + imagery).")
    print("Enter 'yes' to wipe, or press Enter to continue existing session: ", end="")
    if input().strip().lower() == 'yes':
        fresh_start()
    else:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        print(f"  Continuing in {SESSION_DIR}\n")
    print("Stages:")
    print("  1 · Discover   – search all aerial datasets")
    print("  2 · Metadata   – collect file sizes / download options")
    print("  3 · Select     – pick optimal scenes per year (requires geopandas)")
    print("  4 · Download   – download pre-2013 high-coverage years")
    print("  5 · QA         – launch interactive review tool")
    print("  6 · Process    – apply rotations and build year mosaics")
    print("  7 · Georeference – fetch USGS metadata and georeference historical imagery")
    print("  8 · Export      – copy all outputs to Google Drive for ArcGIS")
    print("\nEnter stages to run (e.g. '1 2 3 4 5 6 7 8' or press Enter for all): ", end="")
    raw = input().strip()
    chosen = [int(x) for x in raw.split() if x.isdigit()] if raw else None
    p = Pipeline()
    p.run_all(stages=chosen)