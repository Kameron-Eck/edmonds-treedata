"""One discovery rule for the run-outcome ledger, and it must not eat real data.

TWO FAILURES ARE BEING GUARDED HERE, AND THE SECOND IS THE SUBTLE ONE.

(1) Under-exclusion. On 2026-08-29 a test wrote a synthetic row into the shared status
CSV. It was "quarantined" by renaming to `train_queue_status.CONTAMINATED-BY-TEST-….csv`
— which escapes `train_queue_status_*.csv` but NOT `train_queue_status*.csv`, the
pattern five readers actually use. The rename quarantined nothing.

(2) OVER-exclusion, which the first fix caused. That fix used a deny-list of words a
human might rename a file to, matched as substrings. Against the real directory it
excluded ten files, of which one was the fixture:

    train_queue_status_queue_corrupt10/25/50_*.csv   the DAMAGE CURVE experiment
    train_queue_status_queue_golden_v2_*.csv         "golden" contains "old"

Nine legitimate campaigns would have vanished from the ledger — the same harm, caused by
the guard. Short words are substrings of real names; a lexical deny-list cannot be made
safe by lengthening it. The rule is shape-based instead.

Run:
  PYTHONUTF8=1 py -3.12 -m pytest qc/test_status_discovery.py -q
"""
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS / "pipeline"))

from phase4seg.names import STATUS_STEM, is_status_file, status_files  # noqa: E402


# ── (1) the fixture must be excluded ──────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "train_queue_status.CONTAMINATED-BY-TEST-20260829.csv",
    "train_queue_status.BACKUP.csv",
    "train_queue_status.2026-08-29.csv",
])
def test_a_dot_suffixed_file_is_not_a_status_file(name):
    """The discriminator is the SEPARATOR. The writer always joins with an underscore
    (`train_queue_status_{stem}_{ts}.csv`); a human renaming a file aside appends with a
    dot. That distinction is structural and needs no vocabulary — which is the whole
    lesson of failure (2) above."""
    assert not is_status_file(name), f"{name} would still be ingested"


# ── (2) real campaign names must survive, whatever words they contain ─────────

@pytest.mark.parametrize("name", [
    "train_queue_status.csv",                                        # legacy shared
    "train_queue_status_queue_nodeb_2009_20260828T145940Z.csv",
    "train_queue_status_queue_poc_a_seed.csv",
    "train_queue_status_queue_corrupt10_2009_20260829T010837Z.csv",  # damage curve
    "train_queue_status_queue_corrupt25_2009_seed.csv",
    "train_queue_status_queue_corrupt50_2009_20260829T032240Z.csv",
    "train_queue_status_queue_golden_v2_20260826T190350Z.csv",       # 'golden' ⊃ 'old'
    "train_queue_status_queue_golden_v2_seed.csv",
    # A queue file need not be named queue_*.yaml. The status name is
    # train_queue_status_{stem}_{ts}.csv for ANY stem — the `_queue_` infix every
    # existing file happens to carry is a naming coincidence, and a rule requiring it
    # excluded the pilot-slice shape below. Six existing tests caught that.
    "train_queue_status_pilot_2019_20260901T120000Z.csv",
    "train_queue_status_a.csv",
])
def test_real_campaign_files_are_kept(name):
    """These are the nine a lexical deny-list ate. A queue may be named anything."""
    assert is_status_file(name), f"{name} is a real campaign file and was excluded"


def test_the_word_corrupt_is_a_legitimate_queue_name():
    """Named explicitly because it reads like a quarantine marker and is not — it is
    the damage-curve experiment, which deliberately corrupts labels at 10/25/50%."""
    assert is_status_file("train_queue_status_queue_corrupt50_2009_seed.csv")


# ── unrelated files stay out ──────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "other_file.csv",
    "train_queue_status_queue_x_ts.csv.part.9f2a1b",   # temp: not a .csv tail
    "qc_indep_report.csv",
    "train_queue_statusfoo.csv",                        # no separator
])
def test_unrelated_files_are_excluded(name):
    assert not is_status_file(name)


def test_status_files_sorts_and_filters(tmp_path):
    for n in ("train_queue_status.csv",
              "train_queue_status_queue_b_seed.csv",
              "train_queue_status_queue_a_seed.csv",
              "train_queue_status.CONTAMINATED-BY-TEST-20260829.csv",
              "unrelated.csv"):
        (tmp_path / n).write_text("x", encoding="utf-8")
    got = [p.name for p in status_files(tmp_path)]
    assert got == ["train_queue_status.csv",
                   "train_queue_status_queue_a_seed.csv",
                   "train_queue_status_queue_b_seed.csv"], got


# ── every reader must use the one rule ────────────────────────────────────────

def test_no_reader_still_uses_the_bare_glob():
    """Five readers merged this ledger with `glob("train_queue_status*.csv")`. If one
    reverts, the fixture becomes ingestible again in that reader only — which is worse
    than uniformly wrong, because the ledger would then disagree with itself."""
    bad = []
    for rel in ("pipeline/phase4_train_queue.py",
                "pipeline/registry_from_manifests.py",
                "qc/pipeline_status.py",
                "qc/runtime_health.py",
                "qc/watch_queue.py"):
        src = (SCRIPTS / rel).read_text(encoding="utf-8")
        if f'glob("{STATUS_STEM}*.csv")' in src:
            bad.append(rel)
        if "status_files" not in src:
            bad.append(f"{rel} (does not import the shared rule)")
    assert not bad, "readers not using phase4seg.names.status_files: " + ", ".join(bad)


def test_names_module_stays_stdlib_only():
    """It is importable from the ORCHESTRATOR, which must keep running when the
    engine's environment is broken. A heavy import here would break that property and
    re-justify the hand-maintained twins this module exists to remove."""
    before = set(sys.modules)
    import importlib

    importlib.reload(importlib.import_module("phase4seg.names"))
    heavy = {"torch", "rasterio", "geopandas", "shapely", "sklearn",
             "numpy", "pandas", "fiona"}
    pulled = heavy & {m.split(".")[0] for m in set(sys.modules) - before}
    assert not pulled, f"names.py pulled heavy deps: {sorted(pulled)}"
