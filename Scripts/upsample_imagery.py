"""
Upsample Imagery — Edmonds Temporal Pipeline
============================================
Reprojects all source imagery to match the 2020 reference grid:
  - Same CRS       : EPSG:3857
  - Same resolution: 0.0746 m (7.62 cm)
  - Same dimensions: 148736 x 211968 px
  - Same transform : snapped to 2020 pixel grid

City of Edmonds years (2017, 2020, 2022, 2024) are already on the
correct grid — they are copied to the output folder unchanged.

All other years are reprojected using cubic resampling:
  King County  (0.1493 m) — 2013, 2015, 2019, 2021, 2023
  Snohomish Co.(0.5000 m) — 2016, 2021*
  NAIP         (variable) — 2019*, 2022*

Upsampled files are cached in DRIVE_UPSAMPLE and reused on
subsequent runs. Re-run is safe — existing valid files are skipped.

COLAB SETUP
-----------
    from google.colab import drive
    drive.mount('/content/drive')
    !pip install rasterio numpy tqdm psutil -q

USAGE
-----
    %run upsample_imagery.py              # all years
    %run upsample_imagery.py --year 2013  # single year
    %run upsample_imagery.py --year 2013 --force  # force rebuild

OUTPUT
------
    Pipeline Imagery/upsample/{stem}_upsampled.tif   all non-CoE years
    Pipeline Imagery/upsample/2017_coe_rgb.tif       CoE years (copied)
    Pipeline Imagery/upsample/2020_coe_rgb.tif
    Pipeline Imagery/upsample/2022_coe_rgb.tif
    Pipeline Imagery/upsample/2024_coe_rgb.tif
"""

import argparse
import ctypes
import gc
import multiprocessing as mp
import os
import shutil
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import psutil
import rasterio
import rasterio.warp
import rasterio.windows
from rasterio.enums import Resampling
from rasterio.transform import Affine
from tqdm import tqdm

warnings.filterwarnings("ignore")


# ══════════════════════════════════════════════════════════════
# PATHS
# ══════════════════════════════════════════════════════════════

DRIVE_BASE     = Path("/content/drive/MyDrive/treedata")
IMAGERY_DIR    = DRIVE_BASE / "Full_Image/Pipeline Imagery"
DRIVE_UPSAMPLE = IMAGERY_DIR / "upsample"
LOCAL_SRC_DIR  = Path("/content/source_imagery")
LOCAL_OUT_DIR  = Path("/content/upsampled")

REFERENCE_YEAR = 2020


# ══════════════════════════════════════════════════════════════
# IMAGERY CATALOGUE
# ══════════════════════════════════════════════════════════════
#
# needs_upsample=False  → already on 2020 grid, copy only
# needs_upsample=True   → reproject to 2020 grid

IMAGERY_CATALOG = {
    2013:    {"file": "2013_king_rgb.tif",    "needs_upsample": True},
    2015:    {"file": "2015_king_rgb.tif",    "needs_upsample": True},
    2016:    {"file": "2016_snoh_rgbi.tif",   "needs_upsample": True},
    2017:    {"file": "2017_coe_rgb.tif",     "needs_upsample": False},
    2019:    {"file": "2019_king_rgb.tif",    "needs_upsample": True},
    "2019n": {"file": "2019_naip_rgbi.tif",  "needs_upsample": True},
    2020:    {"file": "2020_coe_rgb.tif",     "needs_upsample": False},
    2021:    {"file": "2021_king_rgb.tif",    "needs_upsample": True},
    "2021s": {"file": "2021_snoh_rgbi.tif",  "needs_upsample": True},
    2022:    {"file": "2022_coe_rgb.tif",     "needs_upsample": False},
    "2022n": {"file": "2022_naip_rgbi.tif",  "needs_upsample": True},
    2023:    {"file": "2023_king_rgb.tif",    "needs_upsample": True},
    2024:    {"file": "2024_coe_rgb.tif",     "needs_upsample": False},
}

TARGET_YEARS = list(IMAGERY_CATALOG.keys())


# ══════════════════════════════════════════════════════════════
# TUNING
# ══════════════════════════════════════════════════════════════

UPSAMPLE_CHUNK_PX      = 4096
N_UPSAMPLE_WORKERS     = 3
WORKER_BATCH_SIZE      = 10
WORKER_STALL_TIMEOUT_S = 180   # 3 min — if no chunk arrives, abort
POOL_SCALE_THRESHOLD   = 2     # scale factors ≤ this use single-threaded reproject


# ══════════════════════════════════════════════════════════════
# MEMORY / CACHE HELPERS
# ══════════════════════════════════════════════════════════════

def mem(label: str = "") -> float:
    vm       = psutil.virtual_memory()
    used_gb  = vm.used  / 1e9
    total_gb = vm.total / 1e9
    pct      = vm.percent
    bar      = "█" * int(20 * pct / 100) + "░" * (20 - int(20 * pct / 100))
    tag      = f"  [{label}]" if label else ""
    print(f"  MEM{tag}: {used_gb:.1f}/{total_gb:.1f} GB  [{bar}] {pct:.1f}%",
          flush=True)
    return used_gb


def _trim():
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def _drop_page_cache_file(path: Path):
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        with open(path, "rb") as fh:
            libc.posix_fadvise(fh.fileno(), 0, 0, 4)
    except Exception:
        pass


def drop_all_page_cache(silent: bool = False):
    try:
        if not silent:
            subprocess.run(["sync"], check=False, timeout=30)
        with open("/proc/sys/vm/drop_caches", "w") as f:
            f.write("1\n")
        if not silent:
            vm = psutil.virtual_memory()
            print(f"  Page cache dropped — RAM now: "
                  f"{vm.used/1e9:.1f}/{vm.total/1e9:.1f} GB ({vm.percent:.1f}%)",
                  flush=True)
    except Exception as e:
        if not silent:
            print(f"  Could not drop page cache: {e}", flush=True)


# ══════════════════════════════════════════════════════════════
# TIMING
# ══════════════════════════════════════════════════════════════

_TIMER_STACK: list = []
_TIMER_LOG:   list = []


def tick(label: str = "") -> float:
    t0 = time.time()
    _TIMER_STACK.append((label, t0))
    return t0


def tock(label: str = "") -> float:
    t1 = time.time()
    if not _TIMER_STACK:
        return 0.0
    stored_label, t0 = _TIMER_STACK.pop()
    display_label    = label or stored_label or "unnamed"
    elapsed_s        = t1 - t0
    if elapsed_s < 1.0:
        disp = f"{elapsed_s*1000:.0f} ms"
    elif elapsed_s < 120:
        disp = f"{elapsed_s:.1f} s"
    else:
        disp = f"{elapsed_s/60:.1f} min"
    depth  = len(_TIMER_STACK)
    indent = "  " + "  " * depth
    bar    = "▓" * min(20, int(20 * elapsed_s / 300)) + "░" * max(0, 20 - int(20 * elapsed_s / 300))
    print(f"{indent}⏱  {display_label:<40}  {disp:>10}  [{bar}]", flush=True)
    _TIMER_LOG.append({"label": display_label, "elapsed_s": elapsed_s})
    return elapsed_s


def timer_summary():
    if not _TIMER_LOG:
        return
    sorted_log = sorted(_TIMER_LOG, key=lambda x: x["elapsed_s"], reverse=True)
    total = sum(x["elapsed_s"] for x in sorted_log)
    print("\n" + "═" * 60)
    print(f"  TIMING SUMMARY  (total: {total/60:.1f} min)")
    print("═" * 60)
    for entry in sorted_log:
        e   = entry["elapsed_s"]
        pct = 100 * e / total if total > 0 else 0
        bar = "▓" * int(20 * pct / 100) + "░" * (20 - int(20 * pct / 100))
        disp = f"{e*1000:.0f} ms" if e < 1 else f"{e:.1f} s" if e < 120 else f"{e/60:.1f} min"
        print(f"  {entry['label']:<42}  {disp:>8}  {pct:5.1f}%  [{bar}]")
    print("═" * 60)


# ══════════════════════════════════════════════════════════════
# PATH HELPERS
# ══════════════════════════════════════════════════════════════

def _entry(year) -> dict:
    if year not in IMAGERY_CATALOG:
        raise KeyError(f"Year {year!r} not in IMAGERY_CATALOG")
    return IMAGERY_CATALOG[year]


def raw_path(year) -> Path:
    return IMAGERY_DIR / _entry(year)["file"]


def _stem(year) -> str:
    return _entry(year)["file"].replace(".tif", "")


def output_filename(year) -> str:
    """
    CoE years keep their original name (no _upsampled suffix).
    All other years get _upsampled suffix.
    """
    entry = _entry(year)
    if not entry["needs_upsample"]:
        return entry["file"]
    return f"{_stem(year)}_upsampled.tif"


def drive_output_path(year) -> Path:
    return DRIVE_UPSAMPLE / output_filename(year)


def local_output_path(year) -> Path:
    return LOCAL_OUT_DIR / output_filename(year)


def metres_per_pixel(transform) -> float:
    return abs(transform.a)


def make_tile_windows(width: int, height: int, tile_size: int):
    windows = []
    for row_off in range(0, height, tile_size):
        for col_off in range(0, width, tile_size):
            w = min(tile_size, width  - col_off)
            h = min(tile_size, height - row_off)
            windows.append(rasterio.windows.Window(col_off, row_off, w, h))
    return windows


# ══════════════════════════════════════════════════════════════
# VALIDATE OUTPUT
# ══════════════════════════════════════════════════════════════

def _validate(path: Path, ref_profile: dict) -> tuple[bool, str]:
    """Return (valid, reason). Checks dimensions, band count, and centre sample."""
    if not path.exists():
        return False, "file not found"
    size_gb = path.stat().st_size / 1e9
    if size_gb < 0.5:
        return False, f"too small ({size_gb:.2f} GB)"
    try:
        with rasterio.open(path) as src:
            if src.width  != ref_profile["width"]:
                return False, f"width mismatch ({src.width} != {ref_profile['width']})"
            if src.height != ref_profile["height"]:
                return False, f"height mismatch ({src.height} != {ref_profile['height']})"
            cx  = src.width  // 2
            cy  = src.height // 2
            win = rasterio.windows.Window(cx - 256, cy - 256, 512, 512)
            s   = src.read(1, window=win)
            if s.max() == 0:
                return False, "centre sample all zeros — corrupt"
    except Exception as e:
        return False, f"open failed: {e}"
    return True, f"OK  {size_gb:.1f} GB  {path.name}"


# ══════════════════════════════════════════════════════════════
# WORKER — chunk reprojection
# ══════════════════════════════════════════════════════════════

def _reproject_chunk_batch(args):
    import time as _t
    import os as _os
    import numpy as _np
    import rasterio as _rio
    import rasterio.warp as _rwarp
    from rasterio.enums import Resampling as _R
    from rasterio.transform import Affine as _Affine

    (src_path_str, band_i, chunk_list,
     src_transform_tuple, src_crs_wkt, dst_crs_wkt,
     src_dtype, gdal_cachemax) = args

    _os.environ["GDAL_CACHEMAX"] = str(gdal_cachemax)
    worker_pid = _os.getpid()
    results    = []

    try:
        src_f = _rio.open(src_path_str)
        src_open_ok = True
    except Exception as e:
        src_open_ok  = False
        src_open_err = str(e)

    src_t = _Affine(*src_transform_tuple)

    for (col_off, row_off, chunk_w, chunk_h, dst_transform_tuple) in chunk_list:
        t_start   = _t.time()
        dst_t     = _Affine(*dst_transform_tuple)
        dst_arr   = _np.zeros((chunk_h, chunk_w), dtype=src_dtype)
        failed    = False
        error_msg = ""
        open_ms   = 0
        proj_ms   = 0

        if not src_open_ok:
            failed    = True
            error_msg = src_open_err
        else:
            try:
                t_proj = _t.time()
                _rwarp.reproject(
                    source        = _rio.band(src_f, band_i),
                    destination   = dst_arr,
                    src_transform = src_t,
                    src_crs       = src_crs_wkt,
                    dst_transform = dst_t,
                    dst_crs       = dst_crs_wkt,
                    resampling    = _R.cubic,
                )
                proj_ms = int((_t.time() - t_proj) * 1000)
            except Exception as e:
                dst_arr[:] = 0
                failed     = True
                error_msg  = str(e)

        total_ms = int((_t.time() - t_start) * 1000)
        results.append((
            band_i, col_off, row_off, chunk_w, chunk_h,
            dst_arr, failed, error_msg,
            worker_pid, open_ms, proj_ms, total_ms,
        ))

    if src_open_ok:
        src_f.close()
    return results


# ══════════════════════════════════════════════════════════════
# SINGLE-THREADED FULL-BAND REPROJECT
# ══════════════════════════════════════════════════════════════

def _do_fullband_reproject(local_src: Path, dst_local: Path,
                           src_count: int, src_dtype,
                           src_transform, src_crs: str,
                           ref_profile: dict, dst_crs: str,
                           year):
    profile = ref_profile.copy()
    profile.pop("photometric", None)
    profile.update(count=src_count, dtype=src_dtype,
                   compress="lzw", predictor=2, bigtiff="IF_SAFER",
                   tiled=True, blockxsize=512, blockysize=512)

    src_t = Affine(*src_transform) if isinstance(src_transform, tuple) \
            else src_transform

    try:
        with rasterio.open(dst_local, "w", **profile) as dst:
            for band_i in tqdm(range(1, src_count + 1),
                               desc=f"  Reprojecting {year} bands"):
                tick(f"band {band_i}/{src_count}")
                with rasterio.open(str(local_src)) as src:
                    rasterio.warp.reproject(
                        source        = rasterio.band(src, band_i),
                        destination   = rasterio.band(dst, band_i),
                        src_transform = src_t,
                        src_crs       = src_crs,
                        dst_transform = ref_profile["transform"],
                        dst_crs       = ref_profile["crs"],
                        resampling    = Resampling.cubic,
                    )
                tock(f"band {band_i}/{src_count}")
                gc.collect()
    except Exception as e:
        if dst_local.exists():
            dst_local.unlink()
            print(f"  Partial output deleted: {dst_local.name}", flush=True)
        raise


# ══════════════════════════════════════════════════════════════
# PARALLEL CHUNKED REPROJECT
# ══════════════════════════════════════════════════════════════

def _do_chunked_reproject(local_src: Path, dst_local: Path,
                          src_count: int, src_dtype,
                          src_transform, src_crs: str,
                          ref_profile: dict, dst_crs: str,
                          year):
    out_w         = ref_profile["width"]
    out_h         = ref_profile["height"]
    out_transform = ref_profile["transform"]

    profile = ref_profile.copy()
    profile.pop("photometric", None)
    profile.update(count=src_count, dtype=src_dtype,
                   compress="lzw", predictor=2, bigtiff="IF_SAFER",
                   tiled=True, blockxsize=512, blockysize=512)

    chunk_windows = make_tile_windows(out_w, out_h, UPSAMPLE_CHUNK_PX)
    n_chunks      = len(chunk_windows)

    N_DIAG_CHUNKS = 20
    failed_chunks = 0
    band_timings  = []

    try:
        _spawn_ctx = mp.get_context("spawn")
    except Exception:
        _spawn_ctx = mp

    print(f"\n  Pre-allocating output file...", flush=True)
    with rasterio.open(dst_local, "w", **profile):
        pass

    for band_i in range(1, src_count + 1):
        print(f"\n  {'═'*50}", flush=True)
        print(f"  BAND {band_i}/{src_count}  —  year {year}", flush=True)
        mem(f"{year} band {band_i} start")

        band_tasks = [
            (win.col_off, win.row_off, win.width, win.height,
             tuple(rasterio.windows.transform(win, out_transform)))
            for win in chunk_windows
        ]
        band_batches = [
            band_tasks[i:i + WORKER_BATCH_SIZE]
            for i in range(0, len(band_tasks), WORKER_BATCH_SIZE)
        ]
        batch_args = [
            (str(local_src), band_i, batch,
             src_transform, src_crs, dst_crs,
             src_dtype, 512)
            for batch in band_batches
        ]

        completed   = 0
        band_failed = 0
        seen_pids   = set()
        times_ms    = []
        last_t      = time.time()
        band_t0     = time.time()

        tick(f"band {band_i}/{src_count}")

        with rasterio.open(dst_local, "r+") as dst:
            with _spawn_ctx.Pool(processes=N_UPSAMPLE_WORKERS,
                                 maxtasksperchild=None) as pool:

                async_iter = pool.imap_unordered(
                    _reproject_chunk_batch, batch_args, chunksize=1)

                pbar = tqdm(total=len(band_tasks),
                            desc=f"  band {band_i} chunks",
                            mininterval=10, miniters=50)

                while completed < len(band_tasks):
                    # Stall detection
                    wait_s = time.time() - last_t
                    if wait_s > WORKER_STALL_TIMEOUT_S:
                        pool.terminate()
                        pool.join()
                        pbar.close()
                        raise RuntimeError(
                            f"Stalled for {wait_s:.0f}s at chunk "
                            f"{completed}/{len(band_tasks)} "
                            f"band {band_i} year {year}")

                    try:
                        batch_results = next(async_iter)
                    except StopIteration:
                        break
                    except Exception as e:
                        print(f"  [ERR] imap raised: {e}", flush=True)
                        completed   += WORKER_BATCH_SIZE
                        band_failed += WORKER_BATCH_SIZE
                        pbar.update(WORKER_BATCH_SIZE)
                        last_t = time.time()
                        continue

                    last_t = time.time()

                    for result in batch_results:
                        (b_i, col_off, row_off, cw, ch,
                         arr, failed, error_msg,
                         worker_pid, open_ms, proj_ms, total_ms) = result

                        seen_pids.add(worker_pid)
                        times_ms.append(total_ms)

                        if completed < N_DIAG_CHUNKS:
                            status = "FAIL" if failed else "ok"
                            print(f"  [DIAG] chunk {completed:>4}  "
                                  f"col={col_off:>6}  row={row_off:>6}  "
                                  f"pid={worker_pid}  "
                                  f"proj={proj_ms}ms  total={total_ms}ms  "
                                  f"[{status}]"
                                  + (f"  ERR: {error_msg}" if failed else ""),
                                  flush=True)

                        if completed > 0 and completed % 200 == 0:
                            elapsed = time.time() - band_t0
                            rate    = completed / elapsed if elapsed > 0 else 0
                            eta_s   = (len(band_tasks) - completed) / rate \
                                      if rate > 0 else 0
                            recent  = times_ms[-200:]
                            avg_ms  = sum(recent) // len(recent)
                            print(f"\n  [PROG] chunk {completed}/{len(band_tasks)}  "
                                  f"({100*completed/len(band_tasks):.1f}%)  "
                                  f"rate={rate:.1f}/s  ETA={eta_s/60:.1f}min  "
                                  f"avg={avg_ms}ms  workers={len(seen_pids)}",
                                  flush=True)
                            mem(f"{year} band {band_i} chunk {completed}")

                        win = rasterio.windows.Window(col_off, row_off, cw, ch)
                        try:
                            dst.write(arr, band_i, window=win)
                        except Exception as we:
                            print(f"  [ERR] write chunk {completed}: {we}",
                                  flush=True)
                            band_failed += 1

                        if failed:
                            band_failed += 1

                        del arr
                        del result
                        completed   += 1
                        pbar.update(1)

                    if completed % 100 == 0:
                        _trim()

                pbar.close()

        band_elapsed = tock(f"band {band_i}/{src_count}")
        band_timings.append((band_i, band_elapsed, band_failed))
        failed_chunks += band_failed

        print(f"\n  Band {band_i}: {band_elapsed/60:.1f} min  "
              f"({band_failed} failed chunks)", flush=True)
        if times_ms:
            print(f"  Chunk timing: min={min(times_ms)}ms  "
                  f"max={max(times_ms)}ms  "
                  f"mean={sum(times_ms)//len(times_ms)}ms", flush=True)

        _drop_page_cache_file(dst_local)
        _trim()

    if failed_chunks > 0:
        print(f"\n  Total failed chunks: {failed_chunks}/{n_chunks * src_count}",
              flush=True)


# ══════════════════════════════════════════════════════════════
# UPSAMPLE ONE YEAR
# ══════════════════════════════════════════════════════════════

def upsample_year(year, ref_profile: dict, force: bool = False) -> Path:
    """
    Reproject one year to the 2020 reference grid.
    Returns the path to the Drive output file.
    CoE years (needs_upsample=False) are copied rather than reprojected.
    """
    entry      = _entry(year)
    src_path   = raw_path(year)
    drive_dst  = drive_output_path(year)
    local_dst  = local_output_path(year)

    print(f"\n  {'─'*56}", flush=True)
    print(f"  YEAR {year}  —  {src_path.name}", flush=True)
    print(f"  {'─'*56}", flush=True)

    if not src_path.exists():
        raise FileNotFoundError(f"Source not found: {src_path}")

    # ── CoE years: copy to upsample folder unchanged ──────────
    if not entry["needs_upsample"]:
        if drive_dst.exists() and not force:
            ok, msg = _validate(drive_dst, ref_profile)
            if ok:
                print(f"  Already in upsample folder — skipping: {msg}",
                      flush=True)
                return drive_dst
            else:
                print(f"  Existing file invalid ({msg}) — re-copying",
                      flush=True)

        print(f"  City of Edmonds year — copying to upsample folder",
              flush=True)
        tick("copy: CoE → upsample folder")
        shutil.copy2(src_path, drive_dst)
        tock("copy: CoE → upsample folder")
        print(f"  ✓ {drive_dst.name}  "
              f"({drive_dst.stat().st_size/1e9:.2f} GB)", flush=True)
        return drive_dst

    # ── Check Drive cache ─────────────────────────────────────
    if drive_dst.exists() and not force:
        ok, msg = _validate(drive_dst, ref_profile)
        if ok:
            print(f"  Drive cache valid — skipping: {msg}", flush=True)
            return drive_dst
        else:
            print(f"  Drive cache invalid ({msg}) — rebuilding", flush=True)
            drive_dst.unlink()

    # ── Copy source to local disk ─────────────────────────────
    local_src = LOCAL_SRC_DIR / src_path.name
    if not local_src.exists() or local_src.stat().st_size < 1e9:
        LOCAL_SRC_DIR.mkdir(parents=True, exist_ok=True)
        size_gb = src_path.stat().st_size / 1e9
        print(f"  Copying source to local SSD: {src_path.name}  "
              f"({size_gb:.1f} GB)", flush=True)
        tick("copy: Drive → local SSD")
        shutil.copy2(src_path, local_src)
        tock("copy: Drive → local SSD")
        drop_all_page_cache()
        mem(f"{year} after source copy")
    else:
        print(f"  Source already local: {local_src.name}  "
              f"({local_src.stat().st_size/1e9:.1f} GB)", flush=True)

    # ── Read source metadata ──────────────────────────────────
    with rasterio.open(local_src) as src_f:
        src_res       = metres_per_pixel(src_f.transform)
        ref_res       = metres_per_pixel(ref_profile["transform"])
        scale_factor  = src_res / ref_res
        src_count     = src_f.count
        src_dtype     = src_f.dtypes[0]
        src_crs       = src_f.crs.to_wkt()
        src_transform = tuple(src_f.transform)
        src_w         = src_f.width
        src_h         = src_f.height

    print(f"  Source       : {src_w}x{src_h} px  "
          f"{src_count} bands  {src_dtype}", flush=True)
    print(f"  Scale factor : {src_res:.4f}m → {ref_res:.4f}m  "
          f"(x{scale_factor:.2f})", flush=True)
    print(f"  Output       : {ref_profile['width']}x{ref_profile['height']} px",
          flush=True)

    LOCAL_OUT_DIR.mkdir(parents=True, exist_ok=True)
    dst_crs = ref_profile["crs"].to_wkt() \
              if hasattr(ref_profile["crs"], "to_wkt") \
              else str(ref_profile["crs"])

    os.environ["GDAL_CACHEMAX"] = "256"
    tick(f"upsample {year}")

    try:
        if scale_factor <= POOL_SCALE_THRESHOLD:
            print(f"  Strategy: single-threaded full-band reproject "
                  f"(scale {scale_factor:.2f}x ≤ {POOL_SCALE_THRESHOLD}x)",
                  flush=True)
            _do_fullband_reproject(
                local_src, local_dst,
                src_count, src_dtype, src_transform, src_crs,
                ref_profile, dst_crs, year)
        else:
            print(f"  Strategy: parallel chunked reproject "
                  f"(scale {scale_factor:.2f}x > {POOL_SCALE_THRESHOLD}x  "
                  f"{N_UPSAMPLE_WORKERS} workers)", flush=True)
            _do_chunked_reproject(
                local_src, local_dst,
                src_count, src_dtype, src_transform, src_crs,
                ref_profile, dst_crs, year)

    except Exception as e:
        if local_dst.exists():
            local_dst.unlink()
            print(f"  Partial output deleted: {local_dst.name}", flush=True)
        raise RuntimeError(f"Upsample failed for {year}: {e}") from e

    tock(f"upsample {year}")

    # ── Validate ──────────────────────────────────────────────
    ok, msg = _validate(local_dst, ref_profile)
    if not ok:
        local_dst.unlink()
        raise RuntimeError(f"Validation failed for {year}: {msg}")
    print(f"  Validation: {msg}", flush=True)
    mem(f"{year} after upsample")

    # ── Copy to Drive ─────────────────────────────────────────
    DRIVE_UPSAMPLE.mkdir(parents=True, exist_ok=True)
    size_gb = local_dst.stat().st_size / 1e9
    print(f"\n  Copying to Drive ({size_gb:.1f} GB)...", flush=True)
    tick("copy: local → Drive")
    shutil.copy2(local_dst, drive_dst)
    tock("copy: local → Drive")
    drop_all_page_cache()
    print(f"  ✓ Drive: {drive_dst.name}  "
          f"({drive_dst.stat().st_size/1e9:.2f} GB)", flush=True)

    return drive_dst


# ══════════════════════════════════════════════════════════════
# CLEAN LOCAL SCRATCH
# ══════════════════════════════════════════════════════════════

def _clean_local(year):
    freed = 0.0
    for path in [LOCAL_SRC_DIR / _entry(year)["file"],
                 local_output_path(year)]:
        if path.exists():
            size_gb = path.stat().st_size / 1e9
            path.unlink()
            freed += size_gb
            print(f"    Deleted: {path.name}  ({size_gb:.1f} GB)", flush=True)
    if freed > 0:
        print(f"    Freed: {freed:.1f} GB", flush=True)
    _trim()
    mem(f"{year} after cleanup")


# ══════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ══════════════════════════════════════════════════════════════

def run(years: list = None, force: bool = False):
    if years is None:
        years = TARGET_YEARS

    print("=" * 60, flush=True)
    print("  UPSAMPLE IMAGERY — Edmonds Temporal Pipeline", flush=True)
    print("=" * 60, flush=True)
    print(f"  Years     : {years}", flush=True)
    print(f"  Force     : {force}", flush=True)
    print(f"  Drive out : {DRIVE_UPSAMPLE}", flush=True)
    print(f"  Reference : {REFERENCE_YEAR}", flush=True)

    mem("startup")
    _, _, free = shutil.disk_usage("/content")
    print(f"  Local disk: {free/1e9:.0f} GB free", flush=True)

    for d in [LOCAL_SRC_DIR, LOCAL_OUT_DIR, DRIVE_UPSAMPLE]:
        d.mkdir(parents=True, exist_ok=True)

    # Load reference profile from 2020 source
    ref_src = IMAGERY_DIR / IMAGERY_CATALOG[REFERENCE_YEAR]["file"]
    if not ref_src.exists():
        print(f"\n  ERROR: Reference imagery not found: {ref_src}", flush=True)
        sys.exit(1)
    with rasterio.open(ref_src) as src:
        ref_profile = src.profile.copy()
    print(f"\n  Reference profile: {ref_profile['width']}x{ref_profile['height']}  "
          f"{ref_profile['crs']}  {metres_per_pixel(ref_profile['transform']):.4f} m/px",
          flush=True)

    results = []

    for i, year in enumerate(years):
        print(f"\n{'='*60}", flush=True)
        print(f"  YEAR {year}  ({i+1}/{len(years)})", flush=True)
        print(f"{'='*60}", flush=True)

        t0 = time.time()
        try:
            out = upsample_year(year, ref_profile, force=force)
            elapsed = time.time() - t0
            results.append((year, "pass", f"{out.name}  ({elapsed/60:.1f} min)"))
        except Exception as e:
            import traceback
            elapsed = time.time() - t0
            print(f"\n  FATAL: {e}", flush=True)
            traceback.print_exc()
            results.append((year, "fail", str(e)))

        gc.collect()
        mem(f"{year} after gc")

        if _entry(year)["needs_upsample"]:
            print(f"\n  Cleaning local scratch for {year}...", flush=True)
            _clean_local(year)

    # ── Summary ───────────────────────────────────────────────
    print(f"\n{'='*60}", flush=True)
    print(f"  SUMMARY", flush=True)
    print(f"{'='*60}", flush=True)
    for year, status, msg in results:
        icon = "✓" if status == "pass" else "✗"
        print(f"  {icon} {year}  [{status.upper()}]  {msg}", flush=True)
    passed = sum(1 for _, s, _ in results if s == "pass")
    print(f"\n  {passed}/{len(results)} years complete", flush=True)
    print(f"  Output: {DRIVE_UPSAMPLE}", flush=True)

    timer_summary()
    return results


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if not hasattr(sys.modules["__main__"], "__spec__"):
        sys.modules["__main__"].__spec__ = None
    mp.set_start_method("spawn", force=True)

    parser = argparse.ArgumentParser(
        description="Upsample all imagery to 2020 reference grid")
    parser.add_argument(
        "--year", type=str, default=None,
        help="Single year to process (e.g. 2013, 2019n, 2021s)")
    parser.add_argument(
        "--force", action="store_true",
        help="Force rebuild even if output already exists")

    filtered = [a for a in sys.argv[1:]
                if not (a == "-f" or a.endswith(".json"))]
    args = parser.parse_args(filtered)

    years = None
    if args.year:
        key = args.year
        try:
            key = int(key)
        except ValueError:
            pass
        years = [key]

    run(years=years, force=args.force)
