"""
PHASE 1B — Stratified Sampling
==========================================
Builds (or rebuilds) the review queue with a proportional rotation
across strata so that every 500-crown block gives the Phase 1D
classifier training examples from all strata.

FIRST RUN vs RE-RUN
────────────────────
On first run (no existing queue), Phase 1B loads Phase 1A's output,
filters to the ~61k "needs_review" crowns (auto_label is None),
assigns strata based on spatial/spectral rules, and builds the
initial interleaved queue.

On re-runs (queue exists + Phase 1D classifier scores available),
it re-sorts the existing queue by classifier uncertainty so the
next batch of reviews targets where the model is most confused.

STRATUM ASSIGNMENT (checked in order — first match wins)
────────────────────────────────────────────────────────
  S1  Near buildings       bldg_dist_m < 5        primary FP zone
  S3  Moderate impervious  impervious_frac >= 0.20 ambiguous surface
  S4  Spatially isolated   bldg_dist_m >= 20       far from structures
  S2  Inconsistent veg     n_veg_years < 3         broad spectral catch
  S5  Remaining ambiguous  catch-all               (currently empty)

ROTATION (per 500-crown block)
──────────────────────────────
  Stratum 1:  200  (40%)  near-building FP zone
  Stratum 3:  150  (30%)  moderate impervious
  Stratum 2:  100  (20%)  inconsistent veg
  Stratum 4:   50  (10%)  spatially isolated
  Stratum 5:    0  ( 0%)  currently empty

WITHIN-STRATUM ORDERING
────────────────────────
Crowns the classifier is most uncertain about (0.25-0.75) are
prioritised first within each stratum, followed by low-scoring
crowns (<0.25), then high-scoring (>0.75). This maximises the
information gain per review hour.

Already-reviewed crowns are excluded from the queue.

INPUTS
──────
  First run:
    phase1a/crowns_phase1a.parquet       Phase 1A auto-labeled crowns (preferred)
    phase1a/edmonds_crowns_phase1a.gpkg  Phase 1A auto-labeled crowns (fallback)
  Re-run:
    phase1b/review_queue.gpkg            Existing queue from prior run
  Optional:
    phase1d/crowns_phase1d.parquet       Classifier scores (feedback loop)
    phase1c/reviews_live.csv             Already-reviewed crowns to exclude

OUTPUTS
───────
  phase1b/review_queue.gpkg           Interleaved review queue
  phase1b/review_queue_stats.csv      Per-stratum breakdown
  phase1b/batch_{n:03d}.gpkg          1,000-crown batch files

USAGE
─────
  %run phase1b_sampling.py                    # default 1000-crown batches
  %run phase1b_sampling.py --batch-size 600
  %run phase1b_sampling.py --dry-run          # stats only
"""

import argparse
import shutil
import sys
import time
import threading
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd

# ══════════════════════════════════════════════════════════════
#  TIMING HELPERS (from phase1_preprocess.py)
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

# ══════════════════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════════════════

DRIVE_BASE    = Path("/content/drive/MyDrive/treedata")
QUEUE_GPKG    = DRIVE_BASE / "phase1b/review_queue.gpkg"
PHASE1A_GPKG  = DRIVE_BASE / "phase1a/edmonds_crowns_phase1a.gpkg"
PHASE1A_PARQUET = DRIVE_BASE / "phase1a/crowns_phase1a.parquet"
PHASE1D_GPKG  = DRIVE_BASE / "phase1d/edmonds_crowns_phase1d.gpkg"
PHASE1D_PARQUET = DRIVE_BASE / "phase1d/crowns_phase1d.parquet"
REVIEWS_CSV   = DRIVE_BASE / "phase1c/reviews_live.csv"
OUT_DIR       = DRIVE_BASE / "phase1b"
OUT_QUEUE     = OUT_DIR / "review_queue.gpkg"
OUT_QUEUE_LOCAL = Path("/content/phase1b_queue.gpkg")
OUT_STATS     = OUT_DIR / "review_queue_stats.csv"

# ── Stratum definitions ──────────────────────────────────────
# Applied to "needs_review" crowns (auto_label is None) from Phase 1A.
# Strata are mutually exclusive, checked in order (first match wins).
# Order matters: specific rules (S1, S3, S4) fire before the broad
# S2 catch, otherwise S2 (n_veg_years < 3) swallows S3/S4/S5.
#
#   S1  Near buildings      bldg_dist_m < 5       (narrowest — FP hot zone)
#   S3  Moderate impervious impervious_frac >= 0.20 (specific signal)
#   S4  Spatially isolated  bldg_dist_m >= 20       (specific signal)
#   S2  Inconsistent veg    n_veg_years < 3         (broad catch)
#   S5  Remaining ambiguous everything else          (catch-all)
#
STRATUM_DEFS = [
    (1, {"label": "Near buildings (bldg < 5m)",
         "rule":  lambda r: r["bldg_dist_m"] < 5.0}),
    (3, {"label": "Moderate impervious (imp >= 0.20)",
         "rule":  lambda r: r["impervious_frac"] >= 0.20}),
    (4, {"label": "Spatially isolated (bldg >= 20m)",
         "rule":  lambda r: r["bldg_dist_m"] >= 20.0}),
    (2, {"label": "Inconsistent veg (veg_yrs < 3)",
         "rule":  lambda r: r["n_veg_years"] < 3}),
    (5, {"label": "Remaining ambiguous",
         "rule":  lambda r: True}),   # catch-all
]

# Rotation: how many crowns from each stratum per 500-crown block.
# Rebalanced for current stratum sizes after reordering:
#   S1: 14,338 (23%)  near buildings — highest FP density
#   S3: 17,001 (28%)  moderate impervious — ambiguous surface signal
#   S4:  9,575 (16%)  spatially isolated — may be FP or real
#   S2: 20,357 (33%)  inconsistent veg — broad, many edge cases
#   S5:      0 ( 0%)  remaining ambiguous — currently empty
ROTATION = {
    1: 200,   # 40% — near-building, primary FP zone
    3: 150,   # 30% — moderate impervious
    2: 100,   # 20% — inconsistent veg
    4:  50,   # 10% — spatially isolated
    5:   0,   #  0% — currently empty (catch-all)
}
BLOCK_SIZE = sum(ROTATION.values())   # 500

# Within each stratum, priority order by classifier score band:
# 1. Uncertain (0.25-0.75) — highest information gain per label
# 2. Low (<0.25) — model thinks FP, may be wrong
# 3. High (>0.75) — model confident tree, lowest priority
def score_priority(prob):
    """Lower = higher priority."""
    if 0.25 <= prob < 0.75:
        return 0   # uncertain — highest priority
    elif prob < 0.25:
        return 1   # low — model likely wrong in this zone
    else:
        return 2   # high — model confident, lowest priority


# ══════════════════════════════════════════════════════════════
#  STRATUM ASSIGNMENT
# ══════════════════════════════════════════════════════════════

def assign_strata(crowns: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Assign stratum_id and stratum_label to each crown.
    Rules are checked in STRATUM_DEFS order — first match wins.
    """
    print(f"\n── Assigning strata ──")
    crowns = crowns.copy()
    crowns["stratum_id"]    = 0
    crowns["stratum_label"] = ""

    assigned = np.zeros(len(crowns), dtype=bool)

    for sid, sdef in STRATUM_DEFS:
        mask = crowns.apply(sdef["rule"], axis=1) & (~assigned)
        crowns.loc[mask, "stratum_id"]    = sid
        crowns.loc[mask, "stratum_label"] = sdef["label"]
        assigned |= mask.values
        print(f"  S{sid}: {mask.sum():>7,}  {sdef['label']}")

    unassigned = (~assigned).sum()
    if unassigned > 0:
        print(f"  WARNING: {unassigned:,} crowns unassigned")

    return crowns


# ══════════════════════════════════════════════════════════════
#  LOAD
# ══════════════════════════════════════════════════════════════

def load_data():
    """
    Load the review queue. Two modes:

    FIRST RUN (no existing queue):
      Load Phase 1A output → filter to auto_label == None
      (needs_review) → assign strata → use as initial queue.

    RE-RUN (queue exists):
      Load existing queue (already has strata) → re-sort with
      updated classifier scores.
    """
    print(f"\n── Loading data ──")

    # ── Try existing queue first (re-run path) ────────────────
    if QUEUE_GPKG.exists():
        tick("load queue")
        queue = gpd.read_file(QUEUE_GPKG)
        tock("load queue")
        print(f"  Existing queue   : {len(queue):,} crowns")

    # ── Bootstrap from Phase 1A output (first-run path) ──────
    else:
        print(f"  No existing queue — bootstrapping from Phase 1A output")

        if PHASE1A_PARQUET.exists():
            tick("load phase1a (parquet)")
            crowns = gpd.read_parquet(PHASE1A_PARQUET)
            tock("load phase1a (parquet)")
            print(f"  Loaded Phase 1A : {len(crowns):,} rows (from Parquet)")
        elif PHASE1A_GPKG.exists():
            tick("load phase1a (gpkg)")
            crowns = gpd.read_file(PHASE1A_GPKG)
            tock("load phase1a (gpkg)")
            print(f"  Loaded Phase 1A : {len(crowns):,} rows (from GPKG)")
        else:
            print(f"  ERROR: Phase 1A output not found.")
            print(f"    Expected: {PHASE1A_PARQUET}")
            print(f"         or : {PHASE1A_GPKG}")
            print(f"    Run phase1a_autolabel.py first.")
            sys.exit(1)

        # Check that auto_label column exists
        if "auto_label" not in crowns.columns:
            print(f"  ERROR: 'auto_label' column not found in Phase 1A output.")
            print(f"    The file may be from before Phase 1A was run.")
            print(f"    Run phase1a_autolabel.py first.")
            sys.exit(1)

        # Filter to needs-review crowns only
        needs_review = crowns[crowns["auto_label"].isna()].copy()
        print(f"  Needs review     : {len(needs_review):,} crowns "
              f"(auto_label is None)")

        if len(needs_review) == 0:
            print(f"  ERROR: no crowns need review — "
                  f"all were auto-labeled by Phase 1A")
            sys.exit(1)

        # Assign strata
        queue = assign_strata(needs_review)

    # ── Merge classifier scores (if Phase 1D has run) ─────────
    tick("load classifier scores")
    if PHASE1D_PARQUET.exists():
        phase1d = pd.read_parquet(
            PHASE1D_PARQUET,
            columns=["crown_id", "classifier_prob"])
        # Drop any existing classifier_prob before merge
        if "classifier_prob" in queue.columns:
            queue = queue.drop(columns=["classifier_prob"])
        queue = queue.merge(
            phase1d[["crown_id", "classifier_prob"]],
            on="crown_id", how="left")
        tock("load classifier scores")
        print(f"  Classifier scores: merged (from Parquet — fast)")
    elif PHASE1D_GPKG.exists():
        phase1d = gpd.read_file(PHASE1D_GPKG,
                               include_fields=["crown_id","classifier_prob"])
        if "classifier_prob" in queue.columns:
            queue = queue.drop(columns=["classifier_prob"])
        queue = queue.merge(
            phase1d[["crown_id","classifier_prob"]],
            on="crown_id", how="left")
        tock("load classifier scores")
        print(f"  Classifier scores: merged (from GPKG — slow)")
    else:
        if "classifier_prob" not in queue.columns:
            queue["classifier_prob"] = 0.5
        tock("load classifier scores")
        print(f"  Phase 1D not yet run — "
              f"using default score 0.5 (uniform priority)")

    # Fill any NaN classifier scores with 0.5
    queue["classifier_prob"] = queue["classifier_prob"].fillna(0.5)

    # ── Exclude already-reviewed crowns ───────────────────────
    reviewed_ids = set()
    if REVIEWS_CSV.exists():
        reviews = pd.read_csv(REVIEWS_CSV)
        reviews = reviews[reviews["label"] != "undo"]
        reviewed_ids = set(reviews["crown_id"].unique())
        print(f"  Already reviewed : {len(reviewed_ids):,} crowns (excluded)")

    # Exclude reviewed crowns
    queue = queue[~queue["crown_id"].isin(reviewed_ids)].copy()
    print(f"  Remaining        : {len(queue):,} crowns")

    return queue


# ══════════════════════════════════════════════════════════════
#  BUILD INTERLEAVED QUEUE
# ══════════════════════════════════════════════════════════════

def build_interleaved_queue(queue: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Build a new queue that rotates through strata every BLOCK_SIZE
    crowns, ordered within each stratum by classifier uncertainty.
    """
    print(f"\n── Building interleaved queue ──")
    print(f"  Block size : {BLOCK_SIZE} crowns")
    print(f"  Rotation   :")
    for sid, n in ROTATION.items():
        pct = 100 * n / BLOCK_SIZE
        print(f"    Stratum {sid}: {n:>3} ({pct:.0f}%)")

    # Add score priority within each stratum
    queue["score_priority"] = queue["classifier_prob"].apply(score_priority)

    # Sort each stratum by: priority band first, then median_vs_roof
    # (most ambiguous / roof-like cases first within each band)
    stratum_pools = {}
    for sid in ROTATION:
        pool = queue[queue["stratum_id"] == sid].copy()
        pool = pool.sort_values(
            ["score_priority", "median_vs_roof"],
            ascending=[True, True]
        ).reset_index(drop=True)
        stratum_pools[sid] = pool
        uncertain = ((pool["classifier_prob"] >= 0.25) &
                     (pool["classifier_prob"] < 0.75)).sum()
        low  = (pool["classifier_prob"] < 0.25).sum()
        high = (pool["classifier_prob"] >= 0.75).sum()
        print(f"\n  Stratum {sid} ({len(pool):,} remaining): "
              f"uncertain={uncertain:,}  low={low:,}  high={high:,}")

    # Interleave: take ROTATION[sid] from each stratum per block
    # until all pools are exhausted
    cursors   = {sid: 0 for sid in ROTATION}
    blocks    = []
    iteration = 0

    while True:
        block = []
        any_remaining = False
        for sid, n_per_block in ROTATION.items():
            pool   = stratum_pools[sid]
            start  = cursors[sid]
            end    = min(start + n_per_block, len(pool))
            if start < len(pool):
                any_remaining = True
                block.append(pool.iloc[start:end])
                cursors[sid] = end
        if not any_remaining:
            break
        if block:
            blocks.append(pd.concat(block, ignore_index=True))
        iteration += 1

    if not blocks:
        print("  WARNING: no crowns to queue")
        return gpd.GeoDataFrame()

    result = gpd.GeoDataFrame(
        pd.concat(blocks, ignore_index=True),
        geometry="geometry",
        crs=queue.crs
    )

    # Drop helper columns
    result = result.drop(columns=["score_priority"], errors="ignore")

    print(f"\n  Total interleaved queue : {len(result):,} crowns")
    print(f"  Blocks of {BLOCK_SIZE}        : {iteration}")

    return result


# ══════════════════════════════════════════════════════════════
#  STATS
# ══════════════════════════════════════════════════════════════

def build_stats(queue: gpd.GeoDataFrame,
                batch_size: int) -> pd.DataFrame:
    rows = []
    for sid in sorted(ROTATION.keys()):
        chunk = queue[queue["stratum_id"] == sid]
        if len(chunk) == 0:
            continue
        uncertain = ((chunk["classifier_prob"] >= 0.25) &
                     (chunk["classifier_prob"] < 0.75)).sum()
        rows.append({
            "stratum_id":       sid,
            "stratum_label":    chunk["stratum_label"].iloc[0]
                                if "stratum_label" in chunk.columns else f"S{sid}",
            "count":            len(chunk),
            "pct_of_queue":     round(100 * len(chunk) / len(queue), 1),
            "rotation_per_block": ROTATION[sid],
            "uncertain":        int(uncertain),
            "low_lt25":         int((chunk["classifier_prob"] < 0.25).sum()),
            "high_gt75":        int((chunk["classifier_prob"] >= 0.75).sum()),
            "hours":            round(len(chunk) / 1200, 1),
            "batches":          int(np.ceil(len(chunk) / batch_size)),
        })
    rows.append({
        "stratum_id":       0,
        "stratum_label":    "TOTAL",
        "count":            len(queue),
        "pct_of_queue":     100.0,
        "rotation_per_block": BLOCK_SIZE,
        "uncertain":        int(((queue["classifier_prob"] >= 0.25) &
                                  (queue["classifier_prob"] < 0.75)).sum()),
        "low_lt25":         int((queue["classifier_prob"] < 0.25).sum()),
        "high_gt75":        int((queue["classifier_prob"] >= 0.75).sum()),
        "hours":            round(len(queue) / 1200, 1),
        "batches":          int(np.ceil(len(queue) / batch_size)),
    })
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════
#  WRITE BATCHES
# ══════════════════════════════════════════════════════════════

def write_batches(queue: gpd.GeoDataFrame, batch_size: int):
    n_batches = int(np.ceil(len(queue) / batch_size))
    for i in range(n_batches):
        start = i * batch_size
        end   = min(start + batch_size, len(queue))
        batch = queue.iloc[start:end].copy()
        path  = OUT_DIR / f"batch_{i+1:03d}.gpkg"
        batch.to_file(path, driver="GPKG")
        s_counts = batch["stratum_id"].value_counts().sort_index()
        s_str = "  ".join(f"S{k}:{v}" for k, v in s_counts.items())
        print(f"  Batch {i+1:03d}: {len(batch):,} crowns  [{s_str}]")
    print(f"  {n_batches} batch files written")


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    filtered = [a for a in sys.argv[1:]
                if not (a == "-f" or a.endswith(".json"))]
    parser = argparse.ArgumentParser(
        description="Phase 1B resampling — classifier-informed queue")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(filtered)

    print("=" * 60)
    print("  PHASE 1B — Stratified Sampling (Classifier-Informed)")
    print("=" * 60)

    queue = load_data()

    print(f"\n── Classifier score breakdown by stratum ──")
    print(f"  {'St':<4} {'Stratum':<38} {'N':>7} "
          f"{'Uncertain':>10} {'Low<0.25':>10} {'High>0.75':>10}")
    print(f"  {'─'*4} {'─'*38} {'─'*7} "
          f"{'─'*10} {'─'*10} {'─'*10}")
    for sid in sorted(queue["stratum_id"].unique()):
        s = queue[queue["stratum_id"] == sid]
        label = (s["stratum_label"].iloc[0]
                 if "stratum_label" in s.columns else f"Stratum {sid}")
        u = ((s["classifier_prob"] >= 0.25) &
             (s["classifier_prob"] < 0.75)).sum()
        l = (s["classifier_prob"] < 0.25).sum()
        h = (s["classifier_prob"] >= 0.75).sum()
        print(f"  {sid:<4} {label:<38} {len(s):>7,} "
              f"{u:>10,} {l:>10,} {h:>10,}")

    new_queue = build_interleaved_queue(queue)

    if args.dry_run:
        print(f"\n  DRY RUN — no files written")
        print(f"  Re-run without --dry-run to write queue")
        sys.exit(0)

    # Write
    print(f"\n── Writing output ──")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    tick("write queue GPKG")
    new_queue.to_file(OUT_QUEUE_LOCAL, driver="GPKG")
    shutil.copy2(OUT_QUEUE_LOCAL, OUT_QUEUE)
    tock("write queue GPKG")
    print(f"  ✓ {OUT_QUEUE.name}  ({len(new_queue):,} crowns)")

    stats = build_stats(new_queue, args.batch_size)
    stats.to_csv(OUT_STATS, index=False)
    print(f"  ✓ {OUT_STATS.name}")

    if args.batch_size:
        print(f"\n── Writing batches ({args.batch_size} crowns each) ──")
        write_batches(new_queue, args.batch_size)

    # Summary
    print(f"\n── Queue summary ──")
    print(f"  {'St':<4} {'Stratum':<38} {'N':>7} "
          f"{'/block':>7} {'hrs':>5}")
    print(f"  {'─'*4} {'─'*38} {'─'*7} {'─'*7} {'─'*5}")
    for _, row in stats[stats["stratum_id"] > 0].iterrows():
        print(f"  {int(row['stratum_id']):<4} "
              f"{row['stratum_label']:<38} "
              f"{row['count']:>7,} "
              f"{row['rotation_per_block']:>7} "
              f"{row['hours']:>5.1f}")

    total = stats[stats["stratum_id"] == 0].iloc[0]
    print(f"  {'─'*4} {'─'*38} {'─'*7} {'─'*7} {'─'*5}")
    print(f"  {'TOT':<4} {'TOTAL':<38} "
          f"{int(total['count']):>7,} "
          f"{'500':>7} "
          f"{total['hours']:>5.1f}")

    print(f"""
  NEXT STEPS
  ──────────
  Load the new queue in phase1c_review.py by updating QUEUE_GPKG:
    QUEUE_GPKG = DRIVE_BASE / "phase1b/review_queue.gpkg"

  Or update phase1c_review.py to use v2 automatically:
    The script will need to be re-run to extract crops for
    any crowns not already in /content/phase1c/crops/
    (most will already exist from the original extraction)

  After every ~500 reviews, retrain Phase 1D:
    %run phase1d_classifier.py

  The rotation ensures every retrain gets examples from all strata.
""")
    timer_summary()