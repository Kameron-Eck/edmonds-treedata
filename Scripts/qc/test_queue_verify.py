"""Queue verification gates (D6/D7/D8/D9/D10/D11, 2026-08-29).

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
  D10 the status file was TRUNCATED then refilled on the mount after every step,
      and unreadable status files were dropped from the merge — which rewrites
      history in the unsafe direction, since rows merge latest-wins.
  D11 the cross-VM run-tag guard ran once at launch and read the tag out of the
      ENGINE's cmdline, which is absent between engine steps.

These tests fix all six in place: each asserts the state the OLD code got wrong.

No Drive, no GPU, no torch.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_queue_verify.py -q
"""
import csv
import io
import json
import os
import sys
from pathlib import Path

import pandas as pd
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


# ── D1: VERIFY:train asks DRIVE, not the cache that wrote the file ───────────

def test_a_cached_checkpoint_drive_never_received_is_not_a_pass(tmp_path, monkeypatch):
    """THE FAILURE OF 2026-08-29, reproduced. Every other check in verify_step
    reads through the rclone mount, which serves this VM's own write cache — so
    size, zip magic, epoch, run_tag and run_id ALL PASS on a checkpoint that never
    reached Drive. That night the cache held B24, Drive held B7, the log said B24,
    and VERIFY:train passed. Only asking Drive can see it."""
    ck = tmp_path / "sem_best_2009_x.pt"
    ck.write_bytes(b"epoch24-bytes")
    monkeypatch.setattr(q, "_DRIVE_MOUNT_PREFIX", str(tmp_path) + os.sep)
    monkeypatch.setattr(q.subprocess, "run", _fake_rclone(remote_md5="b" * 32))
    monkeypatch.setattr(q.time, "sleep", lambda s: None)
    state, note = q._drive_matches_mount(ck, wait_s=0)
    assert state == "mismatch" and "DRIVE HOLDS DIFFERENT BYTES" in note


def test_a_drained_checkpoint_passes(tmp_path, monkeypatch):
    ck = tmp_path / "sem_best_2009_x.pt"
    ck.write_bytes(b"epoch24-bytes")
    monkeypatch.setattr(q, "_DRIVE_MOUNT_PREFIX", str(tmp_path) + os.sep)
    monkeypatch.setattr(q.subprocess, "run", _fake_rclone(remote_md5=q._md5_of(ck)))
    state, note = q._drive_matches_mount(ck, wait_s=0)
    assert state == "ok" and "drive md5 ok" in note


def test_no_sa_remote_is_unavailable_not_ok(tmp_path, monkeypatch):
    """Nothing was checked; the note must say so rather than implying a pass."""
    ck = tmp_path / "sem_best_2009_x.pt"
    ck.write_bytes(b"x")
    monkeypatch.setattr(q, "_DRIVE_MOUNT_PREFIX", str(tmp_path) + os.sep)
    monkeypatch.setattr(q.subprocess, "run", _fake_rclone(remotes=""))
    state, note = q._drive_matches_mount(ck, wait_s=0)
    assert state == "unavailable" and "n/a" in note
    # a path outside the mount can never be checked
    assert q._drive_matches_mount(Path("/tmp/x.pt"), wait_s=0)[0] == "unavailable"


def test_the_drive_check_is_skipped_on_a_resume_recheck(tmp_path, monkeypatch):
    """step_start=None means another runtime wrote this file, so this VM holds no
    dirty cache entry for it: a mount read IS a Drive read and the comparison is
    vacuously equal. Skipping it avoids a second full 150-300 MB FUSE read inside
    verify_step, which has no watchdog over it."""
    torch = pytest.importorskip("torch")
    ck = tmp_path / "sem_best_2009_x.pt"
    torch.save({"phase": "B", "epoch": 24, "run_tag": "x", "run_id": "r1"}, ck)
    called = []
    monkeypatch.setattr(q, "_drive_matches_mount",
                        lambda *a, **k: called.append(1) or ("ok", "n"))
    state, detail = q._verify_ckpt_identity(ck, "2009", "x", 150.0, None)
    assert not called, "the drive check ran on a re-verify"
    # ...and because it did not run, and freshness could not run either, the
    # verdict must say so. Returning OK here graduated a step that a crashed
    # launch had left UNVERIFIED into a permanent pass on identity fields alone —
    # which the B24/B7 corpse satisfies, since it IS this arm's year and tag.
    assert state == "UNVERIFIED", "a re-verify laundered into a pass"
    assert state not in q._VERIFY_HARD_FAIL, "and it must not kill the job either"
    assert "drive check skipped" in detail
    q._verify_ckpt_identity(ck, "2009", "x", 150.0, ck.stat().st_mtime - 60)
    assert called, "the drive check must run when THIS VM wrote the file"


def test_a_drive_mismatch_is_unverified_not_a_hard_stop(tmp_path, monkeypatch):
    """rclone uploads asynchronously, so a mismatch can mean 'not drained yet'.
    It must be loud and it must not count as a pass — but it must not throw away a
    finished training run either."""
    assert "UNVERIFIED" in q._VERIFY_UNVERIFIED
    assert "UNVERIFIED" not in q._VERIFY_HARD_FAIL


def _fake_rclone(remote_md5=None, remotes="treedata-sa:\n"):
    """Stand-in for the two rclone calls _drive_matches_mount makes."""
    class R:
        def __init__(self, rc, out):
            self.returncode, self.stdout, self.stderr = rc, out, ""

    def run(cmd, **kw):
        if cmd[:2] == ["rclone", "listremotes"]:
            return R(0, remotes)
        if cmd[:2] == ["rclone", "md5sum"]:
            return R(0, f"{remote_md5}  x\n") if remote_md5 else R(1, "")
        raise AssertionError(f"unexpected command {cmd}")
    return run


# ── D11: the cross-VM run-tag guard ──────────────────────────────────────────

def _beacon(tmp_path, name, **fields):
    logs = tmp_path / "phase4" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    p = logs / f"heartbeat_{name}.json"
    p.write_text(json.dumps(fields), encoding="utf-8")
    return p


def test_a_declared_tag_on_another_vm_is_a_clash(tmp_path, monkeypatch):
    monkeypatch.setattr(q, "BASE", tmp_path)
    _beacon(tmp_path, "gpu2", session="gpu2", host="other-vm",
            run_tags=["smooth5"], run_tags_pid=999)
    clashes, scanned, blind = q._tag_owners({"smooth5"})
    assert scanned == 1 and blind is None
    assert clashes == [("gpu2", "smooth5", "declared")]


def test_a_declaration_survives_the_gap_between_engine_steps(tmp_path, monkeypatch):
    """THE D11 CORE. The old guard read the ENGINE's cmdline, which is None
    whenever no engine is running — every gap between steps, and the whole of the
    labels/evaluate work. A queue that owns a tag for four hours appeared to hold
    it only in bursts, and a peer launching in a gap saw a free tag."""
    monkeypatch.setattr(q, "BASE", tmp_path)
    _beacon(tmp_path, "gpu2", session="gpu2", host="other-vm", engine_proc=None,
            queue_proc=444, run_tags=["smooth5"], run_tags_pid=444)
    clashes, _, _ = q._tag_owners({"smooth5"})
    assert clashes, "a declared tag must be visible with no engine running"


def test_an_old_build_beacon_still_falls_back_to_the_cmdline(tmp_path, monkeypatch):
    monkeypatch.setattr(q, "BASE", tmp_path)
    _beacon(tmp_path, "gpu2", session="gpu2", host="other-vm",
            engine_proc="python -u phase4_semantic_finetune.py --run-tag smooth5 --step train")
    clashes, _, _ = q._tag_owners({"smooth5"})
    assert clashes == [("gpu2", "smooth5", "engine cmdline")]


def test_our_own_beacon_is_not_a_clash(tmp_path, monkeypatch):
    """The beacon on THIS VM republishes THIS queue's tags within 60s of launch. A
    guard that counted its own reflection would refuse every second job."""
    monkeypatch.setattr(q, "BASE", tmp_path)
    _beacon(tmp_path, "me", session="me", host=q._ident()["host"],
            run_tags=["smooth5"], run_tags_pid=os.getpid())
    clashes, scanned, _ = q._tag_owners({"smooth5"})
    assert scanned == 1 and clashes == []


def test_an_old_build_beacon_on_our_own_vm_is_not_a_clash(tmp_path, monkeypatch):
    """The mixed-version case, and it is the NORMAL one after a P11.5 crash fix:
    the VM pulls a fix/ branch and relaunches the queue WITHOUT re-running the
    bootstrap, so the beacon keeps running pre-D11 code. It publishes no run_tags,
    falls through to the cmdline fallback, and that cmdline is OUR OWN engine's.
    Since a whole queue shares one tag, every job after the first would have
    skipped itself as TAG_IN_USE."""
    monkeypatch.setattr(q, "BASE", tmp_path)
    _beacon(tmp_path, "me", session="me", host=q._ident()["host"],
            queue_proc=os.getpid(),                       # old build: no run_tags
            engine_proc="python -u phase4_semantic_finetune.py --run-tag citywide_rgb")
    clashes, scanned, _ = q._tag_owners({"citywide_rgb"})
    assert scanned == 1 and clashes == [], \
        "the guard matched this queue's own engine and would skip its own jobs"


def test_the_same_tag_on_a_DIFFERENT_vm_is_still_a_clash(tmp_path, monkeypatch):
    """The self-exclusion must not become a blanket exemption: a peer VM running
    an old-build beacon with our tag is exactly what this guard is for."""
    monkeypatch.setattr(q, "BASE", tmp_path)
    _beacon(tmp_path, "gpu2", session="gpu2", host="other-vm",
            queue_proc=os.getpid(),                       # same pid, DIFFERENT host
            engine_proc="python -u phase4_semantic_finetune.py --run-tag citywide_rgb")
    clashes, _, _ = q._tag_owners({"citywide_rgb"})
    assert clashes == [("gpu2", "citywide_rgb", "engine cmdline")]


def test_a_stale_beacon_is_a_dead_vm(tmp_path, monkeypatch):
    monkeypatch.setattr(q, "BASE", tmp_path)
    p = _beacon(tmp_path, "gpu2", session="gpu2", host="other-vm",
                run_tags=["smooth5"], run_tags_pid=999)
    os.utime(p, (0, 0))
    clashes, scanned, blind = q._tag_owners({"smooth5"})
    assert clashes == [] and scanned == 0
    assert blind and "all stale" in blind


def test_a_blind_guard_says_so_in_the_STATUS_CSV_not_just_the_log(tmp_path, monkeypatch):
    """It fails OPEN — an unreadable lake must not block a legitimate run — but it
    may not fail SILENTLY. The old version printed a warning to a log nobody reads
    and proceeded as if guarded."""
    monkeypatch.setattr(q, "BASE", tmp_path)          # no phase4/logs at all
    monkeypatch.setattr(q, "_status_write", lambda r: None)
    rows = []
    assert q._duplicate_tag_guard([dict(id="a", year="2009", tag="smooth5")],
                                  rows, at_launch=True) is True
    assert rows and rows[-1]["state"] == "GUARD_UNVERIFIED"
    assert rows[-1]["step"] == "GUARD:runtag"


def test_a_clash_at_launch_refuses_before_any_spend(tmp_path, monkeypatch):
    monkeypatch.setattr(q, "BASE", tmp_path)
    monkeypatch.setattr(q, "_status_write", lambda r: None)
    _beacon(tmp_path, "gpu2", session="gpu2", host="other-vm",
            run_tags=["smooth5"], run_tags_pid=999)
    rows = []
    with pytest.raises(SystemExit):
        q._duplicate_tag_guard([dict(id="a", year="2009", tag="smooth5")],
                               rows, at_launch=True)
    assert rows[-1]["state"] == "TAG_IN_USE"


def test_a_clash_mid_queue_skips_the_job_not_the_queue(tmp_path, monkeypatch):
    """A peer that starts after us was invisible to the launch-time scan. Losing
    one job to that is right; losing a queue that has already produced good work
    is not."""
    monkeypatch.setattr(q, "BASE", tmp_path)
    monkeypatch.setattr(q, "_status_write", lambda r: None)
    _beacon(tmp_path, "gpu2", session="gpu2", host="other-vm",
            run_tags=["smooth5"], run_tags_pid=999)
    rows = []
    ok = q._duplicate_tag_guard([dict(id="a", year="2009", tag="smooth5")],
                                rows, at_launch=False)
    assert ok is False                       # this job is skipped …
    assert rows[-1]["state"] == "TAG_IN_USE" # … and the queue carries on


def test_declaration_round_trips_from_the_queue_to_the_beacon(tmp_path, monkeypatch):
    """The cross-module contract: the queue WRITES the declaration and the beacon
    READS it. Both sides are asserted here because a key-name drift between two
    files is invisible to either one's own tests."""
    vh = pytest.importorskip("vm_heartbeat")
    decl = tmp_path / "queue_tags.json"
    monkeypatch.setattr(q, "_COLAB_BASE", tmp_path)      # pretend we are on a VM
    monkeypatch.setattr(q, "TAGS_FILE", decl)
    q._declare_run_tags([dict(id="a", year="2009", tag="smooth5"),
                         dict(id="b", year="2013", tag="smooth5")],
                        "queue_smooth.yaml", job="a", step="train")
    got = vh.run_tags(os.getpid(), str(decl))
    assert got and got["tags"] == ["smooth5"] and got["job"] == "a"
    # a DEAD queue's leftover declaration must never keep holding a tag
    assert vh.run_tags(os.getpid() + 1, str(decl)) is None
    assert vh.run_tags(None, str(decl)) is None
    assert vh.run_tags(os.getpid(), str(tmp_path / "absent.json")) is None


def test_a_torn_status_file_is_caught_by_its_header(tmp_path, monkeypatch):
    """csv.DictReader does NOT raise on a truncated file — it yields rows with
    missing keys. Only a header check notices."""
    monkeypatch.setattr(q, "QC_DIR", tmp_path)
    (tmp_path / "train_queue_status_torn.csv").write_text(
        "job,year,step\n2009,2009,train\n", encoding="utf-8")   # no state/tag/ts
    rows, problem = q._read_status_file(tmp_path / "train_queue_status_torn.csv")
    assert rows == [] and problem and "header lacks" in problem


# ── VERIFY:tile must check THIS ARM's tiles ───────────────────────────────────
def test_verify_tile_reads_the_tagged_index_not_the_legacy_one(tmp_path, monkeypatch):
    """Every queue job passes --run-tag, so the engine tiles into
    tiles/{year}__{tag}/. This check read tiles/{year}/ — the pre-branch untagged
    directory, which for every year still holds an index from some earlier arm. So
    it did not fail; it PASSED, against another arm's tiles, and reported their
    count as this arm's.
    """
    # BASE ALONE IS NOT ENOUGH, and this test learned that the expensive way.
    # QC_DIR and STATUS are bound at import from the ORIGINAL BASE, so verify_step
    # -> _status_write wrote a fixture row onto the real lake ledger and replaced
    # 69 rows of queue history. Redirect everything the write path can reach.
    monkeypatch.setattr(q, "BASE", tmp_path)
    monkeypatch.setattr(q, "QC_DIR", tmp_path / "phase4" / "qc")
    monkeypatch.setattr(q, "STATUS", tmp_path / "phase4" / "qc" / "status.csv")
    monkeypatch.setattr(q, "STATUS_OUT", tmp_path / "phase4" / "qc" / "status.csv")
    tiles = tmp_path / "phase4" / "tiles"
    legacy = tiles / "2009"
    legacy.mkdir(parents=True)
    img = tmp_path / "legacy.tif"
    img.write_bytes(b"x")
    pd.DataFrame([{"img_path": str(img)}] * 99).to_csv(
        legacy / "tile_index_2009.csv", index=False)

    job = {"id": "j1", "year": "2009", "tag": "mytag"}
    rows = []
    # The legacy index exists and is complete, and the old code PASSED on it. Now
    # it is a hard fail: training this arm on another arm's tiles is the corruption,
    # so stopping the job is the point, not a side effect.
    assert q.verify_step(job, "tile", rows, step_start=None) is False
    assert rows[-1]["state"] == "MISSING", (
        f"passed against another arm's tiles: {rows[-1]['detail']}")
    assert "legacy untagged" in rows[-1]["detail"], "and it should say why"

    # now give the arm its own tiles: the check must find them
    tagged = tiles / "2009__mytag"
    tagged.mkdir(parents=True)
    pd.DataFrame([{"img_path": str(img)}] * 7).to_csv(
        tagged / "tile_index_2009.csv", index=False)
    rows = []
    q.verify_step(job, "tile", rows, step_start=None)
    assert rows[-1]["state"] == "OK", rows[-1]["detail"]
    assert "7 tiles" in rows[-1]["detail"], rows[-1]["detail"]


def test_the_naming_rules_have_exactly_one_implementation():
    """These were hand-maintained TWINS. They are now shared through
    phase4seg.names, and this asserts the copies are GONE rather than merely in sync.

    A sync-checking test (which is what stood here) accepts two implementations and
    only complains when they diverge. That is strictly weaker: _pid_alive's copies
    were in sync for exactly as long as it took someone to add a third one without
    the Windows guard — which shipped, passed the suite, and would have called
    TerminateProcess on a live process.
    """
    import ast as _ast

    SCRIPTS_DIR = Path(__file__).resolve().parents[1]

    def _calls_os_kill(tree):
        """AST, not grep. A first pass matched `os.kill(` inside the DOCSTRING that
        explains why the guard exists — flagging the very comment that documents the
        fix is the kind of false positive that gets a test deleted."""
        for n in _ast.walk(tree):
            if (isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute)
                    and n.func.attr == "kill"
                    and isinstance(n.func.value, _ast.Name)
                    and n.func.value.id == "os"):
                return True
        return False

    def _has_sanitiser(tree):
        """The sanitiser is a genexp over `c.isalnum() or c in "._-"`. Look for the
        literal, which no other code in these files uses."""
        for n in _ast.walk(tree):
            if isinstance(n, _ast.Constant) and n.value == "._-":
                return True
        return False

    offenders = []
    for rel in ("pipeline/phase4_train_queue.py", "pipeline/phase4seg/cli.py",
                "pipeline/phase4seg/common.py"):
        tree = _ast.parse((SCRIPTS_DIR / rel).read_text(encoding="utf-8"))
        if _has_sanitiser(tree):
            offenders.append(f"{rel}: a second copy of the tag sanitiser")
        if _calls_os_kill(tree):
            offenders.append(f"{rel}: calls os.kill directly — use names.pid_alive")
    assert not offenders, ("naming/probe logic duplicated outside names.py: "
                           + "; ".join(offenders))


def test_the_shared_rules_are_actually_used():
    """Delegation must be real, not decorative."""
    assert q._sanitize_tag("node c/v1") == "node_c_v1"
    assert q._pid_alive(999999) is True or q._pid_alive(999999) is False
    idx = q._tagged_tile_index("2009", "rgb3")
    assert idx.parent.name == "2009__rgb3", idx
    assert q._tagged_tile_index("2009", "").parent.name == "2009"



# ── _pid_alive must never call os.kill on Windows ─────────────────────────────
def test_pid_alive_does_not_touch_os_kill_off_posix(monkeypatch):
    """On Windows os.kill does NOT probe — CPython maps it to TerminateProcess for
    every signal but CTRL_C_EVENT/CTRL_BREAK_EVENT, so os.kill(pid, 0) KILLS the
    process it was asked about. phase4seg/common.py:230 has carried this guard all
    along; the queue's copy was added on 2026-08-30 without it.

    Asserting the RETURN VALUE is not enough — True is also what a successful probe
    gives. The test has to prove os.kill was never reached.
    """
    monkeypatch.setattr(os, "name", "nt")

    def _boom(*a, **k):
        raise AssertionError("os.kill was called off-posix — this TERMINATES on Windows")

    monkeypatch.setattr(os, "kill", _boom)
    assert q._pid_alive(4321) is True, "off-posix must assume the peer is alive"


def test_pid_alive_still_probes_on_posix(monkeypatch):
    """The guard must not disable the check where it genuinely works."""
    monkeypatch.setattr(os, "name", "posix")
    seen = []
    monkeypatch.setattr(os, "kill", lambda p, s: seen.append((p, s)))
    assert q._pid_alive(4321) is True
    assert seen == [(4321, 0)], "posix must still probe with signal 0"

    def _gone(p, s):
        raise ProcessLookupError

    monkeypatch.setattr(os, "kill", _gone)
    assert q._pid_alive(4321) is False, "a dead pid must read as dead on posix"


# ── postproc: the deliverable step, and the unknown-step fallthrough ──────────
def _pp_job():
    return {"id": "pp1", "year": "2009", "tag": "t1"}


def test_postproc_is_in_the_queue_step_list():
    """step_postproc polygonises the canopy mask + GPKG — the deliverable. It was
    absent from STEPS, so it never ran under the queue and --skip-postproc was a
    no-op. config.PER_YEAR_STEPS has always included it."""
    assert "postproc" in q.STEPS, "the deliverable step is not in the queue"
    assert q.STEP_TIMEOUT_MIN.get("postproc"), "postproc has no wall-clock ceiling"


def test_verify_postproc_needs_both_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(q, "BASE", tmp_path)
    monkeypatch.setattr(q, "QC_DIR", tmp_path / "qc")
    monkeypatch.setattr(q, "STATUS", tmp_path / "qc" / "s.csv")
    monkeypatch.setattr(q, "STATUS_OUT", tmp_path / "qc" / "s.csv")
    masks = tmp_path / "masks"
    masks.mkdir()
    monkeypatch.setattr(q, "MASKS", masks)

    rows = []
    assert q.verify_step(_pp_job(), "postproc", rows, step_start=None) is False
    assert rows[-1]["state"] == "MISSING", rows[-1]

    # only the raster — half a deliverable must still fail
    (masks / "edmonds_canopy_mask_2009_t1.tif").write_bytes(b"x" * 2_000_000)
    rows = []
    q.verify_step(_pp_job(), "postproc", rows, step_start=None)
    assert rows[-1]["state"] == "MISSING" and "gpkg" in rows[-1]["detail"]

    # both present and non-trivial
    (masks / "edmonds_canopy_mask_2009_t1.gpkg").write_bytes(b"y" * 500_000)
    rows = []
    assert q.verify_step(_pp_job(), "postproc", rows, step_start=None) is not False
    assert rows[-1]["state"] == "OK", rows[-1]


def test_an_unrecognised_step_cannot_pass(tmp_path, monkeypatch):
    """`state` is initialised to "OK", so before the else-branch existed any step
    with no elif fell through every test and was recorded OK having checked
    nothing. That is the silent-pass class, and adding postproc would have widened
    it."""
    monkeypatch.setattr(q, "BASE", tmp_path)
    monkeypatch.setattr(q, "QC_DIR", tmp_path / "qc")
    monkeypatch.setattr(q, "STATUS", tmp_path / "qc" / "s.csv")
    monkeypatch.setattr(q, "STATUS_OUT", tmp_path / "qc" / "s.csv")
    rows = []
    q.verify_step(_pp_job(), "a_step_nobody_wrote_a_verifier_for", rows, step_start=None)
    assert rows[-1]["state"] == "UNCHECKED", \
        f"an unverifiable step recorded {rows[-1]['state']} — it must never read as OK"
    assert "no verifier" in rows[-1]["detail"]


# ── a job must declare where its labels come from ─────────────────────────────
def _queue_file(tmp_path, jobs):
    import yaml
    p = tmp_path / "queue_test.yaml"
    p.write_text(yaml.safe_dump(jobs), encoding="utf-8")
    return str(p)


def test_a_fine_year_without_a_declared_label_source_is_refused(tmp_path):
    """`polygons/` was overwritten with accept-all test data and the 14,476-crown
    review was never finished. Every queue file passes --force-citywide to avoid that
    path, but the QUEUE DOES NOT INJECT IT — it comes from the YAML alone. So the only
    thing standing between a run and known-bad labels was one hand-written line, and
    omitting it produced no error: cli.py computes citywide = (tier=="coarse" or
    force_citywide), gets False on a fine year, and takes the polygon path silently.
    """
    qf = _queue_file(tmp_path, [{"id": "j1", "year": "2020", "tag": "t",
                                 "extra": ["--no-hillshade"]}])
    with pytest.raises(SystemExit) as e:
        q._load_queue(qf)
    msg = str(e.value)
    assert "does not declare a label source" in msg
    assert "accept-all test data" in msg, "the message must say WHY, not just refuse"


@pytest.mark.parametrize("flag", ["--force-citywide", "--anchor-labels",
                                  "--coarse-site-tiling"])
def test_any_explicit_declaration_is_accepted(tmp_path, flag):
    """Three real label sources exist. The guard wants a DECLARATION, not one
    particular answer — --coarse-site-tiling is 'yes, I really mean the site
    polygons', which is a legitimate choice once the review is finished."""
    qf = _queue_file(tmp_path, [{"id": "j1", "year": "2020", "tag": "t",
                                 "extra": [flag]}])
    assert len(q._load_queue(qf)) == 1


def test_a_coarse_year_is_exempt(tmp_path):
    """Coarse tier already forces citywide (cli.py: tier == "coarse" or force_citywide).
    Demanding a redundant flag there would train people to add flags that do nothing,
    which is its own hazard."""
    import sys as _s
    _s.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
    from phase4seg import config as C
    coarse = next(e["label"] for e in C.YEAR_CATALOG if C.tier_for(e) == "coarse")
    qf = _queue_file(tmp_path, [{"id": "j1", "year": coarse, "tag": "t", "extra": []}])
    assert len(q._load_queue(qf)) == 1, f"{coarse} is coarse and should be exempt"


def test_every_shipped_queue_file_still_loads():
    """The guard must not break the 31 queue files that already exist."""
    qdir = Path(__file__).resolve().parents[1] / "pipeline"
    refused = []
    for f in sorted(qdir.glob("queue_*.yaml")):
        try:
            q._load_queue(f.name)
        except SystemExit as e:
            refused.append(f"{f.name}: {str(e).splitlines()[0]}")
    assert not refused, "shipped queues refused by the new guard:\n  " + "\n  ".join(refused)
