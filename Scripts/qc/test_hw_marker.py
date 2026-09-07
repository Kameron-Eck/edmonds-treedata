"""The open-step marker: the contract between StepLogger and vm_hwlogger.

WHAT IS BEING PINNED, and why it needs a test rather than a convention.

Per-step hardware attribution used to be forensic — join hw_*.csv timestamps against
the step logs of EVERY VM, because nothing recorded which step ran on which machine.
Reports/PIPELINE_SPEEDUP_OPTIONS_2026-09-07.md §7 (line 153) reports 8,304 of 28,999
samples (29%) dropped where concurrently-open intervals disagreed and nothing said which
VM ran which. The fix is a per-machine marker file: StepLogger
writes it on start(), deletes it on finish(), and vm_hwlogger stamps `step`/`run_tag`
onto every sample from it.

Two properties make or break that, and both fail SILENTLY:

  · the marker must never raise into the run, and must never write outside its VM.
    A step that dies because its telemetry file could not be written is strictly worse
    than a step with no telemetry, and the pipeline_log docstring already holds that
    standard for provenance. So the unwritable-directory case is tested explicitly —
    and so is the built-in default off-posix, because a POSIX-absolute path on Windows
    resolves DRIVE-RELATIVE: os.path.isdir("/content") measured True on the code-plane
    box on 2026-09-07, so "the parent does not exist locally" was never true and the
    parent-exists check alone let local steps write at the drive root.
  · the CSV must never mix two schemas. A v1 file that grew 15-column rows would be
    unrepairable, because nothing in the file says where the schema changed.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_hw_marker.py -q

No path hack here — and the omission is load-bearing twice over. qc/conftest.py already
puts pipeline/ on sys.path (THE canonical stanza, per test_status_discovery.py's ledger)
and pipeline_log is an installed py-module, so a bare `import vm_hwlogger` resolves;
`pipeline` is deliberately not a package, which is why it is bare and not dotted. Adding
one would also fail test_path_insert_ledger, whose regex matches the literal anywhere in
a file — this paragraph included, so it does not spell it.
"""
import json
import os
from pathlib import Path

import pytest

import vm_hwlogger as hw
from pipeline_log import StepLogger

SCRIPTS = Path(__file__).resolve().parents[1]


# ── StepLogger writes and clears the marker ───────────────────────────────────

def test_start_writes_the_marker_with_every_contract_field(tmp_path, monkeypatch):
    m = tmp_path / "hw_step_marker.json"
    monkeypatch.setenv("HW_STEP_MARKER", str(m))

    log = StepLogger("phase4_semantic_finetune", "train_2017", tmp_path,
                     capture_stdout=False)
    log.start()
    assert m.exists(), "start() did not publish the marker"

    d = json.loads(m.read_text(encoding="utf-8"))
    assert set(d) == {"script", "step", "run_tag", "pid", "started_utc"}
    assert d["script"] == "phase4_semantic_finetune"
    # The step string is passed through VERBATIM: the harvest groups on it, and the
    # engine's steps are `train_2017`-shaped (cli.py f"train_{lab}"). Any normalising
    # here would split one step across two harvest rows.
    assert d["step"] == "train_2017"
    assert isinstance(d["run_tag"], str)
    assert isinstance(d["pid"], int) and d["pid"] > 0
    assert len(d["started_utc"]) == 20 and d["started_utc"].endswith("Z")

    log.finish()


def test_finish_removes_the_marker_and_a_second_finish_is_a_noop(tmp_path, monkeypatch):
    m = tmp_path / "hw_step_marker.json"
    monkeypatch.setenv("HW_STEP_MARKER", str(m))

    log = StepLogger("s", "tile_2019", tmp_path, capture_stdout=False)
    log.start()
    assert m.exists()
    log.finish()
    assert not m.exists(), "the marker outlived its step — every later idle sample " \
                           "would be attributed to it"
    log.finish()          # the _finished guard: must not raise, must not resurrect
    assert not m.exists()


def test_unwritable_marker_directory_never_raises_into_the_run(tmp_path, monkeypatch):
    """An explicitly-pointed marker whose parent is missing: write nothing, create
    nothing, raise nothing. (The built-in default is covered by the test below.)"""
    m = tmp_path / "missing" / "m.json"
    monkeypatch.setenv("HW_STEP_MARKER", str(m))

    log = StepLogger("s", "labels_2020", tmp_path, capture_stdout=False)
    log.start()               # must not raise
    log.finish()              # must not raise
    assert not m.exists()
    assert not m.parent.exists(), "start() created the marker's parent directory — it " \
                                  "must only ever write into a directory that exists"


@pytest.mark.skipif(os.name == "posix",
                    reason="on posix the default IS the real marker path; writing it "
                           "is the correct behaviour and a test must not touch it")
def test_default_marker_is_never_resolved_off_posix(tmp_path, monkeypatch):
    """The case the parent-exists guard does NOT cover, and the reason it was added.

    "/content/hw_step_marker.json" is a Colab path. Off posix it resolves DRIVE-RELATIVE,
    and the resulting "content" directory exists on the code-plane box (measured
    2026-09-07), so isdir() returns True and the write proceeds — outside the repo, on
    every local QC and label step. Worse, a step that exits before finish() (e.g.
    qc/instruments/nir_change_probe.py calls start() with no context manager and can
    SystemExit) strands it there forever.
    """
    monkeypatch.delenv("HW_STEP_MARKER", raising=False)
    default = os.path.abspath("/content/hw_step_marker.json")
    pre = os.path.exists(default)

    log = StepLogger("s", "labels_2020", tmp_path, capture_stdout=False)
    log.start()
    try:
        assert log._marker_path is None, "the built-in Colab default was resolved off-posix"
        assert os.path.exists(default) == pre, f"start() wrote {default}"
    finally:
        log.finish()


# ── vm_hwlogger reads it ──────────────────────────────────────────────────────

def test_read_marker_valid_file(tmp_path):
    # A LIVE pid: read_marker discards a marker whose writer is gone, and a literal
    # like 7 is a real pid on a Linux VM only by accident.
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"script": "s", "step": "inference_2005",
                             "run_tag": "groves_b", "pid": os.getpid(),
                             "started_utc": "2026-09-07T00:00:00Z"}), encoding="utf-8")
    assert hw.read_marker(str(p)) == ("inference_2005", "groves_b")


def test_read_marker_dead_writer_is_blank_not_the_dead_step(tmp_path, monkeypatch):
    """SIGKILL leaves the marker behind — _clear_marker runs from finish() and nowhere
    else. Stamping the dead step onto every later sample is WORSE than blank: it bills
    the queue's VERIFY and the self-stop watchdog's idle minutes to a train that ended,
    on the tier the harvest calls exact. Patched because names.pid_alive short-circuits
    to True off-posix (os.kill(pid, 0) terminates the target on Windows)."""
    monkeypatch.setattr(hw, "pid_alive", lambda _p: False)
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"script": "s", "step": "train_2017", "run_tag": "",
                             "pid": 999_999,
                             "started_utc": "2026-09-07T00:00:00Z"}), encoding="utf-8")
    assert hw.read_marker(str(p)) == ("", "")


def test_read_marker_without_a_pid_field_still_reads(tmp_path, monkeypatch):
    """Presence-gated, so an older/hand-written marker is not silently discarded."""
    monkeypatch.setattr(hw, "pid_alive", lambda _p: False)
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"step": "tile_2019", "run_tag": "x"}), encoding="utf-8")
    assert hw.read_marker(str(p)) == ("tile_2019", "x")


def test_read_marker_missing_is_blank_not_an_error(tmp_path):
    """Absence is the NORMAL reading, not a failure: it means no step is open."""
    assert hw.read_marker(str(tmp_path / "nope.json")) == ("", "")


def test_read_marker_malformed_json_is_blank(tmp_path):
    """A sample can land mid-write on a box without atomic rename; a blank step is an
    honest 'unknown', a crashed logger loses the whole session's telemetry."""
    p = tmp_path / "m.json"
    p.write_text('{"step": "train_20', encoding="utf-8")
    assert hw.read_marker(str(p)) == ("", "")


# ── the schema never mixes ────────────────────────────────────────────────────

def test_header_is_v2_fifteen_columns():
    cols = hw.HEADER.strip().split(",")
    assert len(cols) == 15
    assert cols[-3:] == ["cpu_iowait_pct", "step", "run_tag"]


def test_resolve_out_absent_file_keeps_the_path(tmp_path):
    p = tmp_path / "hw_sess.csv"
    assert hw.resolve_out(str(p)) == str(p)


def test_resolve_out_v2_file_keeps_the_path(tmp_path):
    p = tmp_path / "hw_sess.csv"
    p.write_text(hw.HEADER + "2026-09-07T00:00:00Z,,,,,1.0\n", encoding="utf-8")
    assert hw.resolve_out(str(p)) == str(p)


def test_resolve_out_legacy_12col_file_forks_a_v2(tmp_path):
    legacy = ("ts_utc,gpu_util_pct,gpu_mem_util_pct,gpu_mem_used_mb,gpu_power_w,"
              "cpu_pct,disk_read_mb_s,disk_write_mb_s,net_rx_mb_s,net_tx_mb_s,"
              "disk_used_gb,disk_free_gb\n")
    assert len(legacy.strip().split(",")) == 12
    p = tmp_path / "hw_sess.csv"
    p.write_text(legacy + "2026-09-02T00:00:00Z,0,0,0,0,1.0,0,0,0,0,10,20\n",
                 encoding="utf-8")
    assert hw.resolve_out(str(p)) == str(tmp_path / "hw_sess_v2.csv")


def test_resolve_out_zero_byte_stub_keeps_the_path(tmp_path):
    """A logger that died before its first flush leaves 0 bytes; forking a _v2 for
    that splits one session across two files for nothing."""
    p = tmp_path / "hw_sess.csv"
    p.write_text("", encoding="utf-8")
    assert hw.resolve_out(str(p)) == str(p)


# ── the iowait arithmetic ─────────────────────────────────────────────────────

def test_cpu_iowait_pct_is_the_iowait_share_of_the_interval():
    # (total, idle_incl_iowait, iowait): 1000 ticks pass, 250 of them iowait
    prev, cur = (10_000, 4_000, 1_000), (11_000, 4_400, 1_250)
    assert hw.cpu_iowait_pct(prev, cur) == 25.0


def test_cpu_pct_arithmetic_is_unchanged_by_the_third_element():
    """v1 files must stay comparable: cpu_pct still reads [0] and [1] only, so busy
    remains total - idle - iowait. iowait is reported BESIDE it, never folded in."""
    prev, cur = (10_000, 4_000, 1_000), (11_000, 4_400, 1_250)
    assert hw.cpu_pct(prev, cur) == 60.0
    assert hw.cpu_pct(prev, cur) + hw.cpu_iowait_pct(prev, cur) < 100.0


def test_cpu_iowait_pct_zero_delta_is_blank_not_a_crash():
    assert hw.cpu_iowait_pct((5, 2, 1), (5, 2, 1)) == ""


# ── it imports where it has to ────────────────────────────────────────────────

def test_module_imports_on_windows_without_touching_proc():
    """Executed fresh from source, not read out of sys.modules — the point is that
    nothing at IMPORT time opens /proc/stat (which does not exist here) or reaches
    for the engine's environment. The logger is stdlib-only for exactly this reason."""
    import importlib.util

    src = SCRIPTS / "pipeline" / "vm_hwlogger.py"
    spec = importlib.util.spec_from_file_location("vm_hwlogger_fresh", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # raises if import-time work touches /proc
    assert mod.HEADER == hw.HEADER
