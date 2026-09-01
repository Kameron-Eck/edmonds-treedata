"""A number in the run registry must belong to the run it sits next to.

WHAT WAS FOUND, 2026-08-30, by running the generator the overhaul plan says nothing ever
invokes. `run_registry.csv` was 146 rows behind; regenerating it printed:

    ..._2009_nodecW_train            held-out IoU 0.6959, AUROC 0.9082, AP 0.8299 [rgb+chm]
    ..._2009_rgb3_ep60_s1234_train   held-out IoU 0.6959, AUROC 0.9082, AP 0.8299 [rgb+chm]
    ..._2009_rgb3_nodeb_twin_train   held-out IoU 0.6959, AUROC 0.9082, AP 0.8299 [rgb+chm]

Three different arms — different seeds, queues and GPUs — byte-identical to four decimals,
and two named `rgb3` while the bracket says `rgb+chm`. The contradiction was on the line.

CAUSE: `held_out_metrics(year, tag)` accepted `tag` and never used it. And it is worse
than a labelling slip — `step_train` writes no eval rows, and the registry holds 46 train
steps against 9 evaluate steps, so most of those train rows displayed an evaluation that
had never been run for that arm at all.

TWO ERAS, AND THE FUNCTION MUST SPAN BOTH.
  · Pre-D6 rows carry no run identity. `semantic_eval_report.csv`'s columns are
    year, gsd_cm, tier, channels, eval_scope, scope, site and the metrics — not one names
    a run. The number is kept (most years have one arm, and for those it IS that run's)
    and stamped as a year-level fact.
  · Post-D6, `step_evaluate` stamps run_tag / run_id / written_utc on every row it writes.
    That landed 2026-08-29, AFTER the last evaluate ran, so the live report still has none
    of them — the columns appear on the first evaluate step that runs from here. The join
    is then exact, and an arm with no eval row of its own gets NOTHING rather than a
    borrowed number.

These tests pin both eras against synthetic reports, so neither path waits on a Colab run
to be covered.

Run:
  PYTHONUTF8=1 py -3.12 -m pytest qc/test_registry_attribution.py -q
"""
import csv
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent

import registry_from_manifests as R  # noqa: E402

_COLS = ["year", "channels", "scope", "site", "iou", "auroc"]


def _write(path, rows, cols=_COLS):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


@pytest.fixture
def report(tmp_path, monkeypatch):
    """Point the module at synthetic reports so both eras are testable locally."""
    main = tmp_path / "semantic_eval_report.csv"
    sup = tmp_path / "semantic_eval_report_superseded.csv"
    monkeypatch.setattr(R, "EVAL_REPORT", main)
    monkeypatch.setattr(R, "EVAL_SUPERSEDED", sup)
    return main, sup


def _row(year="2009", tag=None, ch="rgb", iou="0.5", scope="OVERALL"):
    r = {"year": year, "channels": ch, "scope": scope, "site": "ALL",
         "iou": iou, "auroc": "0.9"}
    if tag is not None:
        r["run_tag"] = tag
    return r


# ── era 1: no run identity ────────────────────────────────────────────────────

def test_without_run_identity_the_number_is_labelled_as_a_year_fact(report):
    """A reader must be able to tell, on the line, that this is not the run's own
    number. Three 2009 arms carried identical metrics with nothing saying so."""
    main, _ = report
    _write(main, [_row(iou="0.6959")])
    out = R.held_out_metrics("2009", "any_arm")
    assert out.startswith("year-eval "), out
    assert "cannot be attributed" in out or "none can be attributed" in out, out
    assert "0.6959" in out


def test_without_run_identity_the_tag_changes_nothing(report):
    """Stated as a fact rather than left implicit: pre-D6 the tag genuinely cannot
    select a row, so two arms see the same string — and it says so."""
    main, _ = report
    _write(main, [_row(iou="0.6959")])
    assert R.held_out_metrics("2009", "arm_a") == R.held_out_metrics("2009", "arm_b")


# ── era 2: run_tag stamped (D6) ───────────────────────────────────────────────

_COLS_T = _COLS + ["run_tag"]


def test_with_run_identity_each_arm_gets_its_own_number(report):
    """The whole point. Once step_evaluate stamps run_tag, the join is exact."""
    main, _ = report
    _write(main, [_row(tag="arm_a", iou="0.61"), _row(tag="arm_b", iou="0.72")],
           cols=_COLS_T)
    a, b = R.held_out_metrics("2009", "arm_a"), R.held_out_metrics("2009", "arm_b")
    assert a.startswith("held-out ") and "0.61" in a, a
    assert b.startswith("held-out ") and "0.72" in b, b
    assert "year-eval" not in a and "0.72" not in a


def test_an_arm_with_no_eval_row_gets_nothing_rather_than_a_borrowed_one(report):
    """THE DEFECT, INVERTED. 46 train steps against 9 evaluate steps: most arms have no
    evaluation of their own, and showing them someone else's is exactly what went wrong.
    Silence is the correct output."""
    main, _ = report
    _write(main, [_row(tag="arm_a", iou="0.61")], cols=_COLS_T)
    assert R.held_out_metrics("2009", "arm_b") == ""


def test_a_superseded_row_still_belongs_to_the_arm_that_measured_it(report):
    """step_evaluate keys replacement on (year, channels) and archives what it displaces,
    precisely so a paired experiment's first arm is not erased. An arm whose row was
    superseded still measured what it measured."""
    main, sup = report
    _write(main, [_row(tag="arm_b", iou="0.72")], cols=_COLS_T)
    _write(sup, [_row(tag="arm_a", iou="0.61")], cols=_COLS_T)
    out = R.held_out_metrics("2009", "arm_a")
    assert out.startswith("held-out ") and "0.61" in out, out


def test_only_overall_rows_are_used(report):
    """Per-site rows share the year and tag; taking the last row regardless of scope
    would headline one site's number as the arm's."""
    main, _ = report
    _write(main, [_row(tag="a", iou="0.61"),
                  _row(tag="a", iou="0.99", scope="site")], cols=_COLS_T)
    assert "0.61" in R.held_out_metrics("2009", "a")


def test_a_year_with_no_rows_reports_nothing(report):
    main, _ = report
    _write(main, [_row(year="2016", tag="a")], cols=_COLS_T)
    assert R.held_out_metrics("2009", "a") == ""


# ── the contrast case, unchanged ──────────────────────────────────────────────

def test_honest_metrics_still_joins_per_run():
    """The pattern held_out_metrics now follows, and it was six lines away the whole
    time. honest_metrics matches on `prob` — the raster THIS run produced — and returns
    "" when the run's raster is unscored. It was written that way because a near-miss had
    already happened: a 2017 citywide run would otherwise have inherited an earlier
    off-recipe number."""
    import inspect
    src = inspect.getsource(R.honest_metrics)
    assert "edmonds_canopy_prob_" in src and '"prob"' in src, (
        "honest_metrics no longer joins on the scored raster — if it has fallen back to "
        "newest-row-wins, it has the defect held_out_metrics just had")
    assert 'return ""' in src, (
        "honest_metrics must still decline to report when this run's raster is unscored")


def test_the_writer_really_does_stamp_run_identity():
    """The post-D6 path above is only reachable because step_evaluate stamps these. If
    that stamping is ever removed, every arm silently falls back to the year-level label
    and this file's second half stops testing anything real."""
    from phase4seg.names import symbol_body
    # By symbol, not by path — see names.py::find_symbol_source. Importing the engine
    # would pull torch, which CI deliberately does not have.
    body = symbol_body(SCRIPTS / "pipeline" / "phase4seg", "step_evaluate", "function")
    assert body, "step_evaluate not found in the engine package"
    for col in R._EVAL_RUN_ID_COLS:
        assert f'new["{col}"]' in body, (
            f"step_evaluate no longer stamps {col} into the eval report — per-run "
            "attribution in the registry is unreachable without it")
