"""litkb review-check (litkb/review_check.py, stage 8 delta 2026-09-20) -- the DETERMINISTIC
K1/K2 gate on a written review, and the known-bad reviews it is shown to refuse.

`decisions.yaml::litkb-operational-definition` fixes the two kill criteria; CLAUDE.md 3.4c says a
kill criterion must be shown to FIRE on a known-bad input before it counts as a gate. So the
table below is not "does the grader run" but "which bad review does each guard catch":

  row  the known-bad review                                        expected finding   test
  m1   cites a block_id that is not in the database                block-not-found    test_m1_*
  m1b  cites a REAL block that no promotable use_evidence row      not-in-brief       test_m1b_*
       anchors (added beyond the delta's five: without it K1
       degrades from "traceable to a verified quote" to "the
       block exists", and RC3 has no kill)
  m2   a citation whose quote is altered by one word               quote-not-verbatim test_m2_*
  m3   a claim paragraph with no citation (K1)                     uncited-claim      test_m3_*
  m4   a CONTRADICTED expectation left out of the section (K2)     expectation-not-   test_m4_*
                                                                     disclosed
  m5   the same review, correct                                    (none)             test_m5_*

The stage-8 AUDIT (auditor-3-stage8.md) measured six routes by which a grammar-conforming review
could pass while unsupported, and one defect. m6-m11 are the five that were closed by code, one
row each; the sixth (whether a sentence MEANS what its quote says) is not machine-checkable and
stays disclosed in grammar §7.

  m6   cites a VERIFIED block, quoting text outside every        quote-not-verified-   test_m6_*
       verified span -- the audit's E1, and the sharpest one:      span
       a block is a paragraph, so a citation verified for its
       first sentence carried a quote from its fourth
  m7   a cited paragraph whose SECOND sentence asserts on its    uncited-claim         test_m7_*
       own (E3: the unit was the paragraph)
  m8   a markdown table row in a claim section, uncited (E5)     uncited-claim         test_m8_*
  m9   a fenced code block inside a claim section (E6)           fenced-in-claims      test_m9_*
  m10  a citation moved into Scope (E4's tell: an uncited        claim-outside-        test_m10_*
       claim there is invisible, a CITED one is not)              claim-section
  m11  a workstream whose every expectation came back            k2-never-fired        test_m11_*
       CONFIRMED -- K2's first half never fired
  CR   a quote spanning the CRLF of a block stored with CRLF,    (none, and the same   test_crlf_*
       through the FILE path: `read_text` translated it to LF     findings as in-
       and no such quote could ever pass the CLI                  process)

m5 is built from REAL rows: the work, file, extraction run, block and promotable use_evidence
that `_evidence_world` writes into the worker database, quoted from that block's own bytes. The
worker database holds no ingested PDF -- `litkb_pg_base` resets and re-migrates it every session
-- so "real blocks" here means real rows through the real write path, not a real paper.

The CODE-mutation campaign (break each -- BEGIN guard -- block in review_check.py, show this file
fails, restore, sha256-verify) is qc/instruments/litkb_p2_mutations.py rows RC1-RC7. m1-m5 are
INPUT mutations: they prove the guards fire on bad documents. RC1-RC7 prove the tests fail when
the guards are removed. Neither substitutes for the other.
"""
import argparse
import uuid

import pytest

import test_litkb_hunt_request as _hrmod
import test_litkb_p1 as _p1mod
from test_litkb_p1 import _add_evidence, _evidence_world

# the P1 suite's session fixtures, reused so this file shares ONE reset of the test database --
# the same binding qc/test_litkb_brief.py makes, and for the same reason (two session fixtures
# each holding the suite's advisory lock would wait on each other forever).
_pg_session = _p1mod._pg_session
pg = _p1mod.pg

pg_only = pytest.mark.requires_litkb_pg


# ── the grammar, with no database in sight ─────────────────────────────────────────────────


def test_header_is_the_first_non_blank_line():
    from litkb import review_check as rc

    assert rc.header_workstream("\n\n<!-- litkb-review workstream=my-slug -->\n# T\n") == "my-slug"
    assert rc.header_workstream("# T\n<!-- litkb-review workstream=my-slug -->\n") is None
    assert rc.header_workstream("") is None


def test_a_citation_carries_the_quote_immediately_before_it():
    from litkb import review_check as rc

    c = rc.citations('He wrote "a verbatim span" [Key_2020_x-paper p.7 #0199a7d2-aaaa].')
    assert len(c) == 1
    assert (c[0]["work_key"], c[0]["page"], c[0]["block_id"]) == (
        "Key_2020_x-paper", 7, "0199a7d2-aaaa")
    assert c[0]["quote"] == "a verbatim span"


@pytest.mark.parametrize("text,quote", [
    ('“curly quotes count” [K p.1 #ab]', "curly quotes count"),
    ('"first" and then "second" [K p.1 #ab]', "second"),
    ('no quote at all [K p.1 #ab]', None),
    ('"trailing prose" is not a quote for [K p.1 #ab]', None),
    ('"" [K p.1 #ab]', ""),
])
def test_the_quote_rule_is_exact(text, quote):
    from litkb import review_check as rc

    assert rc.citations(text)[0]["quote"] == quote


def test_each_list_item_is_its_own_unit():
    """One citation cannot cover a bulleted list of claims."""
    from litkb import review_check as rc

    md = ("<!-- litkb-review workstream=w -->\n\n## Findings\n"
          '- first claim "q" [K p.1 #ab]\n'
          "- second claim, uncited\n")
    codes = [f["code"] for f in rc._claim_findings(md)]
    assert codes == ["uncited-claim"], codes


def test_a_deeper_heading_does_not_escape_its_claim_section():
    from litkb import review_check as rc

    md = ("<!-- litkb-review workstream=w -->\n\n## Findings\n"
          '"q" [K p.1 #ab]\n\n### A sub-heading\nan uncited sentence\n')
    assert [f["code"] for f in rc._claim_findings(md)] == ["uncited-claim"]


def test_a_claim_may_not_hide_in_scope_or_the_preamble():
    from litkb import review_check as rc

    md = ('<!-- litkb-review workstream=w -->\n\n## Scope\nIt says "something" [K p.1 #ab].\n')
    assert [f["code"] for f in rc._claim_findings(md)] == ["claim-outside-claim-section"]


def test_the_citation_unit_is_the_sentence_not_the_paragraph():
    """m7's rule, with no database in sight: a citation covers the sentence it sits in."""
    from litkb import review_check as rc

    md = ("<!-- litkb-review workstream=w -->\n\n## Findings\n"
          'Canopy fell 40 percent. The work states it: "q" [K p.1 #ab].\n')
    found = rc._claim_findings(md)
    assert [f["code"] for f in found] == ["uncited-claim"], found
    assert "Canopy fell 40 percent." in found[0]["detail"]


def test_a_sentence_end_inside_a_quote_is_the_papers_not_the_reviews():
    """The one place the splitter does not cut. The quoted text is compared byte-for-byte against
    a VERIFIED span, so a faithfully copied two-sentence quote must stay writable."""
    from litkb import review_check as rc

    assert rc.sentences('It says: "One. Two" [K p.1 #ab].') == ['It says: "One. Two" [K p.1 #ab].']
    assert rc.sentences("Two things. Then another.") == ["Two things.", "Then another."]


def test_a_table_row_in_a_claim_section_is_a_unit_and_its_header_is_not():
    """m8: a findings table was the most natural way for a model to present per-year results, and
    it was entirely outside K1. The delimiter row and the header it delimits assert nothing."""
    from litkb import review_check as rc

    md = ("<!-- litkb-review workstream=w -->\n\n## Findings\n"
          "| year | canopy loss |\n|---|---|\n"
          '| 2005 | 12% cited "q" [K p.1 #ab] |\n| 2012 | 19% |\n')
    found = rc._claim_findings(md)
    assert [f["code"] for f in found] == ["uncited-claim"], found
    assert "2012" in found[0]["detail"] and found[0]["line"] == 7


def test_m9_a_fenced_block_in_a_claim_section_fails():
    from litkb import review_check as rc

    md = ("<!-- litkb-review workstream=w -->\n\n## Findings\n"
          '"q" [K p.1 #ab]\n\n```\nCanopy cover fell 40 percent and two species were lost.\n```\n')
    assert [f["code"] for f in rc._fenced_findings(md)] == ["fenced-in-claims"]
    # and the same fence in a NON-claim section is fine: that is where a code block belongs
    assert rc._fenced_findings(md.replace("## Findings", "## Scope")) == []


def test_an_unclosed_fence_cannot_swallow_a_claim_section():
    """The way round `fenced-in-claims` the guard could not see by itself: open a fence in
    `Scope` -- legal, and where §4 sends code blocks -- and never close it. Every later heading
    was swallowed, the whole claim section was dropped before a unit was formed, and the fence
    was recorded against `scope`, which is not policed. A `##` at column 0 ends an open fence."""
    from litkb import review_check as rc

    md = ("<!-- litkb-review workstream=w -->\n\n## Scope\n```\nsome setup\n\n"
          "## Findings\nCanopy cover fell 40 percent and two species were lost.\n```\n")
    assert [h for h, _l, _ls, _f in rc.sections(md)] == ["", "scope", "findings"]
    assert [f["code"] for f in rc._fenced_findings(md)] == ["fenced-in-claims"]
    assert [f["code"] for f in rc._claim_findings(md)] == ["uncited-claim"]


def test_m10_a_citation_moved_into_scope_fails():
    """E4's tell. An UNCITED claim in Scope is invisible to the grader by construction (grammar
    §7 says so); a claim that was MOVED there brings its citation with it."""
    from litkb import review_check as rc

    md = ('<!-- litkb-review workstream=w -->\n\n## Scope\nThe work says "something" [K p.1 #ab].\n')
    assert [f["code"] for f in rc._claim_findings(md)] == ["claim-outside-claim-section"]
    md2 = ('<!-- litkb-review workstream=w -->\n\n## Sources\nAs "shown" in [K p.1 #ab].\n')
    assert [f["code"] for f in rc._claim_findings(md2)] == ["claim-outside-claim-section"]


def test_a_mangled_citation_is_named_not_ignored():
    from litkb import review_check as rc

    text = 'It says "q" [K p1 #ab].'
    assert rc.citations(text) == []
    assert [f["code"] for f in rc._malformed_findings(text, [])] == ["malformed-citation"]


def test_a_well_formed_citation_is_not_reported_as_malformed():
    from litkb import review_check as rc

    text = 'It says "q" [K p.1 #ab].'
    assert rc._malformed_findings(text, rc.citations(text)) == []


# ── the worlds the m-rows are graded against ───────────────────────────────────────────────


def _world(pg):
    """A workstream holding: one promotable quote (a VERIFIED brief line) and one hunt_request
    the database resolves CONTRADICTED. Both halves are what a review must account for."""
    w = _evidence_world(pg)
    ws = w["ws"]
    w["key"] = pg.one("SELECT key FROM litkb.works WHERE id = %s", (w["work"],))[0]
    w["quote"] = w["text"][4:20]
    _add_evidence(pg, pg.conn, w, ws, w["uv"], w["quote"], 4, 20, stance="supports")

    hr = _hrmod._record(pg, ws, ref="10.1/contradicted",
                        expected_claim="the identity fails under model mismatch")
    _hrmod._link(pg, ws, hr, w["work"])
    _use, uv2 = pg.proposal(pg.conn, "use", None,
                            {"work_id": str(w["work"]), "hunt_request_id": str(hr)}, None,
                            {"statement": "refutes it", "kind": "contradiction",
                             "status": "refuted"}, None, ws)
    _add_evidence(pg, pg.conn, w, ws, uv2, w["text"][21:40], 21, 40, stance="refutes")
    w["hr"] = hr
    assert pg.one("SELECT resolution_state FROM litkb.hunt_request_status WHERE id = %s",
                  (hr,))[0] == "contradicted"
    return w


def _confirmed_world(pg):
    """A workstream whose ONLY expectation came back CONFIRMED. Everything a review needs is
    here -- a promotable quote, a hunt_request, a disclosure section -- and K2's first half has
    still never fired, which is what `k2-never-fired` exists to refuse (m11)."""
    w = _evidence_world(pg)
    ws = w["ws"]
    w["key"] = pg.one("SELECT key FROM litkb.works WHERE id = %s", (w["work"],))[0]
    w["quote"] = w["text"][4:20]
    _add_evidence(pg, pg.conn, w, ws, w["uv"], w["quote"], 4, 20, stance="supports")

    hr = _hrmod._record(pg, ws, ref="10.1/confirmed",
                        expected_claim="the identity holds under model mismatch")
    _hrmod._link(pg, ws, hr, w["work"])
    _use, uv2 = pg.proposal(pg.conn, "use", None,
                            {"work_id": str(w["work"]), "hunt_request_id": str(hr)}, None,
                            {"statement": "confirms it", "kind": "empirical evidence",
                             "status": "supported"}, None, ws)
    _add_evidence(pg, pg.conn, w, ws, uv2, w["text"][21:40], 21, 40, stance="supports")
    w["hr"] = hr
    assert pg.one("SELECT resolution_state FROM litkb.hunt_request_status WHERE id = %s",
                  (hr,))[0] == "confirmed"
    return w


def _review(w, *, block_id=None, quote=None, extra_claim="", disclose=True):
    """m5 by default; each keyword makes exactly one of the known-bad reviews."""
    expectations = (f"- hunt_request `{w['hr']}` (10.1/contradicted) expected that the identity "
                    "fails under model mismatch; a verified quote from the same work refutes it.\n"
                    if disclose else "- Every expectation was confirmed.\n")
    return (f"<!-- litkb-review workstream={w['ws']} -->\n"
            "\n# Canopy review\n"
            "\n## Scope\n"
            "One workstream, one question, written from its brief alone.\n"
            "\n## Findings\n"
            f'The work states it directly: "{quote or w["quote"]}" '
            f'[{w["key"]} p.1 #{block_id or w["block"]}].\n'
            f"{extra_claim}"
            "\n## Expectations not supported\n"
            f"{expectations}"
            "\n## Sources\n"
            "\n| work | key | pages cited |\n|---|---|---|\n"
            f"| A test work | `{w['key']}` | 1 |\n")


def _codes(pg, text):
    from litkb import review_check as rc

    return [f["code"] for f in rc.check(pg.conn, text, is_text=True) if f["severity"] == "fail"]


# ── m1-m5: each known-bad review, and the correct one ──────────────────────────────────────


@pg_only
def test_m5_a_correct_review_passes(pg):
    w = _world(pg)
    assert _codes(pg, _review(w)) == []


@pg_only
def test_m1_a_block_id_that_does_not_exist_fails(pg):
    w = _world(pg)
    codes = _codes(pg, _review(w, block_id=uuid.uuid4()))
    assert "block-not-found" in codes, codes


@pg_only
def test_m1b_a_real_block_outside_the_brief_still_fails(pg):
    """K1 is 'traceable to a VERIFIED quote', not 'the block exists': a second block of the same
    file, quoted verbatim, carries no promotable use_evidence row and must be refused."""
    w = _world(pg)
    other = pg.one("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) VALUES "
                   "(%s, %s, 1, 'paragraph', %s) RETURNING id",
                   (w["file"], w["run"], "A second paragraph nobody recorded a use for."))[0]
    codes = _codes(pg, _review(w, block_id=other, quote="second paragraph"))
    assert codes == ["not-in-brief"], codes


@pg_only
def test_m2_a_quote_altered_by_one_word_fails(pg):
    w = _world(pg)
    altered = w["quote"].replace("optimism", "pessimism")
    assert altered != w["quote"]
    codes = _codes(pg, _review(w, quote=altered))
    assert "quote-not-verbatim" in codes, codes


@pg_only
def test_m3_a_claim_paragraph_with_no_citation_fails(pg):
    w = _world(pg)
    codes = _codes(pg, _review(w, extra_claim="\nCanopy cover also fell in every dry year.\n"))
    assert codes == ["uncited-claim"], codes


@pg_only
def test_m4_a_contradicted_expectation_left_out_fails(pg):
    """K2, the load-bearing half: the machinery fired and the document did not say so."""
    w = _world(pg)
    codes = _codes(pg, _review(w, disclose=False))
    assert codes == ["expectation-not-disclosed"], codes


@pg_only
def test_m4b_the_expectations_section_is_required_even_when_empty(pg):
    w = _world(pg)
    text = _review(w).replace("## Expectations not supported", "## Notes")
    codes = _codes(pg, text)
    assert "missing-expectations-section" in codes, codes


@pg_only
def test_m6_a_quote_outside_every_verified_span_fails(pg):
    """THE K1 HOLE the audit found (E1). Both promotable rows of this world verify a span of the
    block -- [4:20) and [21:40). `joint model` is [47:58): really in the block, really on a
    VERIFIED line's (work, page, block), and nobody ever verified it. K1 says *verified quote*,
    and before this guard the grader enforced *verified block, quote anything in it*."""
    w = _world(pg)
    outside = w["text"][47:58]
    assert outside == "joint model", outside
    assert outside not in w["quote"] and outside not in w["text"][21:40]
    assert outside in w["text"]                      # so RC1/RC2/RC3 all pass it
    codes = _codes(pg, _review(w, quote=outside))
    assert codes == ["quote-not-verified-span"], codes


@pg_only
def test_the_verified_span_itself_and_a_substring_of_it_pass(pg):
    """The control m6 needs: the guard accepts what the brief verified, and any part of it."""
    w = _world(pg)
    assert _codes(pg, _review(w, quote=w["quote"])) == []
    assert _codes(pg, _review(w, quote=w["quote"][2:10])) == []


@pg_only
def test_m7_an_uncited_second_sentence_of_a_cited_paragraph_fails(pg):
    w = _world(pg)
    codes = _codes(pg, _review(w, extra_claim="Canopy cover also fell in every dry year.\n"))
    assert codes == ["uncited-claim"], codes


@pg_only
def test_m8_an_uncited_table_row_in_a_claim_section_fails(pg):
    w = _world(pg)
    codes = _codes(pg, _review(w, extra_claim="\n| year | loss |\n|---|---|\n| 2012 | 19% |\n"))
    assert codes == ["uncited-claim"], codes


@pg_only
def test_m9_a_fenced_block_in_a_claim_section_fails_end_to_end(pg):
    w = _world(pg)
    codes = _codes(pg, _review(w, extra_claim="\n```\nCanopy cover fell 40 percent.\n```\n"))
    assert codes == ["fenced-in-claims"], codes


@pg_only
def test_m10_a_citation_in_scope_fails_end_to_end(pg):
    w = _world(pg)
    text = _review(w).replace(
        "One workstream, one question, written from its brief alone.",
        f'One workstream. It already says "{w["quote"]}" [{w["key"]} p.1 #{w["block"]}].')
    codes = _codes(pg, text)
    assert codes == ["claim-outside-claim-section"], codes


@pg_only
def test_m11_a_workstream_whose_expectations_all_confirmed_fails(pg):
    """K2's FIRST half, which was a human-run count until 2026-09-20. This review is otherwise
    perfect: every citation verified, every section present, nothing to disclose. That is the
    problem -- nothing fired, so the review proves nothing about the honesty machinery."""
    w = _confirmed_world(pg)
    codes = _codes(pg, _review(w))
    assert codes == ["k2-never-fired"], codes


@pg_only
def test_the_workstream_flag_asserts_and_never_redirects(pg):
    """`--workstream` cannot point the grade at another ledger: a count of contradicted
    expectations in workstream B says nothing about a review written from workstream A."""
    from litkb import review_check as rc

    w = _world(pg)
    other = pg.ws()
    assert rc.check(pg.conn, _review(w), is_text=True, k2_workstream=str(w["ws"])) == []
    with pytest.raises(rc.ReviewGrammarError, match="header declares"):
        rc.check(pg.conn, _review(w), is_text=True, k2_workstream=str(other))


@pg_only
def test_crlf_a_quote_spanning_a_stored_line_break_grades_the_same_from_disk(pg, tmp_path):
    """The auditor's measured defect (§3.3): `_read` was `read_text`, i.e. universal newlines, so
    every CRLF in the review became a bare LF while the block kept its CRLF. The same bytes
    passed in-process and failed through the command line, and no multi-line quote could ever
    pass the CLI on a block stored with CRLF. The quote is compared byte-for-byte, so the reader
    may not rewrite it."""
    w = _world(pg)
    text = "A canopy line\r\nand its second half, stored as the extractor wrote it."
    span = "A canopy line\r\nand its second half"
    assert text[:len(span)] == span and "\r\n" in span
    block = pg.one("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) VALUES "
                   "(%s, %s, 1, 'paragraph', %s) RETURNING id", (w["file"], w["run"], text))[0]
    _add_evidence(pg, pg.conn, dict(w, block=block), w["ws"], w["uv"], span, 0, len(span))

    review = _review(w, block_id=block, quote=span.replace("\r\n", "\n")).replace("\n", "\r\n")
    assert review.count("\r\n") and "\r\r\n" not in review
    path = tmp_path / "crlf.md"
    path.write_bytes(review.encode("utf-8"))

    from litkb import review_check as rc
    in_process = rc.check(pg.conn, review, is_text=True)
    from_disk = rc.check(pg.conn, str(path))
    assert in_process == from_disk == [], (in_process, from_disk)
    # and the byte-exact rule still bites: the SAME quote with the line break translated to LF
    # -- what `read_text` used to hand the grader -- is not this block's text
    # (both byte-exact guards refuse it: it is not the block's text, and not the span anyone
    # verified -- the same rule asked twice, of the block and of the evidence row)
    assert [f["code"] for f in rc.check(pg.conn, review.replace("\r\n", "\n"), is_text=True)] == [
        "quote-not-verbatim", "quote-not-verified-span"]


@pg_only
def test_a_cited_work_missing_from_sources_fails(pg):
    w = _world(pg)
    text = _review(w).replace(f"| A test work | `{w['key']}` | 1 |", "| (none) | |  |")
    assert _codes(pg, text) == ["source-not-listed"]


# ── the command ────────────────────────────────────────────────────────────────────────────


@pg_only
def test_cmd_review_check_exits_non_zero_on_a_failure_and_zero_on_a_pass(pg, tmp_path):
    from litkb import commands

    w = _world(pg)
    good = tmp_path / "good.md"
    good.write_text(_review(w), encoding="utf-8")
    bad = tmp_path / "bad.md"
    bad.write_text(_review(w, disclose=False), encoding="utf-8")
    assert commands.cmd_review_check(argparse.Namespace(review=str(good)), pg.conn) == 0
    assert commands.cmd_review_check(argparse.Namespace(review=str(bad)), pg.conn) == 1


@pg_only
def test_a_review_that_names_no_workstream_is_refused(pg, tmp_path):
    from litkb import review_check as rc

    with pytest.raises(rc.ReviewGrammarError, match="first non-blank line"):
        rc.check(pg.conn, "# A review with no header\n", is_text=True)


@pg_only
def test_a_review_naming_an_unknown_workstream_is_refused(pg):
    from litkb import review_check as rc

    with pytest.raises(rc.ReviewGrammarError, match="no workstream"):
        rc.check(pg.conn, "<!-- litkb-review workstream=no-such-ws -->\n", is_text=True)
