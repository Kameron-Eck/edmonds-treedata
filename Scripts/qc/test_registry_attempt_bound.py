"""An attempt's outcome must be ITS outcome — a dead run cannot inherit a rerun's success.

WHAT HAPPENED, 2026-08-31. The coarse pilot arm's runtime died mid-evaluate, leaving only a
RUNNING row. A fresh runtime resumed and completed evaluate in 26.2 min on an A100. The
registry then recorded:

    20260831T023046Z_2019n_pilot_e2_coarse_evaluate  NVIDIA L4  26.2 min  "queue OK"

An L4 credited with finishing a step it never started, in an APPEND-ONLY ledger — the kind
of row that is permanent once written and that every later cost and timing analysis trusts.

WHY THE EXISTING GUARD MISSED IT. status_for already bounded an attempt to "rows from t0
until the next attempt of the same step BEGINS", and identified that next beginning by
`state == "RUNNING"`. But a launch REWRITES its own status file and updates a step's row IN
PLACE, RUNNING -> OK. Once the rerun finished, its RUNNING marker no longer existed
anywhere, the bound never closed, and the dead attempt swept up everything after it.

The bound is now "any next row of the same step", which is safe precisely because a terminal
row carries its attempt's START timestamp rather than its end: the medium arm's `train OK`
sits at 01:12:54 and evaluate begins 26.8 minutes later at 01:39:51. An attempt's own
terminal row therefore shares its t0 and can never be mistaken for the next attempt.

Run:
  PYTHONUTF8=1 py -3.12 -m pytest qc/test_registry_attempt_bound.py -q
"""
import datetime as dt
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent

import registry_from_manifests as R  # noqa: E402


def _ts(s):
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)


def _row(step, state, ts, minutes="", year="2019n", tag="pilot_e2_coarse"):
    return {"job": "j", "year": year, "tag": tag, "step": step, "state": state,
            "exit": "", "minutes": minutes, "detail": "", "ts": ts,
            "host": "h", "session": "s"}


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """Point status_for at a synthetic ledger; it reads via status_files(QC_DIR)."""
    def _install(rows):
        import csv
        p = tmp_path / "train_queue_status_synthetic_20260831T000000Z.csv"
        cols = ["job", "year", "tag", "step", "state", "exit", "minutes",
                "detail", "ts", "host", "session"]
        with open(p, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        monkeypatch.setattr(R, "QC_DIR", tmp_path)
    return _install


def test_a_dead_attempt_does_not_inherit_the_reruns_outcome(ledger):
    """THE BUG, exactly as it occurred. The dead attempt left a RUNNING row and nothing
    else; the rerun's row is terminal, so under the old `state == RUNNING` bound there was
    no next-attempt marker at all."""
    ledger([
        _row("evaluate", "RUNNING", "2026-08-31 02:30:44"),              # died here
        _row("evaluate", "OK", "2026-08-31 03:51:45", minutes="26.2"),   # the rerun
    ])
    final, _v = R.status_for("2019n", "pilot_e2_coarse", "evaluate",
                             _ts("2026-08-31 02:30:46"))
    assert final is not None
    assert final["state"] == "RUNNING", (
        f"the dead attempt was credited with state {final['state']!r}")
    assert not final["minutes"], (
        f"the dead attempt was credited with {final['minutes']} minutes it never ran")


def test_the_rerun_still_gets_its_own_outcome(ledger):
    """The other half — tightening the bound must not blind an attempt to its own row."""
    ledger([
        _row("evaluate", "RUNNING", "2026-08-31 02:30:44"),
        _row("evaluate", "OK", "2026-08-31 03:51:45", minutes="26.2"),
    ])
    final, _v = R.status_for("2019n", "pilot_e2_coarse", "evaluate",
                             _ts("2026-08-31 03:51:52"))
    assert final["state"] == "OK" and final["minutes"] == "26.2"


def test_an_attempts_own_terminal_row_is_not_read_as_the_next_attempt(ledger):
    """Why bounding on ANY next row is safe: a terminal row carries its attempt's START
    ts, so it shares t0 and never looks like a new attempt. If the writer ever changed to
    stamp the END time instead, this test fails and the bound needs rethinking."""
    ledger([_row("train", "OK", "2026-08-31 01:12:54", minutes="26.8")])
    final, _v = R.status_for("2019n", "pilot_e2_coarse", "train",
                             _ts("2026-08-31 01:12:56"))
    assert final["state"] == "OK" and final["minutes"] == "26.8", (
        "an attempt lost its own terminal row — the bound is now too tight")


def test_three_attempts_each_keep_their_own(ledger):
    """The original motivating case: several attempts of one step, where taking the last
    match would staple the newest outcome onto the oldest manifest."""
    ledger([
        _row("inference", "FAIL", "2026-08-31 01:00:00", minutes="3.0"),
        _row("inference", "FAIL", "2026-08-31 02:00:00", minutes="4.0"),
        _row("inference", "OK", "2026-08-31 03:00:00", minutes="5.0"),
    ])
    for start, want_state, want_min in (("01:00:02", "FAIL", "3.0"),
                                        ("02:00:02", "FAIL", "4.0"),
                                        ("03:00:02", "OK", "5.0")):
        final, _v = R.status_for("2019n", "pilot_e2_coarse", "inference",
                                 _ts(f"2026-08-31 {start}"))
        assert (final["state"], final["minutes"]) == (want_state, want_min), (
            f"attempt at {start} got {final['state']}/{final['minutes']}")


def test_the_bound_does_not_require_a_running_marker():
    """Static guard on the exact regression. The `state == RUNNING` condition looked like a
    reasonable way to spot the next attempt and was invisible until a run died and its
    successor finished — at which point the marker it depended on no longer existed."""
    import inspect
    src = inspect.getsource(R.status_for)
    body = src[src.index("t_end = None"):]
    head = body[:body.index("final = start")]
    assert 'state") == "RUNNING"' not in head and "'RUNNING'" not in head, (
        "the attempt bound depends on a RUNNING marker again — a completed rerun erases "
        "that marker by updating its row in place, so the bound will not close")
