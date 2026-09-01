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
    # REASON REWRITTEN 2026-08-31. The previous one was FALSE: it said _newest "cannot
    # pick up a file renamed aside because the rename breaks the _{stem}_ match it
    # requires". That match is CONDITIONAL — when the queue-process regex finds nothing,
    # stem is None, the filter is skipped, and all 77 candidates are admitted including
    # the contaminated file. vm_heartbeat now carries its own _is_status_name, kept local
    # because the beacon must run when the engine package is unimportable, and proven
    # equivalent by test_vm_heartbeat_agrees_with_the_shared_rule.
    "vm_heartbeat.py":     "VM-side beacon; must survive an unimportable engine package, "
                           "so it keeps a LOCAL copy of the rule — a deliberate twin, "
                           "gated for equivalence rather than trusted",
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


# ── one queue's files: its launches and its seed, nothing else ────────────────

@pytest.mark.parametrize("stem,name,want", [
    # the ONE genuine cross-queue collision on the real lake
    ("queue_noise_2021s", "train_queue_status_queue_noise_2021s_b_20260826T185246Z.csv", False),
    ("queue_noise_2021s", "train_queue_status_queue_noise_2021s_20260826T142501Z.csv", True),
    # the 22 that a naive stem-equality fix would have thrown away
    ("queue_smooth_2009", "train_queue_status_queue_smooth_2009_seed.csv", True),
    ("queue_sectors_base2020", "train_queue_status_queue_sectors_base2020_seed.csv", True),
    ("pilot_2019_fine", "train_queue_status_pilot_2019_fine_20260831T004442Z.csv", True),
])
def test_stem_selection_keeps_seeds_and_rejects_other_queues(tmp_path, stem, name, want):
    """PREFIX MATCHING WAS THE BUG AND STEM EQUALITY WOULD HAVE BEEN THE OVERCORRECTION.

    Callers globbed `train_queue_status_{stem}_*.csv`. Against the real lake that matched
    23 files belonging to some OTHER stem — but 22 of those are the queue's own `_seed`
    file and are wanted: sector_campaign_loop writes a 24-row seed whose entire job is to
    stop the queue re-running finished base-year fine-tunes, so dropping it makes completed
    work look un-run and costs GPU hours. Exactly one is a real collision, and it is the
    one this rule has to reject.
    """
    from phase4seg.names import status_files_for_stem
    (tmp_path / name).write_text("job,year,tag,step,state\n", encoding="utf-8")
    got = [p.name for p in status_files_for_stem(tmp_path, stem)]
    assert (name in got) is want, f"{name} for stem {stem}: got {got}"


def test_the_writer_and_the_parser_round_trip():
    """The formatter did not exist: phase4_train_queue hand-built the f-string while
    names.py owned the parser, and no test constructed a name through the writer — so the
    two could drift apart silently."""
    from phase4seg.names import parse_status_name, status_out_name

    for stem, ts in (("pilot_2019_fine", "20260831T004442Z"),
                     ("queue_smooth_2009", "20260829T135750Z"),
                     ("a", "20260101T000000Z")):
        assert parse_status_name(status_out_name(stem, ts)) == (stem, ts)


def test_the_queue_builds_its_status_name_through_the_formatter():
    src = (SCRIPTS / "pipeline" / "phase4_train_queue.py").read_text(encoding="utf-8")
    assert "status_out_name(" in src, "the writer no longer uses the shared formatter"
    assert 'f"train_queue_status_{' not in src, "the hand-built f-string is back"


def test_vm_heartbeat_agrees_with_the_shared_rule():
    """vm_heartbeat keeps its OWN selector — deliberately, because it is the VM-side
    beacon and must not depend on the engine package being importable. That is a twin, so
    it is PROVEN equivalent here instead of trusted.

    The exemption's previous wording claimed _newest "cannot pick up a file renamed aside
    because the rename breaks the _{stem}_ match it requires". That was FALSE: the stem
    filter is conditional (`if stem and ...`), and when the queue-process regex finds no
    match, stem is None, the filter is off, and all 77 candidates are admitted — including
    train_queue_status.CONTAMINATED-BY-TEST-20260829.csv. A gate whose stated reason is
    wrong is worse than no gate, because it stops anyone looking.
    """
    import importlib.util

    from phase4seg.names import is_status_file

    spec = importlib.util.spec_from_file_location(
        "vmhb", SCRIPTS / "pipeline" / "vm_heartbeat.py")
    vm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vm)

    corpus = [
        "train_queue_status.csv",
        "train_queue_status_queue_smooth_2009_seed.csv",
        "train_queue_status_pilot_2019_fine_20260831T004442Z.csv",
        "train_queue_status.CONTAMINATED-BY-TEST-20260829.csv",
        "train_queue_status.BACKUP.csv",
        "train_queue_statusfoo.csv",
        "unrelated.csv",
    ]
    disagree = [n for n in corpus
                if bool(vm._is_status_name(n)) != bool(is_status_file(n))]
    assert not disagree, (
        "vm_heartbeat's local status-name rule disagrees with names.is_status_file on "
        f"{disagree} — the twin has drifted")


# ── the one argv filter ───────────────────────────────────────────────────────

@pytest.mark.parametrize("argv,want", [
    (["--aoi", "custom.json"], ["--aoi", "custom.json"]),   # space form: value KEPT
    (["--aoi=custom.json"], ["--aoi=custom.json"]),         # EQUALS form: the silent bug
    (["-f", "/x/kernel-9c.json"], []),                      # the actual Colab injection
    (["--year", "2019", "-f", "/k.json"], ["--year", "2019"]),
    ([], []),
])
def test_clean_argv_all_four_measured_cases(argv, want):
    """THE EQUALS FORM IS THE LOAD-BEARING CASE. ~100 files carried
    `[a for a in sys.argv[1:] if not (a == "-f" or a.endswith(".json"))]` — copied from
    CLAUDE.md rule 3.10 itself, which showed that exact line. Space-form values died
    loudly ("expected one argument"); the equals form was dropped WHOLE and the flag fell
    back to its default with no error at all. A test without the equals case passes while
    the bug lives."""
    from phase4seg.names import clean_argv
    assert clean_argv(list(argv)) == want


def test_the_broken_argv_idiom_is_extinct():
    """The sweep took the count to zero; this keeps it there. The idiom spread because
    the RULEBOOK showed it — rule 3.10 now derives from names.clean_argv instead."""
    import re
    pat = re.compile(r'\[\s*\w+\s+for\s+\w+\s+in\s+[\w.\[\]:()\s]+\s+if\s+not\s*\(\s*\w+\s*==\s*"-f"')
    hits = []
    for root in ("pipeline", "qc"):
        for p in sorted((SCRIPTS / root).rglob("*.py")):
            if "_archive" in p.parts or p.name in ("names.py", Path(__file__).name):
                continue
            src = p.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(src.splitlines(), 1):
                if pat.search(line) and "clean_argv" not in line:
                    hits.append(f"{p.name}:{i}")
    assert not hits, (
        "the broken -f/.json one-liner is back (it drops --flag=value.json silently); "
        "use names.clean_argv: " + ", ".join(hits))


# ── the lake has one home ─────────────────────────────────────────────────────

def test_lake_module_is_stdlib_only_and_uses_the_strict_probe():
    """38 files used a bare `.exists()` probe that is true whenever the mount POINT
    exists — mounted or not — so an unmounted Colab drive read as an empty lake rather
    than an unreachable one. lake.py standardises the strict (Full_Image) probe the
    3-file minority carried. Stdlib-only, or the orchestrator loses it."""
    import importlib
    import sys as _s
    before = set(_s.modules)
    lake = importlib.import_module("lake")
    heavy = {"torch", "rasterio", "geopandas", "numpy", "pandas"}
    pulled = heavy & {m.split(".")[0] for m in set(_s.modules) - before}
    assert not pulled, f"lake.py pulled heavy deps: {sorted(pulled)}"
    src = (SCRIPTS / "pipeline" / "lake.py").read_text(encoding="utf-8")
    assert '(COLAB_BASE / "Full_Image").exists()' in src, "the strict probe is gone"
    assert isinstance(lake.DRIVE_MOUNT_PREFIX, str) and lake.DRIVE_MOUNT_PREFIX.endswith("/"), (
        "DRIVE_MOUNT_PREFIX must stay a forward-slash string with its trailing slash — "
        "it feeds startswith() guards and Path() would break them on Windows")


def test_no_new_two_path_probe_idiom():
    """The 38-file sweep took the hand-rolled probe to zero outside the deliberate
    stdlib twins; this keeps it there."""
    import re
    pat = re.compile(r'_COLAB_BASE = Path\("/content/drive/MyDrive/treedata"\)')
    allowed = {"lake.py", "vm_heartbeat.py", "gen_vm_bootstrap.py", Path(__file__).name}
    hits = []
    for root in ("pipeline", "qc"):
        for p in sorted((SCRIPTS / root).rglob("*.py")):
            if "_archive" in p.parts or p.name in allowed:
                continue
            if pat.search(p.read_text(encoding="utf-8", errors="replace")):
                hits.append(p.name)
    assert not hits, (
        "hand-rolled lake-root probes are back — import from pipeline/lake.py: "
        + ", ".join(hits))


def test_emitted_bootstrap_imports_every_module_its_body_uses():
    """The emitted-script gate checks the body PARSES; a used-but-unimported name is a
    NameError on the VM that no parse can see. This nearly shipped on 2026-08-31: the
    editable-install step used sys.executable while the emitted import line read
    `import json, os, subprocess, time` — no sys. Static check on the generator source:
    every MODULE.attr the body uses must appear in its own import line."""
    import re
    src = (SCRIPTS / "pipeline" / "gen_vm_bootstrap.py").read_text(encoding="utf-8")
    m = re.search(r"body = f'''(.*?)'''", src, re.S)
    assert m, "the emitted body f-string was not found"
    body = m.group(1)
    imp = re.match(r"import ([a-z_, ]+)", body)
    assert imp, "the emitted body no longer starts with its import line"
    imported = {x.strip() for x in imp.group(1).split(",")}
    used = set(re.findall(r"\b(json|os|subprocess|sys|time|shutil|pathlib)\.", body))
    missing = used - imported
    assert not missing, (
        f"the emitted bootstrap uses {sorted(missing)} without importing them — "
        f"NameError on the VM, invisible to the parse gate")


# ── refactor 3B ratchet: sys.path hacks stay dead ────────────────────────────
# The editable install (pyproject.toml) resolves phase4seg / lake / pipeline_log /
# registry_from_manifests / cost_report from anywhere; 3B removed the ~40 files of
# per-file inserts that predate it. What SURVIVES is a short ledger, each entry
# justified in place:
#   · conftest.py            — the ONE canonical test stanza: tests import
#                              pipeline-root orchestration modules (phase4_train_queue,
#                              watch_queue, …) the install deliberately does NOT expose
#   · uninstalled-module keeps — files importing pipeline-ROOT scripts by name
#                              (make_nir_stack, phase4_train_queue, acquire_imagery)
#   · preflight / smoke      — pin "validate the engine SITTING NEXT TO ME", not
#                              whatever tree the venv's editable install points at
#   · the finetune shim      — _pkg_import_root() picks local-copy vs Drive on Colab
#   · pipeline→qc reverse    — die in refactor 4a, not 3B
#   · qc-sibling inserts     — die in 4c when instruments/ lands
# A NEW insert anywhere else fails here; so does growing an existing file's count.
_PATH_INSERT_LEDGER = {
    "pipeline/acquire_imagery.py": 1,        # mirror_sync (uninstalled pipeline-root)
    "pipeline/builders/make_building_masks.py": 1,  # roof_presence_matrix (blessed qc import)
    "pipeline/phase4_semantic_finetune.py": 1,  # the shim's import-root logic
    "pipeline/phase4seg_preflight.py": 1,    # gate pins the adjacent tree
    "pipeline/phase4seg_smoke.py": 1,        # gate pins the adjacent tree
    "qc/conftest.py": 1,                     # THE canonical stanza
    "pipeline/builders/build_lidar_quadrants.py": 1,  # builders sibling (self-dir)
    "qc/imagery_qc_suite.py": 2,             # qc sibling (4c) + KERNEL-EXEC keep
    "qc/phase4_qc_indep.py": 1,              # KERNEL-EXEC keep (see file header)
    "qc/instruments/investigate_2024_offset.py": 1,  # imagery_qc_suite (qc root)
    "qc/instruments/investigate_displacement.py": 2,  # qc root + sibling
    "pipeline/builders/make_ndvi_stack_norm.py": 1,  # radiometry_norm (4c home)
    "qc/instruments/phase4_golden_gate.py": 1,  # sibling instruments
    "qc/instruments/phase4_qc_design_power.py": 1,  # sibling instruments
    "qc/instruments/phase4_qc_latent_class_adversarial.py": 1,  # sibling
    "qc/instruments/phase4_qc_latent_class_test.py": 1,  # sibling
    "qc/instruments/phase4_sector_poststrat.py": 1,  # phase4_qc_indep (qc root)
    "qc/instruments/phase4_site_eval.py": 1,  # sibling instruments
    "qc/instruments/roof_presence_matrix.py": 1,  # roof_presence_probe sibling
    "qc/runtime_dashboard.py": 2,            # phase4_train_queue + watch_queue keeps
    "qc/runtime_health.py": 1,               # qc sibling keep
    "qc/instruments/separability_index_control.py": 2,  # qc root + sibling
    "qc/test_acquire_imagery.py": 2,         # acquire_imagery keep + qc sibling
    "qc/test_boundary_loss.py": 1,           # string payload for a spawned subprocess
    "qc/test_ci_gates.py": 2,                # string payloads for spawned subprocesses
    "qc/test_dashboard_chips.py": 1,         # qc sibling
}


def test_path_insert_ledger():
    """Every sys.path.insert in pipeline/ and qc/ is on the ledger above, at or below
    its recorded count. 79 sites predated the editable install; 3B cut them to ~39 and
    this ratchet keeps the number falling. Removing one is free (counts are ceilings);
    ADDING one means either the install should cover the import — fix the import — or
    the new site is deliberate and gets a ledger line WITH its justification."""
    import re
    pat = re.compile(r"path\.insert")
    over, unlisted = [], []
    for root in ("pipeline", "qc"):
        for p in sorted((SCRIPTS / root).rglob("*.py")):
            if "_archive" in p.parts or p.name == "test_status_discovery.py":
                continue  # self: the ledger and this regex literal both match the pattern
            n = len(pat.findall(p.read_text(encoding="utf-8", errors="replace")))
            if n == 0:
                continue
            rel = p.relative_to(SCRIPTS).as_posix()
            cap = _PATH_INSERT_LEDGER.get(rel)
            if cap is None:
                unlisted.append(f"{rel} ({n})")
            elif n > cap:
                over.append(f"{rel} ({n} > {cap})")
    assert not unlisted and not over, (
        "sys.path.insert outside the 3B ledger — the editable install exists, use it. "
        f"unlisted={unlisted} over={over}")
