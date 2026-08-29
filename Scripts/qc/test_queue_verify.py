"""Queue verification gates (D6/D7/D8/D9, 2026-08-29).

The queue's VERIFY rows are what stand between a broken artifact and the next
GPU hour, and four of them could not fail:

  D6  VERIFY:evaluate matched on `year` alone against semantic_eval_report.csv —
      a cumulative file every year, arm and campaign appends into. ANY historical
      row passed it, including one written weeks earlier by a different model.
  D7  every exception inside verify_step landed on UNCHECKED, and UNCHECKED was
      a PASSING state: the job continued AND the resume ledger cleared the step's
      failure marker, so "the checker crashed" produced a stronger resume credit
      than "the checker never ran". The 0-byte-raster branch (`mb == 0`) was also
      dead code — rasterio.open raises on an empty file, so the blanket except
      reported UNCHECKED instead of EMPTY.
  D8  the resume ledger keyed on (job_id, step) — the job's NICKNAME — ignoring
      the year and tag that decide which artifacts the step actually produces.
  D9  a job whose every step was skipped was declared verified having read
      nothing at all.

These tests fix all four in place: each asserts the state the OLD code got wrong.

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


# The resume ledger keys on the WORK (job, year, tag, step), not the job nickname
# — D8. Built through the module's own helper so the test cannot encode a key
# shape the code has since changed.
KEY = q._job_key("2009", "2009", "citywide_rgb", "train")


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
    done, reverify, _ = q._completed_steps()
    assert KEY in done, "an unapproved re-train is not the answer"
    assert KEY in reverify, "but it must not be silently trusted"


def test_a_clean_verify_needs_no_recheck(tmp_path, monkeypatch):
    monkeypatch.setattr(q, "QC_DIR", tmp_path)
    _status_csv(tmp_path / "train_queue_status_a.csv", [
        _row(step="train", state="OK", ts="2026-08-29 01:00:00"),
        _row(step="VERIFY:train", state="OK", ts="2026-08-29 01:05:00"),
    ])
    done, reverify, _ = q._completed_steps()
    assert KEY in done and KEY not in reverify


def test_a_hard_verify_failure_still_forces_a_rerun(tmp_path, monkeypatch):
    monkeypatch.setattr(q, "QC_DIR", tmp_path)
    _status_csv(tmp_path / "train_queue_status_a.csv", [
        _row(step="train", state="OK", ts="2026-08-29 01:00:00"),
        _row(step="VERIFY:train", state="BAD_CKPT", ts="2026-08-29 01:05:00"),
    ])
    done, reverify, _ = q._completed_steps()
    assert KEY not in done
    assert KEY not in reverify        # re-run supersedes re-check


def test_a_later_clean_verify_clears_an_earlier_unchecked(tmp_path, monkeypatch):
    """Rows are sorted by ts and later ones win — a re-check that succeeded must
    retire the flag, or every launch re-checks forever."""
    monkeypatch.setattr(q, "QC_DIR", tmp_path)
    _status_csv(tmp_path / "train_queue_status_a.csv", [
        _row(step="train", state="OK", ts="2026-08-29 01:00:00"),
        _row(step="VERIFY:train", state="UNCHECKED", ts="2026-08-29 01:05:00"),
        _row(step="VERIFY:train", state="OK", ts="2026-08-29 02:05:00"),
    ])
    done, reverify, _ = q._completed_steps()
    assert KEY in done and KEY not in reverify


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


# ── D8: the resume ledger keys on the WORK, not the job's nickname ────────────

def test_same_job_id_different_year_does_not_grant_a_skip(tmp_path, monkeypatch):
    """THE D8 CORE. Job ids are short, hand-written and reused across queue files
    (`2019` in three, `2024` in three), and nothing makes an id mean the same year
    twice. Under the old (job_id, step) key, a completed `2024` step in one queue
    silently satisfied a different queue's `2024`."""
    monkeypatch.setattr(q, "QC_DIR", tmp_path)
    _status_csv(tmp_path / "train_queue_status_a.csv", [
        _row(job="2024", year="2024", tag="citywide_rgb", step="train", state="OK"),
    ])
    done, _, _ = q._completed_steps()
    assert q._job_key("2024", "2024", "citywide_rgb", "train") in done
    # same id, DIFFERENT year — this work has not been done
    assert q._job_key("2024", "2017", "citywide_rgb", "train") not in done


def test_same_job_id_different_tag_does_not_grant_a_skip(tmp_path, monkeypatch):
    """A tag is a whole separate arm: its own tile dir, checkpoint and raster."""
    monkeypatch.setattr(q, "QC_DIR", tmp_path)
    _status_csv(tmp_path / "train_queue_status_a.csv", [
        _row(job="2021s_nr2", year="2021s", tag="noise_r2", step="train", state="OK"),
    ])
    done, _, _ = q._completed_steps()
    assert q._job_key("2021s_nr2", "2021s", "noise_r2", "train") in done
    assert q._job_key("2021s_nr2", "2021s", "noise_r5", "train") not in done


def test_job_key_normalises_both_sides():
    """A YAML `tag: 2020` parses as an int while the CSV holds text; if the two
    sides normalised differently the key would never match and every resume would
    re-run everything."""
    assert q._job_key("2024", 2024, 2020, "train") == \
           q._job_key("2024", "2024", "2020", "train")


# ── D9: a skipped job is not verified by having skipped it ───────────────────

def _skipjob(monkeypatch, tmp_path):
    monkeypatch.setattr(q, "MASKS", tmp_path)
    monkeypatch.setattr(q, "_status_write", lambda r: None)
    return dict(id="2018s_fx", year="2018s", tag="fx"), []


PRIOR = ("OK", "146MB valid=99.1% maxprob=0.996", "2026-08-27 10:00:00")


def test_skipped_job_recheck_catches_a_vanished_raster(tmp_path, monkeypatch):
    """THE D9 CORE. The old branch printed 'already OK' and read nothing at all, so
    a raster deleted between launches still counted as this launch's pass."""
    job, rows = _skipjob(monkeypatch, tmp_path)
    ok = q._recheck_skipped_verify(job, rows, PRIOR)
    assert ok is False
    assert rows[-1]["state"] == "MISSING"
    assert rows[-1]["state"] in q._VERIFY_HARD_FAIL


def test_skipped_job_recheck_catches_a_resized_raster(tmp_path, monkeypatch):
    job, rows = _skipjob(monkeypatch, tmp_path)
    (tmp_path / "edmonds_canopy_prob_2018s_fx.tif").write_bytes(b"x" * 4_000_000)
    ok = q._recheck_skipped_verify(job, rows, PRIOR)
    assert ok is False and rows[-1]["state"] == "SIZE_CHANGED"


def test_skipped_job_recheck_reports_cached_not_ok(tmp_path, monkeypatch):
    """It must NOT claim OK: this launch did not re-read the raster (that read is
    what hung the queue on 2026-08-27). OK_CACHED is the weaker, true statement."""
    job, rows = _skipjob(monkeypatch, tmp_path)
    (tmp_path / "edmonds_canopy_prob_2018s_fx.tif").write_bytes(b"x" * 146_000_000)
    ok = q._recheck_skipped_verify(job, rows, PRIOR)
    assert ok is True
    assert rows[-1]["state"] == "OK_CACHED"
    assert rows[-1]["state"] not in q._VERIFY_HARD_FAIL


def test_skipped_job_recheck_without_a_recorded_size_is_unverified(tmp_path, monkeypatch):
    """A pre-D9 verdict carries no size to compare. That is 'existence only', which
    is its own state — not a pass, and not a crash."""
    job, rows = _skipjob(monkeypatch, tmp_path)
    (tmp_path / "edmonds_canopy_prob_2018s_fx.tif").write_bytes(b"x" * 1000)
    q._recheck_skipped_verify(job, rows, ("OK", "verified earlier", "2026-08-27"))
    assert rows[-1]["state"] == "UNVERIFIED"
    q._recheck_skipped_verify(job, rows, None)          # no prior row at all
    assert rows[-1]["state"] == "UNVERIFIED"


def test_mb_from_verdict_only_reads_the_anchored_size():
    assert q._mb_from_verdict("146MB valid=99.1% maxprob=0.996 p99.9=0.9") == 146
    assert q._mb_from_verdict("valid=99.1% 146MB") is None      # not anchored
    assert q._mb_from_verdict("") is None
    assert q._mb_from_verdict(None) is None


# ── D10: the status table is the audit trail; it must never be half-written ───

def test_status_write_never_truncates_the_live_file(tmp_path, monkeypatch):
    """THE D10 CORE. The flush was open(out, "w") straight onto the mount: the file
    was TRUNCATED first and refilled after, so every step boundary opened a window
    where this launch's whole history was a zero-length file on the lake. Asserted
    at the syscall — no os.replace here may land on an existing destination, and
    the canonical name must never be opened for writing."""
    out = tmp_path / "train_queue_status_q_20260829T000000Z.csv"
    monkeypatch.setattr(q, "QC_DIR", tmp_path)
    monkeypatch.setattr(q, "STATUS_OUT", out)
    q._status_write([_row(step="train", state="OK")])
    assert out.exists()

    seen, opened = [], []
    real_replace, real_open = q.os.replace, io.open

    def _spy_replace(a, b):
        seen.append((Path(b).name, Path(b).exists()))
        return real_replace(a, b)

    def _spy_open(f, *a, **kw):
        if "w" in str(a[0] if a else kw.get("mode", "")):
            opened.append(Path(f).name)
        return real_open(f, *a, **kw)

    monkeypatch.setattr(q.os, "replace", _spy_replace)
    monkeypatch.setattr(q.io, "open", _spy_open)
    q._status_write([_row(step="train", state="OK"),
                     _row(step="VERIFY:train", state="OK")])
    assert not any(existed for _, existed in seen), \
        f"replaced over an existing destination on the mount: {seen}"
    assert out.name not in opened, \
        "the canonical status file was opened for writing — that truncates it"
    rows = list(csv.DictReader(io.open(out, encoding="utf-8", newline="")))
    assert len(rows) == 2
    assert not list(tmp_path.glob("*.part.*")) and not list(tmp_path.glob("*.prev.*"))


def test_status_temp_files_are_invisible_to_every_reader(tmp_path):
    """Readers glob `train_queue_status*.csv`. A temp named `...csv.part.x` matches
    none of them; a temp named `...part.csv` would be MERGED, double-counting rows
    into the resume ledger. Suffix after the extension, always."""
    out = tmp_path / "train_queue_status_q_20260829T000000Z.csv"
    tmp = out.with_name(out.name + ".part.1234ab")
    tmp.write_text("junk", encoding="utf-8")
    assert list(tmp_path.glob("train_queue_status*.csv")) == []


def test_an_unreadable_status_file_disables_resume(tmp_path, monkeypatch):
    """Dropping a file's rows REWRITES HISTORY in the unsafe direction: rows merge
    latest-wins, so losing the file that holds a FAIL leaves the earlier OK
    standing and the next launch skips a step that failed."""
    monkeypatch.setattr(q, "QC_DIR", tmp_path)
    _status_csv(tmp_path / "train_queue_status_a.csv", [
        _row(step="train", state="OK", ts="2026-08-29 01:00:00")])
    done, _, _ = q._completed_steps()
    assert KEY in done                       # readable ledger: the skip is granted

    # now a second file nobody can interpret — a torn write, a truncated header
    (tmp_path / "train_queue_status_b.csv").write_text(
        "this is not a csv header\n", encoding="utf-8")
    done, reverify, _ = q._completed_steps()
    assert done == set() and reverify == set(), \
        "an incomplete ledger must not justify skipping anything"
    assert q._MERGE_DEFECTS, "the unreadable file must be reported, not dropped"


def test_a_torn_status_file_is_caught_by_its_header(tmp_path, monkeypatch):
    """csv.DictReader does NOT raise on a truncated file — it yields rows with
    missing keys. Only a header check notices."""
    monkeypatch.setattr(q, "QC_DIR", tmp_path)
    (tmp_path / "train_queue_status_torn.csv").write_text(
        "job,year,step\n2009,2009,train\n", encoding="utf-8")   # no state/tag/ts
    rows, problem = q._read_status_file(tmp_path / "train_queue_status_torn.csv")
    assert rows == [] and problem and "header lacks" in problem
