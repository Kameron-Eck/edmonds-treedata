"""A number in the run registry must belong to the run it sits next to.

WHAT WAS FOUND, 2026-08-30, by running the generator the overhaul plan says nothing ever
invokes. `run_registry.csv` was 146 rows behind; regenerating it printed:

    20260829T155419Z_2009_nodecW_train              held-out IoU 0.6959, AUROC 0.9082 [rgb+chm]
    20260829T164103Z_2009_rgb3_ep60_s1234_train     held-out IoU 0.6959, AUROC 0.9082 [rgb+chm]
    20260829T171355Z_2009_rgb3_nodeb_twin_train     held-out IoU 0.6959, AUROC 0.9082 [rgb+chm]

Three different arms — different seeds, different queues, different GPUs — reporting
byte-identical metrics to four decimals, and two of them named `rgb3` while the bracket
says `rgb+chm`. The contradiction was visible on the line itself.

THE CAUSE. `held_out_metrics(year, tag)` accepted `tag` and never used it. It filtered on
`year == year and scope == OVERALL` and took the last match. There is only ever one such
row: the eval report's columns are

    year, gsd_cm, tier, channels, eval_scope, scope, site, <metrics...>

and NOT ONE identifies a run. `step_evaluate` keys rows on (label, channels, scope, site)
and drops superseded ones, so a year holds one OVERALL row however many arms trained on
it. The registry could not have attributed correctly; the signature promised something
the data cannot supply.

WHY THE NUMBER IS KEPT AND RELABELLED RATHER THAN DELETED. Most years carry one arm, and
for those the newest row genuinely is that run's. Blanking every train/evaluate metric
would delete real information to avoid a labelling problem. So it is stamped as a
year-level fact — the same move STATUS.md makes for its lake section.

WHAT THE REAL FIX IS. Attribution can only be created at WRITE time: step_evaluate has to
stamp `run_tag` into each eval row. That is a separate engine change (14 files read this
report). The test below is the tripwire: the moment a run-identity column appears, it
fails and says to upgrade the registry to real per-run attribution. The relabelling
cannot outlive the reason for it.

Run:
  PYTHONUTF8=1 py -3.12 -m pytest qc/test_registry_attribution.py -q
"""
import csv
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS / "pipeline"))

import registry_from_manifests as R  # noqa: E402


def _eval_header():
    p = R.EVAL_REPORT
    if not p.exists():
        pytest.skip(f"eval report not reachable ({p}) — lake not mounted")
    with open(p, encoding="utf-8", newline="") as fh:
        return next(csv.reader(fh))


def test_held_out_metrics_does_not_take_an_argument_it_ignores():
    """The dead `tag` parameter WAS the lie — a signature that reads as per-run
    attribution. Removing it is not cosmetic: it is what stops the next caller from
    believing the number is keyed on the arm."""
    import inspect
    params = list(inspect.signature(R.held_out_metrics).parameters)
    assert params == ["year"], (
        f"held_out_metrics{tuple(params)} — an argument it does not use is a promise "
        "the eval report cannot keep")


def test_the_metric_is_labelled_as_a_year_fact():
    """A reader must be able to tell, on the line, that this is not the run's own
    number. Three 2009 arms carried identical metrics with nothing saying so."""
    out = R.held_out_metrics("2009")
    if not out:
        pytest.skip("no 2009 OVERALL row in the eval report")
    assert "year-eval" in out and "no run identity" in out, (
        f"the metric does not disclose that it is year-level, not run-level: {out!r}")


def test_the_tripwire_for_when_the_writer_learns_to_stamp_runs():
    """FAILS ON PURPOSE once step_evaluate stamps run_tag/run_id into the eval report.
    At that moment the registry should do a real per-run join — the way honest_metrics
    already joins on the `prob` raster — and this whole relabelling should go."""
    header = set(_eval_header())
    present = header & set(R._EVAL_RUN_ID_COLS)
    assert not present, (
        f"the eval report now carries run identity ({sorted(present)}) — "
        "held_out_metrics can and should join per-run now, like honest_metrics does. "
        "Upgrade it and delete the year-level relabelling (and this test).")


def test_honest_metrics_is_the_contrast_and_still_joins_per_run():
    """The counter-example lives six lines below the defect in the same file. It matches
    on `prob` — the raster THIS run produced — and returns "" when the run's raster has
    not been scored. It was written that way because a near-miss had already happened:
    a 2017 citywide run would otherwise have inherited an earlier off-recipe number."""
    import inspect
    src = inspect.getsource(R.honest_metrics)
    assert 'edmonds_canopy_prob_' in src and '"prob"' in src, (
        "honest_metrics no longer joins on the scored raster — if it has fallen back to "
        "newest-row-wins, it has the defect held_out_metrics just had")
    assert 'return ""' in src, (
        "honest_metrics must still decline to report when this run's raster is unscored")


def test_a_year_with_two_arms_cannot_be_told_apart_yet():
    """States the limitation as a fact rather than a hope. 2009 has several arms and one
    OVERALL row; that IS the ceiling on attribution until the writer changes."""
    rows = [r for r in R._rows(R.EVAL_REPORT)
            if r.get("year") == "2009" and r.get("scope") == "OVERALL"]
    if not rows:
        pytest.skip("no 2009 OVERALL rows")
    assert len(rows) <= 1, (
        "more than one 2009 OVERALL row now exists — if they are distinguishable, "
        "attribution is possible and held_out_metrics should use it")
