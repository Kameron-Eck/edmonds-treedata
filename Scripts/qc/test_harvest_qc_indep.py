"""The honest-results harvester: copies exactly the right files, and its three gates fire.

Each gate is exercised on a KNOWN-BAD input (a shrunken lake, a re-shaped header, a
lineage with two live generations) — a gate that has never fired is not known to work.
Everything runs in tmp_path; conftest blocks the lake regardless.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from instruments import harvest_qc_indep as h

COLS = list(h.REPORT_COLS)


def _row(year, arm, ts, live="1", ref="ccap_2021_hires_lc.tif", canopy_def="forest_wetland",
         aoi=""):
    r = {c: "" for c in COLS}
    r.update(year=year, ref=ref, prob=f"edmonds_canopy_prob_{year}_{arm}.tif",
             canopy_def=canopy_def, thresh="0.5", recall="0.7", precision="0.8",
             tp="1", fn="1", fp="1", primary="1", live=live, run_tag=arm, aoi=aoi, ts=ts)
    return r


def _write_report(path: Path, rows, cols=COLS):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in cols})
    path.write_text(buf.getvalue(), encoding="utf-8")


@pytest.fixture
def lake(tmp_path):
    d = tmp_path / "lake"
    d.mkdir()
    _write_report(d / h.REPORT, [_row("2019", "trend8_2019", "t1"),
                                 _row("2020", "of_2020", "t2")])
    (d / "qc_indep_2019.txt").write_text("breakout 2019", encoding="utf-8")
    (d / "qc_indep_surfaces_2019.csv").write_text("group,px\ngrass,1\n", encoding="utf-8")
    (d / "qc_indep_2023n.txt.CONTAMINATED-2022N-BYTECOPY.20260905").write_text("x")
    (d / "qc_indep_report.csv.bak_20260817").write_text("x")
    (d / "qc_indep_sweep_2019_trend8_2019_ccap_2021_hires_lc.csv").write_text("k\n1\n")
    return d


@pytest.fixture
def tracked(tmp_path):
    d = tmp_path / "tracked"
    d.mkdir()
    return d


def test_copies_report_and_sidecars_only(lake, tracked, capsys):
    assert h.harvest(lake, tracked) == 0
    names = sorted(p.name for p in tracked.iterdir())
    assert names == ["qc_indep_2019.txt", "qc_indep_report.csv", "qc_indep_surfaces_2019.csv"]
    assert (tracked / h.REPORT).read_bytes() == (lake / h.REPORT).read_bytes()
    out = capsys.readouterr().out
    assert "lake 2 rows (2 live) · tracked 0 rows · +2" in out


def test_second_run_is_a_noop(lake, tracked, capsys):
    h.harvest(lake, tracked)
    capsys.readouterr()
    assert h.harvest(lake, tracked) == 0
    assert "already matches the lake" in capsys.readouterr().out


def test_dry_run_writes_nothing(lake, tracked):
    assert h.harvest(lake, tracked, dry_run=True) == 0
    assert list(tracked.iterdir()) == []


def test_shrink_gate_fires_and_override_works(lake, tracked, capsys):
    h.harvest(lake, tracked)
    _write_report(lake / h.REPORT, [_row("2019", "trend8_2019", "t1")])  # the lake lost a row
    assert h.harvest(lake, tracked) == 2
    assert "REFUSED" in capsys.readouterr().out
    assert len(list(csv.DictReader((tracked / h.REPORT).open(encoding="utf-8")))) == 2
    assert h.harvest(lake, tracked, allow_shrink=True) == 0
    assert len(list(csv.DictReader((tracked / h.REPORT).open(encoding="utf-8")))) == 1


def test_contract_gate_fires_on_reshaped_header(lake, tracked, capsys):
    _write_report(lake / h.REPORT, [_row("2019", "trend8_2019", "t1")], cols=COLS + ["extra"])
    assert h.harvest(lake, tracked) == 2
    assert "SCHEMAS contract" in capsys.readouterr().out
    assert not (tracked / h.REPORT).exists()


def test_lineage_conflict_is_reported_not_fatal(lake, tracked, capsys):
    rows = [_row("2019", "trend8_2019", "t1"), _row("2019", "trend8_2019", "t9"),
            _row("2019", "sectors_v1", "t1"),            # another arm: its own lineage
            _row("2019", "trend8_2019", "t1", aoi="sample-test"),  # aoi: its own lineage
            _row("2019", "trend8_2019", "t0", live="0")]  # history never counts
    _write_report(lake / h.REPORT, rows)
    assert h.live_lineage_conflicts(rows) == [("2019", "ccap_2021_hires_lc.tif",
                                               "trend8_2019", "")]
    assert h.harvest(lake, tracked) == 0
    assert "1 live lineage(s) carry two timestamps" in capsys.readouterr().out


def test_tracked_orphan_is_reported_and_kept(lake, tracked, capsys):
    (tracked / "qc_indep_2023n.txt").write_text("quarantined lake-side", encoding="utf-8")
    assert h.harvest(lake, tracked) == 0
    out = capsys.readouterr().out
    assert "1 tracked file(s) have no lake counterpart" in out and "qc_indep_2023n.txt" in out
    assert (tracked / "qc_indep_2023n.txt").exists()


def test_main_cli_with_explicit_dirs(lake, tracked):
    assert h.main(["--lake-dir", str(lake), "--tracked-dir", str(tracked)]) == 0
    assert (tracked / h.REPORT).exists()


def test_main_reports_unreachable_lake(tmp_path):
    assert h.main(["--lake-dir", str(tmp_path / "nowhere"), "--tracked-dir", str(tmp_path)]) == 3
