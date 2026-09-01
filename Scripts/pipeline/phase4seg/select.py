"""select.py — checkpoint selection: raw vs K-epoch smoothed peak.

Split out of core.py 2026-09-01 (plan item 1 / 3.5 continuation — the losses.py
precedent). core.py re-exports every name here with a facade import, so call sites
and test monkeypatches that reach them as core.X keep working unchanged.

Torch-free by design (measured: no name _ensure_torch injects appears here).
The two checkpoint-file helpers it needs live in ckpt.py.
"""
from __future__ import annotations

import os

import numpy as np

import pandas as pd
from collections import deque

from phase4seg import config
from phase4seg.config import EARLY_STOP_PAT
# MODELS_DIR / OUT_DIR are read from core AT RUN TIME, not imported: the selector
# tests redirect them by patching core.MODELS_DIR / core.OUT_DIR, and a from-import
# here would freeze the real lake paths behind their backs (the facade contract
# covers writes, not just calls).
from phase4seg.common import _tag_sfx


from phase4seg.ckpt import _model_state_of, _save_ckpt_state

# ══════════════════════════════════════════════════════════════════════════════
#  Checkpoint selection: raw per-epoch peak (default) vs K-epoch smoothed peak
# ══════════════════════════════════════════════════════════════════════════════

def _centred_moving_average(values, k):
    """K-epoch CENTRED moving average, EDGE-TRUNCATED (never zero-padded).

    values[i] averages over indices [i-k//2, i+k//2] clipped to the series, so the
    first and last k//2 entries average over the shorter window that actually
    exists rather than being dropped or diluted with zeros. k=1 returns the input
    values unchanged — that identity is what makes --select-smooth 1 exactly
    today's raw-peak selection.

    ONE implementation, used by both the online selector (which needs the value
    for epoch i as soon as epoch i+k//2 has run) and the post-hoc loss-history
    column, so the CSV can never disagree with what was actually selected.
    """
    n = len(values)
    if k <= 1 or n == 0:
        return [float(v) for v in values]
    half = k // 2
    out = []
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        w = values[lo:hi]
        out.append(float(sum(w)) / len(w))
    return out


class _SmoothCkptSelector:
    """Picks the DEPLOYED epoch by the smoothed metric, holding its real weights.

    Constructed only when SELECT_SMOOTH_K > 1 — at K=1 the caller leaves this
    None and the untouched raw best-checkpoint logic is the whole story.

    Save policy (the centred-smoothing trap): the smoothed value of epoch i is
    only final once epoch i+half has run, so the decision LAGS the training loop.
    A naive implementation that picked the smoothed argmax out of the finished
    loss-history CSV would then have no weights left for that epoch and would
    deploy the wrong (or the last-saved) checkpoint. This class instead keeps a
    ring of the last `half+1` epochs' CPU weight snapshots, so the moment epoch
    i's smoothed value finalises its real weights are still in hand; the winner
    is copied out and the ring rolls on. Peak cost is (half+2) CPU copies of the
    model state (~371 MB each for the resnet101 U-Net) — reported at construction.

    Smoothing runs WITHIN a phase, not across the A→B boundary: Phase B restarts
    from the best Phase-A checkpoint, so the two series are separate trajectories
    and averaging across the seam would blend unrelated weights' scores. The
    winners are then compared ACROSS phases with the same strict >/< and the same
    A-then-B order as the raw logic, so the global pick reproduces exactly at K=1.
    """

    def __init__(self, k, maximize, model_mb=None):
        self.k = int(k)
        self.half = self.k // 2
        self.maximize = bool(maximize)
        self.ring = deque()          # [(phase, epoch, state), ...] pending finalisation
        self.raw = []                # raw metric of the CURRENT phase
        self.best = None             # winner WITHIN the current phase
        # T8 (2026-08-29): `best` used to persist across end_phase() and the
        # cross-phase comparison ran on SMOOTHED values, so a Phase B epoch whose
        # raw score was WORSE than Phase A's peak could still win and replace
        # best_ckpt. The raw rule structurally cannot do that: best_val carries
        # across the A->B boundary and B overwrites only on strict RAW improvement.
        # Fix: keep each phase's winner separately, track each phase's RAW peak, and
        # apply the raw rule's cross-phase test at selection time. Smoothing stays
        # free to pick a below-peak plateau epoch WITHIN a phase — that is its whole
        # purpose — while B can only supersede A if B genuinely beat A on raw.
        self.phase_best = {}         # phase -> (smoothed, phase, epoch, raw, state)
        self.phase_raw_peak = {}     # phase -> best RAW value seen in that phase
        est = ((self.half + 2) * model_mb / 1024.0) if model_mb else None
        print(f"  Ckpt selection: {self.k}-epoch CENTRED moving average of the "
              f"early-stop metric (edge-truncated)"
              + (f"; holds ≤{self.half + 2} CPU weight snapshots "
                 f"(~{est:.1f} GB)" if est else ""))

    # ── internals ────────────────────────────────────────────────────────────
    def _better(self, a, b):
        return a > b if self.maximize else a < b

    def _finalise(self, upto):
        """Score every ring entry whose centred window is complete (index < upto).

        Comparison is WITHIN the current phase only (self.best is cleared by
        end_phase); the cross-phase choice happens in `selection`.
        """
        sm = _centred_moving_average(self.raw, self.k)
        while self.ring and self.ring[0][1] - 1 < upto:
            phase, ep, state = self.ring.popleft()
            i = ep - 1
            if self.best is None or self._better(sm[i], self.best[0]):
                self.best = (sm[i], phase, ep, self.raw[i], state)
            peak = self.phase_raw_peak.get(phase)
            if peak is None or self._better(self.raw[i], peak):
                self.phase_raw_peak[phase] = self.raw[i]

    # ── public ───────────────────────────────────────────────────────────────
    def observe(self, phase, ep, es_val, model):
        """Record epoch `ep` (1-based) of `phase` and snapshot its weights."""
        self.raw.append(float(es_val))
        state = {kk: v.detach().to("cpu", copy=True)      # copy=True: a CPU-run
                 for kk, v in _model_state_of(model).items()}   # .cpu() would alias
        self.ring.append((phase, ep, state))
        self._finalise(len(self.raw) - self.half)         # all windows now closed

    def end_phase(self):
        """Close the phase: the trailing `half` epochs get their truncated windows,
        then bank this phase's winner and start the next phase clean (T8)."""
        self._finalise(len(self.raw))
        if self.best is not None:
            self.phase_best[self.best[1]] = self.best
        self.best = None                       # do NOT carry across the seam
        self.raw = []
        self.ring.clear()

    def _winner(self):
        """The global winner, applying the RAW rule's cross-phase test (T8).

        Within a phase the smoothed pick stands — that is what smoothing is for.
        ACROSS phases, B supersedes A only if B's RAW peak strictly beat A's, which
        is exactly the condition the raw rule uses (`best_val` carries over the
        seam and B overwrites only on strict raw improvement). Without this, a
        Phase B epoch that never matched Phase A on the real metric could still be
        deployed because its SMOOTHED value happened to be higher.
        """
        banked = dict(self.phase_best)
        if self.best is not None:                     # current, unbanked phase
            banked[self.best[1]] = self.best
        if not banked:
            return None
        if len(banked) == 1:
            return next(iter(banked.values()))
        a, b = banked.get("A"), banked.get("B")
        if a is None or b is None:
            return b or a
        pa, pb = self.phase_raw_peak.get("A"), self.phase_raw_peak.get("B")
        if pa is None or pb is None:
            return b                                   # no raw evidence; historical order
        return b if self._better(pb, pa) else a

    @property
    def selection(self):
        """(smoothed_val, phase, epoch, raw_val) of the winner, or None."""
        w = self._winner()
        return None if w is None else w[:4]

    @property
    def winner_state(self):
        """The winning epoch's weight snapshot, or None. Public because callers
        (and tests) must not reach into the private tuple — `best` is now
        phase-local and is None between phases, which is the point of T8."""
        w = self._winner()
        return None if w is None else w[4]

    def write(self, path, history, extra=None):
        """Save the winning epoch's REAL weights to `path`."""
        self.best = self._winner()          # apply the cross-phase raw rule (T8)
        if self.best is None:
            return False
        sm, phase, ep, raw, state = self.best
        # optim/sched are deliberately None: they would have to be the SELECTED
        # epoch's, and holding AdamW's two moment buffers per ring slot would
        # triple the snapshot cost for state nothing in this repo ever reads back
        # (grep: phase4seg writes optim_state, only phase0/phase3 read theirs).
        _save_ckpt_state(phase, ep, state, None, None, history, raw, path,
                         extra=extra)
        return True

    def release(self):
        self.ring.clear()
        self.best = None
        self.raw = []
        self.phase_best = {}
        self.phase_raw_peak = {}


def _state_mb(model):
    try:
        return sum(v.numel() * v.element_size()
                   for v in _model_state_of(model).values()) / 1e6
    except Exception:
        return None


def _stop_reason(es, ran, budget):
    """PATIENCE or EPOCH_CAP — the fact no run used to record.

    `es` is the epochs-since-improvement counter as the loop left it, `ran` the
    epochs actually executed, `budget` the configured cap.
    """
    if budget == 0:
        return "skipped"
    if es >= EARLY_STOP_PAT:
        return "patience"
    if ran >= budget:
        return "epoch_cap"
    return "incomplete"          # loop exited some other way (should not happen)


def _phase_smoothed(history, k):
    """Post-hoc smoothed series over the FINISHED history, smoothed within phase.

    Same _centred_moving_average the online selector used, applied per phase, so
    the CSV column is provably the series that drove the pick — not a re-derived
    approximation.
    """
    out = [None] * len(history["es_val"])
    for ph in ("A", "B"):
        idx = [i for i, p in enumerate(history["phase"]) if p == ph]
        sm = _centred_moving_average([history["es_val"][i] for i in idx], k)
        for j, i in enumerate(idx):
            out[i] = sm[j]
    return out


def _record_manifest_training(label, payload):
    """Add this year's training-stop + checkpoint-selection block to the run
    manifest. Best-effort, exactly like the manifest writer itself — provenance
    must never be able to kill a run."""
    try:
        run_id = getattr(config, "RUN_ID", None)
        if not run_id or run_id == "unrecorded":
            return
        import json as _json
        from phase4seg import core as _core   # runtime lookup — see import note
        mp = _core.OUT_DIR / "runs" / run_id / "manifest.json"
        if not mp.exists():
            return
        man = _json.loads(mp.read_text(encoding="utf-8"))
        man.setdefault("training", {})[label] = payload
        mp.write_text(_json.dumps(man, indent=2), encoding="utf-8")
    except Exception as e:                                       # noqa: BLE001
        print(f"  WARNING: training block not added to manifest ({e})")


def _deploy_smoothed_keeping_raw(sel, best_ckpt, history, extra):
    """Deploy the smoothed pick to best_ckpt, keeping the raw pick beside it.

    WHY. The raw pick and the smoothed pick come from the SAME training
    trajectory, so scoring both against the independent reference is a PAIRED
    comparison with zero retrain noise in it: the only difference between the two
    rasters is which epoch was deployed. Without this the raw pick is destroyed at
    the instant the smoothed one is written, and answering "did smoothing help?"
    costs a second training run whose own noise (~.002 AUROC, measured) is the
    size of the effect being measured. Keeping the file makes the question
    answerable for one extra inference pass (~5 min) instead of one extra train.

    ORDERING. best_ckpt must never be left missing and `deployed` must never claim
    "smoothed" while the file on disk holds the raw peak, so: write the new
    checkpoint under a temp name FIRST, then move the old one aside, then move the
    new one into place. Both renames have an ABSENT destination, which is the
    os.replace case the rclone mount canary proved. Every failure branch below
    either restores the raw pick and returns False (caller then reports "raw",
    truthfully) or deploys without keeping the pair and says so.

    To score the kept file later: copy it to sem_best_{year}_{tag}raw.pt and run
    `--step inference --run-tag {tag}raw`. Raster inference reads only the
    checkpoint and the ortho, so this needs no tiles and no retrain.
    """
    # PREFIXED, not suffixed. As sem_best_{year}_{tag}.smoothtmp.pt it matched
    # pipeline_status.py's `sem_best_{label}*.pt` glob, so a crash between write and
    # rename left something that reads as one of the arm's checkpoints and that
    # nothing ever deletes. A leading underscore keeps it out of every such glob.
    tmp = best_ckpt.with_name("_smoothtmp_" + best_ckpt.name)
    if not sel.write(tmp, history, extra=extra):
        return False
    raw_keep = best_ckpt.with_name(best_ckpt.name.replace("sem_best_", "sem_rawbest_", 1))
    try:
        # The docstring claimed both renames hit an ABSENT destination — the one
        # os.replace case the mount canary actually proved. That was true for tmp
        # and false for this one: sem_rawbest_{year}_{tag}.pt survives from any
        # earlier run of the SAME tag, so a relaunch replaces over an existing file
        # on the rclone mount, which is how the ` (1)` conflict copies appear.
        # Unlink first and the claim becomes true again.
        if raw_keep.exists():
            raw_keep.unlink()
        os.replace(best_ckpt, raw_keep)
    except OSError as e:
        print(f"  ! could not move the raw pick aside ({e}); deploying the smoothed "
              f"pick WITHOUT keeping the pair")
        try:
            os.replace(tmp, best_ckpt)
            return True
        except OSError as e2:
            print(f"  ! and could not deploy it either ({e2}) — best_ckpt still holds "
                  f"the RAW peak, reporting that rather than claiming otherwise")
            try:
                tmp.unlink()
            except OSError:
                pass
            return False
    try:
        os.replace(tmp, best_ckpt)
    except OSError as e:
        print(f"  ! smoothed pick could not be moved into place ({e}) — restoring the raw peak")
        try:
            os.replace(raw_keep, best_ckpt)
        except OSError:
            pass
        try:
            tmp.unlink()
        except OSError:
            pass
        return False
    print(f"  raw pick kept as {raw_keep.name} — score both tags for a paired read "
          f"on smoothing, with no retrain noise between them")
    return True


def _finish_selection(label, history, es_metric, es_maximize, best_val, raw_best,
                      smooth_k, sel, best_ckpt, stop_a, stop_b, ran_b,
                      val_split=None):
    """Deploy the chosen epoch, write the loss history, and record WHY it stopped.

    At K=1 `sel` is None: best_ckpt already holds the raw-peak epoch, written
    during training exactly as it always was, and nothing here rewrites it.
    """
    sm = _phase_smoothed(history, smooth_k)
    n = len(history["es_val"])
    # raw argmax/argmin in the SAME order and with the SAME strict comparison the
    # training loops used, so the first epoch to reach the peak wins ties.
    ri = mi = None                        # raw argbest, smoothed argbest
    for i in range(n):
        if ri is None or (history["es_val"][i] > history["es_val"][ri] if es_maximize
                          else history["es_val"][i] < history["es_val"][ri]):
            ri = i
        if mi is None or (sm[i] > sm[mi] if es_maximize else sm[i] < sm[mi]):
            mi = i

    def _row_of(phase, epoch, fallback):
        return next((i for i in range(n) if history["phase"][i] == phase
                     and history["epoch"][i] == epoch), fallback)

    # Default (K=1, or any failure below): the raw peak is what best_ckpt holds.
    deployed = "raw"
    sel_phase, sel_epoch = raw_best[0], raw_best[1]
    sel_row = _row_of(sel_phase, sel_epoch, ri)

    if sel is not None:
        pick = sel.selection                 # (smoothed, phase, epoch, raw)
        post = (history["phase"][mi], history["epoch"][mi]) if mi is not None else None
        if pick is None:
            print("  WARNING: --select-smooth held no epoch (no validation epochs "
                  "ran?) — leaving the raw-peak checkpoint in place.")
        else:
            # Online (lagged) pick and post-hoc pick are the SAME arithmetic on the
            # SAME numbers; a disagreement means a bug in the ring, so say so loudly
            # and deploy the online pick — its weights are the ones actually held.
            if post is not None and (pick[1], pick[2]) != post:
                print(f"  WARNING: smoothed-selection disagreement — online picked "
                      f"{pick[1]}E{pick[2]}, post-hoc {post[0]}E{post[1]}; "
                      f"deploying the online pick (it owns the weights).")
            if (pick[1], pick[2]) == (raw_best[0], raw_best[1]):
                # Same epoch: best_ckpt on disk already IS those weights, and it
                # still carries its optimiser/scheduler state. Rewriting would cost
                # a ~371 MB Drive round-trip to produce a strictly poorer file.
                deployed = "smoothed(==raw)"
                print(f"  Smoothed selection agrees with the raw peak "
                      f"({pick[1]}E{pick[2]}) — best_ckpt left exactly as written.")
            elif _deploy_smoothed_keeping_raw(sel, best_ckpt, history, extra={
                    "select_smooth_k": smooth_k, "selected_by": "smoothed",
                    "es_metric": es_metric,
                    "raw_best_phase": raw_best[0], "raw_best_epoch": raw_best[1],
                    "raw_best_val": (float(history["es_val"][ri])
                                     if ri is not None else None),
                    "sel_smooth_val": float(pick[0])}):
                deployed = "smoothed"
                sel_phase, sel_epoch = pick[1], pick[2]
                sel_row = _row_of(sel_phase, sel_epoch, sel_row)
                print(f"  ★ DEPLOYED {sel_phase}E{sel_epoch} — smoothed {es_metric}"
                      f"={pick[0]:.4f} (raw {pick[3]:.4f}); REPLACES the raw peak "
                      f"{raw_best[0]}E{raw_best[1]} "
                      f"(raw {history['es_val'][ri]:.4f}) in {best_ckpt.name}")
        sel.release()

    df = pd.DataFrame(history)
    df["es_smooth"] = sm
    df["is_raw_best"] = [1 if i == ri else 0 for i in range(n)]
    df["is_smooth_best"] = [1 if i == mi else 0 for i in range(n)]
    df["is_deployed"] = [1 if i == sel_row else 0 for i in range(n)]
    df["select_smooth_k"] = smooth_k
    df["es_metric"] = es_metric
    df["stop_reason_a"] = stop_a
    df["stop_reason_b"] = stop_b
    from phase4seg import core as _core       # runtime lookup — see import note
    df.to_csv(_core.MODELS_DIR / f"sem_loss_history_{label}{_tag_sfx()}.csv", index=False)

    def _at(i, series):
        return float(series[i]) if i is not None else None

    summary = {
        "es_metric": es_metric,
        # T3: WHICH split the early-stop metric above was measured on. Every
        # number in this summary — the selected epoch, the stop reason, best_val
        # — is conditioned on it, and until now nothing recorded it, so a run
        # scored on a leaked val set looked exactly like a run scored on a
        # blocked one. Reporting only; nothing is keyed on it.
        "val_split_mode": val_split or "unrecorded",
        "select_smooth_k": smooth_k,
        "deployed_by": deployed,
        "stop_reason_a": stop_a, "stop_reason_b": stop_b,
        "epochs_a": sum(1 for p in history["phase"] if p == "A"),
        "epochs_b": ran_b,
        "epoch_cap_a": config.EPOCHS_PHASE_A, "epoch_cap_b": config.EPOCHS_PHASE_B,
        "early_stop_patience": EARLY_STOP_PAT,
        "raw_best_phase": raw_best[0], "raw_best_epoch": raw_best[1],
        "raw_best_val": _at(ri, history["es_val"]),
        "smooth_best_phase": history["phase"][mi] if mi is not None else None,
        "smooth_best_epoch": history["epoch"][mi] if mi is not None else None,
        "smooth_best_val": _at(mi, sm),
        "deployed_phase": sel_phase, "deployed_epoch": sel_epoch,
        "deployed_raw_val": _at(sel_row, history["es_val"]),
        "deployed_smooth_val": _at(sel_row, sm),
        "best_val": (float(best_val) if best_val is not None
                     and np.isfinite(best_val) else None),
    }
    if ri is None:
        print("  Selection: no epoch produced a finite metric — nothing deployed.")
    else:
        print(f"  Selection [{deployed}]: raw peak {raw_best[0]}E{raw_best[1]}"
              f"={summary['raw_best_val']:.4f}  |  smoothed(K={smooth_k}) peak "
              f"{summary['smooth_best_phase']}E{summary['smooth_best_epoch']}"
              f"={summary['smooth_best_val']:.4f}  |  DEPLOYED "
              f"{sel_phase}E{sel_epoch} (raw={summary['deployed_raw_val']:.4f})")
    _record_manifest_training(label, summary)
    return summary
