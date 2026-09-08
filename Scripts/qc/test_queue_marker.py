"""The QUEUE's own step marker, and the VERIFY duration it brackets (2026-09-07).

Until now only the ENGINE published "a step is open" (pipeline_log.py::StepLogger
::_write_marker). Everything the queue does AROUND a step had no marker at all, so
vm_hwlogger stamped those samples blank and harvest_hw_attribution bucketed them as
`(between)` — hardware time attributable to nothing.

Measured 2026-09-07 on the CPU pilot, that bucket was not small and not idle: 17 min
at 44% iowait before the first step marker ever opened — 7 min of it the labels
VERIFY, 9 min the tile engine process running imports, the deps bootstrap and ortho
staging before StepLogger got control. And the ledger could not have told you either:
the queue wrote every VERIFY row with a BLANK `minutes`.

So these assert the writer side of the contract in phase4seg/names.py
::hw_step_marker_path (the reader side is qc/test_hw_marker.py):

  · `launching` is on disk BEFORE the engine process exists, carrying OUR pid
  · it is removed when the engine exits — but ONLY if it is still ours. StepLogger
    overwrites the same path with its own marker, and a queue that deleted THAT
    would blank every sample of a running engine step
  · `verifying` brackets the post-step check, and the check's wall clock now lands
    in the row's `minutes`

NOT here: queue_ledger.py::_replace_absent's EIO-after-rename branch. Those three
tests live in test_queue_verify.py, beside the D10 publish cluster they belong to.

No Drive, no GPU, no torch. HW_STEP_MARKER redirects the marker into tmp_path, which
is also what keeps the default POSIX path (/content/hw_step_marker.json — drive-
relative on Windows) from being resolved at all.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_queue_marker.py -q
"""
import json
import os
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]

q = pytest.importorskip("phase4_train_queue")
queue_ledger = pytest.importorskip("queue_ledger")
status_out_name = pytest.importorskip("phase4seg.names").status_out_name


@pytest.fixture
def marker(tmp_path, monkeypatch):
    """The marker path, redirected off /content and off the lake.

    `STATUS_OUT` is redirected too — run_step and verify flush the ledger, and
    conftest's lake guard is a detector, not a redirect. The per-launch name is
    built through names.py::status_out_name rather than spelled out, so this
    fixture cannot drift from the one formatter the queue itself uses.
    """
    p = tmp_path / "hw_step_marker.json"
    monkeypatch.setenv("HW_STEP_MARKER", str(p))
    monkeypatch.setattr(q, "QC_DIR", tmp_path)
    monkeypatch.setattr(q, "STATUS_OUT",
                        tmp_path / status_out_name("marker", "20260907T000000Z"))
    return p


def _read(p):
    return json.loads(p.read_text(encoding="utf-8"))


JOB = {"id": "j1", "year": "2019", "tag": "tg", "extra": ["--force-citywide"]}


# ── publish / clear, in isolation ─────────────────────────────────────────────

def test_publish_writes_the_full_contract_object(marker):
    """Same five keys StepLogger writes, plus the phase. `step` is joined to the
    year because that is what the ENGINE writes (cli.py: f"{step}_{lab}"), so both
    markers normalise to the same step row in the harvest."""
    queue_ledger.publish_phase_marker("tile", "2019", "tg", "launching")
    d = _read(marker)
    assert d["script"] == "phase4_train_queue"
    assert d["step"] == "tile_2019"
    assert d["run_tag"] == "tg"
    assert d["phase"] == "launching"
    assert d["pid"] == os.getpid()
    assert d["started_utc"].endswith("Z")


def test_publish_leaves_no_orphan_temp(marker):
    """StepLogger's pid-suffixed temp, and the same sweep on the way out."""
    queue_ledger.publish_phase_marker("tile", "2019", "tg", "launching")
    assert list(marker.parent.glob("*.tmp")) == []


def test_publish_never_raises_when_the_parent_is_missing(tmp_path, monkeypatch):
    """Never mkdir, never raise: a marker that can kill the queue is worse than no
    marker. A VM without the marker directory has no hardware logger reading it."""
    monkeypatch.setenv("HW_STEP_MARKER", str(tmp_path / "nope" / "m.json"))
    queue_ledger.publish_phase_marker("tile", "2019", "tg", "launching")   # no raise
    assert not (tmp_path / "nope").exists()


def test_clear_removes_only_our_own_marker(marker):
    queue_ledger.publish_phase_marker("tile", "2019", "tg", "launching")
    queue_ledger.clear_phase_marker()
    assert not marker.exists()


def test_clear_leaves_a_marker_owned_by_another_pid(marker):
    """THE ONE THAT MATTERS. StepLogger overwrites this exact path when the engine's
    step opens; deleting it would hand every sample of a running step back to
    `(between)`, which is the bucket this mechanism exists to empty."""
    marker.write_text(json.dumps(
        {"script": "phase4_semantic_finetune", "step": "tile_2019",
         "run_tag": "tg", "pid": os.getpid() + 1}), encoding="utf-8")
    queue_ledger.clear_phase_marker()
    assert marker.exists(), "the queue deleted the ENGINE's open-step marker"
    assert _read(marker)["script"] == "phase4_semantic_finetune"


def test_clear_leaves_an_unreadable_marker_alone(marker):
    """Torn or half-written is not "not ours" — it may be the engine's, mid-publish.
    Only a marker that NAMES our pid is ours to delete."""
    marker.write_text("{not json", encoding="utf-8")
    queue_ledger.clear_phase_marker()
    assert marker.exists()


def test_clear_on_an_absent_marker_is_a_noop(marker):
    queue_ledger.clear_phase_marker()                            # no raise
    assert not marker.exists()


# ── run_step: launching, published BEFORE the process exists ─────────────────

class _FakeProc:
    """Stands in for the engine. Records what was on disk at the instant Popen
    returned — which is the earliest moment the real engine's interpreter could
    have started, so anything not published by then is unattributed time."""
    seen = None

    def __init__(self, *a, **kw):
        path = os.environ["HW_STEP_MARKER"]
        try:
            with open(path, encoding="utf-8") as f:
                _FakeProc.seen = json.load(f)
        except OSError:
            _FakeProc.seen = None
        self.pid = os.getpid() + 1
        self.stdout = iter(())
        self.returncode = 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass

    def terminate(self):
        pass


def test_launching_is_on_disk_before_the_engine_process_starts(marker, monkeypatch):
    """Nine of the pilot's seventeen unattributed minutes were HERE: the engine
    process running before its StepLogger opened. If the marker is published after
    Popen, that window keeps its old blank stamp."""
    _FakeProc.seen = None
    monkeypatch.setattr(q.subprocess, "Popen", _FakeProc)
    assert q.run_step(JOB, "tile", 8, []) is True
    assert _FakeProc.seen is not None, "no marker existed when the engine started"
    assert _FakeProc.seen["step"] == "tile_2019"
    assert _FakeProc.seen["phase"] == "launching"
    assert _FakeProc.seen["run_tag"] == "tg"
    assert _FakeProc.seen["pid"] == os.getpid(), \
        "a marker carrying anything but the WRITER's live pid is discarded by " \
        "vm_hwlogger's liveness gate — see names.py::hw_step_marker_path"


def test_run_step_clears_our_launching_marker_when_the_engine_exits(marker, monkeypatch):
    """The engine here never wrote its own marker (StepLogger off-posix, or it died
    before start()). Ours is still ours, so it must not survive into the next step."""
    monkeypatch.setattr(q.subprocess, "Popen", _FakeProc)
    q.run_step(JOB, "tile", 8, [])
    assert not marker.exists()


def test_run_step_does_not_clear_the_engines_marker(marker, monkeypatch):
    """The normal case: StepLogger overwrote our marker with its own. A SIGKILLed
    engine (the queue's timeout, an OOM, preemption) leaves that behind — and it is
    vm_hwlogger's liveness gate that retires it, never the queue."""
    class _EngineWrites(_FakeProc):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            Path(os.environ["HW_STEP_MARKER"]).write_text(json.dumps(
                {"script": "phase4_semantic_finetune", "step": "tile_2019",
                 "run_tag": "tg", "pid": 999_999}), encoding="utf-8")

    monkeypatch.setattr(q.subprocess, "Popen", _EngineWrites)
    q.run_step(JOB, "tile", 8, [])
    assert marker.exists(), "the queue deleted a marker it did not write"
    assert _read(marker)["pid"] == 999_999


def test_run_step_clears_the_marker_when_popen_itself_fails(marker, monkeypatch):
    """The `finally` covers the path with no process at all. Without it a launching
    marker outlives the step it named and claims every later sample."""
    def _boom(*a, **kw):
        raise OSError("no such executable")

    monkeypatch.setattr(q.subprocess, "Popen", _boom)
    assert q.run_step(JOB, "tile", 8, []) is False
    assert not marker.exists()


# ── verify: the `verifying` bracket and the minutes that were always blank ───

def test_verify_step_brackets_itself_with_a_verifying_marker(marker, monkeypatch):
    """`labels` under --force-citywide touches no filesystem, so this measures the
    bracket and nothing else. The marker must still be up when the row is written:
    that is the interval the hardware samples and the ledger both describe."""
    seen = {}

    def _spy(rows):
        try:
            seen["marker"] = _read(marker)
        except OSError:
            seen["marker"] = None

    monkeypatch.setattr(q, "_status_write", _spy)
    rows = []
    assert q.verify_step(JOB, "labels", rows) is True
    assert seen["marker"]["step"] == "labels_2019"
    assert seen["marker"]["phase"] == "verifying"
    assert seen["marker"]["pid"] == os.getpid()
    assert not marker.exists(), "the verifying marker outlived the check"


def test_verify_step_records_its_own_minutes(marker, monkeypatch):
    """It used to be hard-blank, and blank was read as "seconds" (docs/SCHEMAS.md,
    harvest_runtime_sessions.py both say so) — an assumption, not a reading. Measured
    it holds: the pilot's labels VERIFY was ~3 s (spdc1's adjacent stamps) and the
    first rows to carry the field read 0.0 (spdc2). A number, always — even when it
    rounds to 0.0."""
    monkeypatch.setattr(q, "_status_write", lambda rows: None)
    rows = []
    q.verify_step(JOB, "labels", rows)
    assert rows[-1]["step"] == "VERIFY:labels"
    assert isinstance(rows[-1]["minutes"], float), rows[-1]["minutes"]


def test_job_end_verify_brackets_and_times_itself(marker, monkeypatch):
    """The steps-subset early return is still a VERIFY row and still gets a number.

    Its marker step is `VERIFY`, not the step whose artifact it reads: this check
    runs after ALL of a job's steps, so folding it into `inference` would bill
    post-postproc time to a step that had already ended."""
    seen = {}
    monkeypatch.setattr(q, "_status_write",
                        lambda rows: seen.update(marker=_read(marker)))
    job = dict(JOB, steps=["labels", "tile"])
    rows = []
    assert q.verify(job, rows) is True
    assert seen["marker"]["step"] == "VERIFY_2019"
    assert seen["marker"]["phase"] == "verifying"
    assert isinstance(rows[-1]["minutes"], float)
    assert not marker.exists()


def test_job_end_verify_clears_its_marker_even_on_the_raster_path(marker, monkeypatch):
    """The MASKS path is redirected at tmp_path, so _check_prob_raster reports
    MISSING — a hard fail, and the marker must still come down."""
    monkeypatch.setattr(q, "MASKS", marker.parent)
    monkeypatch.setattr(q, "_status_write", lambda rows: None)
    rows = []
    assert q.verify(JOB, rows) is False
    assert rows[-1]["state"] == "MISSING"
    assert isinstance(rows[-1]["minutes"], float)
    assert not marker.exists()


def test_recheck_skipped_verify_times_and_brackets_itself(marker, monkeypatch):
    """D9's stat-only re-check writes the same `step="VERIFY"` row as verify(), so
    it must claim the same harvest bucket — two spellings of one activity would
    split it across two rows."""
    seen = {}
    monkeypatch.setattr(q, "MASKS", marker.parent)
    monkeypatch.setattr(q, "_status_write",
                        lambda rows: seen.update(marker=_read(marker)))
    rows = []
    q._recheck_skipped_verify(JOB, rows, ("OK", "146MB valid", "2026-09-01 00:00:00"))
    assert seen["marker"]["step"] == "VERIFY_2019"
    assert seen["marker"]["phase"] == "verifying"
    assert isinstance(rows[-1]["minutes"], float)
    assert not marker.exists()


# ── the readers of `minutes` still behave ────────────────────────────────────

def test_cost_report_still_excludes_verify_rows_from_step_minutes():
    """VERIFY rows now carry a number, and cost_report sums `minutes` to apportion
    real money across arms. It filters on the STEP NAME, so the new numbers cannot
    inflate a bill — asserted here rather than assumed, because the filter is the
    only thing standing between a VERIFY minute and a GPU-cost line."""
    cost_report = pytest.importorskip("cost_report")
    assert cost_report._is_verify("VERIFY")
    assert cost_report._is_verify("VERIFY:train")
    assert not cost_report._is_verify("train")


def test_offload_compare_step_minutes_reads_step_rows_only(tmp_path):
    """offload_pilot_compare's `step_minutes` metric is the queue's own wall clock
    per STEP. It matches the step name exactly, so `VERIFY:train` cannot be read as
    `train` — the pilot comparison keeps measuring the same bracket it always did."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_ofc", SCRIPTS / "qc" / "instruments" / "offload_pilot_compare.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    rows = [{"step": "train", "state": "OK", "minutes": "40.0",
             "host": "h", "session": "s", "_file": "f.csv"},
            {"step": "VERIFY:train", "state": "OK", "minutes": "7.0",
             "host": "h", "session": "s", "_file": "f.csv"}]
    value, _src, _note = m.step_minutes(rows, "train")
    assert value == "40.0", "a VERIFY row was read as its step's time"
