"""
run_registration.py — Registration orchestrator with memory management
========================================================================
Processes one year at a time with Drive verification and local cleanup.

KEY CHANGE FROM PREVIOUS VERSION:
    Uses direct function calls to coregister_imagery.register_year()
    instead of subprocess.run(). This eliminates the fork() memory spike
    that was pushing RAM to the ceiling before processing even started.

USAGE (Colab cell):
    %run /content/drive/MyDrive/treedata/Scripts/run_registration.py
    %run /content/drive/MyDrive/treedata/Scripts/run_registration.py --years 2013 2015
    %run /content/drive/MyDrive/treedata/Scripts/run_registration.py --skip-coreg

FLOW PER YEAR:
    1. Print RAM and disk before starting
    2. Check if already registered on Drive — skip if valid
    3. Call register_year() directly — no subprocess fork
    4. Verify output on Drive: exists, size > threshold, centre sample non-zero
    5. If pass: clean local scratch, force gc, print RAM after cleanup
    6. If fail: halt with summary
    7. Move to next year
"""

import argparse
import gc
import sys
import time
from pathlib import Path

import psutil
import rasterio
import rasterio.windows
import numpy as np

# ── Config ────────────────────────────────────────────────────
DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")
from pipeline_config import (
    DRIVE_BASE, IMAGERY_DIR, REGISTERED_DIR, UPSAMPLE_DIR,
)
DRIVE_OUTPUT   = REGISTERED_DIR
DRIVE_UPSAMPLE = UPSAMPLE_DIR

LOCAL_SRC_DIR    = Path("/content/source_imagery")
LOCAL_UPSAMPLE   = Path("/content/upsampled")
LOCAL_REGISTERED = Path("/content/registered")

ALL_YEARS         = [2013, 2015, 2017, 2019, 2021, 2022, 2023, 2024]
KING_COUNTY_YEARS = {2013, 2015, 2019, 2021, 2023}

MIN_REGISTERED_GB = 10.0


# ── Memory helpers ────────────────────────────────────────────

def mem(label: str = "") -> float:
    """Print RAM usage with a progress bar. Returns used GB."""
    vm      = psutil.virtual_memory()
    used_gb = vm.used  / 1e9
    tot_gb  = vm.total / 1e9
    pct     = vm.percent
    filled  = int(20 * pct / 100)
    bar     = "█" * filled + "░" * (20 - filled)
    tag     = f"  [{label}]" if label else ""
    print(f"  MEM{tag}: {used_gb:.1f}/{tot_gb:.1f} GB  [{bar}] {pct:.1f}%")
    return used_gb


def disk(label: str = "") -> float:
    """Print local disk free space. Returns free GB."""
    import shutil
    _, _, free = shutil.disk_usage("/content")
    free_gb = free / 1e9
    tag = f"  [{label}]" if label else ""
    print(f"  DISK{tag}: {free_gb:.0f} GB free")
    return free_gb


def collect(label: str = ""):
    """Force garbage collection and print RAM before and after."""
    before = psutil.virtual_memory().used / 1e9
    gc.collect()
    after  = psutil.virtual_memory().used / 1e9
    freed  = before - after
    tag    = f" after {label}" if label else ""
    if freed > 0.1:
        print(f"  GC{tag}: freed {freed:.1f} GB  "
              f"({after:.1f}/{psutil.virtual_memory().total/1e9:.1f} GB remaining)")
    else:
        mem(f"gc{(' ' + label) if label else ''}")


def check_ram_headroom(min_free_gb: float = 15.0) -> bool:
    """Warn if RAM headroom is below threshold before starting a year."""
    vm      = psutil.virtual_memory()
    free_gb = vm.available / 1e9
    if free_gb < min_free_gb:
        print(f"  WARNING: only {free_gb:.1f} GB RAM available "
              f"(recommended >= {min_free_gb:.0f} GB)")
        print(f"  Consider restarting runtime if upsample OOMs")
        return False
    return True


# ── Verification ──────────────────────────────────────────────

def verify_registered(year: int) -> tuple:
    """
    Verify a registered output on Drive.
    Returns (passed: bool, message: str).
    Checks: exists, size > MIN_REGISTERED_GB, centre sample non-zero.
    """
    out_path = DRIVE_OUTPUT / f"{year}_edmonds_registered.tif"

    if not out_path.exists():
        return False, f"Not found on Drive: {out_path.name}"

    size_gb = out_path.stat().st_size / 1e9
    if size_gb < MIN_REGISTERED_GB:
        return False, f"Too small: {size_gb:.2f} GB (min {MIN_REGISTERED_GB} GB)"

    try:
        with rasterio.open(out_path) as src:
            w, h = src.width, src.height
            cx, cy = w // 2, h // 2
            win    = rasterio.windows.Window(cx - 256, cy - 256, 512, 512)
            sample = src.read(1, window=win)
            if sample.max() == 0:
                return False, "Centre sample all zeros — corrupt"
            bands = src.count
    except Exception as e:
        return False, f"Failed to open: {e}"

    return True, (f"OK — {size_gb:.1f} GB  {w}x{h} px  "
                  f"{bands} bands  centre max={int(sample.max())}")


# ── Local cleanup ─────────────────────────────────────────────

def clean_local(year: int):
    """Delete all local scratch files for a year and force gc."""
    patterns = [
        (LOCAL_SRC_DIR,    f"{year}_edmonds.tif"),
        (LOCAL_UPSAMPLE,   f"{year}_edmonds_upsampled.tif"),
        (LOCAL_REGISTERED, f"{year}_edmonds_registered.tif"),
    ]
    freed_gb = 0.0
    for directory, filename in patterns:
        f = directory / filename
        if f.exists():
            size_gb = f.stat().st_size / 1e9
            f.unlink()
            freed_gb += size_gb
            print(f"    Deleted local: {filename}  ({size_gb:.1f} GB)")

    if freed_gb > 0:
        print(f"    Freed: {freed_gb:.1f} GB local disk")
    else:
        print(f"    No local files for {year}")

    collect(f"{year} cleanup")


# ── Main orchestrator ─────────────────────────────────────────

def run(years: list = None, skip_coreg: bool = False):
    """
    Run registration for a list of years, one at a time.
    Calls register_year() directly — no subprocess fork, no RAM spike.
    """
    if years is None:
        years = ALL_YEARS

    # Import coregister_imagery in-process — no fork
    scripts_dir = str(DRIVE_BASE / "Scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    if "coregister_imagery" in sys.modules:
        del sys.modules["coregister_imagery"]
    import coregister_imagery as coreg

    print("=" * 60)
    print("  REGISTRATION ORCHESTRATOR")
    print("=" * 60)
    print(f"  Years      : {years}")
    print(f"  Skip coreg : {skip_coreg}")
    print(f"  Drive out  : {DRIVE_OUTPUT}")
    mem("startup")
    disk("startup")
    print()

    for d in [LOCAL_SRC_DIR, LOCAL_UPSAMPLE, LOCAL_REGISTERED, DRIVE_OUTPUT]:
        d.mkdir(parents=True, exist_ok=True)

    # Load reference profile and buildings once — reused across all years
    # Avoids reloading 23,666 building polygons per year
    ref_path = coreg.raw_imagery_path(coreg.REFERENCE_YEAR)
    with rasterio.open(ref_path) as src:
        ref_crs     = src.crs
        ref_profile = src.profile.copy()

    buildings = coreg.load_buildings(ref_crs)
    collect("after buildings load")

    results = []

    for i, year in enumerate(years):
        print(f"\n{'='*60}")
        print(f"  YEAR {year}  ({i+1}/{len(years)})")
        mem(f"{year} start")
        disk(f"{year} start")
        print(f"{'='*60}")

        check_ram_headroom(min_free_gb=15.0)

        # ── Skip if already done ──────────────────────────────
        passed, msg = verify_registered(year)
        if passed:
            print(f"  Already on Drive — skipping")
            print(f"  {msg}")
            results.append((year, "skipped", msg))
            continue

        # ── Register — direct call, no subprocess fork ────────
        print(f"\n  Registering {year}...")
        t0 = time.time()

        try:
            log     = coreg.register_year(year, buildings, ref_profile,
                                          skip_coreg=skip_coreg)
            success = log["passed"]
        except Exception as e:
            log     = {"passed": False, "notes": str(e)}
            success = False
            print(f"  FATAL: {e}")

        elapsed = time.time() - t0
        print(f"\n  Finished in {elapsed/60:.1f} min")
        mem(f"{year} after register_year")

        # Release tile buffers, control point arrays, warp buffers
        collect(f"{year} post-register")

        # ── Verify Drive output ───────────────────────────────
        print(f"\n  Verifying Drive output...")
        time.sleep(3)

        passed, msg = verify_registered(year)
        if passed:
            print(f"  PASS: {msg}")
            results.append((year, "pass", msg))
        else:
            print(f"  FAIL: {msg}")
            print(f"  Halting — fix {year} before continuing")
            results.append((year, "fail", msg))
            _print_summary(results)
            return results

        # ── Clean local scratch ───────────────────────────────
        print(f"\n  Cleaning local scratch for {year}...")
        clean_local(year)
        disk(f"{year} after cleanup")

    _print_summary(results)
    return results


def _print_summary(results):
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    for year, status, msg in results:
        icon = "✓" if status in ("pass", "skipped") else "✗"
        print(f"  {icon} {year}  [{status.upper()}]  {msg}")
    passed = sum(1 for _, s, _ in results if s in ("pass", "skipped"))
    print(f"\n  {passed}/{len(results)} years complete")
    mem("final")


# ── CLI ───────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, nargs="+", default=None)
    parser.add_argument("--skip-coreg", action="store_true")

    filtered = [a for a in sys.argv[1:]
                if not (a == "-f" or a.endswith(".json"))]
    args = parser.parse_args(filtered)
    run(years=args.years, skip_coreg=args.skip_coreg)
