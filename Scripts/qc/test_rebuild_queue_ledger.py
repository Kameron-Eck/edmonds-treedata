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


def _block(year, step, tag, run_id, step_log_name, outcome=None):
    """One `$` command block: the queue's command, the engine's two echo lines,
    and optionally the queue's outcome line. Indentation is the whole point —
    queue lines are two spaces, engine stdout is `    | `."""
    s = (f"\n  $ -u /content/repo/Scripts/pipeline/phase4_semantic_finetune.py "
         f"--year {year} --step {step} --infer-batch 32 --run-tag {tag} "
         f"--force-citywide\n"
         f"    |   run_id: {run_id}  (git deadbeef on work/x; GPU none)\n"
         f"    |   ✓ log → /content/drive/MyDrive/treedata/phase4/logs/"
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
    # ts is the step log's `completed:`, reshaped to the ledger's format
    assert ev[0]["ts"] == "2026-09-03 01:26:10"
    # host/session are not derivable from a log and are left blank, not guessed
    assert ev[0]["host"] == "" and ev[0]["session"] == ""


def test_a_covered_step_is_never_synthesised(evidence, monkeypatch):
    """train IS covered by the snapshots, so its log outcome adds no row — a
    synthesised row could only compete with a queue-written one on latest-wins."""
    rows, _out, _rep = _run_main(evidence, monkeypatch)
    recovered_train = [r for r in rows if r["step"] == "train"
                       and r["detail"].startswith(rql.PREFIX)]
    assert recovered_train == []


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
