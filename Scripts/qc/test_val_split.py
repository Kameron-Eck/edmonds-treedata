"""Train/val split gates — audit findings T1..T4 (2026-08-29).

The audit established that the validation set is not held out, three ways:

  T1  medium/coarse tiers stride 256/128 under TILE_SIZE 512, and the
      spatial-buffer branch was gated on `tier_stride >= TILE_SIZE`, so both
      fell through to a plain random 15% split. Every val tile shared 50%
      (medium) or 75% (coarse) of its linear extent with a train tile.
  T2  SPATIAL_BUFFER_PX = 512 buffers nothing: the retention test is
      `md[i] >= buffer_px` and at fine stride 512 a val tile's eight
      neighbours sit at Chebyshev distance exactly 512, so all eight stay in
      train. CANOPY_AUTOCORR_M = 520 METRES lives in the same file.
  T3  a degraded (random, unbuffered) split was indistinguishable from a
      blocked one — the `block` column is written before the bail — and core
      printed "Val split: BLOCKED" for both. Tiling is cached, so the single
      warning never reappeared on retrain.
  T4  --seed patched the RANDOM_SEED that the random-fallback split read, so it
      silently re-drew the validation set while printing "split unchanged".

The fix lands DISABLED BY DEFAULT behind --honest-val-split, because changing
the split moves early stopping, LR scheduling and checkpoint selection, and
would make every arm trained after it incomparable with every arm before it.
This file is the proof of the three claims that matters:

  1. flag ON  ⇒ ZERO Chebyshev overlap between any val and any train tile;
  2. flag OFF ⇒ the split is IDENTICAL to the pre-change code, row order
     included, differentially against a verbatim copy of it;
  3. a degraded split reports DEGRADED — never BLOCKED, and never by omission.

Plus the two things that would make the change expensive or silently inert:
the tile signature must not move (a needless re-tile is ~20 min of GPU/year),
and the honest cache guard must not re-tile its own output forever.

Torch-free: core binds torch lazily, and nothing here touches it.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_val_split.py -q
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "pipeline"))

import phase4seg.config as config                                # noqa: E402
import phase4seg.core as core                                    # noqa: E402
import phase4seg.tiling as tiling                                # noqa: E402

TILE = config.TILE_SIZE


# ── the pre-change code, kept verbatim so the OFF path can be diffed ──────────

def _legacy_val_split(train_df, tier):
    """core.step_train's train/val selection EXACTLY as it stood before
    2026-08-29 (core.py:1279-1310 at commit b8a4e29), lifted character for
    character apart from being a function. `core.RANDOM_SEED` is read at call
    time, as the original did — that is what T4 is about.
    """
    tier_stride = config.TIER_TILE_PARAMS[tier]["stride"]
    ftr = fva = None

    if ftr is None and tier_stride >= TILE and train_df["site"].nunique() > 1 \
            and len(train_df) >= 25:
        folds = core.make_spatial_buffer_splits(
            train_df, n_folds=5, buffer_px=config.SPATIAL_BUFFER_PX, seed=42)
        tr_idx, val_idx = folds[0]
        if len(tr_idx) > 0 and len(val_idx) > 0:
            ftr = train_df.iloc[tr_idx].reset_index(drop=True)
            fva = train_df.iloc[val_idx].reset_index(drop=True)

    if ftr is None:
        if len(train_df) >= 7:
            strat = (train_df["site"]
                     if train_df["site"].nunique() > 1
                     and train_df["site"].value_counts().min() >= 2 else None)
            ftr, fva = core.train_test_split(train_df, test_size=0.15,
                                             random_state=core.RANDOM_SEED,
                                             stratify=strat)
            ftr = ftr.reset_index(drop=True); fva = fva.reset_index(drop=True)
        else:
            ftr = train_df.copy(); fva = train_df.copy()
    return ftr, fva


# ── synthetic tile pools ──────────────────────────────────────────────────────

def make_pool(sites=("SiteA", "SiteB"), grid=6, stride=256, seed=0):
    """A tile index shaped like tiling.tile_site_native's output: per-site
    pixel origins on a regular `stride` lattice, so consecutive tiles overlap
    exactly as they do on disk."""
    rng = np.random.RandomState(seed)
    rows = []
    for s in sites:
        for i in range(grid):
            for j in range(grid):
                rows.append({"tile_name": f"{s.lower()}_r{i*stride:05d}_c{j*stride:05d}.tif",
                             "site": s, "row_off": i * stride, "col_off": j * stride,
                             "canopy_frac": float(rng.rand()), "block": "",
                             "img_path": "x", "mask_path": "y", "height_path": ""})
    return pd.DataFrame(rows).reset_index(drop=True)


def min_cross_chebyshev(ftr, fva):
    """Smallest Chebyshev distance between any train tile and any val tile of the
    SAME site. Cross-site distances are meaningless (6-site records carry
    site-crop-local pixel coordinates) and are excluded."""
    best = np.inf
    for s in set(fva["site"]) & set(ftr["site"]):
        v = fva[fva["site"] == s][["row_off", "col_off"]].to_numpy()
        t = ftr[ftr["site"] == s][["row_off", "col_off"]].to_numpy()
        if not len(v) or not len(t):
            continue
        d = np.maximum(np.abs(t[:, None, 0] - v[None, :, 0]),
                       np.abs(t[:, None, 1] - v[None, :, 1]))
        best = min(best, float(d.min()))
    return best


@pytest.fixture(autouse=True)
def _restore_flags():
    """Every test starts from the shipped defaults and leaves them restored —
    these are module-level globals that cli.py patches at run time."""
    hv, seed = config.HONEST_VAL_SPLIT, core.RANDOM_SEED
    config.HONEST_VAL_SPLIT = False
    core.RANDOM_SEED = 42
    yield
    config.HONEST_VAL_SPLIT, core.RANDOM_SEED = hv, seed


# ══════════════════════════════════════════════════════════════════════════════
#  1. The default path is UNCHANGED — differential against the verbatim copy
# ══════════════════════════════════════════════════════════════════════════════

# Each case exercises a distinct branch of the historical chain.
CASES = [
    ("fine buffer branch",       dict(sites=("A", "B"), grid=6, stride=512), "fine"),
    ("fine single site",         dict(sites=("A",),     grid=6, stride=512), "fine"),
    ("fine below the 25 floor",  dict(sites=("A", "B"), grid=3, stride=512), "fine"),
    ("medium random fallback",   dict(sites=("A", "B"), grid=6, stride=256), "medium"),
    ("medium single site",       dict(sites=("A",),     grid=5, stride=256), "medium"),
    ("coarse random fallback",   dict(sites=("A", "B"), grid=4, stride=128), "coarse"),
    ("tiny pool -> train as val", dict(sites=("A",),    grid=2, stride=512), "fine"),
]


@pytest.mark.parametrize("name,kw,tier", CASES, ids=[c[0] for c in CASES])
def test_flag_off_is_identical_to_the_pre_change_code(name, kw, tier):
    """The whole premise of landing this disabled: with --honest-val-split off,
    the split must be what it has always been. Compared as ORDERED frames, not
    sets — ftr's row order feeds the sampler's weight vector and the dataset
    indexing, so a reordering is a behaviour change even at identical membership.
    """
    df = make_pool(**kw)
    want_tr, want_va = _legacy_val_split(df, tier)
    got_tr, got_va, mode, _notes = core._choose_val_split(df, tier, gsd_m=0.30)
    pd.testing.assert_frame_equal(got_tr, want_tr)
    pd.testing.assert_frame_equal(got_va, want_va)
    assert mode in (config.SPLIT_MODE_BUFFER_PX, config.SPLIT_MODE_RANDOM_TT,
                    config.SPLIT_MODE_TRAIN_AS_VAL)


def test_flag_off_covers_the_stratify_none_edge():
    """A multi-site pool where one site holds a single tile: value_counts().min()
    is 1, so sklearn would raise if stratify were passed. Both implementations
    must take the same escape."""
    df = pd.concat([make_pool(sites=("A",), grid=4, stride=256),
                    make_pool(sites=("B",), grid=1, stride=256)],
                   ignore_index=True)
    assert df["site"].value_counts().min() == 1
    want_tr, want_va = _legacy_val_split(df, "medium")
    got_tr, got_va, _m, _n = core._choose_val_split(df, "medium", gsd_m=0.30)
    pd.testing.assert_frame_equal(got_tr, want_tr)
    pd.testing.assert_frame_equal(got_va, want_va)


def test_the_differential_is_not_vacuous():
    """Guard on the guard: perturb the input and the two sides must disagree, or
    the assertions above would pass on any implementation at all."""
    df = make_pool(sites=("A", "B"), grid=6, stride=256)
    a_tr, _a_va = _legacy_val_split(df, "medium")
    b_tr, _b_va, _m, _n = core._choose_val_split(df.iloc[::-1].reset_index(drop=True),
                                                 "medium", gsd_m=0.30)
    assert list(a_tr["tile_name"]) != list(b_tr["tile_name"])


# ══════════════════════════════════════════════════════════════════════════════
#  2. T4 — --seed no longer moves the split, and the message is now true
# ══════════════════════════════════════════════════════════════════════════════

def test_seed_no_longer_redraws_the_val_split():
    df = make_pool(sites=("A", "B"), grid=6, stride=256)      # medium → random fallback
    base_tr, base_va, _m, _n = core._choose_val_split(df, "medium", gsd_m=0.30)
    core.RANDOM_SEED = 7                                      # what cli.py's --seed does
    seed_tr, seed_va, _m2, _n2 = core._choose_val_split(df, "medium", gsd_m=0.30)
    pd.testing.assert_frame_equal(seed_tr, base_tr)
    pd.testing.assert_frame_equal(seed_va, base_va)


def test_seed_used_to_redraw_the_val_split():
    """The bug, reproduced against the verbatim pre-change copy — otherwise the
    test above proves only that a constant is a constant."""
    df = make_pool(sites=("A", "B"), grid=6, stride=256)
    core.RANDOM_SEED = 42
    a_tr, _ = _legacy_val_split(df, "medium")
    core.RANDOM_SEED = 7
    b_tr, _ = _legacy_val_split(df, "medium")
    assert list(a_tr["tile_name"]) != list(b_tr["tile_name"])


def test_split_seed_is_independent_of_random_seed():
    assert config.SPLIT_SEED == 42 == config.RANDOM_SEED, \
        "SPLIT_SEED must start equal to the historical RANDOM_SEED or the " \
        "default path is not preserved"
    core.RANDOM_SEED = 999
    assert core.SPLIT_SEED == 42, "--seed must not reach the split seed"


# ══════════════════════════════════════════════════════════════════════════════
#  3. T1/T2 — flag ON gives ZERO Chebyshev overlap
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("tier,stride,gsd_m", [
    ("fine",   512, 0.15),      # T2: the fixed-512px buffer retained all 8 neighbours
    ("medium", 256, 0.299),     # T1: 50% overlap — the whole 2009 campaign
    ("coarse", 128, 0.50),      # T1: 75% overlap
])
def test_honest_split_has_zero_train_val_overlap(tier, stride, gsd_m):
    df = make_pool(sites=("A", "B"), grid=10, stride=stride)
    config.HONEST_VAL_SPLIT = True
    ftr, fva, mode, notes = core._choose_val_split(df, tier, gsd_m=gsd_m)
    assert mode == config.SPLIT_MODE_BLOCKED_TT
    assert len(ftr) > 0 and len(fva) > 0
    assert set(ftr["tile_name"]).isdisjoint(set(fva["tile_name"]))
    d = min_cross_chebyshev(ftr, fva)
    assert d >= TILE, (
        f"{tier}: nearest train tile is {d}px from a val tile — tiles are "
        f"{TILE}px, so they OVERLAP")
    # and the real promise: the metre-scale buffer, not just non-overlap.
    assert d >= config.CANOPY_AUTOCORR_M / gsd_m, (
        f"{tier}: {d}px < {config.CANOPY_AUTOCORR_M}m "
        f"({config.CANOPY_AUTOCORR_M / gsd_m:.0f}px) of canopy autocorrelation")
    assert notes and "BLOCKED" in notes[0]


def test_t2_fine_tier_retains_every_direct_neighbour():
    """T2, measured. At fine stride 512 the buffer branch DOES run, and the
    nearest retained train tile sits at Chebyshev EXACTLY 512 — a val tile's
    eight direct neighbours, kept because the retention test is `md >= 512`.
    They do not overlap; they abut, with zero of the 520 m of spatial
    independence the same config file asks for elsewhere."""
    df = make_pool(sites=("A", "B"), grid=10, stride=512)
    ftr, fva, mode, _n = core._choose_val_split(df, "fine", gsd_m=0.15)
    assert mode == config.SPLIT_MODE_BUFFER_PX
    d = min_cross_chebyshev(ftr, fva)
    assert d == TILE, f"expected the neighbour at exactly {TILE}px, got {d}"
    assert d < config.CANOPY_AUTOCORR_M / 0.15


@pytest.mark.parametrize("tier,stride,frac", [("medium", 256, 0.50), ("coarse", 128, 0.75)])
def test_t1_medium_and_coarse_val_tiles_overlap_train_tiles(tier, stride, frac):
    """T1, measured. Both tiers stride under TILE_SIZE, the buffer branch is
    gated out, and the random fallback leaves val tiles literally overlapping
    train tiles by `frac` of their linear extent."""
    df = make_pool(sites=("A", "B"), grid=10, stride=stride)
    ftr, fva, mode, _n = core._choose_val_split(df, tier, gsd_m=0.30)
    assert mode == config.SPLIT_MODE_RANDOM_TT
    d = min_cross_chebyshev(ftr, fva)
    assert d <= stride, f"{tier}: nearest train tile {d}px, expected ≤ one stride"
    assert (TILE - d) / TILE >= frac, (
        f"{tier}: overlap {(TILE - d) / TILE:.0%} of the tile, expected ≥ {frac:.0%}")


def test_honest_split_refuses_rather_than_falling_back():
    """A pool too small to hold anything out must RAISE. Silently reverting to
    the random split is the failure this flag exists to prevent."""
    config.HONEST_VAL_SPLIT = True
    df = make_pool(sites=("A",), grid=2, stride=512)     # 4 tiles, one block
    with pytest.raises(RuntimeError, match="honest-val-split"):
        core._choose_val_split(df, "fine", gsd_m=0.15)


def test_blocked_split_helper_never_uses_the_global_rng():
    """Determinism: two calls with the global RNG advanced in between must agree."""
    df = make_pool(sites=("A", "B"), grid=8, stride=256)
    a = core.make_blocked_val_split(df, gsd_m=0.30)
    np.random.seed(1); np.random.rand(1000)
    b = core.make_blocked_val_split(df, gsd_m=0.30)
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])


# ══════════════════════════════════════════════════════════════════════════════
#  4. T3 — a degraded split reports DEGRADED, and is PERSISTED
# ══════════════════════════════════════════════════════════════════════════════

def _records(n, stride=128, span=4):
    return [{"tile_name": f"t{i}.tif", "site": "city",
             "row_off": (i % span) * stride, "col_off": (i // span) * stride,
             "canopy_frac": 0.5}
            for i in range(n)]


def test_degraded_partition_is_labelled_degraded():
    recs = _records(8)                       # < 10 tiles → the early bail
    st = tiling._block_partition(recs, gsd_m=0.5)
    assert st["degraded"] is True
    assert st["mode"] == config.SPLIT_MODE_DEGRADED
    assert st["mode"] not in config.HONEST_SPLIT_MODES
    assert st["test"] == 0 and st["val"] > 0     # val rows exist — the whole T3 trap


def test_blocked_partition_is_labelled_blocked():
    # 6 well-separated blocks at 1500 m / 0.5 m = 3000 px block edge.
    recs = [{"tile_name": f"t{i}.tif", "site": "city",
             "row_off": (i // 6) * 9000, "col_off": (i % 6) * 9000,
             "canopy_frac": 0.5} for i in range(36)]
    st = tiling._block_partition(recs, gsd_m=0.5)
    assert st["degraded"] is False
    assert st["mode"] == config.SPLIT_MODE_BLOCKED
    assert st["mode"] in config.HONEST_SPLIT_MODES


def test_a_random_split_can_never_report_blocked():
    """The exact defect: core inferred BLOCKED from `len(val_df) > 0`, which a
    degraded split satisfies. Every non-honest mode, and the absent mode, must
    read as something other than BLOCKED."""
    for mode in (config.SPLIT_MODE_DEGRADED, config.SPLIT_MODE_SITEWISE,
                 config.SPLIT_MODE_ALL_TRAIN, config.SPLIT_MODE_RANDOM_TT, ""):
        label = core._split_mode_label(mode)
        assert not label.startswith("BLOCKED"), f"{mode!r} reported as {label!r}"
    assert core._split_mode_label("").startswith("UNKNOWN")
    assert core._split_mode_label(config.SPLIT_MODE_BLOCKED).startswith("BLOCKED")
    assert core._split_mode_label(config.SPLIT_MODE_DEG_BUF).startswith("BLOCKED")


def test_index_split_mode_reads_the_column_and_survives_its_absence():
    df = make_pool(sites=("A",), grid=2, stride=512)
    assert core._index_split_mode(df) == ""            # legacy index: no column
    df["split_mode"] = config.SPLIT_MODE_DEGRADED
    assert core._index_split_mode(df) == config.SPLIT_MODE_DEGRADED


def _wide_records(n=9, spacing=600):
    """Fewer than 10 tiles → _block_partition takes the early degraded bail, but
    spread wider than the 520 m buffer (1040 px at 0.5 m GSD) so a buffered
    fallback still leaves a training set."""
    return [{"tile_name": f"t{i}.tif", "site": "city",
             "row_off": 0, "col_off": i * spacing, "canopy_frac": 0.5}
            for i in range(n)]


def test_honest_flag_buffers_the_degraded_fallback():
    """Where blocking is impossible the flag still has to deliver the invariant:
    random val draw, but a buffered train side."""
    config.HONEST_VAL_SPLIT = True
    recs = _wide_records()
    st = tiling._block_partition(recs, gsd_m=0.5)
    assert st["mode"] == config.SPLIT_MODE_DEG_BUF
    assert st["mode"] in config.HONEST_SPLIT_MODES, \
        "degraded_buffered must be cache-valid or every honest run re-tiles forever"
    assert st["dropped"] > 0, "the buffer must actually have bitten in this pool"
    assert st["train"] > 0 and st["val"] > 0
    val = [(r["row_off"], r["col_off"]) for r in recs if r["split"] == "val"]
    tr = [(r["row_off"], r["col_off"]) for r in recs if r["split"] == "train"]
    for vr, vc in val:
        for tr_, tc in tr:
            assert max(abs(tr_ - vr), abs(tc - vc)) >= TILE


def test_degraded_without_the_flag_drops_nothing():
    """...and with the flag off, that same pool degrades exactly as it always
    did: every tile kept, no buffer, and it SAYS so."""
    recs = _wide_records()
    st = tiling._block_partition(recs, gsd_m=0.5)
    assert st["mode"] == config.SPLIT_MODE_DEGRADED
    assert st["dropped"] == 0
    assert all(r["split"] in ("train", "val") for r in recs)
    # and the split is IDENTICAL to the honest run's random draw — the flag adds
    # the buffer, it does not re-draw val (no extra RNG is consumed).
    off_val = {r["tile_name"] for r in recs if r["split"] == "val"}
    config.HONEST_VAL_SPLIT = True
    recs2 = _wide_records()
    tiling._block_partition(recs2, gsd_m=0.5)
    assert {r["tile_name"] for r in recs2 if r["split"] == "val"} == off_val


def test_degraded_buffer_that_empties_train_is_a_hard_error():
    """A pool narrower than the autocorrelation range: the buffer consumes every
    training tile. That must RAISE, not quietly hand back a leaked split."""
    config.HONEST_VAL_SPLIT = True
    recs = _records(9, stride=128, span=3)      # 9 tiles inside 256px ≈ 128 m
    with pytest.raises(RuntimeError, match="honest-val-split"):
        tiling._block_partition(recs, gsd_m=0.5)


def test_t5_curated_negative_tiles_skip_the_buffer_by_default():
    """T5, measured on the 19 live tile indexes: force_keep tiles are pinned to
    train BEFORE the buffer and never see it, so a curated negative-site tile can
    share pixels with a validation tile. Eight live years do exactly that (seven
    catalogued — 2000, 2002, 2005, 2006s, 2007, 2021, 2022 — plus 2022n). Here
    the mechanism is reproduced in miniature: with the flag off the overlapping
    negative tile survives into train; with it on, it is dropped."""
    def build():
        held = [{"tile_name": f"v{i}.tif", "site": "city", "row_off": 0,
                 "col_off": i * 6000, "canopy_frac": 0.5, "split": "val"}
                for i in range(3)]
        neg = [{"tile_name": "neg_parking.tif", "site": "neg:Parking",
                "row_off": 0, "col_off": 100, "canopy_frac": 0.0,
                "split": "train", "force_keep": True}]
        return held, neg

    held, neg = build()
    # 100px from a val tile at col 0 — 512px tiles, so they share ~80% of a row.
    assert max(abs(neg[0]["col_off"] - held[0]["col_off"]), 0) < TILE

    config.HONEST_VAL_SPLIT = False
    assert tiling._drop_buffered_train(neg + held, gsd_m=0.6,
                                       buffer_m=config.CANOPY_AUTOCORR_M,
                                       min_px=0) == 1, \
        "the helper itself must see the overlap — it is the pin, not the maths"

    held, neg = build()
    config.HONEST_VAL_SPLIT = True
    n = tiling._drop_buffered_train(neg + held, gsd_m=0.6,
                                    buffer_m=config.CANOPY_AUTOCORR_M,
                                    min_px=TILE)
    assert n == 1 and neg[0]["split"] == "drop"


def test_t5_fix_is_gated_on_the_flag():
    """Source-level: the negative-site buffer must sit behind the flag, or the
    default recipe silently loses curated hard negatives."""
    src = (SCRIPTS / "pipeline" / "phase4seg" / "tiling.py").read_text(encoding="utf-8")
    i = src.index("n_forced_drop = 0")
    assert "if config.HONEST_VAL_SPLIT:" in src[i:i + 200]


def test_the_writer_persists_the_mode_to_index_and_meta():
    """Source-level regression guard: step_tile must write `split_mode` into the
    index rows and `split_status` into the meta json. Nothing else in the test
    suite can reach step_tile without real imagery."""
    src = (SCRIPTS / "pipeline" / "phase4seg" / "tiling.py").read_text(encoding="utf-8")
    assert '"split_mode": split_status.get("mode", "")' in src
    assert '"split_status": split_status,' in src


# ══════════════════════════════════════════════════════════════════════════════
#  5. The cache must not move — a needless re-tile is ~20 min of GPU per year
# ══════════════════════════════════════════════════════════════════════════════

def test_the_flag_does_not_perturb_the_tile_signature():
    off = tiling._tile_signature("2009", stride=256, max_tiles=None, citywide=True)
    config.HONEST_VAL_SPLIT = True
    on = tiling._tile_signature("2009", stride=256, max_tiles=None, citywide=True)
    assert off == on, ("--honest-val-split leaked into _tile_signature — every "
                       "cached tile set on the repo would re-tile")
    assert "split_status" not in off and "honest_val_split" not in off


def _fake_cache(tmp_path, monkeypatch, meta):
    """A minimal on-disk tile set: index + the files it references + a meta json."""
    monkeypatch.setattr(tiling, "tile_dir_for", lambda label: tmp_path)
    monkeypatch.setattr(tiling, "_meta_path", lambda label: tmp_path / "meta.json")
    img, msk = tmp_path / "a_img.tif", tmp_path / "a_mask.tif"
    img.write_bytes(b"i"); msk.write_bytes(b"m")
    pd.DataFrame([{"tile_name": "a.tif", "split": "train",
                   "img_path": str(img), "mask_path": str(msk)}]
                 ).to_csv(tmp_path / "tile_index_X.csv", index=False)
    (tmp_path / "meta.json").write_text(json.dumps(meta))


SIG = {"label": "X", "citywide": True, "stride": 256}


def test_recording_split_status_does_not_invalidate_a_cache(tmp_path, monkeypatch):
    """The trap this design had to avoid: the meta json IS the signature, compared
    by whole-dict equality, so adding a field would re-tile every year on the
    first run of the new code."""
    _fake_cache(tmp_path, monkeypatch, {**SIG, "split_status": {"mode": "blocked"}})
    assert tiling._existing_tiles_valid("X", SIG) is True


def test_a_legacy_meta_without_split_status_still_validates(tmp_path, monkeypatch):
    _fake_cache(tmp_path, monkeypatch, dict(SIG))
    assert tiling._existing_tiles_valid("X", SIG) is True


@pytest.mark.parametrize("stored_mode,expect", [
    (config.SPLIT_MODE_BLOCKED,  True),    # honest cache → reuse, no re-tile
    (config.SPLIT_MODE_DEG_BUF,  True),    # its OWN output → must not re-tile forever
    (config.SPLIT_MODE_DEGRADED, False),   # leaked cache → re-tile
    (None,                       False),   # legacy index, mode unknown → re-tile
])
def test_honest_cache_guard(tmp_path, monkeypatch, stored_mode, expect):
    meta = dict(SIG) if stored_mode is None else {**SIG, "split_status": {"mode": stored_mode}}
    _fake_cache(tmp_path, monkeypatch, meta)
    config.HONEST_VAL_SPLIT = True
    assert tiling._existing_tiles_valid("X", SIG) is expect


def test_the_guard_is_inert_when_the_flag_is_off(tmp_path, monkeypatch):
    """A degraded cache is reused exactly as today when the flag is off — the
    guard must not change default behaviour, only report it."""
    _fake_cache(tmp_path, monkeypatch,
                {**SIG, "split_status": {"mode": config.SPLIT_MODE_DEGRADED}})
    assert tiling._existing_tiles_valid("X", SIG) is True
