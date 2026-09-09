"""scratchcache.py — LOCAL_SCRATCH as a keyed cache instead of a scratch pad.

WHAT CHANGED, IN ONE SENTENCE. `common.py::_stage_imagery_local` was already a cache
with a working hit path (`exists() and size == src_size` → return the local copy); every
step then DELETED its payload on the way out, so the hit never fired across steps. This
module adds the journal that makes the hit survive the step, and nothing else.

WHAT IT IS WORTH, MEASURED (`phase4/qc/timing_events.csv`, and it is a PREDICTION until
a real Colab run shows the inference-step `stage <ortho>` event gone for a job whose tile
and inference shared a VM — CLAUDE.md §3.4c):
  • the same 11.5 GB `2017_king_rgb.tif` was staged FOUR times across the pilot and its
    baseline. On the baseline A100 box alone: tile 123.5 s (93.5 MB/s) then inference
    87.1 s (132.6 MB/s) — 87.1 s of that pair is pure repetition;
  • re-staging is 42% of all staged seconds all-time, 53% post-08-30; worst single case
    `2020_coe_rgb.tif` at 1.02 h (Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md §2);
  • `edmonds_canopy_mask_2020.tif` is staged by EVERY tile step: 77 events, 1,318.6 s
    (re-counted off the CSV 2026-09-07, not quoted from a report). Across that mask plus
    the CHM/overlay set (`lidar_snoh_chm`, `lidar_chm2_2016_50cm`, `lidar_chm2005_2m`,
    `add_chm2005`, `add_chm2016`) there are 119 stage events / 2,759.9 s, of which
    SAME-DAY repeats — keeping the LARGEST event per file per day as the unavoidable
    cold copy, dating off the log filename, matching filenames by substring — are 92
    events / 1,496.7 s. That is the part that scales with queue length rather than with
    year count.
    EVERY NUMBER IN THIS BLOCK IS A SNAPSHOT AND IT GROWS: the live campaign appends to
    timing_events.csv, and it moved between the two counts above being taken. Re-derive
    rather than trust it — the filter is `label` beginning `stage ` and naming one of the
    files listed. (The 92 / 1,496.7 figure also RECONCILES a discrepancy left open at
    review: an earlier re-count of the same quantity reported 90 / 1,344.7 and could not
    reproduce the design's 92 / 1,497; the method spelled out above reproduces it.)
    It is an UPPER bound on
    same-VM hits: timing_events.csv carries no VM identity, and at least one counted
    pair is known cross-VM (the pilot's `2017k spd_2017k` tile ran on a 2-vCPU CPU
    runtime and its inference on an A100).
Nothing is bought on a cold VM's first step, across VMs, or across a queue split by
`--only JOB`: `/content` is ephemeral, so the cache lives exactly as long as the runtime.

── THE TWO HAZARDS A CACHE INTRODUCES, AND THE TWO GATES ──────────────────────
Keeping bytes instead of deleting them can delete something a peer is READING, or keep
so much that a non-cache writer hits ENOSPC. So:

  THE PIN. Every reader pins the entry it is using, under the flock, BEFORE validating
  and before opening it. Pins are per (entry, pid); two arms on one VM is a real
  configuration, so both pin the same ortho and neither can evict it. Liveness is
  `phase4seg.names::pid_alive` — never `os.kill` directly (qc/test_queue_verify.py bans
  that by AST, and off POSIX `os.kill` TERMINATES). A wedged (not dead) reader is bounded
  by PIN_MAX_MIN — and so is a wedged WRITER, whose `copying` record would otherwise hold
  both its key and its payload for the life of the runtime (`_copier_alive`).

  THE FLOOR. Eviction is triggered only at admission (`stage`) and at `reserve`, never by
  a timer: an evictor running while nothing is asking for space can only race readers for
  no benefit. THE FLOOR IS THE EVICTION TARGET, NOT THE ADMISSION GATE. Making it the
  gate would mean an 11.5 GB ortho needed ~33 GB free to be staged at all, so on a loaded
  VM the cache would REFUSE where today's `_stage_imagery_local` stages — reintroducing
  the windowed-FUSE pathology P4.3 exists to remove. So: evict toward the floor, then
  admit iff the bytes FIT. That is what makes "never worse than today" true.

  AND AN UNREACHABLE TARGET IS NOT AN INSTRUCTION TO EMPTY THE CACHE. If evicting every
  unpinned entry still could not reach `floor + nbytes*ADMIT_MARGIN`, chasing it deletes
  every hit and buys nothing — the writer either fits anyway or fails either way. So the
  target steps DOWN A LADDER to the largest rung eviction can actually reach:
  `floor + nbytes*ADMIT_MARGIN`, then `max(floor, nbytes)`, then `nbytes` itself — the
  bare minimum that keeps `stage()` from refusing, because dropping to the floor ALONE
  would refuse a stage that would have fitted. And if even `nbytes` is out of reach,
  NOTHING is evicted and the shortfall is logged. A single capped target was not enough:
  when the cap was ALSO out of reach the loop still ran off the end of the candidate
  list and emptied the cache, which is the bug the (u)/(v) pair now pins.
  THE BOUNDARY THIS MOVES, stated because it moves one: `nbytes` here is a deliberate
  over-estimate, so "over-reserving costs a re-stage, never a refusal" now holds only
  while `nbytes` stays inside `free + evictable`. Past that the over-estimate stops
  eviction that a truthful number would have got.

Both gates are shown to FIRE on a known-bad input in qc/test_scratch_cache.py, in
mutation PAIRS ((a)/(b) for the pin, (e)/(f) and (u)/(v) for the floor, and the
crash pair for `_clear_destination`), per CLAUDE.md §3.4c.

  THE PIN IS PER PID, SO ONE PROCESS'S THREADS SHARE ONE — AND THAT LOST A PAYLOAD.
  2026-09-09 22:09Z (phase4_semantic_finetune_inference_2016_2026-09-09T22-09.log,
  wb50_2016_in05): core.py::step_inference stages the CHM lazily from its
  INFER_READ_WORKERS reader threads (`_prep` → common.py::_hillshade_ds), the 6.4 MB
  CHM is under common.py::STAGE_LOCK_MIN_BYTES so the P11.4 lock is a nullcontext, and
  nothing else serialised same-key `stage()` calls inside one process. At least two
  threads passed both `_lookup`s before the first `copying` record landed — the VM log
  cannot count them: same-label ticks collapse to ONE `⏱` line whatever K was, and the
  ENOENT itself needs a second publisher, so K ≥ 2 is what the log PROVES; 7 of 8 is
  what the pre-fix code MEASURED when reproduced unhooked on the dev box
  (qc/test_scratch_cache.py::test_eight_threads_staging_one_source_all_get_the_payload).
  Each such thread ran `_clear_destination` — which refused only FOREIGN pins — copied, and
  each unlinked the canonical name ahead of its own os.replace, deleting the file a
  sibling had just been handed and was opening: `RasterioIOError: …
  lidar_chm2005_2m__cc5263da.tif: No such file or directory` in every worker. The
  process was alone on the VM and reserve() had run before the CHM was staged, so no
  peer and no evictor was involved. Three things close the class:
    • `stage()` holds a PROCESS-LOCAL lock per key for its whole body (`_key_lock`), so
      same-key callers in one process serialise: the first copies, the rest hit. The
      threads that used to see `copying` and answer "wait" → source were silently
      reading the CHM windowed over FUSE for the whole step; they now hit too.
    • `_clear_destination` refuses under ANY live pin, our own pid included. A pin is a
      reader's claim whoever holds it; the pre-clear is reached only after a "miss",
      and every path that turns a `ready` entry into a miss drops our own pin first
      (`_delete_entry`), so an own pin there can only be another part of this process.
    • the publish is a bare atomic os.replace — no unlink ahead of it, so the canonical
      name is never absent, for a peer's open fd or for our own sibling thread.
  Own pins are deliberately NOT honoured by `_lookup`'s stale-entry delete: there the
  own pin is a keep-for-postproc claim (`adopt`), and refusing would turn a stale
  adopted raster into a 60-100 min FUSE read instead of a re-copy.

── NAMESPACE: THE SIDECAR DEFINES OWNERSHIP ───────────────────────────────────
The evictor may delete ONLY a payload this cache wrote a `ready` sidecar for. Everything
else under LOCAL_SCRATCH is un-owned and untouchable — `tiles/`, `bundles/`, `tileout/`,
`bundleout/`, every `common.py::_local_artifact_path` write artifact, and any pre-cache
stump. Deleting an un-owned payload is the one direction that could destroy another
step's in-flight multi-GB write, so it is unreachable by construction.

The payload path does not move: it stays `LOCAL_SCRATCH / common.py::_scratch_name(src)`.
That preserves two live invariants — `postproc.py::_resolve_prob_source`'s "(a) and (b)
resolve to the SAME scratch path by construction", and
`common.py::_unstage_imagery_local`'s `startswith(LOCAL_SCRATCH)` guard.

── THE LOCAL_SCRATCH WRITER CENSUS (MUST-FIX 3), COVERED AND NOT ──────────────
`reserve()` is only as good as its call sites, and an uninstrumented large writer
competing with a full cache is the genuinely NEW failure this design creates. Every
writer into LOCAL_SCRATCH, named:

  COVERED by reserve()
    core.py::step_inference   the 2.4-6.7 GB probability raster (`prob_out`), sized from
                              the previous raster's own bytes or PROB_RASTER_BYTES_ASSUMED
                              — never from the uncompressed grid, see that tunable
    staging.py::_stage_from_bundle   the tile tar plus the tree it extracts
    postproc.py::_resolve_prob_source   BOTH branches. Case (b) reserves its own copy and
                              its existing STAGE_FREE_MARGIN pre-check still decides;
                              case (a) inherits a copy it does not have to make, and
                              reserves the same margin's SLACK for the mask and gpkg it
                              is about to write beside it. Case (a) is the branch the
                              queue takes now that inference adopts the raster instead of
                              unlinking it, and until that reservation it was the one
                              covered writer that reached step_postproc having run no
                              evictor at all.

  NOT COVERED, stated rather than hidden
    ckpt.py::_save_ckpt_state  writes `sem_best_*.pt` through _local_artifact_path
                              (371 MB after the checkpoint diet). ckpt.py is outside
                              this change's file set; the floor's absolute term is what
                              stands in for it.
    tiling.py                 `tileout/{label}/` — the per-year tile write-out, one tile
                              file at a time, 0.2-0.7 GB per set.
    staging.py                `bundleout/` — the write-side bundle tar.
    postproc.py::step_postproc  the mask GeoTIFF and the gpkg GeoPackage, written to
                              LOCAL_SCRATCH while the probability raster is still open.
                              Not reserved AT the write; what stands in for them is
                              STAGE_FREE_MARGIN's 0.3 slack, which _resolve_prob_source
                              now reserves on BOTH of its branches before returning.
    core.py::step_evaluate    two small CSVs (`_sup_local`, `_eval_local`).
The floor is sized to cover one ortho copy plus one concurrent prob-raster write with the
cache full; it is ASSUMED, not measured, exactly as postproc.py::STAGE_FREE_MARGIN says
of its own 0.3.

── WHAT IS NOT HERE, DELIBERATELY ─────────────────────────────────────────────
Nothing is appended to `config.py`: its constants feed `_tile_signature`, so one more
would force a ~20-min re-tile of every year. The tunables below are module attributes,
exactly as `common.py::STAGE_LOCK_MIN_BYTES` and its siblings live in common.py.

No third copy of the aside-rename. `queue_ledger.py::_replace_absent` and
`common.py::_publish_replace` are near-twins of one pattern that has already been bitten
by drift (c5dc91c), and `_replace_absent` cannot be reused here anyway — it calls `_q()`,
which resolves the queue module. So this file does NOT reproduce that pattern: a cache
payload has no previous-good artifact to preserve (losing one is a MISS, not data loss),
so the destination is simply made absent under the flock and a plain `os.replace`
publishes. See `_publish_payload`.

`sha256` is computed at admission only, never on a hit, and only when the source carries
a hash sidecar. The only producer of that pattern in the repo today is the tile bundle's
`tar_sha256` (staging.py); no ortho on Drive carries one, so the branch is inert. A hit
stays a stat, which is what keeps the queue's step-timeout budgets untouched. And, as
`postproc.py::_resolve_prob_source` already says of itself: a size (or mtime) check is
NOT a content check — it catches a short, differently-sized or re-uploaded file, never a
same-length same-mtime substitution.

Colab-only in effect: `_stage_imagery_local` still returns early for anything not under
`/content/drive`, so on Windows QC nothing here is reached live. The flock is a no-op off
POSIX (precedent: staging.py::_extract_lock) — a hypothetical multi-process Windows use
would be unprotected, the same limitation that helper already carries.
"""
import contextlib
import hashlib
import json
import os
import secrets
import shutil
import socket
import threading
import time
from pathlib import Path

from phase4seg import config
from phase4seg import names

# ── Tunables (module attributes; NOTHING goes in config.py) ───────────────────
FLOOR_ABS = 20 << 30
"""Free bytes the evictor aims to leave. ASSUMED, NOT MEASURED — the same disclosure
postproc.py::STAGE_FREE_MARGIN carries about its 0.3. Sized against what IS measured:
the largest ortho in play is 11.5 GB (2017_king_rgb.tif, timing_events.csv), probability
rasters run 2.4-6.7 GB, and hw_t1gpuF.csv shows an ~87 GB runtime already down to 6.0 GB
free under today's delete-everything behaviour (Reports §2). So the floor must cover one
ortho copy and one concurrent prob-raster write with the cache full."""

FLOOR_FRAC = 0.10
"""…or this fraction of the device, whichever is larger. ASSUMED, NOT MEASURED."""

ADMIT_MARGIN = 1.15
"""Slack on the requested bytes when computing the eviction TARGET. ASSUMED. It is
deliberately not part of the admission test (see the floor note in the module docstring):
over-reserving costs a re-stage, never a refusal — WHILE the request stays inside
`free + evictable`. Past that, `_evict_to_target`'s ladder bottoms out and evicts
nothing, so an over-estimate can withhold eviction a truthful number would have got."""

PIN_MAX_MIN = 960
"""A pin older than this is stale however alive its pid looks.

DERIVED: 2 x max(phase4_train_queue.py::STEP_TIMEOUT_MIN) = 2 x 480 (inference). It is a
restatement, so qc/test_scratch_cache.py::test_pin_max_min_is_derived_from_the_queue_budget
asserts it against the queue's own table rather than trusting this comment. The engine
cannot import the queue to read it live — queue_ledger.py::_q explains why (a bare import
EXECUTES the file a second time under a second name).

WHY 2x AND NOT 1x: pipeline/phase4_semantic_finetune.py preserves the `%run --args` path,
and a hand-run step carries NO queue timeout at all, so the bound has to sit above any
queue-legal reader rather than at it. pid liveness is exact within one VM and does the
real work; this only bounds a WEDGED (not dead) reader, which liveness cannot see.

IT BOUNDS THE WRITER SIDE TOO. A `copying` record whose pid is wedged rather than dead
holds its key AND its payload for the life of the runtime: `_lookup` answers "wait"
forever, `sweep` skips it, and `_evict_to_target` takes only `ready` candidates, so the
bytes can never be freed either. `_copier_alive` applies this same bound to `ts_start`."""

PROB_RASTER_BYTES_ASSUMED = 7 << 30
"""What core.py::step_inference reserves for the probability raster when it cannot stat
a previous one. ASSUMED, NOT MEASURED — the same disclosure FLOOR_ABS carries.

It replaces `img_h * img_w`, which was the uncompressed grid and therefore NOT the file:
joining the `copy edmonds_canopy_prob_*.tif` rows of phase4/qc/timing_events.csv (bytes)
against phase4/qc/imagery_geometry.csv (width x height) gives a compressed raster
2.4-25.2x SMALLER than its grid across the 24 years that join — re-derived 2026-09-07
taking the LARGEST raster per year, which is the full-city case; per-TAG the spread runs
to 48.5x, because an AOI or SAMPLE run writes a mostly-nodata raster on the same grid.
The exact pair this constant is sized against: 31.5e9 grid bytes (148736 x 211968)
against the 6.72 GB file for 2017_citywide_rgb, the largest measured. That request put
the eviction
target above anything an ~87 GB runtime could reach with the ortho pinned, so every
inference step emptied the cache and destroyed the cross-year hits the change exists to
buy. This value sits just above that measured maximum; over-reserving costs another step
a re-stage, never correctness — and, since `_evict_to_target`'s ladder, an over-estimate
big enough to leave `free + evictable` behind withholds eviction instead of forcing it,
which is one more reason to keep this sized against a measured raster."""

MTIME_TOL_SEC = 1.0
"""Tolerance on the source-mtime comparison, for filesystem timestamp granularity. A
mismatch costs a re-copy, never correctness."""

CACHE_DIR_NAME = ".cache"
PIN_DIR_NAME = "pins"

_DEFAULT_ROOT_OVERRIDE = None
"""Test-only injection point for the default root, so the site-level tests can drive
`common.py`'s shim without a `/content` directory. Production always resolves
config.LOCAL_SCRATCH."""


# ── Paths and identity ────────────────────────────────────────────────────────

def cache_root(root=None):
    """The cache root. Injectable so no cache function ever tests for a mount.

    The Drive-prefix test stays exactly where it is today — in the
    `common.py::_stage_imagery_local` shim — rather than migrating in here, so this
    module is drivable from a tmp_path on Windows with no `os.name` branch other than
    the flock's.
    """
    if root is not None:
        return Path(root)
    if _DEFAULT_ROOT_OVERRIDE is not None:
        return Path(_DEFAULT_ROOT_OVERRIDE)
    return Path(config.LOCAL_SCRATCH)


def _key(src):
    """The entry key: the 8-hex sha256-of-FULL-source-path.

    This is the SAME rule common.py::_scratch_name already applies to build the payload
    basename — D18 fixed basename aliasing there for exactly this reason (different
    years' native/ files routinely share a basename). Recomputing it here rather than
    parsing it back out of the name keeps the parse from breaking on a stem containing
    `__`; the two are pinned together by
    qc/test_scratch_cache.py::test_the_key_is_the_hash_common_already_puts_in_the_payload_name.

    8 hex is 2^32, small enough that a collision must be LOUD rather than silent — hence
    the full source path in the sidecar, compared on every hit.
    """
    return hashlib.sha256(str(Path(src)).encode("utf-8")).hexdigest()[:8]


def _payload_path(src, root=None):
    """Where the bytes live. UNCHANGED from today by design (module docstring)."""
    from phase4seg.common import _scratch_name      # lazy: common imports THIS module
    return cache_root(root) / _scratch_name(Path(src))


def _meta_dir(root=None):
    return cache_root(root) / CACHE_DIR_NAME


def _pin_dir(root=None):
    return _meta_dir(root) / PIN_DIR_NAME


def _sidecar_path(key, root=None):
    return _meta_dir(root) / f"{key}.json"


# ── The flock (staging.py::_extract_lock precedent) ───────────────────────────

@contextlib.contextmanager
def _cache_lock(root=None):
    """Serialise enumerate/pin/delete between same-VM processes. Held only across
    metadata work — NEVER across a multi-GB copy. flock on posix, a no-op elsewhere."""
    if os.name != "posix":
        yield
        return
    import fcntl
    d = _meta_dir(root)
    try:
        d.mkdir(parents=True, exist_ok=True)
        fh = open(d / "cache.lock", "w")
    except OSError:
        yield                                   # unlockable: proceed, never block a step
        return
    try:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
    finally:
        fh.close()


# ── The per-key lock (one process, many threads) ──────────────────────────────

_KEY_LOCKS = {}
_KEY_LOCKS_GUARD = threading.Lock()


def _key_lock(key):
    """The process-local lock for one entry key. See the module docstring's
    "THE PIN IS PER PID" paragraph: every other guard here is keyed by pid, so the
    reader threads of one process are invisible to each other, and `stage()` holds
    this for its whole body so same-key callers serialise — first copies, rest hit.
    A plain Lock, not an RLock: nothing in `stage()` re-enters it for the same key
    (the P11.4 lock is a separate mechanism, and it is entered INSIDE this one)."""
    with _KEY_LOCKS_GUARD:
        lk = _KEY_LOCKS.get(key)
        if lk is None:
            lk = _KEY_LOCKS[key] = threading.Lock()
        return lk


# ── The journal ───────────────────────────────────────────────────────────────

def _read_sidecar(key, root=None):
    """The entry record, or None when it is absent OR unparseable. A torn or truncated
    object reads as "no entry" — a miss, which costs a copy, never a wrong answer."""
    try:
        return json.loads(_sidecar_path(key, root).read_text(encoding="utf-8"))
    except Exception:                                        # noqa: BLE001
        return None


def _write_sidecar(key, root, payload):
    """Publish an entry record temp + os.replace, so a peer reading it from another
    process never sees half an object — the pattern
    queue_ledger.py::publish_phase_marker uses for its marker."""
    d = _meta_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    p = _sidecar_path(key, root)
    tmp = p.with_name(p.name + f".tmp.{os.getpid()}.{secrets.token_hex(3)}")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, p)
    return p


def _iter_entries(root=None):
    """(key, sidecar) for every record this cache wrote. One scandir of a small dir."""
    d = _meta_dir(root)
    try:
        entries = list(os.scandir(d))
    except OSError:
        return
    for e in entries:
        if not e.name.endswith(".json") or not e.is_file():
            continue
        sc = _read_sidecar(e.name[:-5], root)
        if isinstance(sc, dict) and sc.get("key"):
            yield sc["key"], sc


def _entry_by_payload(path, root=None):
    """The record owning `path`, or None. The sidecar defines ownership, so a payload
    with no record is un-owned and this returns None for it."""
    name = Path(path).name
    for _k, sc in _iter_entries(root):
        if sc.get("payload") == name:
            return sc
    return None


# ── Pins ──────────────────────────────────────────────────────────────────────

def _pin_path(key, pid, root=None):
    return _pin_dir(root) / f"{key}.{pid}.pin"


def _write_pin(key, root=None):
    d = _pin_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    p = _pin_path(key, os.getpid(), root)
    p.write_text(json.dumps({"pid": os.getpid(), "host": socket.gethostname(),
                             "ts": time.time()}), encoding="utf-8")
    return p


def _live_pins(key, root=None):
    """Pin files for `key` whose holder is still a plausible reader.

    LOCAL_SCRATCH is per-VM (`/content` is ephemeral), so every pin is a local pid and
    `names.pid_alive` is exact for it. A dead pid's pin is absent; so is one older than
    PIN_MAX_MIN. Pid REUSE can make a dead holder look live — the harm is bounded to an
    entry held longer than it should be, i.e. space, never correctness. Stated, not
    hidden."""
    out = []
    try:
        cands = list(_pin_dir(root).glob(f"{key}.*.pin"))
    except OSError:
        return out
    now = time.time()
    for p in cands:
        try:
            pid = int(p.name.split(".")[-2])
        except (ValueError, IndexError):
            continue
        try:
            age_min = (now - p.stat().st_mtime) / 60.0
        except OSError:
            continue
        if age_min > PIN_MAX_MIN or not names.pid_alive(pid):
            with contextlib.suppress(OSError):
                p.unlink()
            continue
        out.append((pid, p))
    return out


def _drop_record(key, root=None):
    """Remove the RECORD and our pin, leaving any payload alone.

    The cleanup for a copy that never landed. `_delete_entry` would be wrong here: it
    unlinks the payload, and on this path the bytes at the payload name are not ours —
    the copy went to `.part` — so they are either absent or an un-owned file this
    process has no claim on, which the namespace rule says never to delete.
    """
    with contextlib.suppress(OSError):
        _sidecar_path(key, root).unlink()
    _drop_our_pin(key, root)


def _drop_our_pin(key, root=None):
    """Remove only a pin naming OUR pid — the discipline
    queue_ledger.py::publish_phase_marker already applies to its own marker."""
    with contextlib.suppress(OSError):
        _pin_path(key, os.getpid(), root).unlink()


# ── Entry lifecycle ───────────────────────────────────────────────────────────

def _copier_alive(sc):
    """Is the process that wrote this `copying` record still a plausible copier?

    THE ASYMMETRY THIS CLOSES. A pin has PIN_MAX_MIN; a `copying` record had nothing, so
    a WEDGED (not dead) writer held its key AND its payload for the life of the runtime:
    `_lookup` answers "wait" while the pid looks alive, `sweep` skips the record, and
    `_evict_to_target` takes only `ready` candidates — so the entry could neither be
    served, re-copied, nor freed. `ts_start` bounds it with the same number, and for the
    same reason (see PIN_MAX_MIN: no queue-legal step outlives 2x its own timeout).

    A MISSING OR UNPARSEABLE PID READS AS DEAD HERE, which is the opposite of
    `names.pid_alive`'s posture — it returns True for anything it cannot interpret. That
    fail-OPEN is right for every other caller ("assume the peer is alive" keeps the
    protection) and wrong for exactly this one, where it means "never resolve".
    """
    try:
        pid = int(sc.get("pid"))
    except (TypeError, ValueError):
        return False
    try:
        started = float(sc.get("ts_start"))
    except (TypeError, ValueError):
        return False                      # undatable: resolve it rather than wait forever
    if (time.time() - started) / 60.0 > PIN_MAX_MIN:
        return False
    return bool(names.pid_alive(pid))


def _delete_entry(sc, root=None):
    """Payload first, then sidecar. A sidecar without a payload is invalid and is
    re-swept; a payload without a sidecar is un-owned and untouchable — so this is the
    safe direction, and never the reverse."""
    payload = cache_root(root) / str(sc.get("payload") or "")
    if sc.get("payload"):
        with contextlib.suppress(OSError):
            payload.unlink()
    with contextlib.suppress(OSError):
        _sidecar_path(sc["key"], root).unlink()
    _drop_our_pin(sc["key"], root)


def _src_stat(src):
    """(size, mtime) for a source, or None when it is UNVERIFIABLE.

    Fails CLOSED, the posture common.py::_staging_lock_for takes when its own stat
    fails: any OSError, and a 0-byte answer (a wedged mount replying, not a match),
    means we do not trust the cache for this source at all."""
    try:
        st = Path(src).stat()
    except OSError:
        return None
    if st.st_size <= 0:
        return None
    return st


def _matches(sc, src, st):
    """Does this `ready` record describe the source in front of us?

    Size AND source mtime (the mtime is GRAFT 3's narrowing: size-only trust used to die
    with the step and now persists across steps, so one extra stat against an 87-309 s
    copy is worth it). It is NOT a content check — the same words
    postproc.py::_resolve_prob_source uses about itself — but a re-uploaded ortho of
    identical length is exactly the substitution size alone cannot see.
    """
    if str(sc.get("src")) != str(src):
        return False
    if int(sc.get("bytes") or -1) != st.st_size:
        return False
    if int(sc.get("src_size") or -1) != st.st_size:
        return False
    try:
        return abs(float(sc.get("src_mtime")) - st.st_mtime) <= MTIME_TOL_SEC
    except (TypeError, ValueError):
        return False


def _lookup(key, src, st, root):
    """→ ("hit", payload) | ("miss", None) | ("wait", None) | ("degrade", None).

    Call under the flock. A HIT PINS FIRST, then validates, then the caller opens:
    pinning after validation would leave a hit→evict→open window that ENOENTs under a
    concurrent `stage()`.

    "wait" and "degrade" are deliberately NOT the same answer. "wait" means a peer on
    this VM is mid-copy of this exact file, and the right move is to fall through into
    the P11.4 lock — for a >= STAGE_LOCK_MIN_BYTES ortho that is what today does, and
    the waiter then hits NVMe for its whole step instead of reading 11.5 GB windowed
    over FUSE. Only after the lock, if the peer is STILL copying, do we take the source
    path. "degrade" means the entry is unusable and no amount of waiting changes it.
    """
    sc = _read_sidecar(key, root)
    if not isinstance(sc, dict):
        return "miss", None
    if str(sc.get("src")) != str(src):
        print(f"  ! scratch cache KEY COLLISION on {key}: the entry names "
              f"{sc.get('src')!r}, not {str(src)!r} — refusing to serve it", flush=True)
        return "degrade", None
    if sc.get("state") != "ready":
        # `copying` with a live pid is a peer mid-copy: do not touch it, do not serve it.
        # A wedged one is bounded by _copier_alive, or it would answer "wait" forever.
        if _copier_alive(sc):
            return "wait", None
        return "miss", None                     # dead-pid `copying` is resolved by sweep
    payload = cache_root(root) / str(sc.get("payload") or "")
    _write_pin(key, root)
    try:
        ok = payload.exists() and payload.stat().st_size == st.st_size and _matches(sc, src, st)
    except OSError:
        ok = False
    if not ok:
        _drop_our_pin(key, root)
        # NEVER DELETE UNDER A READER — the same rule invalidate() enforces at its own
        # door. A stale-looking entry that another pid has open is still that pid's open
        # file; on POSIX its fd survives an unlink, but postproc opens the probability
        # raster TWICE (header, then the windowed loop), so the second open would ENOENT.
        # Leave it and take the source path.
        if [pid for pid, _f in _live_pins(key, root) if pid != os.getpid()]:
            return "degrade", None
        _delete_entry(sc, root)
        return "miss", None
    sc["last_use"] = time.time()
    _write_sidecar(key, root, sc)
    return "hit", payload


# ── Eviction ──────────────────────────────────────────────────────────────────

def _floor_bytes(root):
    du = shutil.disk_usage(cache_root(root))
    return max(FLOOR_ABS, int(FLOOR_FRAC * du.total))


def _evict_to_target(nbytes, root, keep_key=None):
    """Free space toward `floor + nbytes*ADMIT_MARGIN`, coldest `last_use` first.

    Stops the INSTANT the target holds. An evictor that kept going would empty a cache
    that had already made room, turning every later step back into a miss.

    AND IT NEVER CHASES A TARGET IT CANNOT REACH — WHICH THE OLD SINGLE CAP DID NOT
    GUARANTEE. That cap dropped an out-of-reach target to `max(floor, nbytes)` and then
    ran the loop anyway, so whenever THAT was out of reach too (250 free, 400 evictable,
    a 1000-byte request against a 2000-byte floor) the loop ran off the end of the
    candidate list and emptied the cache to reach nothing — the exact outcome the cap
    was written to prevent. Pinned by qc/test_scratch_cache.py's (u)/(v) pair.

    So the target is now the LARGEST OF THREE RUNGS THAT EVICTION CAN ACTUALLY REACH,
    each one a weaker version of the same want:

      floor + nbytes*ADMIT_MARGIN   the ideal: the floor, plus slack over the request
      max(floor, nbytes)            the floor, or the request if it is bigger
      nbytes                        the bare minimum that keeps `stage()` from refusing

    and if `free + evictable` cannot even reach the last of them, NOTHING is evicted and
    the shortfall is printed. Deleting there buys nothing — the writer fits without those
    bytes or fails with them — while costing every cross-year hit the cache exists for.

    THE ONE PLACE THAT BOUNDARY BITES, stated rather than hidden. `nbytes` in this
    codebase is a deliberate OVER-estimate (PROB_RASTER_BYTES_ASSUMED is sized above the
    largest raster ever measured; staging.py::_stage_from_bundle asks for 2x the tar).
    When the over-estimate is what pushes `nbytes` out of reach, a write that would have
    fitted after eviction now runs against an un-evicted cache. That is the price of not
    emptying the cache on every over-reserve, and it is why the reservation callers size
    themselves to something measured rather than to a grid (core.py::step_inference).

    `keep_key` is a STRUCTURAL guarantee, not a fix for a live bug: no candidate is ever
    the entry the caller is about to use. Every call site today protects that entry with
    a pin instead — `_lookup` pins before it validates, postproc.py::_resolve_prob_source
    pins before it reserves — and the one window a pin does not cover is a peer
    publishing `ready` for this key between our `_lookup` miss and this call, whose fresh
    copy we would otherwise delete and immediately re-make.
    """
    try:
        floor = _floor_bytes(root)
        need = max(0, int(nbytes))
        want = floor + int(need * ADMIT_MARGIN)
        if shutil.disk_usage(cache_root(root)).free >= want:
            return
        with _cache_lock(root):
            cands = [sc for _k, sc in _iter_entries(root)
                     if sc.get("state") == "ready" and sc.get("key") != keep_key
                     and not _live_pins(sc["key"], root)]
            cands.sort(key=lambda s: (float(s.get("last_use") or 0.0),
                                      float(s.get("ts_ready") or 0.0)))
            free_now = shutil.disk_usage(cache_root(root)).free
            evictable = sum(max(0, int(s.get("bytes") or 0)) for s in cands)
            reach = free_now + evictable
            target = next((t for t in (want, max(floor, need), need) if reach >= t), None)
            if target is None:
                print(f"  (scratch cache: {need / 1e9:.1f} GB cannot be freed here — "
                      f"{(need - reach) / 1e9:.1f} GB short of it even after evicting "
                      f"every unpinned entry, so keeping all {len(cands)})", flush=True)
                return
            if free_now >= target:
                return                        # the reachable rung already holds
            if target < want:
                print(f"  (scratch cache: {want / 1e9:.1f} GB is out of reach — "
                      f"evicting toward {target / 1e9:.1f} GB instead)", flush=True)
            for sc in cands:
                if shutil.disk_usage(cache_root(root)).free >= target:
                    return
                _delete_entry(sc, root)
    except Exception as e:                                   # noqa: BLE001
        print(f"  (scratch cache: eviction skipped, {e!r})", flush=True)


# ── Public API ────────────────────────────────────────────────────────────────

def reserve(nbytes, root=None):
    """Make room for a NON-CACHE writer of `nbytes`, then say whether it fits.

    Today the big writers into LOCAL_SCRATCH find room only BECAUSE every step deleted
    its ortho on exit. This replaces that accident with a contract. Callers do not gate
    on the answer — today's code checks nothing at all, and refusing where today wrote
    would be a regression — so this is called for its eviction, and its return value is
    advisory. The writers it does and does not cover are enumerated in the module
    docstring (MUST-FIX 3).

    IT CREATES NOTHING. `stage()` mkdirs because it is about to write a payload; this is
    a make-room call, and a root that does not exist holds nothing to evict and nothing
    yet written into it. The mkdir this used to do reached out of the tests entirely: the
    default root is config.LOCAL_SCRATCH = `/content/phase4_scratch`, which on Windows is
    DRIVE-RELATIVE, so the unpatched staging.py::_stage_from_bundle call under
    qc/test_tile_bundle.py created `D:\\content\\phase4_scratch` on the dev box and ran
    the evictor's scandir against the real drive. qc/conftest.py does not catch that —
    it is not a lake write — and an evictor enumerating a production-named directory
    from a test is the shape that eventually deletes something.
    """
    try:
        r = cache_root(root)
        if not r.exists():
            return True
        _evict_to_target(nbytes, r)
        return shutil.disk_usage(r).free >= nbytes
    except Exception as e:                                   # noqa: BLE001
        print(f"  (scratch cache: reserve skipped, {e!r})", flush=True)
        return True


def sweep(root=None):
    """Crash-state cleanup: `.part` orphans by PID, and `copying` entries whose writer is
    gone — dead by pid, or wedged past PIN_MAX_MIN (`_copier_alive`).

    The pid is IN the `.part` filename, so a VM death mid-copy does not have to wait out
    common.py::_sweep_part_orphans' 24 h age gate — which is still called afterwards, for
    the same names, to catch anything this cannot attribute.

    THE ONE GAP, DECIDED EXPLICITLY. A crash between the rename and the sidecar's flip to
    `ready` leaves a COMPLETE payload under `copying`. Promote it iff its size matches
    the source size the record captured; otherwise delete it. Nothing is left to chance
    in that window — and an interrupted copy is precisely the multi-GB stump
    postproc.py::_resolve_prob_source documents at length.

    THAT PROMOTION IS ONLY SOUND BECAUSE OF `_clear_destination`, and the dependency is
    one-way and load-bearing: "size matches" identifies OUR published bytes only while
    the canonical name is known to have been empty when the record was written. Without
    the pre-clear it promotes whatever happened to be sitting there at the right length
    — see that function for the wrong-content hit it produced.
    """
    try:
        r = cache_root(root)
        for p in list(r.glob("*.part.*")):
            try:
                pid = int(p.name.rsplit(".part.", 1)[1].split(".")[0])
            except (ValueError, IndexError):
                continue
            if not names.pid_alive(pid):
                with contextlib.suppress(OSError):
                    p.unlink()
        with _cache_lock(r):
            for key, sc in list(_iter_entries(r)):
                payload = r / str(sc.get("payload") or "")
                if sc.get("state") == "ready":
                    if not payload.exists():
                        _delete_entry(sc, r)        # a record whose bytes are gone
                    continue
                if _copier_alive(sc):
                    continue                        # a peer is mid-copy: leave it alone
                try:
                    complete = (payload.exists()
                                and payload.stat().st_size == int(sc.get("src_size") or -1))
                except OSError:
                    complete = False
                if complete:
                    sc["state"] = "ready"
                    sc["bytes"] = payload.stat().st_size
                    sc.setdefault("ts_ready", time.time())
                    sc["last_use"] = time.time()
                    _write_sidecar(key, r, sc)
                else:
                    _delete_entry(sc, r)
        from phase4seg.common import _sweep_part_orphans
        _sweep_part_orphans(r)
    except Exception as e:                                   # noqa: BLE001
        print(f"  (scratch cache: sweep skipped, {e!r})", flush=True)


def pin(path, root=None):
    """Pin an EXISTING ready entry at `path` without copying anything. → bool.

    This exists for postproc.py::_resolve_prob_source case (a), which validates an
    inherited copy by size and then returns it WITHOUT going through `stage()`. Under
    the queue that copy is the adopted probability raster — `ready` and unpinned — and
    postproc then holds it open for 60-100 min across two separate `rasterio.open` calls.
    A concurrent `stage()`/`reserve()` from the other arm on the VM could evict it
    between them. Pinning closes that.
    """
    try:
        p = Path(path)
        with _cache_lock(root):
            sc = _entry_by_payload(p, root)
            if not sc or sc.get("state") != "ready" or not p.exists():
                return False
            _write_pin(sc["key"], root)
            sc["last_use"] = time.time()
            _write_sidecar(sc["key"], root, sc)
            return True
    except Exception:                                        # noqa: BLE001
        return False


def release(path, root=None):
    """Stop using `path`. Drops OUR pin; the bytes stay, evictable.

    A payload with NO sidecar is not a cache entry — nobody would ever free it — so for
    that case this keeps the historical `_unstage_imagery_local` behaviour and unlinks
    it. Only OWNED entries survive a release.
    """
    try:
        p = Path(path)
        r = cache_root(root)
        with _cache_lock(r):
            sc = _entry_by_payload(p, r)
            if sc is not None:
                _drop_our_pin(sc["key"], r)
                return
        if p.exists() and str(p.resolve()).startswith(str(r.resolve())):
            with contextlib.suppress(OSError):
                p.unlink()
    except Exception:                                        # noqa: BLE001
        pass


def invalidate(path, root=None):
    """Delete `path` and its record. → True if it is gone, False if a reader holds it.

    THE ONE CALL THAT STILL DELETES, and it is called only where deletion is
    CORRECTNESS rather than space management: postproc.py::_resolve_prob_source's
    short/stale discards, and core.py::step_inference's own destination before it opens
    it for write. A refusal (a live foreign pin) leaves the caller on today's degrade
    path — read the source — rather than deleting under an open fd.
    """
    try:
        p = Path(path)
        r = cache_root(root)
        with _cache_lock(r):
            sc = _entry_by_payload(p, r)
            if sc is not None:
                foreign = [pid for pid, _f in _live_pins(sc["key"], r)
                           if pid != os.getpid()]
                if foreign:
                    print(f"  (scratch cache: {p.name} is pinned by pid {foreign[0]} — "
                          f"not discarding it)", flush=True)
                    return False
                _delete_entry(sc, r)
                return True
        if p.exists():
            if not str(p.resolve()).startswith(str(r.resolve())):
                return False
            with contextlib.suppress(OSError):
                p.unlink()
        return True
    except Exception:                                        # noqa: BLE001
        return False


def adopt(path, src, root=None):
    """Register a payload ALREADY IN PLACE as a cache entry for `src`. → bool.

    No bytes move. This is how the probability raster stops being re-staged:
    core.py::step_inference writes it via `_local_artifact_path`, so it has no sidecar,
    and turning its unlink into a bare release would re-open the 2.4-6.7 GB leak P4.3's
    `finally` exists to bound. Called immediately after `_copy_to_drive` returns — the
    verified write has just proved size and sha256 against Drive — it writes a `ready`
    record for a file that is already there.

    WHY IT PAYS. `POSTPROC_FOLLOWS` is set in exactly one place (cli.py), on the
    single-invocation path. Under the queue, `phase4_train_queue.py::run_step` launches
    ONE PROCESS PER `--step`, so it is False, inference unlinked the raster, and the
    separate postproc process re-staged the whole thing back down through
    `_resolve_prob_source` case (b). With adoption that becomes a hit.
    """
    try:
        p, s = Path(path), Path(src)
        if p != _payload_path(s, root):
            return False                        # only the canonical name is adoptable
        st = _src_stat(s)
        if st is None or not p.exists() or p.stat().st_size != st.st_size:
            return False                        # an entry the evictor owns must validate
        key = _key(s)
        with _cache_lock(root):
            _write_sidecar(key, root, {
                "state": "ready", "key": key, "src": str(s), "src_size": st.st_size,
                "src_mtime": st.st_mtime, "payload": p.name, "bytes": p.stat().st_size,
                "pid": os.getpid(), "host": socket.gethostname(),
                "ts_start": time.time(), "ts_ready": time.time(),
                "last_use": time.time(), "adopted": True})
            _write_pin(key, root)
        return True
    except Exception as e:                                   # noqa: BLE001
        print(f"  (scratch cache: adopt skipped, {e!r})", flush=True)
        return False


def _clear_destination(key, payload, root):
    """Make the canonical payload name ABSENT before anything is journalled. → bool.

    THE HOLE THIS CLOSES, AND WHY `.part` + os.replace DOES NOT CLOSE IT ON ITS OWN.
    The publish is already atomic (`_publish_payload`), so a killed copy can no longer
    leave a truncated file at the name a later reader trusts. But `sweep`'s crash-state
    rule reads the CANONICAL name and promotes whatever sits there to `ready` iff its
    size equals the record's `src_size` — and it cannot tell our own os.replace result
    from a file that was ALREADY at that name. A pre-cache stump, a
    common.py::_local_artifact_path write artifact, an entry whose sidecar was lost:
    journal `copying` over the top of one of those, die before `ready`, and the next
    sweep promotes somebody else's bytes under our source's key. `_lookup` then serves
    them as a hit whose source, size and mtime all check out and whose CONTENT is wrong.
    Size is not a content check — the same words postproc.py::_resolve_prob_source uses
    about itself — and there it was being asked to be one.

    Clearing the name first makes that promotion sound BY CONSTRUCTION: afterwards a
    complete-sized file under a `copying` record can only have arrived through
    `_publish_payload`. qc/test_scratch_cache.py
    ::test_a_stale_payload_under_a_crashed_copy_is_never_served drives the whole
    sequence — right-sized wrong-content payload, a death mid-copy, a fresh process —
    and without this it is served as a hit.

    IT RUNS BEFORE `_evict_to_target`, deliberately. Anything still at this name is
    UN-OWNED (an owned entry for this key is already gone — `_lookup`'s mismatch path
    deletes it, or refuses and degrades), so the evictor's `evictable` sum does not
    count it: clearing first hands the evictor the space the stump was holding instead
    of making it delete a real entry to find the same bytes.

    NEVER UNDER A PINNED READER — OURS INCLUDED. A live pin on this key means somebody
    has it open, so this refuses and `stage()` degrades to the source rather than
    unlinking under an open fd. It used to exempt our own pid, and that exemption is
    how one inference process deleted its own CHM out from under its reader threads
    (module docstring, "THE PIN IS PER PID"): a pin is a reader's claim whoever holds
    it, and since every path from `ready` to "miss" drops our own pin first
    (`_delete_entry`), an own pin here can only be another thread of this process.

    THE EXPOSURE THAT LEAVES, STATED RATHER THAN HIDDEN: a pin needs a sidecar, so an
    UN-OWNED reader has none. postproc.py::_resolve_prob_source case (a) is exactly that
    when it inherits a sidecar-less raster — its `_pin_staged` is a no-op there — and it
    holds the file open across two separate `rasterio.open` calls. Unlinking early moves
    that second open's ENOENT window from the microseconds of the publish rename to the
    whole duration of the copy. It is still narrower than it looks (a same-VM peer
    staging the very file postproc is reading is a rerun of one year+tag), and it buys
    the wrong-content hit above, which is a correctness failure rather than a slow one —
    but it IS a widening, and it is the reason case (a) pins whenever it can.
    """
    with _cache_lock(root):
        if _live_pins(key, root):
            print(f"  (scratch cache: {payload.name} is held by a live reader — "
                  f"not re-staging over it)", flush=True)
            return False
        with contextlib.suppress(OSError):
            payload.unlink()
        return not payload.exists()


def _publish_payload(part, payload):
    """`os.replace(part, payload)` — atomic, and NOT preceded by an unlink.

    The name was made absent by `_clear_destination` before the journal (that is what
    keeps `sweep`'s size-based promotion sound). Anything at it NOW was published by a
    peer while we copied, and os.replace goes over the top of it atomically: the name
    resolves to the old bytes or to ours, never to nothing, and a peer's open fd keeps
    its inode on POSIX. The unlink that used to sit ahead of this call existed for that
    same peer case and was redundant with the rename — while being exactly the window
    in which one process's sibling thread found the CHM gone (module docstring, "THE
    PIN IS PER PID"). Off POSIX a replace over a file another process holds open fails
    with PermissionError, and the re-probe below answers True for the peer's copy, the
    same outcome the suppressed unlink produced before.

    NOT a third copy of common.py::_publish_replace / queue_ledger.py::_replace_absent.
    Those exist to keep a PREVIOUS GOOD ARTIFACT recoverable when a publish fails, which
    is why they carry the aside rename and its restore. A cache payload has no such
    thing: losing one is a miss, and the next caller copies it again. So there is nothing
    to set aside, and the only handling needed is a re-probe on OSError — which is what
    c5dc91c established (do not trust the exception's type, ask the filesystem).

    → True when `payload` is in place afterwards, whoever put it there.
    """
    try:
        os.replace(part, payload)
        return True
    except OSError:
        return payload.exists()


def stage(src, root=None):
    """THE single entry. Return a local copy of `src`, or `src` itself.

    Never raises: the whole body is one try that degrades to the source, honouring the
    contract postproc.py::_resolve_prob_source already sets — a cache problem costs
    speed, never the run.

    A HIT EMITS NO TIMING EVENT. `⏱ stage <file>: 0.0s` under the exact event name this
    saving is measured from would put a fabricated row in phase4/qc/timing_events.csv —
    the series qc/instruments/harvest_timing_events.py reads, and the one the 39.7 MB/s
    Drive-throughput median comes off. Today's exists+size early return emits nothing; a
    hit keeps emitting nothing and prints a distinct `cache hit` line instead. Same
    discipline as staging.py::_stage_tiles_local's `untick` calls.

    SAME-PROCESS CALLERS OF ONE KEY ARE SERIALISED (`_key_lock`), for the whole body:
    the eight inference reader threads that stage the CHM at once now produce one copy
    and seven hits, where they produced seven copies and one lost payload (module
    docstring, "THE PIN IS PER PID"). Cross-process peers are still the pin's and the
    flock's business, unchanged.
    """
    src = Path(src)
    try:
        r = cache_root(root)
        r.mkdir(parents=True, exist_ok=True)
        key = _key(src)
        with _key_lock(key):
            return _stage_under_key_lock(src, r, key)
    except Exception as e:                                   # noqa: BLE001
        print(f"  WARNING: scratch cache error ({e!r}); reading from the source")
        return src


def _stage_under_key_lock(src, r, key):
    """The body of `stage()`, entered with this process's lock on `key` held. Raises
    freely — `stage()` owns the degrade-to-source except."""
    st = _src_stat(src)
    if st is None:
        return src                          # unverifiable source: fail closed
    sweep(root=r)
    with _cache_lock(r):
        kind, payload = _lookup(key, src, st, r)
    if kind == "hit":
        print(f"  cache hit {payload.name} ({st.st_size / 1e6:.0f} MB) — "
              f"no Drive copy")
        return payload
    if kind == "degrade":
        return src
    # "wait" falls through: a peer is mid-copy, and the P11.4 lock is exactly the
    # thing that serialises us behind it. That is today's behaviour for a bulk ortho
    # and it must not regress — a waiter that gave up here would read the whole file
    # windowed over FUSE for its entire step.

    from phase4seg.common import _staging_lock_for, tick, tock, untick
    with _staging_lock_for(src):            # P11.4: one bulk Drive copy at a time
        with _cache_lock(r):
            kind, payload = _lookup(key, src, st, r)
        if kind == "hit":                   # a same-VM peer staged it while we waited
            print(f"  cache hit {payload.name} ({st.st_size / 1e6:.0f} MB) — "
                  f"no Drive copy")
            return payload
        if kind in ("degrade", "wait"):
            # Still copying after the lock (or below STAGE_LOCK_MIN_BYTES, where the
            # lock is a nullcontext and there was nothing to wait on). Take the
            # source rather than copy2 into a destination a peer is writing —
            # today's code races there, so this is strictly safer than today.
            return src
        payload = _payload_path(src, root=r)
        # ABSENT BEFORE THE JOURNAL, not merely before the publish. `_clear_
        # destination` says why the atomic `.part` rename below is not enough on its
        # own — `sweep` promotes by SIZE at this name, and a pre-existing payload of
        # the right size is indistinguishable from our own result. It also runs
        # ahead of the evictor on purpose: the bytes it frees are bytes the evictor
        # would otherwise have deleted a real entry to find.
        if not _clear_destination(key, payload, r):
            return src                      # a live reader holds it: degrade
        _evict_to_target(st.st_size, r, keep_key=key)
        if shutil.disk_usage(r).free < st.st_size:
            print(f"  NOT caching {src.name}: {st.st_size / 1e9:.1f} GB does not "
                  f"fit in {shutil.disk_usage(r).free / 1e9:.1f} GB of scratch — "
                  f"reading from the source")
            return src
        _write_sidecar(key, r, {
            "state": "copying", "key": key, "src": str(src),
            "src_size": st.st_size, "src_mtime": st.st_mtime,
            "payload": payload.name, "bytes": 0, "pid": os.getpid(),
            "host": socket.gethostname(), "ts_start": time.time()})
        part = payload.with_name(
            payload.name + f".part.{os.getpid()}.{secrets.token_hex(3)}")
        # THE TIMER IS RE-ARMED PER ATTEMPT, and that is not a detail. `⏱ stage
        # <file>` is the exact row qc/instruments/harvest_timing_events.py ingests
        # into phase4/qc/timing_events.csv — the series this change is validated
        # against, and the one the 39.7 MB/s Drive-throughput median is computed
        # from. A single tick outside this loop would have put the FAILED attempt
        # and the eviction between attempts inside the interval the published row
        # names, so the row would report a duration that is not the duration of the
        # copy it describes, and MB/s would come out wrong LOW — precisely in the
        # constrained-disk regime the cache creates, where the retry fires.
        for attempt in (0, 1):
            tick(f"stage {src.name}")
            try:
                shutil.copy2(src, part)
                break
            except OSError as e:
                untick(f"stage {src.name}")   # this attempt is not the measurement
                with contextlib.suppress(OSError):
                    part.unlink()
                if attempt == 0:
                    # ENOSPC is the realistic one and it is recoverable: evict hard
                    # and try once more before giving the caller the source path.
                    _evict_to_target(st.st_size, r, keep_key=key)
                    continue
                _drop_record(key, r)          # no event: nothing was staged
                print(f"  WARNING: staging {src.name} failed ({e}); "
                      f"reading from the source")
                return src
        tock(f"stage {src.name}")
        with _cache_lock(r):
            # NO unlink ahead of the publish: `_clear_destination` emptied this
            # name before the journal, and anything at it now is a peer's copy
            # that the atomic os.replace goes over the top of. The unlink that
            # used to sit here is the window in which a sibling thread found the
            # CHM gone (`_publish_payload`, module docstring "THE PIN IS PER PID").
            if not _publish_payload(part, payload):
                _drop_record(key, r)
                with contextlib.suppress(OSError):
                    part.unlink()
                return src
            _write_sidecar(key, r, {
                "state": "ready", "key": key, "src": str(src),
                "src_size": st.st_size, "src_mtime": st.st_mtime,
                "payload": payload.name, "bytes": payload.stat().st_size,
                "pid": os.getpid(), "host": socket.gethostname(),
                "ts_start": time.time(), "ts_ready": time.time(),
                "last_use": time.time()})
            _write_pin(key, r)
    return payload
