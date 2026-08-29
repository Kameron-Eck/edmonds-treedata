"""--select-smooth / stop-reason gates (2026-08-29).

Proves the three things the smoothing change has to be true for:

  1. K=1 is BEHAVIOUR-PRESERVING — the selector picks the identical epoch the
     raw best-checkpoint rule picks, on the same series, with the same
     first-wins tie-break. (In the engine K=1 never even builds the selector,
     so this is belt-and-braces on top of the code-path guard.)
  2. K>1 picks the PLATEAU, not an outlier spike, on a synthetic noisy series
     whose raw peak is a known one-epoch artefact.
  3. The deployed checkpoint holds a REAL epoch's weights — the exact tensors
     that epoch had — never an average, and never an epoch whose weights were
     not captured. This is the one that matters: a naive implementation that
     read the smoothed argmax out of the FINISHED loss-history CSV would have
     no weights left for the winning epoch, because centred smoothing only
     finalises epoch i once epoch i+K//2 has run.

Also gates the claim that neither --select-smooth nor the epoch budgets perturb
_tile_signature (they are TRAINING params; a leak would invalidate every cached
tile set) and that the _save_ckpt -> _save_ckpt_state refactor is payload-identical.

Needs torch (CPU is fine); skipped where torch is absent, so the no-torch CI job
is unaffected.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_select_smooth.py -q
"""
import sys
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
import torch.nn as nn                                            # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "pipeline"))

import phase4seg.config as config                                # noqa: E402
import phase4seg.core as core                                    # noqa: E402

core._ensure_torch()      # core binds torch lazily at module level (the CI no-torch gate)


# ── the synthetic metric series ───────────────────────────────────────────────
# Maximised metric (val_iou_bt is the live default for every citywide/--force-
# citywide run). Phase A climbs; Phase B opens with a ONE-EPOCH SPIKE of 0.95
# sandwiched between 0.63 and 0.40 — the lucky-val-draw artefact — then settles
# onto a genuine plateau peaking at 0.84, then decays.
PHASE_A = [0.50, 0.55, 0.60, 0.62, 0.63]
PHASE_B = [0.95, 0.40, 0.41, 0.42, 0.80, 0.82, 0.84, 0.82, 0.80, 0.60, 0.55, 0.50]
SERIES = [("A", i + 1, v) for i, v in enumerate(PHASE_A)] + \
         [("B", i + 1, v) for i, v in enumerate(PHASE_B)]

RAW_PEAK = ("B", 1)          # 0.95, the spike
SMOOTH_PEAK_K5 = ("B", 7)    # 0.84, centre of the plateau


class Tiny(nn.Module):
    """Two params, so a snapshot is cheap and an epoch's weights are identifiable
    by value: every parameter is filled with that epoch's own tag."""

    def __init__(self):
        super().__init__()
        self.conv = nn.Conv2d(3, 2, 3)
        self.head = nn.Conv2d(2, 1, 1)

    def stamp(self, value):
        with torch.no_grad():
            for p in self.parameters():
                p.fill_(float(value))


class FakeCompiled(nn.Module):
    """Stands in for a torch.compile wrapper: exposes ._orig_mod and a state_dict
    whose keys carry the `_orig_mod.` prefix, exactly the shape that makes
    load_state_dict(strict=False) match NOTHING if the wrapper is captured."""

    def __init__(self, mod):
        super().__init__()
        self._orig_mod = mod


def _raw_best(series, maximize=True):
    """The engine's own rule, transcribed: strict >/< scanning A-then-B, so the
    FIRST epoch to reach the peak wins ties."""
    best_val = float("-inf") if maximize else float("inf")
    best = None
    for phase, ep, v in series:
        if (v > best_val) if maximize else (v < best_val):
            best_val, best = v, (phase, ep)
    return best, best_val


def _run_selector(k, series, model=None, maximize=True):
    """Drive the selector exactly the way step_train/_run_phase_b do."""
    model = model or Tiny()
    sel = core._SmoothCkptSelector(k, maximize, model_mb=core._state_mb(model))
    last_phase = None
    for phase, ep, v in series:
        if last_phase is not None and phase != last_phase:
            sel.end_phase()                     # A→B seam: separate trajectories
        last_phase = phase
        model.stamp(ep + (0 if phase == "A" else 100))   # A1→1 … B7→107
        sel.observe(phase, ep, v, model)
    sel.end_phase()
    return sel


# ── 1. the moving average itself ──────────────────────────────────────────────

def test_k1_moving_average_is_the_identity():
    vals = [0.1, 0.9, 0.2, 0.7]
    assert core._centred_moving_average(vals, 1) == vals


def test_window_is_edge_truncated_not_zero_padded():
    vals = [1.0, 1.0, 1.0, 1.0, 1.0]
    # Zero-padding would drag the first/last entries below 1.0.
    assert core._centred_moving_average(vals, 5) == [1.0] * 5
    # And the truncated windows are the means of what exists.
    v = [0.0, 1.0, 2.0, 3.0, 4.0]
    sm = core._centred_moving_average(v, 3)
    assert sm[0] == pytest.approx(0.5)          # mean(0,1)
    assert sm[2] == pytest.approx(2.0)          # mean(1,2,3)
    assert sm[4] == pytest.approx(3.5)          # mean(3,4)


# ── 2. K=1 reproduces the raw rule; K=5 does not ──────────────────────────────

def test_k1_selector_matches_the_raw_rule_exactly():
    expected, expected_val = _raw_best(SERIES)
    assert expected == RAW_PEAK
    sel = _run_selector(1, SERIES)
    sm, phase, ep, raw = sel.selection
    assert (phase, ep) == expected
    assert raw == pytest.approx(expected_val)
    assert sm == pytest.approx(raw)             # K=1 → smoothed IS the raw value


def test_k5_picks_the_plateau_and_disagrees_with_the_raw_peak():
    sel = _run_selector(5, SERIES)
    sm, phase, ep, raw = sel.selection
    assert (phase, ep) == SMOOTH_PEAK_K5, "K=5 must pick the plateau centre"
    assert (phase, ep) != RAW_PEAK, "the two selections must actually differ"
    assert raw == pytest.approx(0.84)           # a real epoch's real metric …
    assert sm == pytest.approx(0.816)           # … chosen on its smoothed value
    # The rejected spike really was the raw winner and really was higher.
    assert _raw_best(SERIES)[1] == pytest.approx(0.95)


def test_smoothing_does_not_cross_the_phase_seam():
    """Phase B restarts from the best Phase-A checkpoint, so the two series are
    separate trajectories. A single series smoothed across the seam would let the
    0.95 spike bleed into Phase A's tail."""
    sel = _run_selector(5, SERIES)
    a_only = core._centred_moving_average(PHASE_A, 5)
    assert a_only[-1] == pytest.approx((0.60 + 0.62 + 0.63) / 3)
    assert sel.selection[1] == "B"


# ── 3. the deployed checkpoint holds that epoch's REAL weights ────────────────

def test_written_checkpoint_is_the_selected_epochs_actual_weights(tmp_path):
    model = Tiny()
    sel = _run_selector(5, SERIES, model=model)
    sm, phase, ep, raw = sel.selection
    assert (phase, ep) == SMOOTH_PEAK_K5

    # By the time B7 is selected, training has run on to B12 and the live model
    # carries B12's weights — the whole point of the snapshot ring.
    live = next(iter(model.state_dict().values())).flatten()[0].item()
    assert live == pytest.approx(112.0)         # 100 + 12, i.e. NOT the winner

    out = tmp_path / "sem_best_test.pt"
    assert sel.write(out, {"phase": [], "epoch": []},
                     extra={"selected_by": "smoothed"})
    ck = torch.load(out, map_location="cpu", weights_only=False)

    assert ck["phase"] == "B" and ck["epoch"] == 7
    assert ck["best_val"] == pytest.approx(0.84)
    assert ck["selected_by"] == "smoothed"
    # Every tensor equals epoch B7's stamp — a real epoch, not an average of the
    # plateau (an average would land somewhere near 105-109, not exactly 107).
    for name, t in ck["model_state"].items():
        assert torch.all(t == 107.0), f"{name} is not B7's weights"

    # And it loads cleanly back into a fresh model of the same shape.
    fresh = Tiny()
    core.load_state_into(fresh, out, torch.device("cpu"))
    for p in fresh.parameters():
        assert torch.all(p == 107.0)


def test_snapshots_are_copies_not_aliases_of_the_live_cpu_model():
    """.cpu() on an already-CPU tensor returns the SAME tensor — a snapshot that
    keeps mutating with training. The ring must force copy=True."""
    model = Tiny()
    sel = core._SmoothCkptSelector(3, True, model_mb=None)
    model.stamp(1)
    sel.observe("A", 1, 0.9, model)
    model.stamp(2)                              # training moves on
    sel.observe("A", 2, 0.1, model)
    sel.observe("A", 3, 0.1, model)
    sel.end_phase()
    _, _, ep, _ = sel.selection
    assert ep == 1
    for t in sel.best[4].values():
        assert torch.all(t == 1.0), "snapshot aliased the live model"


def test_ring_unwraps_torch_compile():
    """Capturing the compiled WRAPPER prefixes every key with `_orig_mod.`, and
    load_state_into's strict=False would then silently match nothing — a
    random-init model deployed with no error raised. Guard it."""
    inner = Tiny()
    wrapped = FakeCompiled(inner)
    assert any(k.startswith("_orig_mod.") for k in wrapped.state_dict())
    assert set(core._model_state_of(wrapped)) == set(inner.state_dict())
    assert not any(k.startswith("_orig_mod.") for k in core._model_state_of(wrapped))


def test_ring_stays_bounded():
    model = Tiny()
    sel = core._SmoothCkptSelector(5, True, model_mb=None)
    for i in range(40):
        model.stamp(i)
        sel.observe("A", i + 1, 0.5 + 0.001 * i, model)
        assert len(sel.ring) <= sel.half + 1     # + the single held winner


# ── 4. stop reason ────────────────────────────────────────────────────────────

def test_stop_reason_distinguishes_patience_from_the_cap():
    pat = core.EARLY_STOP_PAT
    assert core._stop_reason(pat, 24, 30) == "patience"
    assert core._stop_reason(pat - 1, 30, 30) == "epoch_cap"
    assert core._stop_reason(0, 30, 30) == "epoch_cap"       # best epoch was LAST
    assert core._stop_reason(0, 0, 0) == "skipped"


# ── 5. neither flag may perturb the tile signature ────────────────────────────

def test_training_params_do_not_key_the_tile_signature():
    from phase4seg import tiling
    base = dict(tiling._tile_signature("2009", 256, None, True))
    saved = (config.SELECT_SMOOTH_K, config.EPOCHS_PHASE_A, config.EPOCHS_PHASE_B)
    try:
        config.SELECT_SMOOTH_K, config.EPOCHS_PHASE_A, config.EPOCHS_PHASE_B = 7, 99, 60
        assert dict(tiling._tile_signature("2009", 256, None, True)) == base
    finally:
        (config.SELECT_SMOOTH_K, config.EPOCHS_PHASE_A,
         config.EPOCHS_PHASE_B) = saved


# ── 6. the refactor on the DEFAULT path ───────────────────────────────────────

def test_save_ckpt_refactor_writes_the_same_payload(tmp_path):
    """_save_ckpt now delegates to _save_ckpt_state. Same keys, same values as the
    pre-refactor inline torch.save — this is the only default-path code change."""
    model = Tiny()
    model.stamp(3)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-4)
    sched = torch.optim.lr_scheduler.StepLR(opt, step_size=1)
    hist = {"phase": ["A"], "epoch": [1]}

    new = tmp_path / "new.pt"
    core._save_ckpt("A", 0, model, opt, sched, hist, 0.5, new)

    ref = tmp_path / "ref.pt"                       # the pre-refactor body
    torch.save({"phase": "A", "epoch": 0,
                "model_state": model.state_dict(),
                "optim_state": opt.state_dict(), "sched_state": sched.state_dict(),
                "history": hist, "best_val": 0.5,
                "in_channels": config.IN_CHANNELS,
                "aux_height_head": bool(config.AUX_HEIGHT),
                "hs_source": config.HS_SOURCE}, ref)

    a = torch.load(new, map_location="cpu", weights_only=False)
    b = torch.load(ref, map_location="cpu", weights_only=False)
    assert sorted(a) == sorted(b)
    for k in b:
        if k == "model_state":
            assert set(a[k]) == set(b[k])
            for name in b[k]:
                assert torch.equal(a[k][name], b[k][name])
        elif k in ("optim_state", "sched_state"):
            assert type(a[k]) is type(b[k])
        else:
            assert a[k] == b[k]


# ── 7. the REAL Phase-B loop + the real finish path ───────────────────────────
#  Colab-only code (torch.compile, fork workers, GPU) is out of reach locally,
#  but _run_phase_b's control flow is not: stub the two per-epoch functions and
#  the actual loop, break, stop-reason, selector wiring and return arity all run.

class TinyUnet(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = nn.Conv2d(3, 2, 3)
        self.head = nn.Conv2d(2, 1, 1)

    def stamp(self, v):
        with torch.no_grad():
            for p in self.parameters():
                p.fill_(float(v))


def _drive_phase_b(monkeypatch, tmp_path, iou_series, budget, k=1):
    """Run the real _run_phase_b over a scripted val_iou_bt series, then the real
    _finish_selection — called exactly the way step_train calls them."""
    model = TinyUnet()
    seq = iter(list(enumerate(iou_series)))
    state = {"i": 0}

    def fake_train(*a, **kw):
        state["i"] += 1
        model.stamp(100 + state["i"])            # this epoch's identifiable weights
        return 0.0, 0.1

    def fake_validate(*a, **kw):
        i, v = next(seq)
        return 0.3, v, v, 0.5                    # (v_bce, v_iou, v_iou_bt, v_thr)

    monkeypatch.setattr(core, "_train_one_epoch", fake_train)
    monkeypatch.setattr(core, "_validate", fake_validate)
    monkeypatch.setattr(core, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(config, "EPOCHS_PHASE_B", budget)
    monkeypatch.setattr(config, "EPOCHS_PHASE_A", 20)

    history = {"phase": [], "epoch": [], "train_bce": [], "val_bce": [],
               "val_iou": [], "val_iou_bt": [], "val_thr_bt": [], "es_val": []}
    raw_best = [None, None]
    sel = core._SmoothCkptSelector(k, True, model_mb=None) if k > 1 else None
    best_ckpt = tmp_path / "sem_best_x.pt"

    best_val, stop_b, ran_b = core._run_phase_b(
        model, None, None, None, torch.device("cpu"), "bce_dice",
        "val_iou_bt", True, "max", float("-inf"), best_ckpt,
        tmp_path / "sem_latest_x.pt", history, raw_best, sel)
    summary = core._finish_selection("x", history, "val_iou_bt", True, best_val,
                                     raw_best, k, sel, best_ckpt,
                                     "epoch_cap", stop_b, ran_b)
    return summary, best_ckpt, history


def test_phase_b_reports_epoch_cap_when_it_never_plateaus(monkeypatch, tmp_path):
    """The measured 2009 failure mode: still improving when the budget runs out."""
    series = [0.50 + 0.01 * i for i in range(20)]          # monotone rise
    summary, _, _ = _drive_phase_b(monkeypatch, tmp_path, series, budget=20)
    assert summary["stop_reason_b"] == "epoch_cap"
    assert summary["epochs_b"] == 20
    assert summary["raw_best_epoch"] == 20                 # best epoch was the LAST
    assert summary["deployed_by"] == "raw"


def test_phase_b_reports_patience_when_it_converges(monkeypatch, tmp_path):
    pat = core.EARLY_STOP_PAT
    series = [0.50, 0.60, 0.70] + [0.10] * (pat + 5)
    summary, _, _ = _drive_phase_b(monkeypatch, tmp_path, series, budget=40)
    assert summary["stop_reason_b"] == "patience"
    assert summary["raw_best_epoch"] == 3
    assert summary["epochs_b"] == 3 + pat


def test_finish_selection_k1_leaves_the_raw_checkpoint_untouched(monkeypatch, tmp_path):
    summary, ckpt, _ = _drive_phase_b(monkeypatch, tmp_path, PHASE_B, budget=len(PHASE_B))
    assert summary["deployed_by"] == "raw"
    assert (summary["raw_best_phase"], summary["raw_best_epoch"]) == RAW_PEAK
    assert (summary["deployed_phase"], summary["deployed_epoch"]) == RAW_PEAK
    ck = torch.load(ckpt, map_location="cpu", weights_only=False)
    assert ck["epoch"] == 0                     # _save_ckpt stores the 0-based ep
    assert ck["optim_state"] is not None        # untouched: still the full ckpt
    for t in ck["model_state"].values():
        assert torch.all(t == 101.0)            # B1's weights, the raw peak


def test_finish_selection_k5_redeploys_the_plateau_epoch(monkeypatch, tmp_path):
    summary, ckpt, history = _drive_phase_b(monkeypatch, tmp_path, PHASE_B,
                                            budget=len(PHASE_B), k=5)
    assert summary["deployed_by"] == "smoothed"
    assert (summary["raw_best_phase"], summary["raw_best_epoch"]) == RAW_PEAK
    assert (summary["deployed_phase"], summary["deployed_epoch"]) == SMOOTH_PEAK_K5
    assert summary["deployed_raw_val"] == pytest.approx(0.84)
    assert summary["deployed_smooth_val"] == pytest.approx(0.816)
    assert summary["raw_best_val"] == pytest.approx(0.95)
    ck = torch.load(ckpt, map_location="cpu", weights_only=False)
    for t in ck["model_state"].values():
        assert torch.all(t == 107.0)            # B7's REAL weights, not B1's
    # …and the CSV says so, auditably.
    import pandas as pd
    df = pd.read_csv(tmp_path / "sem_loss_history_x.csv")
    assert df.loc[df["is_raw_best"] == 1, "epoch"].tolist() == [1]
    assert df.loc[df["is_deployed"] == 1, "epoch"].tolist() == [7]
    assert df.loc[df["is_smooth_best"] == 1, "epoch"].tolist() == [7]
    assert df["select_smooth_k"].unique().tolist() == [5]
    assert set(df["stop_reason_b"]) == {"epoch_cap"}
    assert df["es_smooth"].max() == pytest.approx(0.816)


# ── 8. the run manifest gets the stop reason + the selection ──────────────────

def test_training_block_lands_in_the_run_manifest(monkeypatch, tmp_path):
    import json
    run_id = "20260829T000000Z_x_test_train"
    (tmp_path / "runs" / run_id).mkdir(parents=True)
    mp = tmp_path / "runs" / run_id / "manifest.json"
    mp.write_text(json.dumps({"run_id": run_id, "argv": []}), encoding="utf-8")
    monkeypatch.setattr(core, "OUT_DIR", tmp_path)
    monkeypatch.setattr(config, "RUN_ID", run_id, raising=False)

    core._record_manifest_training("2009", {"stop_reason_b": "epoch_cap",
                                            "raw_best_epoch": 30})
    man = json.loads(mp.read_text(encoding="utf-8"))
    assert man["run_id"] == run_id                 # pre-existing keys survive
    assert man["training"]["2009"]["stop_reason_b"] == "epoch_cap"


def test_manifest_recorder_never_raises(monkeypatch, tmp_path):
    """Provenance must not be able to kill a training run — same contract as the
    manifest writer in cli.py."""
    monkeypatch.setattr(core, "OUT_DIR", tmp_path / "nope")
    monkeypatch.setattr(config, "RUN_ID", "unrecorded", raising=False)
    core._record_manifest_training("2009", {"a": 1})
    monkeypatch.setattr(config, "RUN_ID", None, raising=False)
    core._record_manifest_training("2009", {"a": 1})
    monkeypatch.setattr(config, "RUN_ID", "missing_dir", raising=False)
    core._record_manifest_training("2009", {"a": 1})
