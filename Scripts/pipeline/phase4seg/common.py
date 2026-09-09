import contextlib
import errno
import hashlib
import json
import os
import random
import secrets
import socket
import subprocess
import shutil
import threading
import time
import warnings
from pathlib import Path

from phase4seg.config import *
from phase4seg import config
# The scratch cache. Imported at module scope BECAUSE it imports nothing from here at
# module scope — scratchcache reaches back into common (for _scratch_name, tick/tock,
# _staging_lock_for, _sweep_part_orphans) through function-local imports only, the same
# lazy-import discipline phase4seg/CLAUDE.md sets for torch. A cycle in both directions
# would half-initialise both modules.
from phase4seg import scratchcache


# The bootstrap MECHANISM lives in phase4seg/deps.py since 2026-08-31 (refactor 2.3).
# These local names survive because qc/test_ci_gates.py::_bootstrap_specs AST-matches
# `_ensure_deps([...literal list...])` call sites BY NAME in this file — the gate that
# keeps in-script specs consistent with requirements-colab.txt. The names delegate; the
# literal list below stays a literal.
from phase4seg.deps import ensure_deps as _ensure_deps            # noqa: F401
from phase4seg.deps import pip_install as _pip_install            # noqa: F401


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

warnings.filterwarnings("ignore")


def _crs_unit_m(crs):
    """Metres per CRS linear unit, for turning CRS-unit areas into TRUE m².

    THE TRAP (measured 2026-08-27, same family as the gsd_cm defect, WORKPLAN §1.5):
    a raw `.area` or `transform.a * transform.e` is in the CRS's own units, and
    neither CRS this project uses gives true metres —

      EPSG:2285  US survey FEET  -> 1 unit² = 0.0929 m²  (areas 10.76x TOO LARGE)
      EPSG:3857  Web Mercator    -> conformal, not equal-area; at Edmonds
                                    (47.81°N) areas are inflated 1/cos²(lat)
                                    = 2.215x  (measured: the canonical crown
                                    layer's stored area_m2 is 2.2215x its true
                                    UTM-10N area, median 87.8 vs 39.5 m²)

    Multiply an area by `_crs_unit_m(crs) ** 2` to get true m². For Mercator the
    factor is latitude-dependent, so this returns cos(lat) at Edmonds rather than
    the nominal 1.0 — good to ~0.1% across the city, and the honest answer is to
    measure in an equal-area/local CRS (EPSG:26910 UTM 10N) where that matters.
    """
    try:
        epsg = crs.to_epsg() if hasattr(crs, "to_epsg") else rasterio.crs.CRS.from_user_input(crs).to_epsg()
    except Exception:                                    # noqa: BLE001
        epsg = None
    if epsg == 3857:
        return float(np.cos(np.radians(47.81)))
    try:
        from pyproj import CRS as _pyCRS
        return float(_pyCRS.from_user_input(crs).axis_info[0].unit_conversion_factor)
    except Exception:                                    # noqa: BLE001
        return 1.0


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


def untick(label):
    """Drop a running timer WITHOUT printing — an attempt that turned out not to be
    the thing being measured. Added 2026-09-07 for staging.py's tile-bundle attempt:
    it must publish "⏱ stage tiles {label}" only when it actually staged the set, or
    a refused attempt would put a second, ~0 s event of that name in the log the
    rclone fallback is about to write, and the harvested timing series would carry
    two rows per step. Without this the alternative was re-implementing tock's format
    string at the call site, which is exactly the kind of restatement that drifts."""
    _timers.pop(label, None)


def timer_summary():
    if _timers:
        print(f"\n  Unclosed timers: {list(_timers.keys())}")


def _tag_sfx():
    """Filename suffix for --run-tag ('' when unset → legacy names)."""
    return f"_{config.RUN_TAG}" if config.RUN_TAG else ""


def tile_dir_for(label):
    """The tile directory for THIS ARM — {label}__{run_tag}, or {label} untagged.

    THE BUG THIS FIXES (measured 2026-08-28, and it corrupted a landed result).
    Tiles lived at TILE_DIR/{label} with no run-tag component. `_tile_signature`
    DOES key on the overlay, so a SEQUENTIAL arm with different labels correctly
    invalidates and re-tiles. But two arms on the SAME YEAR running CONCURRENTLY
    both resolve to one directory, each judges the other's cache invalid, and both
    re-tile into it — racing. The 2026-08-27 groves arms did exactly this
    (`groves_nolidar` tiled 21:28-21:54, `groves_lidar` 21:36-22:05: 18 minutes of
    overlap, 635 vs 599 tiles), so their B-vs-C comparison compared two models
    trained on an unknown mixture of each other's labels. The A-vs-B/C headline
    survived only because that effect was 21-26 pp and both arms lost.

    Tagged runs now get their own directory, so concurrent arms cannot collide.
    Untagged runs keep the legacy path unchanged — no spurious retile for the
    historical caches. The first run of each tagged arm re-tiles once (~15-25 min);
    that is the price of the isolation and it is worth paying exactly once.
    """
    # The RULE lives in names.tile_dir_name (stdlib-only, shared with the
    # orchestrator); this function supplies the engine's root and its RUN_TAG.
    from phase4seg.names import tile_dir_name
    return TILE_DIR / tile_dir_name(label, config.RUN_TAG)

def remaining_entries():
    """Every acquisition Phase 4 fine-tunes — the catalog minus the 2020 anchor."""
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
# This is a BEST-EFFORT lock on a non-POSIX substrate. Drive has no cross-client
# atomic primitive: O_EXCL is only atomic against each VM's own drivefs cache, Drive
# keeps duplicate names, and cross-VM visibility of creates/updates lags by seconds.
# So: each claimant writes its OWN uniquely named claim file and holds only while its
# claim is the OLDEST live one (by self-reported t_acq, ties by name), confirmed on a
# listing taken ≥ STAGE_LOCK_CONFIRM_SEC after the claim was written (longer than any
# plausible propagation lag), with a one-poll hysteresis when a peer's claim
# disappears. Liveness is judged in the READER's clock (time since a peer's stamp was
# last seen to change — immune to clock skew); a same-host claim with a dead pid is
# stale at once. Re-stamps are in place (same Drive file, never a rename-over).
# Waiting is bounded by STAGE_LOCK_MAX_WAIT_MIN; after that the copy proceeds
# UNLOCKED with a warning but the claim stays live so later claimants still queue
# behind it. Unknown states fail CLOSED (assume a peer is older; assume a file is
# bulk). Every lost race is logged by the holder's heartbeat. Non-Colab runs never
# lock. phase4/locks/ must exist BEFORE two runtimes start (the queue creates it at
# launch, the cockpit's bootstrap cell mkdir's it) — two VMs racing to create it would
# leave Drive with two same-named folders and an inert lock.
# Residual exposure: propagation lag > STAGE_LOCK_CONFIRM_SEC, or a wedged mount.
# The queue's per-step ceilings (phase4_train_queue.STEP_TIMEOUT_MIN) must exceed
# STAGE_LOCK_MAX_WAIT_MIN + own staging + the step's work.
STAGE_LOCK_DIR          = BASE / "phase4" / "locks"
STAGE_LOCK_MIN_BYTES    = 4 << 30  # ≥ 4 GiB copies contend (RETUNED 2026-08-26: the
                                   # rclone-user-mount era; small orthos (2016 2.6 GB)
                                   # were paying hour-scale waits behind big ones for
                                   # a throttle never established. Was 1 GiB). Tile
                                   # sets (0.2-0.7 GiB measured), CHM, masks copy unlocked.
STAGE_LOCK_SETTLE_SEC   = 10       # first listing waits this long after our claim
STAGE_LOCK_CONFIRM_SEC  = 60       # a fresh claim must STILL be oldest ≥ this long after
                                   # it was written (drivefs cross-VM lag is "seconds")
STAGE_LOCK_STALE_MIN    = 15       # a peer's stamp unchanged this long (our clock) = dead
STAGE_LOCK_POLL_SEC     = 30
STAGE_LOCK_BEAT_SEC     = 60
STAGE_LOCK_MAX_WAIT_MIN = 15       # then copy UNLOCKED (claim kept + beating, warn).
                                   # RETUNED 60->15 (2026-08-26): an hour of A100 idle
                                   # behind the lock was measured; 15 min bounds the
                                   # worst case at ~$0.15 while keeping serialization
                                   # for genuinely concurrent bulk pulls.


def _lock_enabled():
    """Only a Colab VM with Drive mounted takes the lock. config.BASE is the
    hard-coded Colab path on every platform, so test the MOUNT, not BASE —
    locally (Windows smoke/QC) this is always False and nothing is created."""
    return os.name == "posix" and Path("/content/drive/MyDrive/treedata").is_dir()


def _pid_alive(pid):
    """POSIX only: os.kill(pid, 0) probes. On Windows os.kill TERMINATES, so the
    answer there is always 'alive'. Implementation shared with the orchestrator —
    these were twins, and they DID diverge (the queue's copy lost this guard)."""
    from phase4seg.names import pid_alive
    return pid_alive(pid)


class _StagingLock:
    """`with _StagingLock("2024_coe_rgb.tif"):` around any bulk copy from Drive.
    `.held` is False when the copy proceeds unlocked (local run, or max-wait hit)."""

    def __init__(self, what):
        self.what = what
        self.host = socket.gethostname()
        self.pid = os.getpid()
        self.token = secrets.token_hex(3)              # threads / pid reuse never collide
        self.t_acq = None
        self.path = STAGE_LOCK_DIR / f"staging.{self.host}.{self.pid}.{self.token}.lock"
        self.held = False
        self._stop = threading.Event()
        self._beat = None
        self._seen = {}          # peer claim name -> (last ts value seen, when WE saw it change)
        self._last_stamp = None  # when we last wrote our claim
        self._broken = False     # a peer removed our claim (detected at re-stamp)

    # -- claim files ---------------------------------------------------------
    def _payload(self):
        return json.dumps({"host": self.host, "pid": self.pid, "what": self.what,
                           "t_acq": self.t_acq, "ts": time.time()})

    def _write_claim(self):
        exists = self.path.exists()
        if self._last_stamp is not None and not exists:
            self._broken = True                      # a peer broke us as stale: we lost our place
        if exists:
            self.path.write_text(self._payload())    # re-stamp IN PLACE: same Drive file, one
        else:                                        # revision (a torn read ⇒ "older" ⇒ wait)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(self._payload())
            os.replace(tmp, self.path)               # first create only: never a half-written claim
        self._last_stamp = time.time()

    def _remove_claim(self):
        err = None
        for delay in (1, 2, 4, 8, 16, 30):           # ~1 min of backoff << STALE_MIN
            try:
                self.path.unlink()
                return
            except FileNotFoundError:
                return
            except OSError as e:                     # drivefs EIO/ETIMEDOUT
                err = e
                time.sleep(delay)
        print(f"  WARNING: could not remove our staging claim {self.path.name} ({err}); "
              f"peers will wait up to {STAGE_LOCK_STALE_MIN} min", flush=True)

    def _claims(self):
        """Sorted [(t_acq, name, path, payload)] of live claims. Stale claims of OTHER
        claimants (and orphaned .tmp halves) are removed on the way — never our own."""
        now = time.time()
        for p in STAGE_LOCK_DIR.glob("staging.*.tmp"):        # orphaned half of a first create
            try:
                if (now - p.stat().st_mtime) / 60 > STAGE_LOCK_STALE_MIN:
                    p.unlink()
            except OSError:
                pass
        live = []
        for p in sorted(STAGE_LOCK_DIR.glob("staging.*.lock")):
            if p == self.path:                                # ours: t_acq is in hand — never
                live.append((self.t_acq, p.name, p, {}))      # read it back (unreadable self
                continue                                      # must not sort to "oldest")
            d, ts, t_acq = {}, None, 0.0                      # unknown ⇒ assume it PREDATES us
            try:
                d = json.loads(p.read_text())
                if not isinstance(d, dict):
                    d = {}
                ts = float(d["ts"])
                t_acq = float(d.get("t_acq") or ts)
            except Exception:                                 # noqa: BLE001  (torn/odd payload)
                try:
                    ts = p.stat().st_mtime
                except OSError:
                    ts = None                                 # listed but gone: transient — keep, older
            prev = self._seen.get(p.name)
            if prev is None or (ts is not None and prev[0] != ts):
                self._seen[p.name] = (ts, now)                # stamp advanced (or first sight): live now
            age_min = (now - self._seen[p.name][1]) / 60.0    # READER clock only — skew-immune
            dead_local = d.get("host") == self.host and not _pid_alive(d.get("pid"))
            if age_min > STAGE_LOCK_STALE_MIN or dead_local:
                why = "dead pid" if dead_local else f"stamp unchanged {age_min:.0f} min"
                print(f"  staging lock: breaking stale claim {p.name} ({why})", flush=True)
                try:
                    p.unlink()
                except OSError:
                    pass
                self._seen.pop(p.name, None)
                continue
            live.append((t_acq, p.name, p, d))
        return sorted(live, key=lambda c: (c[0], c[1]))

    def _heartbeat(self):
        warned_broken = False
        while not self._stop.wait(STAGE_LOCK_BEAT_SEC):
            try:
                self._write_claim()
                if self._broken and not warned_broken:
                    print("  WARNING: a peer broke our staging claim as stale while we were "
                          "copying — recreated; two bulk copies may be running", flush=True)
                    warned_broken = True
                claims = self._claims()
                if claims and claims[0][2] != self.path:
                    print("  WARNING: an older live staging claim is present while we copy — "
                          f"two bulk copies may be running ({claims[0][3]})", flush=True)
            except Exception as e:                            # noqa: BLE001
                print(f"  staging lock: heartbeat error ({e!r}); continuing", flush=True)
        self._remove_claim()     # program-ordered after our last write: the claim cannot outlive us

    def _start_beat(self):
        self._beat = threading.Thread(target=self._heartbeat, daemon=True)
        self._beat.start()

    # -- context manager -----------------------------------------------------
    def __enter__(self):
        if not _lock_enabled():
            return self
        t0 = time.time()
        self.t_acq = t0
        announce = first = True
        prev_others = set()
        while True:
            if (time.time() - t0) / 60 > STAGE_LOCK_MAX_WAIT_MIN:
                print(f"  WARNING: waited {STAGE_LOCK_MAX_WAIT_MIN} min for the staging lock; "
                      f"proceeding WITHOUT it ({self.what}) — claim kept so later claimants "
                      "still queue behind this copy", flush=True)
                self._start_beat()                            # held stays False
                return self
            wait = STAGE_LOCK_POLL_SEC + random.uniform(0, STAGE_LOCK_POLL_SEC / 2)
            try:
                STAGE_LOCK_DIR.mkdir(parents=True, exist_ok=True)
                if first:
                    dups = [p.name for p in STAGE_LOCK_DIR.parent.iterdir()
                            if p.name.startswith("locks")]
                    if len(dups) > 1:
                        print(f"  WARNING: duplicate lock folders on Drive {dups} — the "
                              "staging lock may NOT be cross-runtime", flush=True)
                self._write_claim()                           # (re)stamp ts; t_acq fixed …
                if self._broken:                              # … unless a peer broke us: re-queue
                    self.t_acq = time.time()
                    self._broken = False
                    self._write_claim()
                if first:
                    time.sleep(STAGE_LOCK_SETTLE_SEC)
                    first = False
                claims = self._claims()
                others = {c[1] for c in claims if c[2] != self.path}
                vanished = prev_others - others
                prev_others = others
                if claims and claims[0][2] == self.path:
                    if vanished:
                        pass        # a live peer claim just disappeared (release, or a drivefs
                                    # visibility hiccup): trust it only if still gone next poll
                    else:
                        remaining = STAGE_LOCK_CONFIRM_SEC - (time.time() - self.t_acq)
                        if remaining > 0:
                            wait = remaining    # fresh claim: a peer's slightly-earlier claim may
                        else:                   # not have propagated yet — confirm after the lag window
                            self.held = True
                            self._start_beat()
                            if not announce:
                                print(f"  staging lock acquired after {(time.time() - t0) / 60:.1f} min",
                                      flush=True)
                            return self
                elif announce and claims:
                    h = claims[0][3]
                    print(f"  staging lock held by {h.get('host', '?')}:{h.get('pid', '?')} "
                          f"for {h.get('what', '?')}; waiting for {self.what} "
                          f"(poll {STAGE_LOCK_POLL_SEC}s) …", flush=True)
                    announce = False
            except OSError as e:                              # drivefs EIO/ETIMEDOUT etc.
                print(f"  staging lock: Drive error ({e}); retrying", flush=True)
            except Exception as e:                            # noqa: BLE001  never raise out of here
                print(f"  staging lock: unexpected error ({e!r}); retrying", flush=True)
            time.sleep(wait)

    def __exit__(self, *exc):
        if self._beat is not None:
            self._stop.set()
            while self._beat.is_alive():                      # a re-stamp may be mid-flight on
                self._beat.join(timeout=10)                   # FUSE: unlink only once nothing
                if self._beat.is_alive():                     # can land after us
                    print("  staging lock: waiting for the heartbeat's Drive write …", flush=True)
        self.held = False
        self._remove_claim()
        return False


def _staging_lock_for(src_path):
    """The lock for a copy of `src_path`, or a no-op for small files (CHM, masks):
    only bulk copies contend for Drive bandwidth. Fails CLOSED: an unreadable size
    (drivefs EIO/ETIMEDOUT) is treated as bulk."""
    name = Path(src_path).name
    try:
        size = Path(src_path).stat().st_size
    except OSError as e:
        print(f"  staging lock: stat {name} failed ({e}); assuming bulk copy", flush=True)
        return _StagingLock(name)
    if size >= STAGE_LOCK_MIN_BYTES:
        return _StagingLock(name)
    return contextlib.nullcontext()


def _stage_imagery_local(src_path):
    """Copy a Drive ortho to local NVMe; return the local path (or src on failure).

    THIS FUNCTION WAS ALREADY A CACHE. Its `dst.exists() and size == src_size` early
    return is a hit, and it worked — it just never fired across steps, because every
    step DELETED the payload on its way out (the ledger in `_unstage_imagery_local`
    below). phase4seg/scratchcache.py adds the journal that lets the hit survive the
    step: pins so a peer cannot evict what someone is reading, a floor so a full disk
    still refuses gracefully, and an atomic `.part` + os.replace so a copy killed midway
    can no longer leave a truncated multi-GB file at the exact path a later reader
    trusts (the failure postproc.py::_resolve_prob_source documents at length).

    The two contracts of this shim are UNCHANGED and are the reason it stays a shim:
    the `/content/drive` prefix early return (so nothing off-Colab is ever cached, and
    no cache function has to test for a mount), and the returns-SOURCE-on-failure
    except. The payload path is unchanged too — LOCAL_SCRATCH / _scratch_name(src) —
    which is what preserves postproc.py::_resolve_prob_source's "(a) and (b) resolve to
    the SAME scratch path by construction" and the LOCAL_SCRATCH guard below.

    D18 was applied to _local_artifact_path (the WRITE side) and not here (the READ
    side), though the collision is the same one: two Drive orthos whose basenames match
    — different years' native/ files routinely do — staged to one scratch file, and the
    exists+size test then hands the second caller the first one's imagery. Same
    deterministic full-path hash, same reasoning; scratchcache keys on that same hash.
    """
    src_path = Path(src_path)
    if not str(src_path).startswith("/content/drive"):
        return src_path  # already local
    try:
        return scratchcache.stage(src_path)
    except Exception as e:                                   # noqa: BLE001
        print(f"  WARNING: local staging failed ({e}); reading from Drive")
        return src_path


def _unstage_imagery_local(local_path):
    """RELEASE a staged file — drop our claim on it; the bytes stay, evictable.

    IT USED TO UNLINK, AND THAT IS WHAT THIS CHANGE IS. The same 11.5 GB ortho
    `2017_king_rgb.tif` was staged FOUR times across the pilot and its baseline; on the
    baseline A100 box tile paid 123.5 s and inference then paid 87.1 s for the identical
    file (phase4/qc/timing_events.csv). Re-staging is 42% of all staged seconds
    all-time, 53% post-08-30 (Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md §2).

    THE LEDGER — why each historical delete existed, so the next reader knows which
    were space management (now the evictor's job) and which were correctness (still
    deletes, via scratchcache.invalidate):

      labels.py::step_labels finally            the year's ortho — space; tiling.py
                                                re-stages the SAME file next  -> release
      tiling.py::_gather_citywide_coarse (x3)   ortho, MASK_2020, the --add-canopy-mask
                                                overlay — space. The two shared rasters
                                                are the CROSS-YEAR hits; the measured
                                                count has ONE home, scratchcache.py's
                                                module docstring -> release
      core.py::step_inference dry-run return    NOT A SITE. It read `_unstage_imagery_
                                                local(local) if local != native`, but a
                                                dry run sets `local = native`, so it
                                                never fired and nothing was ever staged
                                                there. Deleted, not converted.
      core.py::step_inference tail              the ortho — space -> release
      core.py::step_inference (not POSTPROC_
        FOLLOWS) prob_out.unlink()              an explicit disk bound, so a long
                                                inference-only queue could not fill the
                                                VM — now the evictor's floor -> adopt
                                                + release
      postproc.py::step_postproc finally        the prob raster, both branches — bound
                                                the per-year leak -> release
      postproc.py::_resolve_prob_source         a short/stale copy — CORRECTNESS, not
        discard-on-size-mismatch                space -> scratchcache.invalidate
      postproc.py mask/gpkg after _copy_to_
        drive; staging.py local_tar.unlink      write-side / transient -> UNCHANGED

    A payload with no cache record is not an entry — nobody would ever free it — so
    scratchcache.release keeps this function's historical unlink for that case. Only
    OWNED entries survive a release.
    """
    local_path = Path(local_path)
    try:
        if str(local_path).startswith(str(LOCAL_SCRATCH)):
            scratchcache.release(local_path)
    except Exception:
        pass


def _digests(path, algos=("sha256",), chunk=1 << 20):
    """{algo: hexdigest} for `path`, computed in ONE pass over the bytes.

    One pass matters because the verified write now wants sha256 (local↔copy) AND
    md5 (the only hash Google Drive exposes, so the only one a SERVER-SIDE check
    can compare against). Two passes over a multi-GB raster is minutes of NVMe for
    nothing.
    """
    hs = {a: hashlib.new(a) for a in algos}
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            for h in hs.values():
                h.update(b)
    return {a: h.hexdigest() for a, h in hs.items()}


def _sha256(path, chunk=1 << 20):
    return _digests(path, ("sha256",), chunk)["sha256"]


# ── Server-side write verification (D1) ───────────────────────────────────────
# THE DEFECT. `_copy_to_drive` wrote through the rclone FUSE mount and then read
# the copy back THROUGH THE SAME MOUNT to verify it. With --vfs-cache-mode writes
# that read is served from the VM's own local write cache, so "✓ verified write"
# attested only that bytes reached a cache on the machine that wrote them — the
# exact thing that was true on 2026-08-29 when the log reported deploying epoch
# B24 and every checkpoint on Drive was B7. The bytes were in the cache; the VM
# was unassigned before they drained; nothing had ever asked Drive.
#
# THE INDEPENDENT CHANNEL. gen_vm_bootstrap.py's write canary already proves the
# pattern: ask the SERVICE ACCOUNT remote, over the Drive API, for the file's md5.
# That path shares no cache, no mount and no process with the write. `treedata-sa`
# is READ-ONLY in practice (the SA has zero storage quota, so it cannot own
# uploads) which is exactly what a verifier should be.
#
# WHAT A MISMATCH MEANS — the trap that makes this safe to run in a hot loop.
# rclone uploads ASYNCHRONOUSLY, so for a while after the write the server still
# holds the PREVIOUS file and answers with its md5. A mismatch is therefore NOT
# evidence of corruption; it is "not drained yet" until proven otherwise. So this
# only ever polls for a MATCH and reports what it found. It never raises, never
# triggers a re-copy, and never fails a run. Raising stays with the local
# size/sha256 check, where a mismatch really does mean a broken copy.
_SA_REMOTE = "treedata-sa"                 # gen_vm_bootstrap.py's VERIFIER remote
_DRIVE_MOUNT_PREFIX = "/content/drive/MyDrive/treedata/"
_sa_remote_probe = None                    # None = unprobed; True/False = cached


def _sa_remote_ready():
    """True iff `rclone` is on PATH and the SA verification remote is configured.

    Probed at most once per process. Anywhere this is False — local Windows QC, a
    VM booted without the SA, an old bootstrap — server-side verification is simply
    UNAVAILABLE, and every caller says so out loud rather than claiming a proof it
    does not have.
    """
    global _sa_remote_probe
    if _sa_remote_probe is None:
        _sa_remote_probe = False
        try:
            if os.name == "posix" and shutil.which("rclone"):
                r = subprocess.run(["rclone", "listremotes"], capture_output=True,
                                   text=True, timeout=60)
                _sa_remote_probe = (r.returncode == 0 and
                                    f"{_SA_REMOTE}:" in (r.stdout or "").split())
        except Exception:                              # noqa: BLE001 — any failure = no
            _sa_remote_probe = False
    return _sa_remote_probe


def _drive_rel(drive_path):
    """`treedata`-relative posix path for a mounted path, or None if it is not
    under the mount. `treedata-sa:`'s root_folder_id IS the treedata folder, so the
    mapping is 1:1 (phase4/models/sem_best_2009_x.pt)."""
    s = str(drive_path)
    if not s.startswith(_DRIVE_MOUNT_PREFIX):
        return None
    return s[len(_DRIVE_MOUNT_PREFIX):].strip("/")


def _remote_md5(drive_path, timeout=120):
    """Server-side md5 of `drive_path` via the SA remote, or None if unavailable.

    `rclone md5sum`, not `lsjson --hashes`: that flag does not exist on the VM's
    rclone build (measured 2026-08-26, when the flagless canary false-failed a good
    upload). Output is "<md5>  <path>"; a missing remote file exits non-zero.
    """
    rel = _drive_rel(drive_path)
    if rel is None or not _sa_remote_ready():
        return None
    try:
        r = subprocess.run(["rclone", "md5sum", f"{_SA_REMOTE}:{rel}"],
                           capture_output=True, text=True, timeout=timeout)
    except Exception:                                  # noqa: BLE001
        return None
    if r.returncode != 0:
        return None
    tok = (r.stdout or "").split()
    return tok[0].lower() if tok and len(tok[0]) == 32 else None


def verify_on_drive(drive_path, want_md5, wait_s=0.0, poll_s=10.0):
    """Poll the Drive API for `want_md5` at `drive_path`. → (state, note).

    state is one of:
      "ok"          the bytes are ON DRIVE — proven independently of this VM.
      "pending"     no match within `wait_s`. Almost always an undrained upload
                    backlog, NOT corruption (see the module note above), so the
                    caller reports it and carries on. It is still not a pass.
      "unavailable" no rclone / no SA remote / path outside the mount. Nothing was
                    checked and the caller must not imply otherwise.

    wait_s=0.0 does exactly one probe and never sleeps — cheap enough for the
    per-epoch checkpoint write, where the authoritative long wait belongs instead
    to the queue's once-per-job VERIFY:train.
    """
    if not want_md5:
        return "unavailable", "no local md5 to compare"
    if _drive_rel(drive_path) is None:
        return "unavailable", "path is not under the Drive mount"
    if not _sa_remote_ready():
        return "unavailable", f"no `{_SA_REMOTE}` rclone remote on this host"
    t0 = time.time()
    got = None
    while True:
        got = _remote_md5(drive_path)
        if got == want_md5:
            return "ok", f"drive md5 {got[:8]}"
        if time.time() - t0 >= wait_s:
            break
        time.sleep(min(poll_s, max(0.0, wait_s - (time.time() - t0))))
    waited = int(time.time() - t0)
    return "pending", (f"drive md5 {(got or 'absent')[:8]} != local {want_md5[:8]}"
                       f" after {waited}s")


_PROBE_RETRY_ERRNOS = (errno.EIO, errno.ENOTCONN)
_PROBE_BACKOFF_S = (2, 4, 8, 16, 30)


def _probe_retry(fn, what, tries=5, backoff=_PROBE_BACKOFF_S):
    """Call `fn()` — a metadata probe (exists / stat) on the FUSE mount — retrying
    ONLY a transient-mount errno, bounded, logging every retry. → fn()'s result.

    WHY (2026-09-09). bb50_2011s_cor05 died at epoch A17 with
    `OSError: [Errno 5] Input/output error` raised by `dest.exists()` — the very
    first line of _publish_replace — after 16 epochs of clean publishes
    (phase4/logs/phase4_semantic_finetune_train_2011s_2026-09-09T09-03.log). The
    checkpoint was already safe on local NVMe and the copy to the `.part` had
    succeeded; what failed was one stat() the mount answered with EIO, and it took
    the whole train step with it. _copy_to_drive already retries EIO on the COPY
    (2009_corrupt25, 2026-08-29) — the probes were the one call in the publish path
    that a single mount hiccup could still turn into a dead run.

    BOUNDED AND NARROW, on purpose. Five tries, 2..30 s backoff (~60 s total): a mount
    that is still refusing after a minute is a dead mount, and the step should die
    loudly rather than hang. Only EIO and ENOTCONN are retried — the two errnos an
    rclone FUSE mount returns for a transient transport failure. Every other OSError
    (ENOENT, EACCES, ...) is a real answer about the path and propagates on the first
    call, unchanged; masking those would hide exactly the kind of failure this
    module exists to surface. The final EIO propagates as the ORIGINAL exception so
    the log and known_failures.yaml's "Errno 5" match keep working.
    """
    for i in range(tries):
        try:
            return fn()
        except OSError as e:
            if e.errno not in _PROBE_RETRY_ERRNOS or i >= tries - 1:
                raise
            wait = backoff[min(i, len(backoff) - 1)]
            print(f"  ! {what} raised {type(e).__name__} [Errno {e.errno}] "
                  f"{e.strerror or e} — mount hiccup? retrying in {wait}s "
                  f"[{i + 1}/{tries}]", flush=True)
            time.sleep(wait)


def _publish_replace(part, dest):
    """os.replace `part` onto `dest` with the destination guaranteed ABSENT.

    WHY (D4). This was a plain `os.replace(part, drive_path)` over a destination
    that already existed, on the rclone FUSE mount, once per improving epoch. The
    mount canary that blessed os.replace only ever proved the ABSENT-destination
    case — select.py::_deploy_smoothed_keeping_raw says so in as many words — so the
    hot loop was running the
    unproven case thousands of times a night.

    Rename-aside makes BOTH renames absent-destination, and unlike
    unlink-then-replace it never destroys the previous artifact before the new one
    is in place: if the publish fails WITHOUT landing, the old file is restored from
    the aside name, and either way the caller still has something valid on Drive.

    The aside suffix goes AFTER the extension (`sem_best_2009_x.pt.prev.a1b2c3`).
    Every artifact glob in this repo is extension-anchored, so `.prev.*` matches
    none of them — the same reason `.part.*` is spelled that way.

    THE ASIDE RENAME'S ERROR IS NOT ALWAYS FileNotFoundError. It was guarded against
    that alone, which reads "dest vanished under us, so there is no aside" — true for
    ENOENT and false for everything else. On this rclone FUSE mount a transient EIO
    is documented (queue_verify.py::_check_prob_raster retries for it), and an
    EIO can be raised AFTER the rename has already landed: dest is then gone, `aside`
    is set to None by the old code as if nothing had moved, and the publish proceeds
    with the previous CHECKPOINT stranded under a `.prev.<hex>` name no reader globs
    — every artifact glob in this repo is extension-anchored — and only
    _sweep_part_orphans reclaims, past its 24 h age gate, on the next _copy_to_drive
    into that directory. So the previous checkpoint is unreachable to every reader
    for up to a day and is then deleted: not kept, just slowly lost, which is why it
    must not be stranded in the first place. The three `.prev.*` orphans found on the
    lake 2026-09-07 (e499355's closing note) were STATUS TABLES, not checkpoints — but
    this path carried the same guard byte-for-byte, so the same mechanism was
    available to it, and here it is worse: if the publish then failed too, the
    restore never ran and the destination — the file a scoring run loads — stayed
    EMPTY.

    So: catch OSError, then RE-PROBE the filesystem rather than trust the exception's
    type. dest still there means the rename did not land — re-raise without
    publishing, because publishing over an existing destination is the unproven
    os.replace case this function exists to avoid. The raise propagates out of
    _copy_to_drive — its retry loop covers the COPY, not the publish — and its
    `finally` drops the `.part.*`, so what is left on Drive is the previous
    checkpoint, intact and complete, which is the recoverable state. That branch does
    NOT unlink an aside that landed anyway. The probe is the only evidence either
    way, and the two mistakes are not the same size: if it is right, the file it
    would delete is a duplicate of a `dest` that is still published and the sweep
    collects it; if it is wrong, that file is the LAST copy of a 371 MB checkpoint.
    Under equal uncertainty, keep the copy. dest gone AND the aside present means the
    rename DID complete: the aside holds the only copy of the previous checkpoint,
    so the publish below proceeds and restores from it only where it can still see an
    absent destination. dest gone and no aside is the original ENOENT reading.

    THE PUBLISH RENAME COMPLETES-THEN-FAILS THE SAME WAY, and the restore did not ask.
    `os.replace(aside, dest)` ran on ANY OSError from the publish, so an EIO raised
    after the publish had already landed put the previous checkpoint back over an
    EXISTING destination — the unproven case, inside the function whose only reason to
    exist is avoiding it — and silently reverted a good new checkpoint while telling
    the caller the publish had failed. Same shape as the aside bug, one line lower.
    The restore now probes first: a present dest means a checkpoint IS published
    there, so leave it, leave the aside for the sweep, and re-raise without
    clobbering. Only an absent dest is restored into. It re-raises rather than
    reporting success because it cannot PROVE which file landed — verify_on_drive
    downstream reports and never refuses, so a returned success would pass a gate
    that cannot push back. The caller-visible behaviour is unchanged from before this
    fix (publish error → raise); only the clobber is gone.

    COVERAGE, INFERRED not measured: both probes read the LOCAL view of a FUSE mount.
    They cover the case that was reproduced — the rename landed and the error came
    back afterwards. A stale view the other way (the kernel believes the rename
    failed, dest reads absent while the server has it) would still take the old
    branch. Nothing on this box can measure rclone's cache behaviour.

    The aside-rename guard was ported from queue_ledger.py::_replace_absent (c5dc91c),
    which met that bug first; the two probe-before-destroy fixes above were made HERE
    first (2026-09-07). Whether the ledger twin has caught up is stated in
    queue_ledger.py::_replace_absent's own docstring — this one does not restate it.
    """
    aside = None
    # Every probe below goes through _probe_retry: one EIO on a stat() must not end
    # a train step (2026-09-09, see the helper). The retry changes nothing about
    # WHAT the probes decide — only whether one transient answer is final.
    if _probe_retry(lambda: dest.exists(), f"probe {dest.name}"):
        aside = dest.with_name(dest.name + f".prev.{secrets.token_hex(3)}")
        try:
            os.replace(dest, aside)                    # absent destination
        except OSError:
            if _probe_retry(lambda: dest.exists(), f"re-probe {dest.name}"):
                # the rename did not happen; the previous checkpoint is still
                # published, so re-raise without publishing over it. An aside that
                # landed anyway is NOT unlinked here: that unlink is a no-op in
                # every case except the one where this probe is what is wrong, and
                # there it deletes the last copy of the checkpoint.
                raise
            if not _probe_retry(lambda: aside.exists(), f"probe {aside.name}"):
                aside = None               # dest vanished under us — nothing to keep
            # else: the rename completed and THEN failed. Fall through: `aside` holds
            # the only copy of the previous checkpoint, and the publish below
            # restores it if it cannot land the new one — but only where the
            # destination still reads absent, never over a published file.
    try:
        os.replace(part, dest)                         # absent destination
    except OSError:
        if _probe_retry(lambda: dest.exists(), f"re-probe {dest.name}"):
            # the publish landed and THEN reported the error: a checkpoint is
            # published. Restoring would replace over an EXISTING destination and
            # revert it to the previous one. Leave both files and re-raise.
            print(f"  ! {dest.name} is published but its rename reported an error; "
                  f"not restoring over it"
                  + (f" (previous copy at {aside.name})" if aside is not None else ""))
        elif aside is not None:
            try:
                os.replace(aside, dest)                # put the old one back
            except OSError:
                print(f"  ! could not restore the previous {dest.name}; it is at "
                      f"{aside.name}")
        raise
    if aside is not None:
        try:
            aside.unlink()
        except OSError:
            pass


def _local_artifact_path(final_path):
    """Where to WRITE a heavy artifact destined for `final_path`.

    On Colab (final under /content/drive) → a scratch path on local NVMe, so the
    multi-GB write never streams over FUSE; the caller then _copy_to_drive()s it.
    Anywhere else → final_path unchanged (already local disk).

    D18 (2026-08-29): the scratch name was the BASENAME ALONE, so every Drive path
    ending in the same filename mapped to ONE local file. LOCAL_SCRATCH is shared
    by every process on the VM, and the names in play are not as unique as they
    look — `semantic_eval_report.csv` under phase4/eval and any same-named file
    elsewhere collide outright, and two engine steps writing different
    destinations with a shared basename would silently interleave into one
    multi-GB staging file and then publish each other's bytes.

    The scratch name now carries a short hash of the FULL destination path, so
    distinct destinations cannot alias. It stays DETERMINISTIC (no pid, no token)
    on purpose: a retry after a crash must reuse — and overwrite — the same
    scratch file rather than leaking another 8 GB onto a disk that is not swept.

    This does not make two LIVE processes writing the same destination safe;
    nothing here could. That is a shared run tag, and the tag guard is what has to
    catch it.
    """
    final_path = Path(final_path)
    if str(final_path).startswith("/content/drive"):
        LOCAL_SCRATCH.mkdir(parents=True, exist_ok=True)
        return LOCAL_SCRATCH / _scratch_name(final_path)
    return final_path


def _scratch_name(final_path):
    """Staging basename for `final_path` — its own function so the naming rule is
    testable off-Colab (the branch above cannot be entered on Windows, by design:
    str(WindowsPath("/content/drive/…")) is backslashed)."""
    final_path = Path(final_path)
    h = hashlib.sha256(str(final_path).encode("utf-8")).hexdigest()[:8]
    # The tag goes before the EXTENSION CHAIN, so the file keeps its type and GDAL
    # still picks the right driver: sem_best_2009_x.pt → sem_best_2009_x__3f2a9c01.pt
    name = final_path.name
    stem, dot, ext = name.partition(".")
    return f"{stem}__{h}{dot}{ext}" if dot else f"{name}__{h}"


def _sweep_part_orphans(dirpath, max_age_h=24):
    """Remove *.part.* / *.prev.* staging files a died process left behind
    (multi-GB quota leaks otherwise). Age-gated generously: a live .part being
    written by a concurrent runtime is minutes old, never a day, and a .prev.
    aside exists for the microseconds between two renames unless a publish died
    between them."""
    now = time.time()
    try:
        for pat in ("*.part.*", "*.prev.*"):
            for p in Path(dirpath).glob(pat):
                try:
                    if now - p.stat().st_mtime > max_age_h * 3600:
                        p.unlink()
                        print(f"  swept stale staging orphan: {p.name}")
                except OSError:
                    pass
    except OSError:
        pass


def _copy_to_drive(local_path, drive_path, checksum=True, retries=3,
                   server_wait_s=0.0):
    """ATOMIC local-then-copy write, verified as far as it can actually prove.

    The unverified direct-to-Drive write has produced three broken artifacts
    (2022 xsensor 0-byte, 2017 xsensor 96.5%-nodata, 2024 truncated stub) that
    each cost a GPU run before anyone noticed. This copy refuses to be silent:
    size must match, and (checksum=True) the staged copy must hash identical to
    the local one; on repeated mismatch, RAISE — a loud failure at write time is
    the entire point.

    E02 (2026-08-25): the copy stages to `<name>.part.<pid><token>` and only an
    os.replace within the Drive directory publishes the final name, so a death
    mid-copy can no longer leave a truncated file at the canonical path — and a
    FAILED re-copy no longer unlinks the previous GOOD artifact (the old code
    unlinked drive_path itself on mismatch). The suffix is APPENDED (never
    with_suffix: mask .tif/.gpkg pairs share a stem) and pid+token-unique so two
    runtimes targeting one path cannot collide; every artifact-reading glob in
    the repo is extension-anchored, so .part.* files match none of them.

    TWO CHECKS, AND THEY PROVE DIFFERENT THINGS (D1, 2026-08-29):

      size + sha256 of the staged copy — read back through the SAME mount that
        wrote it, so under --vfs-cache-mode writes it is served from this VM's own
        write cache. It catches a truncated or garbled COPY, and that is all it
        has ever been able to catch. It is not evidence the bytes are on Drive.
        This is the check that RAISES.

      md5 against the Drive API via the service-account remote — no shared cache,
        no shared mount, no shared process. This is the only one that can say the
        artifact SURVIVES THIS VM. It never raises: an unmatched md5 shortly after
        a write is an undrained upload backlog far more often than corruption (see
        the `verify_on_drive` note), so it is reported, not acted on.

    So the line this prints now says which of the two it earned:
        ✓ verified write        — proven on Drive
        ✓ staged write … PENDING/LOCAL CACHE ONLY — bytes copied, Drive not (yet)
                                  confirmed. NOT the same claim, and not spelled
                                  the same, because the old wording is precisely
                                  what made an epoch-7 corpse look like a pass.

    server_wait_s=0.0 probes Drive once without sleeping, which is what the
    per-epoch checkpoint write wants; the authoritative long wait lives in the
    queue's once-per-job VERIFY:train, where it can decide something.
    """
    local_path, drive_path = Path(local_path), Path(drive_path)
    drive_path.parent.mkdir(parents=True, exist_ok=True)
    if local_path == drive_path:
        return drive_path
    _sweep_part_orphans(drive_path.parent)
    want_size = local_path.stat().st_size
    # md5 is computed whenever a server-side check is possible at all — it is the
    # ONLY hash Drive exposes. Both digests come from a single pass over the file.
    _want_md5_too = _drive_rel(drive_path) is not None and _sa_remote_ready()
    _algos = (("sha256",) if checksum else ()) + (("md5",) if _want_md5_too else ())
    _dig = _digests(local_path, _algos) if _algos else {}
    want_sha = _dig.get("sha256")
    want_md5 = _dig.get("md5")
    part = drive_path.with_name(
        drive_path.name + f".part.{os.getpid()}{secrets.token_hex(3)}")
    try:
        for attempt in range(retries + 1):
            tick(f"copy {drive_path.name}")
            # copyfile + BEST-EFFORT copystat, not copy2: copystat's utime on the
            # rclone FUSE mount can raise a transient EIO on a dirty/uploading
            # file, and that metadata nicety killed a 45-min train at epoch 24
            # (2021s noise_r2, 2026-08-26). Data integrity is enforced below by
            # size+sha256, never by mtime.
            # The COPY ITSELF can raise EIO when the rclone mount hiccups — not a
            # mismatch we could detect below, an exception that killed the whole
            # job. Measured: 2009_corrupt25 lost 114.5 min of A100 to
            # `OSError: [Errno 5] Input/output error` on this exact .part write
            # (2026-08-29). The checkpoint was already safe on local NVMe; only
            # the transfer failed, so a retry costs seconds and saves the run.
            # Backoff is generous because the mount usually recovers in tens of
            # seconds. Integrity is still enforced by size+sha256 below — this
            # widens WHAT we retry, never what we accept.
            try:
                shutil.copyfile(local_path, part)
            except OSError as e:
                tock(f"copy {drive_path.name}")
                print(f"  ! copy raised {type(e).__name__}: {e} "
                      f"[attempt {attempt + 1}/{retries + 1}]")
                try:
                    part.unlink()
                except OSError:
                    pass
                if attempt < retries:
                    time.sleep(20 * (attempt + 1))
                    continue
                raise
            try:
                shutil.copystat(local_path, part)
            except OSError as e:
                print(f"  (copystat skipped on {part.name}: {e})")
            tock(f"copy {drive_path.name}")
            got_size = _probe_retry(lambda: part.stat().st_size,
                                    f"stat {part.name}")
            if got_size != want_size:
                problem = f"size {got_size} != {want_size}"
            elif checksum and _sha256(part) != want_sha:
                problem = "sha256 mismatch"
            else:
                _publish_replace(part, drive_path)     # D4: destination absent
                local_note = f"{want_size/1e6:.0f} MB" + (", sha256 ok" if checksum else "")
                state, note = verify_on_drive(drive_path, want_md5, wait_s=server_wait_s)
                if state == "ok":
                    print(f"  ✓ verified write: {drive_path.name} "
                          f"({local_note}, {note})")
                elif state == "pending":
                    print(f"  ✓ staged write: {drive_path.name} ({local_note}) — "
                          f"Drive NOT CONFIRMED: {note}. The upload backlog is "
                          f"drained before the VM stops; VERIFY:train/inference "
                          f"is what proves it landed.")
                else:
                    print(f"  ✓ staged write: {drive_path.name} ({local_note}) — "
                          f"LOCAL CACHE ONLY, no server-side check ({note})")
                return drive_path
            print(f"  ! verified write FAILED ({problem}) for {drive_path.name} "
                  f"[attempt {attempt + 1}/{retries + 1}]")
            try:
                part.unlink()
            except OSError:
                pass
    finally:
        try:
            _part_left = _probe_retry(lambda: part.exists(), f"probe {part.name}")
        except OSError:
            _part_left = True              # cannot tell — try the unlink anyway
        if _part_left:
            try:
                part.unlink()
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

_HILLSHADE_DS = {}   # source name → staged local PATH (handles are per-thread, below)

_HS_TLS = threading.local()          # one open handle PER THREAD (see below)


def _hillshade_ds():
    """Open + cache the staged HS_SOURCE master, or None if absent/disabled.

    THREAD SAFETY (P11.6, 2026-08-22): a rasterio/GDAL DatasetReader must not be read
    from several threads at once — concurrent block decodes race in the per-dataset
    cache and raise `IReadBlock failed ... TIFFReadEncodedTile() failed`. Threaded
    inference therefore keeps ONE handle per thread; the staging (a Drive->NVMe copy,
    guarded by the cross-runtime lock) still happens once, on the first caller.
    """
    key = config.HS_SOURCE
    if key == HS_SOURCE_NIR:
        # M06: band 4 is the YEAR'S OWN NIR band, read from the ortho itself in
        # tiling/inference — there is no master raster to open or stage. Returning
        # None (not a hillshade) makes any accidental caller take the "no 4th band"
        # branch instead of silently getting LIDAR under an NIR run tag.
        return None
    cache = getattr(_HS_TLS, "ds", None)
    if cache is None:
        cache = _HS_TLS.ds = {}
    if key in cache:
        return cache[key]
    path = HS_PATHS[key]
    if not path.exists():
        print(f"  WARNING: --hs-source {key} raster not found at {path} — "
              f"falling back to RGB-only despite USE_HILLSHADE.")
        return None
    # EVERY READER THREAD ARRIVES HERE AT ONCE on its first tile (core.py::step_inference
    # has INFER_READ_WORKERS of them and stages nothing up front), so this is a same-key
    # fan-in of `stage()` calls from ONE pid. scratchcache serialises those per key —
    # first copies, the rest hit. Before it did, at least two threads copied the 6.4 MB
    # CHM (7 of 8 when reproduced on the dev box; the VM log cannot count them) and
    # each publish unlinked the name a sibling had just been handed
    # (2026-09-09, scratchcache.py module docstring "THE PIN IS PER PID").
    local = _stage_imagery_local(path)          # idempotent; returns the staged copy
    # "remembered for _unstage/teardown" — AND THERE IS NO TEARDOWN. The only other
    # references to _HILLSHADE_DS are its definition above and tiling.py's
    # _hillshade_ds() calls; nothing ever reads it back to release anything. So the
    # staged CHM/hillshade master has been un-swept garbage on every VM, outliving the
    # step that made it with no owner. The scratch cache does not add a release site
    # here — the handle is deliberately held for the life of the process — but the
    # staged master now carries a `ready` sidecar, so for the first time it is
    # EVICTABLE once this pid is gone, instead of sitting there until the runtime dies.
    # It is pinned while we hold it open, which is correct: it is open.
    _HILLSHADE_DS[key] = local
    cache[key] = rasterio.open(local)
    return cache[key]


def close_thread_hillshade():
    """Close this thread's hillshade handle (threaded inference teardown)."""
    cache = getattr(_HS_TLS, "ds", None) or {}
    for ds in cache.values():
        try:
            ds.close()
        except Exception:                                   # noqa: BLE001
            pass
    _HS_TLS.ds = {}


def read_hillshade_chip(dst_crs, dst_transform, h, w):
    """Reproject the hillshade onto an arbitrary target grid → (1,h,w) uint8.
    Out-of-coverage (water / no first-return) reprojects to 0, matching the RGB
    nodata fill. Returns zeros if the hillshade is unavailable."""
    if config.nir_mode():
        # M06 fail-loud: under --hs-source nir the 4th band MUST come from the
        # year's own ortho (tiling.step_tile / core._prep read it directly). If
        # this is reached, a caller was not converted and would have silently
        # written zeros — never let an NIR run carry a blank/LIDAR band 4.
        raise RuntimeError(
            "read_hillshade_chip() called with --hs-source nir: band 4 must be "
            "read from the year's own ortho, not warped from a LIDAR master.")
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
            # Reproject to the CALLER's target_crs, always. The old test was
            # `g.crs.to_epsg() != 3857` — it baked in the assumption that the
            # target is always CROWN_CRS, so a 3857 regions file asked for in a
            # year's native CRS came back UNPROJECTED. tiling.py's negative-site
            # path (the 2026-08-24 region fix) passes target_crs=src.crs, which
            # is EPSG:2285/2926/26910 for every snoh/NAIP year: the 3857 geometry
            # then rasterised entirely outside the tile transform, `inside` was
            # all-zero, and the <0.05 guard dropped EVERY tile — silently zeroing
            # Negative_Parking on 2016/2006s and blocking Edmonds_Heights.
            # to_crs is a no-op when the CRSes already match, so 3857 years (and
            # labels.py's default-target call) are bit-identical to before.
            if g.crs is not None and target_crs is not None:
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
