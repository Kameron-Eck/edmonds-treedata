from phase4seg.config import *
from phase4seg import config
from phase4seg.common import (
    _stage_imagery_local, _unstage_imagery_local, entry_for, resolve_native_path,
    _hillshade_ds, read_hillshade_chip, _site_window, _load_review_regions,
    tile_dir_for,
)
from phase4seg.labels import (
    canopy_label_from_2020_mask, additions_from_mask, apply_additions,
)

import json
import os
import shutil
import subprocess
import time

import numpy as np
import pandas as pd
import rasterio
import rasterio.features
import rasterio.warp
import rasterio.windows
from pathlib import Path
from rasterio.coords import BoundingBox
from rasterio.enums import Resampling
from sklearn.model_selection import train_test_split
from tqdm import tqdm


# ══════════════════════════════════════════════════════════════════════════════
#  Step 2 — Tiling (per-tier stride; reads the native-GSD site crops)
# ══════════════════════════════════════════════════════════════════════════════

def tile_site_native(site_label, img_path, mask_path, stride, neg_rate,
                     keep_all_empty=False):
    """512×512 paired tiles for one site crop at native resolution."""
    records = []
    with rasterio.open(img_path) as img_src, rasterio.open(mask_path) as msk_src:
        h, w = img_src.height, img_src.width
        assert (h, w) == (msk_src.height, msk_src.width), \
            f"dim mismatch {site_label}"
        img_tf, crs = img_src.transform, img_src.crs

        if h < TILE_SIZE or w < TILE_SIZE:
            # Site smaller than one tile (can happen at very coarse GSD): pad-read
            # a single TILE_SIZE window so the year still contributes a tile.
            row_starts, col_starts = [0], [0]
        else:
            row_starts = range(0, h - TILE_SIZE + 1, stride)
            col_starts = range(0, w - TILE_SIZE + 1, stride)

        accepted = rejected = 0
        for ro in row_starts:
            for co in col_starts:
                win = rasterio.windows.Window(co, ro, TILE_SIZE, TILE_SIZE)
                img_tile = img_src.read(window=win, boundless=True, fill_value=0)
                msk_tile = msk_src.read(1, window=win, boundless=True,
                                        fill_value=IGNORE_LABEL)
                labeled = msk_tile != IGNORE_LABEL
                n_lab = int(labeled.sum())
                if n_lab == 0:
                    rejected += 1            # entirely unreviewed → no signal
                    continue
                canopy_frac = float((msk_tile == 1).sum()) / n_lab

                if canopy_frac == 0.0:
                    if keep_all_empty or np.random.random() < neg_rate:
                        pass
                    else:
                        rejected += 1
                        continue

                records.append({
                    "tile_name": f"{site_label.lower()}_r{ro:05d}_c{co:05d}.tif",
                    "site": site_label, "row_off": ro, "col_off": co,
                    "canopy_frac": round(canopy_frac, 4),
                    "crs": crs,
                    "tile_transform": rasterio.windows.transform(win, img_tf),
                    "_img_tile": img_tile, "_mask_tile": msk_tile,
                })
                accepted += 1
        print(f"    {site_label:<22} {accepted} accepted / {rejected} rejected")
    return records


# ── Canopy-fraction stratification (Fix 3) ────────────────────────────────────

def _frac_bin(f):
    """5-bin index for a tile's canopy fraction. Bin 0 is exactly-background
    (hard negatives: roads, rooftops, water, parking)."""
    if f <= 0.0:
        return 0
    if f <= 0.25:
        return 1
    if f <= 0.50:
        return 2
    if f <= 0.75:
        return 3
    return 4


def _stratified_sample(records, budget, seed=RANDOM_SEED):
    """Sample ~balanced counts per canopy-fraction bin up to `budget` — NEVER
    first-N (the old cap took the first N canopy tiles and dropped every
    negative). Records flagged ``force_keep`` (true-negative-site tiles) are
    always retained; they count against the budget but not the per-bin balance.
    Returns a shuffled list. May exceed `budget` only if forced tiles alone do.
    """
    if budget is None or len(records) <= budget:
        return list(records)
    rng = np.random.RandomState(seed)
    forced = [r for r in records if r.get("force_keep")]
    pool   = [r for r in records if not r.get("force_keep")]
    remaining = max(0, budget - len(forced))
    bins = {}
    for r in pool:
        bins.setdefault(_frac_bin(r["canopy_frac"]), []).append(r)
    per = max(1, remaining // max(1, len(bins)))
    chosen, leftover = [], []
    for b in sorted(bins):
        rs = bins[b]
        rng.shuffle(rs)
        chosen.extend(rs[:per])
        leftover.extend(rs[per:])
    if len(chosen) < remaining:
        rng.shuffle(leftover)
        chosen.extend(leftover[:remaining - len(chosen)])
    out = forced + chosen[:remaining]
    rng.shuffle(out)
    return out


def _bin_histogram(records):
    """'b0:120 b1:80 …' canopy-fraction bin counts, for logging."""
    counts = {}
    for r in records:
        counts[_frac_bin(r["canopy_frac"])] = counts.get(_frac_bin(r["canopy_frac"]), 0) + 1
    return "  ".join(f"b{b}:{counts.get(b, 0)}" for b in range(5))


def _tile_grvi(img_tile, valid):
    """Mean GRVI = (G-R)/(G+R) over labeled pixels of an RGB tile (3×H×W uint8).
    Positive → vegetated; near-zero / negative → pavement, roof, bare, water.
    Used to flag green hard-negatives (Fix B)."""
    if int(valid.sum()) == 0:
        return 0.0
    r = img_tile[0].astype(np.float32)
    g = img_tile[1].astype(np.float32)
    grvi = (g - r) / (g + r + 1e-6)
    return float(grvi[valid].mean())


def _select_citywide_tiles(records, budget, seed=RANDOM_SEED):
    """City-wide coarse tile selection (Fix B).

    force_keep tiles (curated negative sites) are always retained and exempt
    from the budget caps. BACKGROUND_BUDGET_FRACTION of the remaining budget goes
    to background (bin 0), of which HARD_NEG_FRACTION is reserved for green
    hard-negatives (grass) so the grass/canopy boundary is represented; the rest
    of the budget is split among canopy bins (1..4), balanced among themselves
    (Fix B + Fix C). Returns (selected_records, stats_dict).
    """
    if budget is None or len(records) <= budget:
        return list(records), {"forced": sum(1 for r in records if r.get("force_keep")),
                               "background": sum(1 for r in records
                                                 if not r.get("force_keep")
                                                 and _frac_bin(r["canopy_frac"]) == 0),
                               "green_hardneg": sum(1 for r in records
                                                    if r.get("is_green_hardneg")),
                               "canopy": sum(1 for r in records
                                             if _frac_bin(r["canopy_frac"]) > 0)}
    rng = np.random.RandomState(seed)
    forced = [r for r in records if r.get("force_keep")]
    pool   = [r for r in records if not r.get("force_keep")]
    remaining = max(0, budget - len(forced))

    by_bin = {}
    for r in pool:
        by_bin.setdefault(_frac_bin(r["canopy_frac"]), []).append(r)

    # Background gets a fixed share of the budget (Fix C); canopy bins split the
    # rest. Carry any background shortfall over to canopy so the budget is used.
    bg = by_bin.get(0, [])
    n_bg = min(len(bg), int(round(BACKGROUND_BUDGET_FRACTION * remaining)))
    n_can_budget = remaining - n_bg

    # Background bin 0 with a reserved green-hard-negative slice (Fix B).
    green = [r for r in bg if r.get("is_green_hardneg")]
    plain = [r for r in bg if not r.get("is_green_hardneg")]
    rng.shuffle(green); rng.shuffle(plain)
    n_green = min(len(green), int(round(HARD_NEG_FRACTION * n_bg)))
    bg_sel = green[:n_green] + plain[:max(0, n_bg - n_green)]
    if len(bg_sel) < n_bg:                          # ran out of plain → more green
        bg_sel += green[n_green:n_green + (n_bg - len(bg_sel))]

    # Canopy bins 1..4 balanced among themselves.
    canopy_bins = [b for b in sorted(by_bin) if b != 0]
    per_can = max(1, n_can_budget // max(1, len(canopy_bins))) if canopy_bins else 0
    can_sel, leftover = [], []
    for b in canopy_bins:
        rs = by_bin[b]; rng.shuffle(rs)
        can_sel.extend(rs[:per_can]); leftover.extend(rs[per_can:])
    if len(can_sel) < n_can_budget:                 # top up to the canopy budget
        rng.shuffle(leftover)
        can_sel.extend(leftover[:n_can_budget - len(can_sel)])
    can_sel = can_sel[:n_can_budget]

    chosen = bg_sel + can_sel
    out = forced + chosen
    rng.shuffle(out)
    stats = dict(
        forced=len(forced),
        background=sum(1 for r in chosen if _frac_bin(r["canopy_frac"]) == 0),
        green_hardneg=sum(1 for r in chosen if r.get("is_green_hardneg")),
        canopy=sum(1 for r in chosen if _frac_bin(r["canopy_frac"]) > 0))
    return out, stats


def _is_negative_site(site_label, crowns):
    """A curated negative training site (Fix A). True for: a 'Negative_*' site,
    a site with no crown file (``crowns is None``), or a review site whose
    approved-crown count is zero.

    Negative_Parking carries a review gpkg with zero approved crowns, so the old
    ``crowns is None`` test misclassified it as a positive site and dropped it
    from the city-wide negative pool — the root of the precision problem.
    """
    if str(site_label).lower().startswith("negative"):
        return True
    if crowns is None:
        return True
    cols = getattr(crowns, "columns", [])
    if "status" in cols:
        return int((crowns["status"].astype(str).str.lower()
                    == "approved").sum()) == 0
    return False


def _negative_site_records(src, sites, src_nodata, stride):
    """Explicit guaranteed-background tiles from curated negative sites (Fix A).

    Tiles each negative site's footprint straight from the year's ortho, in the
    ortho's pixel space (so block/split coordinates line up with the city-wide
    tiles), and labels every pixel background (0; IGNORE only where the imagery
    is nodata) — we do NOT trust the 2020 mask over a curated negative. Records
    are ``force_keep=True`` so they bypass the stratified cap and are pinned to
    train.

    Tune Fix 2: tiles at the coarse tiling ``stride`` (not TILE_SIZE) so a site
    spanning a few tiles' worth of ground yields many overlapping background
    tiles instead of one — Negative_Parking (~450 m → ~750 px at 59.7 cm) went
    from 1 tile to dozens.
    """
    out, seen = [], set()
    img_h, img_w, tf = src.height, src.width, src.transform
    nir_mode = config.nir_mode()          # M06: band 4 = this ortho's own band 4
    for site_label, b3857, crowns in sites:
        if not _is_negative_site(site_label, crowns):
            continue
        # Honour the site's REGION file when one exists (2026-08-24). Before this fix the
        # whole footprint RECTANGLE was labelled background — so any tree inside a negative
        # site's bounds (Parking's known street-tree sliver; the traced trees in the new
        # Edmonds Heights site) became a FALSE background label, teaching the model to
        # suppress isolated trees. Now: inside region → 0, outside region (incl. the
        # hole-punched cut-outs) → IGNORE. No regions file → rectangle behaviour unchanged.
        region_gdf = _load_review_regions(site_label, target_crs=src.crs)
        if src.crs is not None and src.crs.to_epsg() != 3857:
            bn = BoundingBox(*rasterio.warp.transform_bounds(
                CROWN_CRS, src.crs, b3857.left, b3857.bottom,
                b3857.right, b3857.top))
        else:
            bn = b3857
        win = _site_window(src, bn)
        if win.width <= 0 or win.height <= 0:
            continue
        r0, c0 = int(win.row_off), int(win.col_off)
        rh, rw = int(win.height), int(win.width)
        rows = list(range(r0, r0 + max(1, rh - TILE_SIZE + 1), stride)) or [r0]
        cols = list(range(c0, c0 + max(1, rw - TILE_SIZE + 1), stride)) or [c0]
        kept = 0
        for ro in rows:
            for co in cols:
                ro2 = min(max(0, ro), max(0, img_h - TILE_SIZE))
                co2 = min(max(0, co), max(0, img_w - TILE_SIZE))
                if (ro2, co2) in seen:
                    continue
                seen.add((ro2, co2))
                win_t = rasterio.windows.Window(co2, ro2, TILE_SIZE, TILE_SIZE)
                img_tile = src.read([1, 2, 3], window=win_t,
                                    boundless=True, fill_value=0)
                if src_nodata is not None:
                    nod = np.all(img_tile == src_nodata, axis=0)
                else:
                    nod = np.all(img_tile == 0, axis=0)
                if float(nod.mean()) > COVERAGE_NODATA_MAX:
                    continue
                mask_tile = np.zeros((TILE_SIZE, TILE_SIZE), dtype=np.uint8)
                if region_gdf is not None and len(region_gdf):
                    tile_tf = rasterio.windows.transform(win_t, tf)
                    inside = rasterio.features.rasterize(
                        [(geom, 1) for geom in region_gdf.geometry],
                        out_shape=(TILE_SIZE, TILE_SIZE), transform=tile_tf,
                        fill=0, dtype="uint8")
                    mask_tile[inside == 0] = IGNORE_LABEL
                    if float((inside == 1).mean()) < 0.05:
                        continue          # tile barely touches the region — nothing to teach
                mask_tile[nod] = IGNORE_LABEL
                out.append({
                    "tile_name": f"neg_{site_label.lower()}_r{ro2:05d}_c{co2:05d}.tif",
                    "site": f"neg:{site_label}", "row_off": ro2, "col_off": co2,
                    "canopy_frac": 0.0, "crs": src.crs,
                    "tile_transform": rasterio.windows.transform(win_t, tf),
                    "_img_tile": img_tile, "_mask_tile": mask_tile,
                    # M06: same window, same file → co-registered with no warp.
                    # Read only for kept tiles (after the nodata/region filters).
                    "_nir_tile": (src.read([4], window=win_t, boundless=True,
                                           fill_value=0) if nir_mode else None),
                    "force_keep": True, "grvi": 0.0, "is_green_hardneg": False,
                })
                kept += 1
        if kept:
            print(f"    negative site {site_label:<22} +{kept} background tile(s)")
    return out


def _gather_citywide_coarse(label, sites, stride_override=None, dry_run=False):
    """Coarse-tier city-wide tiling (Fix 3).

    Sample 512px tiles across the FULL city ortho for this year, labelling each
    from the Phase 3 2020 binary canopy mask reprojected to the year's native
    grid. Curated negative sites are then explicitly tiled as guaranteed
    background and appended (force_keep=True, Fix A). Returns a list of tile
    records (same schema as ``tile_site_native``, plus a ``force_keep`` flag).
    """
    entry  = entry_for(label)
    native = resolve_native_path(entry)
    if not native.exists():
        print(f"  ERROR: native ortho not found: {native}")
        return []
    if not MASK_2020.exists():
        print(f"  ERROR: Phase 3 2020 canopy mask not found: {MASK_2020}\n"
              f"        coarse city-wide tiling needs it as the label source.")
        return []
    stride = int(stride_override) if stride_override else CITYWIDE_CANDIDATE_STRIDE

    local      = native    if dry_run else _stage_imagery_local(native)
    mask_local = MASK_2020  if dry_run else _stage_imagery_local(MASK_2020)
    # Optional ADD-ONLY corrected-label overlay (NIR+CHM-confirmed canopy).
    add_path = Path(config.ADD_CANOPY_MASK) if config.ADD_CANOPY_MASK else None
    if add_path and not add_path.exists():
        print(f"  WARNING: --add-canopy-mask not found, ignoring: {add_path}")
        add_path = None
    add_local = None
    if add_path:
        add_local = add_path if dry_run else _stage_imagery_local(add_path)
        print(f"  + corrected-label overlay (ADD-ONLY): {add_path.name}")
    asrc = None
    records = []
    try:
        with rasterio.open(local) as src:
            native_crs, src_nodata = src.crs, src.nodata
            img_h, img_w, tf = src.height, src.width, src.transform
            print(f"  Ortho: {img_w}×{img_h}px  GSD≈{tf.a*100:.1f}cm  "
                  f"nodata={src_nodata}")
            # ── M06: band 4 = THIS ortho's NIR band (no LIDAR, no warp) ────────
            nir_mode = config.nir_mode()
            if nir_mode:
                if src.count < 4:
                    raise RuntimeError(
                        f"--hs-source nir: year {label} ortho {native.name} has "
                        f"{src.count} band(s) — it carries no NIR. Fail loud; the "
                        f"engine never substitutes RGB or a LIDAR band for a "
                        f"missing NIR. Use a YEAR_CATALOG entry with bands=4.")
                print(f"  + NIR band 4 from THIS YEAR'S ortho {native.name} "
                      f"(source=nir; same window, no reprojection)")
                if str(label) in NIR_LIFTED_FLOOR_YEARS:
                    print(f"  ⚠ WARNING: {label} has a LIFTED NIR BLACK POINT "
                          f"(IMAGERY_FACTS §12) — structure/location honest, "
                          f"absolute NIR level NOT comparable to the healthy "
                          f"eight that HS_STATS['nir'] was measured on.")
            # Bound the scan to ~CITYWIDE_CANDIDATE_TARGET candidates regardless of
            # GSD (floor = CITYWIDE_CANDIDATE_STRIDE, so coarse is unchanged). An
            # explicit --stride override is always honoured.
            if config.SAMPLE_MANIFEST:
                origins = _origins_from_manifest(native_crs, tf, img_h, img_w)
                print(f"  SAMPLE manifest: {Path(config.SAMPLE_MANIFEST).name} → "
                      f"{len(origins):,} fixed C-CAP-stratified tile locations")
            else:
                if not stride_override:
                    adaptive = int(round((img_h * img_w / CITYWIDE_CANDIDATE_TARGET) ** 0.5))
                    stride = max(CITYWIDE_CANDIDATE_STRIDE, adaptive)
                rows = list(range(0, max(1, img_h - TILE_SIZE + 1), stride)) or [0]
                cols = list(range(0, max(1, img_w - TILE_SIZE + 1), stride)) or [0]
                origins = [(r, c) for r in rows for c in cols]
                print(f"  Candidate positions: {len(origins):,}  (stride={stride}"
                      f"{'' if stride_override else ', adaptive'})")
            if dry_run:
                print("  Dry run — not reading tiles")
                return []
            with rasterio.open(mask_local) as msrc:
                asrc = rasterio.open(add_local) if add_local else None
                for ro, co in tqdm(origins, desc="  City-wide scan",
                                   mininterval=2.0):
                    win = rasterio.windows.Window(co, ro, TILE_SIZE, TILE_SIZE)
                    # RGB only. RGBI orthos (2016/2021s Snoh, 2019n/2023n NAIP)
                    # carry a 4th NIR band; reading all bands here wrote a (4,H,W)
                    # tile into the count=3 profile in step_tile → ValueError. The
                    # semantic model is RGB, so drop NIR like read_rgb_window does.
                    img_tile = src.read([1, 2, 3], window=win,
                                        boundless=True, fill_value=0)
                    if src_nodata is not None:
                        nod = np.all(img_tile == src_nodata, axis=0)
                    else:
                        nod = np.all(img_tile == 0, axis=0)
                    if float(nod.mean()) > COVERAGE_NODATA_MAX:
                        continue                       # un-imaged tile
                    win_tf = rasterio.windows.transform(win, tf)
                    mask_tile = canopy_label_from_2020_mask(
                        msrc, native_crs, win_tf, TILE_SIZE, TILE_SIZE)
                    if asrc is not None:                 # ADD-ONLY corrected labels
                        add_tile = additions_from_mask(
                            asrc, native_crs, win_tf, TILE_SIZE, TILE_SIZE)
                        mask_tile = apply_additions(mask_tile, add_tile)
                    mask_tile[nod] = IGNORE_LABEL
                    n_lab = int((mask_tile != IGNORE_LABEL).sum())
                    if n_lab == 0:
                        continue                       # no 2020 label here
                    canopy_frac = float((mask_tile == 1).sum()) / n_lab
                    grvi = _tile_grvi(img_tile, mask_tile != IGNORE_LABEL)
                    records.append({
                        "tile_name": f"city_r{ro:05d}_c{co:05d}.tif",
                        "site": "city", "row_off": ro, "col_off": co,
                        "canopy_frac": round(canopy_frac, 4),
                        "crs": native_crs,
                        "tile_transform": win_tf,
                        "_img_tile": img_tile, "_mask_tile": mask_tile,
                        # M06: read band 4 ONLY for tiles that survived every
                        # filter above, so nodata/GRVI/selection stay byte-
                        # identical to the RGB arm and RAM holds one extra chip
                        # per KEPT candidate, not per scanned position.
                        "_nir_tile": (src.read([4], window=win, boundless=True,
                                               fill_value=0) if nir_mode else None),
                        "force_keep": False, "grvi": round(grvi, 4),
                        "is_green_hardneg": (canopy_frac == 0.0
                                             and grvi >= GREEN_GRVI_THRESHOLD),
                    })
            # Curated negative sites → explicit guaranteed-background tiles
            # (Fix A), tiled at the coarse tiling stride so they contribute many
            # tiles, not one (Tune Fix 2).
            neg_stride = TIER_TILE_PARAMS[tier_for(entry)]["stride"]
            records.extend(_negative_site_records(src, sites, src_nodata,
                                                  neg_stride))
    finally:
        if asrc is not None:
            asrc.close()
        if not dry_run:
            if local != native:
                _unstage_imagery_local(local)
            if mask_local != MASK_2020:
                _unstage_imagery_local(mask_local)
            if add_local is not None and add_local != add_path:
                _unstage_imagery_local(add_local)
    n_force = sum(1 for r in records if r.get("force_keep"))
    n_green = sum(1 for r in records if r.get("is_green_hardneg"))
    print(f"  Gathered {len(records)} labeled tiles "
          f"({n_force} force-kept negative-site, {n_green} green hard-neg "
          f"candidates @GRVI≥{GREEN_GRVI_THRESHOLD})  bins[{_bin_histogram(records)}]")
    return records


def _assign_blocks(records, gsd_m, block_size_m=SPATIAL_BLOCK_SIZE_M):
    """Tag each record with a spatial block id (Fix 4). Block edge is
    `block_size_m` on the ground, never smaller than one tile."""
    block_px = max(TILE_SIZE, int(round(block_size_m / gsd_m)))
    for r in records:
        r["block"] = f"{r['row_off'] // block_px}_{r['col_off'] // block_px}"
    return block_px


def _block_partition(records, gsd_m, val_frac=COARSE_VAL_FRAC,
                     test_frac=COARSE_TEST_FRAC, buffer_m=CANOPY_AUTOCORR_M,
                     seed=RANDOM_SEED):
    """Geographically-blocked train/val/test split for city-wide coarse tiles
    (Fix 4). Whole spatial blocks go to test, val, or train; then train tiles
    within `buffer_m` of any val/test tile are dropped so the held-out sets are
    honestly separated (canopy autocorrelation range ≈ 250–520 m).

    Sets ``r['split']`` ∈ {train, val, test, drop} on each record. Falls back to
    a degraded split (no test, random val, nothing dropped) and flags it when
    blocking can't form non-empty val AND test (e.g. partial-coverage years with
    too few blocks). Returns a status dict for logging.
    """
    block_px = _assign_blocks(records, gsd_m)
    n = len(records)
    rng = np.random.RandomState(seed)
    status = {"blocks": 0, "block_px": block_px, "degraded": False,
              "train": 0, "val": 0, "test": 0}

    def _degraded():
        status["degraded"] = True
        idx = list(range(n)); rng.shuffle(idx)
        n_val = max(1, int(round(val_frac * n)))
        val_ids = set(idx[:n_val])
        for i, r in enumerate(records):
            r["split"] = "val" if i in val_ids else "train"
        status["train"] = sum(r["split"] == "train" for r in records)
        status["val"]   = sum(r["split"] == "val" for r in records)
        status["test"]  = 0
        return status

    blocks = sorted({r["block"] for r in records})
    rng.shuffle(blocks)
    status["blocks"] = len(blocks)
    if len(blocks) < 3 or n < 10:
        return _degraded()

    block_tiles = {b: [r for r in records if r["block"] == b] for b in blocks}
    test_blocks, val_blocks = set(), set()
    acc = 0
    for b in blocks:
        if acc >= test_frac * n:
            break
        test_blocks.add(b); acc += len(block_tiles[b])
    acc = 0
    for b in blocks:
        if b in test_blocks:
            continue
        if acc >= val_frac * n:
            break
        val_blocks.add(b); acc += len(block_tiles[b])

    for r in records:
        r["split"] = ("test" if r["block"] in test_blocks
                      else "val" if r["block"] in val_blocks else "train")

    # Buffer: drop train tiles within buffer_m (Chebyshev) of any held-out tile.
    buf_px = buffer_m / gsd_m
    held = [(r["row_off"], r["col_off"]) for r in records
            if r["split"] in ("val", "test")]
    if held:
        hp = np.asarray(held, dtype=np.float64)
        for r in records:
            if r["split"] != "train":
                continue
            d = np.maximum(np.abs(hp[:, 0] - r["row_off"]),
                           np.abs(hp[:, 1] - r["col_off"])).min()
            if d < buf_px:
                r["split"] = "drop"

    status["train"] = sum(r["split"] == "train" for r in records)
    status["val"]   = sum(r["split"] == "val" for r in records)
    status["test"]  = sum(r["split"] == "test" for r in records)
    if status["train"] == 0 or status["val"] == 0 or status["test"] == 0:
        return _degraded()           # partial coverage left a split empty
    return status


# ── Idempotent tiling: skip the ~20-min city scan when a complete tile set for
# the current sampling constants already sits on Drive. Tile SELECTION is fully
# deterministic (seeded), so re-running the default pipeline after a lost Colab
# session should reuse tiles, not rebuild them. The signature captures every
# constant that changes which tiles are selected/how they're labelled+split; if
# any differs, or a referenced tile is missing, we re-tile. --force-retile
# overrides. Non-citywide (6-site) tiling isn't cached (fast, and its inputs are
# the per-year site crops, not a fixed signature). ────────────────────────────
def _add_canopy_mask_sig():
    """Signature component for the ADD-ONLY corrected-label overlay. The overlay is
    baked into tiles at tile time (in _gather_citywide_coarse), so a cached tile set
    built WITHOUT it (or with a different additions file) must be rebuilt. Keyed on
    path + size + mtime so rebuilding the additions raster (e.g. new NDVI/height
    thresholds) also invalidates the cache."""
    p = Path(config.ADD_CANOPY_MASK)
    if not p.exists():
        return {"path": str(p), "missing": True}
    st = p.stat()
    return {"path": str(p), "size": int(st.st_size), "mtime": int(st.st_mtime)}


def _sample_manifest_sig():
    """Signature component for a --sample-manifest tile set — path+size+mtime, so a
    different or regenerated manifest rebuilds the cached tiles."""
    p = Path(config.SAMPLE_MANIFEST)
    if not p.exists():
        return {"path": str(p), "missing": True}
    st = p.stat()
    return {"path": str(p), "size": int(st.st_size), "mtime": int(st.st_mtime)}


def _origins_from_manifest(native_crs, tf, img_h, img_w, half=None, extent=None):
    """Fixed C-CAP-stratified tile locations (phase4_ccap_sample.py) → this ortho's
    pixel-space tile origins. Each manifest point (lon/lat) is reprojected into the
    year's native CRS and mapped to a pixel; a patch of size ``extent`` is CENTRED on
    it (origin = pixel − ``half``), clamped to the ortho, deduped.

    Points that fall OUTSIDE this year's ortho are SKIPPED (partial-coverage sensors),
    not clamped to an edge — clamping would silently relocate a sample to non-target
    ground. ``half``/``extent`` default to a full TILE_SIZE tile (tiling); inference
    passes its write-crop size so the SCORED patch centres on the point, not a
    half-tile off."""
    if half is None:
        half = TILE_SIZE // 2
    if extent is None:
        extent = TILE_SIZE
    mp = Path(config.SAMPLE_MANIFEST)
    if mp.suffix.lower() in (".gpkg", ".geojson", ".shp"):
        import geopandas as gpd
        g = gpd.read_file(mp).to_crs("EPSG:4326")
        lons, lats = g.geometry.x.tolist(), g.geometry.y.tolist()
    else:                                   # CSV: documented lon/lat in EPSG:4326
        df = pd.read_csv(mp)
        if not {"lon", "lat"}.issubset(df.columns):
            raise ValueError(f"{mp.name}: CSV manifest needs 'lon','lat' columns "
                             f"(EPSG:4326); got {list(df.columns)}")
        lons, lats = df["lon"].tolist(), df["lat"].tolist()
    xs, ys = rasterio.warp.transform("EPSG:4326", native_crs, lons, lats)
    inv = ~tf
    origins = set()
    for x, y in zip(xs, ys):
        col, row = inv * (x, y)
        if not (0 <= row < img_h and 0 <= col < img_w):
            continue                        # point outside this year's coverage → skip
        ro = min(max(0, int(row) - half), max(0, img_h - extent))
        co = min(max(0, int(col) - half), max(0, img_w - extent))
        origins.add((ro, co))
    return sorted(origins)


def _tile_signature(label, stride, max_tiles, citywide):
    sig = {
        "label": label, "citywide": bool(citywide), "stride": int(stride),
        "max_tiles": max_tiles, "tile_size": TILE_SIZE, "random_seed": RANDOM_SEED,
        "use_hillshade": bool(config.USE_HILLSHADE), "hs_source": config.HS_SOURCE,
        "use_vi": bool(config.USE_VI),
        "citywide_tiles": COARSE_CITYWIDE_TILES,
        "hard_neg_fraction": HARD_NEG_FRACTION,
        "background_budget_fraction": BACKGROUND_BUDGET_FRACTION,
        "green_grvi_threshold": GREEN_GRVI_THRESHOLD,
        "coarse_val_frac": COARSE_VAL_FRAC, "coarse_test_frac": COARSE_TEST_FRAC,
        "spatial_block_size_m": SPATIAL_BLOCK_SIZE_M,
        "canopy_autocorr_m": CANOPY_AUTOCORR_M,
    }
    # Only present when the overlay is active, so runs WITHOUT it keep matching
    # existing (pre-v043) tile caches — no spurious retile for other years.
    if config.ADD_CANOPY_MASK:
        sig["add_canopy_mask"] = _add_canopy_mask_sig()
    if config.SAMPLE_MANIFEST:
        sig["sample_manifest"] = _sample_manifest_sig()
    # --aux-height writes per-tile height sidecars → a distinct tile set; keyed only
    # when on so plain RGB-only caches are not spuriously invalidated.
    if config.AUX_HEIGHT:
        sig["aux_height"] = True
        sig["chm_credible_years"] = sorted(CHM_CREDIBLE_YEARS)
    # P6.6: the ortho the tiles were cut from. A replaced/re-mosaicked ortho used
    # to reuse stale tiles silently (the v042 failure class, but for imagery).
    # name+size only — mtime is deliberately EXCLUDED (Drive rewrites mtimes; the
    # phantom-M lesson). Legacy caches without this key are grandfathered in
    # _existing_tiles_valid, so nothing spuriously retiles.
    try:
        _ortho = resolve_native_path(entry_for(label))
        sig["ortho"] = {"name": _ortho.name,
                        "size": int(_ortho.stat().st_size) if _ortho.exists() else None}
    except Exception:
        pass
    return sig


def _meta_path(label):
    return tile_dir_for(label) / f"tile_index_{label}.meta.json"


def _existing_tiles_valid(label, sig):
    """True iff a complete tile set matching ``sig`` is already on disk: sidecar
    meta matches the signature, the index exists, and every referenced tile file
    is present. Any mismatch/missing file → False (re-tile)."""
    mp = _meta_path(label)
    idx = tile_dir_for(label) / f"tile_index_{label}.csv"
    if not (mp.exists() and idx.exists()):
        return False
    try:
        stored = json.loads(mp.read_text())
        want = dict(sig)
        if "ortho" not in stored:
            want.pop("ortho", None)   # legacy (pre-P6.6) cache: honored, ortho unchecked
        if stored != want:
            return False
        df = pd.read_csv(idx)
    except Exception:
        return False
    if len(df) == 0:
        return False
    for col in ("img_path", "mask_path"):
        for p in df[col]:
            if not Path(p).exists():
                return False
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  Bulk tile upload (rclone) — a WRITE-TRANSPORT change, nothing else
#
#  MEASURED 2026-08-26, live, on an rclone-mounted Colab VM: step_tile wrote each
#  tile file straight into the Drive tile dir through the FUSE mount at ~7-21
#  s/tile, so a 612-tile NIR retile burned ~100 min of a nearly-idle A100. Native
#  drivefs moved the same volume in ~8 min; a bulk `rclone copy` of the same byte
#  volume takes ~1-3 min. The per-FILE round trip is the cost, not the bytes.
#  CLAUDE.md rule 3 (local-then-copy, validate, then copy) already mandates this
#  pattern for every other large artifact — tiling simply predates the rule.
#
#  So, and ONLY when the activation triple in _bulk_upload_enabled holds: write
#  every tile file to local NVMe under LOCAL_SCRATCH/tileout/{label}/ in the SAME
#  relative layout, then do ONE bulk `rclone copy` to treedata-user:phase4/tiles/
#  {label}, VERIFY it server-side, and only after that write the index CSV and
#  meta.json THROUGH THE MOUNT exactly as today (meta last, so an interrupted run
#  never leaves a "cache valid" marker).
#
#  What deliberately does NOT change:
#    * the tile paths recorded in the index CSV are the same Drive-dir paths as
#      today — core._stage_tiles_local and the queue's VERIFY:tile probe both
#      depend on them being /content/drive/... strings;
#    * every byte and every path that ends up on Drive;
#    * tile selection, labelling, splitting — and _tile_signature gains NO key,
#      so no cached tile set is invalidated and no re-tile is triggered;
#    * behaviour anywhere the triple does not hold (local Windows QC/smoke,
#      drivefs-mounted VMs, rclone missing): the original direct-write path runs
#      unchanged, with `write_dir is out_tile_dir`.
# ══════════════════════════════════════════════════════════════════════════════

_RCLONE_REMOTE            = "treedata-user"  # gen_vm_bootstrap.py's WRITER remote. Its
                                             # root_folder_id IS the `treedata` folder,
                                             # so remote paths are BASE-relative 1:1.
_RCLONE_TRANSFERS         = 16
_RCLONE_CHECKERS          = 16
_RCLONE_PROBE_TIMEOUT_SEC = 60
_RCLONE_COPY_TIMEOUT_SEC  = 30 * 60          # a wedged remote must not hang past the
                                             # queue's per-step ceiling with no cleanup
_TILE_VISIBLE_TIMEOUT_SEC = 600              # mount dir-cache default is 5 min; Drive
_TILE_VISIBLE_POLL_SEC    = 15               # change-polling normally beats that by ~4x

_rclone_probe = None                         # None = unprobed; True/False = cached


def _rclone_ready():
    """True iff `rclone` is on PATH AND a remote named ``_RCLONE_REMOTE`` exists.

    `rclone listremotes` runs at most ONCE per process (the answer cannot change
    mid-run). Any failure — no binary, bad config, timeout — answers False, which
    simply leaves the original direct-write path in charge.
    """
    global _rclone_probe
    if _rclone_probe is None:
        _rclone_probe = False
        try:
            if shutil.which("rclone"):
                r = subprocess.run(["rclone", "listremotes"], capture_output=True,
                                   text=True, timeout=_RCLONE_PROBE_TIMEOUT_SEC)
                _rclone_probe = (r.returncode == 0
                                 and f"{_RCLONE_REMOTE}:" in (r.stdout or "").split())
        except Exception:                     # noqa: BLE001 — any probe failure = "no"
            _rclone_probe = False
    return _rclone_probe


def _bulk_upload_enabled(out_tile_dir):
    """The activation triple for the bulk-upload path — ALL THREE required:

      1. POSIX **and** the tile output root is under the /content/drive mount.
         On Windows ``str(WindowsPath("/content/drive/..."))`` is backslashed, so
         a local QC/smoke run cannot enter this branch even in principle.
      2. `rclone` on PATH.
      3. an rclone remote named ``treedata-user`` is configured.

    Anything else → False → today's direct-through-the-mount write, unchanged.
    Kept as its own function so the dry-harness can force the branch.
    """
    if os.name != "posix":
        return False
    if not str(out_tile_dir).startswith("/content/drive/"):
        return False
    return _rclone_ready()


def _remote_for(rel_posix):
    """Remote path for a BASE-relative posix path. ``treedata-user:``'s
    root_folder_id is the `treedata` folder itself, so the mapping is 1:1
    ("phase4/tiles/2016"). Its own function so the harness can retarget it."""
    return f"{_RCLONE_REMOTE}:{rel_posix}"


def _bulk_upload_target(out_tile_dir, label):
    """``(local staging root, remote path)`` for this year's tiles, or
    ``(None, None)`` when the unchanged direct-write path applies."""
    if not _bulk_upload_enabled(out_tile_dir):
        return None, None
    try:
        rel = out_tile_dir.relative_to(BASE).as_posix()
    except ValueError:
        return None, None                  # tile dir outside BASE → never guess a remote
    return LOCAL_SCRATCH / "tileout" / str(label), _remote_for(rel)


def _run_rclone(args, timeout):
    """Run one rclone command. Returns ``(rc, stdout, stderr)``; never raises —
    the caller decides what a nonzero rc means. A timeout answers rc=124, a
    missing/unrunnable binary rc=127."""
    cmd = ["rclone"] + list(args)
    print(f"    $ {' '.join(cmd)}", flush=True)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or ""), (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "", f"TIMEOUT after {timeout}s"
    except Exception as e:                    # noqa: BLE001 (OSError, missing binary)
        return 127, "", f"{type(e).__name__}: {e}"


def _echo_rclone(stdout, stderr, n=12):
    """Last few lines of an rclone transcript, into the step log."""
    tail = [ln for ln in ((stdout or "") + (stderr or "")).splitlines() if ln.strip()]
    for ln in tail[-n:]:
        print(f"      | {ln}")


def _staged_files(stage_root):
    """``{relative posix path: size}`` for every file under the staging root."""
    out = {}
    for p in stage_root.rglob("*"):
        if p.is_file():
            out[p.relative_to(stage_root).as_posix()] = p.stat().st_size
    return out


def _bulk_upload_fail(label, why, stdout="", stderr=""):
    """Loud, CACHE-INVALIDATING failure. No meta.json is left behind, so the next
    run re-tiles instead of trusting a half-uploaded set; the index CSV has not
    been written yet either, so the queue's VERIFY:tile reports MISSING. Raises
    RuntimeError — cli.main() does not catch it (StepLogger re-raises), so the
    process exits nonzero."""
    try:
        _meta_path(label).unlink()
    except OSError:
        pass
    print("\n" + "!" * 74, flush=True)
    print(f"!! BULK TILE UPLOAD FAILED for {label}: {why}")
    print(f"!! No tile index and no meta.json were written — the tile cache is "
          f"INVALID and the next run re-tiles.")
    print(f"!! The LOCAL staging copy is KEPT so a re-run resumes cheaply "
          f"(rclone copy skips what already landed).")
    print("!" * 74 + "\n", flush=True)
    _echo_rclone(stdout, stderr, n=20)
    raise RuntimeError(f"bulk tile upload failed for {label}: {why}")


def _wait_tiles_visible(stage_root, out_tile_dir):
    """Bounded wait until every uploaded tile is visible THROUGH THE MOUNT.
    Returns the number of still-missing files (0 = all visible).

    The upload went straight to Drive's API, so the FUSE mount can still be
    serving its pre-upload directory listing (often an empty one, since the split
    dirs were just mkdir'd through the mount). rclone mount invalidates on Drive
    change notifications (--poll-interval, ~1 min) and expires its listings at
    --dir-cache-time (5 min default), so this normally clears on the first or
    second poll. We wait anyway because the very next things to touch these paths
    — the queue's VERIFY:tile probe and core._stage_tiles_local's per-file stat —
    both read THROUGH the mount, and neither may be handed an index whose paths
    do not yet resolve.
    """
    want = {}
    for rel in _staged_files(stage_root):
        d, _, name = rel.rpartition("/")
        want.setdefault(d, set()).add(name)
    n_total = sum(len(v) for v in want.values())
    t0 = time.time()
    while True:
        missing = 0
        for d, names in want.items():
            mdir = out_tile_dir / d if d else out_tile_dir
            try:
                have = {p.name for p in mdir.iterdir()}
            except OSError:
                have = set()
            missing += len(names - have)
        el = time.time() - t0
        if missing == 0:
            print(f"    mount sees all {n_total} uploaded tiles ({el:.0f}s)", flush=True)
            return 0
        if el >= _TILE_VISIBLE_TIMEOUT_SEC:
            return missing
        print(f"    waiting for the mount to see the upload: {missing}/{n_total} "
              f"not visible yet ({el:.0f}s)", flush=True)
        time.sleep(_TILE_VISIBLE_POLL_SEC)


def _bulk_upload_tiles(stage_root, remote, out_tile_dir, label):
    """ONE bulk upload of the year's staged tiles, then verification. Raises
    RuntimeError (via _bulk_upload_fail) on any failure — the caller has not yet
    written the index or the meta, so a failed year leaves no cache-valid marker.

    IDEMPOTENT / RESUMABLE: `--checksum` makes `rclone copy` skip destination
    files whose md5 already matches, so a re-run after a partial upload (killed
    runtime, wedged mount) re-writes the tiles to local NVMe cheaply and uploads
    only the ones that never landed. It must be --checksum and NOT the default
    (size+modtime) or --size-only: the resumed run REGENERATES the tiles, so
    every local mtime is new (default → re-uploads everything), while --size-only
    would skip a same-name same-size tile whose CONTENT changed. Nothing is
    deleted at the destination — same as the direct-write path, which likewise
    leaves an older run's stale tiles in place.
    """
    staged = _staged_files(stage_root)
    n, nbytes = len(staged), sum(staged.values())
    if not n:
        _bulk_upload_fail(label, f"staging root {stage_root} holds no tile files")
    print(f"  Bulk upload: {n} files / {nbytes / 1e6:.0f} MB   "
          f"{stage_root} → {remote}", flush=True)
    t0 = time.time()
    rc, so, se = _run_rclone(
        ["copy", str(stage_root), remote, "--checksum",
         "--transfers", str(_RCLONE_TRANSFERS),
         "--checkers", str(_RCLONE_CHECKERS),
         "--stats", "60s", "--stats-one-line"],
        timeout=_RCLONE_COPY_TIMEOUT_SEC)
    _echo_rclone(so, se)
    if rc != 0:
        _bulk_upload_fail(label, f"rclone copy rc={rc}", so, se)
    t_copy = time.time() - t0

    # VERIFY server-side — NOT through the mount, whose cache we do not trust yet.
    # Every staged file must exist on the remote with a matching md5 (local and
    # Drive both expose md5, so `check` compares hashes, not just size). --one-way
    # so pre-existing EXTRA files on Drive (a stale tile from an older sampling)
    # are not a failure: the direct-write path leaves those behind too.
    check_args = ["check", str(stage_root), remote, "--one-way",
                  "--checkers", str(_RCLONE_CHECKERS)]
    rc, so, se = _run_rclone(check_args, timeout=_RCLONE_COPY_TIMEOUT_SEC)
    if rc != 0 and "no common hash" in (so + se).lower():
        # A backend pair with no shared hash (never true for local→drive, but the
        # verification must not silently vanish on one that isn't) → size-only.
        print("      (no common hash on this backend pair — falling back to "
              "--size-only verification)")
        rc, so, se = _run_rclone(check_args + ["--size-only"],
                                 timeout=_RCLONE_COPY_TIMEOUT_SEC)
    _echo_rclone(so, se)
    if rc != 0:
        rc2, so2, se2 = _run_rclone(["size", remote, "--json"], timeout=300)
        print(f"      remote size: {(so2 or se2).strip()[:300]}")
        _bulk_upload_fail(label, f"rclone check rc={rc} (--one-way)", so, se)

    # Corroborating counts for the log (never a gate — the remote legitimately
    # holds >= our count when an older sampling left tiles behind).
    rc2, so2, _ = _run_rclone(["size", remote, "--json"], timeout=300)
    if rc2 == 0:
        try:
            d = json.loads((so2 or "").strip().splitlines()[-1])
            print(f"    remote now holds {int(d['count'])} files / "
                  f"{int(d['bytes']) / 1e6:.0f} MB (local set: {n} / "
                  f"{nbytes / 1e6:.0f} MB)")
        except Exception:                     # noqa: BLE001 — diagnostics only
            pass

    n_missing = _wait_tiles_visible(stage_root, out_tile_dir)
    if n_missing:
        _bulk_upload_fail(
            label, f"{n_missing} uploaded tile(s) still not visible through the "
                   f"mount after {_TILE_VISIBLE_TIMEOUT_SEC}s — the bytes are on "
                   f"Drive (check passed) but the mount cache is stale; re-run "
                   f"the tile step (the upload will be a no-op)")

    shutil.rmtree(stage_root, ignore_errors=True)
    print(f"  ✓ bulk upload verified: {n} files / {nbytes / 1e6:.0f} MB in "
          f"{t_copy:.0f}s copy ({time.time() - t0:.0f}s total); staging root "
          f"cleaned", flush=True)


def step_tile(label, sites, dry_run=False, max_tiles=None, stride_override=None,
              citywide=False, force_retile=False):
    """Step 2 for one year: tile site crops (or the full city for coarse) and
    write the per-year index.

    ``citywide`` (coarse default, Fix 3) samples tiles across the whole city
    ortho labelled from the 2020 mask, balanced by canopy fraction, instead of
    tiling the 6 site crops.
    """
    entry = entry_for(label)
    tier  = tier_for(entry)
    tp    = TIER_TILE_PARAMS[tier]
    stride = int(stride_override) if stride_override else tp["stride"]
    mode = "CITY-WIDE" if citywide else "6-site"
    nir_mode = config.nir_mode()
    if nir_mode and not citywide:
        # The 6-site path tiles the per-year SITE CROPS, and those are written
        # RGB-only (labels.project_and_rasterise_site → read_rgb_window). Rather
        # than silently give an NIR run a 3-band tile set (or a LIDAR band), stop.
        raise RuntimeError(
            f"--hs-source nir on year {label} without the citywide path: site "
            f"crops are RGB-only (3 bands), so there is no NIR to bake. Pass "
            f"--force-citywide (what every queue job uses).")

    sig = _tile_signature(label, stride, max_tiles, citywide)
    if citywide and not dry_run and not force_retile \
            and _existing_tiles_valid(label, sig):
        idx = tile_dir_for(label) / f"tile_index_{label}.csv"
        n = len(pd.read_csv(idx))
        print(f"\n── [{label}] Step 2: Tiling [{mode}] — REUSED {n} existing "
              f"tiles (sampling signature unchanged; --force-retile to rebuild) ──")
        return

    print(f"\n── [{label}] Step 2: Tiling [{mode}] ({tier}: stride={stride}, "
          f"neg_rate={tp['neg_rate']}, test={'yes' if tp['has_test'] else 'no'}) ──")

    out_tile_dir  = tile_dir_for(label)
    # WRITE TRANSPORT ONLY (see "Bulk tile upload" above): on an rclone-mounted
    # Colab VM the tile files are written to local NVMe and bulk-uploaded once.
    # Everywhere else stage_root is None and `write_dir is out_tile_dir` — i.e.
    # byte-for-byte today's direct-through-the-mount write.
    stage_root, remote = _bulk_upload_target(out_tile_dir, label)
    write_dir = stage_root if stage_root is not None else out_tile_dir
    if stage_root is not None:
        # A leftover staging tree from an earlier, differently-sampled run must
        # never be uploaded; the tiles themselves are cheap to regenerate locally.
        shutil.rmtree(stage_root, ignore_errors=True)
        print(f"  Bulk-upload path ACTIVE: tiles → {write_dir} → one rclone copy "
              f"→ {remote}; index + meta still written through the mount")
    for split in ("train", "val", "test"):
        # The Drive-side split dirs are created THROUGH the mount in BOTH branches
        # so the directory tree on Drive ends identical — `rclone copy` creates no
        # empty dirs, and an empty split would otherwise silently disappear.
        (out_tile_dir / split / "images").mkdir(parents=True, exist_ok=True)
        (out_tile_dir / split / "masks").mkdir(parents=True, exist_ok=True)
        if config.AUX_HEIGHT:
            (out_tile_dir / split / "heights").mkdir(parents=True, exist_ok=True)
        if stage_root is not None:
            (write_dir / split / "images").mkdir(parents=True, exist_ok=True)
            (write_dir / split / "masks").mkdir(parents=True, exist_ok=True)
            if config.AUX_HEIGHT:
                (write_dir / split / "heights").mkdir(parents=True, exist_ok=True)

    np.random.seed(RANDOM_SEED)

    if citywide:
        all_records = _gather_citywide_coarse(
            label, sites, stride_override=stride_override, dry_run=dry_run)
        if dry_run:
            print("  Dry run — not writing tiles")
            return
        all_records, sel = _select_citywide_tiles(all_records, COARSE_CITYWIDE_TILES)
        tot = max(1, len(all_records))
        print(f"  Selected {len(all_records)} tiles: {sel['canopy']} canopy / "
              f"{sel['background']} background ({sel['green_hardneg']} green "
              f"hard-neg) + {sel['forced']} neg-site  "
              f"[bg target {BACKGROUND_BUDGET_FRACTION:.0%}, "
              f"actual {(sel['background'] + sel['forced']) / tot:.0%}]  "
              f"bins[{_bin_histogram(all_records)}]")
    else:
        year_site_dir  = SITE_DIR / label
        negative_sites = {s for s, _, c in sites if c is None}
        all_records = []
        for site_label, _, _ in sites:
            ip = year_site_dir / f"{site_label.lower()}_img.tif"
            mp = year_site_dir / f"{site_label.lower()}_mask.tif"
            if not (ip.exists() and mp.exists()):
                continue  # uncovered/skipped in step 1
            all_records.extend(tile_site_native(
                site_label, ip, mp, stride, tp["neg_rate"],
                keep_all_empty=(site_label in negative_sites)))

        print(f"  Total tiles: {len(all_records)}")

        # Optional cap for fast test runs — stratified by canopy fraction, NEVER
        # first-N (the old cap dropped all negatives).
        if max_tiles is not None and len(all_records) > max_tiles:
            all_records = _stratified_sample(all_records, max_tiles)
            n_pos = sum(1 for r in all_records if r["canopy_frac"] > 0)
            print(f"  Capped to {len(all_records)} tiles "
                  f"({n_pos} canopy / {len(all_records) - n_pos} background, "
                  f"stratified)  bins[{_bin_histogram(all_records)}]")

        if dry_run:
            print("  Dry run — not writing tiles")
            return

    if not all_records:
        print(f"  ERROR: no tiles for {label} — skipping (run step labels first).")
        return

    # Split assignment.
    if citywide:
        # Fix 4: geographically-blocked train/val/test over the SAMPLED city
        # tiles. Fix A: curated negative-site tiles (force_keep) are pinned to
        # train and never enter the held-out split — they are guaranteed
        # background, not test material.
        forced  = [r for r in all_records if r.get("force_keep")]
        sampled = [r for r in all_records if not r.get("force_keep")]
        st = _block_partition(sampled, gsd_m=entry["gsd_cm"] / 100.0)
        n_drop = sum(1 for r in sampled if r["split"] == "drop")
        sampled = [r for r in sampled if r["split"] != "drop"]
        for r in forced:                       # curated negatives → always train
            r["split"] = "train"
            r.setdefault("block", "neg")
        all_records = sampled + forced
        if st["degraded"]:
            print(f"  ⚠ blocked split DEGRADED (blocks={st['blocks']}): no held-out "
                  f"test, random val — partial coverage / too few blocks")
        print(f"  Blocked split: train {st['train']} (+{len(forced)} neg-site) / "
              f"val {st['val']} / test {st['test']}  (dropped {n_drop} buffer "
              f"tiles; block={st['block_px']}px, buffer={CANOPY_AUTOCORR_M:.0f}m)")
    else:
        # Train/test split. Coarse 6-site years have no held-out test → all train.
        tile_names = [r["tile_name"] for r in all_records]
        site_of    = [r["site"] for r in all_records]
        if tp["has_test"] and len(set(site_of)) > 1 and len(all_records) >= 20:
            np.random.seed(RANDOM_SEED)
            train_names, _ = train_test_split(
                tile_names, test_size=tp["test_frac"], stratify=site_of,
                random_state=RANDOM_SEED)
            train_set = set(train_names)
        else:
            if tp["has_test"]:
                print("  (too few tiles/sites for a stratified test split — all train)")
            train_set = set(tile_names)
        for r in all_records:
            r["split"] = "train" if r["tile_name"] in train_set else "test"

    # Bake the LIDAR structure raster as a 4th band (co-registered per tile) when
    # enabled and the raster is present. Single injection point: every record
    # carries crs + tile_transform, so all tiling modes (city-wide / 6-site /
    # negative) get it. The HS_SOURCE tag on each image tile records which raster
    # was baked, so train/eval pick the matching normalization stats.
    # M06: in nir mode band 4 already rides on each record (read from the year's
    # own ortho during the gather), so there is no master raster to open.
    add_hs = bool(config.USE_HILLSHADE) and (nir_mode or _hillshade_ds() is not None)
    n_img_bands = 4 if add_hs else 3
    if add_hs and nir_mode:
        print(f"  + NIR band 4 from the year's own ortho (source=nir, "
              f"co-registered by construction — no reprojection)")
    elif add_hs:
        print(f"  + LIDAR hillshade band 4 from {HS_PATHS[config.HS_SOURCE].name} "
              f"(source={config.HS_SOURCE}, reprojected per tile)")
    img_base  = {"driver": "GTiff", "dtype": "uint8", "count": n_img_bands,
                 "width": TILE_SIZE, "height": TILE_SIZE, "compress": "lzw"}
    mask_base = {"driver": "GTiff", "dtype": "uint8", "count": 1,
                 "width": TILE_SIZE, "height": TILE_SIZE, "compress": "lzw",
                 "nodata": 255}
    # --aux-height: write a per-tile CHM-DN height TARGET sidecar (0=nodata), but only
    # for CHM-credible years (2015-2020); other years get no sidecar → aux loss zeros.
    write_height = bool(config.AUX_HEIGHT) and str(label) in CHM_CREDIBLE_YEARS
    height_base = {"driver": "GTiff", "dtype": "uint8", "count": 1,
                   "width": TILE_SIZE, "height": TILE_SIZE, "compress": "lzw",
                   "nodata": 0}
    if config.AUX_HEIGHT:
        print(f"  + aux-height sidecars: {'ON' if write_height else 'OFF'} "
              f"(year {label}{'' if write_height else ' — not CHM-credible'})")

    index_rows = []
    for rec in tqdm(all_records, desc="  Writing tiles"):
        split = rec["split"]
        # img_out/mask_out are the paths RECORDED IN THE INDEX — always the Drive
        # tile dir, identical to today (readers + training staging depend on the
        # /content/drive/... form). *_dst is where the bytes are actually written:
        # the very same file unless the bulk-upload path is active.
        img_out  = out_tile_dir / split / "images" / rec["tile_name"]
        mask_out = out_tile_dir / split / "masks"  / rec["tile_name"]
        img_dst  = write_dir / split / "images" / rec["tile_name"]
        mask_dst = write_dir / split / "masks"  / rec["tile_name"]
        img_tile = np.asarray(rec["_img_tile"])[:3]            # RGB (C,H,W)
        if add_hs and nir_mode:
            nir = rec.get("_nir_tile")
            if nir is None:
                raise RuntimeError(
                    f"--hs-source nir: tile {rec['tile_name']} carries no NIR "
                    f"chip — a gather path did not read band 4. Refusing to "
                    f"write a tile with a substituted 4th band.")
            img_tile = np.concatenate(
                [img_tile, np.asarray(nir)[:1]], axis=0)       # (4,H,W)
        elif add_hs:
            hs = read_hillshade_chip(rec["crs"], rec["tile_transform"],
                                     img_tile.shape[1], img_tile.shape[2])
            img_tile = np.concatenate([img_tile, hs], axis=0)  # (4,H,W)
        with rasterio.open(img_dst, "w", **{**img_base, "crs": rec["crs"],
                           "transform": rec["tile_transform"]}) as dst:
            dst.write(img_tile)
            if add_hs:
                dst.update_tags(HS_SOURCE=config.HS_SOURCE)
        with rasterio.open(mask_dst, "w", **{**mask_base, "crs": rec["crs"],
                           "transform": rec["tile_transform"]}) as dst:
            dst.write(np.asarray(rec["_mask_tile"]).squeeze(), 1)
        height_out = ""
        if write_height:
            hpath = out_tile_dir / split / "heights" / rec["tile_name"]
            hdst  = write_dir / split / "heights" / rec["tile_name"]
            hchip = read_hillshade_chip(rec["crs"], rec["tile_transform"],
                                        TILE_SIZE, TILE_SIZE)     # CHM DN (1,H,W), 0=nodata
            with rasterio.open(hdst, "w", **{**height_base, "crs": rec["crs"],
                               "transform": rec["tile_transform"]}) as dst:
                dst.write(hchip)
            height_out = str(hpath)
        index_rows.append({
            "tile_name": rec["tile_name"], "site": rec["site"], "split": split,
            "row_off": rec["row_off"], "col_off": rec["col_off"],
            "canopy_frac": rec["canopy_frac"], "block": rec.get("block", ""),
            "img_path": str(img_out), "mask_path": str(mask_out),
            "height_path": height_out,
        })

    # Bulk-upload path: every tile byte reaches Drive HERE, in one rclone copy,
    # and is verified server-side BEFORE the index/meta below are written. Raises
    # on failure, so a bad upload never gets an index or a cache-valid marker.
    if stage_root is not None:
        _bulk_upload_tiles(stage_root, remote, out_tile_dir, label)

    index_df = pd.DataFrame(index_rows)
    index_path = out_tile_dir / f"tile_index_{label}.csv"
    index_df.to_csv(index_path, index=False)
    # Sidecar signature enables idempotent reuse next session (see step_tile top).
    # Written last so an interrupted write never leaves a "valid" marker.
    if citywide:
        _meta_path(label).write_text(json.dumps(
            _tile_signature(label, stride, max_tiles, citywide)))
    n_tr = (index_df["split"] == "train").sum()
    n_va = (index_df["split"] == "val").sum()
    n_te = (index_df["split"] == "test").sum()
    print(f"  ✓ {len(index_rows)} tiles  (train {n_tr} / val {n_va} / "
          f"test {n_te})  → {index_path.name}")

