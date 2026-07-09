#!/usr/bin/env python3
"""
COMPREHENSIVE EDMONDS SERVER DIAGNOSTIC v2
==========================================
Tests:
1. Geographic heatmap of success/fail chunks
2. Worker count sensitivity (1, 2, 3 workers)
3. Retry logic for failed chunks
4. Random chunk visualizations
5. Chunk size sensitivity (1024px vs 2048px)

Outputs:
- Heatmap showing which grid cells succeed/fail
- Success rate by worker count
- Sample images from random successful chunks
- Full diagnostic log
"""

import os, io, math, time, json, shutil, traceback, gc, psutil
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
from PIL import Image
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ============================================================
#  CONFIG
# ============================================================
from pipeline_config import FULL_IMAGE_DIR
BASE_DIR   = str(FULL_IMAGE_DIR)
LOCAL_TMP  = "/content/tmp_imagery"
XMIN, YMIN, XMAX, YMAX = -13625876.424, 6068463.621, -13614805.955, 6084271.153

EDM_URL = "https://maps.edmondswa.gov/gis/rest/services/Basemap/2020_Aerial_Cached/ImageServer"
NATIVE_EPSG = 3857
RES_M = 0.075
BANDS = 4
TIMEOUT = 180

# Test configurations
TEST_CONFIGS = [
    # (chunk_px, workers, label)
    (2048, 1, "2048px_1worker"),
    (2048, 2, "2048px_2workers"),
    (2048, 3, "2048px_3workers"),
    (1024, 1, "1024px_1worker"),
]

# Number of chunks to test per config
CHUNKS_PER_TEST = 100

# Number of successful chunks to visualize
VISUALIZE_COUNT = 5

LOG_FILE = "/content/diagnostic_v2.log"
RESULTS_DIR = "/content/diagnostic_results"

# ============================================================
#  LOGGING
# ============================================================
def log(msg, to_file=True):
    """Thread-safe logging with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    mem_mb = psutil.Process().memory_info().rss / 1e6
    line = f"[{timestamp}] [MEM:{mem_mb:.0f}MB] {msg}"
    print(line)
    if to_file:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")

# ============================================================
#  HTTP SESSION
# ============================================================
def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": "EdmondsDiagnosticV2/1.0"})
    retry = Retry(
        total=3,
        backoff_factor=2.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s

# ============================================================
#  CHUNK FETCHER WITH RETRY
# ============================================================
def fetch_chunk_with_retry(export_url, params, row, col, max_retries=3):
    """Fetch chunk with retry logic for truncated responses"""
    session = make_session()
    chunk_id = f"[{row},{col}]"
    
    for attempt in range(max_retries):
        try:
            start = time.time()
            resp = session.get(export_url, params=params, timeout=TIMEOUT)
            elapsed = time.time() - start
            
            ct = resp.headers.get("Content-Type", "")
            size_kb = len(resp.content) / 1024
            
            # Check for errors
            if "json" in ct or "html" in ct:
                log(f"FETCH_ERROR {chunk_id} attempt {attempt+1} - got {ct}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # exponential backoff
                    continue
                return None, elapsed, "wrong_content_type"
            
            if len(resp.content) < 500:
                log(f"FETCH_ERROR {chunk_id} attempt {attempt+1} - too small ({len(resp.content)}B)")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None, elapsed, "too_small"
            
            # Try to open as image
            try:
                img = Image.open(io.BytesIO(resp.content))
                arr = np.array(img)
                
                # Check for truncation
                if arr.size == 0 or arr.max() == 0:
                    log(f"FETCH_WARN {chunk_id} attempt {attempt+1} - empty/black image")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None, elapsed, "empty_image"
                
                # Success!
                img.close()
                return resp.content, elapsed, "success"
                
            except Exception as e:
                error_msg = str(e)
                if "truncated" in error_msg.lower():
                    log(f"FETCH_WARN {chunk_id} attempt {attempt+1} - truncated ({size_kb:.0f}KB)")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None, elapsed, "truncated"
                else:
                    log(f"FETCH_ERROR {chunk_id} attempt {attempt+1} - {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None, elapsed, f"decode_error:{e}"
        
        except Exception as e:
            log(f"FETCH_EXCEPTION {chunk_id} attempt {attempt+1} - {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return None, 0, f"exception:{e}"
    
    return None, 0, "max_retries_exceeded"

# ============================================================
#  TEST RUNNER
# ============================================================
def test_configuration(chunk_px, workers, label):
    """Test a single configuration and return results"""
    log("="*60)
    log(f"Testing: {label}")
    log(f"  chunk_px={chunk_px}, workers={workers}")
    log("="*60)
    
    # Calculate grid
    px_unit = RES_M
    chunk_ext = chunk_px * px_unit
    width = XMAX - XMIN
    height = YMAX - YMIN
    ncols = max(1, math.ceil(width / chunk_ext))
    nrows = max(1, math.ceil(height / chunk_ext))
    total_chunks = ncols * nrows
    
    log(f"Grid: {ncols}x{nrows} = {total_chunks} total chunks")
    log(f"Testing first {CHUNKS_PER_TEST} chunks")
    
    # Build work list
    work = []
    export_url = EDM_URL + "/exportImage"
    
    chunk_count = 0
    chunk_map = {}  # (row, col) -> index in work list
    
    for row in range(nrows):
        for col in range(ncols):
            if chunk_count >= CHUNKS_PER_TEST:
                break
            
            cx0 = XMIN + col * chunk_ext
            cx1 = cx0 + chunk_ext
            cy1 = YMAX - row * chunk_ext
            cy0 = cy1 - chunk_ext
            
            params = {
                "bbox": f"{cx0},{cy0},{cx1},{cy1}",
                "bboxSR": NATIVE_EPSG,
                "imageSR": NATIVE_EPSG,
                "size": f"{chunk_px},{chunk_px}",
                "format": "tiff",
                "pixelType": "U8",
                "interpolation": "RSP_BilinearInterpolation",
                "f": "image",
            }
            
            work.append((export_url, params, row, col))
            chunk_map[(row, col)] = chunk_count
            chunk_count += 1
        
        if chunk_count >= CHUNKS_PER_TEST:
            break
    
    # Results tracking
    results = {
        "label": label,
        "chunk_px": chunk_px,
        "workers": workers,
        "grid_size": (ncols, nrows),
        "chunks_tested": len(work),
        "success_count": 0,
        "fail_count": 0,
        "failure_reasons": {},
        "fetch_times": [],
        "chunk_sizes": [],
        "success_map": {},  # (row, col) -> True/False
        "successful_chunks": [],  # list of (row, col, img_bytes) for visualization
    }
    
    # Download
    log("Starting download...")
    start_time = time.time()
    
    pbar = tqdm(total=len(work), desc=f"  {label}", unit="chunk")
    
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_chunk_with_retry, *w): w for w in work}
        
        for fut in as_completed(futures):
            export_url, params, row, col = futures[fut]
            img_bytes, elapsed, status = fut.result()
            
            results["fetch_times"].append(elapsed)
            
            if status == "success":
                results["success_count"] += 1
                results["success_map"][(row, col)] = True
                results["chunk_sizes"].append(len(img_bytes) / 1024)
                
                # Save first N successful chunks for visualization
                if len(results["successful_chunks"]) < VISUALIZE_COUNT:
                    results["successful_chunks"].append((row, col, img_bytes))
            else:
                results["fail_count"] += 1
                results["success_map"][(row, col)] = False
                results["failure_reasons"][status] = results["failure_reasons"].get(status, 0) + 1
            
            pbar.update(1)
    
    pbar.close()
    elapsed_total = time.time() - start_time
    
    # Summary
    success_rate = results["success_count"] / len(work) * 100 if work else 0
    log(f"Results for {label}:")
    log(f"  Success: {results['success_count']}/{len(work)} ({success_rate:.1f}%)")
    log(f"  Failed: {results['fail_count']}/{len(work)}")
    log(f"  Avg fetch time: {np.mean(results['fetch_times']):.2f}s")
    if results["chunk_sizes"]:
        log(f"  Avg chunk size: {np.mean(results['chunk_sizes']):.0f} KB")
    log(f"  Total time: {elapsed_total:.1f}s")
    
    if results["failure_reasons"]:
        log(f"  Failure breakdown:")
        for reason, count in sorted(results["failure_reasons"].items(), key=lambda x: -x[1]):
            log(f"    {reason}: {count}")
    
    return results

# ============================================================
#  VISUALIZATION
# ============================================================
def create_heatmap(all_results):
    """Create heatmap showing success/fail by grid location"""
    log("Creating geographic heatmap...")
    
    # Find grid dimensions
    max_ncols = max(r["grid_size"][0] for r in all_results)
    max_nrows = max(r["grid_size"][1] for r in all_results)
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    axes = axes.flatten()
    
    for idx, result in enumerate(all_results):
        ax = axes[idx]
        
        # Create grid
        grid = np.zeros((max_nrows, max_ncols))
        grid[:] = -1  # -1 = not tested
        
        for (row, col), success in result["success_map"].items():
            grid[row, col] = 1 if success else 0
        
        # Plot
        cmap = plt.cm.colors.ListedColormap(['red', 'lightgray', 'green'])
        bounds = [-1.5, -0.5, 0.5, 1.5]
        norm = plt.cm.colors.BoundaryNorm(bounds, cmap.N)
        
        im = ax.imshow(grid, cmap=cmap, norm=norm, origin='upper', aspect='auto')
        ax.set_title(f"{result['label']}\n{result['success_count']}/{result['chunks_tested']} success ({result['success_count']/result['chunks_tested']*100:.1f}%)")
        ax.set_xlabel("Column (West → East)")
        ax.set_ylabel("Row (North → South)")
        
        # Add grid
        ax.set_xticks(np.arange(max_ncols), minor=True)
        ax.set_yticks(np.arange(max_nrows), minor=True)
        ax.grid(which="minor", color="black", linestyle='-', linewidth=0.5, alpha=0.3)
    
    # Legend
    patches = [
        mpatches.Patch(color='green', label='Success'),
        mpatches.Patch(color='red', label='Failed'),
        mpatches.Patch(color='lightgray', label='Not tested')
    ]
    fig.legend(handles=patches, loc='lower center', ncol=3, bbox_to_anchor=(0.5, -0.02))
    
    plt.tight_layout()
    heatmap_path = os.path.join(RESULTS_DIR, "success_heatmap.png")
    plt.savefig(heatmap_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    log(f"Heatmap saved: {heatmap_path}")
    return heatmap_path

def visualize_successful_chunks(all_results):
    """Create visualization grid of successful chunks"""
    log("Creating chunk visualizations...")
    
    for result in all_results:
        if not result["successful_chunks"]:
            continue
        
        n = len(result["successful_chunks"])
        fig, axes = plt.subplots(1, min(n, 5), figsize=(15, 3))
        if n == 1:
            axes = [axes]
        
        for idx, (row, col, img_bytes) in enumerate(result["successful_chunks"][:5]):
            try:
                img = Image.open(io.BytesIO(img_bytes))
                arr = np.array(img)
                
                # Show RGB (first 3 bands)
                if arr.ndim == 3 and arr.shape[2] >= 3:
                    rgb = arr[:, :, :3]
                else:
                    rgb = arr
                
                axes[idx].imshow(rgb)
                axes[idx].set_title(f"Chunk [{row},{col}]\n{len(img_bytes)/1024:.0f} KB")
                axes[idx].axis('off')
                img.close()
            except Exception as e:
                axes[idx].text(0.5, 0.5, f"Error: {e}", ha='center', va='center')
                axes[idx].axis('off')
        
        plt.tight_layout()
        viz_path = os.path.join(RESULTS_DIR, f"chunks_{result['label']}.png")
        plt.savefig(viz_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        log(f"Chunk visualization saved: {viz_path}")

def create_summary_charts(all_results):
    """Create summary comparison charts"""
    log("Creating summary charts...")
    
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    
    # Chart 1: Success rate by configuration
    labels = [r["label"] for r in all_results]
    success_rates = [r["success_count"] / r["chunks_tested"] * 100 for r in all_results]
    
    axes[0].barh(labels, success_rates, color=['green' if s > 50 else 'red' for s in success_rates])
    axes[0].set_xlabel("Success Rate (%)")
    axes[0].set_title("Success Rate by Configuration")
    axes[0].set_xlim(0, 100)
    for i, v in enumerate(success_rates):
        axes[0].text(v + 2, i, f"{v:.1f}%", va='center')
    
    # Chart 2: Average fetch time
    avg_times = [np.mean(r["fetch_times"]) for r in all_results]
    axes[1].barh(labels, avg_times, color='skyblue')
    axes[1].set_xlabel("Average Fetch Time (s)")
    axes[1].set_title("Fetch Time by Configuration")
    for i, v in enumerate(avg_times):
        axes[1].text(v + 0.1, i, f"{v:.2f}s", va='center')
    
    # Chart 3: Failure reason breakdown (for first config)
    if all_results and all_results[0]["failure_reasons"]:
        reasons = list(all_results[0]["failure_reasons"].keys())
        counts = list(all_results[0]["failure_reasons"].values())
        axes[2].barh(reasons, counts, color='coral')
        axes[2].set_xlabel("Count")
        axes[2].set_title(f"Failure Reasons ({all_results[0]['label']})")
        for i, v in enumerate(counts):
            axes[2].text(v + 0.5, i, str(v), va='center')
    
    plt.tight_layout()
    summary_path = os.path.join(RESULTS_DIR, "summary_charts.png")
    plt.savefig(summary_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    log(f"Summary charts saved: {summary_path}")
    return summary_path

# ============================================================
#  MAIN
# ============================================================
def main():
    # Setup
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
    
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    log("="*60)
    log("COMPREHENSIVE EDMONDS SERVER DIAGNOSTIC V2")
    log("="*60)
    log(f"Test configurations: {len(TEST_CONFIGS)}")
    log(f"Chunks per test: {CHUNKS_PER_TEST}")
    log(f"Results directory: {RESULTS_DIR}")
    log("")
    
    # Run all tests
    all_results = []
    
    for chunk_px, workers, label in TEST_CONFIGS:
        try:
            result = test_configuration(chunk_px, workers, label)
            all_results.append(result)
            
            # Brief cooldown between tests
            log("Cooldown 10s before next test...")
            time.sleep(10)
            gc.collect()
            
        except Exception as e:
            log(f"ERROR testing {label}: {e}")
            traceback.print_exc()
    
    # Generate visualizations
    log("")
    log("="*60)
    log("GENERATING VISUALIZATIONS")
    log("="*60)
    
    try:
        heatmap_path = create_heatmap(all_results)
        visualize_successful_chunks(all_results)
        summary_path = create_summary_charts(all_results)
    except Exception as e:
        log(f"ERROR creating visualizations: {e}")
        traceback.print_exc()
    
    # Save results JSON
    results_json = os.path.join(RESULTS_DIR, "results.json")
    with open(results_json, "w") as f:
        # Remove img_bytes from successful_chunks before saving
        clean_results = []
        for r in all_results:
            clean_r = r.copy()
            clean_r["successful_chunks"] = [
                (row, col, len(img_bytes)) 
                for row, col, img_bytes in r["successful_chunks"]
            ]
            clean_r["success_map"] = {f"{row},{col}": v for (row, col), v in r["success_map"].items()}
            clean_results.append(clean_r)
        
        json.dump(clean_results, f, indent=2)
    
    log(f"Results JSON saved: {results_json}")
    
    # Final summary
    log("")
    log("="*60)
    log("FINAL SUMMARY")
    log("="*60)
    
    for r in all_results:
        success_rate = r["success_count"] / r["chunks_tested"] * 100
        log(f"{r['label']:20s} - {r['success_count']:3d}/{r['chunks_tested']:3d} success ({success_rate:5.1f}%)")
    
    log("")
    log(f"All results saved to: {RESULTS_DIR}")
    log(f"View heatmap: {RESULTS_DIR}/success_heatmap.png")
    log(f"View summary: {RESULTS_DIR}/summary_charts.png")
    log(f"Full log: {LOG_FILE}")
    log("="*60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("INTERRUPTED BY USER")
    except Exception as e:
        log(f"FATAL ERROR: {e}")
        traceback.print_exc()