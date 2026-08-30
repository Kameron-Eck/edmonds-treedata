"""Documented facts must match the code. This is the gate the overhaul exists to build.

THE FAILURE IT CLOSES. For an unknown number of weeks `CLAUDE.md` — the file every
session reads first — told each one the archive held **18 acquisitions, 15 calendar
years, 4 NIR years**. The live catalog held **36 / 20 / 10**. It also named a NIR year,
`2022n`, that had not existed since commit 5a12da5 renamed it `2023n`, so a reader
chasing that year looked for a file nothing writes.

Nothing caught it because nothing compared the two. `ci.yml` verified code against code
and one CSV header against its generator; a grep for `CHATLOG|WORKPLAN|CLAUDE.md` across
the whole test suite returned nothing. Every documented fact in the repo was maintained
by hand, by convention, and drifted silently.

WHY A TEST AND NOT A CONVENTION. The repo already states the rule — "one fact, one home"
(`README.md`, `CLAUDE.md`) — and states it in two places, both of which then disagreed
about how long `CHATLOG.md`'s STATE block was. A rule nothing enforces is a wish.

WHY IT COVERS ONLY SOME DOCS TODAY. The doc cleanup is Stage 1 of the overhaul and is
in flight. `README.md`, `IMAGERY_FACTS.md`, `pipeline_buildtracker.md` and
`litreview_phase4_prompt.md` still carry the old figures. Adding them here now would make
the gate red on arrival and it would be switched off. GATED_DOCS grows as Stage 1 lands —
that is the forcing function, and the list below is the to-do list.

WHAT MUST NEVER BE GATED. Dated records and measured outputs (`phase4/qc/*.md`, the
campaign reports, `_archive/`) legitimately contain the old numbers, because they are
what was true when they were written. Editing those to match today would falsify the
record. Staleness is a defect only in a document that claims to be current.

Run:
  PYTHONUTF8=1 py -3.12 -m pytest qc/test_docs_match_code.py -q
"""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS / "pipeline"))


def _status_mod():
    spec = importlib.util.spec_from_file_location(
        "_ps", SCRIPTS / "qc" / "pipeline_status.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


PS = _status_mod()
FACTS = PS.code_facts()

# Docs that CLAIM TO BE CURRENT and have been brought in line with the code.
# Stage 1 still to add: README.md, IMAGERY_FACTS.md, pipeline_buildtracker.md,
# litreview_phase4_prompt.md. The list only grows.
GATED_DOCS = [
    "CLAUDE.md",
    "STATUS.md",
    "WORKPLAN.md",
    "SEMANTIC_OVERHAUL_PLAN_2026-08-29.md",
    "Method_Pipeline.md",
]

# Figures that were true once and are not now. A gated doc may still MENTION one while
# explicitly recording it as corrected — the check below allows that and only that.
RETIRED = {
    "18 acquisitions": "36",
    "15 calendar years": "20",
    "2022n": "renamed to 2023n in 5a12da5",
}
_CORRECTION_CUES = ("was ", "were ", "corrected", "stale", "retired", "no longer",
                    "not exist", "renamed", "previously", "drift", "wrong", "against a")


def _gated_files():
    return [SCRIPTS / d for d in GATED_DOCS if (SCRIPTS / d).exists()]


@pytest.mark.parametrize("doc", GATED_DOCS)
def test_gated_doc_exists(doc):
    assert (SCRIPTS / doc).exists(), f"{doc} is gated but missing — fix the list"


@pytest.mark.parametrize("phrase", sorted(RETIRED))
def test_no_gated_doc_asserts_a_retired_figure(phrase):
    """A retired figure may appear only on a line that is CORRECTING it."""
    offenders = []
    for p in _gated_files():
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if phrase not in line:
                continue
            low = line.lower()
            # A line is a CORRECTION, not an assertion, if it either uses a
            # correcting turn of phrase or names the replacement value alongside
            # the retired one. The supersession tables in the plan docs are pure
            # column pairs with no cue word at all — "| 18 acquisitions, 15
            # calendar years | **36 acquisitions, 20 calendar years** |" — and
            # those are exactly the record we want kept.
            if any(c in low for c in _CORRECTION_CUES):
                continue
            if RETIRED[phrase].split()[0].lower() in low:
                continue
            offenders.append(f"{p.name}:{n}: {line.strip()[:90]}")
    assert not offenders, (
        f"'{phrase}' is retired (now {RETIRED[phrase]}) but is asserted at:\n  "
        + "\n  ".join(offenders))


def test_the_live_numbers_are_what_the_code_says():
    """Pins the derivation itself. If YEAR_CATALOG changes, this fails and every
    number in STATUS.md and the gated docs must be revisited — which is the point."""
    assert FACTS["acquisitions"] == 36, FACTS["acquisitions"]
    assert FACTS["calendar_years"] == 20, FACTS["calendar_years"]
    assert len(FACTS["nir_labels"]) == 10, FACTS["nir_labels"]
    assert FACTS["rgb_only"] == 26
    assert (FACTS["gsd_min"], FACTS["gsd_max"]) == (5.0, 100.0)
    assert "2022n" not in FACTS["nir_labels"], "2022n was renamed to 2023n"


def test_status_md_is_not_stale():
    """The regenerate-and-compare that makes the generator actually run.

    `run_registry.csv` has had a correct, idempotent generator all along
    (registry_from_manifests.py) and is 178 runs behind the data plane, because
    nothing invoked it. A generator that is not wired to a gate is just another stale
    file. This is that wiring.
    """
    status = SCRIPTS / "STATUS.md"
    assert status.exists(), (
        "STATUS.md is missing — run `py -3.12 qc/pipeline_status.py --markdown`")
    text = status.read_text(encoding="utf-8")
    assert PS.CODE_BEGIN in text and PS.CODE_END in text, "STATUS.md lost its markers"
    on_disk = text.split(PS.CODE_BEGIN)[1].split(PS.CODE_END)[0]
    fresh = PS.render_code_block(FACTS).split(PS.CODE_BEGIN)[1].split(PS.CODE_END)[0]
    assert on_disk.strip() == fresh.strip(), (
        "STATUS.md's code block is stale — regenerate with "
        "`py -3.12 qc/pipeline_status.py --markdown`")


def test_exactly_one_document_claims_to_be_the_active_plan():
    """`CHATLOG.md`'s STATE block carried FOUR mutually exclusive 'ACTIVE plan' claims,
    including a duplicate key 111 lines below the first and one naming a plan file that
    does not exist. A session reading it top-down got the right answer once and the
    wrong answer three times."""
    # Plans that read as live TODAY and are known debt. Stage 1.4 of the overhaul
    # applies supersession banners; each one that lands is deleted from this list.
    # The list only ever shrinks — a NEW unbannered plan fails immediately, which is
    # the property worth having while the cleanup is in flight.
    KNOWN_UNBANNERED = {
        "OVERHAUL_PLAN_2026-08-20.md",          # executed P0-P8; still reads ACTIVE
        "IMAGERY_ACQUISITION_PLAN_2026-08-22.md",  # its successor says to mark it
        "IMAGERY_PLAN.md",                      # overtaken by the two above
        "WORKPLAN_2026-08-19.md",               # retires into WORKPLAN.md (Stage 0.1)
    }
    LIVE = "SEMANTIC_OVERHAUL_PLAN_2026-08-29.md"
    # WORKPLAN.md is THE living document, not a dated campaign plan — it is supposed to
    # read as current. Named explicitly because it would otherwise be caught by the
    # filename filter, and it currently escapes only by accident: it happens to use the
    # word "superseded" about CHATLOG's STATE block within the first 2000 characters.
    # Rewording that sentence would break this test for no real reason.
    NOT_A_CAMPAIGN_PLAN = {"WORKPLAN.md"}

    claims = set()
    for p in SCRIPTS.glob("*.md"):
        if "plan" not in p.name.lower() or p.name in NOT_A_CAMPAIGN_PLAN:
            continue
        head = p.read_text(encoding="utf-8")[:2000].lower()
        if "superseded" in head or "retired" in head:
            continue
        claims.add(p.name)

    unexpected = claims - KNOWN_UNBANNERED - {LIVE}
    assert not unexpected, (
        f"a plan document reads as live and is not the active one ({LIVE}): "
        f"{sorted(unexpected)}. Either banner it superseded or make it the live plan.")
    assert LIVE in claims or not (SCRIPTS / LIVE).exists(), (
        f"{LIVE} is the active plan but reads as superseded")
    # and the debt must not grow silently
    stale = KNOWN_UNBANNERED - claims
    assert not stale, (
        f"these are now bannered — delete them from KNOWN_UNBANNERED: {sorted(stale)}")


def test_no_gated_doc_points_at_a_missing_file():
    """A doc naming a file that does not exist sends the reader somewhere empty.
    CHATLOG STATE named `cozy-skipping-jellyfish.md`, which exists nowhere."""
    missing = []
    for p in _gated_files():
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for ref in re.findall(r"`([A-Za-z0-9_./-]+\.(?:md|py|yaml|csv))`", line):
                # Only PATHS. A bare `core.py` is shorthand for "the engine's core",
                # used constantly in prose; requiring it to resolve would force every
                # mention to be spelled pipeline/phase4seg/core.py, which is worse
                # writing and not what this check is for.
                if "/" not in ref or ref.startswith(("http", "_archive")) or "*" in ref:
                    continue
                if any((base / ref).exists() for base in (SCRIPTS, REPO,
                                                          SCRIPTS / "pipeline",
                                                          SCRIPTS / "qc")):
                    continue
                missing.append(f"{p.name}:{n}: {ref}")
    assert not missing, "gated docs reference files that do not exist:\n  " + \
        "\n  ".join(missing)
