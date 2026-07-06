#!/usr/bin/env python3
"""
BATCH ORCHESTRATOR — Subprocess isolation for zero memory leaks
================================================================
Runs each batch in a completely fresh Python subprocess.
Memory resets to ~100 MB between batches.

Usage:
  import os
  os.environ["YEAR"] = "2020"
  %run edmonds_batch_orchestrator.py
"""

import os, subprocess, time
import rasterio
from rasterio.merge import merge

YEAR = os.environ.get("YEAR", "2020")
BATCH_DIR = "/content/tmp_batches"
from pipeline_config import IMAGERY_DIR
OUTPUT_DIR = str(IMAGERY_DIR)
SINGLE_BATCH_SCRIPT = "/content/drive/MyDrive/treedata/Scripts/edmonds_single_batch.py"

# Total chunks after coverage filter: 3811
# Batches needed: ceil(3811 / 500) = 8
NUM_BATCHES = 8

print("="*72)
print(f"  BATCH ORCHESTRATOR — {YEAR}")
print(f"  Running {NUM_BATCHES} batches in isolated subprocesses")
print("="*72)

batch_files = []

for batch_num in range(NUM_BATCHES):
    print(f"\n{'='*72}")
    print(f"  BATCH {batch_num}/{NUM_BATCHES-1}")
    print(f"{'='*72}")
    
    # Check if already exists
    batch_path = os.path.join(BATCH_DIR, f"batch_{batch_num:04d}.tif")
    if os.path.exists(batch_path):
        sz_mb = os.path.getsize(batch_path) / 1e6
        print(f"  Batch {batch_num} already exists ({sz_mb:.1f} MB), skipping")
        batch_files.append(batch_path)
        continue
    
    # Run in fresh subprocess
    env = os.environ.copy()
    env["YEAR"] = YEAR
    env["BATCH_NUM"] = str(batch_num)
    
    try:
        result = subprocess.run(
            ["python3", SINGLE_BATCH_SCRIPT],
            env=env,
            capture_output=True,  # capture to show errors
            text=True,
        )
        
        # Show output
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        if result.returncode != 0:
            print(f"  ERROR: Batch {batch_num} failed with return code {result.returncode}")
            continue
        
        # Verify file was created
        if os.path.exists(batch_path):
            batch_files.append(batch_path)
        else:
            print(f"  ERROR: Batch {batch_num} completed but file not found")
    
    except Exception as e:
        print(f"  ERROR running batch {batch_num}: {e}")
        import traceback
        traceback.print_exc()

print()
print("="*72)
print("  STITCHING BATCHES")
print("="*72)

if len(batch_files) < NUM_BATCHES:
    print(f"  WARNING: Only {len(batch_files)}/{NUM_BATCHES} batches completed")
    print(f"  Proceeding with available batches...")

if not batch_files:
    print("  ERROR: No batch files to merge!")
else:
    print(f"  Merging {len(batch_files)} batch files...")
    
    try:
        # Open all batch files
        src_files = [rasterio.open(f) for f in batch_files]
        
        # Merge
        mosaic, out_trans = merge(src_files)
        
        # Close sources
        for src in src_files:
            src.close()
        
        # Write final output
        out_path = os.path.join(OUTPUT_DIR, f"{YEAR}_coe_rgb.tif")
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        out_meta = src_files[0].meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": mosaic.shape[1],
            "width": mosaic.shape[2],
            "transform": out_trans,
            "compress": "deflate",
            "predictor": 2,
            "tiled": True,
            "blockxsize": 512,
            "blockysize": 512,
            "BIGTIFF": "YES",
        })
        
        with rasterio.open(out_path, "w", **out_meta) as dst:
            dst.write(mosaic)
        
        sz_mb = os.path.getsize(out_path) / 1e6
        print(f"\n  SUCCESS! Final file: {out_path}")
        print(f"  Size: {sz_mb:.1f} MB")
        
        # Cleanup batch files
        print(f"\n  Cleaning up {len(batch_files)} batch files...")
        for bf in batch_files:
            try:
                os.remove(bf)
                print(f"    Removed: {os.path.basename(bf)}")
            except:
                pass
        
        print("\n  DONE!")
        
    except Exception as e:
        print(f"\n  ERROR during merge: {e}")
        import traceback
        traceback.print_exc()