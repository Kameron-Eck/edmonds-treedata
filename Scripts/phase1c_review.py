"""
PHASE 1C — Crown Review
========================
Preprocessing script for the Edmonds tree crown review pipeline.

What this script does
─────────────────────
1.  Copies 2020 imagery to local Colab SSD (~3-5 min, once per session)
2.  Extracts 512×512 px JPEG crops for all 61,271 review-queue crowns
    from local disk (~2 min at ~500 crops/sec)
3.  Computes crown polygon outlines in crop-pixel space (~1 min)
4.  Writes manifest.json + review_app.html to local disk
5.  Backs up manifest.json to Drive
6.  Starts a unified HTTP server (static files + /label POST endpoint)
    that streams every label decision to reviews_live.csv on Drive
    in real time

Architecture
────────────
Single server on port 8888 handles everything:
  GET  /manifest.json   → serves 61k-crown manifest
  GET  /crops/*.jpg     → serves crop images
  GET  /review_app.html → serves the review UI
  POST /label           → appends label row to CSV on Drive + local backup
  GET  /status          → returns row count and CSV path

No Flask, no second port, no Colab proxy URL expiry issues.

Sync status indicator in the browser
─────────────────────────────────────
  🟢 Green  — last label confirmed written to Drive
  🟡 Amber  — POST in flight
  🔴 Red    — server unreachable, labels buffered in localStorage
              with count shown. Buffered labels are retried
              automatically when connection is restored.

Conflict resolution (two reviewers, same crown)
────────────────────────────────────────────────
  Same label     → merged, assigned randomly to one reviewer
  Different label → written with conflict="conflict" flag for re-review

PREREQUISITES
─────────────
Phases 0, 1, 1A, 1B complete:
  treedata/phase1/edmonds_crowns_phase1.gpkg
  treedata/phase1b/review_queue.gpkg

COLAB SETUP
─────────────
    from google.colab import drive
    drive.mount('/content/drive')
    !pip install rasterio geopandas numpy pillow tqdm -q
    %run phase1c_review.py

RE-RUNNING (fresh Colab session)
─────────────────────────────────
    %run phase1c_review.py
    # Detects existing local imagery and crops, skips re-extraction.
    # Full restart takes ~6-8 min from cold.
"""

import csv
import datetime
import http.server
import json
import math
import os
import random
import shutil
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import rasterio.windows
from PIL import Image
from tqdm import tqdm

# ══════════════════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════════════════

DRIVE_BASE    = Path("/content/drive/MyDrive/treedata")
QUEUE_GPKG    = DRIVE_BASE / "phase1b/review_queue.gpkg"
IMAGERY_DRIVE = DRIVE_BASE / "Full_Image/Pipeline Imagery/upsample/2020_coe_rgb.tif"
IMAGERY_LOCAL = Path("/content/2020_coe_rgb.tif")
DRIVE_OUT     = DRIVE_BASE / "phase1c"
LOCAL_OUT     = Path("/content/phase1c")
CROP_SIZE     = 512
PORT          = 8888

# External HTML template — loaded at runtime instead of inline
# The template file is co-located with this script or in DRIVE_OUT
SCRIPT_DIR        = Path(__file__).parent if "__file__" in dir() else Path(".")
HTML_TEMPLATE     = SCRIPT_DIR / "review_app_template.html"
HTML_TEMPLATE_ALT = DRIVE_BASE / "phase1c/review_app_template.html"

CSV_DRIVE     = DRIVE_OUT  / "reviews_live.csv"
CSV_LOCAL     = LOCAL_OUT  / "reviews_live_local.csv"

FIELDNAMES    = [
    "ts", "crown_id", "reviewer", "label_code", "label",
    "stratum_id", "stratum_name", "n_veg_years",
    "median_vs_roof", "bldg_dist_m", "impervious_frac",
    "area_m2", "centroid_x", "centroid_y", "conflict"
]

HIGH_ALPHA_YEARS = [
    "2016", "2017", "2019", "2019n", "2020",
    "2021", "2021s", "2022", "2022n", "2023", "2024"
]

# Set at runtime by ensure_local_imagery()
IMAGERY_TIF = IMAGERY_DRIVE


# ── Timing helpers (from phase1_preprocess.py) ────────────────────────────────

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
    bar    = ("▓" * min(20, int(20 * elapsed_s / 300))
              + "░" * max(0, 20 - int(20 * elapsed_s / 300)))
    print(f"{indent}⏱  {display_label:<40}  {disp:>10}  [{bar}]",
          flush=True)
    _TIMER_LOG.append({"label": display_label, "elapsed_s": elapsed_s})
    return elapsed_s


def timer_summary():
    if not _TIMER_LOG:
        return
    sorted_log = sorted(_TIMER_LOG,
                        key=lambda x: x["elapsed_s"], reverse=True)
    total = sum(x["elapsed_s"] for x in sorted_log)
    print("\n" + "═" * 60)
    print(f"  TIMING SUMMARY  (total: {total/60:.1f} min)")
    print("═" * 60)
    for entry in sorted_log:
        e   = entry["elapsed_s"]
        pct = 100 * e / total if total > 0 else 0
        bar = ("▓" * int(20 * pct / 100)
               + "░" * (20 - int(20 * pct / 100)))
        disp = (f"{e*1000:.0f} ms" if e < 1
                else f"{e:.1f} s" if e < 120
                else f"{e/60:.1f} min")
        print(f"  {entry['label']:<42}  {disp:>8}  "
              f"{pct:5.1f}%  [{bar}]")
    print("═" * 60)


def load_review_app_html() -> str:
    """
    Load the review app HTML from an external template file.
    Falls back to the inline REVIEW_APP_HTML constant if no
    template file is found.
    """
    for path in [HTML_TEMPLATE, HTML_TEMPLATE_ALT]:
        if path.exists():
            html = path.read_text(encoding="utf-8")
            print(f"  ✓ Loaded review app template: {path.name}")
            return html
    # Fallback: use the inline constant (kept for backwards compat)
    print(f"  ⚠ No external template found — using inline HTML")
    return REVIEW_APP_HTML


# ══════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════

def _is_nan(v):
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False


def _safe_float(v, decimals=3):
    if v is None or _is_nan(v):
        return None
    return round(float(v), decimals)


def _write_csv_row(path: Path, row: dict):
    is_new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        if is_new:
            w.writeheader()
        w.writerow(row)


def _csv_row_count(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path) as f:
        return sum(1 for _ in f) - 1


def _check_conflict(crown_id: str, new_label: str,
                    new_reviewer: str) -> str:
    """
    Returns 'ok', 'merged', or 'conflict'.
    Reads only from local CSV for speed.
    """
    src = CSV_LOCAL if CSV_LOCAL.exists() else CSV_DRIVE
    if not src.exists():
        return "ok"
    try:
        rows = []
        with open(src) as f:
            for r in csv.DictReader(f):
                if r["crown_id"] == crown_id and r["label"] != "undo":
                    rows.append(r)
        if not rows:
            return "ok"
        last = rows[-1]
        if last["reviewer"] == new_reviewer:
            return "ok"
        return "merged" if last["label"] == new_label else "conflict"
    except Exception:
        return "ok"


# ══════════════════════════════════════════════════════════════
#  STEP 1 — VALIDATE
# ══════════════════════════════════════════════════════════════

def validate():
    print("\n── Validating inputs ──")
    ok = True
    for label, path in [("Queue GeoPackage", QUEUE_GPKG),
                         ("2020 imagery",     IMAGERY_DRIVE)]:
        if path.exists():
            print(f"  ✓ {label}: {path.name}")
        else:
            print(f"  ✗ {label} NOT FOUND: {path}")
            ok = False
    if not ok:
        sys.exit(1)


# ══════════════════════════════════════════════════════════════
#  STEP 2 — LOCAL IMAGERY
# ══════════════════════════════════════════════════════════════

def ensure_local_imagery():
    """
    Copy 2020 imagery from Drive to local NVMe.
    Local reads are ~50× faster than Drive FUSE for random tile access.
    Sets global IMAGERY_TIF to the local path.
    """
    global IMAGERY_TIF
    if IMAGERY_LOCAL.exists():
        print(f"  ✓ Imagery already local "
              f"({IMAGERY_LOCAL.stat().st_size/1e9:.1f} GB)")
        IMAGERY_TIF = IMAGERY_LOCAL
        return
    print(f"  Copying 2020 imagery to local disk (~27 GB, ~3-5 min)...")
    start = time.time()
    shutil.copy2(IMAGERY_DRIVE, IMAGERY_LOCAL)
    elapsed = time.time() - start
    print(f"  ✓ Done in {elapsed/60:.1f} min  "
          f"({IMAGERY_LOCAL.stat().st_size/1e9:.1f} GB)")
    IMAGERY_TIF = IMAGERY_LOCAL


# ══════════════════════════════════════════════════════════════
#  STEP 3 — LOAD QUEUE
# ══════════════════════════════════════════════════════════════

def load_queue() -> gpd.GeoDataFrame:
    print(f"\n── Loading Phase 1B review queue ──")
    gdf = gpd.read_file(QUEUE_GPKG)
    print(f"  Crowns  : {len(gdf):,}")
    print(f"  Columns : {len(gdf.columns)}")

    with rasterio.open(IMAGERY_TIF) as src:
        img_crs = src.crs
    if gdf.crs != img_crs:
        print(f"  Reprojecting: {gdf.crs} → {img_crs}")
        gdf = gdf.to_crs(img_crs)

    gdf["centroid_x"] = gdf.geometry.centroid.x
    gdf["centroid_y"] = gdf.geometry.centroid.y

    print(f"\n  Stratum breakdown:")
    for sid in sorted(gdf["stratum_id"].unique()):
        chunk = gdf[gdf["stratum_id"] == sid]
        label = (chunk["stratum_label"].iloc[0]
                 if "stratum_label" in chunk.columns
                 else f"Stratum {sid}")
        print(f"    {sid}: {label:<38} {len(chunk):>7,}")

    return gdf


# ══════════════════════════════════════════════════════════════
#  STEP 4 — EXTRACT CROPS
# ══════════════════════════════════════════════════════════════

def extract_crops(gdf: gpd.GeoDataFrame) -> list:
    """
    Write JPEG crops to local /content/phase1c/crops/.
    Skips any crown whose JPEG already exists locally.
    Always reads from local imagery (fast NVMe).
    """
    crops_local = LOCAL_OUT / "crops"
    crops_local.mkdir(parents=True, exist_ok=True)

    existing   = {f.stem for f in crops_local.glob("*.jpg")}
    to_extract = len(gdf) - len(existing)

    print(f"\n── Extracting crops ──")
    print(f"  Imagery     : {IMAGERY_TIF.name}")
    print(f"  Destination : {crops_local}")
    print(f"  Existing    : {len(existing):,}")
    print(f"  To extract  : {to_extract:,}")

    manifest  = []
    skipped   = 0
    extracted = 0
    half      = CROP_SIZE // 2

    with rasterio.open(IMAGERY_TIF) as src:
        img_h, img_w = src.height, src.width
        transform    = src.transform

        for _, row in tqdm(gdf.iterrows(), total=len(gdf),
                           desc="  Cropping"):
            cx    = row["centroid_x"]
            cy    = row["centroid_y"]
            col   = int((cx - transform.c) / transform.a)
            r     = int((cy - transform.f) / transform.e)
            c0, r0 = col - half, r - half
            c1, r1 = c0 + CROP_SIZE, r0 + CROP_SIZE
            fname  = f"{row['crown_id']}.jpg"

            if c0 < 0 or r0 < 0 or c1 > img_w or r1 > img_h:
                skipped += 1
                continue

            if row["crown_id"] not in existing:
                win  = rasterio.windows.Window(
                    col_off=c0, row_off=r0,
                    width=CROP_SIZE, height=CROP_SIZE)
                crop = src.read([1, 2, 3], window=win)
                Image.fromarray(crop.transpose(1, 2, 0)).save(
                    crops_local / fname,
                    format="JPEG", quality=82, optimize=True)
                extracted += 1

            entry = {
                "id":                row["crown_id"],
                "crop":              f"crops/{fname}",
                "centroid_x":        round(float(cx), 1),
                "centroid_y":        round(float(cy), 1),
                "pixel_col":         col,
                "pixel_row":         r,
                "area_m2":           round(float(row.get("area_m2", 0)), 2),
                "size_class":        str(row.get("size_class", "unknown")),
                "stratum_id":        int(row.get("stratum_id", -1)),
                "stratum_name":      str(row.get("stratum_name", "")),
                "stratum_label":     str(row.get("stratum_label", "")),
                "bldg_dist_m":       round(float(row.get("bldg_dist_m", 0)), 2),
                "impervious_frac":   round(float(row.get("impervious_frac", 0)), 3),
                "within_water":      bool(row.get("within_water", False)),
                "roof_score_nearby": round(float(row.get("roof_score_nearby", 0)), 3),
                "n_veg_years":       int(row.get("n_veg_years", 0)),
                "n_high_alpha":      int(row.get("n_high_alpha", 0)),
                "median_vs_roof":    _safe_float(row.get("median_vs_roof"), 3),
                "outline":           [],
                "ndvi_pct_by_year":  {},
            }

            for yr in HIGH_ALPHA_YEARS:
                val = row.get(f"ndvi_pct_{yr}")
                if val is not None and not _is_nan(val):
                    entry["ndvi_pct_by_year"][yr] = round(float(val), 1)

            # R/G ratio for reddish ornamental detection
            # Compute max across confirmed summer years
            summer_rg_years = ["2019n", "2022n", "2022", "2024"]
            rg_vals = []
            for yr in summer_rg_years:
                r_col = f"rgb_mean_r_{yr}"
                g_col = f"rgb_mean_g_{yr}"
                r_val = row.get(r_col)
                g_val = row.get(g_col)
                if (r_val is not None and g_val is not None
                        and not _is_nan(r_val) and not _is_nan(g_val)
                        and float(g_val) > 0):
                    rg_vals.append(float(r_val) / float(g_val))
            entry["rg_max_summer"] = (
                round(max(rg_vals), 3) if rg_vals else None)

            manifest.append(entry)

    print(f"\n  Extracted   : {extracted:,}")
    print(f"  Total local : {len(list(crops_local.glob('*.jpg'))):,}")
    print(f"  Manifest    : {len(manifest):,}")
    if skipped:
        print(f"  Skipped     : {skipped}")
    return manifest


# ══════════════════════════════════════════════════════════════
#  STEP 5 — CROWN OUTLINES
# ══════════════════════════════════════════════════════════════

def compute_outlines(gdf: gpd.GeoDataFrame,
                     manifest: list) -> list:
    """
    Convert crown polygon exterior rings to pixel-space coordinates
    within each crop window. Keeps every 2nd point to halve data size.
    """
    print(f"\n── Computing crown outlines ──")

    with rasterio.open(IMAGERY_TIF) as src:
        transform = src.transform

    half   = CROP_SIZE // 2
    id_map = {row["crown_id"]: row for _, row in gdf.iterrows()}

    for entry in tqdm(manifest, desc="  Outlines"):
        row = id_map.get(entry["id"])
        if row is None:
            continue
        geom       = row.geometry
        col_center = entry["pixel_col"]
        row_center = entry["pixel_row"]
        try:
            if geom.geom_type == "Polygon":
                coords = list(geom.exterior.coords)
            elif geom.geom_type == "MultiPolygon":
                largest = max(geom.geoms, key=lambda g: g.area)
                coords  = list(largest.exterior.coords)
            else:
                coords = []
            coords = coords[::2]
            entry["outline"] = [
                [round((gx - transform.c) / transform.a
                       - (col_center - half), 1),
                 round((gy - transform.f) / transform.e
                       - (row_center - half), 1)]
                for gx, gy in coords
            ]
        except Exception:
            entry["outline"] = []

    return manifest


# ══════════════════════════════════════════════════════════════
#  STEP 6 — WRITE MANIFEST + APP
# ══════════════════════════════════════════════════════════════

def write_local(manifest: list, gdf: gpd.GeoDataFrame):
    strata_summary = []
    for sid in sorted(gdf["stratum_id"].unique()):
        chunk = gdf[gdf["stratum_id"] == sid]
        strata_summary.append({
            "id":    int(sid),
            "name":  str(chunk["stratum_name"].iloc[0]),
            "label": str(chunk["stratum_label"].iloc[0]),
            "count": len(chunk)
        })

    data = {
        "version":          4,
        "created":          datetime.datetime.now().isoformat(),
        "imagery_year":     2020,
        "crop_size_px":     CROP_SIZE,
        "total_crowns":     len(manifest),
        "high_alpha_years": HIGH_ALPHA_YEARS,
        "strata":           strata_summary,
        "crowns":           manifest,
    }

    # Drop fields not needed in browser to reduce parse time
    for c in data["crowns"]:
        c.pop("pixel_col", None)
        c.pop("pixel_row", None)

    raw = json.dumps(data, separators=(",", ":"))
    for bad, fix in [(":NaN,",  ":null,"), (":NaN}",  ":null}"),
                     (":NaN]",  ":null]"), (":Infinity,",  ":null,"),
                     (":-Infinity,", ":null,")]:
        raw = raw.replace(bad, fix)

    manifest_path = LOCAL_OUT / "manifest.json"
    manifest_path.write_text(raw, encoding="utf-8")
    print(f"  ✓ manifest.json  ({manifest_path.stat().st_size/1e6:.1f} MB)")

    app_path = LOCAL_OUT / "review_app.html"
    app_html = load_review_app_html()
    app_path.write_text(app_html, encoding="utf-8")
    print(f"  ✓ review_app.html  ({app_path.stat().st_size/1024:.0f} KB)")


def backup_manifest_to_drive():
    DRIVE_OUT.mkdir(parents=True, exist_ok=True)
    for fname in ["manifest.json", "review_app.html"]:
        src = LOCAL_OUT / fname
        if src.exists():
            shutil.copy2(src, DRIVE_OUT / fname)
            print(f"  ✓ {fname} → Drive")


# ══════════════════════════════════════════════════════════════
#  STEP 7 — UNIFIED HTTP + LABEL SERVER
# ══════════════════════════════════════════════════════════════

def make_handler(static_dir: Path,
                 csv_drive: Path,
                 csv_local: Path):
    """
    Returns an HTTP handler class that serves static files AND
    handles POST /label and GET /status on the same port.
    No Flask, no second proxy URL — works reliably through Colab proxy.
    """

    class Handler(http.server.SimpleHTTPRequestHandler):

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(static_dir), **kwargs)

        # ── POST /label ───────────────────────────────────────
        def do_POST(self):
            if self.path != "/label":
                self.send_response(404)
                self.end_headers()
                return

            length  = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
            ts      = payload.get("ts",
                                  datetime.datetime.utcnow().isoformat())

            if payload.get("label") == "undo":
                row = {k: "" for k in FIELDNAMES}
                row.update(ts=ts,
                           crown_id=payload.get("crown_id", ""),
                           reviewer=payload.get("reviewer", ""),
                           label_code=-1, label="undo", conflict="")
                _write_csv_row(csv_local, row)
                try:
                    _write_csv_row(csv_drive, row)
                    resp = {"status": "ok", "drive": True}
                except Exception as e:
                    resp = {"status": "ok", "drive": False, "err": str(e)}
                self._json(resp)
                return

            # Conflict check
            conflict = _check_conflict(
                payload.get("crown_id", ""),
                payload.get("label", ""),
                payload.get("reviewer", ""))

            # Merge: randomly assign to one reviewer
            if conflict == "merged":
                candidates = [payload.get("reviewer", "")]
                try:
                    src = csv_local if csv_local.exists() else csv_drive
                    with open(src) as f:
                        for r in csv.DictReader(f):
                            if (r["crown_id"] == payload.get("crown_id")
                                    and r["label"] != "undo"):
                                candidates.append(r["reviewer"])
                except Exception:
                    pass
                payload["reviewer"] = random.choice(candidates)

            row = {k: payload.get(k, "") for k in FIELDNAMES}
            row["ts"]       = ts
            row["conflict"] = (conflict
                               if conflict in ("merged", "conflict")
                               else "")

            # Always write local first
            _write_csv_row(csv_local, row)

            # Then Drive
            drive_ok = True
            try:
                _write_csv_row(csv_drive, row)
            except Exception as e:
                drive_ok = False

            self._json({
                "status":    "ok",
                "conflict":  conflict,
                "drive":     drive_ok,
                "row_count": _csv_row_count(csv_local),
            })

        # ── GET /status ───────────────────────────────────────
        def do_GET(self):
            if self.path == "/status":
                self._json({
                    "status":      "ok",
                    "rows_local":  _csv_row_count(csv_local),
                    "rows_drive":  _csv_row_count(csv_drive),
                    "csv_drive":   str(csv_drive),
                })
                return
            super().do_GET()

        # ── CORS pre-flight ───────────────────────────────────
        def do_OPTIONS(self):
            self.send_response(200)
            self._cors()
            self.end_headers()

        def _json(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)

        def _cors(self):
            self.send_header("Access-Control-Allow-Origin",  "*")
            self.send_header("Access-Control-Allow-Methods", "POST,GET,OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def log_message(self, fmt, *args):
            # Only log label POSTs — suppress noisy static file GETs
            msg = args[0] if args else ""
            if "/label" in msg or "/status" in msg:
                print(f"  [{datetime.datetime.now().strftime('%H:%M:%S')}] "
                      f"{fmt % args}")

    return Handler


def start_server():
    import requests
    from google.colab.output import eval_js
    from IPython.display import display, HTML

    print(f"\n── Starting unified server (port {PORT}) ──")

    # Kill any existing server on this port
    os.system(f'pkill -f "http.server {PORT}" 2>/dev/null')
    os.system(f'fuser -k {PORT}/tcp 2>/dev/null')
    time.sleep(2)

    Handler = make_handler(LOCAL_OUT, CSV_DRIVE, CSV_LOCAL)

    server = socketserver.ThreadingTCPServer(("", PORT), Handler)
    server.allow_reuse_address = True

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(1)

    # Verify
    try:
        r = requests.get(f"http://localhost:{PORT}/manifest.json",
                         timeout=8)
        print(f"  ✓ Static files — manifest: "
              f"{r.status_code} ({len(r.content)/1e6:.1f} MB)")
    except Exception as e:
        print(f"  ✗ Static check failed: {e}")

    try:
        r = requests.get(f"http://localhost:{PORT}/status", timeout=4)
        d = r.json()
        print(f"  ✓ Label endpoint — rows: "
              f"local={d['rows_local']}  drive={d['rows_drive']}")
    except Exception as e:
        print(f"  ✗ Label check failed: {e}")

    # Get Colab proxy URL
    proxy_url = eval_js(f"google.colab.kernel.proxyPort({PORT})")
    review_url = proxy_url + "/review_app.html"

    print(f"\n  Open in Chrome:")
    print(f"  {review_url}")
    display(HTML(
        f'<a href="{review_url}" target="_blank" '
        f'style="font-size:16px;font-family:monospace;color:#58a6ff">'
        f'→ Open Crown Reviewer</a>'
    ))

    return server


# ══════════════════════════════════════════════════════════════
#  REVIEW APP HTML
# ══════════════════════════════════════════════════════════════

REVIEW_APP_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Crown Reviewer — Edmonds Tree Detection QA</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body {
  background:#0d1117; color:#c9d1d9;
  font-family:'JetBrains Mono',monospace,sans-serif;
  font-size:12px; height:100vh; overflow:hidden;
  user-select:none; display:flex; flex-direction:column;
}
.topbar {
  display:flex; align-items:center; justify-content:space-between;
  padding:7px 14px; background:#161b22;
  border-bottom:1px solid #21262d; flex-shrink:0; gap:8px; flex-wrap:wrap;
}
.topbar .title { font-size:13px; font-weight:700; color:#58a6ff; }
.topbar .subtitle { color:#484f58; font-size:10px; margin-left:10px; }
.topbar .filters { display:flex; gap:6px; flex-wrap:wrap; align-items:center; }
.topbar button {
  background:transparent; border:1px solid transparent;
  color:#484f58; padding:3px 9px; border-radius:4px;
  cursor:pointer; font-size:10px; font-family:inherit;
}
.topbar button.active { background:#21262d; border-color:#30363d; color:#58a6ff; }
.main { display:flex; flex:1; overflow:hidden; }
.canvas-area {
  flex:1; display:flex; flex-direction:column;
  align-items:center; justify-content:center; position:relative;
}
#cropCanvas {
  border-radius:8px; border:2px solid #21262d;
  transition:border-color .15s; cursor:crosshair;
  max-width:90%; max-height:62vh;
}
#cropCanvas.cat-0 { border-color:#c62828bb; }
#cropCanvas.cat-1 { border-color:#2e7d32bb; }
#cropCanvas.cat-2 { border-color:#e6a817bb; }
#cropCanvas.cat-3 { border-color:#7b1fa2bb; }
.cat-banner {
  position:absolute; top:10px; left:50%; transform:translateX(-50%);
  padding:4px 14px; border-radius:4px; font-size:11px; font-weight:700;
  letter-spacing:.8px; display:none; z-index:10; pointer-events:none;
}
.cat-banner.show { display:block; }
.cat-banner.cat-0 { background:#c62828; color:#fff; }
.cat-banner.cat-1 { background:#2e7d32; color:#fff; }
.cat-banner.cat-2 { background:#e6a817; color:#1a1a1a; }
.cat-banner.cat-3 { background:#7b1fa2; color:#fff; }
.actions {
  display:flex; gap:8px; margin-top:12px;
  align-items:center; flex-wrap:wrap; justify-content:center;
}
.btn-cat {
  border:none; color:#fff; padding:9px 14px; border-radius:7px;
  cursor:pointer; font-size:11px; font-family:inherit;
  font-weight:700; letter-spacing:.4px; min-width:96px;
  display:flex; flex-direction:column; align-items:center; gap:2px;
  transition:transform .1s;
}
.btn-cat:active { transform:scale(.95); }
.key-hint { font-size:9px; opacity:.55; font-weight:400; }
.btn-cat-0 { background:#c62828; }
.btn-cat-1 { background:#2e7d32; }
.btn-cat-2 { background:#c79100; color:#1a1a1a; }
.btn-cat-3 { background:#7b1fa2; }
.nav-row { display:flex; align-items:center; gap:14px; margin-top:8px; }
.nav-pos { font-size:14px; color:#c9d1d9; }
.btn-undo {
  background:transparent; border:1px solid #30363d; color:#484f58;
  padding:3px 10px; border-radius:4px; cursor:pointer;
  font-size:10px; font-family:inherit;
}
.scroll-hint { color:#484f58; font-size:10px; margin-top:4px; text-align:center; }
.zoom-ctrls {
  position:absolute; bottom:10px; left:10px;
  display:flex; gap:3px; align-items:center;
}
.zoom-ctrls button {
  background:#21262d; border:1px solid #30363d; color:#c9d1d9;
  width:26px; height:26px; border-radius:4px; cursor:pointer;
  font-size:13px; font-family:inherit;
}
.zoom-lbl { padding:0 6px; color:#484f58; font-size:10px; }
.panel {
  width:260px; background:#161b22; border-left:1px solid #21262d;
  padding:14px; display:flex; flex-direction:column;
  gap:12px; overflow-y:auto; flex-shrink:0;
}
.sec-title {
  color:#484f58; font-size:9px; text-transform:uppercase;
  letter-spacing:.9px; margin-bottom:7px;
}
.row { display:flex; justify-content:space-between; margin-bottom:4px; }
.row .lbl { color:#484f58; }
.row .val { color:#c9d1d9; font-weight:600; }
.stratum-badge {
  display:inline-block; padding:2px 8px; border-radius:3px;
  font-size:10px; font-weight:700; margin-bottom:6px;
}
.s1 { background:#3d1f10; color:#D85A30; }
.s2 { background:#2a1f3d; color:#9B8FE8; }
.s3 { background:#3d2d10; color:#E8A040; }
.s4 { background:#0f2d20; color:#40C080; }
.s5 { background:#2a2a2a; color:#888780; }
.reddish-badge {
  display:inline-block; padding:2px 8px; border-radius:3px;
  font-size:10px; font-weight:700; margin-bottom:4px;
  background:#3d1020; color:#E8609A; letter-spacing:.4px;
}
.sparkline-wrap {
  margin-top:4px; border:1px solid #21262d; border-radius:4px;
  padding:6px; background:#0d1117;
}
.spark-bars { display:flex; gap:2px; align-items:flex-end; height:36px; }
.spark-bar { flex:1; border-radius:2px 2px 0 0; min-height:2px; }
.spark-labels { display:flex; gap:2px; margin-top:3px; }
.spark-lbl {
  flex:1; font-size:7px; color:#484f58; text-align:center;
  overflow:hidden; white-space:nowrap;
}
.progress-bar { height:4px; background:#21262d; border-radius:2px; overflow:hidden; }
.progress-fill { height:100%; background:#58a6ff; border-radius:2px; transition:width .3s; }
.stat-fp { font-weight:700; font-size:13px; }
.btn-export {
  background:#21262d; border:1px solid #30363d; color:#58a6ff;
  padding:9px; border-radius:6px; cursor:pointer;
  font-size:11px; font-family:inherit; font-weight:600; text-align:center;
}
.btn-export:disabled { color:#484f58; cursor:default; background:#161b22; }
.dot-grid { display:flex; flex-wrap:wrap; gap:2px; }
.dot {
  width:6px; height:6px; border-radius:1px; cursor:pointer;
  background:#21262d; transition:background .12s;
}
.dot.cur   { background:#58a6ff; }
.dot.cat-0 { background:#c62828; }
.dot.cat-1 { background:#2e7d32; }
.dot.cat-2 { background:#e6a817; }
.dot.cat-3 { background:#7b1fa2; }
.help-ov {
  position:fixed; inset:0; background:rgba(0,0,0,.75);
  display:flex; align-items:center; justify-content:center;
  z-index:100; backdrop-filter:blur(4px);
}
.help-ov.hidden { display:none; }
.help-box {
  background:#161b22; border:1px solid #30363d; border-radius:10px;
  padding:24px 30px; max-width:460px; width:90%;
}
.help-box h2 { color:#58a6ff; font-size:15px; margin-bottom:14px; font-family:inherit; }
.help-row { display:flex; align-items:center; gap:10px; margin-bottom:7px; }
.hkey {
  background:#21262d; padding:3px 9px; border-radius:4px;
  color:#c9d1d9; font-size:10px; min-width:110px; text-align:center;
  border:1px solid #30363d;
}
.hdesc { color:#484f58; font-size:11px; }
.help-note {
  margin-top:14px; padding:10px; background:#0d1117;
  border-radius:5px; border:1px solid #21262d;
  color:#484f58; font-size:10px; line-height:1.65;
}
.help-note strong { color:#c9d1d9; }
.btn-close {
  margin-top:14px; width:100%; background:#21262d;
  border:1px solid #30363d; color:#c9d1d9; padding:7px;
  border-radius:5px; cursor:pointer; font-size:11px; font-family:inherit;
}
.setup-ov {
  position:fixed; inset:0; background:rgba(0,0,0,.85);
  display:flex; align-items:center; justify-content:center; z-index:200;
}
.setup-box {
  background:#161b22; border:1px solid #30363d; border-radius:10px;
  padding:28px 32px; max-width:380px; width:90%;
}
.setup-box h2 { color:#58a6ff; font-size:15px; margin-bottom:18px; font-family:inherit; }
.setup-box label { color:#484f58; font-size:10px; display:block; margin-bottom:5px; }
.setup-box input {
  width:100%; background:#0d1117; border:1px solid #30363d;
  color:#c9d1d9; padding:8px 10px; border-radius:5px;
  font-family:inherit; font-size:12px; margin-bottom:14px;
}
.setup-box input:focus { outline:none; border-color:#58a6ff; }
.btn-start {
  width:100%; background:#2e7d32; border:none; color:#fff;
  padding:10px; border-radius:6px; cursor:pointer;
  font-family:inherit; font-size:12px; font-weight:700;
}
.btn-start:disabled { background:#21262d; color:#484f58; cursor:default; }
</style>
</head>
<body>

<div class="setup-ov" id="setupOv">
  <div class="setup-box">
    <h2>🌲 Crown Reviewer</h2>
    <label>Your reviewer name or ID</label>
    <input type="text" id="reviewerInput"
           placeholder="e.g. Alice or Reviewer_1"
           oninput="if(window.manifest)document.getElementById('startBtn').disabled=!this.value.trim()"
           onkeydown="if(event.key==='Enter'&&this.value.trim()&&window.manifest)startSession()">
    <div style="color:#484f58;font-size:10px;margin-bottom:14px;line-height:1.6">
      Stored with every label. Labels stream to Drive in real time.
      Progress resumes automatically on reload.
    </div>
    <button class="btn-start" id="startBtn" disabled onclick="startSession()">
      Start reviewing →
    </button>
  </div>
</div>

<div class="topbar">
  <div style="display:flex;align-items:center">
    <span class="title">🌲 CROWN REVIEWER</span>
    <span class="subtitle">Edmonds · 2020 · Phase 3 queue</span>
    <span id="syncDot" title="Sync status"
          style="display:inline-block;width:8px;height:8px;border-radius:50%;
                 background:#484f58;margin-left:12px;transition:background .3s">
    </span>
    <span id="syncMsg"
          style="font-size:10px;color:#484f58;margin-left:6px;min-width:140px">
    </span>
  </div>
  <div class="filters">
    <button class="active" data-filter="all"
            onclick="setFilter('all')">All (<span id="cntAll">0</span>)</button>
    <button data-filter="unreviewed"
            onclick="setFilter('unreviewed')">Unreviewed (<span id="cntNR">0</span>)</button>
    <button data-filter="fp"
            onclick="setFilter('fp')">FP (<span id="cntFP">0</span>)</button>
    <button data-filter="tree"
            onclick="setFilter('tree')">Tree (<span id="cntT">0</span>)</button>
    <button onclick="toggleHelp()" style="margin-left:8px">? keys</button>
    <button onclick="exportCSV()">⬇ export</button>
  </div>
</div>

<div class="main">
  <div class="canvas-area">
    <div class="cat-banner" id="catBanner"></div>
    <canvas id="cropCanvas" width="600" height="600"></canvas>
    <div class="actions">
      <button class="btn-cat btn-cat-0" onclick="mark(0)">
        ✗ FALSE POS<span class="key-hint">← arrow</span>
      </button>
      <button class="btn-cat btn-cat-2" onclick="mark(2)">
        ◐ UNDERSIZED<span class="key-hint">↓ arrow</span>
      </button>
      <button class="btn-cat btn-cat-3" onclick="mark(3)">
        ❋ SHRUB<span class="key-hint">↑ arrow</span>
      </button>
      <button class="btn-cat btn-cat-1" onclick="mark(1)">
        ✓ TREE<span class="key-hint">→ arrow</span>
      </button>
    </div>
    <div class="nav-row">
      <button class="btn-undo" id="undoBtn" style="display:none"
              onclick="undo()">undo [Z]</button>
      <span class="nav-pos" id="navPos">— / —</span>
    </div>
    <div class="scroll-hint">
      scroll to browse · arrow keys to label · +/− zoom · ? help
    </div>
    <div class="zoom-ctrls">
      <button onclick="zm(-1)">−</button>
      <span class="zoom-lbl" id="zmLbl">1.00×</span>
      <button onclick="zm(+1)">+</button>
    </div>
  </div>

  <div class="panel">
    <div>
      <div class="sec-title">Stratum</div>
      <div id="stratumBadge" class="stratum-badge s1">—</div>
      <div style="color:#484f58;font-size:10px;line-height:1.5"
           id="stratumDesc">—</div>
    </div>
    <div>
      <div class="sec-title">Crown</div>
      <div class="row"><span class="lbl">ID</span>
           <span class="val" id="iId">—</span></div>
      <div class="row"><span class="lbl">Area</span>
           <span class="val" id="iArea">—</span></div>
      <div class="row"><span class="lbl">Size</span>
           <span class="val" id="iSize">—</span></div>
      <div class="row"><span class="lbl">Bldg dist</span>
           <span class="val" id="iBldg">—</span></div>
      <div class="row"><span class="lbl">Impervious</span>
           <span class="val" id="iImp">—</span></div>
    </div>
    <div>
      <div class="sec-title">Vegetation signal (high-α years)</div>
      <div id="reddishBadge" style="display:none" class="reddish-badge">
        🍁 Reddish ornamental — label by shape not colour
      </div>
      <div class="row">
        <span class="lbl">Veg years</span>
        <span class="val" id="iVeg">—</span>
      </div>
      <div class="row">
        <span class="lbl">vs roof (med)</span>
        <span class="val" id="iRoof">—</span>
      </div>
      <div class="row">
        <span class="lbl">R/G summer max</span>
        <span class="val" id="iRG">—</span>
      </div>
      <div class="sparkline-wrap">
        <div class="spark-bars"   id="sparkBars"></div>
        <div class="spark-labels" id="sparkLabels"></div>
      </div>
      <div style="color:#484f58;font-size:9px;margin-top:4px">
        ndvi percentile rank per year (0=low · 100=high)
      </div>
    </div>
    <div>
      <div class="sec-title">Session</div>
      <div class="row"><span class="lbl">Reviewer</span>
           <span class="val" id="iReviewer">—</span></div>
      <div class="row"><span class="lbl">Reviewed</span>
           <span class="val" id="sReviewed">0 / 0</span></div>
      <div class="progress-bar" style="margin-bottom:6px">
        <div class="progress-fill" id="sProg" style="width:0%"></div>
      </div>
      <div class="row"><span class="lbl">✓ Tree</span>
           <span class="val" style="color:#4CAF50" id="sT">0</span></div>
      <div class="row"><span class="lbl">◐ Undersized</span>
           <span class="val" style="color:#e6a817" id="sU">0</span></div>
      <div class="row"><span class="lbl">❋ Shrub</span>
           <span class="val" style="color:#CE93D8" id="sS">0</span></div>
      <div class="row"><span class="lbl">✗ False Pos</span>
           <span class="val" style="color:#f44336" id="sFP">0</span></div>
      <div class="row"><span class="lbl">FP rate</span>
           <span class="stat-fp" id="sFPR">—%</span></div>
      <div class="row"><span class="lbl">Speed</span>
           <span class="val" id="sRate">—/min</span></div>
    </div>
    <button class="btn-export" disabled onclick="exportCSV()" id="exportBtn">
      ⬇ Export reviews CSV
    </button>
    <div>
      <div class="sec-title">Progress (first 100)</div>
      <div class="dot-grid" id="dotGrid"></div>
    </div>
  </div>
</div>

<div class="help-ov hidden" id="helpOv">
  <div class="help-box">
    <h2>🌲 Crown Reviewer — Controls</h2>
    <div style="margin-bottom:10px;color:#484f58;font-size:10px">Classification</div>
    <div class="help-row">
      <span class="hkey">→  Right Arrow</span>
      <span class="hdesc" style="color:#4CAF50">✓ Tree — correct detection</span>
    </div>
    <div class="help-row">
      <span class="hkey">↓  Down Arrow</span>
      <span class="hdesc" style="color:#e6a817">◐ Undersized — real tree, crown too small</span>
    </div>
    <div class="help-row">
      <span class="hkey">↑  Up Arrow</span>
      <span class="hdesc" style="color:#CE93D8">❋ Shrub — vegetation but not a tree</span>
    </div>
    <div class="help-row">
      <span class="hkey">←  Left Arrow</span>
      <span class="hdesc" style="color:#f44336">✗ False Pos — not vegetation</span>
    </div>
    <div style="margin:10px 0 7px;color:#484f58;font-size:10px">Navigation</div>
    <div class="help-row">
      <span class="hkey">Scroll wheel</span>
      <span class="hdesc">Browse without classifying</span>
    </div>
    <div class="help-row"><span class="hkey">Z</span>
      <span class="hdesc">Undo current label</span></div>
    <div class="help-row"><span class="hkey">+ / −</span>
      <span class="hdesc">Zoom in / out</span></div>
    <div class="help-row"><span class="hkey">H or ?</span>
      <span class="hdesc">Toggle this help</span></div>
    <div class="help-note">
      <strong>Yellow outline</strong> = crown boundary from 2020 DDT
      detection. Label whatever is inside that outline.<br><br>
      <strong>Sync dot</strong> top-left: green = label saved to Drive,
      amber = sending, red = offline (labels buffered, auto-retry).<br><br>
      <strong>Sparkline</strong> = ndvi percentile rank across 11
      high-confidence years. Consistently above 50 = real tree.<br><br>
      <strong>Stratum</strong> explains why this crown needs review.
    </div>
    <button class="btn-close" onclick="toggleHelp()">
      Got it — start reviewing
    </button>
  </div>
</div>

<script>
var manifest=null, crowns=[], reviewerName="";
var currentIdx=0, reviews={}, filter="all";
var zoom=1.0, sessionStart=Date.now(), imgCache={};
var HIGH_ALPHA_YEARS=[];
var localBackup=[];

var CATS={
  0:{name:"False Pos", outline:"#f44336"},
  1:{name:"Tree",      outline:"#FFD600"},
  2:{name:"Undersized",outline:"#e6a817"},
  3:{name:"Shrub",     outline:"#CE93D8"},
};
var SCLS={1:"s1",2:"s2",3:"s3",4:"s4",5:"s5"};
var SDESC={
  1:"Near buildings — primary FP failure mode",
  2:"Inconsistent veg — green in some years only",
  3:"Moderate impervious — partial pavement",
  4:"Spatially isolated — weak veg signal",
  5:"Remaining ambiguous"
};

// ── Sync status ──────────────────────────────────────────────
function setSyncStatus(state, msg){
  var dot=document.getElementById("syncDot");
  var lbl=document.getElementById("syncMsg");
  var cols={ok:"#2e7d32", pending:"#e6a817", err:"#c62828", idle:"#484f58"};
  if(dot) dot.style.background = cols[state]||cols.idle;
  if(lbl){
    lbl.textContent = msg||"";
    lbl.style.color = state==="err" ? "#c62828" : "#484f58";
  }
}

// ── Label streaming ──────────────────────────────────────────
function postLabel(payload){
  setSyncStatus("pending");
  fetch("/label",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(payload)
  })
  .then(function(r){ return r.json(); })
  .then(function(d){
    if(d.status==="ok"){
      setSyncStatus("ok");
      if(localBackup.length>0) setTimeout(flushBackup,500);
    } else {
      throw new Error(d.status);
    }
  })
  .catch(function(e){
    localBackup.push(payload);
    saveBackupLocal();
    setSyncStatus("err", "\u26a0 "+localBackup.length+" buffered");
  });
}

function flushBackup(){
  if(!localBackup.length) return;
  var item=localBackup[0];
  fetch("/label",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(item)
  })
  .then(function(r){ return r.json(); })
  .then(function(d){
    if(d.status==="ok"){
      localBackup.shift();
      saveBackupLocal();
      if(localBackup.length>0){
        setSyncStatus("err","\u26a0 "+localBackup.length+" buffered");
        setTimeout(flushBackup,300);
      } else {
        setSyncStatus("ok");
      }
    }
  })
  .catch(function(){
    setSyncStatus("err","\u26a0 "+localBackup.length+" buffered");
    setTimeout(flushBackup,5000);
  });
}

function saveBackupLocal(){
  var key="crown_backup_"+reviewerName.replace(/\s+/g,"_");
  localStorage.setItem(key,JSON.stringify(localBackup));
}
function loadBackupLocal(){
  var key="crown_backup_"+reviewerName.replace(/\s+/g,"_");
  var s=localStorage.getItem(key);
  if(s){ try{ localBackup=JSON.parse(s); }catch(e){ localBackup=[]; } }
  if(localBackup.length>0){
    setSyncStatus("err","\u26a0 "+localBackup.length+" buffered (retrying)");
    setTimeout(flushBackup,2000);
  }
}

// ── Setup ────────────────────────────────────────────────────
function startSession(){
  reviewerName=document.getElementById("reviewerInput").value.trim();
  if(!reviewerName||!window.manifest)return;
  document.getElementById("setupOv").style.display="none";
  var key="crown_reviews_v4_"+reviewerName.replace(/\s+/g,"_");
  var saved=localStorage.getItem(key);
  if(saved){
    try{
      var parsed=JSON.parse(saved);
      var n=Object.keys(parsed).length;
      if(n>0&&confirm("Found "+n+" saved reviews for "+reviewerName+". Resume?"))
        reviews=parsed;
    }catch(e){}
  }
  loadBackupLocal();
  buildDots();
  setSyncStatus("idle");
  requestAnimationFrame(function(){ updateAll(); preload(0,8); });
}

// ── Manifest loading ─────────────────────────────────────────
async function init(){
  var canvas=document.getElementById("cropCanvas");
  var ctx=canvas.getContext("2d");
  function drawMsg(msg,sub,col){
    ctx.fillStyle="#1a1a2e"; ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.textAlign="center"; ctx.fillStyle=col||"#c9d1d9";
    ctx.font="14px monospace"; ctx.fillText(msg,canvas.width/2,canvas.height/2-8);
    if(sub){ctx.fillStyle="#484f58";ctx.font="11px monospace";
             ctx.fillText(sub,canvas.width/2,canvas.height/2+14);}
  }
  drawMsg("Please wait while environment gets set up","~30 seconds for 61k crowns","#ffffff");
  var btn=document.getElementById("startBtn");
  if(btn){btn.textContent="Please wait...";btn.disabled=true;}
  try{
    var resp=await fetch("manifest.json");
    manifest=await resp.json();
    crowns=manifest.crowns;
    HIGH_ALPHA_YEARS=manifest.high_alpha_years||[];
    sessionStart=Date.now();
    var setupGone=document.getElementById("setupOv").style.display==="none";
    if(setupGone&&reviewerName){
      requestAnimationFrame(function(){updateAll();preload(0,8);});
    } else {
      drawMsg("Manifest ready \u2713","Enter your name above and click Start","#4CAF50");
      if(btn){
        btn.textContent="Start reviewing \u2192";
        var inp=document.getElementById("reviewerInput");
        btn.disabled=!(inp&&inp.value.trim());
      }
    }
  }catch(e){
    document.body.innerHTML=
      '<div style="display:flex;align-items:center;justify-content:center;'+
      'height:100vh;font-family:monospace;color:#484f58;flex-direction:column;gap:12px">'+
      '<div style="font-size:16px;color:#c9d1d9">Could not load manifest.json</div>'+
      '<div>Run phase4_review.py first</div></div>';
  }
}

// ── Image loading ────────────────────────────────────────────
function loadImg(idx){
  return new Promise(function(res){
    if(imgCache[idx]){res(imgCache[idx]);return;}
    var img=new Image();
    img.onload=function(){imgCache[idx]=img;res(img);};
    img.onerror=function(){res(null);};
    img.src=crowns[idx].crop;
  });
}
function preload(start,n){
  var fi=filteredIdx();
  for(var i=0;i<n&&start+i<fi.length;i++)loadImg(fi[start+i]);
}

// ── Filter / navigation ──────────────────────────────────────
function filteredIdx(){
  var out=[];
  for(var i=0;i<crowns.length;i++){
    if(filter==="all")out.push(i);
    else if(filter==="unreviewed"&&reviews[i]===undefined)out.push(i);
    else if(filter==="fp"&&reviews[i]===0)out.push(i);
    else if(filter==="tree"&&reviews[i]===1)out.push(i);
  }
  return out;
}
function setFilter(f){
  filter=f;
  document.querySelectorAll(".topbar button[data-filter]").forEach(function(b){
    b.classList.toggle("active",b.dataset.filter===f);
  });
  var fi=filteredIdx();
  if(fi.length&&!fi.includes(currentIdx))currentIdx=fi[0];
  updateAll();
}
function goNext(){
  var fi=filteredIdx(),p=fi.indexOf(currentIdx);
  currentIdx=p<fi.length-1?fi[p+1]:(fi.length?fi[0]:currentIdx);
  updateAll();preload(currentIdx,5);
}
function goPrev(){
  var fi=filteredIdx(),p=fi.indexOf(currentIdx);
  currentIdx=p>0?fi[p-1]:(fi.length?fi[fi.length-1]:currentIdx);
  updateAll();
}

// ── Marking ──────────────────────────────────────────────────
var CAT_NAMES={0:"false_positive",1:"tree",2:"undersized",3:"shrub"};
function mark(cat){
  var crown=crowns[currentIdx];
  reviews[currentIdx]=cat;
  saveLocal();
  showBanner(cat);
  postLabel({
    crown_id:crown.id, reviewer:reviewerName,
    label_code:cat, label:CAT_NAMES[cat],
    stratum_id:crown.stratum_id, stratum_name:crown.stratum_name,
    n_veg_years:crown.n_veg_years, median_vs_roof:crown.median_vs_roof,
    bldg_dist_m:crown.bldg_dist_m, impervious_frac:crown.impervious_frac,
    area_m2:crown.area_m2, centroid_x:crown.centroid_x,
    centroid_y:crown.centroid_y, ts:new Date().toISOString()
  });
  setTimeout(goNext,140);
}
function undo(){
  var crown=crowns[currentIdx];
  delete reviews[currentIdx];
  saveLocal();
  postLabel({crown_id:crown.id, reviewer:reviewerName,
             label_code:-1, label:"undo", ts:new Date().toISOString()});
  updateAll();
}
function saveLocal(){
  var key="crown_reviews_v4_"+reviewerName.replace(/\s+/g,"_");
  localStorage.setItem(key,JSON.stringify(reviews));
}
function showBanner(cat){
  var b=document.getElementById("catBanner");
  b.textContent=CATS[cat].name.toUpperCase();
  b.className="cat-banner show cat-"+cat;
  setTimeout(function(){b.classList.remove("show");},380);
}
function zm(d){zoom=Math.min(4,Math.max(0.5,zoom+d*0.5));updateAll();}

// ── Sparkline ────────────────────────────────────────────────
function renderSparkline(pctByYear){
  var bars=document.getElementById("sparkBars");
  var labels=document.getElementById("sparkLabels");
  bars.innerHTML="";labels.innerHTML="";
  HIGH_ALPHA_YEARS.forEach(function(yr){
    var pct=(pctByYear&&pctByYear[yr]!==undefined&&pctByYear[yr]!==null)
            ?pctByYear[yr]:null;
    var h=pct!==null?Math.max(2,pct*0.36):2;
    var col=pct===null?"#21262d":pct>70?"#2e7d32":pct>40?"#c79100":"#c62828";
    var bar=document.createElement("div");
    bar.className="spark-bar";bar.style.height=h+"px";bar.style.background=col;
    bar.title=yr+": "+(pct!==null?pct.toFixed(0)+"th pct":"no data");
    bars.appendChild(bar);
    var lbl=document.createElement("div");lbl.className="spark-lbl";
    lbl.textContent=yr.replace("20","'").replace("n","N").replace("s","S");
    labels.appendChild(lbl);
  });
}

// ── Main render ──────────────────────────────────────────────
async function updateAll(){
  if(!crowns.length||!reviewerName)return;
  var crown=crowns[currentIdx];
  var fi=filteredIdx(),pos=fi.indexOf(currentIdx);
  var rv=reviews[currentIdx];
  var canvas=document.getElementById("cropCanvas");
  var ctx=canvas.getContext("2d");
  var cw=canvas.width,ch=canvas.height;
  ctx.fillStyle="#1a1a2e";ctx.fillRect(0,0,cw,ch);
  var img=await loadImg(currentIdx);
  if(img){
    var sz=cw*zoom,ox=(cw-sz)/2,oy=(ch-sz)/2;
    ctx.imageSmoothingEnabled=true;ctx.drawImage(img,ox,oy,sz,sz);
    if(crown.outline&&crown.outline.length>2){
      var sc=sz/manifest.crop_size_px;
      ctx.beginPath();
      for(var i=0;i<crown.outline.length;i++){
        var px=ox+crown.outline[i][0]*sc,py=oy+crown.outline[i][1]*sc;
        if(i===0)ctx.moveTo(px,py);else ctx.lineTo(px,py);
      }
      ctx.closePath();
      ctx.strokeStyle=rv!==undefined?CATS[rv].outline:"#FFD600";
      ctx.lineWidth=rv!==undefined?2.5:2;ctx.stroke();
    }
    ctx.strokeStyle="rgba(255,255,255,.12)";ctx.lineWidth=1;ctx.setLineDash([4,4]);
    ctx.beginPath();
    ctx.moveTo(cw/2-10,ch/2);ctx.lineTo(cw/2+10,ch/2);
    ctx.moveTo(cw/2,ch/2-10);ctx.lineTo(cw/2,ch/2+10);
    ctx.stroke();ctx.setLineDash([]);
  }else{
    ctx.fillStyle="#484f58";ctx.textAlign="center";ctx.font="12px monospace";
    ctx.fillText("Image not found",cw/2,ch/2);
  }
  canvas.className=rv!==undefined?"cat-"+rv:"";
  document.getElementById("navPos").textContent=(pos+1)+" / "+fi.length;
  document.getElementById("undoBtn").style.display=rv!==undefined?"":"none";
  document.getElementById("zmLbl").textContent=zoom.toFixed(2)+"\u00d7";
  var sid=crown.stratum_id||5;
  var badge=document.getElementById("stratumBadge");
  badge.textContent=crown.stratum_label||"Unknown";
  badge.className="stratum-badge "+(SCLS[sid]||"s5");
  document.getElementById("stratumDesc").textContent=SDESC[sid]||"";
  document.getElementById("iId").textContent=crown.id;
  document.getElementById("iArea").textContent=(crown.area_m2||0).toFixed(1)+" m\u00b2";
  document.getElementById("iSize").textContent=crown.size_class||"—";
  document.getElementById("iBldg").textContent=(crown.bldg_dist_m||0).toFixed(1)+" m";
  document.getElementById("iImp").textContent=((crown.impervious_frac||0)*100).toFixed(0)+"%";
  var nveg=crown.n_veg_years!==undefined?crown.n_veg_years:"—";
  var nha=crown.n_high_alpha!==undefined?" / "+crown.n_high_alpha:"";
  document.getElementById("iVeg").textContent=nveg+nha+" yrs";
  var vegEl=document.getElementById("iVeg");
  if(typeof nveg==="number")
    vegEl.style.color=nveg>=5?"#4CAF50":nveg>=3?"#e6a817":"#f44336";
  var vroof=crown.median_vs_roof!==null&&crown.median_vs_roof!==undefined
            ?crown.median_vs_roof.toFixed(3):"—";
  document.getElementById("iRoof").textContent=vroof;

  // R/G summer max — reddish ornamental indicator
  var rg = crown.rg_max_summer;
  var rgEl = document.getElementById("iRG");
  var badge = document.getElementById("reddishBadge");
  if(rg !== null && rg !== undefined){
    rgEl.textContent = rg.toFixed(3);
    if(rg > 1.10){
      rgEl.style.color = "#E8609A";
      rgEl.style.fontWeight = "700";
      badge.style.display = "block";
    } else {
      rgEl.style.color = "#c9d1d9";
      rgEl.style.fontWeight = "600";
      badge.style.display = "none";
    }
  } else {
    rgEl.textContent = "—";
    badge.style.display = "none";
  }

  renderSparkline(crown.ndvi_pct_by_year);
  var total=Object.keys(reviews).length;
  var cats={0:0,1:0,2:0,3:0};
  Object.values(reviews).forEach(function(v){cats[v]=(cats[v]||0)+1;});
  var fpr=total>0?(cats[0]/total*100).toFixed(1):"—";
  var mins=(Date.now()-sessionStart)/60000;
  var rate=total>0?(total/mins).toFixed(0):"—";
  document.getElementById("iReviewer").textContent=reviewerName;
  document.getElementById("sReviewed").textContent=total+" / "+crowns.length;
  document.getElementById("sProg").style.width=(total/Math.max(crowns.length,1)*100)+"%";
  document.getElementById("sT").textContent=cats[1];
  document.getElementById("sU").textContent=cats[2];
  document.getElementById("sS").textContent=cats[3];
  document.getElementById("sFP").textContent=cats[0];
  var fprEl=document.getElementById("sFPR");
  fprEl.textContent=fpr+"%";
  fprEl.style.color=fpr!=="—"&&parseFloat(fpr)>20?"#f44336":"#c9d1d9";
  document.getElementById("sRate").textContent=rate+"/min";
  document.getElementById("exportBtn").disabled=total===0;
  document.getElementById("cntAll").textContent=crowns.length;
  document.getElementById("cntNR").textContent=crowns.length-total;
  document.getElementById("cntFP").textContent=cats[0];
  document.getElementById("cntT").textContent=cats[1];
  updateDots();
}

// ── Progress dots ────────────────────────────────────────────
function buildDots(){
  var grid=document.getElementById("dotGrid");grid.innerHTML="";
  var n=Math.min(100,crowns.length);
  for(var i=0;i<n;i++){
    var d=document.createElement("div");d.className="dot";d.dataset.i=i;
    d.onclick=(function(idx){return function(){currentIdx=idx;updateAll();};})(i);
    grid.appendChild(d);
  }
}
function updateDots(){
  document.querySelectorAll(".dot").forEach(function(d){
    var i=parseInt(d.dataset.i),rv=reviews[i];
    d.className="dot";
    if(i===currentIdx)d.classList.add("cur");
    else if(rv!==undefined)d.classList.add("cat-"+rv);
  });
}
function toggleHelp(){document.getElementById("helpOv").classList.toggle("hidden");}

// ── CSV export (fallback) ────────────────────────────────────
function exportCSV(){
  if(!Object.keys(reviews).length){alert("No reviews yet.");return;}
  var cols=["crown_id","reviewer","stratum_id","stratum_name",
            "label_code","label","n_veg_years","median_vs_roof",
            "bldg_dist_m","impervious_frac","area_m2",
            "centroid_x","centroid_y"];
  var csv=cols.join(",")+"\n";
  Object.entries(reviews).forEach(function(e){
    var idx=parseInt(e[0]),val=e[1],c=crowns[idx];
    csv+=[c.id,reviewerName,c.stratum_id,c.stratum_name,val,
          {0:"false_positive",1:"tree",2:"undersized",3:"shrub"}[val],
          c.n_veg_years,
          c.median_vs_roof!=null?c.median_vs_roof.toFixed(3):"",
          (c.bldg_dist_m||0).toFixed(2),(c.impervious_frac||0).toFixed(3),
          (c.area_m2||0).toFixed(2),(c.centroid_x||0).toFixed(1),
          (c.centroid_y||0).toFixed(1)
         ].join(",")+"\n";
  });
  var blob=new Blob([csv],{type:"text/csv"});
  var a=document.createElement("a");
  a.href=URL.createObjectURL(blob);
  a.download="crown_reviews_"+reviewerName.replace(/\s+/g,"_")+
             "_"+new Date().toISOString().slice(0,10)+".csv";
  a.click();URL.revokeObjectURL(a.href);
}

// ── Keyboard / scroll ────────────────────────────────────────
document.addEventListener("keydown",function(e){
  if(e.target.tagName==="INPUT"||e.target.tagName==="TEXTAREA")return;
  switch(e.key){
    case"ArrowRight":e.preventDefault();mark(1);break;
    case"ArrowDown": e.preventDefault();mark(2);break;
    case"ArrowUp":   e.preventDefault();mark(3);break;
    case"ArrowLeft": e.preventDefault();mark(0);break;
    case"z":case"Z":undo();break;
    case"+":case"=":zm(+1);break;
    case"-":case"_":zm(-1);break;
    case"?":case"h":case"H":toggleHelp();break;
    case"Escape":document.getElementById("helpOv").classList.add("hidden");break;
  }
});
document.addEventListener("wheel",function(e){
  if(e.target.closest&&e.target.closest(".panel"))return;
  e.preventDefault();
  if(e.deltaY>0)goNext();else goPrev();
},{passive:false});

init();
</script>
</body>
</html>
"""



def print_folder_summary(n_crowns: int):
    """
    Print a plain-English summary of everything in the phase4
    folder so the operator knows what each file is and what to
    do next.
    """
    import pandas as pd

    print(f"\n{'=' * 60}")
    print(f"  PHASE 1C READY")
    print(f"{'=' * 60}")

    # ── Review progress ───────────────────────────────────────
    print(f"\n── Review progress ──")
    if CSV_DRIVE.exists():
        df = pd.read_csv(CSV_DRIVE)
        df = df[df["label"] != "undo"]
        n_reviewed = df["crown_id"].nunique()
        pct        = 100 * n_reviewed / n_crowns
        hrs_done   = n_reviewed / 1200
        hrs_left   = (n_crowns - n_reviewed) / 1200
        print(f"  Crowns reviewed : {n_reviewed:>7,} / {n_crowns:,} "
              f"({pct:.1f}%)")
        print(f"  Hours logged    : {hrs_done:.1f} hrs")
        print(f"  Hours remaining : {hrs_left:.1f} hrs  "
              f"(at 1,200 crowns/hr)")
        if len(df) > 0:
            print(f"  Label breakdown :")
            for lbl, cnt in df["label"].value_counts().items():
                print(f"    {lbl:<20} {cnt:>7,}  "
                      f"({100*cnt/len(df):.1f}%)")
    else:
        print(f"  No reviews yet — reviews_live.csv will be created")
        print(f"  on the first label decision.")

    # ── What's in the Drive phase4 folder ──────────────────────
    print(f"\n── Drive folder: {DRIVE_OUT} ──")
    drive_files = [
        (DRIVE_OUT / "manifest.json",
         "Crown metadata for all 61,271 review-queue crowns. "
         "Loaded by the reviewer app on startup."),
        (DRIVE_OUT / "review_app.html",
         "The Crown Reviewer web app. Open via the Chrome URL above."),
        (DRIVE_OUT / "reviews_live.csv",
         "Live label stream. Every arrow key press appends a row. "
         "Source of truth for Phase 1D classifier training."),
    ]
    for path, desc in drive_files:
        if path.exists():
            size = path.stat().st_size
            if size > 1e6:
                size_str = f"{size/1e6:.1f} MB"
            else:
                size_str = f"{size/1e3:.0f} KB"
            print(f"  ✓ {path.name:<25} {size_str:<10} {desc}")
        else:
            print(f"  – {path.name:<25} {'(not yet)':<10} {desc}")

    # ── What's on local disk ──────────────────────────────────
    print(f"\n── Local disk: {LOCAL_OUT} ──")
    local_files = [
        (LOCAL_OUT / "crops",
         f"JPEG crops ({n_crowns:,} files). "
         "Re-extracted from imagery each session (~2 min). "
         "NOT backed up to Drive — always re-extracted."),
        (LOCAL_OUT / "manifest.json",
         "Same as Drive copy. Served directly to browser."),
        (LOCAL_OUT / "review_app.html",
         "Same as Drive copy. Served directly to browser."),
        (LOCAL_OUT / "reviews_live_local.csv",
         "Local backup of every label POST. Written simultaneously "
         "with the Drive CSV. Safety net if Drive write fails."),
        (IMAGERY_LOCAL,
         "2020 CoE imagery copied from Drive for fast tiling. "
         "27 GB. Re-copied if missing (~3-5 min)."),
    ]
    for path, desc in local_files:
        if path.exists():
            if path.is_dir():
                n = sum(1 for _ in path.glob("*"))
                size_str = f"{n:,} files"
            else:
                size = path.stat().st_size
                size_str = (f"{size/1e9:.1f} GB" if size > 1e9
                            else f"{size/1e6:.1f} MB" if size > 1e6
                            else f"{size/1e3:.0f} KB")
            print(f"  ✓ {path.name:<25} {size_str:<14} {desc}")
        else:
            print(f"  – {path.name:<25} {'(not yet)':<14} {desc}")

    # ── What to do next ───────────────────────────────────────
    print(f"\n── What to do next ──")
    print(f"  1. Open the Crown Reviewer in Chrome using the URL above")
    print(f"  2. Enter your reviewer name and start labeling")
    print(f"     → arrow  =  Tree        ← arrow  =  False Positive")
    print(f"     ↓ arrow  =  Undersized  ↑ arrow  =  Shrub")
    print(f"     Scroll wheel to browse  ·  Z to undo  ·  ? for help")
    print(f"  3. Labels stream automatically to Drive in real time")
    print(f"     Sync dot: 🟢 OK  🟡 sending  🔴 offline (buffered)")
    print(f"  4. Run Phase 1D at any time to train the classifier:")
    print(f"     %run .../Scripts/phase1d_classifier.py")
    print(f"  5. Run Phase 1D diagnostics to check progress:")
    print(f"     %run .../Scripts/phase1d_diagnostics.py")
    print(f"\n  Session will stay live as long as this Colab cell")
    print(f"  is running. Do not interrupt the kernel during review.")
    print(f"{'=' * 60}")

# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import pandas as pd
    from pipeline_log import StepLogger
    LOGS_DIR = DRIVE_BASE / "Scripts" / "logs"
    SCRIPT_NAME = "phase1c_review"

    print("=" * 60)
    print("  PHASE 1C — Crown Review")
    print("=" * 60)

    # Setup is the loggable work; the server below runs in a background
    # daemon thread, so it is started after the setup log is written.
    with StepLogger(SCRIPT_NAME, "setup", LOGS_DIR) as log:
        validate()
        LOCAL_OUT.mkdir(parents=True, exist_ok=True)
        DRIVE_OUT.mkdir(parents=True, exist_ok=True)

        # ── Imagery ────────────────────────────────────────────────
        print(f"\n── Checking imagery ──")
        tick("local imagery copy")
        ensure_local_imagery()
        tock("local imagery copy")

        # ── Crops + manifest ───────────────────────────────────────
        tick("load queue")
        gdf      = load_queue()
        tock("load queue")

        tick("extract crops")
        manifest = extract_crops(gdf)
        tock("extract crops")

        tick("compute outlines")
        manifest = compute_outlines(gdf, manifest)
        tock("compute outlines")

        print(f"\n── Writing manifest + app ──")
        tick("write manifest + app")
        write_local(manifest, gdf)
        tock("write manifest + app")

        print(f"\n── Backing up to Drive ──")
        tick("backup to Drive")
        backup_manifest_to_drive()
        tock("backup to Drive")
        log.finish(crowns=len(gdf), manifest_items=len(manifest), errors=0)

    # ── Server (background daemon thread — not logged) ──────────
    server = start_server()

    # ── Folder summary ─────────────────────────────────────
    print_folder_summary(len(manifest))
    timer_summary()