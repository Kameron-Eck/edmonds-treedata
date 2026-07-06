"""
╔══════════════════════════════════════════════════════════════════╗
  PHASE 4 — Temporal-Anchor Crown Reviewer  (web app)
  Edmonds Temporal Active Learning Pipeline

  A browser review tool for assigning each 2020 crown a Present /
  Absent / Unsure decision against the YEAR-2000 ortho, so the
  semantic fine-tune gets honest per-year canopy labels and — for the
  first time at the coarse tier — real labeled NEGATIVES.

  This is the web-app successor to the QGIS workflow in
  ``phase4_label_review_prep.py``. The prep script still does the
  region/crown assembly (expanded footprints, hand-traced ∪ buffered
  model-predicted crowns, per-site crop GeoTIFFs). This script CONSUMES
  that package, serves it crown-by-crown in the browser, and compiles
  the decisions back into the interval-tagged files the fine-tune reads.

  ── PIPELINE POSITION ────────────────────────────────────────────────
    phase4_label_review_prep.py   →  builds phase4/review/2000/
        {site}_2000_crop.tif, {site}_crowns_review.gpkg, {site}_regions.gpkg
    phase4_label_review.py  --step prep     →  per-crown JPEG crops + manifest
    phase4_label_review.py  --step serve    →  browser reviewer (Present/Absent/Unsure)
    phase4_label_review.py  --step compile  →  interval-tagged crowns + region-minus-unsure
        →  copy into polygons/  →  %run phase4_semantic_finetune.py --year 2000

  ── DECISION → LABEL CONTRACT (verified against phase4_semantic_finetune) ─
    The fine-tune burns a crown as canopy iff status=='approved' and
    valid_from ≤ year ≤ valid_to. Inside the region polygon, non-canopy
    pixels are background (0); outside it they are IGNORE (255). With the
    2020 hand-trace/detection treated as the present anchor, a 2000-only
    pass maps to:

      present @2000  → approved, valid_from=2000, valid_to=2020   (canopy)
      absent  @2000  → approved, valid_from=2020, valid_to=2020   (background
                       negative — out-of-interval for 2000, real-tree
                       bookkeeping kept for later years)
      unsure  @2000  → footprint SUBTRACTED from {site}_regions.gpkg
                       (unreviewed too) → pixels become IGNORE; never
                       asserts a label we can't confirm.

    All three use mechanisms the fine-tune already supports — no changes
    to phase4_semantic_finetune.py are required.

  ── SERVER (reused intact from phase1c_review.py) ────────────────────
    Single no-Flask ThreadingTCPServer on one Colab-proxy port:
      GET  /manifest.json   GET /crops/*.jpg   GET /review_app.html
      POST /label           append decision to CSV (Drive + local) w/ undo
      GET  /status          row counts
    Conflict handling: same-label→merged, different-label→flagged.

  USAGE (Colab):
    %run phase4_label_review.py --step prep
    %run phase4_label_review.py --step serve      # open the printed URL in Chrome
    %run phase4_label_review.py --step compile    # after reviewing
    %run phase4_label_review.py --step compile --to-polygons   # write straight to polygons/

  NOTE: --year defaults to 2000 (the only control year wired up so far).
  The schema (valid_from / valid_to) is forward-compatible: a later 2024
  pass extends valid_to and regenerates the region files.
╚══════════════════════════════════════════════════════════════════╝
"""

import argparse
import csv
import datetime
import http.server
import importlib
import json
import os
import random
import shutil
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path


# ── Dependency bootstrap (fresh-runtime safe) ─────────────────────────────────
def _pip(spec):
    print(f"  • installing {spec} …")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", spec], check=True)

for _imp, _spec in [("rasterio", "rasterio"), ("geopandas", "geopandas"),
                    ("numpy", "numpy"), ("PIL", "pillow"),
                    ("shapely", "shapely"), ("fiona", "fiona")]:
    try:
        importlib.import_module(_imp)
    except ImportError:
        _pip(_spec)

import numpy as np
import geopandas as gpd
import pandas as pd
import rasterio
import rasterio.windows
from PIL import Image
from shapely.ops import unary_union


# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

BASE          = Path("/content/drive/MyDrive/treedata")
POLYGONS_DIR  = BASE / "polygons"
CROWN_CRS     = "EPSG:3857"

YEAR          = 2000          # control year under review (overridable via --year)
ANCHOR_YEAR   = 2020          # the year the crowns were traced / detected

CROP_SIZE     = 512           # px, fixed (matches phase1c); browser zoom handles detail
PORT          = 8888

# Drive review package produced by phase4_label_review_prep.py
def review_root(year=YEAR):
    return BASE / "phase4" / "review" / str(year)

# Local NVMe staging (Drive FUSE is unreliable for the per-crown crop write storm)
def local_root(year=YEAR):
    return Path("/content") / f"phase4_review_{year}"

CSV_NAME      = "reviews_live.csv"

FIELDNAMES    = [
    "ts", "crown_id", "site", "reviewer", "label_code", "label",
    "year", "source", "centroid_x", "centroid_y", "conflict",
]

# label_code mapping (kept in sync with the HTML keyboard shortcuts)
LABEL_CODES   = {"present": 1, "absent": 2, "unsure": 3, "undo": -1}


# ── Timing helpers (trimmed from phase1c_review.py) ───────────────────────────
_T0 = {}
def tick(label):  _T0[label] = time.time(); return _T0[label]
def tock(label):
    if label not in _T0:
        return 0.0
    e = time.time() - _T0.pop(label)
    disp = f"{e*1000:.0f} ms" if e < 1 else f"{e:.1f} s" if e < 120 else f"{e/60:.1f} min"
    print(f"  ⏱  {label:<34}  {disp:>10}", flush=True)
    return e


# ══════════════════════════════════════════════════════════════════════════════
#  CSV / CONFLICT HELPERS  (server contract, from phase1c_review.py)
# ══════════════════════════════════════════════════════════════════════════════

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
        return max(0, sum(1 for _ in f) - 1)


def _check_conflict(csv_local: Path, csv_drive: Path,
                    crown_id: str, new_label: str, new_reviewer: str) -> str:
    """'ok' | 'merged' | 'conflict' — read from local CSV for speed."""
    src = csv_local if csv_local.exists() else csv_drive
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


# ══════════════════════════════════════════════════════════════════════════════
#  REVIEW PACKAGE DISCOVERY
# ══════════════════════════════════════════════════════════════════════════════

def discover_package(year, sites_filter=None):
    """Find per-site (crop_tif, crowns_gpkg, regions_gpkg) in the prep output.

    Returns a list of dicts. Crop GeoTIFF naming from the prep script is
    ``{site}_{year}_crop.tif``; we also accept ``{site}_crop.tif``.
    """
    root = review_root(year)
    if not root.exists():
        raise FileNotFoundError(
            f"Review package not found: {root}\n"
            f"  Run phase4_label_review_prep.py first.")
    out = []
    for crown_gpkg in sorted(root.glob("*_crowns_review.gpkg")):
        site = crown_gpkg.name.replace("_crowns_review.gpkg", "")
        if sites_filter and site not in sites_filter:
            continue
        crop_tif = None
        for cand in (root / f"{site}_{year}_crop.tif", root / f"{site}_crop.tif"):
            if cand.exists():
                crop_tif = cand
                break
        if crop_tif is None:
            print(f"  ⚠ {site}: no crop GeoTIFF — skipping")
            continue
        regions = root / f"{site}_regions.gpkg"
        out.append(dict(site=site, crop_tif=crop_tif, crowns=crown_gpkg,
                        regions=regions if regions.exists() else None))
    if not out:
        raise FileNotFoundError(f"No per-site crown packages under {root}")
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  STEP: PREP  —  per-crown crops + outlines + manifest
# ══════════════════════════════════════════════════════════════════════════════

def _crown_centroid_3857(geom):
    c = geom.centroid
    return float(c.x), float(c.y)


def _stage_local(src_path: Path, year):
    """Copy a (small) Drive crop raster to local NVMe once; return local path.

    Per-crown window reads over Drive FUSE are the documented slow path; the
    crop GeoTIFFs are only a few MB each, so staging them is cheap and makes
    the ~14k window reads fast.
    """
    dst = local_root(year) / "orthos" / src_path.name
    if dst.exists() and dst.stat().st_size == src_path.stat().st_size:
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dst)
    return dst


def extract_site_crops(pkg, crops_dir, half=CROP_SIZE // 2):
    """Write one JPEG per crown from the site's native-res crop GeoTIFF.

    The crop window is a fixed CROP_SIZE box centred on the crown centroid.
    Windows that run off the GeoTIFF edge are padded with black (crowns are
    never dropped). Outlines are returned in crop-pixel space.
    """
    site = pkg["site"]
    crowns = gpd.read_file(pkg["crowns"]).reset_index(drop=True)
    if crowns.crs is not None and str(crowns.crs) != CROWN_CRS:
        crowns = crowns.to_crs(CROWN_CRS)

    crop_tif = _stage_local(pkg["crop_tif"], pkg.get("year", YEAR))
    entries = []
    with rasterio.open(crop_tif) as src:
        # Crop GeoTIFF CRS — for 2000 this is EPSG:3857, same as crowns.
        if src.crs is not None and src.crs.to_epsg() != 3857:
            crowns = crowns.to_crs(src.crs)
        tf = src.transform
        img_w, img_h = src.width, src.height

        for i, row in crowns.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            cx, cy = _crown_centroid_3857(geom)
            col = int(round((cx - tf.c) / tf.a))
            r   = int(round((cy - tf.f) / tf.e))
            c0, r0 = col - half, r - half           # window top-left (may be <0)

            # Intersect the desired window with the raster, read, paste into a
            # black CROP_SIZE canvas at the matching offset (pad off-edge area).
            rc0, rr0 = max(c0, 0), max(r0, 0)
            rc1, rr1 = min(c0 + CROP_SIZE, img_w), min(r0 + CROP_SIZE, img_h)
            canvas = np.zeros((CROP_SIZE, CROP_SIZE, 3), dtype=np.uint8)
            if rc1 > rc0 and rr1 > rr0:
                win = rasterio.windows.Window(rc0, rr0, rc1 - rc0, rr1 - rr0)
                chip = src.read([1, 2, 3], window=win)           # 3×h×w
                chip = np.transpose(chip, (1, 2, 0))
                canvas[rr0 - r0:rr0 - r0 + chip.shape[0],
                       rc0 - c0:rc0 - c0 + chip.shape[1], :] = chip

            # Deterministic, guaranteed-unique id from site + positional index.
            # Decoupled from any inherited crown_id (model-predicted crowns carry
            # one, hand-traced rows don't → blanks/collisions). compile rebuilds
            # the identical id from the same file + order, so decisions map back.
            crown_id = f"{site}_{int(i):05d}"
            fname = f"{crown_id}.jpg"
            Image.fromarray(canvas).save(
                crops_dir / fname, format="JPEG", quality=82, optimize=True)

            # Outline → pixel space relative to the window top-left (c0, r0).
            outline = _outline_px(geom, tf, c0, r0)

            entries.append({
                "id":         crown_id,
                "site":       site,
                "source":     str(row.get("source", "")),
                "crop":       f"crops/{fname}",
                "centroid_x": round(cx, 1),
                "centroid_y": round(cy, 1),
                "area_m2":    round(float(row.get("area_m2", 0) or 0), 1),
                "outline":    outline,
            })
    return entries


def _outline_px(geom, tf, c0, r0):
    try:
        if geom.geom_type == "Polygon":
            coords = list(geom.exterior.coords)
        elif geom.geom_type == "MultiPolygon":
            coords = list(max(geom.geoms, key=lambda g: g.area).exterior.coords)
        else:
            return []
        coords = coords[::2]  # halve point count
        return [[round((gx - tf.c) / tf.a - c0, 1),
                 round((gy - tf.f) / tf.e - r0, 1)] for gx, gy in coords]
    except Exception:
        return []


def step_prep(year, sites_filter=None):
    print("=" * 64)
    print(f"  PHASE 4 — Crown Reviewer  ·  PREP  ·  year {year}")
    print("=" * 64)

    pkgs = discover_package(year, sites_filter)
    lroot = local_root(year)
    crops_dir = lroot / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Sites      : {len(pkgs)}")
    print(f"  Local out  : {lroot}")

    tick("extract crops")
    manifest = []
    for pkg in pkgs:
        ents = extract_site_crops(pkg, crops_dir)
        print(f"    {pkg['site']:<22} {len(ents):>5} crowns")
        manifest.extend(ents)
    tock("extract crops")

    # Manifest
    data = {
        "version":     1,
        "created":     datetime.datetime.now().isoformat(),
        "year":        year,
        "anchor_year": ANCHOR_YEAR,
        "crop_size":   CROP_SIZE,
        "total":       len(manifest),
        "sites":       sorted({m["site"] for m in manifest}),
        "crowns":      manifest,
    }
    raw = json.dumps(data, separators=(",", ":"))
    for bad, fix in [(":NaN,", ":null,"), (":NaN}", ":null}"), (":NaN]", ":null]")]:
        raw = raw.replace(bad, fix)
    (lroot / "manifest.json").write_text(raw, encoding="utf-8")
    print(f"  ✓ manifest.json  ({(lroot/'manifest.json').stat().st_size/1e6:.1f} MB, "
          f"{len(manifest)} crowns)")

    # App HTML
    (lroot / "review_app.html").write_text(REVIEW_APP_HTML, encoding="utf-8")
    print(f"  ✓ review_app.html")

    # Backup manifest + app to Drive
    droot = review_root(year)
    droot.mkdir(parents=True, exist_ok=True)
    for fn in ("manifest.json", "review_app.html"):
        try:
            shutil.copy2(lroot / fn, droot / fn)
        except Exception as e:
            print(f"  ⚠ Drive backup of {fn} failed: {e}")
    print(f"\n  Next:  %run phase4_label_review.py --step serve --year {year}")
    return manifest


# ══════════════════════════════════════════════════════════════════════════════
#  STEP: SERVE  —  unified static + /label server (from phase1c_review.py)
# ══════════════════════════════════════════════════════════════════════════════

def make_handler(static_dir: Path, csv_drive: Path, csv_local: Path):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(static_dir), **k)

        def do_POST(self):
            if self.path != "/label":
                self.send_response(404); self.end_headers(); return
            length  = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
            ts      = payload.get("ts", datetime.datetime.utcnow().isoformat())

            if payload.get("label") == "undo":
                row = {k: "" for k in FIELDNAMES}
                row.update(ts=ts, crown_id=payload.get("crown_id", ""),
                           site=payload.get("site", ""),
                           reviewer=payload.get("reviewer", ""),
                           label_code=-1, label="undo", conflict="")
                _write_csv_row(csv_local, row)
                try:
                    _write_csv_row(csv_drive, row); resp = {"status": "ok", "drive": True}
                except Exception as e:
                    resp = {"status": "ok", "drive": False, "err": str(e)}
                self._json(resp); return

            conflict = _check_conflict(csv_local, csv_drive,
                                       payload.get("crown_id", ""),
                                       payload.get("label", ""),
                                       payload.get("reviewer", ""))
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
            row["ts"]         = ts
            row["year"]       = payload.get("year", "")
            row["label_code"] = LABEL_CODES.get(payload.get("label", ""), "")
            row["conflict"]   = conflict if conflict in ("merged", "conflict") else ""
            _write_csv_row(csv_local, row)
            drive_ok = True
            try:
                _write_csv_row(csv_drive, row)
            except Exception:
                drive_ok = False
            self._json({"status": "ok", "conflict": conflict, "drive": drive_ok,
                        "row_count": _csv_row_count(csv_local)})

        def do_GET(self):
            if self.path == "/status":
                self._json({"status": "ok",
                            "rows_local": _csv_row_count(csv_local),
                            "rows_drive": _csv_row_count(csv_drive),
                            "csv_drive": str(csv_drive)})
                return
            super().do_GET()

        def do_OPTIONS(self):
            self.send_response(200); self._cors(); self.end_headers()

        def _json(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._cors(); self.end_headers(); self.wfile.write(body)

        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST,GET,OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def log_message(self, fmt, *args):
            msg = args[0] if args else ""
            if "/label" in msg or "/status" in msg:
                print(f"  [{datetime.datetime.now():%H:%M:%S}] {fmt % args}")

    return Handler


def step_serve(year):
    lroot = local_root(year)
    if not (lroot / "manifest.json").exists():
        print(f"  ✗ No manifest at {lroot}. Run --step prep first.")
        sys.exit(1)

    # Always refresh the app HTML from this script, so UI changes land without
    # a re-prep (crops + manifest are untouched by HTML edits).
    (lroot / "review_app.html").write_text(REVIEW_APP_HTML, encoding="utf-8")
    try:
        shutil.copy2(lroot / "review_app.html",
                     review_root(year) / "review_app.html")
    except Exception:
        pass

    csv_drive = review_root(year) / CSV_NAME
    csv_local = lroot / "reviews_live_local.csv"

    print(f"\n── Starting unified server (port {PORT}) ──")
    os.system(f'fuser -k {PORT}/tcp 2>/dev/null')
    time.sleep(2)
    Handler = make_handler(lroot, csv_drive, csv_local)
    server = socketserver.ThreadingTCPServer(("", PORT), Handler)
    server.allow_reuse_address = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(1)

    try:
        import requests
        r = requests.get(f"http://localhost:{PORT}/manifest.json", timeout=8)
        print(f"  ✓ static — manifest: {r.status_code} ({len(r.content)/1e6:.1f} MB)")
        s = requests.get(f"http://localhost:{PORT}/status", timeout=4).json()
        print(f"  ✓ label endpoint — rows local={s['rows_local']} drive={s['rows_drive']}")
    except Exception as e:
        print(f"  ⚠ self-check: {e}")

    try:
        from google.colab.output import eval_js
        from IPython.display import display, HTML
        proxy = eval_js(f"google.colab.kernel.proxyPort({PORT})")
        url = proxy + "/review_app.html"
        print(f"\n  Open in Chrome:\n  {url}")
        display(HTML(f'<a href="{url}" target="_blank" style="font-size:16px;'
                     f'font-family:monospace;color:#58a6ff">→ Open Crown Reviewer</a>'))
    except Exception:
        print(f"\n  Open: http://localhost:{PORT}/review_app.html")
    print(f"\n  Keys: 1=Present  2=Absent  3=Unsure  ·  Z=undo  ·  scroll=browse")
    print(f"  Decisions stream to {csv_drive}")
    print(f"  Keep this cell running during review.")
    return server


# ══════════════════════════════════════════════════════════════════════════════
#  STEP: COMPILE  —  decisions → interval-tagged crowns + region-minus-unsure
# ══════════════════════════════════════════════════════════════════════════════

def _final_decisions(csv_path: Path):
    """Collapse the review CSV to one label per crown (last non-undo wins;
    an undo erases the immediately preceding decision for that crown)."""
    if not csv_path.exists():
        raise FileNotFoundError(f"No reviews CSV at {csv_path}")
    per_crown = {}    # crown_id -> list of labels in order
    with open(csv_path) as f:
        for r in csv.DictReader(f):
            cid, lab = r["crown_id"], r["label"]
            if not cid:
                continue
            seq = per_crown.setdefault(cid, [])
            if lab == "undo":
                if seq:
                    seq.pop()
            else:
                seq.append(lab)
    return {cid: seq[-1] for cid, seq in per_crown.items() if seq}


def _status_interval(label):
    """Map a 2000 decision to (status, valid_from, valid_to). Unsure/None →
    (uncertain, None, None) and the footprint is later cut from the region."""
    if label == "present":
        return "approved", YEAR, ANCHOR_YEAR
    if label == "absent":
        return "approved", ANCHOR_YEAR, ANCHOR_YEAR
    return "uncertain", None, None


def step_compile(year, sites_filter=None, to_polygons=False, accept_all=False):
    print("=" * 64)
    print(f"  PHASE 4 — Crown Reviewer  ·  COMPILE  ·  year {year}")
    print("=" * 64)

    if accept_all:
        # Test mode: skip the review CSV entirely and treat every crown as
        # present (→ canopy, valid_from=YEAR). No crown is unsure/unreviewed,
        # so no footprint is cut from the regions. Lets you see the downstream
        # result of accepting all annotations without doing a manual review.
        decisions = {}
        print("  ACCEPT-ALL mode: every crown → present (canopy); CSV ignored")
    else:
        csv_drive = review_root(year) / CSV_NAME
        csv_local = local_root(year) / "reviews_live_local.csv"
        src_csv = csv_drive if csv_drive.exists() else csv_local
        decisions = _final_decisions(src_csv)
        print(f"  Reviews CSV : {src_csv}")
        print(f"  Decisions   : {len(decisions)} crowns")
        counts = {k: sum(1 for v in decisions.values() if v == k)
                  for k in ("present", "absent", "unsure")}
        print(f"    present {counts['present']}  absent {counts['absent']}  "
              f"unsure {counts['unsure']}")

    pkgs = discover_package(year, sites_filter)
    out_dir = POLYGONS_DIR if to_polygons else review_root(year) / "compiled"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Output      : {out_dir}\n")

    n_app = n_neg = n_unc = n_pending = 0
    for pkg in pkgs:
        site = pkg["site"]
        crowns = gpd.read_file(pkg["crowns"]).reset_index(drop=True)
        if crowns.crs is not None and str(crowns.crs) != CROWN_CRS:
            crowns = crowns.to_crs(CROWN_CRS)

        statuses, vfs, vts = [], [], []
        cut_geoms = []   # unsure / unreviewed footprints → remove from region
        for i, row in crowns.iterrows():
            cid = f"{site}_{int(i):05d}"        # identical scheme to prep
            lab = "present" if accept_all else decisions.get(cid)  # None → unreviewed
            status, vf, vt = _status_interval(lab)
            statuses.append(status); vfs.append(vf); vts.append(vt)
            geom = row.geometry
            ok_geom = geom is not None and not geom.is_empty
            if lab == "present":
                n_app += 1
            elif lab == "absent":
                n_neg += 1
            elif lab == "unsure":
                n_unc += 1
                if ok_geom:
                    cut_geoms.append(geom)
            else:
                n_pending += 1
                # Unreviewed crown: don't assert anything → cut from region.
                if ok_geom:
                    cut_geoms.append(geom)

        crowns["crown_id"]   = [f"{site}_{i:05d}" for i in range(len(crowns))]
        crowns["status"]     = statuses
        crowns["valid_from"] = vfs
        crowns["valid_to"]   = vts

        crown_out = out_dir / f"{site}_crowns_review.gpkg"
        _gpkg_safe(crowns).to_file(crown_out, driver="GPKG")

        # Region minus unsure/unreviewed footprints.
        region_out = out_dir / f"{site}_regions.gpkg"
        if pkg["regions"] is not None:
            regions = gpd.read_file(pkg["regions"])
            if regions.crs is not None and str(regions.crs) != CROWN_CRS:
                regions = regions.to_crs(CROWN_CRS)
            if cut_geoms:
                cut = unary_union(cut_geoms)
                regions["geometry"] = regions.geometry.apply(
                    lambda g: g.difference(cut))
                regions = regions[~regions.geometry.is_empty].reset_index(drop=True)
            _gpkg_safe(regions).to_file(region_out, driver="GPKG")
        print(f"    {site:<22} approved-present {sum(1 for s,f in zip(statuses,vfs) if s=='approved' and f==year):>4}"
              f"  neg {sum(1 for s,f in zip(statuses,vfs) if s=='approved' and f==ANCHOR_YEAR):>4}"
              f"  cut {len(cut_geoms):>4}")

    print(f"\n  TOTAL  present(canopy) {n_app}  absent(neg) {n_neg}  "
          f"unsure {n_unc}  unreviewed {n_pending}")
    if to_polygons:
        print(f"\n  ✓ Written into polygons/ — ready to fine-tune:")
        print(f"    %run phase4_semantic_finetune.py --year {year}")
    else:
        print(f"\n  Review the files in {out_dir}, then copy into polygons/:")
        print(f"    cp {out_dir}/*_crowns_review.gpkg {POLYGONS_DIR}/")
        print(f"    cp {out_dir}/*_regions.gpkg {POLYGONS_DIR}/")
        print(f"  Or re-run compile with --to-polygons to write there directly.")


def _gpkg_safe(gdf):
    """Make a GeoDataFrame safe to write as GeoPackage.

    Drops columns that collide with reserved names (FID) or are Esri
    shapefile auto-fields (Shape_Length / Shape_Area, often truncated in
    the DBF to SHAPE_Leng / SHAPE_Area / SHAPE_Le_1), removes case-
    insensitive duplicate columns (the cause of the pyogrio
    "Error adding field 'SHAPE_Leng'" failure when sites are concatenated),
    and resets the index. The geometry column is always preserved.
    """
    geom_name = gdf.geometry.name
    drop_lower = {"fid", "shape_leng", "shape_length", "shape_area",
                  "shape_le_1", "shape_ar_1"}
    keep, seen = [], {geom_name.lower()}
    for c in gdf.columns:
        if c == geom_name:
            continue
        lc = str(c).lower()
        if lc in drop_lower or lc in seen:
            continue
        seen.add(lc)
        keep.append(c)
    return gdf[keep + [geom_name]].reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════
#  REVIEW APP HTML  (self-contained; Present / Absent / Unsure)
# ══════════════════════════════════════════════════════════════════════════════

REVIEW_APP_HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Phase 4 — Temporal Crown Reviewer</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d1117;color:#c9d1d9;font-family:'JetBrains Mono',monospace;
  font-size:13px;height:100vh;overflow:hidden;user-select:none;display:flex;flex-direction:column}
.topbar{display:flex;align-items:center;justify-content:space-between;
  padding:8px 14px;background:#161b22;border-bottom:1px solid #30363d;gap:14px;flex-wrap:wrap}
.topbar b{color:#58a6ff}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px}
.g{background:#3fb950}.a{background:#d29922}.r{background:#f85149}
.muted{color:#8b949e}
.stage{flex:1;display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden}
#wrap{position:relative}
canvas{background:#000;image-rendering:pixelated;border:1px solid #30363d;
  box-shadow:0 0 24px #000}
.meta{position:absolute;top:10px;left:10px;background:rgba(13,17,23,.82);
  padding:6px 10px;border-radius:5px;line-height:1.5;font-size:12px}
.hint{position:absolute;bottom:10px;left:50%;transform:translateX(-50%);
  background:rgba(13,17,23,.82);padding:6px 12px;border-radius:5px;color:#8b949e;font-size:12px}
.btns{display:flex;gap:10px;padding:10px 14px;background:#161b22;
  border-top:1px solid #30363d;justify-content:center}
.btn{padding:10px 22px;border:1px solid #30363d;border-radius:6px;cursor:pointer;
  background:#21262d;color:#c9d1d9;font-family:inherit;font-size:14px;font-weight:600}
.btn:hover{border-color:#58a6ff}
.b-present{border-color:#238636}.b-present:hover{background:#238636}
.b-absent{border-color:#9e6a03}.b-absent:hover{background:#9e6a03}
.b-unsure{border-color:#484f58}.b-unsure:hover{background:#484f58}
.k{opacity:.6;font-size:11px;margin-left:6px}
#overlay{position:fixed;inset:0;background:#0d1117;display:flex;align-items:center;
  justify-content:center;z-index:50}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:28px 34px;text-align:center}
.card h2{color:#58a6ff;margin-bottom:6px}
.card input{margin-top:14px;padding:9px 12px;background:#0d1117;border:1px solid #30363d;
  border-radius:6px;color:#c9d1d9;font-family:inherit;width:240px}
.card button{margin-top:14px;display:block;width:100%;padding:10px;background:#238636;
  border:none;border-radius:6px;color:#fff;font-family:inherit;cursor:pointer}
.bar{height:4px;background:#21262d}.bar > i{display:block;height:100%;background:#58a6ff;width:0}
a.dl{color:#58a6ff;text-decoration:none;cursor:pointer}
</style></head><body>

<div id="overlay"><div class="card">
  <h2>Phase 4 — Temporal Crown Reviewer</h2>
  <div class="muted">Is each 2020 crown a real tree in the <b id="yrlab"></b> imagery?</div>
  <input id="rev" placeholder="your name" autocomplete="off">
  <button onclick="start()">Start reviewing</button>
</div></div>

<div class="topbar">
  <div><b>Crown Reviewer</b> <span class="muted">year <b id="yr2"></b></span></div>
  <div><span id="dot" class="dot g"></span><span id="sync">ready</span></div>
  <div class="muted"><span id="pos">0</span> / <span id="tot">0</span>
     · done <span id="done">0</span> · <a class="dl" onclick="csv()">export CSV</a></div>
</div>
<div class="bar"><i id="prog"></i></div>

<div class="stage"><div id="wrap">
  <canvas id="cv" width="512" height="512"></canvas>
  <div class="meta" id="metabox"></div>
  <div class="hint">← Present · → Absent · ↓ Unsure · ↑ Undo · shift+scroll/+− zoom · drag pan · ,/. or scroll browse</div>
</div></div>

<div class="btns">
  <div class="btn b-present" onclick="mark('present')">Present<span class="k">← / 1</span></div>
  <div class="btn b-absent"  onclick="mark('absent')">Absent<span class="k">→ / 2</span></div>
  <div class="btn b-unsure"  onclick="mark('unsure')">Unsure<span class="k">↓ / 3</span></div>
</div>

<script>
let M=null, crowns=[], idx=0, reviewer="", YEAR="", labels={}, history=[];
let zoom=null, panx=0, pany=0, drag=false, lx=0, ly=0;
const cv=document.getElementById('cv'), ctx=cv.getContext('2d');
const buf={};   // crown_id -> pending POST (offline buffer)

fetch('manifest.json').then(r=>r.json()).then(m=>{
  M=m; crowns=m.crowns; YEAR=m.year;
  document.getElementById('tot').textContent=crowns.length;
  document.getElementById('yrlab').textContent=m.year;
  document.getElementById('yr2').textContent=m.year;
});

function start(){
  const v=document.getElementById('rev').value.trim();
  if(!v){return;}
  reviewer=v; document.getElementById('overlay').style.display='none';
  // resume at first unlabeled
  idx=0; while(idx<crowns.length && labels[crowns[idx].id]) idx++;
  draw();
}

function cur(){return crowns[idx];}

function draw(){
  const c=cur(); if(!c){return;}
  document.getElementById('pos').textContent=idx+1;
  document.getElementById('prog').style.width=(100*(idx)/crowns.length)+'%';
  const img=new Image();
  img.onload=()=>{
    // Fixed default zoom for every crown (zoom===null). Every crop is the same
    // ~306m ground window, so a constant zoom keeps a consistent wide-context
    // view. Coarse 2000 imagery is low-res — magnifying small crowns just blows
    // up pixels and hides the surrounding context needed to judge them. Use
    // +/- or shift+scroll to zoom into an individual crown when needed.
    if(zoom===null){
      zoom=2; panx=256-256*zoom; pany=256-256*zoom;   // constant 2x, centre fixed
    }
    ctx.save();ctx.clearRect(0,0,512,512);
    ctx.translate(panx,pany);ctx.scale(zoom,zoom);
    ctx.drawImage(img,0,0,512,512);
    // crown highlight — translucent fill + dark halo + bright core
    if(c.outline&&c.outline.length>2){
      ctx.beginPath();
      c.outline.forEach((p,i)=>{i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]);});
      ctx.closePath();
      ctx.fillStyle='rgba(255,230,0,.16)';ctx.fill();
      ctx.lineWidth=4/zoom;ctx.strokeStyle='rgba(0,0,0,.85)';ctx.stroke();
      ctx.lineWidth=2/zoom;ctx.strokeStyle='#ffe600';ctx.stroke();
    } else {
      // no polygon for this crown → marker at centre so there's always a target
      ctx.beginPath();ctx.arc(256,256,16/zoom,0,7);
      ctx.lineWidth=3/zoom;ctx.strokeStyle='#ffe600';ctx.stroke();
    }
    // centre crosshair (the crown's centroid)
    ctx.strokeStyle='rgba(255,60,60,.9)';ctx.lineWidth=1.5/zoom;
    ctx.beginPath();ctx.moveTo(256-10,256);ctx.lineTo(256+10,256);
    ctx.moveTo(256,256-10);ctx.lineTo(256,256+10);ctx.stroke();
    ctx.restore();
  };
  img.src=c.crop;
  const prev=labels[c.id]?(' · last: '+labels[c.id]):'';
  document.getElementById('metabox').innerHTML=
    `<b>${c.id}</b><br>${c.site}<br><span class="muted">${c.source||''} `+
    `${c.area_m2?('· '+c.area_m2+' m²'):''}${prev}</span>`;
}

function mark(label){
  const c=cur(); if(!c){return;}
  labels[c.id]=label; history.push(c.id);
  document.getElementById('done').textContent=Object.keys(labels).length;
  postLabel({crown_id:c.id, site:c.site, label:label, year:YEAR,
             source:c.source||'', reviewer:reviewer,
             centroid_x:c.centroid_x, centroid_y:c.centroid_y,
             ts:new Date().toISOString()});
  next();
}

function undo(){
  const id=history.pop(); if(!id){return;}
  delete labels[id];
  document.getElementById('done').textContent=Object.keys(labels).length;
  postLabel({crown_id:id, label:'undo', site:'', reviewer:reviewer,
             ts:new Date().toISOString()});
  idx=crowns.findIndex(x=>x.id===id); if(idx<0)idx=0;
  zoom=null;panx=0;pany=0; draw();
}

function next(){ if(idx<crowns.length-1){idx++;zoom=null;panx=0;pany=0;draw();} }
function prev(){ if(idx>0){idx--;zoom=null;panx=0;pany=0;draw();} }

function setSync(cls,txt){
  document.getElementById('dot').className='dot '+cls;
  document.getElementById('sync').textContent=txt;
}

function postLabel(p){
  setSync('a','sending…');
  fetch('/label',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(p)}).then(r=>r.json()).then(d=>{
      setSync(d.drive?'g':'a', d.drive?('saved ('+(d.row_count||'')+')'):'local only');
      if(d.conflict==='conflict') setSync('a','conflict flagged');
      delete buf[p.crown_id+p.ts];
    }).catch(()=>{ buf[p.crown_id+p.ts]=p; setSync('r','offline · buffered '+Object.keys(buf).length); });
}

setInterval(()=>{  // retry buffered
  const keys=Object.keys(buf); if(!keys.length)return;
  keys.forEach(k=>postLabel(buf[k]));
},5000);

function csv(){
  let rows=['crown_id,site,label'];
  for(const c of crowns){ if(labels[c.id]) rows.push(`${c.id},${c.site},${labels[c.id]}`); }
  const blob=new Blob([rows.join('\n')],{type:'text/csv'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);
  a.download='reviews_export.csv';a.click();
}

// input
document.addEventListener('keydown',e=>{
  if(document.getElementById('overlay').style.display==='none'){
    // arrow keys → decisions;  digits 1/2/3 still work
    if(e.key==='ArrowLeft'||e.key==='1'){e.preventDefault();mark('present');}
    else if(e.key==='ArrowRight'||e.key==='2'){e.preventDefault();mark('absent');}
    else if(e.key==='ArrowDown'||e.key==='3'){e.preventDefault();mark('unsure');}
    else if(e.key==='ArrowUp'||e.key==='z'||e.key==='Z'){e.preventDefault();undo();}
    else if(e.key==='+'||e.key==='=')changeZoom(1.25);
    else if(e.key==='-')changeZoom(0.8);
    else if(e.key===',')prev();
    else if(e.key==='.')next();
  } else if(e.key==='Enter') start();
});
function changeZoom(f){
  if(zoom===null)zoom=1;
  zoom=Math.max(1,Math.min(8,zoom*f));
  panx=256-256*zoom; pany=256-256*zoom;   // zoom about the canvas centre
  draw();
}
cv.addEventListener('wheel',e=>{e.preventDefault();
  if(e.shiftKey){changeZoom(e.deltaY<0?1.15:0.87);} else {e.deltaY<0?prev():next();}
},{passive:false});
cv.addEventListener('mousedown',e=>{drag=true;lx=e.offsetX;ly=e.offsetY;});
window.addEventListener('mouseup',()=>drag=false);
cv.addEventListener('mousemove',e=>{ if(drag){panx+=e.offsetX-lx;pany+=e.offsetY-ly;lx=e.offsetX;ly=e.offsetY;draw();} });
</script></body></html>
"""


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    from pipeline_log import StepLogger
    LOGS_DIR = BASE / "Scripts" / "logs"
    SCRIPT_NAME = "phase4_label_review"

    filtered = [a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]
    p = argparse.ArgumentParser(description="Phase 4 temporal-anchor crown reviewer")
    p.add_argument("--step", choices=["prep", "serve", "compile"], required=True)
    p.add_argument("--year", type=int, default=YEAR)
    p.add_argument("--sites", default=None)
    p.add_argument("--to-polygons", action="store_true")
    p.add_argument("--accept-all", action="store_true",
                   help="compile: skip the CSV and treat every crown as present "
                        "(canopy) — test the downstream effect of accepting all.")
    args = p.parse_args(filtered)

    sites_filter = set(args.sites.split(",")) if args.sites else None

    if args.step == "prep":
        with StepLogger(SCRIPT_NAME, "prep", LOGS_DIR) as log:
            manifest = step_prep(args.year, sites_filter)
            sites_done = sorted({m["site"] for m in manifest})
            log.finish(
                year=args.year,
                crowns=len(manifest),
                sites=sites_done,
                manifest_mb=round(
                    (local_root(args.year) / "manifest.json").stat().st_size / 1e6, 1
                ),
                errors=0,
            )

    elif args.step == "serve":
        # serve blocks; log setup only, then log shutdown
        logger = StepLogger(SCRIPT_NAME, "serve", LOGS_DIR, capture_stdout=False)
        logger.start()
        server = step_serve(args.year)
        rows_start = _csv_row_count(review_root(args.year) / CSV_NAME)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("\n  server stopped.")
        rows_end = _csv_row_count(review_root(args.year) / CSV_NAME)
        logger.finish(
            year=args.year,
            labels_this_session=rows_end - rows_start,
            total_labels=rows_end,
        )

    elif args.step == "compile":
        with StepLogger(SCRIPT_NAME, "compile", LOGS_DIR) as log:
            result = step_compile(args.year, sites_filter,
                                  to_polygons=args.to_polygons,
                                  accept_all=args.accept_all)
            log.finish(
                year=args.year,
                to_polygons=args.to_polygons,
                accept_all=args.accept_all,
                errors=0,
                # step_compile should return a summary dict; adjust as needed
            )
if __name__ == "__main__":
    main()