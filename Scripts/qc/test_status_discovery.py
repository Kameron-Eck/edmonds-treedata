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


# ── the state vocabulary: readers must see everything the writer writes ───────
def _load(name, rel):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_every_reader_sees_every_state_the_writer_writes():
    """THE BLIND SPOT. The queue writes ten states meaning "the artifact you just paid
    GPU hours for is broken". watch_queue watched a hand-copied ELEVEN that omitted
    UNREADABLE, STALE_EVAL and SIZE_CHANGED; sector_campaign_loop watched SIX. All
    three omitted states are really written.

    So a run that died because its probability raster could not be opened produced
    bad_jobs == [] and runtime_health printed ALL_OK and exited 0. Not merely
    incomplete — confidently wrong, which is worse than having no watcher at all.
    """
    from phase4seg.names import VERIFY_HARD_FAIL

    readers = {
        "watch_queue.BAD": set(_load("wq", "qc/watch_queue.py").BAD),
        "sector_campaign_loop.HARD_FAIL":
            set(_load("scl", "qc/sector_campaign_loop.py").HARD_FAIL),
    }
    gaps = {n: sorted(VERIFY_HARD_FAIL - s) for n, s in readers.items()
            if VERIFY_HARD_FAIL - s}
    assert not gaps, (
        "these oversight readers cannot see states the queue really writes — a run "
        f"failing one of them would report healthy: {gaps}")


def test_runtime_health_inherits_the_same_set():
    """runtime_health imports watch_queue's set rather than keeping its own, which is
    the right shape — but only because that set is now the shared one."""
    src = (SCRIPTS / "qc" / "runtime_health.py").read_text(encoding="utf-8")
    assert "from watch_queue import" in src and "BAD" in src


def test_unverified_is_not_a_failure_and_not_a_pass():
    """"The check could not answer" is its own thing. Folding it into either bucket
    was D7: every exception landed on UNCHECKED, UNCHECKED was not a hard fail, and
    everything downstream treated not-hard-fail as a pass."""
    from phase4seg.names import BAD_STATES, VERIFY_HARD_FAIL, VERIFY_UNVERIFIED

    assert not (VERIFY_UNVERIFIED & BAD_STATES), "UNCHECKED must not abort a job"
    assert not (VERIFY_UNVERIFIED & VERIFY_HARD_FAIL)
    assert "UNCHECKED" in VERIFY_UNVERIFIED and "UNVERIFIED" in VERIFY_UNVERIFIED


def test_the_queue_uses_the_shared_set():
    import phase4_train_queue as _q
    from phase4seg.names import VERIFY_HARD_FAIL

    assert set(_q._VERIFY_HARD_FAIL) == set(VERIFY_HARD_FAIL)


# ── the launch filter and the row key ─────────────────────────────────────────

@pytest.mark.parametrize("name,stem,ts", [
    ("train_queue_status.csv", "", None),                      # legacy shared
    ("train_queue_status_queue_golden_v2_seed.csv",
     "queue_golden_v2_seed", None),                            # hand-written seed
    ("train_queue_status_queue_smooth_2009_20260829T135750Z.csv",
     "queue_smooth_2009", "20260829T135750Z"),
    ("train_queue_status_pilot_2019_20260901T120000Z.csv",
     "pilot_2019", "20260901T120000Z"),
])
def test_parse_status_name(name, stem, ts):
    from phase4seg.names import parse_status_name
    assert parse_status_name(name) == (stem, ts)


def test_a_pilot_shaped_launch_reaches_the_cost_report():
    """THE ONE WITH TEETH, and it points forward rather than back.

    cost_report discovered launches with glob("train_queue_status_queue_*_2*.csv") —
    the `_queue_` infix again, the same naming coincidence names.py already records
    rejecting. The overhaul's Stage 5 pilot queue is `pilot_2019.yaml`, so its status
    file is train_queue_status_pilot_2019_{ts}.csv, which that glob does not match.
    The pilot would have burned A100 hours and appeared in no cost report, with
    nothing raised — the failure mode is a silent absence, not an error.
    """
    import fnmatch
    from phase4seg.names import parse_status_name

    pilot = "train_queue_status_pilot_2019_20260901T120000Z.csv"
    assert not fnmatch.fnmatch(pilot, "train_queue_status_queue_*_2*.csv"), (
        "the old glob would have matched — this test no longer proves anything")
    assert parse_status_name(pilot)[1] is not None, (
        "the pilot's launch must be visible to cost accounting")


@pytest.mark.parametrize("name", [
    "train_queue_status.csv",
    "train_queue_status_queue_smooth_2009_seed.csv",
])
def test_seeds_and_the_legacy_file_are_not_launches(name):
    """A seed row records a step declared already-done; no GPU was burned. Counting it
    would inflate the bill for work nobody paid for. `ts is None` is the filter, and it
    is a fact about the file rather than a guess about its name."""
    from phase4seg.names import parse_status_name
    assert parse_status_name(name)[1] is None


def test_cost_report_and_the_dashboard_use_the_queue_row_key():
    """D8 fixed the queue's key from (job, step) to (job, year, tag, step) because a
    job id is a hand-written nickname reused across queue files. Two READERS kept the
    old 2-tuple and would collapse rows differing only in year or tag."""
    src_cost = (SCRIPTS / "pipeline" / "cost_report.py").read_text(encoding="utf-8")
    src_dash = (SCRIPTS / "qc" / "runtime_dashboard.py").read_text(encoding="utf-8")
    for name, src in (("cost_report", src_cost), ("runtime_dashboard", src_dash)):
        assert "job_key" in src, f"{name} does not use the shared row key"
        assert '[(r.get("job"), r.get("step"))]' not in src, (
            f"{name} still keys ledger rows on (job, step)")

    import phase4_train_queue as _q
    from phase4seg.names import job_key
    assert _q._job_key("2024", 2024, "a", "train") == job_key("2024", 2024, "a", "train")
    assert job_key("2024", 2019, "a", "train") != job_key("2024", 2024, "a", "train"), (
        "two queues may both call their work `2024`; the key must separate them")


# Every file that reads the ledger goes through the one discovery rule — or is named
# here WITH the reason it does not. An undocumented reader is exactly what this checks
# for: the rule is worth nothing if the next tool to touch the ledger writes its own glob.
_DISCOVERY_EXEMPT = {
    "names.py":            "the home of the rule",
    "conftest.py":         "names the lake paths a test must never write; reads none",
    "test_status_discovery.py": "this file",
    "test_queue_verify.py":     "constructs fixtures under tmp_path",
    "test_verified_write.py":   "constructs fixtures under tmp_path",
    "vm_heartbeat.py":     "VM-side beacon, stdlib-only by design; its _newest() is a "
                           "stem-scoped NEWEST-FILE selector, not a discovery rule — it "
                           "cannot pick up a file renamed aside because the rename "
                           "breaks the _{stem}_ match it requires",
}


def test_no_undocumented_reader_of_the_ledger():
    missing = []
    for root in ("pipeline", "qc"):
        for p in sorted((SCRIPTS / root).rglob("*.py")):
            if "_archive" in p.parts or "litwatch_scratch" in p.parts:
                continue
            src = p.read_text(encoding="utf-8", errors="replace")
            if "train_queue_status" not in src:
                continue
            if p.name in _DISCOVERY_EXEMPT:
                continue
            if "status_files" in src or "is_status_file" in src:
                continue
            missing.append(p.name)
    assert not missing, (
        "these read the run-outcome ledger without the one discovery rule — either "
        "import status_files/is_status_file, or add the file to _DISCOVERY_EXEMPT "
        f"with the reason: {missing}")


# ── locating a symbol without importing the engine ────────────────────────────

def test_the_locator_finds_symbols_across_modules():
    """Gates that assert something about the engine's TEXT were written as
    `(… / "core.py").read_text()`. core.py is 2,833 lines and a split is boarded as 3.5;
    every one of those gates would then pass VACUOUSLY or fail spuriously depending on
    which half the symbol landed in. A gate that silently stops checking reads exactly
    like a gate that passes, which is the failure this repo keeps finding."""
    from phase4seg.names import find_symbol_source

    pkg = SCRIPTS / "pipeline" / "phase4seg"
    assert find_symbol_source(pkg, "step_evaluate", "function")[0].name == "core.py"
    # the proof it is not just reading core.py under another name:
    assert find_symbol_source(pkg, "step_labels", "function")[0].name == "labels.py"
    assert find_symbol_source(pkg, "no_such_symbol_anywhere") is None


def test_the_locator_refuses_an_ambiguous_name_instead_of_guessing():
    """Taking the first match would be a silent wrong answer — the same shape as the
    status-file glob, the ledger row key and the eval-report join, all fixed this week
    because they answered confidently from an under-specified key."""
    from phase4seg.names import AmbiguousSymbol, find_symbol_source

    pkg = SCRIPTS / "pipeline" / "phase4seg"
    with pytest.raises(AmbiguousSymbol):
        find_symbol_source(pkg, "__init__")     # defined in common.py and core.py


def test_within_disambiguates_a_method():
    """How __getitem__ is reached: name the class, not the file."""
    from phase4seg.names import symbol_body

    pkg = SCRIPTS / "pipeline" / "phase4seg"
    body = symbol_body(pkg, "__getitem__", "function", within="SemanticDataset")
    assert body and "def __getitem__" in body and "tile_name" in body


def test_no_gate_still_hardcodes_the_engine_file_it_checks():
    """The coupling this replaces. Four tests read core.py by path; three were written
    the same day. Keeping the ban is what stops the next one being added."""
    bad = []
    for p in sorted((SCRIPTS / "qc").glob("test_*.py")):
        if p.name == Path(__file__).name:
            continue                      # this file NAMES the banned shape to ban it
        src = p.read_text(encoding="utf-8", errors="replace")
        if '"core.py"' in src and "read_text" in src:
            bad.append(p.name)
    assert not bad, (
        "these assert on the engine's text via a hardcoded core.py path — use "
        "names.find_symbol_source / symbol_body so the check follows the symbol: " +
        ", ".join(bad))
