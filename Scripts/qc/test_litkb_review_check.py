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

Auditor 3b then measured three routes STILL open on the fixed grader, none of them in the
grammar's disclosure list (auditor-3b-stage8-fixes.md §1.6, §1.7, §1.9), and one MEASUREMENT that
made a rule untenable (§5):

  m12  a one-character -- or one-SPACE -- quote under any        quote-too-short       test_m12_*
       claim at all: ' ' is a substring of every verified span
  m13  a second `## Scope` opened below the findings, which      duplicate-section     test_m13_*
       un-polices everything after it
  m14  a 12-word assertion written as a `###` heading, which     uncited-heading       test_m14_*
       was dropped before a unit was formed
  CR   a quote crossing a block's stored `\r\n`, quoted from an  (none -- it PASSES,   test_crlf_*
       LF-only file. 48.9 % of current-run blocks carry `\r\n`    and one changed
       and 7 of 8 verified spans cross one, so "quote within      character still
       one stored line" truncated almost every verified quote     fails)
       -- once to 33 characters asserting nothing. The LINE
       ENDING ENCODING is now canonical on both sides, and
       nothing else is.

m5 is built from REAL rows: the work, file, extraction run, block and promotable use_evidence
that `_evidence_world` writes into the worker database, quoted from that block's own bytes. The
worker database holds no ingested PDF -- `litkb_pg_base` resets and re-migrates it every session
-- so "real blocks" here means real rows through the real write path, not a real paper.

The CODE-mutation campaign (break each -- BEGIN guard -- block in review_check.py, show this file
fails, restore, sha256-verify) is qc/instruments/litkb_p2_mutations.py rows RC1-RC15. m1-m14 are
INPUT mutations: they prove the guards fire on bad documents. RC1-RC15 prove the tests fail when
the guards are removed. Neither substitutes for the other. RC14 and RC15 are the two halves of
the newline canonicalisation, in two languages with no migration binding them: either half alone,
made the identity, silently restores the defect the pair was written to remove.
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
    assert [h for h, _l, _ls, _f, _d in rc.sections(md)] == ["", "scope", "findings"]
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


def test_canonical_newlines_maps_the_ENCODING_and_never_the_content():
    """G1's whole correctness argument in three lines: every line ending becomes one `\\n`, and
    the number of breaks is preserved -- a run is NOT collapsed. Collapsing `\\n\\n` to `\\n`
    would let a quote silently join two paragraphs of the stored block, which is a change of
    content, not of encoding, and the guard would then accept words the paper never put together."""
    from litkb.textnorm import canonical_newlines as canon

    assert canon("a\r\nb") == canon("a\rb") == canon("a\nb") == "a\nb"
    assert canon("a\r\n\r\nb") == "a\n\nb"          # two breaks stay two
    assert canon("a b") == "a b" and canon(None) is None


def test_m12_a_quote_too_short_to_be_evidence_fails():
    """The auditor's §1.6, measured on the fixed grader: `' '` -- one space -- is a substring of
    essentially every verified span, so one space plus a real citation token satisfied every
    byte-exact guard in the file, under any claim at all."""
    from litkb import review_check as rc

    for quote in (" ", "C", "by", "fell by eleven percent"):
        c = rc.citations(f'Edmonds lost four fifths of its canopy: "{quote}" [K p.1 #ab].')[0]
        assert [f["code"] for f in rc._quote_length_findings(c)] == ["quote-too-short"], quote
    long = rc.citations('It says "Canopy cover fell by eleven percent between 2000 and 2020." '
                        "[K p.1 #ab].")[0]
    assert rc._quote_length_findings(long) == []
    # A BREAK COSTS ONE CHARACTER, NOT TWO. This is the only assertion that reaches the
    # `canonical_newlines` call inside this guard: the quote below is 24 characters canonical and
    # 25 raw, so without the canon it would be exactly long enough and pass.
    edge = "a" * 11 + "\r\n" + "b" * 12
    assert len(edge) == 25 and len(edge.replace("\r\n", "\n")) == 24
    assert [f["code"] for f in rc._quote_length_findings(dict(long, quote=edge))] == [
        "quote-too-short"]
    # and the same text may not pass or fail on which machine wrote the file
    crlf = dict(long, quote="A canopy line\r\nand its second half")
    assert rc._quote_length_findings(crlf) == rc._quote_length_findings(
        dict(long, quote="A canopy line\nand its second half")) == []


def test_m13_a_second_non_claim_section_cannot_un_police_the_document():
    """The auditor's §1.7, measured as PASS: `NON_CLAIM` is matched per OCCURRENCE, so a second
    `## Scope` under the findings turned everything below it into unpoliced prose -- cheaper than
    the E4 hole it generalises, because the writer never has to move anything upward."""
    from litkb import review_check as rc

    md = ("<!-- litkb-review workstream=w -->\n\n## Scope\nwhat this reads.\n"
          '\n## What the record shows\nThe record is explicit: "q" [K p.1 #ab].\n'
          "\n## Scope\nEdmonds lost four fifths of its canopy and every conifer species died.\n")
    found = rc._duplicate_section_findings(md)
    assert [f["code"] for f in found] == ["duplicate-section"], found
    assert found[0]["line"] == 9 and "line 3" in found[0]["detail"], found
    # the first occurrence of each is fine, and two CLAIM sections may share a name: both are
    # graded, so nothing hides in the second one
    assert rc._duplicate_section_findings(md.replace("\n## Scope\nEdmonds", "\n## Findings\nEdmonds")) == []


def test_m14_an_assertion_written_as_a_heading_is_graded():
    """The auditor's §1.9, measured as PASS: `sections` dropped every `#`-prefixed line before a
    unit was formed, so the most natural place for a model to put a summary assertion was the one
    place K1 could not look. A heading short enough to be a LABEL is still exempt."""
    from litkb import review_check as rc

    base = "<!-- litkb-review workstream=w -->\n\n## Findings\n"
    long_heading = "### Edmonds lost four fifths of its canopy and every conifer species died\n"
    found = rc._deep_heading_findings(base + long_heading)
    assert [f["code"] for f in found] == ["uncited-heading"], found
    assert found[0]["line"] == 4
    # the same text with no space after the '#' is not a heading to a renderer either
    assert [f["code"] for f in rc._deep_heading_findings(base + long_heading.replace("### ", "#"))
            ] == ["uncited-heading"]
    # exempt: a label, and any heading that carries its own citation
    assert rc._deep_heading_findings(base + "### Method\n") == []
    assert rc._deep_heading_findings(base + "#### 2005 to 2012, northern parcels\n") == []
    assert rc._deep_heading_findings(base + long_heading.rstrip("\n") + ' "q" [K p.1 #ab]\n') == []
    # and a deep heading in a NON-claim section is not graded (Scope is the writer's own words)
    assert rc._deep_heading_findings(
        "<!-- litkb-review workstream=w -->\n\n## Scope\n" + long_heading) == []


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


#: The block every m-row is graded against. `_evidence_world`'s own block is 59 characters and the
#: spans the P1 suite anchors in it are 16 and 19 -- all under `MIN_QUOTE_CHARS` since 2026-09-20,
#: so a world built on it would fail `quote-too-short` in every row and test nothing else. Three
#: sentences, because m6 needs a real sentence of the block that NO verified span covers.
#:   S1 [0:58)    58 chars   verified, stance supports   -- the review's quote
#:   S2 [59:112)  53 chars   verified, stance refutes    -- the contradicting use
#:   S3 [113:151) 38 chars   in the block, in no verified span -- m6 quotes this
_BLOCK_TEXT = ("Canopy cover fell by eleven percent between 2000 and 2020. The decline was "
               "concentrated in the northern parcels. Conifer mortality explained most of it.")
_S1, _S2, _S3 = (0, 58), (59, 112), (113, 151)


def _long_block(pg, w):
    """Give the world a block long enough to quote from, in the SAME file and extraction run (so
    it is still that file's current run, which is all `_BLOCK_SQL` asks). Must run BEFORE any
    `_add_evidence` call: that helper anchors on `w["block"]`."""
    w["text"] = _BLOCK_TEXT
    w["block"] = pg.one("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) VALUES "
                        "(%s, %s, 1, 'paragraph', %s) RETURNING id",
                        (w["file"], w["run"], _BLOCK_TEXT))[0]
    return w


def _world(pg):
    """A workstream holding: one promotable quote (a VERIFIED brief line) and one hunt_request
    the database resolves CONTRADICTED. Both halves are what a review must account for."""
    w = _long_block(pg, _evidence_world(pg))
    ws = w["ws"]
    w["key"] = pg.one("SELECT key FROM litkb.works WHERE id = %s", (w["work"],))[0]
    w["quote"] = w["text"][slice(*_S1)]
    _add_evidence(pg, pg.conn, w, ws, w["uv"], w["quote"], *_S1, stance="supports")

    hr = _hrmod._record(pg, ws, ref="10.1/contradicted",
                        expected_claim="the identity fails under model mismatch")
    _hrmod._link(pg, ws, hr, w["work"])
    _use, uv2 = pg.proposal(pg.conn, "use", None,
                            {"work_id": str(w["work"]), "hunt_request_id": str(hr)}, None,
                            {"statement": "refutes it", "kind": "contradiction",
                             "status": "refuted"}, None, ws)
    _add_evidence(pg, pg.conn, w, ws, uv2, w["text"][slice(*_S2)], *_S2, stance="refutes")
    w["hr"] = hr
    assert pg.one("SELECT resolution_state FROM litkb.hunt_request_status WHERE id = %s",
                  (hr,))[0] == "contradicted"
    return w


def _confirmed_world(pg):
    """A workstream whose ONLY expectation came back CONFIRMED. Everything a review needs is
    here -- a promotable quote, a hunt_request, a disclosure section -- and K2's first half has
    still never fired, which is what `k2-never-fired` exists to refuse (m11)."""
    w = _long_block(pg, _evidence_world(pg))
    ws = w["ws"]
    w["key"] = pg.one("SELECT key FROM litkb.works WHERE id = %s", (w["work"],))[0]
    w["quote"] = w["text"][slice(*_S1)]
    _add_evidence(pg, pg.conn, w, ws, w["uv"], w["quote"], *_S1, stance="supports")

    hr = _hrmod._record(pg, ws, ref="10.1/confirmed",
                        expected_claim="the identity holds under model mismatch")
    _hrmod._link(pg, ws, hr, w["work"])
    _use, uv2 = pg.proposal(pg.conn, "use", None,
                            {"work_id": str(w["work"]), "hunt_request_id": str(hr)}, None,
                            {"statement": "confirms it", "kind": "empirical evidence",
                             "status": "supported"}, None, ws)
    _add_evidence(pg, pg.conn, w, ws, uv2, w["text"][slice(*_S2)], *_S2, stance="supports")
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
def test_a_review_quoting_a_use_recorded_across_a_stored_crlf_passes(pg):
    """THE END-TO-END ROW for the 2026-09-20 record-use fix: a use RECORDED through the ordinary
    path from an LF quote that crosses a stored `\\r\\n`, then cited in a review that (like every
    file a writer's Write tool produces) holds no CR at all.

    Before migration 0026 this document could not exist: `use.locate_quote` refused the LF quote,
    so there was no verified span to cite, and the writer of the proving run quoted single LINES
    instead. What makes the row worth having is that BOTH ends are exercised -- the recording path
    chose the offsets and the database verified them, and the grader then found the same words
    through `_BLOCK_SQL` and `_verified_span_findings` -- so a fix to one end alone fails here.

    The control below is the same review with one word changed: the relaxation is of the line
    break's ENCODING and of nothing else."""
    from litkb import use as _use

    w = _world(pg)
    crlf = ("Seasonal difference enters as label error, not as scattered noise.\r\n"
            "Every label in the archive comes from one April flight.\r\n")
    span = "as label error, not as scattered noise.\r\nEvery label in the archive"
    block = pg.one("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) VALUES "
                   "(%s, %s, 1, 'paragraph', %s) RETURNING id", (w["file"], w["run"], crlf))[0]
    lf = span.replace("\r\n", "\n")
    hit = next(h for h in _use.locate_quote(pg.conn, w["work"], lf) if h["block_id"] == block)
    assert (hit["char_start"], hit["char_end"]) == (crlf.index(span), crlf.index(span) + len(span))
    ev = _use.attach_quote(pg.conn, w["ws"], pg.token(w["ws"]), w["uv"], hit, lf)
    assert ev["quote_verified"] is True, ev
    assert _codes(pg, _review(w, block_id=block, quote=lf)) == []
    altered = lf.replace("scattered", "sporadic")
    assert altered != lf, "the control changes no word"
    codes = _codes(pg, _review(w, block_id=block, quote=altered))
    assert "quote-not-verbatim" in codes, codes


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
    text = "A second paragraph of the same file that nobody ever recorded a use for."
    other = pg.one("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) VALUES "
                   "(%s, %s, 1, 'paragraph', %s) RETURNING id", (w["file"], w["run"], text))[0]
    codes = _codes(pg, _review(w, block_id=other, quote=text))
    assert codes == ["not-in-brief"], codes


@pg_only
def test_m2_a_quote_altered_by_one_word_fails(pg):
    w = _world(pg)
    altered = w["quote"].replace("eleven", "twelve")
    assert altered != w["quote"] and altered not in w["text"]
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
    outside = w["text"][slice(*_S3)]
    assert outside == "Conifer mortality explained most of it", outside
    assert outside not in w["quote"] and outside not in w["text"][slice(*_S2)]
    assert outside in w["text"]                      # so RC1/RC2/RC3 all pass it
    from litkb.review_check import MIN_QUOTE_CHARS   # and RC11: it is not simply too short
    assert len(outside) >= MIN_QUOTE_CHARS
    codes = _codes(pg, _review(w, quote=outside))
    assert codes == ["quote-not-verified-span"], codes


@pg_only
def test_the_verified_span_itself_and_a_substring_of_it_pass(pg):
    """The control m6 needs: the guard accepts what the brief verified, and any part of it."""
    w = _world(pg)
    assert _codes(pg, _review(w, quote=w["quote"])) == []
    assert _codes(pg, _review(w, quote=w["quote"][2:40])) == []


@pg_only
def test_m12_a_one_space_quote_no_longer_satisfies_every_byte_exact_guard(pg):
    """End to end, against the real brief: a single space is inside every verified span, so
    before RC11 it carried any claim at all past every guard in the file."""
    w = _world(pg)
    assert " " in w["quote"]                        # which is why it used to pass
    assert _codes(pg, _review(w, quote=" ")) == ["quote-too-short"]
    assert _codes(pg, _review(w, quote=w["quote"][:10])) == ["quote-too-short"]


@pg_only
def test_m13_a_second_scope_below_the_findings_fails_end_to_end(pg):
    w = _world(pg)
    text = _review(w) + ("\n## Scope\nEdmonds lost four fifths of its canopy and every conifer "
                         "species died.\n")
    assert _codes(pg, text) == ["duplicate-section"]


@pg_only
def test_m14_a_heading_that_asserts_fails_end_to_end(pg):
    w = _world(pg)
    text = _review(w, extra_claim="\n### Edmonds lost four fifths of its canopy and every "
                                  "conifer species died\n")
    assert _codes(pg, text) == ["uncited-heading"]


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
def _crlf_world(pg):
    """`_world`, plus a block stored the way ~half this corpus really is: with `\\r\\n` inside it,
    and a VERIFIED span that CROSSES that break. Measured on the 2026-09-19 dump: 48.9 % of
    current-run blocks carry `\\r\\n` and 7 of the project's 8 verified spans cross one."""
    w = _world(pg)
    text = "A canopy line\r\nand its second half, stored as the extractor wrote it."
    span = "A canopy line\r\nand its second half"
    assert text[:len(span)] == span and "\r\n" in span
    block = pg.one("INSERT INTO litkb.blocks (file_id, run_id, page_no, type, text) VALUES "
                   "(%s, %s, 1, 'paragraph', %s) RETURNING id", (w["file"], w["run"], text))[0]
    _add_evidence(pg, pg.conn, dict(w, block=block), w["ws"], w["uv"], span, 0, len(span))
    return w, block, span


@pg_only
def test_crlf_an_lf_review_may_quote_a_span_that_crosses_a_stored_crlf(pg, tmp_path):
    """THE CASE THE GRAMMAR USED TO FORBID, and the reason it could not stand.

    Until 2026-09-20 the comparison was byte-exact including the line ENDING, so a quote crossing
    a stored `\\r\\n` could only match if the review file carried that CR -- and grammar §2 told
    writers to quote within one stored line instead. The auditor measured the price: that rule
    truncates 7 of the project's 8 verified spans, one of them to the 33 characters
    `Tent reduces generalization error`, which assert nothing without the rest of the sentence.
    The only other path was an LLM emitting a raw CR byte through its `Write` tool, which nobody
    has ever observed.

    So the LINE ENDING ENCODING is canonicalised on both sides and nothing else is. This test is
    the file written the way a writer's `Write` tool actually writes one -- LF only, no CR
    anywhere in the bytes on disk -- quoting a span that crosses the block's `\\r\\n`."""
    w, block, span = _crlf_world(pg)
    review = _review(w, block_id=block, quote=span.replace("\r\n", "\n"))
    path = tmp_path / "lf.md"
    path.write_bytes(review.encode("utf-8"))
    assert b"\r" not in path.read_bytes()

    from litkb import review_check as rc
    in_process = rc.check(pg.conn, review, is_text=True)
    from_disk = rc.check(pg.conn, str(path))
    assert in_process == from_disk == [], (in_process, from_disk)


@pg_only
def test_crlf_a_crlf_review_quoting_the_same_span_also_passes(pg, tmp_path):
    """The other encoding of the same content. `_read` still reads with newline translation OFF
    (the auditor's F1), so the two routes see different bytes and must reach the same verdict:
    the encoding of a line break is the ONE difference the grader forgives."""
    w, block, span = _crlf_world(pg)
    review = _review(w, block_id=block, quote=span.replace("\r\n", "\n")).replace("\n", "\r\n")
    assert review.count("\r\n") and "\r\r\n" not in review
    path = tmp_path / "crlf.md"
    path.write_bytes(review.encode("utf-8"))

    from litkb import review_check as rc
    assert rc.check(pg.conn, review, is_text=True) == rc.check(pg.conn, str(path)) == []


@pg_only
def test_crlf_one_changed_character_in_that_span_still_fails(pg, tmp_path):
    """The control the relaxation needs: only the BREAK may differ. The same LF-on-disk review
    with one character of the quote altered is refused by both byte-exact guards -- it is not the
    block's text, and not the span anyone verified."""
    w, block, span = _crlf_world(pg)
    altered = span.replace("\r\n", "\n").replace("canopy", "canapy")
    assert altered != span.replace("\r\n", "\n")
    path = tmp_path / "lf_altered.md"
    path.write_bytes(_review(w, block_id=block, quote=altered).encode("utf-8"))
    assert b"\r" not in path.read_bytes()

    from litkb import review_check as rc
    assert [f["code"] for f in rc.check(pg.conn, str(path))] == [
        "quote-not-verbatim", "quote-not-verified-span"]


@pg_only
def test_the_sql_and_python_newline_canonicalisations_agree(pg):
    """`canonical_newlines`'s database half is `litkb.canonical_newlines(text)` (migration 0026),
    reached from Python only through `textnorm.sql_canonical_newlines` -- which is what
    `_CANON_TEXT` is built from, so this drives the very expression `_BLOCK_SQL` uses AND the
    function the 0026 verify trigger calls. THIS TEST IS THE ONLY THING BINDING THE TWO: a regex
    and a SQL function cannot share a definition, so if one is changed and this passes, the other
    was changed too."""
    from litkb import review_check as rc
    from litkb.textnorm import canonical_newlines

    text = "crlf\r\nbare cr\rlf\nand a blank\r\n\r\nline"
    got = pg.one(f"SELECT {rc._CANON_TEXT} FROM (SELECT %s::text AS text) b", (text,))[0]
    assert got == canonical_newlines(text) == "crlf\nbare cr\nlf\nand a blank\n\nline", got


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
