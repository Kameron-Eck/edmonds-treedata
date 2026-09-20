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

# Module names for the synthetic sources below. They keep the litkb/<package>/ prefix the sink scan reads (it
# accepts the redacting WRAPPERS only inside acquire/ and admit/), and end in nothing citable — qc's citation
# check resolves every file-and-symbol reference it sees, and a plausible-looking filename here would fail it.
SYNTH_ACQUIRE = "litkb/acquire/<synthetic module>"
SYNTH_OPS = "litkb/ops/<synthetic module>"


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


def test_the_redaction_family_is_under_the_rule(harness):
    """DEFERRED_HELPERS was a scope statement with a measurement behind it (1 of 20 redaction sites fired). It is
    closed: the family is in HELPERS and nothing is deferred. Re-deferring a helper now has to delete this test."""
    assert {"redact", "add_secret", "_redacted"} <= set(harness.HELPERS)
    assert harness.DEFERRED_HELPERS == {}, harness.DEFERRED_HELPERS


def test_every_stdout_sink_passes_through_a_redactor(harness, capsys):
    """The structural guard. Every print / sys.std{out,err}.write under Scripts/pipeline/litkb either takes a
    redactor's return, interpolates nothing, or is named in SINK_ALLOW with a reason about the code."""
    ok, rows = harness.sink_check(verbose=True)
    out = capsys.readouterr().out
    assert ok, "a sink writes unredacted:\n" + "\n".join(ln for ln in out.splitlines() if "PROBLEM" in ln)
    assert rows, "the sink scan found nothing — it has stopped looking"


def test_the_sink_scan_fires_on_an_unredacted_print(harness):
    """The kill criterion, mutation-tested (CLAUDE.md 3.4c): a new print() of an interpolated string is flagged,
    the same line wrapped in redact() is not, and a bare f-string with no fields is not."""
    bad = harness.sink_sites_of_text('def f(x):\n    print(f"tried {x}")\n', SYNTH_ACQUIRE)
    assert bad[f"{SYNTH_ACQUIRE}::f::print"]["ok"] is False
    good = harness.sink_sites_of_text('def f(x):\n    print(redact(f"tried {x}"))\n', SYNTH_ACQUIRE)
    assert good[f"{SYNTH_ACQUIRE}::f::print"]["ok"] is True
    const = harness.sink_sites_of_text('def f():\n    print("nothing pending")\n', SYNTH_ACQUIRE)
    assert const[f"{SYNTH_ACQUIRE}::f::print"]["ok"] is True


def test_an_extra_sink_inside_an_allowed_function_is_not_covered_by_its_reason(harness):
    """SINK_ALLOW excuses the calls that were READ, not the function for ever. Without the pinned count, adding
    `print(f"{r['detail']}")` to an already-allowed function — annas.run_audit, commands.cmd_ws — would pass in
    silence. The kill is shown by moving the pin, which is the same thing a new print() does to it."""
    sid = "litkb/acquire/annas.py::run_audit::print"
    pinned, why = harness.SINK_ALLOW[sid]
    harness.SINK_ALLOW[sid] = (pinned + 1, why)
    try:
        ok, _rows = harness.sink_check(verbose=False)
    finally:
        harness.SINK_ALLOW[sid] = (pinned, why)
    assert not ok, "a function with a different number of sink calls than its reason covers was accepted"
    assert harness.sink_check(verbose=False)[0], "the pin was not restored"


def test_a_redactor_name_defined_elsewhere_does_not_pass_the_sink_scan(harness):
    """litkb/ops/nightly_dump.py has its own log_line(), which appends to a file and redacts nothing. The scan
    accepts the wrapper names only in the modules that define them."""
    src = 'def f(x):\n    print(log_line(x))\n'
    assert harness.sink_sites_of_text(src, SYNTH_ACQUIRE)[f"{SYNTH_ACQUIRE}::f::print"]["ok"]
    assert not harness.sink_sites_of_text(src, SYNTH_OPS)[
        f"{SYNTH_OPS}::f::print"]["ok"]


#: a new query that widens visibility, written the way the three real ones are
_WIDENS = ("from litkb import visibility\n"
           "def f(conn, ws_id, token):\n"
           "{guards}"
           "    return conn.execute('SELECT 1 FROM litkb.files f ' + visibility.FILE_JOIN,\n"
           "                        {{'ws': ws_id}}).fetchone()\n")


def test_every_visibility_widening_sits_behind_the_token_and_state_checks(harness, capsys):
    """Auditor-2a2's finding: `test_every_guarded_call_site_has_a_mutation_row` censuses calls of
    `_require_token`, so it asks whether every guard is mutation-covered — and answers yes while a
    NEW query binding `ws` into `visibility.FILE_JOIN` with no token check at all passes in silence.
    That is the shape of the defect this branch shipped for one day at `_record_use`, and the
    census could not have caught it. This scan enumerates the thing guarded instead of the guard."""
    ok, rows = harness.vis_check(verbose=True)
    out = capsys.readouterr().out
    assert ok, "a visibility widening is unguarded:\n" + "\n".join(
        ln for ln in out.splitlines() if "PROBLEM" in ln)
    assert rows, "the widening scan found no sites at all — it has stopped looking"
    # every real site is either proven in-function or carries a written reason
    assert all(ok_ or mode for _sid, _binds, ok_, mode in rows), rows


def test_the_visibility_scan_fires_on_a_new_unguarded_binding(harness):
    """The kill criterion (CLAUDE.md 3.4c), shown on text: the same function fails without the two
    guards above the bind and passes with them. A guard BELOW the query it protects is not one, so
    the scan compares line numbers rather than mere presence."""
    sid = "litkb/<synthetic module>::f"
    bad = harness.vis_sites_of_text(_WIDENS.format(guards=""), "litkb/<synthetic module>")
    assert bad[sid]["ok"] is False, bad
    good = harness.vis_sites_of_text(
        _WIDENS.format(guards="    _require_token(conn, ws_id, token)\n"
                              "    _require_open(conn, ws_id)\n"), "litkb/<synthetic module>")
    assert good[sid]["ok"] is True, good
    half = harness.vis_sites_of_text(
        _WIDENS.format(guards="    _require_token(conn, ws_id, token)\n"),
        "litkb/<synthetic module>")
    assert half[sid]["ok"] is False, ("the state check is not optional", half)


def test_a_new_widening_added_to_a_copy_of_the_package_fails_the_census(harness, tmp_path):
    """The kill at the level the finding is about: the whole check, over a COPY of the real
    package with one unguarded widening appended to the module that holds the other three. The
    copy is what makes this runnable — `Scripts/pipeline/litkb` is never written by a test."""
    import shutil

    pkg = tmp_path / "pipeline" / "litkb"
    shutil.copytree(SCRIPTS / "pipeline" / "litkb", pkg)
    assert harness.vis_check(verbose=False, root=pkg)[0], "the untouched copy already fails"
    with (pkg / "mcp" / "server.py").open("a", encoding="utf-8") as fh:
        fh.write("\n\ndef _a_new_search(conn, ws_id):\n"
                 "    return conn.execute('SELECT 1 FROM litkb.files f ' + visibility.FILE_JOIN,\n"
                 "                        {'ws': ws_id}).fetchall()\n")
    ok, rows = harness.vis_check(verbose=False, root=pkg)
    assert not ok, "an unguarded widening was accepted by the census"
    assert any(sid.endswith("::_a_new_search") for sid, *_ in rows), rows


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
