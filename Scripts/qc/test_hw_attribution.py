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

Plus the two accounting traps the row itself must close: a session owning BOTH schemas
keeps each file on its own basis (a marker's per-machine step is never re-guessed from
another VM's step log), and the ALL row pools ATTRIBUTED samples only — which is why
`samples_parsed` and `span_hours` sit beside `samples` and `hours`.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_hw_attribution.py -q
"""
from pathlib import Path

import pytest

from instruments.harvest_hw_attribution import COLS, build_rows, main, norm_step

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
