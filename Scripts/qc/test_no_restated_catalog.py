"""No script may hardcode an imagery filename. The catalog is the one home.

WHAT THIS CAUGHT, 2026-08-31. Four live files each restated the NIR catalog as a literal
dict, and all four had drifted to filenames missing their resolution token:

    config.YEAR_CATALOG          the four restated dicts
    2016_snoh_1ft_rgbi.tif   ->  2016_snoh_rgbi.tif
    2019_naip_60cm_rgbi.tif  ->  2019_naip_rgbi.tif
    2021_snoh_6in_rgbi.tif   ->  2021_snoh_rgbi.tif
    2023_naip_60cm_rgbi.tif  ->  2023_naip_rgbi.tif

BOTH NAMES EXIST ON DISK. Every `.exists()` passed, every resolver returned a real file,
nothing raised. But they are DIFFERENT PRODUCTS covering less ground — 34.49 km2 against
the authoritative 87.11 for 2016/2021s (39.6%), 53.79 against 80.31 for the NAIP years
(67.0%). Only an extent check finds it.

phase4_build_corrected_labels.py is a LABEL PRODUCER, and
canopy_additions_2016.lineage.json records `imagery: ...\\2016_snoh_rgbi.tif`: that overlay
was built from under 40% of the city. The lineage system recorded it faithfully. Nobody
read the lineage. (Nothing consumed the overlay — 0 registry rows, 0 queue files, 0 run
manifests — so no landed result is affected.)

WHY A GATE AND NOT FOUR EDITS. The dicts also held 4 of the catalog's 10 NIR-bearing
acquisitions, and MACHINERY_AUDIT_2026-08.md's sanctioned next action was to hand-add the
missing six — extending dicts whose existing four were wrong. Patching filenames recreates
the rot; forbidding the restatement removes it.

Run:
  PYTHONUTF8=1 py -3.12 -m pytest qc/test_no_restated_catalog.py -q
"""
import ast
import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS / "pipeline"))

from phase4seg import config as C          # noqa: E402  (stdlib-only import chain)
from phase4seg.names import nir_years      # noqa: E402

# Any string that looks like one of this project's imagery deliverables.
IMAGERY_RE = re.compile(r"['\"]((?:19|20)\d{2}[a-z]?_[A-Za-z0-9_]*\.tif)['\"]")

# THE DEBT IS ONE NUMBER, NOT A LIST. A census on 2026-08-31 found 56 hardcoded imagery
# names across 13 files, 38 of them the STALE smaller-extent forms across 12. Enumerating
# that as exemptions would produce a list nobody reads and that grows quietly; a ratchet
# makes it a single figure that can only go down, and it fails the moment someone adds one.
#
# The four LABEL-PATH files are held to a stricter rule below, because those are the ones
# that write training supervision.
STALE = ("2016_snoh_rgbi.tif", "2019_naip_rgbi.tif",
         "2021_snoh_rgbi.tif", "2023_naip_rgbi.tif")
# MEASURED 2026-08-31 AFTER the four label-path fixes. It was briefly set to 38 — the
# PRE-fix census — which left exactly four slots of slack, and a ratchet with slack is not
# a ratchet: a mutation adding a stale name passed. The baseline must be the CURRENT count,
# always, or the gate silently tolerates the next N regressions.
STALE_BASELINE = 34
DERIVED_FILES = ("phase4_build_corrected_labels.py", "phase4_qc_ndvi.py",
                 "phase4_miss_examples.py", "phase4_qc_chm_gap.py")

_OWNERS = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _doc_ids(tree):
    """Docstring Constants — prose. This file's own header quotes the stale names in order
    to ban them, so a text scan would flag the ban itself."""
    out = set()
    for n in ast.walk(tree):
        if not isinstance(n, _OWNERS):
            continue
        b = getattr(n, "body", None)
        if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant)                 and isinstance(b[0].value.value, str):
            out.add(id(b[0].value))
    return out


def _live_files():
    out = []
    for root in ("pipeline", "qc"):
        for p in sorted((SCRIPTS / root).rglob("*.py")):
            if "_archive" in p.parts or "litwatch_scratch" in p.parts:
                continue
            out.append(p)
    return out


def _stale_hits():
    hits = []
    for p in _live_files():
        if p.name == Path(__file__).name:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        docs = _doc_ids(tree)
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str)                     and id(n) not in docs and n.value in STALE:
                hits.append(f"{p.name}:{n.lineno}: {n.value}")
    return hits


def test_the_derived_catalog_is_complete():
    """The restated dicts held 4 of the catalog's 10 NIR-bearing acquisitions, and the
    sanctioned next action was to hand-add the missing six to dicts whose existing four
    were wrong. Deriving gets all ten and cannot drift."""
    n = nir_years(C.YEAR_CATALOG)
    assert len(n) >= 10, f"expected >=10 NIR-bearing acquisitions, got {len(n)}"
    assert n["2016"]["native_file"] == "2016_snoh_1ft_rgbi.tif"
    assert n["2021s"]["native_file"] == "2021_snoh_6in_rgbi.tif"


def test_the_label_path_files_derive_and_do_not_restate():
    """THE STRICT RULE, and it is strict because these write training supervision.
    phase4_build_corrected_labels.py produced canopy_additions_2016.tif from a raster
    covering 39.6% of the city, and its own lineage file recorded that faithfully."""
    bad = []
    for p in _live_files():
        if p.name not in DERIVED_FILES:
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        if "nir_years" not in src:
            bad.append(f"{p.name} does not derive from the catalog")
        tree = ast.parse(src)
        docs = _doc_ids(tree)
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str)                     and id(n) not in docs and n.value in STALE:
                bad.append(f"{p.name}:{n.lineno} still names {n.value}")
    assert not bad, ("label-path files must derive, never restate:" + chr(10)
                     + chr(10).join("  " + b for b in bad))


def test_the_stale_name_debt_only_shrinks():
    """A RATCHET. 34 occurrences remain in files that are viewers, samplers, auditors and
    the frozen Phase 1 — none writes labels, so they are debt rather than urgency. This
    fails the moment the count rises, which is the only property that matters: the
    pre-existing debt is visible and cannot grow while nobody is looking.

    To lower the baseline, fix a file and lower the number in the same commit."""
    hits = _stale_hits()
    assert len(hits) <= STALE_BASELINE, (
        f"stale imagery names rose to {len(hits)} (baseline {STALE_BASELINE}). These are "
        f"smaller-extent products that exist on disk, so they resolve silently:"
        + chr(10) + chr(10).join("  " + h for h in hits[:12]))
