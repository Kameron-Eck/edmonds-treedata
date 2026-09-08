"""The per-runtime session timeline, on fixtures whose answers are hand-computed.

`harvest_runtime_sessions.py` exists to split ONE number that §6 of
`Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md` could not split: 5.0 h of hardware
samples labelled `(between steps)`, half of which is bootstrap (fixable by editing the
pipeline) and half of which is a runtime left alive after its queue finished (fixable
only by stopping it). Everything gated here is a way that split can silently come out
wrong:

  a  a session present in ALL FOUR sources — hw CSV, hw_meta, heartbeat, status rows.
     `startup_min` and `idle_tail_min` are arithmetic on stamps chosen to make the
     minutes whole, so a sign flip or a seconds/minutes slip cannot pass.
  b  a session seen ONLY in an hw CSV. It must still get a row: a runtime that burned
     GPU hours and wrote no ledger is exactly the machine this table is looking for,
     and dropping it would understate the very waste it measures.
  c  a session seen ONLY in status rows (no hw, no heartbeat). Same rule, other side —
     and `idle_tail_min` must be BLANK, because nothing measured when the machine died.
  d  BLANK IS NOT ZERO. `n_queue_rows`, `startup_min`, `idle_tail_min`, `gpu_present`
     and the hw_meta columns are each blank when unmeasured. A 0 in any of them
     reads as "measured, and it was nothing" — the opposite claim.
  e  determinism: two runs over one fixture tree are byte-identical, and the header IS
     the contract in docs/SCHEMAS.md.
  f  the heartbeat SESSION FIELD wins over the filename. A `__conflict-` copy and a
     stranded `.json.prev.{tok}.json` both carry real samples of their session; the
     in-flight `.json.tmp.{pid}` is not a publication and must be skipped.
  g  `queue` comes from a nohup filename only via a heartbeat with a LIVE `queue_proc`
     (vm_heartbeat.py::_newest drops its stem filter without one, and then reports some
     other VM's log), and two disagreeing stems leave the cell blank rather than
     picking one.
  h  the `_v2` suffix on an hw filename is the SCHEMA, not part of the session name;
     both files fold into one row.
  k  a live `queue_proc` is NOT sufficient for the nohup link: `_newest` matches by
     SUBSTRING, so a stem that is a prefix of another queue's stem returns the wrong
     VM's log. The record's own declared `queue_file` wins, and a pre-D11 record with
     no declaration and a prefix-colliding stem publishes nothing.
  l  only a LAUNCH status file's stem may name a queue. A `_seed` file and the
     ledger-recovery candidate are admissible ledgers whose NAMES are not evidence.
  m  a session missing from the heartbeat LISTING is re-probed by name before its
     beacon columns are published blank, and says `heartbeat_not_listed` if it really
     is absent — the mirror drops single entries from a non-empty listing.
  n  a ledger that stops NAMING the session while rows for its own tags keep arriving
     is truncated, not finished: its gap is work, and it leaves the headline sum.
  o  the CPU identity (`cpu_model`, `cpu_mhz`, `bogomips`) is read from hw_meta when the
     keys are there and BLANK when they are not — which is every meta on the lake today,
     because the logger only began writing them 2026-09-08. The columns exist because
     `vcpus` + `ram_gb` could not tell two CPU runtimes apart that ran one 632-tile step
     21.0 vs 39.1 sampled minutes apart (`spdc1`, `spdvc1`).
  p  a DRIVE DUPLICATE — `hw_healA (1).csv` beside `hw_healA.csv`, two objects with one
     name in one folder (rclone.org/drive, "Duplicated files"), as the lake held
     2026-09-08. Read literally it is a whole extra runtime whose `sources` says `hw`
     and nothing else: the shape of a machine with broken telemetry, so it does not even
     look wrong. Both files fold into one row and the row NAMES the duplicate.
  q  the same when only the ` (N)` survives a cleanup — the row keeps the real session
     name. A table that renames a paid runtime according to how its file was tidied is
     worse than one that misses it.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_runtime_sessions.py -q
"""
import csv
import json
from pathlib import Path

import pytest

from instruments import harvest_runtime_sessions as hrs
from instruments.harvest_runtime_sessions import (
    COLS,
    build_rows,
    main,
    parse_ts,
    session_of_hw,
)

HW_HEADER = ("ts_utc,gpu_util_pct,gpu_mem_util_pct,gpu_mem_used_mb,gpu_power_w,"
             "cpu_pct,disk_read_mb_s,disk_write_mb_s,net_rx_mb_s,net_tx_mb_s,"
             "disk_used_gb,disk_free_gb")

STATUS_HEADER = "job,year,tag,step,state,exit,minutes,detail,ts,host,session"


def _hw(path, stamps, gpu="7"):
    """An hw CSV. `gpu=""` writes the blank GPU columns of a CPU runtime."""
    lines = [HW_HEADER]
    for t in stamps:
        lines.append(f"{t},{gpu},0,0,50.0,3.1,0.0,0.0,0.0,0.0,50.0,200.0")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")


def _status(path, rows):
    """A per-launch status file. `rows` are (step, ts, session) triples.

    The fixture NAME is checked against the one discovery rule
    (`phase4seg.names.is_status_file`) rather than being trusted: a fixture the real
    reader would skip proves nothing about the reader, and every assertion below about
    `n_queue_rows` would then pass on an empty join.
    """
    from phase4seg.names import is_status_file
    assert is_status_file(path.name), f"fixture {path.name} is not an admissible ledger"
    lines = [STATUS_HEADER]
    for row in rows:
        step, ts, sess = row[:3]
        state = row[3] if len(row) > 3 else "OK"
        lines.append(f"j1,2019,tag1,{step},{state},0,1.0,,{ts},host1,{sess}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")


def _beat(path, session, ts, prev=None, queue_proc=None, nohup=None, queue_file=None):
    d = {"ts_utc": ts, "session": session, "prev_ts_utc": prev,
         "queue_proc": queue_proc, "queue_file": queue_file,
         "newest_nohup": ({"name": nohup, "size": 1} if nohup else None)}
    path.write_text(json.dumps(d), encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch):
    """Zero the mirror-blink retry pause for the whole file.

    `_listing` retries an EMPTY listing three times (`lake.py::read_retry`) because the
    Drive mirror returns one for a populated directory. Several fixtures below leave a
    directory deliberately empty, and at the real 1.0 s pause each of those would add
    seconds of sleep that measure nothing. The retry itself still runs — only the wait
    is removed — so the code path under test is the shipped one.
    """
    monkeypatch.setattr(hrs, "_RETRY_PAUSE", 0.0)


@pytest.fixture()
def lake(tmp_path):
    """A fixture lake: (logs_dir, qc_dir). Tests never write to the real one."""
    logs = tmp_path / "logs"
    qc = tmp_path / "qc"
    logs.mkdir()
    qc.mkdir()
    return logs, qc


def _by_session(rows):
    return {r["session"]: r for r in rows}


def test_a_session_in_all_four_sources_and_the_arithmetic(lake):
    """(a) hw + hw_meta + heartbeat + status rows, with whole-minute answers.

    hw runs 10:00:00 → 12:30:00 (2.5 h). The queue's first row is 10:20:00, so
    start-up is 20.0 min. Its last row is 12:00:00 and the machine is last seen at
    12:30:00 (hw) — the heartbeat's 12:15 is earlier, so hw wins — giving a 30.0 min
    idle tail.
    """
    logs, qc = lake
    _hw(logs / "hw_alpha.csv",
        ["2026-09-05T10:00:00Z", "2026-09-05T11:00:00Z", "2026-09-05T12:30:00Z"])
    (logs / "hw_meta_alpha.json").write_text(json.dumps({
        "session": "alpha", "gpu_name": "NVIDIA A100-SXM4-40GB", "vcpus": 12,
        "ram_gb": 83.5, "hostname": "h1"}), encoding="utf-8")
    _beat(logs / "heartbeat_alpha.json", "alpha", "2026-09-05T12:15:00Z",
          prev="2026-09-05T12:14:00Z", queue_proc="4242",
          nohup="train_queue_nohup_queue_tier1_science_sample_20260905T100000Z.log")
    _status(qc / "train_queue_status_queue_tier1_science_sample_20260905T100000Z.csv",
            [("tile", "2026-09-05 10:20:00", "alpha"),
             ("train", "2026-09-05 11:00:00", "alpha"),
             ("VERIFY:train", "2026-09-05 12:00:00", "alpha")])

    r = _by_session(build_rows(logs, qc))["alpha"]
    assert r["hw_first_utc"] == "2026-09-05T10:00:00Z"
    assert r["hw_last_utc"] == "2026-09-05T12:30:00Z"
    assert r["hw_hours"] == "2.5000"
    assert r["gpu_present"] == "1"
    assert r["gpu_name"] == "NVIDIA A100-SXM4-40GB"
    assert r["vcpus"] == "12" and r["ram_gb"] == "83.5"
    assert r["queue"] == "queue_tier1_science_sample"
    assert r["n_queue_rows"] == "3"
    assert r["queue_first_row_ts"] == "2026-09-05T10:20:00Z"
    assert r["queue_last_row_ts"] == "2026-09-05T12:00:00Z"
    assert r["startup_min"] == "20.0"
    assert r["idle_tail_min"] == "30.0"
    assert r["heartbeat_first_utc"] == "2026-09-05T12:14:00Z"    # prev_ts_utc counts
    assert r["heartbeat_last_utc"] == "2026-09-05T12:15:00Z"
    assert set(r["sources"].split(";")) == {"hw", "hw_meta", "heartbeat", "queue_rows"}


def test_b_session_only_in_hw_still_gets_a_row(lake):
    """(b) A runtime that logged hardware and nothing else is the machine this table
    is hunting. Its timing columns are blank, not zero."""
    logs, qc = lake
    _hw(logs / "hw_lonely.csv",
        ["2026-09-05T01:00:00Z", "2026-09-05T02:00:00Z"], gpu="")
    rows = build_rows(logs, qc)
    r = _by_session(rows)["lonely"]
    assert r["hw_hours"] == "1.0000"
    assert r["gpu_present"] == "0"                 # blank GPU columns = a CPU runtime
    # …and the beacon really is absent, not merely missing from one listing: the
    # re-probe found no `heartbeat_lonely*` either, which is what the flag reports.
    assert r["sources"] == "hw;heartbeat_not_listed"
    assert r["n_queue_rows"] == ""
    assert r["startup_min"] == ""
    assert r["idle_tail_min"] == ""


def test_c_session_only_in_queue_rows_has_no_idle_tail(lake):
    """(c) Ledger rows with no machine-side beacon: the queue's own span is known, the
    runtime's is not, so start-up and idle tail are UNMEASURED."""
    logs, qc = lake
    _status(qc / "train_queue_status_queue_x_20260905T000000Z.csv",
            [("tile", "2026-09-05 03:00:00", "ghost"),
             ("train", "2026-09-05 04:00:00", "ghost")])
    r = _by_session(build_rows(logs, qc))["ghost"]
    assert r["sources"] == "queue_rows;heartbeat_not_listed"
    assert r["n_queue_rows"] == "2"
    assert r["queue_first_row_ts"] == "2026-09-05T03:00:00Z"
    assert r["queue_last_row_ts"] == "2026-09-05T04:00:00Z"
    assert r["hw_first_utc"] == "" and r["hw_hours"] == ""
    assert r["gpu_present"] == ""                  # not "0": nothing was sampled
    assert r["startup_min"] == "" and r["idle_tail_min"] == ""
    assert r["queue"] == "queue_x"                 # the status FILE's stem


def test_d_blank_is_never_zero_anywhere_on_the_table(lake):
    """(d) Sweep every unmeasured cell across the three fixtures above. The string "0"
    is a measurement; the empty string is the absence of one, and only `gpu_present`
    may legitimately hold "0" (a CPU runtime's blank GPU columns ARE the reading)."""
    logs, qc = lake
    _hw(logs / "hw_lonely.csv", ["2026-09-05T01:00:00Z"], gpu="")
    _status(qc / "train_queue_status_queue_x_20260905T000000Z.csv",
            [("tile", "2026-09-05 03:00:00", "ghost")])
    rows = build_rows(logs, qc)
    numeric = ("vcpus", "ram_gb", "cpu_mhz", "bogomips", "hw_hours", "n_queue_rows",
               "startup_min", "idle_tail_min")
    for r in rows:
        for c in numeric:
            assert r[c] != "0", f"{r['session']}.{c} published 0 for an unmeasured cell"
            assert r[c] != "0.0", f"{r['session']}.{c} published 0.0 unmeasured"


def test_e_deterministic_and_the_header_is_the_contract(lake, tmp_path):
    """(e) Two runs, byte-identical, and the column list is the one SCHEMAS.md names."""
    logs, qc = lake
    _hw(logs / "hw_b.csv", ["2026-09-05T05:00:00Z", "2026-09-05T06:00:00Z"])
    _hw(logs / "hw_a.csv", ["2026-09-05T05:00:00Z"])
    _beat(logs / "heartbeat_c.json", "c", "2026-09-05T07:00:00Z")
    _status(qc / "train_queue_status_queue_z_20260905T000000Z.csv",
            [("tile", "2026-09-05 05:30:00", "b")])

    out1, out2 = tmp_path / "o1.csv", tmp_path / "o2.csv"
    for out in (out1, out2):
        assert main(["--logs-dir", str(logs), "--qc-dir", str(qc),
                     "--out", str(out)]) == 0
    assert out1.read_bytes() == out2.read_bytes()

    text = out1.read_text(encoding="utf-8")
    assert list(csv.reader([text.splitlines()[0]]))[0] == COLS
    got = [r["session"] for r in csv.DictReader(text.splitlines())]
    assert got == sorted(got)


def test_f_heartbeat_session_comes_from_the_field_not_the_filename(lake):
    """(f) A conflict copy and a stranded `.prev.` publication are real samples of the
    session named INSIDE them; the in-flight `.tmp.{pid}` is not a publication."""
    logs, qc = lake
    _beat(logs / "heartbeat_dup.json", "dup", "2026-09-05T09:00:00Z")
    _beat(logs / "heartbeat_dup__conflict-ab12cd.json", "dup", "2026-09-05T09:30:00Z")
    _beat(logs / "heartbeat_dup.json.prev.ff00aa.json", "dup", "2026-09-05T08:00:00Z")
    _beat(logs / "heartbeat_dup.json.tmp.1234", "dup", "2026-09-05T23:00:00Z")

    rows = _by_session(build_rows(logs, qc))
    assert set(rows) == {"dup"}, "the filename must not create extra sessions"
    assert rows["dup"]["heartbeat_first_utc"] == "2026-09-05T08:00:00Z"
    assert rows["dup"]["heartbeat_last_utc"] == "2026-09-05T09:30:00Z"


def test_g_queue_needs_a_live_queue_proc_and_never_guesses(lake):
    """(g) Three cases in one tree.

    `noproc` — heartbeat names a nohup log but `queue_proc` is null, so the beacon's
      stem filter was off and the log may be another VM's: no queue.
    `oneq`   — live queue_proc, one stem: resolved.
    `twoq`   — the heartbeat and the status file name DIFFERENT stems: blank, and
      `sources` records the disagreement rather than picking a side.
    """
    logs, qc = lake
    _beat(logs / "heartbeat_noproc.json", "noproc", "2026-09-05T09:00:00Z",
          queue_proc=None,
          nohup="train_queue_nohup_queue_someone_elses_20260905T010000Z.log")
    _beat(logs / "heartbeat_oneq.json", "oneq", "2026-09-05T09:00:00Z",
          queue_proc="99",
          nohup="train_queue_nohup_queue_tier1_science_sample_20260905T010000Z.log")
    _beat(logs / "heartbeat_twoq.json", "twoq", "2026-09-05T09:00:00Z",
          queue_proc="99",
          nohup="train_queue_nohup_queue_alpha_20260905T010000Z.log")
    _status(qc / "train_queue_status_queue_beta_20260905T000000Z.csv",
            [("tile", "2026-09-05 03:00:00", "twoq")])

    rows = _by_session(build_rows(logs, qc))
    assert rows["noproc"]["queue"] == ""
    assert rows["oneq"]["queue"] == "queue_tier1_science_sample"
    assert rows["twoq"]["queue"] == ""
    assert "queue_ambiguous(queue_alpha,queue_beta)" in rows["twoq"]["sources"]


def test_h_v2_suffix_is_the_schema_not_the_session(lake):
    """(h) `hw_s.csv` and `hw_s_v2.csv` are one runtime, and its span covers both."""
    logs, qc = lake
    _hw(logs / "hw_s.csv", ["2026-09-05T01:00:00Z", "2026-09-05T02:00:00Z"])
    _hw(logs / "hw_s_v2.csv", ["2026-09-05T03:00:00Z", "2026-09-05T04:00:00Z"])
    rows = _by_session(build_rows(logs, qc))
    assert set(rows) == {"s"}
    assert rows["s"]["hw_first_utc"] == "2026-09-05T01:00:00Z"
    assert rows["s"]["hw_last_utc"] == "2026-09-05T04:00:00Z"
    assert rows["s"]["hw_hours"] == "3.0000"


def test_i_a_dead_beacon_gives_a_negative_tail_and_is_flagged_not_clipped(lake):
    """(i) The live case that made this rule necessary: `pilotcoarse`, 2026-08-31 —
    the heartbeat's last surviving stamp is 42.8 min BEFORE the queue's last ledger
    row, and that stamp sits INSIDE the queue's own span, so the beacon died rather
    than the clocks disagreeing.

    Clipping to 0 would report 43 minutes of measured "no idle time" for a runtime
    nobody was watching; dropping the row would hide the telemetry failure. Publish
    the negative number and flag it, so a reader summing the column can exclude it.
    """
    logs, qc = lake
    _beat(logs / "heartbeat_dead.json", "dead", "2026-09-05T01:47:54Z")
    _status(qc / "train_queue_status_queue_p_20260905T000000Z.csv",
            [("tile", "2026-09-05 01:01:33", "dead"),
             ("train", "2026-09-05 02:30:44", "dead")])
    r = _by_session(build_rows(logs, qc))["dead"]
    assert r["idle_tail_min"] == "-42.8"
    assert "beacon_ended_before_queue" in r["sources"]


def test_j_a_running_last_row_is_flagged_so_it_is_not_read_as_idle(lake):
    """(j) `run_step` appends its row in state RUNNING and stamps `ts` there, so a
    session whose newest row is RUNNING has a growing `idle_tail_min` that measures the
    CURRENT step, not idleness. Measured on the live campaign 2026-09-07: `spdg` read
    4.4 min and then 10.4 min off the same unchanged row six minutes later.

    The value is still published — it is the honest gap — but the flag is what stops a
    reader summing it into a waste total.
    """
    logs, qc = lake
    _hw(logs / "hw_live.csv",
        ["2026-09-05T10:00:00Z", "2026-09-05T10:30:00Z"])
    _status(qc / "train_queue_status_queue_live_20260905T000000Z.csv",
            [("tile", "2026-09-05 10:05:00", "live", "OK"),
             ("train", "2026-09-05 10:10:00", "live", "RUNNING")])
    r = _by_session(build_rows(logs, qc))["live"]
    assert r["idle_tail_min"] == "20.0"
    assert "queue_last_row_RUNNING" in r["sources"]

    # …and a finished queue must NOT carry the flag.
    _status(qc / "train_queue_status_queue_done_20260905T000000Z.csv",
            [("train", "2026-09-05 10:10:00", "done", "OK")])
    r2 = _by_session(build_rows(logs, qc))["done"]
    assert "queue_last_row_RUNNING" not in r2["sources"]


def _nohup(logs, stem, ts="20260905T010000Z"):
    """A nohup log on the fixture lake. Its CONTENT is irrelevant — `_prefix_owner`
    reads the directory to learn which stems exist, exactly as the beacon's own
    `_newest` glob did when it produced the mis-hit."""
    (logs / f"train_queue_nohup_{stem}_{ts}.log").write_text("x", encoding="utf-8")


def test_k_declared_queue_wins_and_a_prefix_collision_is_dropped(lake):
    """(k) The live mis-attribution, and the guard that catches it without a
    declaration. Measured 2026-09-07 on `hardyear`: `queue_file` said
    `queue_hard_year_pilot.yaml`, `newest_nohup` said
    `train_queue_nohup_queue_hard_year_pilot_only2006s_….log`, and this table published
    the LONGER stem — the queue a paid runtime never ran. The cause is in
    `vm_heartbeat.py::_newest`: its filter asks whether `"_" + stem + "_"` is a
    SUBSTRING of the filename, which the longer queue's log satisfies.

    `declared` — the beacon declares its queue: that wins, collision or not.
    `bare`     — a pre-D11 record with no declaration, whose parsed stem is a strict
                 prefix-extension of another stem present on the lake: BLANK, flagged.
                 This is the kill criterion, and it fires on the known-bad input.
    `bareok`   — same shape, no colliding stem on the lake: still resolved, so the
                 guard cannot be passing by blanking everything.
    `abspath`  — `queue_file` as an absolute VM path, the form `pilotcoarse` carries.
    """
    logs, qc = lake
    _nohup(logs, "queue_x")                   # the SHORTER stem, the one _newest sought
    _nohup(logs, "queue_x_y")                 # …and the longer log it actually returned
    _nohup(logs, "queue_solo_b")

    _beat(logs / "heartbeat_declared.json", "declared", "2026-09-05T09:00:00Z",
          queue_proc="9", queue_file="queue_x.yaml",
          nohup="train_queue_nohup_queue_x_y_20260905T010000Z.log")
    _beat(logs / "heartbeat_bare.json", "bare", "2026-09-05T09:00:00Z",
          queue_proc="9",
          nohup="train_queue_nohup_queue_x_y_20260905T010000Z.log")
    _beat(logs / "heartbeat_bareok.json", "bareok", "2026-09-05T09:00:00Z",
          queue_proc="9",
          nohup="train_queue_nohup_queue_solo_b_20260905T010000Z.log")
    _beat(logs / "heartbeat_abspath.json", "abspath", "2026-09-05T09:00:00Z",
          queue_proc="9",
          queue_file="/content/repo/Scripts/pipeline/pilot_2019_coarse.yaml",
          nohup="train_queue_nohup_queue_x_y_20260905T010000Z.log")

    rows = _by_session(build_rows(logs, qc))
    assert rows["declared"]["queue"] == "queue_x"
    assert "queue_prefix_collision" not in rows["declared"]["sources"]
    assert rows["bare"]["queue"] == ""
    assert "queue_prefix_collision(queue_x,queue_x_y)" in rows["bare"]["sources"]
    assert rows["bareok"]["queue"] == "queue_solo_b"
    assert rows["abspath"]["queue"] == "pilot_2019_coarse"


def test_l_only_a_launch_status_file_may_name_a_queue(lake):
    """(l) `phase4seg.names.parse_status_name` returns `ts=None` for the two admissible
    files that are not launches, and this table honours that: their ROWS count, their
    NAMES do not.

    `seedy`  — a `_seed` file (25 exist on the lake) beside its own launch. Without the
      gate the two stems disagree and `queue_ambiguous` would blank a correct answer.
    `recov`  — the ledger-recovery CANDIDATE. Reproduced 2026-09-07 by running the
      instrument over the lake's status files plus that file: four sessions published
      `queue = recovered_20260901_20260907`, a queue that never existed.
    """
    logs, qc = lake
    _status(qc / "train_queue_status_queue_s_20260905T000000Z.csv",
            [("tile", "2026-09-05 03:00:00", "seedy")])
    _status(qc / "train_queue_status_queue_s_seed.csv",
            [("train", "2026-09-05 03:30:00", "seedy")])
    _status(qc / "train_queue_status_recovered_20260901_20260907.csv",
            [("tile", "2026-09-05 03:00:00", "recov")])

    rows = _by_session(build_rows(logs, qc))
    assert rows["seedy"]["queue"] == "queue_s"
    assert "queue_ambiguous" not in rows["seedy"]["sources"]
    assert rows["seedy"]["n_queue_rows"] == "2"        # the seed's ROWS still count
    assert rows["recov"]["queue"] == ""
    assert rows["recov"]["n_queue_rows"] == "1"


def test_m_a_session_missing_from_the_listing_is_reprobed_by_name(lake):
    """(m) Reproduced against the live lake 2026-09-07: one `glob("heartbeat_*")`
    returned 143 entries with `spdg` absent while `heartbeat_spdg.json` was readable by
    name seconds either side, and the harvest in between published that live runtime's
    beacon columns blank with nothing recording the loss. `lake.read_retry` does not
    cover it — it retries only while the answer is FALSY, and 143 entries is not falsy.

    `blink` — the file exists and only the listing hid it: the row must come out
      identical to an unblinked one, with `heartbeat` in `sources`.
    `gone`  — really absent: `heartbeat_not_listed`, never a silent blank.
    Also: the aside `write_atomic` leaves during its rename window has no trailing
    `.json`, so the LISTING pass rejects it — the targeted probe must not.
    """
    logs, qc = lake
    _hw(logs / "hw_blink.csv", ["2026-09-05T10:00:00Z", "2026-09-05T11:00:00Z"])
    _hw(logs / "hw_gone.csv", ["2026-09-05T10:00:00Z"])
    _beat(logs / "heartbeat_blink.json", "blink", "2026-09-05T10:30:00Z")

    real_glob = Path.glob

    def blinking(self, pat):
        out = list(real_glob(self, pat))
        if pat == "heartbeat_*":                     # non-empty, one entry dropped
            out = [p for p in out if "blink" not in p.name]
        return iter(out)

    # Its OWN monkeypatch context, not the fixture-injected one: `monkeypatch.undo()`
    # on the shared instance would also undo the autouse `_RETRY_PAUSE` patch, and the
    # empty-listing retries below would then sleep for real (measured: 18 s in this one
    # test). Scoping the blink to a context restores only the blink.
    with pytest.MonkeyPatch.context() as m:
        m.setattr(Path, "glob", blinking)
        r = _by_session(build_rows(logs, qc))["blink"]
    assert r["heartbeat_last_utc"] == "2026-09-05T10:30:00Z"
    assert "heartbeat" in r["sources"].split(";")
    assert "heartbeat_not_listed" not in r["sources"]

    r2 = _by_session(build_rows(logs, qc))["gone"]
    assert r2["heartbeat_first_utc"] == "" and r2["heartbeat_last_utc"] == ""
    assert "heartbeat_not_listed" in r2["sources"]

    # The bare `.json.prev.{tok}` aside: invisible to the listing rule by the writer's
    # own contract, and the only copy of the beacon inside the rename window.
    (logs / "heartbeat_blink.json").unlink()
    (logs / "heartbeat_blink.json.prev.ab12cd").write_text(
        json.dumps({"ts_utc": "2026-09-05T10:29:00Z", "session": "blink"}),
        encoding="utf-8")
    r3 = _by_session(build_rows(logs, qc))["blink"]
    assert r3["heartbeat_last_utc"] == "2026-09-05T10:29:00Z"
    assert "heartbeat_not_listed" not in r3["sources"]


def test_n_a_ledger_that_stops_naming_the_session_is_not_an_idle_tail(lake):
    """(n) The defect the ledger-recovery candidate created the moment it reached the
    lake, 2026-09-07. Its 198 synthesised rows carry an EMPTY `session` (only its 252
    snapshot-native rows have one), so a session's ledger ends where the ATTRIBUTION
    ends, not where the work does. `ofB`'s last session-stamped row is `evaluate` at
    16:33:53 and rows for the same tag run to 18:58:23 — and the table published a
    351.6 min "idle tail" across hours of measured work. Unflagged, the run summary
    read 1826.3 min of idleness over 13 sessions.

    `cut`  — later blank-session rows for its own tag: flagged, and out of the headline.
    `whole`— later blank-session rows for SOMEBODY ELSE's tag: untouched, so the guard
             cannot be passing by flagging everything.
    """
    logs, qc = lake
    _hw(logs / "hw_cut.csv", ["2026-09-05T10:00:00Z", "2026-09-05T16:00:00Z"])
    _hw(logs / "hw_whole.csv", ["2026-09-05T10:00:00Z", "2026-09-05T16:00:00Z"])
    (qc / "train_queue_status_queue_r_20260905T000000Z.csv").write_text(
        "job,year,tag,step,state,exit,minutes,detail,ts,host,session\n"
        "j1,2020,of_2020,evaluate,OK,0,1.0,,2026-09-05 11:00:00,h,cut\n"
        "j1,2020,other,evaluate,OK,0,1.0,,2026-09-05 11:00:00,h,whole\n"
        # …and the recovered rows: same tags, later, naming nobody.
        "j1,2020,of_2020,inference,OK,0,1.0,RECOVERED-FROM-LOGS: x,2026-09-05 14:00:00,,\n"
        "j1,2020,third,inference,OK,0,1.0,RECOVERED-FROM-LOGS: x,2026-09-05 14:00:00,,\n",
        encoding="utf-8", newline="")

    rows = _by_session(build_rows(logs, qc))
    assert rows["cut"]["idle_tail_min"] == "300.0"          # published, not suppressed
    assert "later_rows_unattributed(of_2020)" in rows["cut"]["sources"]
    assert rows["whole"]["idle_tail_min"] == "300.0"
    assert "later_rows_unattributed" not in rows["whole"]["sources"]


def test_o_the_cpu_identity_is_read_from_hw_meta_and_blank_without_it(lake):
    """(o) The three columns appended 2026-09-08, and the reason they had to be.

    `spdc1` and `spdvc1` are both CPU runtimes that ran the SAME 632-tile `tile` step
    over the same ortho, in 21.0 vs 39.1 sampled minutes at a median `cpu_pct` of 28.9
    vs 21.3. Nothing in either machine's record could say whether the hosts differed:
    hw_meta's original eleven keys size a runtime and never name it.

    `named` — a meta carrying the three keys: they reach the table as TEXT, the model
              string intact (it holds `(R)` and an `@`, and would carry a comma on some
              hosts — the writer quotes, it must not be mangled here).
    `sized` — a meta with the eleven original keys only, which is every hw_meta on the
              lake today including `hw_meta_spdvc1.json`: the three cells are blank and
              the columns it DOES carry are untouched, so the reader can tell "this
              logger predates the keys" from "this logger could not read /proc".
    """
    logs, qc = lake
    _hw(logs / "hw_named.csv", ["2026-09-05T01:00:00Z", "2026-09-05T02:00:00Z"], gpu="")
    (logs / "hw_meta_named.json").write_text(json.dumps({
        "session": "named", "vcpus": 2, "ram_gb": 13.6,
        "cpu_model": "Intel(R) Xeon(R) CPU @ 2.20GHz", "cpu_mhz": 2200.0,
        "bogomips": "4399.99"}), encoding="utf-8")
    _hw(logs / "hw_sized.csv", ["2026-09-05T01:00:00Z", "2026-09-05T02:00:00Z"], gpu="")
    (logs / "hw_meta_sized.json").write_text(json.dumps({
        "session": "sized", "vcpus": 2, "ram_gb": 13.6, "gpu_name": ""}),
        encoding="utf-8")

    rows = _by_session(build_rows(logs, qc))
    assert rows["named"]["cpu_model"] == "Intel(R) Xeon(R) CPU @ 2.20GHz"
    assert rows["named"]["cpu_mhz"] == "2200.0"
    assert rows["named"]["bogomips"] == "4399.99"

    assert rows["sized"]["cpu_model"] == ""
    assert rows["sized"]["cpu_mhz"] == ""
    assert rows["sized"]["bogomips"] == ""
    assert rows["sized"]["vcpus"] == "2" and rows["sized"]["ram_gb"] == "13.6"
    assert "hw_meta" in rows["sized"]["sources"].split(";")


def test_the_two_clocks_parse_to_the_same_naive_form():
    """Status rows are naive VM-local (`phase4_train_queue.py::run_step`), hw and
    heartbeat are `...Z`. The instrument treats them as one clock — see its docstring —
    so the parser must return the SAME instant for the two spellings, not offset ones."""
    assert parse_ts("2026-09-05T10:20:30Z") == parse_ts("2026-09-05 10:20:30")
    assert parse_ts("") is None and parse_ts(None) is None and parse_ts("junk") is None


def test_harvested_artifact_matches_the_published_schema():
    """The tracked CSV, when it exists, is the schema docs/SCHEMAS.md describes."""
    p = Path(__file__).resolve().parents[2] / "phase4" / "qc" / "runtime_sessions.csv"
    if not p.exists():
        pytest.skip("runtime_sessions.csv not harvested yet")
    rdr = csv.DictReader(p.read_text(encoding="utf-8").splitlines())
    assert rdr.fieldnames == COLS
    sessions = [r["session"] for r in rdr]
    assert sessions == sorted(sessions)
    assert len(sessions) == len(set(sessions)), "one row per session"


def test_p_a_drive_duplicate_is_the_same_session_not_a_second_runtime(lake):
    """(p) `hw_healA (1).csv` beside `hw_healA.csv` — two Drive objects, one name, one
    folder (rclone.org/drive, "Duplicated files"), as the lake held on 2026-09-08 after
    `vm_hwlogger.py::mirror_once` spent a session replacing a destination that existed.

    Read literally the twin is a WHOLE EXTRA RUNTIME on this table: session `healA (1)`,
    `sources` reading `hw` and nothing else, no beacon, no queue rows, plus a spurious
    `heartbeat_not_listed` — which is precisely the shape of a machine whose telemetry
    failed, so it does not even look wrong. Nobody would be counting a phantom; they
    would be counting a runtime with broken instrumentation.

    Unlike the sibling table this one needs no row-level merge — its hw columns are
    min / max / any over the session's files, already union operations — so what is
    pinned here is that the two files fold into ONE row, that the row's span covers
    both, and that it SAYS a duplicate exists rather than absorbing it silently.
    """
    logs, qc = lake
    _hw(logs / "hw_healA.csv", ["2026-09-08T06:30:51Z", "2026-09-08T08:57:47Z"])
    _hw(logs / "hw_healA (1).csv", ["2026-09-08T06:30:51Z", "2026-09-08T08:05:21Z"])

    rows = _by_session(build_rows(logs, qc))
    assert set(rows) == {"healA"}, "the Drive duplicate published as its own runtime"
    r = rows["healA"]
    assert r["hw_first_utc"] == "2026-09-08T06:30:51Z"
    assert r["hw_last_utc"] == "2026-09-08T08:57:47Z", "the longer file sets the bound"
    assert r["hw_hours"] == "2.4489"
    assert "hw_drive_duplicate(hw_healA (1).csv)" in r["sources"]


def test_q_a_lone_drive_duplicate_keeps_the_real_session_name(lake):
    """The stranded half can outlive the other — a dedupe, or a hand cleanup that deleted
    the wrong object, leaves only the ` (1)`. The row must still be `healA`: a table that
    renames a paid runtime according to how its file was tidied is worse than one that
    misses it, because the new name looks like a real machine. `_v2` is stripped too, and
    Drive appends its suffix to the whole name including the schema fork."""
    logs, qc = lake
    _hw(logs / "hw_healA (1).csv", ["2026-09-08T06:30:51Z", "2026-09-08T08:05:21Z"])
    _hw(logs / "hw_other_v2 (2).csv", ["2026-09-08T06:30:51Z"])

    rows = _by_session(build_rows(logs, qc))
    assert set(rows) == {"healA", "other"}
    assert "hw_drive_duplicate(hw_healA (1).csv)" in rows["healA"]["sources"]
    assert "hw_drive_duplicate(hw_other_v2 (2).csv)" in rows["other"]["sources"]
    # And an ordinary name is not flagged: the suffix is anchored at the end of the
    # stem, so a session genuinely spelled with parentheses is untouched.
    assert session_of_hw("hw_foo (1)bar.csv") == "foo (1)bar"
