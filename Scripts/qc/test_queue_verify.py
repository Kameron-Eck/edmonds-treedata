"""Queue verification gates (D6/D7, 2026-08-29).

The queue's VERIFY rows are what stand between a broken artifact and the next
GPU hour, and two of them could not fail:

  D6  VERIFY:evaluate matched on `year` alone against semantic_eval_report.csv —
      a cumulative file every year, arm and campaign appends into. ANY historical
      row passed it, including one written weeks earlier by a different model.
  D7  every exception inside verify_step landed on UNCHECKED, and UNCHECKED was
      a PASSING state: the job continued AND the resume ledger cleared the step's
      failure marker, so "the checker crashed" produced a stronger resume credit
      than "the checker never ran". The 0-byte-raster branch (`mb == 0`) was also
      dead code — rasterio.open raises on an empty file, so the blanket except
      reported UNCHECKED instead of EMPTY.

These tests fix both in place: each asserts the state the OLD code got wrong.

No Drive, no GPU, no torch.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_queue_verify.py -q
"""
import csv
import io
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "pipeline"))

q = pytest.importorskip("phase4_train_queue")

STATUS_COLS = ["job", "year", "tag", "step", "state", "exit", "minutes",
               "detail", "ts"]


def _status_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=STATUS_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in STATUS_COLS})


def _row(job="2009", step="train", state="OK", ts="2026-08-29 01:00:00",
         year="2009", tag="citywide_rgb", detail=""):
    return dict(job=job, year=year, tag=tag, step=step, state=state, ts=ts,
                detail=detail)


# ── D7: "could not check" is not "checked and fine" ───────────────────────────

def test_zero_byte_raster_reports_empty_not_unchecked(tmp_path):
    """The branch that was unreachable. `mb == 0` sat AFTER rasterio.open(), which
    raises on an empty file, so a 0-byte raster — one of the three real broken
    artifacts this gate exists for — reported UNCHECKED and passed."""
    out = tmp_path / "edmonds_canopy_prob_2009_x.tif"
    out.write_bytes(b"")
    state, detail = q._check_prob_raster(out)
    assert state == "EMPTY", (state, detail)
    assert state in q._VERIFY_HARD_FAIL


def test_unopenable_raster_is_unreadable_and_hard(tmp_path, monkeypatch):
    """A file that is not a raster is a BROKEN ARTIFACT, distinct from a broken
    checker — and it must stop the job."""
    out = tmp_path / "edmonds_canopy_prob_2009_x.tif"
    out.write_bytes(b"not a tif, but not empty either" * 100)
    monkeypatch.setattr(q.time, "sleep", lambda s: None)        # no real backoff
    state, detail = q._check_prob_raster(out, attempts=2, backoff_s=0)
    assert state == "UNREADABLE", (state, detail)
    assert state in q._VERIFY_HARD_FAIL


def test_unopenable_raster_is_retried_before_being_condemned(tmp_path, monkeypatch):
    """Transient EIO on this mount is documented in _copy_to_drive's own comments,
    and UNREADABLE costs a re-run of a 4-hour inference. It must not be declared on
    the first stumble."""
    out = tmp_path / "edmonds_canopy_prob_2009_x.tif"
    out.write_bytes(b"junk" * 100)
    naps = []
    monkeypatch.setattr(q.time, "sleep", naps.append)
    q._check_prob_raster(out, attempts=3, backoff_s=10)
    assert naps == [10, 20], f"expected backoff between tries, got {naps}"


def test_missing_raster_is_missing(tmp_path):
    state, _ = q._check_prob_raster(tmp_path / "nope.tif")
    assert state == "MISSING" and state in q._VERIFY_HARD_FAIL


def test_healthy_raster_still_passes(tmp_path):
    """The OK path must survive the restructure."""
    rasterio = pytest.importorskip("rasterio")
    import numpy as np
    out = tmp_path / "edmonds_canopy_prob_2009_x.tif"
    a = np.full((200, 200), 240, dtype="uint8")
    with rasterio.open(out, "w", driver="GTiff", height=200, width=200, count=1,
                       dtype="uint8", nodata=255) as d:
        d.write(a, 1)
    state, detail = q._check_prob_raster(out)
    assert state == "OK", (state, detail)


def test_unverified_states_do_not_abort_a_job():
    """They are not a pass, but a checker that threw is not evidence the artifact
    is bad either — aborting on it would throw away good GPU hours."""
    for s in q._VERIFY_UNVERIFIED:
        assert s not in q._VERIFY_HARD_FAIL, s


def test_unchecked_no_longer_clears_the_resume_marker(tmp_path, monkeypatch):
    """THE D7 CORE. A step recorded OK whose verification then threw used to have
    its failure marker positively DISCARDED, so the next launch skipped it in
    silence. It keeps its credit now — re-running is unapproved GPU spend — but it
    is flagged for re-checking rather than trusted."""
    monkeypatch.setattr(q, "QC_DIR", tmp_path)
    _status_csv(tmp_path / "train_queue_status_a.csv", [
        _row(step="train", state="OK", ts="2026-08-29 01:00:00"),
        _row(step="VERIFY:train", state="UNCHECKED", ts="2026-08-29 01:05:00"),
    ])
    done, reverify = q._completed_steps()
    assert ("2009", "train") in done, "an unapproved re-train is not the answer"
    assert ("2009", "train") in reverify, "but it must not be silently trusted"


def test_a_clean_verify_needs_no_recheck(tmp_path, monkeypatch):
    monkeypatch.setattr(q, "QC_DIR", tmp_path)
    _status_csv(tmp_path / "train_queue_status_a.csv", [
        _row(step="train", state="OK", ts="2026-08-29 01:00:00"),
        _row(step="VERIFY:train", state="OK", ts="2026-08-29 01:05:00"),
    ])
    done, reverify = q._completed_steps()
    assert ("2009", "train") in done and ("2009", "train") not in reverify


def test_a_hard_verify_failure_still_forces_a_rerun(tmp_path, monkeypatch):
    monkeypatch.setattr(q, "QC_DIR", tmp_path)
    _status_csv(tmp_path / "train_queue_status_a.csv", [
        _row(step="train", state="OK", ts="2026-08-29 01:00:00"),
        _row(step="VERIFY:train", state="BAD_CKPT", ts="2026-08-29 01:05:00"),
    ])
    done, reverify = q._completed_steps()
    assert ("2009", "train") not in done
    assert ("2009", "train") not in reverify        # re-run supersedes re-check


def test_a_later_clean_verify_clears_an_earlier_unchecked(tmp_path, monkeypatch):
    """Rows are sorted by ts and later ones win — a re-check that succeeded must
    retire the flag, or every launch re-checks forever."""
    monkeypatch.setattr(q, "QC_DIR", tmp_path)
    _status_csv(tmp_path / "train_queue_status_a.csv", [
        _row(step="train", state="OK", ts="2026-08-29 01:00:00"),
        _row(step="VERIFY:train", state="UNCHECKED", ts="2026-08-29 01:05:00"),
        _row(step="VERIFY:train", state="OK", ts="2026-08-29 02:05:00"),
    ])
    done, reverify = q._completed_steps()
    assert ("2009", "train") in done and ("2009", "train") not in reverify


# ── D6: the evaluate report has to say WHOSE numbers it holds ─────────────────

def _eval_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["year", "scope", "iou", "run_tag", "run_id", "written_utc"]
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})


def _utc(epoch):
    import datetime as dt
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


# DERIVED from T0, never hand-written. The first draft of this file hardcoded two
# ISO strings and asserted one was older than T0; both were newer, so the STALE
# test passed a value the code correctly called fresh and I nearly "fixed" working
# code to match a broken test. Ordering that the test itself must not get wrong is
# ordering the test should compute.
T0 = 1_800_000_000.0             # a step start, epoch seconds
BEFORE = _utc(T0 - 3600)         # an hour before this step began
AFTER = _utc(T0 + 60)            # a minute after it began


def test_eval_rows_from_another_arm_do_not_count(tmp_path):
    """THE D6 CORE. Rows exist for the year — the old check returned OK on exactly
    this — but they belong to a different arm. They are not this run's evidence."""
    rep = tmp_path / "semantic_eval_report.csv"
    _eval_csv(rep, [dict(year="2009", scope="OVERALL", iou="0.7",
                         run_tag="some_other_arm", written_utc=AFTER)])
    state, detail = q._verify_eval_rows(rep, "2009", "citywide_rgb", T0)
    assert state == "MISSING", (state, detail)
    assert "NONE under tag" in detail


def test_eval_rows_predating_the_step_are_stale(tmp_path):
    """Right year, right tag, but written before this step began: the step exited
    0 and left the PREVIOUS run's numbers in place."""
    rep = tmp_path / "semantic_eval_report.csv"
    _eval_csv(rep, [dict(year="2009", scope="OVERALL", iou="0.7",
                         run_tag="citywide_rgb", written_utc=BEFORE)])
    state, detail = q._verify_eval_rows(rep, "2009", "citywide_rgb", T0)
    assert state == "STALE_EVAL", (state, detail)
    assert state in q._VERIFY_HARD_FAIL


def test_fresh_eval_rows_under_this_tag_pass(tmp_path):
    rep = tmp_path / "semantic_eval_report.csv"
    _eval_csv(rep, [dict(year="2009", scope="OVERALL", iou="0.7",
                         run_tag="citywide_rgb", written_utc=AFTER)])
    state, detail = q._verify_eval_rows(rep, "2009", "citywide_rgb", T0)
    assert state == "OK", (state, detail)


def test_pre_identity_report_is_unverified_not_ok(tmp_path):
    """Reports written before run-identity stamping cannot attribute their rows.
    That is 'nothing was proven', which is its own state — not a pass."""
    rep = tmp_path / "semantic_eval_report.csv"
    with io.open(rep, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["year", "scope", "iou"])
        w.writeheader()
        w.writerow({"year": "2009", "scope": "OVERALL", "iou": "0.7"})
    state, detail = q._verify_eval_rows(rep, "2009", "citywide_rgb", T0)
    assert state == "UNVERIFIED", (state, detail)
    assert state not in q._VERIFY_HARD_FAIL


def test_no_rows_at_all_is_missing(tmp_path):
    rep = tmp_path / "semantic_eval_report.csv"
    _eval_csv(rep, [dict(year="2016", scope="OVERALL", iou="0.7",
                         run_tag="citywide_rgb", written_utc=AFTER)])
    state, _ = q._verify_eval_rows(rep, "2009", "citywide_rgb", T0)
    assert state == "MISSING"
    state, _ = q._verify_eval_rows(tmp_path / "gone.csv", "2009", "x", T0)
    assert state == "MISSING"


def test_a_resume_recheck_has_no_step_to_be_newer_than(tmp_path):
    """step_start=None on a re-verify: the freshness test must stand down rather
    than compare against a timestamp that does not exist."""
    rep = tmp_path / "semantic_eval_report.csv"
    _eval_csv(rep, [dict(year="2009", scope="OVERALL", iou="0.7",
                         run_tag="citywide_rgb", written_utc=BEFORE)])
    state, _ = q._verify_eval_rows(rep, "2009", "citywide_rgb", None)
    assert state == "OK"


def test_parse_utc_is_timezone_aware():
    """written_utc is real UTC; comparing it through a naive datetime would put the
    freshness check hours out and pass everything."""
    import datetime as dt
    got = q._parse_utc("2027-01-15T21:21:00Z")
    want = dt.datetime(2027, 1, 15, 21, 21, tzinfo=dt.timezone.utc).timestamp()
    assert got == want
    assert q._parse_utc("nonsense") is None
    assert q._parse_utc(None) is None
