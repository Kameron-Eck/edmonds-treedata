"""The hardware-attribution instrument, on fixtures whose answers are hand-computed.

WHY THESE CASES. `harvest_hw_attribution.py` exists because the same join was done in
chat and came out wrong twice — once by matching samples against every VM's step
intervals first-hit-wins, once by testing `net_rx_mb_s` and forgetting `net_tx_mb_s`, so
checkpoint uploads counted as "nothing happening". Both defects are pinned here as
tests, on rows small enough to count by hand:

  a  a v2 (marker) file, including a sample where ONLY net TX is high — it must not
     count toward `nothing_frac`. That single row is the second defect.
  b  a legacy file under two overlapping step intervals that DISAGREE — those samples
     must be dropped and counted, not silently assigned. That is the first defect.
  c  a legacy file under one interval — attribution still happens; the drop rule is
     conservative, not paralysing.
  d  a CPU-only file (blank GPU columns) — the rows survive. A "GPU sessions only"
     filter would delete exactly the machines the offload argument is about.
  e  byte-identical output across two runs. A tracked CSV that churns produces a diff
     on every harvest and stops being read.
  f  a session whose every sample is ambiguity-dropped — the ALL row is still emitted,
     with zero samples. A table that accounts for paid VM time may not silently omit a
     machine that ran.
  g  a session whose file parses to NO samples at all — same rule, reached by the other
     road. `if not rows: continue` deleted it from the table outright, which is exactly
     the omission (f) exists to prevent.
  h  a v2 file whose `step` column is present but entirely blank — it must NOT be
     published as a 100% `(between)` machine on the trusted `marker` tier. Presence of
     the column was the old test; use of it is the new one.
  i  a marker file carrying PHASES (`train_2017#launching`) — one step, several rows,
     the `step` column unchanged and the phase in its own column. `(between)` is this
     table's residual, which §7 leaves attributable to nothing; the phases
     are the queue-side time that belongs somewhere else.
  j  a DRIVE DUPLICATE — `hw_healA (1).csv` beside `hw_healA.csv`, two objects with one
     name in one folder (rclone.org/drive, "Duplicated files"). Read literally it is a
     runtime called `healA (1)`, published on the trusted `marker` tier with samples
     counted on both rows. Four shapes, because the twin is not always the strict prefix
     the lake happens to hold: prefix (nothing may move), diverging (the unique samples
     must land), twin-only (the session keeps its real name), and the tie where the twin
     sorts first (it must never be the file that is read).

Plus the two accounting traps the row itself must close: a session owning BOTH schemas
keeps each file on its own basis (a marker's per-machine step is never re-guessed from
another VM's step log), and the ALL row pools ATTRIBUTED samples only — which is why
`samples_parsed` and `span_hours` sit beside `samples` and `hours`.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_hw_attribution.py -q
"""
from pathlib import Path

import pytest

from instruments.harvest_hw_attribution import (
    COLS,
    build_rows,
    main,
    norm_step,
    session_of,
    split_step,
)

V1_HEADER = ("ts_utc,gpu_util_pct,gpu_mem_util_pct,gpu_mem_used_mb,gpu_power_w,"
             "cpu_pct,disk_read_mb_s,disk_write_mb_s,net_rx_mb_s,net_tx_mb_s,"
             "disk_used_gb,disk_free_gb")
V2_HEADER = V1_HEADER + ",cpu_iowait_pct,step,run_tag"

DAY = "2026-09-05T03:"


def _ts(sec):
    return f"{DAY}{sec // 60:02d}:{sec % 60:02d}Z"


def _v2(sec, gpu, cpu, dr, dw, rx, tx, iowait, step, tag="t"):
    return (f"{_ts(sec)},{gpu},0,0,50.0,{cpu},{dr},{dw},{rx},{tx},"
            f"50.0,200.0,{iowait},{step},{tag}")


def _v1(sec, gpu, cpu, dr, dw, rx, tx):
    return f"{_ts(sec)},{gpu},0,0,50.0,{cpu},{dr},{dw},{rx},{tx},50.0,200.0"


def _write(path, header, rows):
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8", newline="")


def _steplog(logs, step, start_sec, end_sec):
    name = f"phase4_semantic_finetune_{step}_2026-09-05T03-{start_sec:02d}.log"
    (logs / name).write_text(
        f"=== phase4_semantic_finetune --step {step} ===\n"
        f"started:   2026-09-05T03:{start_sec // 60:02d}:{start_sec % 60:02d}.000000\n"
        f"completed: 2026-09-05T03:{end_sec // 60:02d}:{end_sec % 60:02d}.000000\n"
        f"elapsed:   1.0min\nerrors:    none\n", encoding="utf-8")


def _by_step(rows, session, basis=None):
    """step -> row for one session. Rows are keyed (session, step, BASIS), so a session
    that owns files of both schemas needs `basis` to pick a side."""
    sel = [r for r in rows if r["session"] == session
           and (basis is None or r["basis"] == basis)]
    out = {r["step"]: r for r in sel}
    assert len(out) == len(sel), "two bases in one session — pass basis="
    return out


def test_norm_step_strips_the_year_label_only():
    assert norm_step("train_2017") == "train"
    assert norm_step("evaluate_2006s") == "evaluate"
    assert norm_step("postproc_2019n") == "postproc"
    assert norm_step("postproc") == "postproc"
    assert norm_step("") == "(between)"
    assert norm_step(None) == "(between)"


def test_marker_basis_fractions_are_hand_checkable(tmp_path):
    """(a) Five samples, counted by hand. The second is the TX row: GPU idle, CPU idle,
    disk idle, RX idle — and 8 MB/s going OUT. A checkpoint upload is work."""
    logs = tmp_path / "logs"
    logs.mkdir()
    _write(logs / "hw_mk.csv", V2_HEADER, [
        _v2(0,  90, 60, 0, 0, 0, 0,  2, "train_2017"),      # gpu busy, cpu busy
        _v2(5,   0,  5, 0, 0, 0, 8, 20, "train_2017"),      # TX only -> NOT nothing
        _v2(10,  0,  1, 0, 0, 0, 0,  1, "train_2017"),      # nothing
        _v2(15,  0,  1, 3, 3, 0, 0, 50, "postproc_2017"),   # disk 6 MB/s
        _v2(20,  0,  1, 0, 0, 0, 0,  0, ""),                # between, nothing
    ])
    rows = _by_step(build_rows(logs), "mk")

    assert set(rows) == {"train", "postproc", "(between)", "ALL"}
    tr = rows["train"]
    assert tr["basis"] == "marker"
    assert tr["ambiguous_dropped"] == 0
    assert tr["samples"] == 3
    assert tr["gpu_present"] == "1.0000"
    assert tr["gpu_busy_frac"] == "0.3333"          # only the 90
    assert tr["gpu_util_mean"] == "30.0000"         # (90+0+0)/3
    assert tr["cpu50_frac"] == "0.3333"
    assert tr["iowait10_frac"] == "0.3333"          # the 20
    assert tr["tx1_frac"] == "0.3333"
    assert tr["rx1_frac"] == "0.0000"
    assert tr["disk5_frac"] == "0.0000"
    assert tr["nothing_frac"] == "0.3333", "the TX sample must not count as nothing"

    pp = rows["postproc"]
    assert pp["disk5_frac"] == "1.0000" and pp["nothing_frac"] == "0.0000"
    assert pp["iowait10_frac"] == "1.0000"

    assert rows["(between)"]["nothing_frac"] == "1.0000"

    a = rows["ALL"]
    assert a["samples"] == 5
    assert a["hours"] == "0.0069"                   # 5 samples x 5 s
    assert a["nothing_frac"] == "0.4000"            # rows 3 and 5
    assert a["gpu_busy_frac"] == "0.2000"


def test_disagreeing_intervals_are_dropped_not_guessed(tmp_path):
    """(b) The cross-VM defect. tile [0,60] and train [20,80] overlap and the step logs
    carry no session field, so 20..60 cannot be told apart — those samples are dropped
    and counted, never assigned to whichever log sorted first."""
    logs = tmp_path / "logs"
    logs.mkdir()
    _steplog(logs, "tile_2017", 0, 60)
    _steplog(logs, "train_2017", 20, 80)
    _write(logs / "hw_lg.csv", V1_HEADER, [
        _v1(0,  0, 1, 0, 0, 0, 0),     # tile only
        _v1(30, 0, 1, 0, 0, 0, 0),     # both -> dropped
        _v1(40, 0, 1, 0, 0, 0, 0),     # both -> dropped
        _v1(70, 0, 1, 0, 0, 0, 0),     # train only
        _v1(99, 0, 1, 0, 0, 0, 0),     # neither
    ])
    rows = _by_step(build_rows(logs), "lg")

    assert rows["ALL"]["basis"] == "interval"
    assert rows["ALL"]["samples"] == 3, "the two ambiguous samples must not be attributed"
    assert rows["ALL"]["ambiguous_dropped"] == 2
    # the ALL row pools ATTRIBUTED samples only, so `hours` (3 kept x the file's own
    # measured cadence, median of 30/10/30/29 s = 29.5 s) is NOT the session span
    # (99 s) — both denominators are on the row so neither has to be re-derived
    assert rows["ALL"]["hours"] == "0.0246"
    assert rows["ALL"]["samples_parsed"] == 5
    assert rows["ALL"]["span_hours"] == "0.0275"
    assert rows["tile"]["samples"] == 1
    assert rows["train"]["samples"] == 1
    assert rows["(between)"]["samples"] == 1
    # the drop count is repeated on every row of the session, so a reader who slices to
    # one step still sees how much of that session was unattributable
    assert all(r["ambiguous_dropped"] == 2 for r in rows.values())
    # a legacy file has no iowait column at all — blank, not zero
    assert all(r["iowait10_frac"] == "" for r in rows.values())


def test_single_interval_still_attributes(tmp_path):
    """(c) The conservative rule must not swallow the unambiguous case."""
    logs = tmp_path / "logs"
    logs.mkdir()
    _steplog(logs, "inference_2019n", 0, 60)
    _write(logs / "hw_one.csv", V1_HEADER, [
        _v1(10, 80, 20, 0, 0, 0, 0),
        _v1(20, 80, 20, 0, 0, 0, 0),
        _v1(90,  0,  1, 0, 0, 0, 0),
    ])
    rows = _by_step(build_rows(logs), "one")
    assert rows["inference"]["samples"] == 2
    assert rows["inference"]["gpu_busy_frac"] == "1.0000"
    assert rows["inference"]["ambiguous_dropped"] == 0
    assert rows["(between)"]["samples"] == 1


def test_cpu_only_sessions_survive_with_blank_gpu(tmp_path):
    """(d) A CPU runtime logs no GPU readings. It is the OFFLOAD TARGET, so it must be
    emitted — with an empty GPU fraction rather than a fabricated 0% busy."""
    logs = tmp_path / "logs"
    logs.mkdir()
    _write(logs / "hw_cpuonly.csv", V1_HEADER, [
        _v1(0,  "", 80, 0, 0, 0, 0),      # cpu busy
        _v1(5,  "",  1, 0, 0, 0, 0),      # nothing at all
        _v1(10, "",  1, 9, 0, 0, 0),      # disk busy
    ])
    rows = _by_step(build_rows(logs), "cpuonly")
    a = rows["ALL"]
    assert a["samples"] == 3
    assert a["gpu_present"] == "0.0000"
    assert a["gpu_busy_frac"] == "", "no reading is not 0% busy"
    assert a["gpu_util_mean"] == ""
    assert a["cpu50_frac"] == "0.3333"
    assert a["disk5_frac"] == "0.3333"
    assert a["nothing_frac"] == "0.3333"


def test_session_name_strips_the_v2_schema_suffix(tmp_path):
    """hw_x.csv and hw_x_v2.csv are one machine writing two schemas (the logger forks
    rather than append a wider row, so a REUSED session name produces exactly this).
    Same session, but each FILE keeps its own basis: pooling them to the weaker one
    threw the v2 samples' own per-machine `step` away and re-guessed them from another
    VM's step log — here that would relabel a marker-stamped `train` as `tile`."""
    logs = tmp_path / "logs"
    logs.mkdir()
    _steplog(logs, "tile_2009", 0, 60)          # some OTHER VM's step, spanning both
    _write(logs / "hw_dual.csv", V1_HEADER, [_v1(0, 0, 1, 0, 0, 0, 0)])
    _write(logs / "hw_dual_v2.csv", V2_HEADER,
           [_v2(5, 0, 1, 0, 0, 0, 0, 0, "train_2017"),
            _v2(10, 0, 1, 0, 0, 0, 0, 0, "train_2017")])
    rows = build_rows(logs)

    mk = _by_step(rows, "dual", "marker")
    assert mk["ALL"]["samples"] == 2 and mk["ALL"]["source_file"] == "hw_dual_v2.csv"
    assert set(mk) == {"train", "ALL"}, "the marker's own step must survive"

    iv = _by_step(rows, "dual", "interval")
    assert iv["ALL"]["samples"] == 1 and iv["ALL"]["source_file"] == "hw_dual.csv"
    assert iv["tile"]["samples"] == 1


def test_a_fully_ambiguous_session_still_gets_its_ALL_row(tmp_path):
    """(f) Every sample dropped -> no step rows. The session must NOT disappear: this
    is an accounting table for paid VM time, and a runtime silently absent is worse
    than one whose split is unknown."""
    logs = tmp_path / "logs"
    logs.mkdir()
    _steplog(logs, "train_2017", 0, 60)
    _steplog(logs, "tile_2018", 0, 60)          # disagrees everywhere they overlap
    _write(logs / "hw_amb.csv", V1_HEADER, [_v1(10, 0, 1, 0, 0, 0, 0),
                                            _v1(20, 0, 1, 0, 0, 0, 0)])
    rows = _by_step(build_rows(logs), "amb")
    assert set(rows) == {"ALL"}
    a = rows["ALL"]
    assert a["samples"] == 0 and a["hours"] == "0.0000"
    assert a["ambiguous_dropped"] == 2
    assert a["samples_parsed"] == 2, "parsed = kept + dropped, recoverable from the row"
    assert a["span_hours"] == "0.0028"          # 10 s
    assert a["nothing_frac"] == "" and a["gpu_present"] == "", "no samples, no fraction"


def test_a_session_with_no_parseable_samples_still_gets_its_ALL_row(tmp_path):
    """(g) The same never-omit rule, on the other road into it.

    (f) covers a session whose samples were all DROPPED. This covers one whose file
    yielded no samples to drop: a header-only file (the logger created it and died
    before its first tick) and one whose every `ts_utc` is unparseable (a truncated or
    half-flushed FUSE write — `read_hw` discards those rows because they can be
    attributed on neither basis). Both used to hit `if not rows: continue` and vanish,
    taking with them the one fact that matters most about that machine: it ran, and its
    hardware log is empty. Zero samples is a finding about the logger; an absent row is
    indistinguishable from a VM that never existed.
    """
    logs = tmp_path / "logs"
    logs.mkdir()
    _write(logs / "hw_hdr.csv", V1_HEADER, [])                    # header only
    _write(logs / "hw_bad.csv", V1_HEADER,                        # unparseable stamps
           ["not-a-timestamp,0,0,0,50.0,1,0,0,0,0,50.0,200.0"])
    rows = build_rows(logs)

    for session in ("hdr", "bad"):
        r = _by_step(rows, session)
        assert set(r) == {"ALL"}, f"{session} lost its ALL row"
        a = r["ALL"]
        assert a["samples"] == 0 and a["samples_parsed"] == 0
        assert a["ambiguous_dropped"] == 0
        assert a["hours"] == "0.0000" and a["span_hours"] == "0.0000"
        assert a["gpu_present"] == "" and a["nothing_frac"] == "", \
            "no samples, no fraction — blank, never 0.0000"
        assert a["basis"] == "interval"
        assert a["source_file"] == f"hw_{session}.csv"


def test_a_blank_step_column_is_demoted_off_the_marker_tier(tmp_path):
    """(h) THE TIER GUARD, fired. The basis used to be chosen on the column's PRESENCE,
    so a v2 file with nothing but blanks in `step` published as `marker` — the tier
    docs/SCHEMAS.md tells readers to trust as a per-machine measurement — asserting that
    100% of the runtime was `(between)`, i.e. that no engine step ran there at all.

    Blank has two causes the column cannot separate: genuinely between steps, or
    `pipeline_log.py::StepLogger` never published a marker on that VM (an unwritable
    directory returns silently, by design). A file that never once carried a marker has
    demonstrated nothing about the marker mechanism, so it drops to the interval basis —
    where, as this fixture shows, the step logs still recover the step that ran.

    The demotion is recorded in `source_file` because the row has no free-text column;
    a reader slicing on `basis` alone already gets the weaker tier, and this says why.
    """
    logs = tmp_path / "logs"
    logs.mkdir()
    _steplog(logs, "train_2017", 0, 60)
    _write(logs / "hw_blank_v2.csv", V2_HEADER,
           [_v2(s, 50, 60, 0, 0, 0, 0, 1, "") for s in (10, 20, 30)])
    rows = _by_step(build_rows(logs), "blank")

    assert set(rows) == {"train", "ALL"}, \
        "the interval basis should have recovered the step that ran"
    a = rows["ALL"]
    assert a["basis"] == "interval", "a never-used step column claimed the trusted tier"
    assert a["samples"] == 3
    assert "step column present but blank" in a["source_file"]
    assert "hw_blank_v2.csv" in a["source_file"]
    # and the fallback is not blind: iowait still reads, because the file IS v2.
    assert a["iowait10_frac"] == "0.0000"


def test_one_used_marker_cell_is_enough_to_keep_the_marker_tier(tmp_path):
    """The other side of (h) — the demotion must not swallow a working v2 file whose
    machine happened to idle between steps for most of its life. One non-blank cell is
    evidence the marker mechanism worked there; the blanks are then real `(between)`.
    """
    logs = tmp_path / "logs"
    logs.mkdir()
    _steplog(logs, "tile_2017", 0, 60)          # would relabel everything if demoted
    _write(logs / "hw_mostly.csv", V2_HEADER,
           [_v2(10, 0, 1, 0, 0, 0, 0, 1, ""),
            _v2(20, 0, 1, 0, 0, 0, 0, 1, ""),
            _v2(30, 90, 60, 0, 0, 0, 0, 1, "train_2017")])
    rows = _by_step(build_rows(logs), "mostly")

    assert rows["ALL"]["basis"] == "marker"
    assert set(rows) == {"(between)", "train", "ALL"}
    assert rows["(between)"]["samples"] == 2
    assert "blank" not in rows["ALL"]["source_file"]


def test_norm_step_strips_the_phase_before_the_year_label(tmp_path):
    """ORDER MATTERS. The year regex is anchored at the end of the string, so with the
    `#phase` still attached it matches nothing and `train_2017#verifying` would become
    its own step — one step split across two rows, which is the failure the phase column
    was added to prevent, not cause."""
    assert norm_step("train_2017#verifying") == "train"
    assert norm_step("postproc_2019n#launching") == "postproc"
    assert norm_step("#launching") == "(between)"
    assert norm_step("train_2017") == "train"


def test_split_step_maps_the_phase_vocabulary():
    """The vocabulary lives in phase4seg/names.py::hw_step_marker_path; this is the
    reader's half of it. An unknown value passes through: reporting what the marker said
    beats silently retiring a phase the queue has started writing."""
    assert split_step("train_2017") == ("train", "open")
    assert split_step("train_2017#launching") == ("train", "launching")
    assert split_step("evaluate_2006s#verifying") == ("evaluate", "verifying")
    assert split_step("train_2017#") == ("train", "open")
    assert split_step("train_2017#futurephase") == ("train", "futurephase")
    assert split_step("") == ("(between)", "")
    assert split_step(None) == ("(between)", "")
    assert split_step("#verifying") == ("(between)", ""), \
        "a phase with no step names no step, so it cannot claim one"


def test_phases_split_one_step_into_rows_and_the_step_column_is_unchanged(tmp_path):
    """The point of the column, on a fixture that mixes all three phases of one step.

    `launching` and `verifying` are queue time around the engine step: today they have
    no marker at all and land in `(between)`, which §7 of
    Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md leaves attributable to nothing — and
    which the tracked `spdc1,(between),marker` row shows is not idleness at all
    (cpu50_frac at zero, iowait10_frac dominant: blocked on I/O). Separated, they are still
    `train` in the `step` column (so every existing slice keeps its meaning) and their
    cost is readable on its own row.
    """
    logs = tmp_path / "logs"
    logs.mkdir()
    _write(logs / "hw_ph.csv", V2_HEADER, [
        _v2(0,  0,  5, 0, 0, 0, 0, 40, "train_2017#launching"),   # staging, iowait
        _v2(5,  0,  5, 0, 0, 0, 0, 40, "train_2017#launching"),
        _v2(10, 90, 60, 0, 0, 0, 0, 1, "train_2017"),             # the step itself
        _v2(15, 0,  1, 0, 0, 0, 0,  1, "train_2017#verifying"),
        _v2(20, 0,  1, 0, 0, 0, 0,  1, ""),                       # really between
    ])
    rows = [r for r in build_rows(logs) if r["session"] == "ph"]
    keyed = {(r["step"], r["phase"]): r for r in rows}

    assert set(keyed) == {("train", "open"), ("train", "launching"),
                          ("train", "verifying"), ("(between)", ""), ("ALL", "")}
    assert all(r["basis"] == "marker" for r in rows)

    launch = keyed[("train", "launching")]
    assert launch["samples"] == 2
    assert launch["iowait10_frac"] == "1.0000", "the staging stall must be visible"
    assert launch["gpu_busy_frac"] == "0.0000"
    assert keyed[("train", "open")]["gpu_busy_frac"] == "1.0000"
    assert keyed[("train", "verifying")]["samples"] == 1
    # the ALL row pools every phase and therefore claims none of them
    assert keyed[("ALL", "")]["samples"] == 5


def test_bare_steps_read_open_and_between_reads_blank(tmp_path):
    """The default on both bases. A step LOG can only record a step that OPENED, so the
    interval basis can never see anything but `open`; `(between)` names no step, so it
    has no phase to report — blank, not `open`."""
    logs = tmp_path / "logs"
    logs.mkdir()
    _steplog(logs, "inference_2019n", 0, 60)
    _write(logs / "hw_iv.csv", V1_HEADER, [_v1(10, 80, 20, 0, 0, 0, 0),
                                           _v1(90, 0, 1, 0, 0, 0, 0)])
    _write(logs / "hw_mk2.csv", V2_HEADER, [_v2(10, 90, 60, 0, 0, 0, 0, 1, "tile_2017"),
                                            _v2(20, 0, 1, 0, 0, 0, 0, 1, "")])
    rows = build_rows(logs)

    iv = _by_step(rows, "iv")
    assert iv["inference"]["phase"] == "open" and iv["(between)"]["phase"] == ""
    assert iv["ALL"]["phase"] == ""
    mk = _by_step(rows, "mk2")
    assert mk["tile"]["phase"] == "open" and mk["(between)"]["phase"] == ""
    assert mk["ALL"]["phase"] == ""


def test_output_is_deterministic_and_columns_are_the_contract(tmp_path):
    """(e) Two runs, byte-identical. Plus the header IS the contract in docs/SCHEMAS.md."""
    logs = tmp_path / "logs"
    logs.mkdir()
    _steplog(logs, "tile_2017", 0, 60)
    _steplog(logs, "train_2017", 20, 80)
    _write(logs / "hw_a.csv", V1_HEADER, [_v1(s, 0, 1, 0, 0, 0, 0)
                                          for s in (0, 30, 70, 99)])
    _write(logs / "hw_b.csv", V2_HEADER, [_v2(s, 50, 1, 0, 0, 0, 0, 1, "train_2017")
                                          for s in (0, 5, 10)])
    out1, out2 = tmp_path / "o1.csv", tmp_path / "o2.csv"
    assert main(["--logs-dir", str(logs), "--out", str(out1)]) == 0
    assert main(["--logs-dir", str(logs), "--out", str(out2)]) == 0
    b1 = out1.read_bytes()
    assert b1 == out2.read_bytes()
    assert b1.decode("utf-8").splitlines()[0] == ",".join(COLS)
    # sorted by (session, step), and every session gets its ALL row
    lines = [ln.split(",")[:2] for ln in b1.decode("utf-8").splitlines()[1:]]
    assert lines == sorted(lines)
    assert ["a", "ALL"] in lines and ["b", "ALL"] in lines


def test_torn_rows_are_counted_and_never_become_samples(tmp_path):
    """The writer defect fixed 2026-09-08, read from this side.

    The old flush appended to Drive from the sampling thread and could land PART of a
    write, leaving fragments: hw_spdg.csv holds a line whose `ts_utc` reads `200.5` and
    whose `gpu_mem_util_pct` reads `train_2017k` — the tail of one sample on a line of
    its own. Those were already dropped, for the unreadable timestamp, but SILENTLY, so
    the archive reported no read errors at all. The other shape the same failure can
    produce is worse and was not handled: a line carrying a whole row plus a fragment
    has a valid `ts_utc` and cells from two samples, and it SURVIVED.

    Both are dropped on arity here, both are counted, and `samples_parsed` — the
    session's own accounting — excludes them, because a torn line is not a sample that
    went unattributed, it is a line that was never a sample. Measured on the archive the
    day this landed: 147 such rows across the lake's hw files, previously reported as
    none.
    """
    logs = tmp_path / "logs"
    logs.mkdir()
    good = _v2(0, 90, 60, 0, 0, 0, 0, 2, "train_2017")
    (logs / "hw_torn.csv").write_text("\n".join([
        V2_HEADER,
        good,
        good + ",spliced,extra",                  # torn head: valid ts, too many cells
        "0,0,5582,60.0",                          # tail fragment: too few cells
        "200.5,0,0,0,50.0,1,0,0,0,0,50.0,200.0,1,train_2017k,t",  # ts is not a time
    ]) + "\n", encoding="utf-8", newline="")

    stats = {}
    rows = _by_step(build_rows(logs, stats=stats), "torn")
    assert stats["rows_dropped_malformed"] == 3
    assert rows["ALL"]["samples"] == 1
    assert rows["ALL"]["samples_parsed"] == 1, "a torn line is not an unattributed sample"
    assert set(rows) == {"train", "ALL"}, "the spliced row must not name a step"


def test_stats_is_optional_so_every_existing_caller_is_unchanged(tmp_path):
    """`stats` is an out-parameter, not a return-type change: build_rows still returns
    the list, and a caller that does not care passes nothing."""
    logs = tmp_path / "logs"
    logs.mkdir()
    _write(logs / "hw_ok.csv", V2_HEADER, [_v2(0, 0, 1, 0, 0, 0, 0, 1, "train_2017")])
    assert [r["step"] for r in build_rows(logs)] == ["ALL", "train"]


def test_dry_run_writes_nothing(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    _write(logs / "hw_z.csv", V1_HEADER, [_v1(0, 0, 1, 0, 0, 0, 0)])
    out = tmp_path / "never.csv"
    assert main(["--logs-dir", str(logs), "--out", str(out), "--dry-run"]) == 0
    assert not out.exists()


def test_the_tracked_csv_matches_the_declared_columns():
    """The harvested artifact, when it exists, is the schema docs/SCHEMAS.md describes."""
    p = Path(__file__).resolve().parents[2] / "phase4" / "qc" / "hw_step_attribution.csv"
    if not p.exists():
        pytest.skip("hw_step_attribution.csv absent — run "
                    "qc/instruments/harvest_hw_attribution.py")
    head = p.read_text(encoding="utf-8").splitlines()[0]
    assert head == ",".join(COLS), (
        "phase4/qc/hw_step_attribution.csv is stale — rerun "
        "qc/instruments/harvest_hw_attribution.py")


# ── Drive duplicates (2026-09-08) ────────────────────────────────────────────
# Google Drive permits two objects with one name in one folder (rclone.org/drive,
# "Duplicated files"); the desktop client renders the second as `hw_healA (1).csv`.
# Read literally that is a runtime named `healA (1)` — a machine that never existed,
# published on the TRUSTED marker tier, sharing samples with the real session and
# counting them on both rows. Four shapes, because the twin is not always a prefix.


def test_session_of_strips_the_drive_suffix_after_the_schema_suffix():
    """Strip order is `.csv` -> ` (N)` -> `_v2`. Drive appends its suffix to the WHOLE
    name, schema fork included, so stripping `_v2` first leaves ` (1)` welded on and the
    session comes back as `x_v2 (1)` — a phantom on the phantom."""
    assert session_of("hw_healA.csv") == "healA"
    assert session_of("hw_healA (1).csv") == "healA"
    assert session_of("hw_healA (12).csv") == "healA"
    assert session_of("hw_x_v2.csv") == "x"
    assert session_of("hw_x_v2 (1).csv") == "x"
    # Anchored at the end with `.csv` already off: a session genuinely spelled this way
    # is not a Drive artifact and must survive.
    assert session_of("hw_foo (1)bar.csv") == "foo (1)bar"


def test_a_twin_that_is_a_prefix_changes_no_number_of_its_session(tmp_path):
    """THE SHAPE ON THE LAKE. `mirror_once` publishes the WHOLE spool every tick, so each
    publish is a superset of the one before and a stranded twin is a strict PREFIX of the
    file that kept growing — `hw_healA (1).csv` is byte-identical to the first 1,128 rows
    of `hw_healA.csv`'s 1,752, measured 2026-09-08.

    Two things must therefore hold at once, and only one of them was true before: the
    twin must not appear as its own session, AND merging it must move nothing. The
    control is the same harvest over the canonical file ALONE — every published number
    must match it, because the twin contributes no sample the canonical lacks. If they
    differ, the merge is double-counting, which is exactly what `rows += rows` did."""
    logs = tmp_path / "logs"
    logs.mkdir()
    rows = [_v2(s, 90, 60, 0, 0, 0, 0, 1, "train_2017") for s in range(0, 60, 5)]
    _write(logs / "hw_healA.csv", V2_HEADER, rows)
    _write(logs / "hw_healA (1).csv", V2_HEADER, rows[:6])      # a strict prefix

    got = build_rows(logs)
    assert {r["session"] for r in got} == {"healA"}, "the twin published as a session"

    control = build_rows(logs, hw_files=[logs / "hw_healA.csv"])
    keys = ("session", "step", "basis", "phase", "samples", "hours", "span_hours",
            "samples_parsed", "ambiguous_dropped", "gpu_busy_frac", "nothing_frac")
    assert [{k: r[k] for k in keys} for r in got] == \
           [{k: r[k] for k in keys} for r in control]

    # What DID change: the row says its files were merged, and says it added nothing.
    all_row = _by_step(got, "healA")["ALL"]
    assert "hw_healA (1).csv" in all_row["source_file"]
    assert "-> +0 rows" in all_row["source_file"]


def test_a_diverging_twin_lands_its_unique_samples_and_reports_them(tmp_path):
    """NOT EVERY TWIN IS A PREFIX. A logger relaunched under one session name seeds its
    spool from whatever `out` it can read (`vm_hwlogger.py::_open_local`), and on the
    VM's own rclone view BOTH objects answer to that name — so a restart can seed from
    either and the two files then diverge. Throwing the twin away would lose real
    samples; concatenating them would count the shared ones twice.

    Union by `ts_utc` behind the longest file does neither: the four samples only the
    twin holds arrive, the six they share arrive once, and `samples_parsed` says 10."""
    logs = tmp_path / "logs"
    logs.mkdir()
    shared = [_v2(s, 90, 60, 0, 0, 0, 0, 1, "train_2017") for s in range(0, 30, 5)]
    _write(logs / "hw_healA.csv", V2_HEADER, shared)
    _write(logs / "hw_healA (1).csv", V2_HEADER,
           shared[:2] + [_v2(s, 90, 60, 0, 0, 0, 0, 1, "train_2017")
                         for s in range(30, 50, 5)])

    stats = {}
    got = build_rows(logs, stats=stats)
    assert {r["session"] for r in got} == {"healA"}
    all_row = _by_step(got, "healA")["ALL"]
    assert int(all_row["samples_parsed"]) == 10, "6 shared + 4 unique, each once"
    assert int(all_row["samples"]) == 10
    assert stats["twin_rows_merged"] == 4
    assert "-> +4 rows" in all_row["source_file"]
    # The span widens to cover the samples only the twin had.
    assert float(all_row["span_hours"]) == pytest.approx(45 / 3600.0, abs=1e-6)


def test_a_twin_whose_canonical_is_gone_is_still_its_session(tmp_path):
    """The stranded half can outlive the other: Drive holds two independent objects, and
    a `rclone dedupe`, a hand cleanup, or a delete of the wrong one leaves only the
    ` (1)`. The session must still be `healA` — the alternative is a table that silently
    renames a paid runtime because of how its file was tidied."""
    logs = tmp_path / "logs"
    logs.mkdir()
    _write(logs / "hw_healA (1).csv", V2_HEADER,
           [_v2(s, 90, 60, 0, 0, 0, 0, 1, "train_2017") for s in range(0, 30, 5)])

    stats = {}
    got = build_rows(logs, stats=stats)
    assert {r["session"] for r in got} == {"healA"}
    all_row = _by_step(got, "healA")["ALL"]
    assert all_row["basis"] == "marker", "a lone twin is still a v2 file with markers"
    assert int(all_row["samples"]) == 6
    # ONE file, so nothing was merged and the note must not appear: a single file passes
    # through untouched, which is what keeps every legacy session's numbers fixed.
    assert "merged by ts_utc" not in all_row["source_file"]
    assert stats["twin_rows_merged"] == 0


def test_the_twin_is_never_primary_even_when_it_sorts_first(tmp_path):
    """`hw_healA (1).csv` sorts BEFORE `hw_healA.csv` — space is 0x20, `.` is 0x2e — so
    `sorted()` alone makes the twin primary. That is invisible while one file is a prefix
    of the other and decides the reading the moment they disagree at a shared `ts_utc`,
    which is what a re-seeded restart produces.

    Equal row counts, so length cannot break the tie: the name WITHOUT ` (N)` must win,
    and the published `gpu_util_mean` says which file was read."""
    logs = tmp_path / "logs"
    logs.mkdir()
    _write(logs / "hw_healA.csv", V2_HEADER,
           [_v2(s, 90, 60, 0, 0, 0, 0, 1, "train_2017") for s in range(0, 20, 5)])
    _write(logs / "hw_healA (1).csv", V2_HEADER,
           [_v2(s, 10, 60, 0, 0, 0, 0, 1, "train_2017") for s in range(0, 20, 5)])

    all_row = _by_step(build_rows(logs), "healA")["ALL"]
    assert int(all_row["samples"]) == 4, "the same four stamps, not eight"
    assert float(all_row["gpu_util_mean"]) == pytest.approx(90.0), \
        "the Drive duplicate was read in preference to the canonical file"
