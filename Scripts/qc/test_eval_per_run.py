"""The per-run eval file (2026-09-09) — the write side, and its place in step_evaluate.

THE CLOBBER. `phase4/eval/semantic_eval_report.csv` is one shared lake file that every
evaluate step read-modify-writes through rclone's async upload cache. Two runtimes
evaluating one year minutes apart each read a copy lacking the other's rows and the
last upload wins: bb18_2006s_base's rows vanished from both the live report and the
superseded archive at 05:44Z while bb50_2006s_base's survived
(experiments/backbone_sweep.yaml extra.cross_vm_eval_report_clobber).

What these tests hold: core.py::_write_per_run_eval writes THIS run's rows — every
row, every column — to `phase4/eval/runs/semantic_eval_<run_id>.csv`, once; and
step_evaluate calls it BEFORE it reads the shared report, so nothing that happens to
the shared file afterwards can take the metrics with it. The read side (VERIFY:evaluate
accepting the file, the instrument counting it) is gated in qc/test_queue_verify.py
and qc/test_eval_rows_from_logs.py.

No lake: EVAL_DIR is patched to tmp_path. No torch: the helper needs pandas only, and
the ordering claim is read from the source, not run.

Run:  PYTHONUTF8=1 py -3.12 -m pytest qc/test_eval_per_run.py -q
"""
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]

pd = pytest.importorskip("pandas")
core = pytest.importorskip("phase4seg.core")
from phase4seg import config, names   # noqa: E402


def _rows():
    base = dict(year="2006s", gsd_cm=45, tier="coarse", channels="rgb",
                eval_scope="held-out test", run_tag="bb18_2006s_base",
                run_id="20260909T054202Z_2006s_bb18_2006s_base_evaluate",
                written_utc="2026-09-09T05:44:10Z", encoder="resnet18", warm_start="")
    return pd.DataFrame([
        dict(base, scope="site", site="city", iou=0.29),
        dict(base, scope="site", site="park", iou=0.31),
        dict(base, scope="OVERALL", site="ALL", iou=0.2939, op_thresh=0.417),
    ])


@pytest.fixture
def lake(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "EVAL_DIR", tmp_path / "eval")
    monkeypatch.setattr(config, "RUN_ID", "20260909T054202Z_2006s_bb18_2006s_base_evaluate")
    monkeypatch.setattr(config, "RUN_TAG", "bb18_2006s_base")
    return tmp_path / "eval"


def test_every_row_and_column_lands_in_the_per_run_file(lake):
    new = _rows()
    out = core._write_per_run_eval(new, "2006s")
    assert out == lake / names.EVAL_RUNS_DIRNAME / names.eval_run_name(config.RUN_ID)
    got = pd.read_csv(out)
    assert list(got.columns) == list(new.columns)
    assert len(got) == 3 and (got["scope"] == "OVERALL").sum() == 1
    assert got.loc[got["scope"] == "OVERALL", "iou"].iloc[0] == pytest.approx(0.2939)
    assert set(got["run_id"]) == {config.RUN_ID}
    # nothing else was written — in particular NOT the shared report
    assert sorted(p.name for p in lake.rglob("*.csv")) == [out.name]


def test_the_per_run_file_is_write_once(lake, capsys):
    out = core._write_per_run_eval(_rows(), "2006s")
    first = out.read_bytes()
    other = _rows()
    other["iou"] = 0.0
    assert core._write_per_run_eval(other, "2006s") == out
    assert out.read_bytes() == first, "a second write under the same run_id overwrote it"
    assert "already exists" in capsys.readouterr().out


def test_an_unrecorded_run_still_gets_its_own_file_with_the_tag_in_its_name(
        lake, monkeypatch):
    """config.RUN_ID is '' when the engine is driven directly (no manifest). The
    file must still be one-per-process, and its name must still carry `_<tag>_` —
    that is what queue_verify's filename filter keys on."""
    monkeypatch.setattr(config, "RUN_ID", "")
    out = core._write_per_run_eval(_rows(), "2006s")
    assert out.name.startswith(names.EVAL_RUN_PREFIX + "unrecorded_")
    assert "_2006s_bb18_2006s_base_" in out.name
    assert names.eval_run_files(out.parent, "bb18_2006s_base") == [out]
    assert names.eval_run_files(out.parent, "some_other_arm") == []


def test_step_evaluate_writes_the_per_run_file_before_it_reads_the_shared_report():
    """The ordering IS the fix: written first, the rows survive whatever the shared
    report does next. Read from the source — step_evaluate needs a GPU to run."""
    body = names.symbol_body(SCRIPTS / "pipeline" / "phase4seg", "step_evaluate")
    assert body, "step_evaluate not found"
    i_write = body.find("_write_per_run_eval(new, label)")
    i_report = body.find("if EVAL_CSV.exists():")
    assert 0 < i_write < i_report, \
        "the per-run file must be written BEFORE the shared report is read"
    assert body.count("_write_per_run_eval(") == 1
