"""vm_hwlogger: the pure arithmetic, unit-tested without a VM. The samplers
read /proc (Linux-only, untestable here); what CAN silently lie are the delta
and rate computations, so those are pinned."""
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
