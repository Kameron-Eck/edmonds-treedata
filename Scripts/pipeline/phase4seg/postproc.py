from phase4seg.config import *
from phase4seg import config
from phase4seg.common import (_tag_sfx, entry_for, tick, tock,
                              _copy_to_drive, _local_artifact_path, _crs_unit_m,
                              _stage_imagery_local, _unstage_imagery_local)
from phase4seg import scratchcache

# Module-level aliases for the three scratch-cache calls this module makes, so each is a
# patchable surface of THIS module — the same reason `_is_drive_path` exists here at all,
# and the reason qc/test_postproc_source.py can drive these paths without a Drive mount.
_invalidate_staged = scratchcache.invalidate
_pin_staged = scratchcache.pin
_reserve_scratch = scratchcache.reserve

import gc
import shutil

import numpy as np
import pandas as pd
import rasterio
import rasterio.features
import rasterio.windows
from shapely.geometry import mapping, shape
from tqdm import tqdm


# ══════════════════════════════════════════════════════════════════════════════
#  Step 6 — Post-processing (threshold → morphology → polygonize)
# ══════════════════════════════════════════════════════════════════════════════

def _operating_threshold(label):
    """Per-year canopy probability operating threshold for post-processing.

    Selects the column by THRESH_MODE (Fix D):
      "best_f1"         → ``best_f1_thresh`` (max-F1 point; default)
      "precision_floor" → ``prec_floor_thresh`` (lowest threshold with
                          precision ≥ PRECISION_FLOOR)
    Read from this year's OVERALL row of ``semantic_eval_report.csv``; falls back
    to CANOPY_PROB_THRESHOLD (0.5) if the report, row, or column is missing /
    NaN / out of (0,1) — e.g. when the precision floor was unreachable.

    Returns (threshold_float, source_str).

    An explicit --infer-thresh (INFER_THRESH_OVERRIDE) wins over everything: it
    returns verbatim, bypassing the eval-CSV lookup (used to lower off-year
    thresholds that suppress real canopy).

    NOTE: for coarse years tiled city-wide the threshold is now read from the
    held-out test block (Fix 3/4) and is out-of-sample; legacy 6-site / degraded
    years remain in-sample and optimistic.
    """
    if config.INFER_THRESH_OVERRIDE is not None and 0.0 < float(config.INFER_THRESH_OVERRIDE) < 1.0:
        return float(config.INFER_THRESH_OVERRIDE), f"--infer-thresh override ({float(config.INFER_THRESH_OVERRIDE):.3f})"
    col = ("prec_floor_thresh" if config.THRESH_MODE == "precision_floor"
           else "best_f1_thresh")
    # The channels arm being deployed — must match how step_evaluate keys its rows
    # (core.py::step_evaluate) so a year with MULTIPLE arms (rgb and rgb+chm) picks THIS
    # arm's threshold, not whichever row happened to be appended last.
    chan_desc = f"rgb+{config.HS_SOURCE}" if config.IN_CHANNELS >= 4 else "rgb"
    if EVAL_CSV.exists():
        try:
            df = pd.read_csv(EVAL_CSV)
            sub = df[(df["year"].astype(str) == str(label)) &
                     (df["scope"] == "OVERALL")]
            if len(sub) and "channels" in sub.columns:
                arm = sub[sub["channels"].astype(str) == chan_desc]
                if len(arm):
                    sub = arm          # exact (year, channels) arm; else fall back below
            if len(sub) and col in sub.columns:
                # Within the matched arm, the last row is the most recent eval.
                val = pd.to_numeric(sub.iloc[-1][col], errors="coerce")
                if pd.notna(val) and 0.0 < float(val) < 1.0:
                    return float(val), f"{col} ({config.THRESH_MODE}, {chan_desc}, semantic_eval_report.csv)"
        except Exception as e:
            print(f"  (could not read {col}: {e}; "
                  f"using default {CANOPY_PROB_THRESHOLD})")
    return CANOPY_PROB_THRESHOLD, f"default 0.5 ({config.THRESH_MODE} unavailable)"


def sieve_min_px(pixel_area_true_m2):
    """THE sieve arithmetic, one home — RE-BASELINED to TRUE m² (Kam, 2026-09-01,
    EPOCH 3): minimum patch size in PIXELS = MIN_CANOPY_PATCH / pixel area in TRUE
    square metres. Until EPOCH 3 the denominator was CRS units, so "3.0 m²" meant
    0.279 m² on survey-foot years and 3.24 m² on NAIP — an 11.6x minimum-mapping-
    unit spread BY CRS FAMILY, measured in phase4/qc/imagery_geometry.csv and
    recorded in docs/CRS_CENSUS.md (now resolved) + IMAGERY_FACTS 15. The residual
    spread is integer-pixel quantisation only (ceil): 3.000-3.24 m² across the
    archive. Masks produced before EPOCH 3 carry the old sieve; the EPOCH stamp in
    every manifest is what keeps the two eras from being silently compared.
    step_postproc and the geometry instrument both call THIS function."""
    return int(np.ceil(MIN_CANOPY_PATCH / pixel_area_true_m2))


def threshold_and_clean(prob, thr_u8, kernel):
    """The postproc NUMERIC kernel, pure: uint8 prob chunk -> {0,1,255} mask chunk.
    Threshold at the operating cut, open+close with the morph kernel, carry nodata
    through as 255. Extracted 2026-09-01 so qc/bench.py regresses the REAL code —
    a replica in the bench would regress nothing. step_postproc is the only other
    caller; behavior identical by construction."""
    from scipy.ndimage import binary_opening, binary_closing
    nod = prob == PROB_NODATA
    m = ((~nod) & (prob >= thr_u8)).astype(np.uint8)
    m = binary_opening(m, structure=kernel).astype(np.uint8)
    m = binary_closing(m, structure=kernel).astype(np.uint8)
    m[nod] = 255                       # carry no-data through to the mask
    return m


# ══════════════════════════════════════════════════════════════════════════════
#  Where postproc reads the probability raster FROM  (P4.3, extended 2026-09-07)
# ══════════════════════════════════════════════════════════════════════════════

STAGE_FREE_MARGIN = 1.3
"""Free bytes required in LOCAL_SCRATCH per byte staged.

ASSUMED, NOT MEASURED. The copy itself needs 1.0x; the extra 0.3x is slack for the
mask and GeoPackage this same step writes into LOCAL_SCRATCH while the staged
probability raster is still open. Nothing was measured to pick 0.3.
"""


def _is_drive_path(path):
    """True when `path` lives on the Colab Drive FUSE mount.

    The same test core.py::step_train applies to MODELS_DIR
    (``str(...).startswith("/content/drive")``), lifted into its own function so the
    branch is reachable from a test off-Colab: on Windows
    ``str(Path("/content/drive/x.tif"))`` is backslashed and can never match, the
    same design note common.py::_scratch_name carries.
    """
    return str(path).startswith("/content/drive")


def _resolve_prob_source(prob_final, allow_stage=True):
    """Choose the probability raster step_postproc actually opens.

    Returns ``(path, staged_here)``. Three cases, in order:

      a. a local copy already sits in LOCAL_SCRATCH — step_inference left it in this
         same invocation — AND its size matches `prob_final` -> read it;
         ``staged_here=False``, because that copy belongs to step_inference.
      b. `prob_final` is on the Drive FUSE mount and LOCAL_SCRATCH has room -> copy it
         down with ONE sequential read, then read the local copy; ``staged_here=True``.
      c. anything else — already local, no room, missing, or ``allow_stage=False``
         (the --dry-run path, which must not trigger a multi-GB copy before printing
         a threshold and returning) -> `prob_final` unchanged, ``staged_here=False``.

    Why (b) exists: postproc reads this raster in 4096-row windows. Over FUSE that is
    thousands of small latency-bound range reads with no CPU, disk or network counter
    moving — 96% of postproc samples showed all four idle
    (Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md §7, and per its §7.5 every hardware
    sample behind that figure predates commit 5096b03, so it measures the pre-fix
    behaviour this function removes rather than what remains) — while one SEQUENTIAL
    copy of the same file measured ~40 MB/s (§1). Commit 5096b03 covered only case (a)
    and fell back to the windowed FUSE read, which is the pathology itself.

    (a) and (b) resolve to the SAME scratch path by construction: _local_artifact_path
    and _stage_imagery_local both name their destination LOCAL_SCRATCH /
    _scratch_name(p) for the same `p` (common.py::_local_artifact_path,
    ::_stage_imagery_local). So (b) simply creates the file (a) would have found.

    THE SIZE CHECK, both sides. This paragraph used to say that
    common.py::_stage_imagery_local is a bare shutil.copy2 with no atomic rename, and
    that nothing sweeps the stump a killed copy leaves. AS OF THE SCRATCH CACHE, ALL
    THREE OF THOSE CLAIMS ARE FALSE and the amendment matters, because they are the
    premises the guards below were built on: staging now copies to
    ``<payload>.part.<pid>.<token>`` and publishes with os.replace
    (scratchcache.py::stage, ::_publish_payload), and scratchcache.py::sweep removes
    ``.part`` orphans BY PID rather than waiting out common.py::_sweep_part_orphans'
    24 h. A copy killed midway therefore no longer leaves a truncated multi-GB file at
    the path a later reader trusts.

    THE GUARDS STAY ANYWAY, and are still shown to fire in qc/test_postproc_source.py.
    Two reasons. First, this function also serves case (a): a copy that step_inference
    ADOPTED, or a pre-cache stump from a runtime that predates this change, neither of
    which the new atomicity covers retroactively. Second, the cache EXTENDS the reach of
    size-only trust — a stale same-size copy used to die with the step and can now
    survive into the next one — so validating on read is more load-bearing, not less.
    So: (a) compares sizes against the Drive original and DISCARDS a mismatch (which
    also drops a stale complete copy left by a superseded run at the same year+tag
    path), and (b) re-checks the size after copying. A size check is NOT a content check
    — it cannot catch a same-length substitution, only a short or differently-sized one.

    (a) ALSO PINS WHAT IT IS ABOUT TO READ. Under the queue that inherited copy is the
    adopted probability raster — a `ready`, UNPINNED cache entry — and this step then
    holds it open for 60-99 min across two separate ``rasterio.open`` calls. A
    concurrent ``stage()``/``reserve()`` from the other arm on the VM could evict it
    between them, so the pin is taken before the first open. It is a no-op for a
    sidecar-less copy, which is exactly today's trust level for one.

    (a) ALSO RESERVES, for the same reason (b) does. Until the scratch cache, case (a)
    was the branch that reached step_postproc having run NO evictor: it returns before
    the STAGE_FREE_MARGIN pre-check below, and step_postproc then writes the mask and the
    gpkg into LOCAL_SCRATCH beside a raster it holds open — on a disk that now also keeps
    the ortho every step used to delete. Pin first, then reserve, so the call cannot evict
    what it just pinned; the reservation is the margin's SLACK only (``STAGE_FREE_MARGIN
    - 1``), because the raster itself is already on the disk being measured.

    Never raises — the whole body sits inside one try, because on a wedged mount even
    ``prob_final.exists()`` re-raises drivefs EIO (CPython's pathlib swallows only
    ENOENT / ENOTDIR / EBADF / ELOOP). Any failure degrades to (`prob_final`, False)
    with a WARNING, so a staging problem costs speed and not the run.

    AND THAT DEGRADE MUST NOT LEAK. There is a window — between _stage_imagery_local
    returning a FINISHED multi-GB copy and this function returning ``(staged, True)`` —
    in which the very next statements touch the filesystem again (``staged.stat()``) and
    can raise. Before 2026-09-07 the ``except`` below returned `prob_final` from inside
    that window and nobody ever owned the copy: `staged_here` was False, so
    step_postproc's `finally` released nothing, and nothing else sweeps the name
    (common.py::_sweep_part_orphans takes only *.part.* / *.prev.*). One such failure
    per year ate the free space this function itself checks, so a transient stat error
    silently switched every LATER year back to the windowed FUSE read. The handler now
    unstages whatever THIS call staged, best-effort and inside its own try — releasing
    the copy must not become a new way for the never-raises contract to be broken.
    """
    prob_final = Path(prob_final)
    staged = None
    try:
        local = _local_artifact_path(prob_final)
        if local != prob_final and local.exists():
            try:
                same_size = local.stat().st_size == prob_final.stat().st_size
            except OSError:
                same_size = True     # cannot compare -> keep the pre-check behaviour
            if same_size:
                _pin_staged(local)      # nothing may evict this out from under us
                # PIN FIRST, THEN RESERVE — this call cannot evict what we just pinned.
                # THE BRANCH THAT RAN NO EVICTOR AT ALL: case (b) reserves and then
                # applies STAGE_FREE_MARGIN, but case (a) returned here having asked for
                # nothing, and it is now the branch the QUEUE takes (inference adopts the
                # raster instead of unlinking it, so postproc inherits a hit). The mask
                # and the gpkg still get written into this same directory while the
                # raster is open, on a disk that now also holds the cached ortho — the
                # accident that used to leave room (every step deleting its ortho on
                # exit) is exactly what the cache removes. So reserve the same slack case
                # (b) does: the margin MINUS the raster itself, which is already on disk.
                _reserve_scratch(int((STAGE_FREE_MARGIN - 1.0) * local.stat().st_size))
                print(f"  reading the staged local probability raster "
                      f"({local.stat().st_size / 1e6:.0f} MB) — no FUSE round-trip")
                return local, False
            print(f"  discarding a short/stale local probability raster "
                  f"({local.stat().st_size / 1e6:.0f} MB against a "
                  f"{prob_final.stat().st_size / 1e6:.0f} MB source) — not this raster")
            # INVALIDATE, not release: this discard is CORRECTNESS, not space management
            # (the ledger in common.py::_unstage_imagery_local separates the two). It is
            # the one call that still deletes — and it refuses under a live reader,
            # leaving us on the degrade path below rather than unlinking an open file.
            _invalidate_staged(local)
        if not allow_stage:
            return prob_final, False
        if not prob_final.exists():
            return prob_final, False          # the caller's ERROR line speaks for this
        if not _is_drive_path(prob_final):
            print("  probability raster is already on local disk — no staging needed")
            return prob_final, False
        LOCAL_SCRATCH.mkdir(parents=True, exist_ok=True)
        size = prob_final.stat().st_size
        # EVICT FIRST, then apply the existing margin to what is left. The scratch cache
        # now holds orthos that every step used to delete on exit, so "free" here is no
        # longer whatever the last step happened to leave behind. reserve() is not
        # allowed to REPLACE the margin below — collapsing the two would relax a check
        # that is pinned by qc/test_postproc_source.py and sized for the mask and gpkg
        # this step writes into the same directory while the raster is still open.
        _reserve_scratch(int(STAGE_FREE_MARGIN * size))
        free = shutil.disk_usage(LOCAL_SCRATCH).free
        if free < STAGE_FREE_MARGIN * size:
            print(f"  NOT staging the probability raster: {size / 1e9:.1f} GB needs "
                  f"{STAGE_FREE_MARGIN * size / 1e9:.1f} GB of scratch, "
                  f"{free / 1e9:.1f} GB free — reading windowed over FUSE")
            return prob_final, False
        staged = _stage_imagery_local(prob_final)
        if staged != prob_final:
            staged_size = staged.stat().st_size
            if staged_size != size:
                print(f"  WARNING: the staged probability raster is "
                      f"{staged_size / 1e9:.2f} GB, not {size / 1e9:.2f} GB — "
                      f"discarding it and reading windowed over FUSE")
                _invalidate_staged(staged)   # correctness discard; see case (a) above
                return prob_final, False
            print(f"  staged the probability raster to local scratch "
                  f"({size / 1e9:.1f} GB, one sequential copy) — the windowed read "
                  f"below runs off NVMe, not FUSE")
            return staged, True
        print("  WARNING: staging the probability raster failed — postproc will read "
              "it windowed over FUSE (slow: thousands of small range reads)")
        return prob_final, False
    except Exception as e:                                       # noqa: BLE001
        if staged is not None and staged != prob_final:
            try:
                _unstage_imagery_local(staged)   # the copy nobody would have owned
            except Exception:                    # noqa: BLE001 — see the docstring
                pass
        print(f"  WARNING: could not stage the probability raster ({e!r}) — postproc "
              f"will read it windowed over FUSE")
        return prob_final, False


def step_postproc(label, dry_run=False):
    print(f"\n── [{label}] Step 6: Post-processing ──")

    prob_final = MASKS_DIR / f"edmonds_canopy_prob_{label}{_tag_sfx()}.tif"
    # P4.3 (2026-09-07): NEVER READ THE PROBABILITY RASTER WINDOWED OVER FUSE.
    # This step is moving bytes, not computing:
    #   • 96% of postproc samples show no GPU, no CPU, no disk AND no network at once
    #     (Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md §7; that report's own §7.5
    #     caveat applies — every sample behind the figure predates 5096b03, so it is
    #     the pre-fix pathology, not a measurement of what is left) — blocked on FUSE
    #     per-request latency, while ONE sequential file reads at ~40 MB/s (§1);
    #   • postproc's elapsed time tracks the probability raster's SIZE, and how strongly,
    #     over how many runs, and what that costs the 5 cm epochs is recorded ONCE, at
    #     core.py::step_inference. Not restated here: that measurement has no tracked
    #     CSV or report home, so a copy of it would rot silently the day it is re-taken.
    # TWO local sources satisfy that, both resolved by _resolve_prob_source:
    #   (a) the copy step_inference left on NVMe when postproc runs in the SAME
    #       invocation (the default full-pipeline path in cli.py) — commit 5096b03;
    #   (b) a copy staged HERE, for the free-CPU postproc workflow where inference ran
    #       on another machine. 5096b03 fell back to the Drive path in that case, which
    #       is the pathology itself, not a fallback away from it. At the measured
    #       ~40 MB/s one sequential copy of 6.7 GB is ~2.8 min (arithmetic, not timed).
    # dry-run must not pay for (b): it prints a threshold and returns without reading.
    prob_out, prob_staged_here = _resolve_prob_source(prob_final,
                                                      allow_stage=not dry_run)
    try:
        mask_final = MASKS_DIR / f"edmonds_canopy_mask_{label}{_tag_sfx()}.tif"
        gpkg_final = MASKS_DIR / f"edmonds_canopy_mask_{label}{_tag_sfx()}.gpkg"
        # verified write path (P4.1): heavy outputs land on local NVMe first, then a
        # size+sha256-verified copy moves each to Drive (also makes the polygonize
        # read-back local instead of a multi-GB FUSE read).
        mask_out = _local_artifact_path(mask_final)
        gpkg_out = _local_artifact_path(gpkg_final)
        if not prob_out.exists():
            print(f"  ERROR: {prob_out} not found — run inference first"); return

        with rasterio.open(prob_out) as src:
            img_h, img_w = src.height, src.width
            img_crs, img_tf = src.crs, src.transform
            px, py = src.transform.a, abs(src.transform.e)
        pixel_area = px * py
        # CRS-UNIT TRAP (2026-08-27). `pixel_area` is in the raster's OWN CRS units,
        # which are NOT true m²: EPSG:2285 is US survey FEET (1 unit² = 0.0929 m², so
        # a "1 m" pixel is 10.76x too small) and EPSG:3857 is Web Mercator (inflated
        # 1/cos²(47.81°) = 2.215x at this latitude). Same family as the gsd_cm defect
        # (WORKPLAN §1.5). `pixel_area_true` below is for REPORTED AREAS only.
        #
        # DELIBERATELY NOT APPLIED to min_px: MIN_CANOPY_PATCH lives in config.py
        # (pure-move protected) and was tuned against these CRS-unit areas, so
        # converting here would silently change every postproc mask. The sieve is
        # therefore ~10.8x more permissive than "3.0 m²" reads on 2285 years and
        # ~2.2x stricter on 3857 years. Retuning that constant is a science decision.
        pixel_area_true = pixel_area * _crs_unit_m(img_crs) ** 2
        min_px = sieve_min_px(pixel_area_true)   # EPOCH 3: true m², not CRS units
        # Per-year operating threshold from step_evaluate (best-F1), not the fixed 0.5.
        thr, thr_src = _operating_threshold(label)
        thr_u8 = int(round(thr * 254))
        print(f"  threshold={thr:.3f} [{thr_src}] (u8≥{thr_u8})  "
              f"min_patch={MIN_CANOPY_PATCH}m²({min_px}px)  "
              f"morph={MORPH_KERNEL_SIZE}×{MORPH_KERNEL_SIZE}")
        if dry_run:
            print("  Dry run — not processing"); return

        tick("postproc")
        CHUNK = 4096
        kernel = np.ones((MORPH_KERNEL_SIZE, MORPH_KERNEL_SIZE), dtype=bool)
        mask_profile = {"driver": "GTiff", "dtype": "uint8", "width": img_w,
                        "height": img_h, "count": 1, "crs": img_crs, "transform": img_tf,
                        "compress": "lzw", "nodata": 255, "BIGTIFF": "YES"}
        canopy_px = valid_px = 0
        with rasterio.open(prob_out) as src, rasterio.open(mask_out, "w", **mask_profile) as dst:
            for r0 in tqdm(range(0, img_h, CHUNK), desc="  Threshold"):
                r1 = min(r0 + CHUNK, img_h)
                win = rasterio.windows.Window(0, r0, img_w, r1 - r0)
                prob = src.read(1, window=win)
                m = threshold_and_clean(prob, thr_u8, kernel)
                canopy_px += int((m == 1).sum())
                valid_px  += int((m != 255).sum())   # nodata carries through as 255
                dst.write(m[np.newaxis], window=win)

        canopy_area = canopy_px * pixel_area_true       # TRUE m² (see _crs_unit_m note)
        pct = 100 * canopy_px / valid_px if valid_px else 0
        print(f"  ✓ Mask (local): {mask_out.name} ({mask_out.stat().st_size/1e6:.0f} MB)")
        print(f"  Canopy: {canopy_px:,}px = {canopy_area/1e4:.1f} ha true "
              f"({pct:.1f}% of imaged area)")

        # ── Polygonize in ROW-STRIPS (memory-safe) ──
        # A fine year's mask is multi-GB (2013 = 74496×105984 ≈ 7.9 GB) — a single
        # src.read(1) OOMs the host (silent kernel kill). Read ~400M-px strips, sieve +
        # polygonize each, and collect the geometries (lightweight vs the raster). A canopy
        # region spanning a strip edge becomes two adjacent polygons — negligible for a
        # semantic-canopy area layer. Coarse years fit in one/two strips (unchanged).
        print("  Polygonizing…"); tick("polygonize")
        import fiona
        schema = {"geometry": "Polygon",
                  "properties": {"canopy_id": "str", "area_m2": "float"}}
        strip_rows = max(TILE_SIZE, min(img_h, int(400_000_000 / max(img_w, 1))))
        geom_list = []
        with rasterio.open(mask_out) as src:
            for _r0 in range(0, img_h, strip_rows):
                _win = rasterio.windows.Window(0, _r0, img_w, min(strip_rows, img_h - _r0))
                _clean = rasterio.features.sieve(
                    (src.read(1, window=_win) == 1).astype(np.uint8),
                    size=min_px, connectivity=POLYGON_CONNECTIVITY)
                _wtf = rasterio.windows.transform(_win, img_tf)
                geom_list.extend(shape(g) for g, _ in rasterio.features.shapes(
                    _clean, mask=(_clean == 1), transform=_wtf,
                    connectivity=POLYGON_CONNECTIVITY))
                del _clean
            gc.collect()
        n = 0
        # v039 speedup: the per-polygon Python loop (simplify preserve_topology=True +
        # is_valid + buffer(0), one fiona write each) dominates postproc on a full-city
        # mask (100k+ crowns). shapely 2.x runs simplify/validity/area as C ufuncs over
        # the whole array at once, and fiona.writerecords batches the write. Fallback to
        # the per-feature loop if shapely 2.x isn't available.
        try:
            import shapely as _shp
            _vec = all(hasattr(_shp, a) for a in
                       ("simplify", "make_valid", "is_valid", "get_parts",
                        "get_type_id", "area"))
        except Exception:
            _vec = False
        # layer= is EXPLICIT since 2026-08-29 (D18). The GPKG driver defaults the layer
        # name to the file's basename, and this file is written under a LOCAL STAGING
        # name before being copied to gpkg_final — so the published artifact's internal
        # layer name was silently inherited from a scratch filename. Pinning it to the
        # final stem reproduces exactly the name every existing GPKG already carries,
        # and stops the staging path from being able to change it.
        with fiona.open(gpkg_out, "w", driver="GPKG", layer=gpkg_final.stem,
                        crs=img_crs.to_wkt(), schema=schema) as dst:
            if _vec:
                print("  (vectorized shapely 2.x polygonize)")
                geoms = np.array(geom_list, dtype=object)
                if len(geoms):
                    if SIMPLIFY_TOLERANCE_M > 0:
                        # preserve_topology=False = fast Douglas-Peucker; the make_valid
                        # pass below repairs the rare self-intersection it can create.
                        geoms = _shp.simplify(geoms, SIMPLIFY_TOLERANCE_M,
                                              preserve_topology=False)
                    bad = ~_shp.is_valid(geoms)
                    if bad.any():
                        geoms[bad] = _shp.make_valid(geoms[bad])
                    parts = _shp.get_parts(geoms)                     # explode multi/coll
                    parts = parts[_shp.get_type_id(parts) == 3]       # keep Polygons only
                    areas = _shp.area(parts)
                    keep = areas >= MIN_CANOPY_PATCH
                    parts = parts[keep]; areas = areas[keep]
                    dst.writerecords(
                        {"geometry": mapping(p),
                         "properties": {"canopy_id": f"CAN_{label}_{i:07d}",
                                        "area_m2": round(float(a), 2)}}
                        for i, (p, a) in enumerate(zip(parts, areas)))
                    n = len(parts)
            else:
                for poly in tqdm(geom_list, desc="  Polygonize", mininterval=5.0):
                    if SIMPLIFY_TOLERANCE_M > 0:
                        poly = poly.simplify(SIMPLIFY_TOLERANCE_M, preserve_topology=True)
                    if not poly.is_valid:
                        poly = poly.buffer(0)
                    if poly.is_empty:
                        continue
                    parts = list(poly.geoms) if poly.geom_type == "MultiPolygon" else [poly]
                    for part in parts:
                        if part.area < MIN_CANOPY_PATCH:
                            continue
                        dst.write({"geometry": mapping(part),
                                   "properties": {"canopy_id": f"CAN_{label}_{n:07d}",
                                                  "area_m2": round(part.area, 2)}})
                        n += 1
        tock("polygonize")
        print(f"  ✓ Canopy GeoPackage: {gpkg_out.name}  ({n:,} polygons)")

        for _local, _final in ((mask_out, mask_final), (gpkg_out, gpkg_final)):
            if _local != _final:
                _copy_to_drive(_local, _final)     # raises loudly on size/sha mismatch
                try:
                    _local.unlink()
                except OSError:
                    pass

        # Record a one-line area summary for the cross-year consistency step.
        _append_area_summary(label, entry_for(label), canopy_area, pct, valid_px,
                             pixel_area_true)
        tock("postproc")
    finally:
        # P4.3 (2026-09-07): release the staged probability raster on EVERY exit —
        # whether inference left it for us or _resolve_prob_source staged it here, and
        # whether this step returned, raised or completed. Both are the SAME
        # LOCAL_SCRATCH path by construction (_local_artifact_path and
        # _stage_imagery_local derive it from _scratch_name of the same destination),
        # so either branch below removes the same file; `prob_staged_here` only picks
        # the guarded helper. It is the `finally` that matters: the file is 3-6.7 GB on
        # the fine epochs, nothing sweeps that name (common.py::_sweep_part_orphans
        # takes only *.part.* / *.prev.*), and one leak per failed year eats the free
        # space _resolve_prob_source checks — so a mid-queue exception used to silently
        # switch every LATER year back to the windowed FUSE read this exists to avoid.
        # Dropping it is free: the authoritative copy is on Drive either way (inference
        # verified its copy by size and sha256; case (b) copied FROM Drive). The cost
        # is that a same-year retry after a crash re-stages instead of reusing the
        # copy — one sequential read, deliberately paid to bound the leak.
        # `prob_staged_here` is never True under --dry-run (allow_stage=False), so the
        # first branch needs no dry-run guard. The second does: --dry-run reads nothing
        # and must not consume the copy step_inference left for the REAL run, which is
        # what the pre-`finally` code did by returning above this block.
        # BOTH BRANCHES NOW RELEASE, and the second one is the change. It used to
        # `unlink()` the copy step_inference left, which under the queue is the ADOPTED
        # probability raster — so a rerun of the same year+tag re-staged 2.4-6.7 GB that
        # was already on the disk. Releasing drops our pin and leaves the entry
        # evictable, which is the same disk bound expressed as a floor instead of an
        # unconditional delete. A payload with no cache record still unlinks (that is
        # common.py::_unstage_imagery_local's historical contract for an un-owned file),
        # so the leak this `finally` exists to bound is bounded either way.
        if prob_staged_here:
            _unstage_imagery_local(prob_out)   # guarded to LOCAL_SCRATCH; never raises
        elif prob_out != prob_final and not dry_run:
            _unstage_imagery_local(prob_out)


def _append_area_summary(label, entry, canopy_area_m2, canopy_pct, valid_px,
                         pixel_area):
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    # P6.4: rows are keyed (year, run_tag) — two tagged runs of one year used to
    # silently overwrite each other's area row.
    row = dict(year=label, run_tag=config.RUN_TAG or "", gsd_cm=entry["gsd_cm"],
               tier=tier_for(entry), coverage=entry["coverage"],
               canopy_ha=round(canopy_area_m2 / 1e4, 2),
               canopy_pct_of_imaged=round(canopy_pct, 2),
               imaged_ha=round(valid_px * pixel_area / 1e4, 2))
    path = EVAL_DIR / "_per_year_canopy_area.csv"
    if path.exists():
        df = pd.read_csv(path)
        if "run_tag" not in df.columns:
            df["run_tag"] = ""                 # legacy rows = untagged
        df["run_tag"] = df["run_tag"].fillna("")
        df = df[~((df["year"].astype(str) == label)
                  & (df["run_tag"].astype(str) == row["run_tag"]))]
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df.to_csv(path, index=False)


# ══════════════════════════════════════════════════════════════════════════════
#  Cross-year consistency (run once after all years)
# ══════════════════════════════════════════════════════════════════════════════

def _year_sort_key(label):
    """Sort chronologically; suffixed keys (2019n, 2021s) sit beside their year."""
    digits = "".join(ch for ch in str(label) if ch.isdigit())
    base = int(digits) if digits else 0
    suffix = "".join(ch for ch in str(label) if ch.isalpha())
    return (base, suffix)


def step_consistency(dry_run=False):
    print("\n── Cross-year consistency check ──")
    area_path = EVAL_DIR / "_per_year_canopy_area.csv"
    if not area_path.exists():
        print(f"  No per-year area summaries yet ({area_path.name}). "
              f"Run inference+postproc first."); return
    df = pd.read_csv(area_path)
    if df.empty:
        print("  No rows."); return
    if "run_tag" in df.columns:
        # One row per year for the trend: prefer the recipe-matched citywide_rgb
        # row when a year has been postproc'd under more than one tag (P6.4).
        df["_pref"] = (df["run_tag"].astype(str) == "citywide_rgb").astype(int)
        df = (df.sort_values("_pref", ascending=False)
                .drop_duplicates(subset="year", keep="first")
                .drop(columns="_pref").reset_index(drop=True))

    # Full-coverage years only for the trend (partial-coverage 67% years aren't
    # directly comparable in absolute hectares).
    df["_full"] = df["coverage"].astype(str).str.lower().eq("full")
    df = df.sort_values(by="year", key=lambda s: s.map(_year_sort_key)).reset_index(drop=True)

    full = df[df["_full"]].reset_index(drop=True)
    # Median canopy across full-coverage years; flag years deviating > ±40%.
    flags = []
    if len(full) >= 3:
        med = float(np.median(full["canopy_ha"]))
        for _, r in full.iterrows():
            dev = (r["canopy_ha"] - med) / med if med else 0
            flag = ""
            if abs(dev) > 0.40:
                flag = "HIGH" if dev > 0 else "LOW"
            flags.append((r["year"], r["canopy_ha"], round(dev * 100, 1), flag))
        print(f"  Median full-coverage canopy: {med:.1f} ha")
        print(f"  {'Year':<8}{'Canopy ha':>11}{'Δ vs median':>13}  flag")
        print(f"  {'-'*8}{'-'*11}{'-'*13}  ----")
        for y, ha, dev, flag in flags:
            print(f"  {str(y):<8}{ha:>11.1f}{dev:>12.1f}%  {flag}")
    else:
        print("  <3 full-coverage years processed — trend check deferred.")

    if dry_run:
        return
    out = df.drop(columns=["_full"]).copy()
    if flags:
        fmap = {str(y): f for y, _, _, f in flags}
        dmap = {str(y): d for y, _, d, _ in flags}
        out["pct_dev_from_median"] = out["year"].astype(str).map(dmap)
        out["anomaly_flag"] = out["year"].astype(str).map(fmap).fillna("")
    out.to_csv(CONSISTENCY_CSV, index=False)
    print(f"  ✓ {CONSISTENCY_CSV.name}")
    print("  Note: large deviations may reflect real canopy change, seasonal/"
          "phenology differences, or model issues — confirm visually before "
          "trusting the trend (Method Pipeline 'Temporal Validity Check').")
