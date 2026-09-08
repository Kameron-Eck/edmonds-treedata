"""vm_hwlogger: the pure arithmetic, unit-tested without a VM. The samplers
read /proc (Linux-only, untestable here); what CAN silently lie are the delta
and rate computations, so those are pinned.

Since 2026-09-08 also THE SPOOL AND THE MIRROR, which is where the logger was losing a
quarter of its own measurements: sampling and the Drive append shared a thread, so every
append the mount was slow to accept stopped the clock (measured on the live pilots:
hw_spdg.csv 22.3 min of a 75.1 min span unsampled, hw_spdc1.csv 9.6 of 49.9). Four
properties replace that, and each fails silently if it is only asserted in a docstring:
the sampler never blocks on the publish, the publish is whole-file so a failure mid-write
leaves the old file untouched, a retried publish duplicates nothing, and a spool that
cannot be opened degrades to the old path instead of taking the logger down.

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
import threading
import types
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


# ── the spool and the mirror ──────────────────────────────────────────────────

ROW = "2026-09-08T00:00:0"          # a row prefix; the tests append their own tail


def _fake_samplers(monkeypatch):
    """/proc does not exist here and this box HAS an nvidia-smi, so the loop is fed
    deterministic counters instead. Without them every sample raises into the loop's
    blanket except and the row count under test would be zero for the wrong reason."""
    state = {"k": 0}

    def _ticks():
        state["k"] += 1
        k = state["k"]
        return (1000 * k, 400 * k, 100 * k)      # (total, idle_incl_iowait, iowait)

    monkeypatch.setattr(hw, "cpu_ticks", _ticks)
    monkeypatch.setattr(hw, "disk_bytes", lambda: (0, 0))
    monkeypatch.setattr(hw, "net_bytes", lambda: (0, 0))
    monkeypatch.setattr(hw, "gpu_row", lambda: ("", "", "", ""))
    monkeypatch.setattr(hw.shutil, "disk_usage",
                        lambda _p: types.SimpleNamespace(used=1e9, free=2e9))


def test_sampling_never_blocks_on_the_mirror(tmp_path, monkeypatch):
    """THE DEFECT, pinned. Sampling and the Drive write used to share a thread, so a
    slow append stopped the measurement: 22.3 min of hw_spdg.csv's 75.1 min span has no
    samples in it at all, in gaps one flush-cadence long.

    Here the mirror never returns until the test lets it, and the sampler must still
    finish its six samples. The assertion is on the THREAD, not on elapsed time: if the
    two were coupled again, `join` times out and `is_alive()` is True — a clean failure
    rather than a hung suite.
    """
    _fake_samplers(monkeypatch)
    local, out = tmp_path / "hw_s.local.csv", tmp_path / "hw_s.csv"
    local.write_text(hw.HEADER, encoding="utf-8")

    entered, release = threading.Event(), threading.Event()

    def _stuck(_local, _out):
        entered.set()
        release.wait(10)
        return True

    monkeypatch.setattr(hw, "mirror_once", _stuck)
    tick, lock = threading.Event(), threading.Lock()
    threading.Thread(target=hw._mirror_worker,
                     args=(str(local), str(out), tick, lock), daemon=True).start()

    fh = open(local, "a", encoding="utf-8", newline="")
    try:
        sampler = threading.Thread(
            target=hw.sample_loop,
            kwargs=dict(sink=hw._local_sink(fh), marker=str(tmp_path / "no_marker.json"),
                        interval=0.01, flush_every=1, flush=tick.set, max_samples=6))
        sampler.start()
        sampler.join(timeout=10)
        assert not sampler.is_alive(), "the sampler blocked on the Drive mirror"
        assert entered.wait(5), "the mirror never ran, so nothing was proved"
    finally:
        release.set()
        fh.close()

    lines = local.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 7, "header + one row per sample, written while Drive was stuck"
    assert lines[0] == hw.HEADER.strip()
    assert all(len(ln.split(",")) == 15 for ln in lines[1:])


def test_the_mirror_is_a_whole_file_replace_so_a_failure_leaves_out_untouched(
        tmp_path, monkeypatch):
    """The other half of the same defect. `writelines` onto the mount could fail HALF
    DONE and the old code then kept the whole buffer for the next attempt — hw_spdg.csv
    carries the result, a row whose `ts_utc` cell reads `200.5` and whose
    `gpu_mem_util_pct` cell reads `train_2017k`. A publish that fails mid-write must
    leave the previous file byte-identical and no `.part` behind."""
    local, out = tmp_path / "l.csv", tmp_path / "o.csv"
    local.write_text(hw.HEADER + f"{ROW}0,a\n", encoding="utf-8")
    assert hw.mirror_once(str(local), str(out)) is True
    published = out.read_bytes()

    local.write_text(hw.HEADER + f"{ROW}0,a\n{ROW}5,b\n", encoding="utf-8")
    real = hw._write_bytes

    def _half(path, data):
        real(path, data[:len(data) // 2])
        raise OSError("EIO halfway through")

    monkeypatch.setattr(hw, "_write_bytes", _half)
    assert hw.mirror_once(str(local), str(out)) is False
    assert out.read_bytes() == published, "a failed publish rewrote the published file"
    assert list(tmp_path.glob("*.part.*")) == [], "the temp was left on the mount"


def test_a_retried_mirror_publishes_no_duplicates(tmp_path, monkeypatch):
    """The dangerous sequence, in order: a mirror LANDS (row a), the spool grows (b), the
    next mirror FAILS, the spool grows again (c), the next one lands. The old appender's
    equivalent — keep the buffer, append it again — put the rows of the failed attempt on
    Drive twice. A whole-file publish cannot: `out` is the spool, whatever happened in
    between."""
    local, out = tmp_path / "l.csv", tmp_path / "o.csv"

    def _append(row):
        with open(local, "a", encoding="utf-8", newline="") as f:
            f.write(row)

    local.write_text(hw.HEADER, encoding="utf-8")
    _append(f"{ROW}0,a\n")
    assert hw.mirror_once(str(local), str(out)) is True     # a lands
    _append(f"{ROW}5,b\n")

    def _boom(_path, _data):
        raise OSError("mount blinked")

    monkeypatch.setattr(hw, "_write_bytes", _boom)
    assert hw.mirror_once(str(local), str(out)) is False    # b does not
    assert out.read_text(encoding="utf-8") == hw.HEADER + f"{ROW}0,a\n"

    monkeypatch.undo()
    _append(f"{ROW}9,c\n")
    assert hw.mirror_once(str(local), str(out)) is True     # a, b and c land, once each
    published = out.read_text(encoding="utf-8")
    assert published == local.read_text(encoding="utf-8")
    assert published == hw.HEADER + f"{ROW}0,a\n{ROW}5,b\n{ROW}9,c\n"
    assert published.count(f"{ROW}0,a") == 1


def test_the_mirror_cuts_at_the_last_complete_line(tmp_path):
    """The spool is flushed per row, so it can be read mid-write. Publishing those bytes
    would put a torn line on Drive by a different road than the one this replaced."""
    local, out = tmp_path / "l.csv", tmp_path / "o.csv"
    local.write_text(hw.HEADER + f"{ROW}0,a\n2026-09-08T00:00:0", encoding="utf-8")
    assert hw.mirror_once(str(local), str(out)) is True
    assert out.read_text(encoding="utf-8") == hw.HEADER + f"{ROW}0,a\n"


def test_the_spool_is_seeded_with_what_drive_already_holds(tmp_path):
    """A whole-file publish from a spool that began at the header would ERASE a restarted
    session. The seed is what makes the publish a superset."""
    out, local = tmp_path / "hw_s.csv", tmp_path / "hw_s.local.csv"
    out.write_text(hw.HEADER + f"{ROW}0,earlier\n", encoding="utf-8")

    fh = hw._open_local(str(local), str(out))
    assert fh is not None
    fh.write(f"{ROW}5,later\n")

    # THE EXIT ORDER, pinned: the spool handle is closed BEFORE the final publish reads
    # it. Interpreter teardown closes it last, so a `main` that let atexit run first
    # would publish a file whose final row was still in a Python buffer.
    fh.close()
    hw._final_mirror(str(local), str(out), threading.Lock())
    assert out.read_text(encoding="utf-8") == local.read_text(encoding="utf-8")
    assert out.read_text(encoding="utf-8") == (
        hw.HEADER + f"{ROW}0,earlier\n{ROW}5,later\n")


def test_an_absent_drive_file_seeds_the_spool_with_the_header(tmp_path):
    out, local = tmp_path / "hw_s.csv", tmp_path / "hw_s.local.csv"
    fh = hw._open_local(str(local), str(out))
    assert fh is not None
    fh.close()
    assert local.read_text(encoding="utf-8") == hw.HEADER


def test_an_unusable_local_dir_falls_back_instead_of_crashing(tmp_path, capsys):
    """Degraded telemetry beats none, and it must SAY so: a silent fallback would hide
    the fact that this session's gaps are the old defect, not the new path."""
    assert hw._open_local(str(tmp_path / "gone" / "l.csv"), str(tmp_path / "o.csv")) is None
    assert not (tmp_path / "gone").exists(), "the spool created its own directory"
    assert "no local spool" in capsys.readouterr().err


def test_an_unreadable_drive_file_falls_back_rather_than_seeding_empty(tmp_path,
                                                                      monkeypatch):
    """The dangerous case, and why this uses os.stat and not os.path.exists — the latter
    reports a mount blink as "absent", which here would mean a header-only spool
    published over a session's worth of samples. Only FileNotFoundError means absent;
    anything else falls back to appending, which cannot shorten a file."""
    out, local = tmp_path / "hw_s.csv", tmp_path / "hw_s.local.csv"
    out.write_text(hw.HEADER + f"{ROW}0,earlier\n", encoding="utf-8")
    real_stat = os.stat

    def _blink(path, *a, **k):
        if str(path) == str(out):
            raise PermissionError("EIO on the mount")
        return real_stat(path, *a, **k)

    monkeypatch.setattr(hw.os, "stat", _blink)
    assert hw._open_local(str(local), str(out)) is None
    monkeypatch.undo()
    assert out.read_text(encoding="utf-8") == hw.HEADER + f"{ROW}0,earlier\n"


def test_the_drive_appender_fallback_still_writes_header_and_rows(tmp_path):
    """The pre-2026-09-08 path, kept for the VM with no usable local disk."""
    out = tmp_path / "hw_s.csv"
    sink, flush = hw._drive_appender(str(out), need_header=True)
    sink(f"{ROW}0,a\n")
    flush()
    sink(f"{ROW}5,b\n")
    flush()
    assert out.read_text(encoding="utf-8") == hw.HEADER + f"{ROW}0,a\n{ROW}5,b\n"


def test_a_sampler_that_raises_costs_a_sample_not_the_logger(tmp_path, monkeypatch):
    """Unchanged contract, re-pinned on the refactored loop: the counters are read
    inside the try, and the PRIMING read is now too — off posix it raises, and a logger
    that dies before its first row has thrown away the session it exists to measure."""
    _fake_samplers(monkeypatch)
    calls = {"n": 0}
    good = hw.cpu_ticks

    def _sometimes():
        calls["n"] += 1
        if calls["n"] in (1, 3):                 # the priming read AND one sample
            raise OSError("/proc/stat vanished")
        return good()

    monkeypatch.setattr(hw, "cpu_ticks", _sometimes)
    rows = []
    assert hw.sample_loop(rows.append, str(tmp_path / "no_marker.json"),
                          interval=0.0, flush_every=100, max_samples=4) == 4
    assert 1 <= len(rows) < 4, "a failed read must cost its own sample and no other"
