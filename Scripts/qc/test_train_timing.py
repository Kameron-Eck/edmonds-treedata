"""Per-epoch phase attribution in the train and evaluate steps (2026-09-07).

WHY THIS EXISTS. The epoch line has printed one wall number since phase 3 —
`A E  6/20 tr_bce=… 53s` — so a slow epoch and a starved epoch looked identical, and
`phase4/qc/hw_step_attribution.csv`'s "nothing busy 32.6% of the train step" had no
column saying WHERE in the epoch that idle sat. `core.py::_publish_epoch_phases` now
splits the epoch into data / gpu / val / save / other and publishes each as a
`⏱ <label>: <N>s` row, which is the shape `qc/instruments/harvest_timing_events.py`
already harvests into `phase4/qc/timing_events.csv`.

An instrument nobody can read is not an instrument, so what is gated here is the
CONTRACT between the printer and the harvester, not the plumbing:

  a  every label core emits parses with the harvester's own `_EVENT` regex — imported,
     not re-typed, so a regex change breaks this test instead of silently orphaning
     eight rows per epoch.
  b  the step SUMMARY line does NOT parse. It restates numbers already published one
     row each; if it were harvestable it would double every bucket in the CSV. That
     negative assertion is the one that stops a later reformat from doing it.
  c  the buckets ATTRIBUTE, they do not merely add up. `other` is defined as the
     remainder, so "the five sum to the wall" is a tautology; the stubbed loop sleeps
     a KNOWN, DIFFERENT duration in each region and each bucket has to find its own.
  d  a monkeypatched `_train_one_epoch` that ignores `phases` (the shape
     `qc/test_select_smooth.py` already uses) prints 0.0 for data/gpu and crashes
     nothing.
  e  `core.py::_tock_total` prints byte-identically to `common.py::tock`. It has to
     restate tock's format string — tock times one contiguous interval through a
     start-time dict and these buckets are sums over disjoint ones — so the
     restatement is pinned rather than trusted.
  f  importing `phase4seg.core` still does not pull torch (the no-torch CI gate); the
     epoch-end `torch.cuda.synchronize()` is guarded by `device.type == "cuda"`, so
     the CPU-stubbed Phase-B loop never touches the module-level binding either.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_train_timing.py -q
"""
import re
import subprocess
import sys as _s
import time
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
import torch.nn as nn                                            # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1]
PKG = SCRIPTS / "pipeline" / "phase4seg"      # for names.py's symbol locators

import phase4seg.config as config                                # noqa: E402
import phase4seg.core as core                                    # noqa: E402
from phase4seg import common                                     # noqa: E402
from instruments.harvest_timing_events import _EVENT             # noqa: E402

core._ensure_torch()      # core binds torch lazily at module level (the CI no-torch gate)


class TinyUnet(nn.Module):
    """Same shape `qc/test_select_smooth.py` drives `_run_phase_b` with: the `.encoder`
    attribute is load-bearing because `core.py::_unfreeze_encoder` reaches for it.
    Weights are never read back here — the subject is wall-clock accounting."""

    def __init__(self):
        super().__init__()
        self.encoder = nn.Conv2d(3, 2, 3)
        self.head = nn.Conv2d(2, 1, 1)


def _phase_rows(captured):
    """-> {label: seconds} for every harvestable ⏱ row in the captured stdout."""
    out = {}
    for line in captured.splitlines():
        m = _EVENT.search(line)
        if m:
            out[m.group(1)] = float(m.group(2))
    return out


# ── a, c: the stubbed epoch loop ──────────────────────────────────────────────

# One epoch, four regions, four DIFFERENT sleeps so no bucket can pass by picking up
# another's seconds. Long enough that the 0.1 s print resolution is not the whole
# signal; short enough that three epochs cost well under a second.
SLEEP_DATA, SLEEP_GPU, SLEEP_VAL, SLEEP_SAVE, SLEEP_OTHER = 0.20, 0.40, 0.30, 0.25, 0.15


def _stub_phase_b(monkeypatch, tmp_path, n_epochs=1, fill_phases=True):
    """Run `_run_phase_b` with every region replaced by a known sleep.

    Returns the phases dict handed in, so the caller can also check the roll-up.
    """
    model = TinyUnet()

    def fake_train(*a, **kw):
        ph = kw.get("phases")
        if fill_phases and ph is not None:
            time.sleep(SLEEP_DATA)
            ph["data"] += SLEEP_DATA
            time.sleep(SLEEP_GPU)
            ph["gpu"] += SLEEP_GPU
            # Slept but NOT attributed — the epoch loop must find this as `other`,
            # which is how the real unnamed remainder (scheduler, bookkeeping,
            # selector) reaches that bucket.
            time.sleep(SLEEP_OTHER)
        return 0.0, 0.1

    def fake_validate(*a, **kw):
        time.sleep(SLEEP_VAL)
        return 0.3, 0.5, 0.5, 0.5                # (v_bce, v_iou, v_iou_bt, v_thr)

    def fake_save(*a, **kw):
        time.sleep(SLEEP_SAVE)

    monkeypatch.setattr(core, "_train_one_epoch", fake_train)
    monkeypatch.setattr(core, "_validate", fake_validate)
    monkeypatch.setattr(core, "_save_ckpt", fake_save)
    monkeypatch.setattr(core, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(config, "EPOCHS_PHASE_B", n_epochs)

    history = {"phase": [], "epoch": [], "train_bce": [], "val_bce": [],
               "val_iou": [], "val_iou_bt": [], "val_thr_bt": [], "es_val": []}
    totals = core._new_phases()
    core._run_phase_b(model, None, None, None, torch.device("cpu"), "bce_dice",
                      "val_iou_bt", True, "max", float("-inf"),
                      tmp_path / "sem_best_x.pt", tmp_path / "sem_latest_x.pt",
                      history, [None, None], None, phases=totals)
    return totals


def test_every_epoch_label_parses_with_the_harvesters_regex(monkeypatch, tmp_path,
                                                            capsys):
    _stub_phase_b(monkeypatch, tmp_path, n_epochs=2)
    rows = _phase_rows(capsys.readouterr().out)
    for ep in (1, 2):
        for suffix in ("data", "gpu (sync at epoch end)", "val", "save", "other"):
            assert f"epoch B{ep} {suffix}" in rows, (
                f"harvest_timing_events._EVENT did not parse 'epoch B{ep} {suffix}' — "
                f"got {sorted(rows)}")


def test_each_bucket_finds_its_own_sleep(monkeypatch, tmp_path, capsys):
    """Attribution, not summation: every region slept a different known duration and
    the matching bucket has to report THAT one."""
    _stub_phase_b(monkeypatch, tmp_path, n_epochs=1)
    rows = _phase_rows(capsys.readouterr().out)
    expect = {"data": SLEEP_DATA, "gpu (sync at epoch end)": SLEEP_GPU,
              "val": SLEEP_VAL, "save": SLEEP_SAVE * 2,   # best + latest, last epoch
              "other": SLEEP_OTHER}
    for suffix, want in expect.items():
        got = rows[f"epoch B1 {suffix}"]
        assert abs(got - want) < 0.12, (
            f"bucket {suffix!r} read {got}s, expected ~{want}s — buckets are crossing")


def test_buckets_sum_to_the_epoch_wall(monkeypatch, tmp_path, capsys):
    _stub_phase_b(monkeypatch, tmp_path, n_epochs=1)
    rows = _phase_rows(capsys.readouterr().out)
    total = sum(rows[f"epoch B1 {s}"] for s in
                ("data", "gpu (sync at epoch end)", "val", "save", "other"))
    wall = SLEEP_DATA + SLEEP_GPU + SLEEP_VAL + 2 * SLEEP_SAVE + SLEEP_OTHER
    # 0.3 s: five buckets each printed at 0.1 s resolution can lose 0.05 s apiece to
    # rounding before any sleep overshoot is counted.
    assert abs(total - wall) < 0.3, f"buckets {total}s vs epoch wall ~{wall}s"


def test_totals_roll_up_across_epochs(monkeypatch, tmp_path, capsys):
    totals = _stub_phase_b(monkeypatch, tmp_path, n_epochs=3)
    capsys.readouterr()
    assert abs(totals["val"] - 3 * SLEEP_VAL) < 0.2, (
        f"step-level roll-up lost epochs: val={totals['val']}s over 3 epochs")


def test_a_stub_that_ignores_phases_still_runs(monkeypatch, tmp_path, capsys):
    """test_select_smooth's `fake_train(*a, **kw)` shape: it accepts `phases` and does
    nothing with it. The loop must publish zeros, not crash and not go negative."""
    _stub_phase_b(monkeypatch, tmp_path, n_epochs=1, fill_phases=False)
    rows = _phase_rows(capsys.readouterr().out)
    assert rows["epoch B1 data"] == 0.0
    assert rows["epoch B1 gpu (sync at epoch end)"] == 0.0
    assert all(v >= 0.0 for k, v in rows.items() if k.startswith("epoch B1 "))


# ── the split itself, not a stub of it ────────────────────────────────────────

class _SlowLoader:
    """A loader whose ITERATOR construction is slow (the shape `persistent_workers=True`
    has on epoch 1: config.NUM_WORKERS=16 processes spawning on a 12-vCPU runtime) and
    whose every `next()` is slow too."""

    def __init__(self, n, spawn_s, item_s):
        self.n, self.spawn_s, self.item_s = n, spawn_s, item_s

    def __iter__(self):
        time.sleep(self.spawn_s)
        return self._gen()

    def _gen(self):
        for i in range(self.n):
            time.sleep(self.item_s)
            yield i


def test_timed_batches_charges_iterator_time_and_only_that():
    """The one mechanism every other test here stubs past: `_timed_batches` must charge
    worker spawn AND each blocking `next()` to `data`, and must charge the CONSUMER's
    own work — the batch body, which is `gpu` — to nothing."""
    spawn, per_item, body = 0.10, 0.05, 0.05
    loader = _SlowLoader(3, spawn, per_item)
    ph = core._new_phases()
    t0 = time.perf_counter()
    for _ in core._timed_batches(loader, ph):
        time.sleep(body)
    wall = time.perf_counter() - t0

    want_data = spawn + 3 * per_item
    # Asymmetric on purpose. The LOWER bound is the proof — all four sleeps must be
    # charged to `data` — and 0.01 s keeps it tight. The upper bound is sanity only:
    # this assertion sums four sleeps' overshoot, which on a loaded shared runner
    # (the normal case here — CLAUDE.md notes parallel sessions share this tree)
    # reached 0.028 s under 12-way load and fired the old symmetric 0.05 s band once
    # (referee probe, 2026-09-07 — a historical observation, not a live measurement).
    # Over-charging is caught by the leak assertion below, not by a tight upper bound.
    assert ph["data"] >= want_data - 0.01, (
        f"data={ph['data']}s, under the {want_data}s of sleeps it must charge "
        f"(spawn {spawn} + 3 x {per_item})")
    assert ph["data"] < want_data + 0.25, (
        f"data={ph['data']}s, implausibly far above the {want_data}s of sleeps")
    assert wall - ph["data"] > 2 * body, (
        f"the consumer's {3 * body}s of batch-body work leaked into `data` "
        f"(wall {wall}s, data {ph['data']}s)")


def test_the_real_train_epoch_keeps_loader_time_out_of_gpu():
    """The REAL `_train_one_epoch`, not a fake of it, on an EMPTY loader whose iterator
    construction is slow. Nothing numeric runs (the batch body never executes), so this
    isolates the accounting: the 0.20 s spent building the iterator has to land in
    `data`, and `gpu` — defined as the epoch's wall MINUS this epoch's own data delta —
    has to come out near zero rather than absorbing it.

    `data` is pre-seeded with a prior epoch's 7.0 s to pin the `_data0` baseline: a
    version that subtracted the dict's running total instead of the delta would report
    gpu = -7.0 here.
    """
    spawn = 0.20
    ph = core._new_phases()
    ph["data"] = 7.0
    loss, seg = core._train_one_epoch(
        TinyUnet(), _SlowLoader(0, spawn, 0.0), None, None, None,
        torch.device("cpu"), phases=ph)
    assert (loss, seg) == (0.0, 0.0)                 # empty loader -> the n=0 branch
    # Same asymmetry as above: tight lower bound (the spawn must be charged), loose
    # upper (sleep overshoot under load is not the thing under test).
    assert ph["data"] >= 7.0 + spawn - 0.01, ph["data"]
    assert ph["data"] < 7.0 + spawn + 0.25, ph["data"]
    # `gpu` is the epoch wall minus this epoch's data DELTA, so it is mathematically
    # non-negative; the lower bound is what catches the baseline regression this test
    # exists for — subtracting the dict's running total would report gpu = -7.0, which
    # a bare upper bound would silently pass. The upper bound is set at half the spawn
    # so it discriminates "gpu absorbed the 0.20s setup" from ordinary python overhead
    # without sitting on a 50 ms knife-edge.
    assert -0.05 < ph["gpu"] < 0.5 * spawn, (
        f"gpu={ph['gpu']}s — the loader's {spawn}s of iterator setup was charged to the "
        f"GPU bucket, or the data baseline is the running total instead of the delta")


# ── b: the summary line must stay OUT of the harvest ──────────────────────────

def test_summary_line_is_not_harvested(capsys):
    core._print_phase_summary({"data": 12.3, "gpu": 5.1, "val": 3.0,
                               "save": 9.8, "other": 1.0})
    out = capsys.readouterr().out
    assert "train epoch phases" in out and "data=12.3s" in out
    assert _EVENT.search(out.strip()) is None, (
        "the step summary now parses as a timing EVENT — every bucket would be counted "
        "twice in timing_events.csv, once as its epoch row and once here")


# ── e: the formatter restatement is pinned to its source ──────────────────────

def test_tock_total_is_byte_identical_to_common_tock(capsys):
    label = "pinned format probe"
    common._timers[label] = time.time() - 3.0
    common.tock(label)
    ref = capsys.readouterr().out.rstrip("\n")
    m = _EVENT.search(ref)
    assert m, f"common.tock's own output no longer parses: {ref!r}"
    core._tock_total(label, float(m.group(2)))
    mine = capsys.readouterr().out.rstrip("\n")
    assert mine == ref, (
        f"core._tock_total drifted from common.tock: {mine!r} vs {ref!r}")


# ── f: torch stays lazy ───────────────────────────────────────────────────────

def test_importing_core_does_not_pull_torch():
    """phase4seg is an editable install (pyproject.toml), so the subprocess needs no
    path surgery — `qc/test_status_discovery.py::test_path_insert_ledger` is the
    ratchet that says so."""
    out = subprocess.run(
        [_s.executable, "-c",
         "import sys, phase4seg.core; print('torch' in sys.modules)"],
        capture_output=True, text=True)
    # Check the DISCRIMINATING field first. Without this, a child that never completed
    # the import produces empty stdout and the stdout assertion below reports it as
    # "torch was imported" — the opposite diagnosis, sending the reader to core.py's
    # module-level imports after a defect that is not there. Observed once on a loaded
    # runner, and CLAUDE.md notes parallel sessions share this tree, so loaded is normal.
    assert out.returncode == 0, (
        f"the no-torch probe subprocess failed rc={out.returncode}: "
        f"{out.stderr[-300:]!r} — this is a child failure, NOT a torch import")
    assert out.stdout.strip() == "False", (
        f"importing phase4seg.core pulled torch: {out.stdout!r} {out.stderr[-300:]!r}")


def test_the_epoch_end_sync_is_guarded_and_once_per_epoch():
    """Derived from the source, not asserted from memory: `_train_one_epoch` calls
    synchronize exactly once, outside the batch loop, under a cuda guard. A per-batch
    sync would drain the queue every iteration and change the throughput the
    instrument exists to measure.

    Located BY SYMBOL (`names.py::symbol_body`), never by a hardcoded engine path —
    `qc/test_status_discovery.py::test_no_gate_still_hardcodes_the_engine_file_it_checks`
    bans the path form so a gate follows a function across a module split.
    """
    import ast
    from phase4seg.names import symbol_body
    body = symbol_body(PKG, "_train_one_epoch", "function") or ""
    assert body, "_train_one_epoch not found in the engine package"
    fn = ast.parse(body).body[0]
    syncs = [n for n in ast.walk(fn)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "synchronize"]
    assert len(syncs) == 1, f"_train_one_epoch has {len(syncs)} synchronize calls"
    for loop in [n for n in ast.walk(fn) if isinstance(n, (ast.For, ast.While))]:
        assert syncs[0] not in list(ast.walk(loop)), (
            "the epoch-end sync moved INSIDE the batch loop — that changes throughput")
    guards = [n for n in ast.walk(fn) if isinstance(n, ast.If)
              and syncs[0] in list(ast.walk(n))]
    assert any("cuda" in ast.unparse(g.test) for g in guards), (
        "torch.cuda.synchronize() is no longer guarded by device.type == 'cuda' — a "
        "CPU-stubbed caller would hit the lazy torch binding")


# ── evaluate: the five labels it now emits ────────────────────────────────────

def test_evaluate_emits_its_five_timing_labels():
    """Evaluate has NO DataLoader — it reads one tile at a time with rasterio — so tile
    staging is the analog of the loader build. Source-derived (by symbol) so a renamed
    tick fails here rather than quietly dropping a row from timing_events.csv."""
    from phase4seg.names import symbol_body
    body = symbol_body(PKG, "step_evaluate", "function") or ""
    assert body, "step_evaluate not found in the engine package"
    for label in ("eval tiles local", "eval model load", "eval forward",
                  "eval metrics", "eval report"):
        assert f'tick("{label}")' in body, f"step_evaluate no longer ticks {label!r}"
        assert f'tock("{label}")' in body, f"step_evaluate no longer tocks {label!r}"
        assert _EVENT.search(f"  ⏱ {label}: 12.3s"), f"{label!r} would not harvest"


def test_no_line_numbers_in_the_new_citations():
    """CLAUDE.md 3.3: comments cite a module and a symbol, never a line number —
    `qc/test_citations_resolve.py` is the repo-wide gate; this one covers the three
    functions this change added."""
    from phase4seg.names import symbol_body
    for sym in ("_train_one_epoch", "_publish_epoch_phases", "step_evaluate"):
        body = symbol_body(PKG, sym, "function") or ""
        bad = re.findall(r"\b\w+\.py:\d+", body)
        assert not bad, f"line-number citations in {sym}: {bad}"
