"""What the queue's STARTUP costs, and that making it cheap changed nothing.

MEASURED, 2026-09-07, from the mirrored lake (no instrument needed — the anchors
were already on disk):

  · the per-launch status file NAME carries the launch stamp (names.py
    ::status_out_name), stamped in main() immediately before the dup-guard;
  · the GUARD:runtag row's `ts` is written the instant _tag_owners returns;
  · the first STEP row's `ts` is written immediately before Popen — and survives
    the later in-place rec.update(state="OK"), which does not touch `ts`.

Five launch-time GUARD rows (sessions hardyear4, trend8A2, trend8B2, ofA, spdc1;
45 → 72 heartbeat files) all stamp the SAME SECOND as their launch stamp: the
beacon scan costs under a second and always did, because the guard has always
stat'ed before reading. The gap is entirely the status merge — guard → first step
row was 173, 280, 343, 174 and 359 s on those same five launches, the last being
76 status files totalling 166 KB, i.e. 4.7 s per file with the network idle.

So this file gates two different things, and the difference is the point:

  BULK STATUS READ — a real fix. One `rclone copy` of the whole set replaces N
  Drive round-trips, and every file is accepted only when its size matches the
  mount's own listing (queue_ledger.py::_stage_status_files). The tests below
  prove the merged rows are identical to the pre-change per-file loop, that a
  short copy makes the size gate FIRE rather than pass, and that every failure
  mode falls back to the mount.

  BEACON FILTER — a regression gate, not a fix. It was already true that a stale
  beacon is never opened; nothing here makes a launch faster. The test counts
  OPENS so that the property stops being an accident of control flow.

No Drive, no GPU, no torch, no rclone: the bulk path is exercised by substituting
queue_ledger.py::_rclone_fetch, which is split out for exactly that reason.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_queue_startup.py -q
"""
import csv
import io
import json
import os
import re
import time
from pathlib import Path

import pytest

q = pytest.importorskip("phase4_train_queue")
queue_ledger = pytest.importorskip("queue_ledger")
names = pytest.importorskip("phase4seg.names")

STATUS_COLS = ["job", "year", "tag", "step", "state", "exit", "minutes",
               "detail", "ts", "host", "session"]


def _status_csv(path, rows, age_s=86400):
    """Write a status file and BACKDATE it.

    The bulk path refuses any file the mount says was touched inside
    queue_ledger.py::_FRESH_SKIP_S, so a fixture written a millisecond ago would
    take the per-file loop and every bulk assertion below would pass vacuously.
    Ageing them is what makes the tests exercise the path they name.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=STATUS_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in STATUS_COLS})
    t = time.time() - age_s
    os.utime(path, (t, t))


def _row(job, step, state, ts, year="2009", tag="t", detail=""):
    return dict(job=job, year=year, tag=tag, step=step, state=state, exit="",
                minutes="", detail=detail, ts=ts, host="h", session="s")


@pytest.fixture
def qc(tmp_path, monkeypatch):
    """A synthetic phase4/qc with three launches' worth of ledger.

    Deliberately includes the two shapes that make the merge order matter: an
    `OK` in one file REVOKED by a later `FAIL` in another (D10's unsafe direction),
    and rows whose `ts` interleave across files rather than nesting.
    """
    d = tmp_path / "qc"
    d.mkdir()
    _status_csv(d / names.status_out_name("a", "20260901T000000Z"), [
        _row("j1", "labels", "OK", "2026-09-01 00:01:00"),
        _row("j1", "tile", "OK", "2026-09-01 00:05:00"),
        _row("j2", "labels", "OK", "2026-09-01 00:09:00"),
    ])
    _status_csv(d / names.status_out_name("b", "20260902T000000Z"), [
        _row("j1", "tile", "FAIL", "2026-09-02 00:03:00"),
        _row("j1", "VERIFY:tile", "MISSING", "2026-09-02 00:04:00"),
    ])
    _status_csv(d / names.status_out_name("c", "20260903T000000Z"), [
        _row("j2", "train", "OK", "2026-09-03 00:02:00"),
        _row("j2", "VERIFY", "OK", "2026-09-03 00:06:00", detail="146MB valid"),
    ])
    # the legacy shared file, which names.is_status_file admits …
    _status_csv(d / "train_queue_status.csv",
                [_row("j0", "inference", "OK", "2026-08-20 00:00:00")])
    # … and two files it must NOT: the quarantined fixture and a publish orphan.
    (d / "train_queue_status.CONTAMINATED-BY-TEST-20260829.csv").write_text(
        "job,year,tag,step,state,ts\nx,x,x,train,OK,2099-01-01 00:00:00\n",
        encoding="utf-8")
    (d / "train_queue_status_a_20260901T000000Z.csv.part.deadbe").write_text(
        "job,year,tag,step,state,ts\ny,y,y,train,OK,2099-01-01 00:00:00\n",
        encoding="utf-8")
    monkeypatch.setattr(q, "QC_DIR", d)
    return d


def _reference_merge(qc_dir):
    """The PRE-CHANGE loop, spelled out, as the thing equivalence is measured against.

    Comparing _merged_rows to itself-with-the-bulk-path-off would only prove the two
    branches agree. This is the code that shipped before 2026-09-07 — one
    names.status_files discovery, one _read_status_file per file through the mount,
    rows extended in that order, sorted by `ts` alone.
    """
    rows = []
    for f in names.status_files(qc_dir):
        got, problem = queue_ledger._read_status_file(f)
        if problem:
            continue
        rows.extend(got)
    rows.sort(key=lambda r: str(r.get("ts", "")))
    return rows


def _fake_rclone(copy=True, truncate=(), replace=None, boom=False):
    """Stand-in for `rclone copy --files-from`. Reads the SAME name list the real
    call is given, so a test cannot silently exercise a different file set.

    `replace` injects the bytes DRIVE holds for a name — which is the whole reason
    the size gate exists: the mount serves this VM's write cache and Drive can be a
    flush behind (queue_verify.py::_drive_matches_mount, the B24/B7 checkpoint).
    """
    def fetch(rel, dst, listfile):
        if boom:
            raise OSError("rclone: no such remote")
        wanted = Path(listfile).read_text(encoding="utf-8").split()
        for name in wanted:
            src = Path(queue_ledger._q().QC_DIR) / name
            if (replace or {}).get(name) is not None:
                (Path(dst) / name).write_bytes(replace[name])
                continue
            if not src.is_file():
                continue                       # rclone silently skips a missing name
            data = src.read_bytes()
            if name in truncate:
                data = data[:len(data) // 2]   # a short/interrupted transfer
            if copy:
                (Path(dst) / name).write_bytes(data)
    return fetch


@pytest.fixture
def bulk(monkeypatch):
    """Force the bulk path on. `_bulk_read_ok` is False on any machine that is not a
    Colab VM with rclone, which is the whole point of it — so the tests substitute
    the gate and the transfer, and exercise everything between them for real."""
    monkeypatch.setattr(queue_ledger, "_bulk_read_ok", lambda qc_dir: True)
    monkeypatch.setattr(q, "_DRIVE_MOUNT_PREFIX", "")
    return monkeypatch


# ── the merge is unchanged, whichever way the bytes arrive ───────────────────

def test_the_bulk_path_and_the_old_per_file_path_merge_to_identical_rows(qc, bulk):
    """THE EQUIVALENCE GATE. Same directory, two transports, one answer — row for
    row, in order, including the D10 case where a later FAIL in file B revokes an
    earlier OK in file A."""
    bulk.setattr(queue_ledger, "_rclone_fetch", _fake_rclone())
    got = queue_ledger._merged_rows()
    assert got == _reference_merge(qc)
    assert queue_ledger.STARTUP_SCAN["status"]["n_local"] == 4, \
        "the bulk path did not actually engage — this test proved nothing"
    assert [r["step"] for r in got][:3] == ["inference", "labels", "tile"]


def test_resume_credit_is_the_same_through_the_bulk_path(qc, bulk):
    """The merge exists to answer ONE question — which steps may be skipped. The
    revoked j1/tile must stay revoked, and the VERIFY:tile MISSING must still kill
    it, no matter which disk the bytes were read from."""
    bulk.setattr(queue_ledger, "_rclone_fetch", _fake_rclone())
    done, reverify, verdicts = queue_ledger._completed_steps()
    assert q._job_key("j1", "2009", "t", "labels") in done
    assert q._job_key("j1", "2009", "t", "tile") not in done
    assert q._job_key("j2", "2009", "t", "train") in done
    assert verdicts[q._job_key("j2", "2009", "t", "VERIFY")][0] == "OK"
    assert not queue_ledger._MERGE_DEFECTS


def test_a_quarantined_file_and_a_publish_orphan_are_still_never_read(qc, bulk):
    """The name list handed to rclone is names.status_files' answer and nothing
    else. `--include train_queue_status*` would have pulled the CONTAMINATED
    fixture and the 22 `.part.*` orphans that sit in the real phase4/qc."""
    seen = {}

    def fetch(rel, dst, listfile):
        seen["wanted"] = Path(listfile).read_text(encoding="utf-8").split()
        _fake_rclone()(rel, dst, listfile)

    bulk.setattr(queue_ledger, "_rclone_fetch", fetch)
    rows = queue_ledger._merged_rows()
    assert not any("CONTAMINATED" in n or ".part." in n for n in seen["wanted"])
    assert len(seen["wanted"]) == 4
    assert not any(r["ts"].startswith("2099") for r in rows)


# ── every failure mode falls back to the mount, and none of them lose a row ──

def test_windows_takes_the_per_file_path_and_gets_identical_rows(qc):
    """No monkeypatch at all: `_bulk_read_ok` is False here (not posix, not under
    the Drive mount, no rclone), so this is the historical loop, unchanged."""
    assert queue_ledger._bulk_read_ok(qc) is False
    assert queue_ledger._stage_status_files(names.status_files(qc)) == (None, {})
    got = queue_ledger._merged_rows()
    assert got == _reference_merge(qc)
    assert queue_ledger.STARTUP_SCAN["status"]["n_local"] == 0


def test_rclone_raising_falls_back_to_the_mount(qc, bulk):
    """A failed transfer is a cheaper path not taken, never an error — the same
    contract phase4seg/staging.py::_bulk_stage_tiles holds for tiles."""
    bulk.setattr(queue_ledger, "_rclone_fetch", _fake_rclone(boom=True))
    got = queue_ledger._merged_rows()
    assert got == _reference_merge(qc)
    assert queue_ledger.STARTUP_SCAN["status"]["n_local"] == 0
    assert not queue_ledger._MERGE_DEFECTS


def test_rclone_transferring_nothing_falls_back_to_the_mount(qc, bulk):
    """rc is deliberately ignored (this launch's own file is dirty in the write
    cache, so a non-zero rc is the NORMAL case). Completeness is decided per file,
    so a copy that lands nothing must still merge the whole ledger."""
    bulk.setattr(queue_ledger, "_rclone_fetch", _fake_rclone(copy=False))
    assert queue_ledger._merged_rows() == _reference_merge(qc)
    assert queue_ledger.STARTUP_SCAN["status"]["n_local"] == 0


def test_a_short_copy_makes_the_size_gate_FIRE_and_the_rows_survive(qc, bulk):
    """THE KILL CRITERION, SHOWN FIRING (CLAUDE.md 3.4c). A gate that has never
    fired is not known to work, so this hands the stage a half-written copy of one
    file and asserts (a) that file is refused, (b) the other three are still taken,
    and (c) the merge is byte-for-byte the mount's answer."""
    short = names.status_out_name("b", "20260902T000000Z")
    bulk.setattr(queue_ledger, "_rclone_fetch", _fake_rclone(truncate=(short,)))
    got = queue_ledger._merged_rows()
    assert queue_ledger.STARTUP_SCAN["status"]["n_local"] == 3, \
        "the truncated copy was accepted — the size gate did not fire"
    assert got == _reference_merge(qc)
    assert not queue_ledger._MERGE_DEFECTS


def test_a_stale_drive_copy_would_have_granted_a_skip_the_lake_revoked(qc, bulk):
    """THE MUTATION THE SIZE GATE EXISTS FOR, run end to end.

    The mount runs `--vfs-cache-mode writes`, so Drive can hold the version of a
    status file from BEFORE this VM's last flush. If the merge took that copy, the
    step's earlier `OK` would stand where the lake already recorded the `FAIL` that
    revoked it, and the next launch would skip a step that failed — D10's unsafe
    direction, arriving through a transport shortcut D10 never had.

    Three parts: what the lake says, what the gate does with a stale copy, and
    (part 3) proof that accepting it would really have flipped the answer.
    """
    e = names.status_out_name("e", "20260904T000000Z")
    _status_csv(qc / e, [_row("j2", "train", "FAIL", "2026-09-04 00:01:00")])
    key = q._job_key("j2", "2009", "t", "train")
    stale = {e: b"job,year,tag,step,state,exit,minutes,detail,ts,host,session\n"}

    bulk.setattr(queue_ledger, "_rclone_fetch", _fake_rclone(replace=stale))
    done, _r, _v = queue_ledger._completed_steps()
    assert queue_ledger.STARTUP_SCAN["status"]["n_local"] == 4, \
        "the stale copy was accepted — the size gate did not fire"
    assert key not in done, "the revoking FAIL was lost"

    # part 3: had it been accepted, the skip would have come back
    _status_csv(qc / e, [])                    # the lake as the stale bytes describe it
    done, _r, _v = queue_ledger._completed_steps()
    assert key in done, \
        "this mutation cannot flip the answer, so the gate above proves nothing"


def test_a_file_the_mount_touched_recently_is_never_taken_from_drive(qc, bulk):
    """THE SECOND HALF OF THE GATE, and the half size alone cannot cover.

    `run_step` updates its row in place, and RUNNING→OK is byte-for-byte the SAME
    LENGTH whenever `minutes` renders as four characters — i.e. any step between 10
    and 99.9 minutes, which is most of them. Size can therefore not distinguish
    those two versions of a file, and the only reason that is survivable today is an
    unstated invariant about how the writer mutates its rows. Freshness does not rely
    on it: a file the lake shows as warm is simply read from the mount.

    This launch's OWN status file is the everyday instance — the dup-guard flushes a
    GUARD row into it seconds before the merge runs.
    """
    warm = names.status_out_name("live", "20260907T000000Z")
    _status_csv(qc / warm, [_row("j9", "train", "RUNNING", "2026-09-07 00:01:00")],
                age_s=0)
    bulk.setattr(queue_ledger, "_rclone_fetch", _fake_rclone())
    got = queue_ledger._merged_rows()
    assert queue_ledger.STARTUP_SCAN["status"]["n_local"] == 4, \
        "the warm file was taken from Drive"
    assert got == _reference_merge(qc)
    assert any(r["state"] == "RUNNING" for r in got)


def test_running_to_ok_really_is_a_zero_byte_edit(qc):
    """The measurement behind the freshness test, kept as a gate rather than a claim
    in a comment: if the writer's columns change so that this transition always moves
    the byte count, the docstring above is overstating the hazard and should be
    revisited — and if a new column makes MORE transitions collide, it is
    understating it."""
    a = qc.parent / "a.csv"
    b = qc.parent / "b.csv"
    _status_csv(a, [_row("j1", "train", "RUNNING", "2026-09-07 00:01:00")])
    r = _row("j1", "train", "OK", "2026-09-07 00:01:00")
    r.update(exit="0", minutes=12.3)
    _status_csv(b, [r])
    assert a.stat().st_size == b.stat().st_size
    rows_a, _ = queue_ledger._read_status_file(a, attempts=1)
    rows_b, _ = queue_ledger._read_status_file(b, attempts=1)
    assert rows_a[0]["state"] == "RUNNING" and rows_b[0]["state"] == "OK"


def test_a_short_copy_of_a_file_is_refused_but_not_recorded_as_damage(qc, bulk):
    """A half-written transfer loses rows silently — csv.DictReader does not raise
    on a truncated file (queue_ledger.py::_read_status_file). The gate refuses it on
    size, and the file is read from the mount instead."""
    short = names.status_out_name("b", "20260902T000000Z")
    src = qc / short
    half = qc.parent / "half.csv"
    half.write_bytes(src.read_bytes()[:len(src.read_bytes()) // 2])
    full_rows, _ = queue_ledger._read_status_file(src)
    half_rows, _ = queue_ledger._read_status_file(half, attempts=1)
    assert len(half_rows) < len(full_rows)
    assert any(r["step"] == "VERIFY:tile" for r in full_rows)
    assert not any(r.get("step") == "VERIFY:tile" for r in half_rows)


def test_an_unparseable_local_copy_is_re_read_from_the_mount(qc, bulk):
    """A bad COPY is evidence about the copy. Recording it in _MERGE_DEFECTS would
    let the speedup manufacture RESUME DISABLED — the state D10 reserves for a
    damaged lake — and cost a queue every skip it had earned."""
    victim = names.status_out_name("c", "20260903T000000Z")

    def fetch(rel, dst, listfile):
        _fake_rclone()(rel, dst, listfile)
        (Path(dst) / victim).write_text("job,year,step\n1,2,3\n", encoding="utf-8")

    bulk.setattr(queue_ledger, "_rclone_fetch", fetch)
    got = queue_ledger._merged_rows()
    assert not queue_ledger._MERGE_DEFECTS, "a bad local copy disabled resume"
    assert got == _reference_merge(qc)


def test_a_genuinely_unreadable_lake_file_is_still_a_merge_defect(qc, bulk):
    """The counterpart: the D10 protection must survive the optimisation. A header
    the mount itself cannot interpret is still counted, still printed, and still
    refuses resume credit."""
    (qc / names.status_out_name("d", "20260904T000000Z")).write_text(
        "job,year,step\n1,2,3\n", encoding="utf-8")
    bulk.setattr(queue_ledger, "_rclone_fetch", _fake_rclone())
    queue_ledger._merged_rows()
    assert [n for n, _w in queue_ledger._MERGE_DEFECTS] == [
        names.status_out_name("d", "20260904T000000Z")]
    done, reverify, _v = queue_ledger._completed_steps()
    assert done == set() and reverify == set()


def test_the_stage_leaves_no_temp_directory_behind(qc, bulk):
    """mkdtemp is LOCAL disk (never the mount, CLAUDE.md 3.9) and it is removed on
    every exit path — a queue relaunched hourly would otherwise leak one copy of
    the whole ledger per launch into the VM's disk."""
    made = []
    real = queue_ledger.tempfile.mkdtemp

    def spy(*a, **kw):
        p = real(*a, **kw)
        made.append(p)
        return p

    bulk.setattr(queue_ledger.tempfile, "mkdtemp", spy)
    bulk.setattr(queue_ledger, "_rclone_fetch", _fake_rclone())
    queue_ledger._merged_rows()
    assert made and not any(os.path.exists(p) for p in made)


# ── the activation discipline, matched to phase4seg/staging.py::_bulk_stage_ok ──

def test_bulk_is_refused_off_posix_and_off_the_mount(qc, monkeypatch):
    """Two of the four conditions, and the two that can be checked here. On this
    box `os.name != "posix"` already answers False; the mount-prefix test is what
    keeps a posix machine with rclone from bulk-copying a directory that is not on
    the lake at all."""
    assert queue_ledger._bulk_read_ok(qc) is False
    monkeypatch.setattr(q, "_DRIVE_MOUNT_PREFIX", str(qc.parent))
    monkeypatch.setattr(queue_ledger.os, "name", "posix")
    monkeypatch.setattr(queue_ledger, "_rclone_probe", None)
    monkeypatch.setattr(queue_ledger.shutil, "which", lambda n: None)
    assert queue_ledger._bulk_read_ok(qc) is False, "no rclone on PATH must refuse"
    monkeypatch.setattr(q, "_DRIVE_MOUNT_PREFIX", "/nowhere/")
    monkeypatch.setattr(queue_ledger, "_rclone_probe", None)
    assert queue_ledger._bulk_read_ok(qc) is False, "off-mount path must refuse"


def test_bulk_is_refused_when_the_writer_remote_is_not_configured(qc, monkeypatch):
    """`rclone listremotes` must actually name the remote the mount uses. A VM with
    rclone but no `treedata-user:` would otherwise run a copy that transfers
    nothing every launch and silently pay for it."""
    class R:
        returncode, stdout, stderr = 0, "treedata-sa:\n", ""

    monkeypatch.setattr(q, "_DRIVE_MOUNT_PREFIX", str(qc.parent))
    monkeypatch.setattr(queue_ledger.os, "name", "posix")
    monkeypatch.setattr(queue_ledger.shutil, "which", lambda n: "/usr/bin/rclone")
    monkeypatch.setattr(queue_ledger.subprocess, "run", lambda *a, **k: R())
    monkeypatch.setattr(queue_ledger, "_rclone_probe", None)
    assert queue_ledger._bulk_read_ok(qc) is False
    R.stdout = "treedata-sa:\ntreedata-user:\n"
    monkeypatch.setattr(queue_ledger, "_rclone_probe", None)
    assert queue_ledger._bulk_read_ok(qc) is True


# ── the beacon scan: one listing, and only fresh beacons are opened ──────────

def _beacon(base, name, age_s, **fields):
    logs = base / "phase4" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    p = logs / f"heartbeat_{name}.json"
    p.write_text(json.dumps(fields), encoding="utf-8")
    t = time.time() - age_s
    os.utime(p, (t, t))
    return p


@pytest.fixture
def beacons(tmp_path, monkeypatch):
    monkeypatch.setattr(q, "BASE", tmp_path)
    return tmp_path


def _count_heartbeat_opens(monkeypatch):
    """Count REAL opens of heartbeat files, independent of the code's own counter —
    a counter that reports itself is not evidence about what it did."""
    seen = []
    real = Path.read_text

    def spy(self, *a, **kw):
        if self.name.startswith("heartbeat_"):
            seen.append(self.name)
        return real(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", spy)
    return seen


def test_only_beacons_inside_the_liveness_window_are_opened(beacons, monkeypatch):
    """THE MUTATION GATE. `max_age_s` is the window the guard already uses to call a
    beacon a dead VM (300 s, phase4_train_queue.py::_tag_owners), and it now gates
    the OPEN as well as the verdict. Delete that `continue` and this fails on both
    counters: the independent open log and the scan's own n_open."""
    _beacon(beacons, "live", 10, session="live", host="other-vm",
            run_tags=["smooth5"], run_tags_pid=999)
    for i in range(8):
        _beacon(beacons, f"dead{i}", 4000, session=f"dead{i}", host="other-vm",
                run_tags=["smooth5"], run_tags_pid=900 + i)
    opened = _count_heartbeat_opens(monkeypatch)
    clashes, scanned, blind = q._tag_owners({"smooth5"})
    assert opened == ["heartbeat_live.json"], \
        f"stale beacons were opened: {sorted(opened)}"
    assert queue_ledger.STARTUP_SCAN["beacons"] == {
        "n": 9, "n_open": 1, "seconds": pytest.approx(
            queue_ledger.STARTUP_SCAN["beacons"]["seconds"])}
    assert scanned == 1 and blind is None
    assert clashes == [("live", "smooth5", "declared")]


def test_a_beacon_just_inside_the_window_is_still_opened(beacons, monkeypatch):
    """The gate must not be tightened by accident either: 300 s is the contract the
    cross-VM guard's protection rests on, and a beacon publishes every 60 s."""
    _beacon(beacons, "edge", 290, session="edge", host="other-vm",
            run_tags=["smooth5"], run_tags_pid=999)
    opened = _count_heartbeat_opens(monkeypatch)
    clashes, scanned, _b = q._tag_owners({"smooth5"})
    assert opened == ["heartbeat_edge.json"] and scanned == 1 and clashes


def test_all_stale_still_reports_the_full_file_count_as_blind(beacons):
    """`blind` names how many heartbeat FILES exist, not how many parsed — it is the
    sentence that tells a reader the run was unprotected and why. The listing rewrite
    must not quietly turn 72 into 0."""
    for i in range(5):
        _beacon(beacons, f"dead{i}", 4000, session=f"dead{i}", host="other-vm")
    clashes, scanned, blind = q._tag_owners({"smooth5"})
    assert clashes == [] and scanned == 0
    assert "5 heartbeat file(s), all stale or unreadable" in blind
    assert queue_ledger.STARTUP_SCAN["beacons"]["n"] == 5
    assert queue_ledger.STARTUP_SCAN["beacons"]["n_open"] == 0


def test_a_fresh_but_unreadable_beacon_is_opened_and_not_counted_as_scanned(beacons):
    """Opened (we could not know it was junk without looking) but not `scanned`:
    a beacon that will not parse proves nothing about who holds a tag."""
    p = _beacon(beacons, "torn", 5, session="torn")
    p.write_text("{not json", encoding="utf-8")
    t = time.time() - 5
    os.utime(p, (t, t))
    clashes, scanned, blind = q._tag_owners({"smooth5"})
    assert scanned == 0 and clashes == []
    assert queue_ledger.STARTUP_SCAN["beacons"]["n_open"] == 1
    assert blind and "1 heartbeat file(s)" in blind


def test_an_unlistable_logs_dir_still_fails_open_and_records_the_scan(beacons):
    """No phase4/logs at all. The guard fails OPEN by contract, and the startup line
    must still be able to say a scan happened rather than print a stale number from
    the previous call."""
    clashes, scanned, blind = q._tag_owners({"smooth5"})
    assert clashes == [] and scanned == 0 and "could not list" in blind
    assert queue_ledger.STARTUP_SCAN["beacons"] == {
        "n": 0, "n_open": 0,
        "seconds": queue_ledger.STARTUP_SCAN["beacons"]["seconds"]}


# ── the one line the nohup log will carry from now on ────────────────────────

_RE = re.compile(r"startup: (\d+) status files in ([\d.]+) s.*?, "
                 r"(\d+) beacons in ([\d.]+) s")


def test_the_startup_line_is_regexable_and_carries_both_scans(monkeypatch):
    monkeypatch.setattr(queue_ledger, "STARTUP_SCAN", {})
    queue_ledger.record_scan("status", n=76, n_local=74, seconds=18.25)
    queue_ledger.record_scan("beacons", n=72, n_open=1, seconds=0.31)
    line = queue_ledger.startup_line()
    m = _RE.search(line)
    assert m, line
    assert m.groups() == ("76", "18.2", "72", "0.3")
    assert "74 bulk-copied, 2 read per-file" in line
    assert "1 opened, 71 skipped stale" in line


def test_the_startup_line_survives_no_resume_and_an_empty_launch(monkeypatch):
    """--no-resume skips the status merge entirely, so half the line has nothing to
    report. It must print the half it has, not a fabricated zero."""
    monkeypatch.setattr(queue_ledger, "STARTUP_SCAN", {})
    assert queue_ledger.startup_line() is None
    queue_ledger.record_scan("beacons", n=72, n_open=0, seconds=0.4)
    line = queue_ledger.startup_line()
    assert "status files" not in line and "72 beacons in 0.4 s" in line


def test_main_prints_the_startup_line_before_the_first_job(qc, tmp_path, monkeypatch,
                                                           capsys):
    """It has to reach the NOHUP LOG, which is the only place a launch's own timings
    survive the runtime. Printed after the resume ledger is built (both scans are
    then done) and before any spend. NOT under --dry-run: that returns before the
    guard and the merge, so there is nothing measured to report."""
    monkeypatch.setattr(q.sys, "argv", ["phase4_train_queue.py"])
    monkeypatch.setattr(queue_ledger, "STARTUP_SCAN", {})
    monkeypatch.setattr(q, "BASE", tmp_path)             # no phase4/logs: guard is blind
    monkeypatch.setattr(q, "_status_write", lambda rows: None)
    monkeypatch.setattr(q, "STATUS_OUT", tmp_path / "out.csv")
    monkeypatch.setattr(q, "JOBS", [dict(id="j1", year="2009", tag="t",
                                         extra=["--force-citywide"], why="", expect="")])
    monkeypatch.setattr(q, "ENGINE", tmp_path / "engine.py")
    (tmp_path / "engine.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(q, "run_step", lambda *a, **k: False)   # no engine is spawned
    assert q.main() == 1
    out = capsys.readouterr().out
    assert re.search(r"startup: \d+ status files in [\d.]+ s.*?, "
                     r"\d+ beacons in [\d.]+ s", out), out[-400:]
    assert out.index("startup: ") < out.index("JOB j1"), \
        "the line landed after the first job had already started"
