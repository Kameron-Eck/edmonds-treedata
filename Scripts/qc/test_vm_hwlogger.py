"""vm_hwlogger: the pure arithmetic, unit-tested without a VM. The samplers
read /proc (Linux-only, untestable here); what CAN silently lie are the delta
and rate computations, so those are pinned.

Since 2026-09-07 also the runtime-facts side (`hw_meta_{session}.json`), which
is the one part of the logger that runs OFF the VM in practice — it is written
before the sampling loop, from sources that mostly do not exist on Windows, so
its failure mode is the thing under test: every field blank, nothing raised,
the loop still reached. /proc, statvfs, os.uname and nvidia-smi are removed
explicitly in those tests rather than left to the platform, because this box
HAS an nvidia-smi (a local T2000) and a POSIX-absolute path here resolves
drive-relative, so "absent on Windows" is not a thing the environment can be
trusted to provide."""
import json
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS / "pipeline"))
import vm_hwlogger as hw  # noqa: E402


def test_cpu_pct_is_busy_fraction_of_delta():
    # 1000 ticks pass, 400 idle+iowait -> 60% busy
    assert hw.cpu_pct((10_000, 4_000), (11_000, 4_400)) == 60.0


def test_cpu_pct_zero_delta_is_blank_not_crash():
    assert hw.cpu_pct((5, 2), (5, 2)) == ""


def test_rate_mb_per_second():
    # 100 MB in 10 s -> 10 MB/s
    assert hw.rate_mb(0, 100_000_000, 10.0) == 10.0


def test_rate_mb_counter_reset_is_blank():
    """A rebooted counter (cur < prev) must read blank, never negative."""
    assert hw.rate_mb(1_000_000, 5, 5.0) == ""


def test_header_matches_row_arity():
    # 15 since v2 (2026-09-07): cpu_iowait_pct, step, run_tag appended.
    # The v2 column names are pinned in qc/test_hw_marker.py, not restated here.
    assert len(hw.HEADER.strip().split(",")) == 15


# ── runtime facts: hw_meta_{session}.json ─────────────────────────────────────

CONTRACT_FIELDS = {"session", "started_utc", "hostname", "vcpus", "ram_gb",
                   "disk_total_gb", "gpu_name", "gpu_mem_mb", "kernel", "python",
                   "marker_path"}


def _no_gpu(monkeypatch):
    """nvidia-smi absent, deterministically. This box has one; a CPU runtime does not,
    and it is the CPU runtime's behaviour that must be pinned."""
    def _boom(*_a, **_k):
        raise FileNotFoundError("nvidia-smi")
    monkeypatch.setattr(hw.subprocess, "run", _boom)


def test_runtime_facts_field_set_is_the_contract(monkeypatch):
    _no_gpu(monkeypatch)
    f = hw.runtime_facts("sess1", "/content/hw_step_marker.json", meminfo="nope")
    assert set(f) == CONTRACT_FIELDS
    assert f["session"] == "sess1"
    assert f["marker_path"] == "/content/hw_step_marker.json"
    assert f["python"] == sys.version.split()[0]
    assert len(f["started_utc"]) == 20 and f["started_utc"].endswith("Z")
    # These two answer on every platform, so they are the ones that must NOT be blank.
    assert isinstance(f["vcpus"], int) and f["vcpus"] > 0
    assert f["hostname"]


def test_runtime_facts_is_blank_where_the_platform_cannot_answer(monkeypatch, tmp_path):
    """No /proc, no statvfs, no os.uname, no nvidia-smi. Off posix the last three are
    AttributeError, not OSError — the exception the first version of this helper would
    not have caught — and the whole point is that the sampling loop is still reached."""
    _no_gpu(monkeypatch)
    monkeypatch.delattr(os, "statvfs", raising=False)
    monkeypatch.delattr(os, "uname", raising=False)

    f = hw.runtime_facts("s", "m.json", mount=str(tmp_path),
                         meminfo=str(tmp_path / "no_meminfo"))
    for k in ("ram_gb", "disk_total_gb", "gpu_name", "gpu_mem_mb", "kernel"):
        assert f[k] == "", f"{k} should be blank, not a guess"


def test_runtime_facts_reads_memtotal_in_gb(monkeypatch, tmp_path):
    """The kernel reports kB. 12,345,678 kB is 12.6 GB, not 12,345,678 of anything."""
    _no_gpu(monkeypatch)
    mi = tmp_path / "meminfo"
    mi.write_text("MemTotal:       12345678 kB\nMemFree:  1 kB\n", encoding="utf-8")
    f = hw.runtime_facts("s", "m.json", meminfo=str(mi))
    assert f["ram_gb"] == 12.6


def test_runtime_facts_takes_the_first_gpu_line(monkeypatch):
    """nvidia-smi prints one row per device; the fields are name and total MB."""
    class _R:
        stdout = "NVIDIA A100-SXM4-40GB, 40960\n"
    monkeypatch.setattr(hw.subprocess, "run", lambda *a, **k: _R())
    f = hw.runtime_facts("s", "m.json", meminfo="nope")
    assert f["gpu_name"] == "NVIDIA A100-SXM4-40GB"
    assert f["gpu_mem_mb"] == "40960"


def test_write_meta_writes_once_and_never_rewrites(tmp_path):
    """Write-once: these are start-of-life constants, and a rewrite could only move
    `started_utc` off the session's first sample."""
    p = tmp_path / "hw_meta_s.json"
    assert hw.write_meta(str(p), {"session": "s", "started_utc": "A"}) is True
    assert hw.write_meta(str(p), {"session": "s", "started_utc": "B"}) is False
    assert json.loads(p.read_text(encoding="utf-8"))["started_utc"] == "A"


def test_write_meta_into_a_missing_directory_is_false_not_a_raise(tmp_path):
    """Same standard as the marker: telemetry that cannot be written must not be able
    to stop the telemetry that can."""
    assert hw.write_meta(str(tmp_path / "gone" / "hw_meta_s.json"), {"a": 1}) is False


def test_write_meta_leaves_no_orphan_temp_when_the_publish_fails(tmp_path,
                                                                 monkeypatch):
    """Temp + os.replace, so a Drive blink mid-write cannot leave a truncated JSON that
    the write-once rule would then protect forever. When the replace itself fails,
    nothing sweeps the temp name and nothing reads it — so it is removed here."""
    def _boom(_src, _dst):
        raise OSError("replace failed")
    monkeypatch.setattr(os, "replace", _boom)

    p = tmp_path / "hw_meta_s.json"
    assert hw.write_meta(str(p), {"a": 1}) is False
    assert not p.exists()
    assert list(tmp_path.glob("*.tmp")) == []
