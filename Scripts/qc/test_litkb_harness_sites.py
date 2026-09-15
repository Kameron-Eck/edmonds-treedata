"""The per-call-site rule, enforced inside qc/check.py.

Twice a litkb guard written in ONE helper and called from SEVERAL places was mutation-tested at one place only,
and the harness passed a mutant that removed it everywhere else (V2b, then E3f: see the docstring of
qc/instruments/litkb_p2_mutations.py). The harness's own self-check closes that: it enumerates every call of every
targeted helper under Scripts/pipeline/litkb and demands a mutation row at each call site, or a written reason why
a mutation there cannot change behaviour.

This test runs that self-check, so a NEW call site of a guarded helper fails the ordinary suite instead of waiting
for someone to run the ~100-minute mutation campaign. It is static: no database, no network, no mutation applied.
"""
import importlib.util
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def harness():
    """The harness module by path. It imports nothing from litkb — the self-check reads the sources with `ast` —
    so there is no import path to arrange (CLAUDE.md 2.4: the path-insert ledger is closed)."""
    spec = importlib.util.spec_from_file_location("litkb_p2_mutations",
                                                  SCRIPTS / "qc" / "instruments" / "litkb_p2_mutations.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_guarded_call_site_has_a_mutation_row(harness, capsys):
    ok, rows = harness.self_check(verbose=True)
    out = capsys.readouterr().out
    assert ok, "the per-call-site rule is broken:\n" + "\n".join(
        ln for ln in out.splitlines() if "PROBLEM" in ln)
    assert rows, "the static scan found no call sites at all — it has stopped looking"


def test_the_scan_sees_a_guard_reached_through_a_renamed_import(harness, tmp_path):
    """E3f hid behind a second copy of a helper; annas.py reaches normalize_doi through resolver's re-export. If
    the scan stopped resolving `import ... as ...`, both would vanish from the table silently."""
    src = ("from litkb.textnorm import jsonb_safe as _clean\n"
           "def f(v):\n"
           "    return _clean(v)\n")
    sites = harness.sites_of_text(src, "<synthetic module>")     # not a path: nothing to cite, nothing on disk
    assert "<synthetic module>::f::jsonb_safe" in sites, sites


def test_a_row_cannot_claim_a_call_site_it_does_not_touch(harness):
    """The self-check's own kill: a row that mutates only a helper's BODY must not count as covering a call of
    that helper elsewhere. E3 (textnorm's guard block) is exactly such a row."""
    e3 = next(m for m in harness.M if m["id"] == "E3")
    claimed = dict(e3, sites=["litkb/admit/front.py::_jsonb::jsonb_safe"])
    harness.M[harness.M.index(e3)] = claimed
    try:
        ok, _rows = harness.self_check(verbose=False)
    finally:
        harness.M[harness.M.index(claimed)] = e3
    assert not ok, "a body-only row was accepted as covering another module's call site"
