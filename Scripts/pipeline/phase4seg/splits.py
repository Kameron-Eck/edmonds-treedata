"""splits.py — train/val split construction and identification.

Split out of core.py 2026-09-01 (plan item 1 / 3.5 continuation — the losses.py
precedent). core.py re-exports every name here with a facade import, so call sites
and test monkeypatches that reach them as core.X keep working unchanged. Torch-free
by design: this cluster never touches the names _ensure_torch injects.
"""
from __future__ import annotations


import numpy as np
from sklearn.model_selection import train_test_split

from phase4seg import config  # module object: HONEST_* flags are set at RUN TIME by
                              # cli.py; a from-import would freeze them at import
from phase4seg.config import (
    CANOPY_AUTOCORR_M, HONEST_SPLIT_MODES, SPATIAL_BLOCK_SIZE_M, SPATIAL_BUFFER_PX,
    SPLIT_MODE_BLOCKED_TT, SPLIT_MODE_BUFFER_PX, SPLIT_MODE_RANDOM_TT,
    SPLIT_MODE_TRAIN_AS_VAL, SPLIT_SEED, TIER_TILE_PARAMS, TILE_SIZE,
)

# ── spatial buffer split (ported from Phase 3) ────────────────────────────────

def make_spatial_buffer_splits(df, n_folds=5, buffer_px=512, seed=42):
    from scipy.spatial.distance import cdist
    rng = np.random.RandomState(seed)
    sites = sorted(df["site"].unique())
    fold_assign = np.full(len(df), -1, dtype=int)
    for site in sites:
        idx = np.where(df["site"] == site)[0]
        for i, j in enumerate(rng.permutation(idx)):
            fold_assign[j] = i % n_folds
    folds = []
    for fold in range(n_folds):
        val_idx, tr_idx = [], []
        for site in sites:
            g = np.where(df["site"] == site)[0]
            v = g[fold_assign[g] == fold]
            o = g[fold_assign[g] != fold]
            if len(v) == 0:
                tr_idx.extend(o.tolist()); continue
            val_idx.extend(v.tolist())
            if len(o) == 0:
                continue
            d = cdist(df.iloc[o][["row_off", "col_off"]].values,
                      df.iloc[v][["row_off", "col_off"]].values, metric="chebyshev")
            md = d.min(axis=1)
            for i, j in enumerate(o):
                if md[i] >= buffer_px:
                    tr_idx.append(j)
        folds.append((np.array(tr_idx), np.array(val_idx)))
    return folds


# ── honest blocked hold-out (2026-08-29, audit T1/T2) ─────────────────────────
#
# What was wrong with the two paths above it:
#
#   T1  medium/coarse tiles OVERLAP (TILE_SIZE 512, stride 256 / 128), and the
#       spatial-buffer branch in step_train was gated on `tier_stride >=
#       TILE_SIZE`, so both tiers fell through to a plain random 15% split. Every
#       validation tile therefore shared 50% (medium) or 75% (coarse) of its
#       linear extent with a training tile. The whole 2009 campaign is medium.
#
#   T2  SPATIAL_BUFFER_PX = 512 buffers nothing even where the branch DOES run.
#       The retention test is `md[i] >= buffer_px`, and at fine stride 512 a val
#       tile's eight neighbours sit at Chebyshev distance exactly 512 — so every
#       direct neighbour is retained in train. The same config file defines
#       CANOPY_AUTOCORR_M = 520 METRES as the citywide buffer: two notions of
#       spatial independence an order of magnitude apart, one file apart.
#
# This function is the opt-in replacement: blocks on the ground, buffered in
# metres, floored at one tile so "no pixel overlap" is structural.

def make_blocked_val_split(df, gsd_m, val_frac=None, buffer_m=None,
                           block_size_m=None, seed=None):
    """Spatially BLOCKED train/val split over a training pool. Per SITE.

    Whole spatial blocks (``block_size_m`` on the ground) are held out until
    ``val_frac`` of the tiles are in val, then every train tile within
    ``buffer_m`` (Chebyshev, on the ground, floored at one TILE_SIZE) of a val
    tile is dropped. Blocks and distances are computed WITHIN each site: 6-site
    records carry row_off/col_off in their own site-crop pixel space
    (tiling.tile_site_native), so a cross-site distance is meaningless — and also
    unnecessary, since separate site crops never overlap.

    Uses its own ``np.random.RandomState(SPLIT_SEED)`` — never the global RNG,
    and never RANDOM_SEED, which ``--seed`` patches (T4).

    Returns ``(train_idx, val_idx, status)`` as positional index arrays into
    ``df``. On failure returns ``(None, None, status)`` with ``status['error']``
    set — the caller must refuse to train rather than fall back to a leaked
    split, which is the exact failure mode this replaces.
    """
    val_frac    = config.HONEST_VAL_FRAC if val_frac is None else val_frac
    buffer_m    = CANOPY_AUTOCORR_M if buffer_m is None else buffer_m
    block_size_m = SPATIAL_BLOCK_SIZE_M if block_size_m is None else block_size_m
    seed        = SPLIT_SEED if seed is None else seed

    n = len(df)
    block_px = max(TILE_SIZE, int(round(block_size_m / gsd_m)))
    buf_px   = max(buffer_m / gsd_m, float(TILE_SIZE))
    rows = df["row_off"].to_numpy()
    cols = df["col_off"].to_numpy()
    sites = df["site"].to_numpy()
    keys = [f"{s}|{int(r) // block_px}_{int(c) // block_px}"
            for s, r, c in zip(sites, rows, cols)]
    status = {"mode": SPLIT_MODE_BLOCKED_TT, "tiles": n, "block_px": block_px,
              "buffer_px": buf_px, "buffer_m": float(buffer_m),
              "sites": int(len(set(sites.tolist()))),
              "blocks": int(len(set(keys))), "val": 0, "train": 0, "dropped": 0,
              "error": ""}
    if status["blocks"] < 2:
        status["error"] = (
            f"only {status['blocks']} spatial block(s) across {status['sites']} "
            f"site(s) at block={block_px}px ({block_size_m:.0f} m / "
            f"{gsd_m * 100:.1f} cm GSD) — nothing can be held out")
        return None, None, status

    rng = np.random.RandomState(int(seed))
    uniq = sorted(set(keys))
    order = list(rng.permutation(len(uniq)))
    counts = {k: keys.count(k) for k in uniq}
    val_keys, acc = set(), 0
    for i in order:
        if acc >= val_frac * n:
            break
        val_keys.add(uniq[i]); acc += counts[uniq[i]]
    # Never hold out everything: leave at least one block on the train side.
    if len(val_keys) >= len(uniq):
        val_keys.discard(uniq[order[-1]])

    is_val = np.array([k in val_keys for k in keys], dtype=bool)
    if not is_val.any() or is_val.all():
        status["error"] = (f"block hold-out produced {int(is_val.sum())}/{n} val "
                           f"tiles from {len(uniq)} blocks — degenerate")
        return None, None, status

    # Buffer, per site: drop train tiles too close to a val tile of the SAME site.
    keep = ~is_val
    for s in sorted(set(sites.tolist())):
        in_site = sites == s
        v = np.where(in_site & is_val)[0]
        t = np.where(in_site & keep)[0]
        if len(v) == 0 or len(t) == 0:
            continue
        d = np.minimum.reduce([
            np.maximum(np.abs(rows[t] - rows[j]), np.abs(cols[t] - cols[j]))
            for j in v])
        keep[t[d < buf_px]] = False

    train_idx = np.where(keep)[0]
    val_idx   = np.where(is_val)[0]
    status["val"]     = int(len(val_idx))
    status["train"]   = int(len(train_idx))
    status["dropped"] = int(n - len(train_idx) - len(val_idx))
    if len(train_idx) == 0:
        status["error"] = (
            f"the {buffer_m:.0f} m buffer around {len(val_idx)} val tiles "
            f"consumed every one of the {n - len(val_idx)} remaining training "
            f"tiles — the pool is smaller than the canopy autocorrelation range")
        return None, None, status
    return train_idx, val_idx, status

# ══════════════════════════════════════════════════════════════════════════════
#  Which split am I actually looking at? (2026-08-29, audit T3)
#
#  tiling.py now writes a `split_mode` column into every tile index and a
#  `split_status` block into the citywide meta json. These two helpers are the
#  only readers. Reporting only — no behaviour is keyed on them; the recipe
#  boolean in step_train stays `len(val_df) > 0` exactly as before.
# ══════════════════════════════════════════════════════════════════════════════

def _index_split_mode(idx_df):
    """The split mode recorded in a tile index, or "" for an index written
    before the column existed. Constant across the index by construction; the
    first non-empty value wins, and a disagreement is surfaced rather than
    silently resolved."""
    if "split_mode" not in idx_df.columns:
        return ""
    vals = {str(v) for v in idx_df["split_mode"].dropna().tolist() if str(v)}
    if not vals:
        return ""
    if len(vals) > 1:
        print(f"  WARNING: tile index carries MIXED split_mode values {sorted(vals)} "
              f"— reporting the lot; the index was not written by one tiling run.")
        return "+".join(sorted(vals))
    return vals.pop()


def _split_mode_label(mode):
    """Human label for a persisted split mode. An index with no recorded mode
    reports UNKNOWN, never BLOCKED — that inference is the bug (T3): a random
    degraded split satisfies every test the old code applied."""
    if not mode:
        return ("UNKNOWN(legacy index, pre-2026-08-29 — mode not recorded; "
                "may be a DEGRADED random split)")
    if mode in HONEST_SPLIT_MODES:
        return f"BLOCKED({mode})"
    return f"DEGRADED/LEAKY({mode})"


def _choose_val_split(train_df, tier, gsd_m):
    """Pick the training-time train/val split for a pool with NO index-carved
    val set. Returns ``(ftr, fva, mode, notes)``; ``notes`` are lines for the
    caller to print, so this stays pure enough to diff-test.

    Lifted VERBATIM out of step_train (2026-08-29) apart from three changes,
    each visible here:

      1. the ``config.HONEST_VAL_SPLIT`` branch at the top — OPT-IN, so with the
         flag off it does not execute and what follows is the historical chain;
      2. ``random_state=SPLIT_SEED`` where the original read ``RANDOM_SEED``
         (T4). Both are 42 by default, so the default result is identical; the
         difference is that ``--seed N`` no longer re-draws the validation set
         while the run prints that the split is unchanged;
      3. the mode strings, which are new and are reporting only.

    What the historical chain does, and why it leaks:
      • fine tier (stride == TILE_SIZE): a 5-fold spatial-buffer split with a
        FIXED-PIXEL buffer of SPATIAL_BUFFER_PX = 512 — which retains every
        direct neighbour, because neighbours sit at Chebyshev exactly 512 and
        the retention test is ``>=`` (T2);
      • medium/coarse: the branch is gated on ``tier_stride >= TILE_SIZE`` and
        those tiers stride 256/128, so they fall through to a plain random 15%
        split over tiles that overlap their neighbours by 50%/75% (T1).
    """
    notes = []
    tier_stride = TIER_TILE_PARAMS[tier]["stride"]
    ftr = fva = None
    mode = ""

    # ── OPT-IN honest hold-out (T1/T2). Gated on the flag, read through
    #    `config.` because cli.py sets it at run time and the star-import
    #    binding here was frozen at import. Off ⇒ this whole block is skipped.
    if config.HONEST_VAL_SPLIT:
        tr_idx, val_idx, st = make_blocked_val_split(train_df, gsd_m)
        if tr_idx is None:
            raise RuntimeError(
                f"--honest-val-split: no honest hold-out is possible for this "
                f"{tier} pool of {len(train_df)} tiles — {st['error']}. Refusing "
                f"to fall back to the random split, which is what the flag "
                f"exists to prevent. Tile more area, or drop the flag and accept "
                f"(and report) a leaked validation set.")
        notes.append(
            f"  Val split: BLOCKED hold-out computed at train time — "
            f"{st['val']} val / {st['train']} train, {st['dropped']} buffer tiles "
            f"dropped ({st['blocks']} blocks over {st['sites']} site(s); "
            f"block={st['block_px']}px, buffer={st['buffer_m']:.0f}m"
            f"={st['buffer_px']:.0f}px)")
        return (train_df.iloc[tr_idx].reset_index(drop=True),
                train_df.iloc[val_idx].reset_index(drop=True),
                SPLIT_MODE_BLOCKED_TT, notes)

    # ── historical chain, unchanged ───────────────────────────────────────────
    if tier_stride >= TILE_SIZE and train_df["site"].nunique() > 1 and len(train_df) >= 25:
        folds = make_spatial_buffer_splits(
            train_df, n_folds=5, buffer_px=SPATIAL_BUFFER_PX, seed=42)
        tr_idx, val_idx = folds[0]
        if len(tr_idx) > 0 and len(val_idx) > 0:
            ftr = train_df.iloc[tr_idx].reset_index(drop=True)
            fva = train_df.iloc[val_idx].reset_index(drop=True)
            mode = SPLIT_MODE_BUFFER_PX
        else:
            notes.append("  (spatial-buffer split left an empty side — random split)")

    if ftr is None:
        if len(train_df) >= 7:
            # Stratify by site only when every site has ≥2 tiles (else sklearn errors).
            strat = (train_df["site"]
                     if train_df["site"].nunique() > 1
                     and train_df["site"].value_counts().min() >= 2 else None)
            ftr, fva = train_test_split(train_df, test_size=0.15,
                                        random_state=SPLIT_SEED, stratify=strat)
            ftr = ftr.reset_index(drop=True); fva = fva.reset_index(drop=True)
            mode = SPLIT_MODE_RANDOM_TT
        else:
            # Too few tiles to hold any out — validate on the training set.
            ftr = train_df.copy(); fva = train_df.copy()
            mode = SPLIT_MODE_TRAIN_AS_VAL
    return ftr, fva, mode, notes
