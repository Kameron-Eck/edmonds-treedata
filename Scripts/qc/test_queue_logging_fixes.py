"""The 2026-09-08 logging blocks, each shown to fire on the input that used to slip.

Three things went dark during the healing campaign and each is pinned here:

  * healC finished heal_2020, printed VERIFY:postproc OK, and then re-opened the 4.1 GB
    prob raster through the mount for the job-level check with no line announcing it
    and no bound — silent for 30+ minutes, heal_2022 never started. verify() now reuses
    the VERIFY:inference verdict on a size match and announces the slow path when it
    must read.
  * the shared-ledger fallback in queue_ledger._status_write — the mechanism that
    erased six days — is gone: no STATUS_OUT means no write, said out loud.
  * landed.py accepts --no-lake; without it an unmounted lake is a failed rung (the
    branch is exercised through main() with lake.BASE pointed at nowhere).

No Drive, no GPU, no torch.  Run: PYTHONUTF8=1 py -3.12 -m pytest qc/test_queue_logging_fixes.py -q
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
q = pytest.importorskip("phase4_train_queue")
ql = pytest.importorskip("queue_ledger")

JOB = dict(id="heal_infill_2017_2023_heal_2020", year="2020", tag="heal_2020")


def _rows_with_inference(state="OK", mb=100):
    return [dict(job=JOB["id"], year="2020", tag="heal_2020", step="inference", state="OK",
                 detail="", ts="2026-09-08 17:19:41"),
            dict(job=JOB["id"], year="2020", tag="heal_2020", step="VERIFY:inference",
                 state=state, detail=f"{mb}MB valid=73.0% maxprob=0.787 p99.9=0.724 [2387x1674 sample]",
                 ts="2026-09-08 18:20:56")]


def _raster(tmp_path, mb):
    p = tmp_path / "masks" / "edmonds_canopy_prob_2020_heal_2020.tif"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\0" * int(mb * 1e6))
    return p


# ── the stall: the job-level verify re-reading a multi-GB raster ─────────────────

def test_prior_inference_verdict_is_reused_on_a_size_match(tmp_path):
    out = _raster(tmp_path, 100)
    got = q._prior_inference_verdict(JOB, _rows_with_inference(), out)
    assert got is not None
    state, detail = got
    assert state == "OK"
    assert detail.startswith("100MB ")                      # the parser anchor survives
    assert "reused-from-inference" in detail and "no re-read" in detail


def test_prior_verdict_is_not_reused_when_the_size_moved(tmp_path):
    """MUTATION. A raster that grew or shrank since inference must be read again."""
    out = _raster(tmp_path, 104)                            # +4 %, beyond the 1 % tolerance
    assert q._prior_inference_verdict(JOB, _rows_with_inference(mb=100), out) is None


def test_prior_verdict_is_not_reused_for_a_hard_failure_or_another_job(tmp_path):
    out = _raster(tmp_path, 100)
    hard = next(iter(q._VERIFY_HARD_FAIL))
    assert q._prior_inference_verdict(JOB, _rows_with_inference(state=hard), out) is None
    other = dict(JOB, id="some_other_job")
    assert q._prior_inference_verdict(other, _rows_with_inference(), out) is None


def test_verify_skips_the_read_and_says_so(tmp_path, monkeypatch, capsys):
    """The queue must never again open the raster in silence: with a prior verdict
    the read does not happen at all (a raising stand-in proves it), and the ledger
    row carries the reused verdict with its anchor intact."""
    monkeypatch.setattr(q, "MASKS", tmp_path / "masks")
    monkeypatch.setattr(q, "QC_DIR", tmp_path)
    monkeypatch.setattr(q, "STATUS_OUT", tmp_path / "train_queue_status_t.csv")
    monkeypatch.setattr(q, "publish_phase_marker", lambda *a, **k: None)
    monkeypatch.setattr(q, "clear_phase_marker", lambda *a, **k: None)
    _raster(tmp_path, 100)

    def boom(*a, **k):
        raise AssertionError("the raster was re-read")
    monkeypatch.setattr(q, "_check_prob_raster", boom)
    rows = _rows_with_inference()
    assert q.verify(dict(JOB), rows) is True
    rec = rows[-1]
    assert rec["step"] == "VERIFY" and rec["state"] == "OK"
    assert rec["detail"].startswith("100MB reused-from-inference")
    assert "reusing VERIFY:inference" in capsys.readouterr().out


def test_verify_announces_the_slow_path_before_reading(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(q, "MASKS", tmp_path / "masks")
    monkeypatch.setattr(q, "QC_DIR", tmp_path)
    monkeypatch.setattr(q, "STATUS_OUT", tmp_path / "train_queue_status_t.csv")
    monkeypatch.setattr(q, "publish_phase_marker", lambda *a, **k: None)
    monkeypatch.setattr(q, "clear_phase_marker", lambda *a, **k: None)
    _raster(tmp_path, 100)
    seen = []
    monkeypatch.setattr(q, "_check_prob_raster", lambda out: (seen.append(out), ("OK", "100MB fresh read"))[1])
    rows = []                                               # no prior verdict this launch
    assert q.verify(dict(JOB), rows) is True
    assert seen, "the read must happen when there is nothing to reuse"
    out = capsys.readouterr().out
    assert "reading edmonds_canopy_prob_2020_heal_2020.tif" in out and "slow path" in out


# ── the erased-ledger mechanism: no fallback to the shared file ────────────────

def test_status_write_refuses_the_shared_ledger_when_no_launch_file(tmp_path, monkeypatch, capsys):
    """MUTATION of the 2026-09-01..07 erasure. With STATUS_OUT unset the old code
    rewrote the shared train_queue_status.csv with this launch's rows; now nothing is
    written and the refusal is printed."""
    monkeypatch.setattr(q, "QC_DIR", tmp_path)
    shared = tmp_path / "train_queue_status.csv"
    shared.write_text("job,year,tag,step,state,exit,minutes,detail,ts,host,session\n"
                      "old,2009,x,train,OK,0,1.0,history,2026-09-01 00:00:00,h,s\n", encoding="utf-8")
    monkeypatch.setattr(q, "STATUS", shared)
    monkeypatch.setattr(q, "STATUS_OUT", None)
    monkeypatch.setattr(ql, "_q", lambda: q)
    before = shared.read_bytes()
    ql._status_write([dict(job="new", year="2020", tag="t", step="tile", state="OK")])
    assert shared.read_bytes() == before, "the shared ledger was rewritten"
    assert list(tmp_path.glob("*.part.*")) == []
    assert "refusing the shared ledger" in capsys.readouterr().out


def test_status_write_still_writes_the_launch_file(tmp_path, monkeypatch):
    monkeypatch.setattr(q, "QC_DIR", tmp_path)
    monkeypatch.setattr(q, "STATUS", tmp_path / "train_queue_status.csv")
    launch = tmp_path / "train_queue_status_queue_x_20260908T000000Z.csv"
    monkeypatch.setattr(q, "STATUS_OUT", launch)
    monkeypatch.setattr(ql, "_q", lambda: q)
    ql._status_write([dict(job="new", year="2020", tag="t", step="tile", state="OK")])
    assert launch.exists() and "new,2020,t,tile,OK" in launch.read_text(encoding="utf-8")
    assert not (tmp_path / "train_queue_status.csv").exists()


# ── landed.py: an unmounted lake is a failed rung unless said on purpose ──────

def _landed_main(argv, monkeypatch, tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("landed_under_test", SCRIPTS / "qc" / "landed.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    import lake
    monkeypatch.setattr(lake, "BASE", tmp_path / "nowhere")   # not mounted
    calls = []
    monkeypatch.setattr(m, "run", lambda name, cmd, dry=False: (calls.append(name), 0)[1])
    monkeypatch.setattr(sys, "argv", ["landed.py", *argv])
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    try:
        rc = m.main()
    except SystemExit as e:
        rc = e.code
    return rc, calls, buf.getvalue()


def test_landed_fails_when_the_lake_is_missing_and_not_excused(tmp_path, monkeypatch):
    rc, calls, out = _landed_main(["--dry-run"], monkeypatch, tmp_path)
    assert rc not in (0, None), "a silent harvest skip reported green"
    assert "FAIL: lake not mounted" in out
    assert not any(str(c).startswith("harvest:") for c in calls)


def test_landed_no_lake_skips_on_purpose_and_stays_green(tmp_path, monkeypatch):
    rc, calls, out = _landed_main(["--dry-run", "--no-lake"], monkeypatch, tmp_path)
    assert rc in (0, None)
    assert "--no-lake" in out and "NOT refreshed" in out
