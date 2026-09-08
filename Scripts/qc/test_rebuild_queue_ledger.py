"""Tests for qc/instruments/rebuild_queue_ledger.py — the ledger recovery candidate.

Everything here runs on SYNTHETIC snapshots, nohup logs and step logs under
tmp_path. Nothing reads or writes the real lake; `qc/conftest.py` would catch it
if it did, and the instrument's own `assert_not_lake` is exercised directly.

The properties under test are the ones that decide whether the candidate can ever
be trusted enough to copy onto the lake:

  · a snapshot row is passed through unchanged, and two snapshots holding the same
    flush of the same row collapse to ONE;
  · the same (job, year, tag, step) recorded twice with different states stays TWO
    rows — that history is what latest-wins needs;
  · a row is synthesised ONLY where the log printed a terminal outcome AND a step
    log gives it a timestamp;
  · a VERIFY verdict is never invented: no printed verdict, no VERIFY row, and a
    printed one is carried through verbatim;
  · the output name satisfies `phase4seg.names.is_status_file`, or the write is an
    error rather than a file no reader would merge;
  · the writer refuses any path inside a lake root, including a fake one;
  · two runs on the same inputs are byte-identical.
"""
import csv
import io
import sys
from pathlib import Path

import pytest

from instruments import rebuild_queue_ledger as rql
from phase4seg.names import is_status_file

COLS = rql.COLS


# ── fixtures: the three synthetic evidence shapes ─────────────────────────────

def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return path


def _snapshot(path, rows):
    """A queue-written status snapshot: the 11 columns, CRLF, as _status_write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})
    return path


def _row(job, year, tag, step, state, exit_="", minutes="", detail="",
         ts="2026-09-03 01:00:00", host="h1", session="s1"):
    return dict(job=job, year=year, tag=tag, step=step, state=state, exit=exit_,
                minutes=minutes, detail=detail, ts=ts, host=host, session=session)


def _step_log(logs, step, year, stamp, started, completed, run_id):
    """An engine step log, header-shaped like pipeline_log.write_step_log's."""
    name = f"phase4_semantic_finetune_{step}_{year}_{stamp}.log"
    return _write(logs / name,
                  f"=== phase4_semantic_finetune --step {step}_{year} ===\n"
                  f"started:   {started}\n"
                  f"completed: {completed}\n"
                  f"elapsed:   0.0s\n"
                  f"run id     {run_id}\n"
                  f"\n--- stdout ---\n\nnothing\n")


def _nohup_header(queue):
    return ("=" * 74 + "\n"
            "  PHASE 4 — UNATTENDED TRAIN QUEUE\n"
            + "=" * 74 + "\n"
            "  BASE   : /content/drive/MyDrive/treedata\n"
            f"  queue  : {queue}\n"
            "  jobs   : 1 of 1\n\n")


def _job_header(job, year, tag):
    return ("\n" + "=" * 74 + "\n"
            f"  JOB {job}  (year {year}, tag {tag})\n"
            + "=" * 74 + "\n"
            "  why not\n")


def _block(year, step, tag, run_id, step_log_name, outcome=None,
           echo_run_id=True):
    """One `$` command block: the queue's command, the engine's two echo lines,
    and optionally the queue's outcome line. Indentation is the whole point —
    queue lines are two spaces, engine stdout is `    | `.

    `echo_run_id=False` drops the run_id line, which is the shape 4 of the 177
    real blocks in the window have — and the one that sends `_anchor` to its
    second rung."""
    s = (f"\n  $ -u /content/repo/Scripts/pipeline/phase4_semantic_finetune.py "
         f"--year {year} --step {step} --infer-batch 32 --run-tag {tag} "
         f"--force-citywide\n")
    if echo_run_id:
        s += f"    |   run_id: {run_id}  (git deadbeef on work/x; GPU none)\n"
    s += (f"    |   ✓ log → /content/drive/MyDrive/treedata/phase4/logs/"
          f"{step_log_name}\n")
    if outcome is not None:
        s += outcome
    return s


@pytest.fixture()
def evidence(tmp_path):
    """A whole synthetic window: two snapshots, one nohup log, three step logs.

    jobA/1999/tagA — train covered by the snapshots, evaluate NOT covered.
    jobB/1998/tagB — train ran and died with no outcome line.
    """
    rec, logs = tmp_path / "rec", tmp_path / "logs"
    _snapshot(rec / "train_queue_status.csv.part.aaa", [
        _row("jobA", "1999", "tagA", "train", "RUNNING", ts="2026-09-03 01:00:00"),
        _row("jobA", "1999", "tagA", "train", "OK", "0", "12.5",
             ts="2026-09-03 01:00:00"),
    ])
    _snapshot(rec / "train_queue_status.csv.part.bbb", [
        # byte-identical repeat of the terminal row — a later flush of the same
        # launch re-writes it; must collapse to one
        _row("jobA", "1999", "tagA", "train", "OK", "0", "12.5",
             ts="2026-09-03 01:00:00"),
        # a LATER, different state for the same key — must survive as its own row
        _row("jobA", "1999", "tagA", "train", "FAIL", "1", "0.4",
             ts="2026-09-03 05:00:00"),
    ])
    _snapshot(rec / "train_queue_status.csv.SHARED_AS_OF_20260907T2246Z", [
        _row("shared", "1997", "tagS", "labels", "OK", ts="2026-09-07 22:44:34"),
    ])

    _step_log(logs, "train", "1999", "2026-09-03T01-10",
              "2026-09-03T01:10:00.000000", "2026-09-03T01:22:30.000000",
              "20260903T011000Z_1999_tagA_train")
    _step_log(logs, "evaluate", "1999", "2026-09-03T01-25",
              "2026-09-03T01:25:00.000000", "2026-09-03T01:26:10.000000",
              "20260903T012500Z_1999_tagA_evaluate")
    _step_log(logs, "train", "1998", "2026-09-03T02-00",
              "2026-09-03T02:00:00.000000", "2026-09-03T02:01:00.000000",
              "20260903T020000Z_1998_tagB_train")

    log = _nohup_header("queue_fake.yaml")
    log += _job_header("jobA", "1999", "tagA")
    log += _block("1999", "train", "tagA", "20260903T011000Z_1999_tagA_train",
                  "phase4_semantic_finetune_train_1999_2026-09-03T01-10.log",
                  "  [jobA/train] exit=0  elapsed 12.5 min\n"
                  "  VERIFY:train jobA: OK  773MB, AE18, run_id ok\n")
    log += _block("1999", "evaluate", "tagA",
                  "20260903T012500Z_1999_tagA_evaluate",
                  "phase4_semantic_finetune_evaluate_1999_2026-09-03T01-25.log",
                  "  [jobA/evaluate] exit=0  elapsed 1.2 min\n"
                  "  VERIFY:evaluate jobA: OK  2 rows for 1999/tagA, written 01:26\n"
                  "  VERIFY jobA: OK  4165MB valid=73.0% maxprob=0.894\n")
    log += _job_header("jobB", "1998", "tagB")
    log += _block("1998", "train", "tagB", "20260903T020000Z_1998_tagB_train",
                  "phase4_semantic_finetune_train_1998_2026-09-03T02-00.log")
    _write(logs / "train_queue_nohup_queue_fake_20260903T010000Z.log", log)

    return dict(rec=rec, logs=logs, tmp=tmp_path)


def _run_main(ev, monkeypatch, out=None, report=None, extra=()):
    out = out or ev["tmp"] / "out" / "train_queue_status_recovered_test.csv"
    report = report or ev["tmp"] / "out" / "report.md"
    argv = ["rebuild_queue_ledger.py",
            "--recovery-dir", str(ev["rec"]), "--logs-dir", str(ev["logs"]),
            "--out", str(out), "--report", str(report),
            "--since", "20260901", "--until", "20260907", *extra]
    monkeypatch.setattr(sys, "argv", argv)
    rql.main()
    with io.open(out, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh)), out, report


# ── snapshots ─────────────────────────────────────────────────────────────────

def test_identical_rows_from_two_snapshots_collapse_to_one(evidence, monkeypatch):
    rows, _out, _rep = _run_main(evidence, monkeypatch)
    same = [r for r in rows if r["step"] == "train" and r["state"] == "OK"
            and r["tag"] == "tagA"]
    assert len(same) == 1, "a row re-flushed into a second snapshot was duplicated"


def test_all_recorded_states_for_one_key_are_kept(evidence, monkeypatch):
    """The ledger is append-style and readers take the latest ts. Collapsing the
    RUNNING/OK/FAIL history of one key onto its last state would destroy exactly
    the evidence queue_ledger.py::_completed_steps needs (a later FAIL revokes an
    earlier OK)."""
    rows, _out, _rep = _run_main(evidence, monkeypatch)
    states = sorted(r["state"] for r in rows
                    if (r["job"], r["step"]) == ("jobA", "train"))
    assert states == ["FAIL", "OK", "RUNNING"]


def test_snapshot_rows_are_passed_through_unchanged(evidence, monkeypatch):
    rows, _out, _rep = _run_main(evidence, monkeypatch)
    ok = [r for r in rows if (r["job"], r["step"], r["state"])
          == ("jobA", "train", "OK")][0]
    assert ok["detail"] == "" and ok["host"] == "h1" and ok["session"] == "s1"
    assert not ok["detail"].startswith(rql.PREFIX)


def test_shared_copy_is_excluded_unless_asked_for(evidence, monkeypatch):
    rows, _out, _rep = _run_main(evidence, monkeypatch)
    assert not [r for r in rows if r["tag"] == "tagS"]
    rows2, _o, _r = _run_main(evidence, monkeypatch,
                              out=evidence["tmp"] / "o2"
                              / "train_queue_status_recovered_test.csv",
                              report=evidence["tmp"] / "o2" / "r.md",
                              extra=("--include-shared",))
    assert [r for r in rows2 if r["tag"] == "tagS"]


# ── synthesis ─────────────────────────────────────────────────────────────────

def test_uncovered_step_is_synthesised_with_the_queues_own_minutes(
        evidence, monkeypatch):
    """evaluate has no snapshot row, so it is recovered — and `minutes` is the
    12-second-precision number the QUEUE printed (1.2), never the step log's
    `elapsed`, which measures a different interval (0.0s in the fixture)."""
    rows, _out, _rep = _run_main(evidence, monkeypatch)
    ev = [r for r in rows if (r["job"], r["step"]) == ("jobA", "evaluate")]
    assert len(ev) == 1
    assert ev[0]["state"] == "OK" and ev[0]["exit"] == "0"
    assert ev[0]["minutes"] == "1.2"
    assert ev[0]["detail"].startswith(rql.PREFIX)
    # `ts` is the step START, because that is what a queue-written ts is. The
    # block's run_id stamp (20260903T012500Z) is the log's own timestamp for it;
    # the step log's `completed:` (01:26:10) is when the step ENDED.
    assert ev[0]["ts"] == "2026-09-03 01:25:00"
    assert ev[0]["detail"].startswith(rql._prefix(rql.TS_START))
    # host/session are not derivable from a log and are left blank, not guessed
    assert ev[0]["host"] == "" and ev[0]["session"] == ""


def test_a_covered_step_of_the_same_launch_is_never_synthesised(
        evidence, monkeypatch):
    """train IS covered by a snapshot row of the SAME launch, so its log outcome
    adds no row — a synthesised row could only compete with a queue-written one on
    latest-wins. (A row from a DIFFERENT launch does not cover it: see
    test_a_later_launch_under_a_reused_tag_is_recovered.)"""
    rows, _out, _rep = _run_main(evidence, monkeypatch)
    recovered_train = [r for r in rows if r["step"] == "train"
                       and r["detail"].startswith(rql.PREFIX)]
    assert recovered_train == []


# ── L1: suppression is per LAUNCH ─────────────────────────────────────────────

@pytest.fixture()
def relaunch(tmp_path):
    """One tag, two launches: an earlier one whose rows SURVIVED and a later one
    whose rows were erased. This is the of_2017k shape — ofB/of2017k failed under
    the tag and their rows sit in orphans, of2017k2 then ran the whole pipeline and
    its rows were clobbered — and it is the case the first version could not
    recover, because the failed launches' rows covered the key."""
    rec, logs = tmp_path / "rec", tmp_path / "logs"
    _snapshot(rec / "train_queue_status.csv.part.one", [
        _row("of_job", "2017k", "of_tag", "labels", "OK", "0", "9.0",
             ts="2026-09-06 00:20:05", host="hostA", session="sessA"),
        _row("of_job", "2017k", "of_tag", "VERIFY:labels", "MISSING",
             detail="no site masks", ts="2026-09-06 00:29:10",
             host="hostA", session="sessA"),
    ])
    # launch 1 — the failed one whose ledger row survived
    _step_log(logs, "labels", "2017k", "2026-09-06T00-29",
              "2026-09-06T00:29:00.000000", "2026-09-06T00:29:00.000000",
              "20260906T002010Z_2017k_of_tag_labels")
    log1 = _nohup_header("queue_of.yaml") + _job_header("of_job", "2017k", "of_tag")
    log1 += _block("2017k", "labels", "of_tag", "20260906T002010Z_2017k_of_tag_labels",
                   "phase4_semantic_finetune_labels_2017k_2026-09-06T00-29.log",
                   "  [of_job/labels] exit=0  elapsed 9.0 min\n"
                   "  VERIFY:labels of_job: MISSING  no site masks\n")
    _write(logs / "train_queue_nohup_queue_of_20260906T002000Z.log", log1)
    # launch 2 — the successful one whose ledger rows were erased
    _step_log(logs, "labels", "2017k", "2026-09-06T01-42",
              "2026-09-06T01:42:44.000000", "2026-09-06T01:42:44.000000",
              "20260906T014036Z_2017k_of_tag_labels")
    _step_log(logs, "tile", "2017k", "2026-09-06T02-03",
              "2026-09-06T01:44:00.000000", "2026-09-06T02:03:07.000000",
              "20260906T014248Z_2017k_of_tag_tile")
    log2 = _nohup_header("queue_of.yaml") + _job_header("of_job", "2017k", "of_tag")
    log2 += _block("2017k", "labels", "of_tag", "20260906T014036Z_2017k_of_tag_labels",
                   "phase4_semantic_finetune_labels_2017k_2026-09-06T01-42.log",
                   "  [of_job/labels] exit=0  elapsed 2.3 min\n"
                   "  VERIFY:labels of_job: OK  citywide: labels step is skipped "
                   "by design\n")
    log2 += _block("2017k", "tile", "of_tag", "20260906T014248Z_2017k_of_tag_tile",
                   "phase4_semantic_finetune_tile_2017k_2026-09-06T02-03.log",
                   "  [of_job/tile] exit=0  elapsed 21.1 min\n"
                   "  VERIFY:tile of_job: OK  632 tiles indexed\n")
    _write(logs / "train_queue_nohup_queue_of_20260906T014000Z.log", log2)
    return dict(rec=rec, logs=logs, tmp=tmp_path)


def test_a_later_launch_under_a_reused_tag_is_recovered(relaunch, monkeypatch):
    """The whole point of L1. A relaunch keeps the run-tag, so (year, tag, step)
    cannot tell two runs apart; keying suppression on it let a FAILED launch's
    surviving row erase a LATER successful one's outcome."""
    rows, _out, _rep = _run_main(relaunch, monkeypatch)
    labels = sorted((r["minutes"], r["ts"], r["detail"][:40])
                    for r in rows if r["step"] == "labels")
    assert [m for m, _t, _d in labels] == ["2.3", "9.0"]
    got = {r["minutes"]: r for r in rows if r["step"] == "labels"}
    # the survivor is untouched…
    assert got["9.0"]["session"] == "sessA" and got["9.0"]["detail"] == ""
    # …and the later launch's row is recovered, quoting ITS log
    assert got["2.3"]["detail"].startswith(rql._prefix(rql.TS_START))
    assert "20260906T014000Z" in got["2.3"]["detail"]
    assert got["2.3"]["ts"] == "2026-09-06 01:40:36"
    tile = [r for r in rows if r["step"] == "tile"]
    assert len(tile) == 1 and tile[0]["minutes"] == "21.1"
    assert tile[0]["ts"] == "2026-09-06 01:42:48"


def test_the_earlier_launchs_own_outcome_is_still_suppressed(relaunch, monkeypatch):
    """Launch-keying must not become "synthesise everything": the row that DID
    survive still speaks for its own launch, and a second copy of it would carry
    the RECOVERED prefix into a key the queue itself recorded."""
    rows, _out, _rep = _run_main(relaunch, monkeypatch)
    assert not [r for r in rows if r["minutes"] == "9.0"
                and r["detail"].startswith(rql.PREFIX)]
    # its VERIFY verdict survived too, and is not written a second time
    missing = [r for r in rows if r["state"] == "MISSING"]
    assert len(missing) == 1 and missing[0]["session"] == "sessA"


def _ev(src, step, state, minutes, kind="step", job="jobA", year="1999",
        tag="tagA", verdict=""):
    """The minimum of a parsed event that `_event_fp` reads."""
    return dict(kind=kind, src=src, job=job, year=year, tag=tag, step=step,
                state=state, minutes=minutes, verdict=verdict)


def test_attribution_needs_the_window_and_the_content_together():
    """Neither signal alone maps a session to its launch.

    TIME alone fails: hardyear4's rows exactly match one outcome line in a launch
    that had already ended — a relaunch of the same job re-printing the same
    rounded `minutes`. CONTENT alone fails for the same reason. Together they are
    unambiguous on the whole window."""
    spans = {"L1": ("2026-09-01 19:47:01", "2026-09-01 21:15:16"),
             "L2": ("2026-09-01 21:18:44", "2026-09-01 22:35:00")}
    events = [_ev("L1", "train", "OK", "5.0"), _ev("L2", "train", "OK", "5.0")]
    rows = [_row("jobA", "1999", "tagA", "train", "OK", "0", "5.0",
                 ts="2026-09-01 21:18:46", host="h", session="s")]
    launch_of, table = rql.attribute_launches(rows, events, spans)
    assert launch_of[("h", "s")] == "L2", "the ended launch was chosen on content"
    assert table[0]["matches"] == 1


def test_a_session_that_matches_nothing_is_left_unattributed():
    """Zero exact matches means the launch is unknown, and an unknown launch
    covers nothing. The safe direction: it can only ADD a row the log proves."""
    spans = {"L1": ("2026-09-01 19:47:01", "2026-09-01 21:15:16")}
    events = [_ev("L1", "train", "OK", "5.0")]
    rows = [_row("jobA", "1999", "tagA", "train", "RUNNING",
                 ts="2026-09-01 19:50:00", host="h", session="s")]
    launch_of, table = rql.attribute_launches(rows, events, spans)
    assert launch_of[("h", "s")] is None
    assert table[0]["launch"] == "" and table[0]["n_candidates"] == 1


def test_a_block_without_an_outcome_line_yields_no_row(evidence, monkeypatch):
    """jobB's train block has the command and the engine echo but no
    `[job/step] exit=…` — the runtime died mid-step. The queue never recorded a
    terminal state and neither may this."""
    rows, _out, report = _run_main(evidence, monkeypatch)
    assert not [r for r in rows if r["tag"] == "tagB"]
    text = report.read_text(encoding="utf-8")
    assert "the runtime died mid-step" in text
    assert "--run-tag tagB" in text, "the refusal must NAME the evidence"


def test_verify_rows_are_only_written_where_a_verdict_was_printed(
        evidence, monkeypatch):
    """jobB printed no VERIFY line at all; no VERIFY row may appear for it. jobA's
    verdicts were printed and are carried through verbatim."""
    rows, _out, _rep = _run_main(evidence, monkeypatch)
    assert not [r for r in rows if r["job"] == "jobB" and "VERIFY" in r["step"]]
    v = [r for r in rows if r["step"] == "VERIFY" and r["job"] == "jobA"][0]
    assert v["state"] == "OK"
    assert '"4165MB valid=73.0% maxprob=0.894"' in v["detail"]
    vt = [r for r in rows if r["step"] == "VERIFY:train"][0]
    assert '"773MB, AE18, run_id ok"' in vt["detail"]


def test_a_verify_state_is_never_invented_from_a_malformed_line(tmp_path):
    """`_split_verdict` is the only thing that turns a printed line into a state.
    Anything that is not a bare upper-case token is refused, not guessed."""
    assert rql._split_verdict("OK  773MB, AE18") == ("OK", "773MB, AE18")
    assert rql._split_verdict("OK") == ("OK", "")
    state, detail = rql._split_verdict(
        "UNCHECKED" + rql.UNPROVEN + "  RuntimeError: boom")
    assert (state, detail) == ("UNCHECKED", "RuntimeError: boom")
    assert rql._split_verdict("probably fine  whatever") == ("", "")
    assert rql._split_verdict("ok  lowercase") == ("", "")


def test_the_unproven_variant_keeps_the_state_out_of_the_verdict_text(tmp_path):
    """verify_step prints D7 states through a banner. The banner belongs to
    neither the state nor the verdict; swallowing it into `detail` would make the
    recovered text differ from what the queue would have written."""
    state, detail = rql._split_verdict("UNVERIFIED" + rql.UNPROVEN + "  no size")
    assert state == "UNVERIFIED"
    assert "COULD NOT CHECK" not in detail


def test_a_verify_for_a_step_the_preceding_block_did_not_run_is_refused(
        tmp_path, monkeypatch):
    """A D7 re-verify of a SKIPPED step prints a VERIFY:{step} line with no block
    of its own. Anchoring it on the previous step's clock would date it wrongly,
    so it is refused and reported instead."""
    rec, logs = tmp_path / "rec", tmp_path / "logs"
    _snapshot(rec / "train_queue_status.csv.part.aaa", [])
    _step_log(logs, "train", "1999", "2026-09-03T01-10",
              "2026-09-03T01:10:00.000000", "2026-09-03T01:22:30.000000",
              "rid_train")
    log = _nohup_header("queue_fake.yaml") + _job_header("jobA", "1999", "tagA")
    log += _block("1999", "train", "tagA", "rid_train",
                  "phase4_semantic_finetune_train_1999_2026-09-03T01-10.log",
                  "  [jobA/train] exit=0  elapsed 12.5 min\n"
                  "  VERIFY:train jobA: OK  773MB ok\n"
                  "  VERIFY:inference jobA: OK  4165MB valid=73.0%\n")
    _write(logs / "train_queue_nohup_queue_fake_20260903T010000Z.log", log)

    out = tmp_path / "out" / "train_queue_status_recovered_test.csv"
    report = tmp_path / "out" / "r.md"
    monkeypatch.setattr(sys, "argv", [
        "x", "--recovery-dir", str(rec), "--logs-dir", str(logs),
        "--out", str(out), "--report", str(report)])
    rql.main()
    with io.open(out, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert sorted(r["step"] for r in rows) == ["VERIFY:train", "train"]
    assert "not 'inference'" in report.read_text(encoding="utf-8")


def test_a_block_whose_step_log_is_absent_is_refused(tmp_path, monkeypatch):
    """No step log means no timestamp. A blank ts sorts FIRST in a lexical merge,
    which silently makes a recovered row the oldest thing in the ledger — refuse
    rather than write one."""
    rec, logs = tmp_path / "rec", tmp_path / "logs"
    _snapshot(rec / "train_queue_status.csv.part.aaa", [])
    logs.mkdir(parents=True, exist_ok=True)
    log = _nohup_header("queue_fake.yaml") + _job_header("jobA", "1999", "tagA")
    log += _block("1999", "train", "tagA", "rid_train",
                  "phase4_semantic_finetune_train_1999_2026-09-03T01-10.log",
                  "  [jobA/train] exit=0  elapsed 12.5 min\n")
    _write(logs / "train_queue_nohup_queue_fake_20260903T010000Z.log", log)
    out = tmp_path / "out" / "train_queue_status_recovered_test.csv"
    report = tmp_path / "out" / "r.md"
    monkeypatch.setattr(sys, "argv", [
        "x", "--recovery-dir", str(rec), "--logs-dir", str(logs),
        "--out", str(out), "--report", str(report)])
    rql.main()
    with io.open(out, encoding="utf-8", newline="") as fh:
        assert list(csv.DictReader(fh)) == []
    assert "is not on the lake" in report.read_text(encoding="utf-8")


def test_a_resume_skip_writes_no_row(tmp_path, monkeypatch):
    rec, logs = tmp_path / "rec", tmp_path / "logs"
    _snapshot(rec / "train_queue_status.csv.part.aaa", [])
    logs.mkdir(parents=True, exist_ok=True)
    log = (_nohup_header("queue_fake.yaml") + _job_header("jobA", "1999", "tagA")
           + "  - skip jobA/train (already OK)\n")
    _write(logs / "train_queue_nohup_queue_fake_20260903T010000Z.log", log)
    out = tmp_path / "out" / "train_queue_status_recovered_test.csv"
    monkeypatch.setattr(sys, "argv", [
        "x", "--recovery-dir", str(rec), "--logs-dir", str(logs),
        "--out", str(out), "--report", str(tmp_path / "out" / "r.md")])
    rql.main()
    with io.open(out, encoding="utf-8", newline="") as fh:
        assert list(csv.DictReader(fh)) == []


def test_engine_stdout_mentioning_verify_is_not_parsed_as_a_verdict(tmp_path):
    """Engine stdout is re-printed behind `    | ` and it TALKS ABOUT VERIFY —
    every staged-write line ends "VERIFY:train/inference is what proves it
    landed". A pattern that is not anchored at the start of a queue-indented line
    would turn that prose, and any verdict-shaped line the engine echoes, into
    ledger rows. Parsed end-to-end, because that is where it would do harm."""
    logs = tmp_path / "logs"
    log = _nohup_header("queue_fake.yaml") + _job_header("jobA", "1999", "tagA")
    log += (
        "\n  $ -u /x/phase4_semantic_finetune.py --year 1999 --step train "
        "--infer-batch 32 --run-tag tagA\n"
        "    |   ✓ staged write: sem_best.pt (773 MB, sha256 ok) — Drive NOT "
        "CONFIRMED. VERIFY:train/inference is what proves it landed.\n"
        "    |   VERIFY:train nested: FAIL  echoed, not this queue's verdict\n"
        "    |   [nested/train] exit=1  elapsed 9.9 min\n")
    p = _write(logs / "train_queue_nohup_queue_fake_20260903T010000Z.log", log)
    events, _notes = rql.parse_nohup(p)
    assert events == [], f"engine stdout became {len(events)} ledger event(s)"


# ── L2: which clock a recovered `ts` comes from ───────────────────────────────

def _one_block_run(tmp_path, monkeypatch, outcome, run_id="rid",
                   echo_run_id=True, started="2026-09-03T01:10:00.000000",
                   completed="2026-09-03T01:22:30.000000", snapshot_rows=()):
    """One job, one block, no surviving rows unless asked → the ladder in
    isolation. Returns the candidate's rows."""
    rec, logs = tmp_path / "rec", tmp_path / "logs"
    _snapshot(rec / "train_queue_status.csv.part.aaa", list(snapshot_rows))
    _step_log(logs, "train", "1999", "2026-09-03T01-10", started, completed,
              run_id)
    log = _nohup_header("q.yaml") + _job_header("jobA", "1999", "tagA")
    log += _block("1999", "train", "tagA", run_id,
                  "phase4_semantic_finetune_train_1999_2026-09-03T01-10.log",
                  outcome, echo_run_id=echo_run_id)
    _write(logs / "train_queue_nohup_q_20260903T010000Z.log", log)
    out = tmp_path / "out" / "train_queue_status_recovered_test.csv"
    report = tmp_path / "out" / "r.md"
    monkeypatch.setattr(sys, "argv", [
        "x", "--recovery-dir", str(rec), "--logs-dir", str(logs),
        "--out", str(out), "--report", str(report)])
    rql.main()
    with io.open(out, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh)), report


def test_ts_falls_to_completed_minus_minutes_when_the_block_has_no_run_id(
        tmp_path, monkeypatch):
    """Rung 2. Four of the 177 real blocks in the window print no run_id line; the
    queue's own `elapsed` then reconstructs the same interval the queue timed,
    because `run_step` starts its clock one line after it stamps the row."""
    rows, _rep = _one_block_run(
        tmp_path, monkeypatch, "  [jobA/train] exit=0  elapsed 12.5 min\n",
        echo_run_id=False)
    got = [r for r in rows if r["step"] == "train"][0]
    assert got["ts"] == "2026-09-03 01:10:00"        # 01:22:30 − 12.5 min
    assert got["detail"].startswith(rql._prefix(rql.TS_COMPLETED_MINUTES))


def test_a_run_id_stamped_off_the_steps_own_window_is_refused(
        tmp_path, monkeypatch):
    """The gate, shown FIRING. A run_id whose stamp cannot belong to this step —
    another VM's clock, another zone — must not pass itself off as a start; the
    ladder falls to rung 2 and the row says so."""
    rows, _rep = _one_block_run(
        tmp_path, monkeypatch, "  [jobA/train] exit=0  elapsed 12.5 min\n",
        run_id="20260902T221000Z_1999_tagA_train")        # 3 h too early
    got = [r for r in rows if r["step"] == "train"][0]
    assert got["ts"] == "2026-09-03 01:10:00"
    assert got["detail"].startswith(rql._prefix(rql.TS_COMPLETED_MINUTES))
    # …and the SAME stamp inside the window is taken
    rows2, _r2 = _one_block_run(
        tmp_path / "b", monkeypatch, "  [jobA/train] exit=0  elapsed 12.5 min\n",
        run_id="20260903T011005Z_1999_tagA_train")
    got2 = [r for r in rows2 if r["step"] == "train"][0]
    assert got2["ts"] == "2026-09-03 01:10:05"
    assert got2["detail"].startswith(rql._prefix(rql.TS_START))


def test_a_timeout_dates_from_completed_because_nothing_else_exists(
        tmp_path, monkeypatch):
    """Rung 3 on a step. A TIMEOUT prints no `elapsed`, so `minutes` stays blank
    (`cost_report` sums that column and a guess would be spend that never
    happened) — and with no minutes there is nothing to subtract."""
    rows, _rep = _one_block_run(
        tmp_path, monkeypatch,
        "  ! TIMEOUT: jobA/train exceeded 240 min — killing it and moving on.\n",
        echo_run_id=False)
    got = [r for r in rows if r["step"] == "train"][0]
    assert (got["state"], got["exit"], got["minutes"]) == ("TIMEOUT", "killed", "")
    assert got["ts"] == "2026-09-03 01:22:30"
    assert got["detail"].startswith(rql._prefix(rql.TS_COMPLETED))


def test_a_verify_row_carries_the_moment_the_check_began(tmp_path, monkeypatch):
    """Rung 3 on a VERIFY, and the only rung one may use. `verify_step` stamps its
    row when the check ENDS, and the log prints no duration for it — measured on
    the CPU pilot, a labels VERIFY ran seven minutes — so the honest value is the
    step's `completed:`, which is when the check started."""
    rows, _rep = _one_block_run(
        tmp_path, monkeypatch,
        "  [jobA/train] exit=0  elapsed 12.5 min\n"
        "  VERIFY:train jobA: OK  773MB, AE18\n",
        run_id="20260903T011000Z_1999_tagA_train")
    v = [r for r in rows if r["step"] == "VERIFY:train"][0]
    assert v["ts"] == "2026-09-03 01:22:30"
    assert v["detail"].startswith(rql._prefix(rql.TS_COMPLETED))
    # the step it follows still dates from its own start
    assert [r for r in rows if r["step"] == "train"][0]["ts"] == \
        "2026-09-03 01:10:00"


def test_same_run_suspects_fires_when_the_attribution_is_broken(
        tmp_path, monkeypatch):
    """The check on L1, mutation-tested. With attribution working the surviving
    row covers its own launch and nothing is synthesised; with it disabled the
    same execution is recorded twice, seconds apart — which is exactly the
    signature `same_run_suspects` exists to catch."""
    survivor = [_row("jobA", "1999", "tagA", "train", "OK", "0", "12.5",
                     ts="2026-09-03 01:09:58", host="h", session="s")]
    rows, report = _one_block_run(
        tmp_path, monkeypatch, "  [jobA/train] exit=0  elapsed 12.5 min\n",
        run_id="20260903T011000Z_1999_tagA_train", snapshot_rows=survivor)
    assert len([r for r in rows if r["step"] == "train"]) == 1
    assert "### Same-run suspects" in report.read_text(encoding="utf-8")
    assert rql.same_run_suspects(rows) == []

    monkeypatch.setattr(rql, "attribute_launches", lambda *a, **k: ({}, []))
    rows2, report2 = _one_block_run(
        tmp_path / "b", monkeypatch,
        "  [jobA/train] exit=0  elapsed 12.5 min\n",
        run_id="20260903T011000Z_1999_tagA_train", snapshot_rows=survivor)
    got = rql.same_run_suspects(rows2)
    assert [d["key"] for d in got] == [("1999", "tagA", "train")]
    assert "1999/tagA/train" in report2.read_text(encoding="utf-8")


def test_queue_ts_reshapes_without_inventing_precision():
    assert rql._queue_ts("2026-09-07T21:58:43.137755") == "2026-09-07 21:58:43"
    assert rql._queue_ts("2026-09-07 21:58:43") == "2026-09-07 21:58:43"
    assert rql._queue_ts("") == ""
    assert rql._queue_ts("not a time") == ""


# ── the schema and the write guard ────────────────────────────────────────────

def test_stale_running_diagnostic_breaks_ties_towards_the_terminal_state(
        tmp_path):
    """A key whose ONLY surviving row is RUNNING is genuinely stuck mid-step and is
    reported. A key whose RUNNING and terminal row both survived at one timestamp
    is NOT — the row order this file writes has already settled it, and listing it
    would send Kam after a step that is fine."""
    logs = tmp_path / "logs"
    _step_log(logs, "train", "1999", "2026-09-03T01-10",
              "2026-09-03T01:10:00.000000", "2026-09-03T01:22:30.000000", "rid1")
    _step_log(logs, "tile", "1998", "2026-09-03T02-10",
              "2026-09-03T02:10:00.000000", "2026-09-03T02:22:30.000000", "rid2")
    log = _nohup_header("q.yaml") + _job_header("jobA", "1999", "tagA")
    log += _block("1999", "train", "tagA", "rid1",
                  "phase4_semantic_finetune_train_1999_2026-09-03T01-10.log",
                  "  [jobA/train] exit=0  elapsed 1.0 min\n")
    log += _job_header("jobB", "1998", "tagB")
    log += _block("1998", "tile", "tagB", "rid2",
                  "phase4_semantic_finetune_tile_1998_2026-09-03T02-10.log",
                  "  [jobB/tile] exit=0  elapsed 2.0 min\n")
    p = _write(logs / "train_queue_nohup_q_20260903T010000Z.log", log)
    events, _notes = rql.parse_nohup(p)
    # jobA's RUNNING row is listed LAST on purpose: a "last one wins" tie-break
    # would pick it and report a finished step as stuck.
    snaps = [
        _row("jobA", "1999", "tagA", "train", "OK", "0", "1.0",
             ts="2026-09-03 01:00:00"),
        _row("jobA", "1999", "tagA", "train", "RUNNING", ts="2026-09-03 01:00:00"),
        _row("jobB", "1998", "tagB", "tile", "RUNNING", ts="2026-09-03 02:00:00"),
    ]
    got = rql.stale_running_coverage(events, snaps, logs)
    assert [d["key"] for d in got] == [("1998", "tagB", "tile")]


def test_output_has_exactly_the_eleven_ledger_columns(evidence, monkeypatch):
    """A twelfth provenance column would hand every reader's DictReader a schema
    it does not know. Provenance lives in `detail` and in the report."""
    _rows, out, _rep = _run_main(evidence, monkeypatch)
    with io.open(out, encoding="utf-8", newline="") as fh:
        header = next(csv.reader(fh))
    assert header == ["job", "year", "tag", "step", "state", "exit", "minutes",
                      "detail", "ts", "host", "session"]


def test_the_real_output_name_is_one_readers_merge():
    assert is_status_file(rql.DEFAULT_OUT.name)
    assert rql.DEFAULT_OUT.name == "train_queue_status_recovered_20260901_20260907.csv"


def test_a_name_no_reader_would_merge_is_an_error(tmp_path):
    with pytest.raises(SystemExit) as e:
        rql.write_csv([], tmp_path / "recovered.csv")
    assert "is_status_file" in str(e.value)


def test_refuses_to_write_under_a_fake_lake_base(tmp_path):
    fake = tmp_path / "fakelake"
    (fake / "phase4" / "qc").mkdir(parents=True)
    target = fake / "phase4" / "qc" / "train_queue_status_recovered_x.csv"
    with pytest.raises(SystemExit) as e:
        rql.assert_not_lake(target, roots=(fake,))
    assert "REFUSING TO WRITE INSIDE THE DATA LAKE" in str(e.value)
    with pytest.raises(SystemExit):
        rql.write_csv([], target, roots=(fake,))
    assert not target.exists()
    # …and a traversal that lands inside the lake is caught on the RESOLVED path
    with pytest.raises(SystemExit):
        rql.assert_not_lake(tmp_path / "elsewhere" / ".." / "fakelake" / "x.csv",
                            roots=(fake,))
    # a sibling whose name merely starts the same way is NOT inside it
    rql.assert_not_lake(tmp_path / "fakelake2" / "x.csv", roots=(fake,))


def test_refuses_the_real_lake_roots(tmp_path, monkeypatch):
    """lake_roots() is read at call time, so both plane literals are covered even
    on the plane whose root does not exist."""
    monkeypatch.setattr(rql.lake, "BASE", tmp_path / "notalake")
    for root in rql.lake_roots():
        with pytest.raises(SystemExit):
            rql.assert_not_lake(Path(root) / "phase4" / "qc" / "x.csv")


def test_main_refuses_an_out_inside_a_lake_root(evidence, monkeypatch):
    fake = evidence["tmp"] / "fakelake"
    monkeypatch.setattr(rql.lake, "BASE", fake)
    monkeypatch.setattr(sys, "argv", [
        "x", "--recovery-dir", str(evidence["rec"]),
        "--logs-dir", str(evidence["logs"]),
        "--out", str(fake / "phase4" / "qc" / "train_queue_status_r.csv"),
        "--report", str(evidence["tmp"] / "r.md")])
    with pytest.raises(SystemExit):
        rql.main()


# ── determinism ───────────────────────────────────────────────────────────────

def test_two_runs_on_the_same_inputs_are_byte_identical(evidence, monkeypatch):
    """A candidate that changes between runs cannot be reviewed. No wall clock
    reaches either output; ordering is the full 11-tuple."""
    _r1, out1, rep1 = _run_main(evidence, monkeypatch)
    a_csv, a_md = out1.read_bytes(), rep1.read_bytes()
    _r2, out2, rep2 = _run_main(
        evidence, monkeypatch,
        out=evidence["tmp"] / "again" / "train_queue_status_recovered_test.csv",
        report=evidence["tmp"] / "again" / "report.md")
    # the paths differ by name only; normalise the one line that names the output
    assert out2.read_bytes() == a_csv
    assert rep2.read_bytes() == a_md


def test_rows_are_sorted_deterministically(evidence, monkeypatch):
    rows, _out, _rep = _run_main(evidence, monkeypatch)
    keys = [rql._sort_key(r) for r in rows]
    assert keys == sorted(keys)


def test_a_running_row_precedes_its_terminal_twin_at_the_same_timestamp(
        evidence, monkeypatch):
    """The mid-step artefact: `run_step` flushes the row as RUNNING and mutates
    that same dict on completion, so two orphans of one launch can preserve both
    halves at ONE `ts`. `queue_ledger.py::_merged_rows` sorts by `ts` alone with a
    STABLE sort, so the reader consumes the file's last such row — and
    `_completed_steps` treats RUNNING as a revocation. Plain 11-tuple order would
    put `OK` before `RUNNING` (alphabetically) and cost a re-run of a step that had
    finished; the terminal row must come LAST."""
    rows, _out, report = _run_main(evidence, monkeypatch)
    at = [i for i, r in enumerate(rows)
          if (r["job"], r["step"], r["ts"]) == ("jobA", "train",
                                                "2026-09-03 01:00:00")]
    states = [rows[i]["state"] for i in at]
    assert states == ["RUNNING", "OK"], f"terminal row not last: {states}"
    assert "Rows that share a timestamp and disagree on state" in \
        report.read_text(encoding="utf-8")
