import contextlib
import hashlib
import importlib
import json
import os
import random
import secrets
import socket
import subprocess
import sys
import shutil
import threading
import time
import warnings
from pathlib import Path

from phase4seg.config import *
from phase4seg import config


def _pip_install(spec):
    print(f"  • installing {spec} …")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", spec], check=True)


def _ensure_deps(deps):
    for import_name, pip_spec in deps:
        try:
            importlib.import_module(import_name)
        except ImportError:
            _pip_install(pip_spec)
            importlib.invalidate_caches()


_ensure_deps([
    ("geopandas", "geopandas"),
    ("rasterio",  "rasterio"),
    ("shapely",   "shapely"),
    ("fiona",     "fiona"),
    ("sklearn",   "scikit-learn"),
    ("scipy",     "scipy"),
    ("tqdm",      "tqdm"),
])

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rasterio.features
import rasterio.transform
import rasterio.warp
import rasterio.windows
from rasterio.coords import BoundingBox
from rasterio.enums import Resampling
from shapely.geometry import box, mapping, shape
from sklearn.model_selection import train_test_split
from tqdm import tqdm

warnings.filterwarnings("ignore")


# ── Timing helpers (same as phase1/phase3) ────────────────────────────────────

_timers = {}


def tick(label):
    _timers[label] = time.time()


def tock(label):
    if label in _timers:
        elapsed = time.time() - _timers.pop(label)
        print(f"  ⏱ {label}: {elapsed:.1f}s")
        return elapsed
    return 0.0


def timer_summary():
    if _timers:
        print(f"\n  Unclosed timers: {list(_timers.keys())}")


def _tag_sfx():
    """Filename suffix for --run-tag ('' when unset → legacy names)."""
    return f"_{config.RUN_TAG}" if config.RUN_TAG else ""

def remaining_entries():
    """The 17 acquisitions Phase 4 fine-tunes (everything except the 2020 anchor)."""
    return [e for e in YEAR_CATALOG if e["label"] != ANCHOR_LABEL]


def entry_for(label):
    for e in YEAR_CATALOG:
        if e["label"] == str(label):
            return e
    raise KeyError(f"Unknown year label: {label!r}")


def resolve_native_path(entry):
    """Locate the year's native ortho via the ONE resolution order.

    The root list lives in config.imagery_roots() (IMAGERY_PLAN.md A5) so the
    engine and the local QC scripts cannot disagree about which copy of a year
    they are reading. On Colab the order is unchanged: native/ then the
    "Pipeline Imagery" root.
    """
    roots = config.imagery_roots() or [NATIVE_DIR, IMAGERY_DIR]
    for d in roots:
        p = d / entry["native_file"]
        if p.exists():
            return p
    # Return the canonical first-root path even if missing, for clear error text.
    return roots[0] / entry["native_file"]
# ── Local SSD staging (phase1 pattern) ────────────────────────────────────────

# ── Cross-runtime staging lock (overhaul P11.4) ───────────────────────────────
# A Google Drive download throttle was measured from ONE client on 2026-08-21 (the
# local Windows Drive client during the P1 backup: ~390 kB/s vs ~5 MB/s after ~300
# GB pulled; it recovered on a rolling window). Whether that quota is per-account or
# per-client is NOT established. On 2026-08-22 two Colab runtimes began staging
# orthos ~10 min apart (11.7 GB at 01:03Z, 26.9 GB at 01:12Z); each runtime's last
# Drive write came seconds after its own staging began and no staging tock ever
# arrived. The cause was NOT established (throttle suspected; a wedged Drive mount or
# VM death fit the evidence equally). Precaution: parallel runtimes serialize their
# BULK Drive→NVMe copies (≥ STAGE_LOCK_MIN_BYTES) through claim files on Drive —
# GPU work still overlaps, only the big copies queue. It removes one candidate
# cause, not all of them.
#
# Drive is not POSIX: O_EXCL is only atomic against each VM's own drivefs cache and
# Drive allows duplicate names, so the lock does NOT rely on exclusive create. Each
# holder writes its OWN uniquely named claim file, waits STAGE_LOCK_SETTLE_SEC for
# peers' claims to propagate, lists the directory, and holds only while its claim is
# the OLDEST live one (ties broken by name). Live = re-stamped within
# STAGE_LOCK_STALE_MIN (holders and waiters re-stamp every beat/poll); a same-host
# claim whose pid is dead is stale at once. Waiting is bounded by
# STAGE_LOCK_MAX_WAIT_MIN, after which the copy proceeds UNLOCKED with a warning, so
# the queue's per-step ceiling (phase4_train_queue.STEP_TIMEOUT_MIN) must exceed
# MAX_WAIT + the step's own work. Non-Colab runs (local smoke/QC) never lock.
# phase4/locks/ must exist BEFORE two runtimes start (the queue creates it at launch
# and the cockpit's bootstrap cell mkdir's it) so two VMs never race to create it —
# Drive would happily keep two folders of the same name.
STAGE_LOCK_DIR          = BASE / "phase4" / "locks"
STAGE_LOCK_MIN_BYTES    = 1 << 30  # only copies ≥ 1 GiB contend (orthos, tile sets)
STAGE_LOCK_SETTLE_SEC   = 10       # let peers' claim files propagate before listing
STAGE_LOCK_STALE_MIN    = 15       # no re-stamp this long = claimant presumed dead
STAGE_LOCK_POLL_SEC     = 30
STAGE_LOCK_BEAT_SEC     = 60
STAGE_LOCK_MAX_WAIT_MIN = 60       # then proceed unlocked (+ warn); see the ceilings


def _lock_enabled():
    """Only a Colab VM with Drive mounted takes the lock. config.BASE is the
    hard-coded Colab path on every platform, so test the MOUNT, not BASE —
    locally (Windows smoke/QC) this is always False and nothing is created."""
    return os.name == "posix" and Path("/content/drive/MyDrive/treedata").is_dir()


def _pid_alive(pid):
    """POSIX only: os.kill(pid, 0) probes. On Windows os.kill TERMINATES, so the
    answer there is always 'alive' (the lock never runs on Windows anyway)."""
    if os.name != "posix":
        return True
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


class _StagingLock:
    """`with _StagingLock("2024_coe_rgb.tif"):` around any bulk copy from Drive.
    `.held` is False when the copy proceeds unlocked (local run, or max-wait hit)."""

    def __init__(self, what):
        self.what = what
        self.host = socket.gethostname()
        self.pid = os.getpid()
        self.token = secrets.token_hex(3)              # threads/pid reuse never collide
        self.t_acq = None
        self.path = STAGE_LOCK_DIR / f"staging.{self.host}.{self.pid}.{self.token}.lock"
        self.held = False
        self._stop = threading.Event()
        self._beat = None

    # -- claim files ---------------------------------------------------------
    def _write_claim(self):
        payload = json.dumps({"host": self.host, "pid": self.pid, "what": self.what,
                              "t_acq": self.t_acq, "ts": time.time()})
        tmp = self.path.with_suffix(".tmp")      # atomic replace: a peer never reads a
        tmp.write_text(payload)                  # half-written claim (found by the unit test)
        os.replace(tmp, self.path)

    def _remove_claim(self):
        for _ in range(3):
            try:
                self.path.unlink()
                return
            except FileNotFoundError:
                return
            except OSError:
                time.sleep(1)

    def _claims(self):
        """Sorted [(t_acq, name, path, payload)] of live claims; stale ones of
        OTHER claimants are removed on the way (never our own)."""
        live = []
        for p in sorted(STAGE_LOCK_DIR.glob("staging.*.lock")):
            d = {}
            try:
                d = json.loads(p.read_text())
                ts = float(d.get("ts"))
                t_acq = float(d.get("t_acq") or ts)
            except Exception:                                   # noqa: BLE001
                try:
                    ts = p.stat().st_mtime                      # unreadable: staleness by mtime,
                    t_acq = 0.0                                 # and assume it PREDATES us (wait,
                except OSError:                                 # never jump the queue)
                    continue                                    # vanished between list and read
            if p == self.path:
                live.append((t_acq, p.name, p, d))
                continue
            age_min = (time.time() - ts) / 60.0
            dead_local = d.get("host") == self.host and not _pid_alive(d.get("pid"))
            if age_min > STAGE_LOCK_STALE_MIN or dead_local:
                why = "dead pid" if dead_local else f"{age_min:.0f} min silent"
                print(f"  staging lock: breaking stale claim {p.name} ({why})", flush=True)
                try:
                    p.unlink()
                except OSError:
                    pass
                continue
            live.append((t_acq, p.name, p, d))
        return sorted(live, key=lambda c: (c[0], c[1]))

    def _heartbeat(self):
        warned = False
        while not self._stop.wait(STAGE_LOCK_BEAT_SEC):
            try:
                self._write_claim()
                if not warned:
                    claims = self._claims()
                    if claims and claims[0][2] != self.path:
                        print("  WARNING: an older live staging claim appeared while we hold the "
                              "lock — two bulk copies may be running concurrently "
                              f"({claims[0][3]})", flush=True)
                        warned = True
            except OSError:
                pass

    # -- context manager -----------------------------------------------------
    def __enter__(self):
        if not _lock_enabled():
            return self
        t0 = time.time()
        self.t_acq = t0
        announced = first = True
        while True:
            if (time.time() - t0) / 60 > STAGE_LOCK_MAX_WAIT_MIN:
                print(f"  WARNING: waited {STAGE_LOCK_MAX_WAIT_MIN} min for the staging lock; "
                      f"proceeding WITHOUT it ({self.what})", flush=True)
                self._remove_claim()
                return self
            try:
                STAGE_LOCK_DIR.mkdir(parents=True, exist_ok=True)
                if first:
                    dups = [p.name for p in STAGE_LOCK_DIR.parent.iterdir()
                            if p.name.startswith("locks")]
                    if len(dups) > 1:
                        print(f"  WARNING: duplicate lock folders on Drive {dups} — the "
                              "staging lock may NOT be cross-runtime", flush=True)
                self._write_claim()                  # (re)stamp ts; t_acq stays fixed
                if first:
                    time.sleep(STAGE_LOCK_SETTLE_SEC)
                    first = False
                claims = self._claims()
                if claims and claims[0][2] == self.path:
                    self.held = True
                    self._beat = threading.Thread(target=self._heartbeat, daemon=True)
                    self._beat.start()
                    if not announced:
                        print(f"  staging lock acquired after {(time.time() - t0) / 60:.1f} min",
                              flush=True)
                    return self
                if announced and claims:
                    h = claims[0][3]
                    print(f"  staging lock held by {h.get('host', '?')}:{h.get('pid', '?')} "
                          f"for {h.get('what', '?')}; waiting for {self.what} "
                          f"(poll {STAGE_LOCK_POLL_SEC}s) …", flush=True)
                    announced = False
            except OSError as e:                     # drivefs EIO/ETIMEDOUT etc.
                print(f"  staging lock: Drive error ({e}); retrying", flush=True)
            time.sleep(STAGE_LOCK_POLL_SEC + random.uniform(0, STAGE_LOCK_POLL_SEC / 2))

    def __exit__(self, *exc):
        if self.held:
            self._stop.set()
            if self._beat is not None:
                self._beat.join(timeout=10)          # never unlink under a live re-stamp
            self.held = False
        self._remove_claim()
        return False


def _staging_lock_for(src_path):
    """The lock for a copy of `src_path`, or a no-op for small files (CHM, masks):
    only bulk copies contend for Drive bandwidth."""
    try:
        size = Path(src_path).stat().st_size
    except OSError:
        size = 0
    if size >= STAGE_LOCK_MIN_BYTES:
        return _StagingLock(Path(src_path).name)
    return contextlib.nullcontext()


def _stage_imagery_local(src_path):
    """Copy a Drive ortho to local NVMe; return the local path (or src on failure)."""
    src_path = Path(src_path)
    if not str(src_path).startswith("/content/drive"):
        return src_path  # already local
    LOCAL_SCRATCH.mkdir(parents=True, exist_ok=True)
    dst = LOCAL_SCRATCH / src_path.name
    try:
        if dst.exists() and dst.stat().st_size == src_path.stat().st_size:
            return dst
        with _staging_lock_for(src_path):          # P11.4: one bulk Drive copy at a time
            tick(f"stage {src_path.name}")
            shutil.copy2(src_path, dst)
            tock(f"stage {src_path.name}")
        return dst
    except Exception as e:
        print(f"  WARNING: local staging failed ({e}); reading from Drive")
        return src_path


def _unstage_imagery_local(local_path):
    local_path = Path(local_path)
    try:
        if str(local_path).startswith(str(LOCAL_SCRATCH)) and local_path.exists():
            local_path.unlink()
    except Exception:
        pass


def _sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def _local_artifact_path(final_path):
    """Where to WRITE a heavy artifact destined for `final_path`.

    On Colab (final under /content/drive) → a scratch path on local NVMe, so the
    multi-GB write never streams over FUSE; the caller then _copy_to_drive()s it.
    Anywhere else → final_path unchanged (already local disk).
    """
    final_path = Path(final_path)
    if str(final_path).startswith("/content/drive"):
        LOCAL_SCRATCH.mkdir(parents=True, exist_ok=True)
        return LOCAL_SCRATCH / final_path.name
    return final_path


def _copy_to_drive(local_path, drive_path, checksum=True, retries=1):
    """VERIFIED local-then-copy write.

    The unverified direct-to-Drive write has produced three broken artifacts
    (2022 xsensor 0-byte, 2017 xsensor 96.5%-nodata, 2024 truncated stub) that
    each cost a GPU run before anyone noticed. This copy refuses to be silent:
    size must match, and (checksum=True) the Drive copy must hash identical to
    the local one. On mismatch the bad Drive copy is removed and the copy is
    retried; if it still mismatches, RAISE — a loud failure at write time is the
    entire point.
    """
    local_path, drive_path = Path(local_path), Path(drive_path)
    drive_path.parent.mkdir(parents=True, exist_ok=True)
    if local_path == drive_path:
        return drive_path
    want_size = local_path.stat().st_size
    want_sha = _sha256(local_path) if checksum else None
    for attempt in range(retries + 1):
        tick(f"copy {drive_path.name}")
        shutil.copy2(local_path, drive_path)
        tock(f"copy {drive_path.name}")
        got_size = drive_path.stat().st_size
        if got_size != want_size:
            problem = f"size {got_size} != {want_size}"
        elif checksum and _sha256(drive_path) != want_sha:
            problem = "sha256 mismatch"
        else:
            print(f"  ✓ verified write: {drive_path.name} "
                  f"({want_size/1e6:.0f} MB{', sha256 ok' if checksum else ''})")
            return drive_path
        print(f"  ! verified write FAILED ({problem}) for {drive_path.name} "
              f"[attempt {attempt + 1}/{retries + 1}]")
        try:
            drive_path.unlink()
        except OSError:
            pass
    raise RuntimeError(f"verified write failed after {retries + 1} attempts: "
                       f"{drive_path} ({problem})")

# ── LIDAR structure 4th-channel reader ────────────────────────────────────────
# The structure master (EPSG:3857, 1 m; source per HS_SOURCE) is reprojected on
# demand onto each tile's native grid (orthos are in 3857/2285/26910 at 7.5-60
# cm). Opened once per source, staged to local NVMe like the orthos.
# read_hillshade_chip is the single source of the 4th band for tiling AND
# inference, so RGB and structure are always co-registered.

_HILLSHADE_DS = {}   # source name → open dataset (cache)

def _hillshade_ds():
    """Open + cache the staged HS_SOURCE master, or None if absent/disabled."""
    if config.HS_SOURCE in _HILLSHADE_DS:
        return _HILLSHADE_DS[config.HS_SOURCE]
    path = HS_PATHS[config.HS_SOURCE]
    if not path.exists():
        print(f"  WARNING: --hs-source {config.HS_SOURCE} raster not found at {path} — "
              f"falling back to RGB-only despite USE_HILLSHADE.")
        return None
    local = _stage_imagery_local(path)
    _HILLSHADE_DS[config.HS_SOURCE] = rasterio.open(local)
    return _HILLSHADE_DS[config.HS_SOURCE]


def read_hillshade_chip(dst_crs, dst_transform, h, w):
    """Reproject the hillshade onto an arbitrary target grid → (1,h,w) uint8.
    Out-of-coverage (water / no first-return) reprojects to 0, matching the RGB
    nodata fill. Returns zeros if the hillshade is unavailable."""
    from rasterio.warp import reproject, Resampling
    ds = _hillshade_ds()
    if ds is None:
        return np.zeros((1, h, w), dtype=np.uint8)
    out = np.zeros((h, w), dtype=np.uint8)
    reproject(source=rasterio.band(ds, 1), destination=out,
              src_transform=ds.transform, src_crs=ds.crs,
              dst_transform=dst_transform, dst_crs=dst_crs,
              resampling=Resampling.bilinear, src_nodata=0, dst_nodata=0)
    return out[np.newaxis]

# ══════════════════════════════════════════════════════════════════════════════
#  Training-site discovery (footprints only — pixels come from per-year orthos)
# ══════════════════════════════════════════════════════════════════════════════

def discover_site_footprints(site_buffer=0.0):
    """Return [(site_label, bounds_3857, crowns_gdf_or_None)] for each training site.

    Footprint geometry is taken from the 2020 7.5 cm site photo's georeferenced
    bounds (cheap metadata read, no pixels). Sites without a crown shapefile are
    dedicated true negatives (kept as all-zero masks).

    site_buffer pads each footprint by N map units (EPSG:3857) on every side,
    enlarging the crop so more tiles fit. Pixels of the enlarged crop that fall
    outside the reviewed regions are IGNORE, so usable extra tiles only appear
    where the regions already reach (≈ the prep --buffer).
    """
    print("\n── Discovering training-site footprints ──")
    if site_buffer:
        print(f"  Site buffer: +{site_buffer:.0f} map units per side")
    photo_files = sorted(PHOTOS_DIR.glob("*_rgb.tif"))
    if not photo_files:
        raise FileNotFoundError(f"No *_rgb.tif training photos in {PHOTOS_DIR}")

    sites = []
    for photo in photo_files:
        label = photo.stem.replace("_rgb", "")
        with rasterio.open(photo) as src:
            b = src.bounds
            pcrs = src.crs
        # Photos are 2020 CoE 7.5 cm in EPSG:3857; reproject bounds if not.
        if pcrs is not None and pcrs.to_epsg() != 3857:
            b = BoundingBox(*rasterio.warp.transform_bounds(pcrs, CROWN_CRS, *b))

        crowns, is_review = load_site_crowns(label)
        sites.append((label, BoundingBox(b.left - site_buffer, b.bottom - site_buffer,
                                         b.right + site_buffer, b.top + site_buffer),
                      crowns))
        if crowns is None:
            tag = "— (true negative)"
        elif is_review:
            n_app = int((crowns["status"].astype(str).str.lower() == "approved").sum()) \
                if "status" in crowns.columns else len(crowns)
            tag = f"{len(crowns)} crowns [REVIEW: {n_app} approved, interval-tagged]"
        else:
            tag = f"{len(crowns)} crowns"
        print(f"  {label:<25} {tag}")

    n_pos = sum(c is not None for _, _, c in sites)
    print(f"\n  Sites: {len(sites)}  ({n_pos} positive / "
          f"{len(sites) - n_pos} true negative)")
    return sites


def load_site_crowns(site_label):
    """Return (crowns_gdf_or_None, is_review).

    Prefers a human-reviewed, interval-tagged crown file
    (``{site}_crowns_review.gpkg`` or ``.shp``) over the legacy
    ``{site}.shp``. Review files carry ``status`` / ``valid_from`` /
    ``valid_to`` columns; legacy files don't. Sites with no crown file are
    dedicated true negatives → (None, False).
    """
    review = (POLYGONS_DIR / f"{site_label}_crowns_review.gpkg")
    review_shp = (POLYGONS_DIR / f"{site_label}_crowns_review.shp")
    legacy = (POLYGONS_DIR / f"{site_label}.shp")
    if review.exists():
        return preprocess_crowns(review), True
    if review_shp.exists():
        return preprocess_crowns(review_shp), True
    if legacy.exists():
        return preprocess_crowns(legacy), False
    return None, False


def _load_review_regions(site_label, target_crs=CROWN_CRS):
    """Reviewed-extent polygons for a site, if present.

    Inside these polygons, non-crown pixels are confirmed *background* (0);
    outside them, pixels are IGNORE (255). Returns None when no regions file
    exists, in which case the whole site crop is treated as reviewed (legacy
    wall-to-wall behaviour).
    """
    for ext in ("_regions.gpkg", "_regions.shp"):
        p = POLYGONS_DIR / f"{site_label}{ext}"
        if p.exists():
            g = gpd.read_file(p)
            if g.crs is not None and g.crs.to_epsg() != 3857:
                g = g.to_crs(target_crs)
            g = g[~g.geometry.is_empty & g.geometry.is_valid].reset_index(drop=True)
            return g if len(g) else None
    return None


def _year_int(label):
    """Calendar year from a year label ('2000' → 2000, '2019n' → 2019)."""
    import re
    m = re.match(r"(\d{4})", str(label))
    return int(m.group(1)) if m else None


def preprocess_crowns(shp_path, target_crs=CROWN_CRS):
    """Load + clean crown polygons in EPSG:3857 (same cleaning as Phase 3).

    Preserves any extra attribute columns (e.g. the review fields
    ``status`` / ``valid_from`` / ``valid_to``) so interval filtering can
    happen at rasterise time.
    """
    gdf = gpd.read_file(shp_path)
    if gdf.crs is None:
        raise ValueError(f"{shp_path} has no CRS — set a .prj before running.")
    if gdf.crs.to_epsg() != 3857:
        gdf = gdf.to_crs(target_crs)

    if "MultiPolygon" in gdf.geometry.geom_type.unique():
        gdf = gdf.explode(index_parts=False).reset_index(drop=True)
    invalid = ~gdf.geometry.is_valid
    if invalid.any():
        gdf["geometry"] = gdf.geometry.buffer(0)
        gdf = gdf[gdf.geometry.is_valid].reset_index(drop=True)
    if "MultiPolygon" in gdf.geometry.geom_type.unique():
        gdf = gdf.explode(index_parts=False).reset_index(drop=True)
    gdf = gdf[~gdf.geometry.is_empty].reset_index(drop=True)
    gdf["area_m2"] = gdf.geometry.area
    gdf = gdf[gdf["area_m2"] >= 0.5].reset_index(drop=True)
    return gdf


def _load_coverage_overrides():
    """Optional: phase2 site×year coverage matrix. Returns {(label,site): bool}."""
    if not COVERAGE_CSV.exists():
        return {}
    try:
        df = pd.read_csv(COVERAGE_CSV)
        # Tolerate a few likely column namings.
        ycol = next((c for c in df.columns if c.lower() in
                     ("year", "label", "year_label")), None)
        scol = next((c for c in df.columns if c.lower() in
                     ("site", "site_label")), None)
        ccol = next((c for c in df.columns if "cover" in c.lower()
                     or "include" in c.lower()), None)
        if not (ycol and scol and ccol):
            return {}
        out = {}
        for _, r in df.iterrows():
            val = str(r[ccol]).strip().lower()
            covered = val in ("1", "true", "yes", "include", "covered", "y", "t")
            out[(str(r[ycol]), str(r[scol]))] = covered
        return out
    except Exception as e:
        print(f"  (coverage CSV present but unreadable: {e})")
        return {}
def read_rgb_window(src, window):
    """Read the first 3 bands (R,G,B) of a window. RGBI orthos drop NIR here —
    the semantic CNN takes 3-channel RGB (NIR is only used for spectral features
    in phase1/phase7)."""
    return src.read([1, 2, 3], window=window)


def _site_window(src, bounds_native):
    """Pixel window in src covering bounds_native, clamped to the raster extent."""
    win = rasterio.windows.from_bounds(
        bounds_native.left, bounds_native.bottom,
        bounds_native.right, bounds_native.top, transform=src.transform)
    win = win.round_offsets(op="floor").round_lengths(op="ceil")
    full = rasterio.windows.Window(0, 0, src.width, src.height)
    win = win.intersection(full)
    return win
