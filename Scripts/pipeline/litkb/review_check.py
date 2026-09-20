"""litkb review-check -- the DETERMINISTIC gate on a written review (stage 8: brief -> review).

    findings = check(conn, path)         # [] means the review passed K1 and K2
    rc = 0 if not fails(findings) else 1

`decisions.yaml::litkb-operational-definition` fixes what "operational" means and states the two
kill criteria, quoted here as the decision words them:

  K1  any claim in the review that does not trace to a VERIFIED quote (work key + page +
      block_id) = FAIL.
  K2  at least one dropped-off expectation must come back CONTRADICTED or UNCONFIRMED **and the
      review must SAY so** -- the honesty machinery is required to FIRE, not merely to exist.

BOTH KILL CRITERIA ARE ENFORCED HERE, and K2 has two halves that are checked by two different
guards, because they are two different questions:

  * `_never_fired_findings` is K2's FIRST half -- did the machinery fire at all. The workstream
    this review declares must HOLD at least one hunt_request the database resolved CONTRADICTED or
    UNCONFIRMED; a workstream in which every expectation came back confirmed produces a review
    with nothing to disclose, and a green grade on it would say the honesty machinery worked when
    it had simply never been asked. That is `k2-never-fired`, and it is ON by default: a proving
    run that cannot show one negative has not proved the thing it exists to prove. It was a
    human-run `hunt-request list --state contradicted` count until 2026-09-20; a step whose
    skipping is invisible is not a gate.
  * `_expectation_findings` is K2's SECOND half -- given such an expectation, is it NAMED in the
    review's own section. A review in which the machinery fired and the document did not say so is
    exactly the failure `hunt_request` exists to catch.

No model runs here. Everything below is a parse, a set membership, or a question asked of the
database; a review either satisfies the grammar in `Scripts/docs/LITKB_REVIEW_GRAMMAR.md` or it
does not, and two runs of this file on the same bytes give the same answer. That is the whole
point: the writer is an LLM, so the grader may not be one (CLAUDE.md 3.4c -- the proposer never
scores its own proposal).

WHAT IS ASKED OF THE DATABASE, AND WHY IT IS NOT RE-IMPLEMENTED HERE

  * **What may be cited at all** is `litkb.brief.build(conn, ws)` -- the same export the writer
    was given, so "never cite anything absent from the brief" is checked against the brief
    itself rather than against a second, looser idea of what exists. A citation whose
    (work key, page, block id) is not a VERIFIED line is `not-in-brief`, even when the block is
    real: a block in the database that no promotable `use_evidence` row anchors is not evidence
    anyone recorded, and K1 says *verified quote*, not *extant block*.
  * **Whether the quoted span is really there** is `position(quote in b.text)`, evaluated by
    Postgres on the block's own bytes. It mirrors `litkb/use.py::locate_quote` (exact match, the
    file's CURRENT run only) and, behind that, migration 0007's trigger, which re-reads the block
    at `[char_start, char_end)` and sets `quote_verified`. A Python `in` over a string this module
    fetched would be a third copy of that rule and the one that goes stale (CLAUDE.md 3.3).
  * **Whether the quoted span is the span anyone VERIFIED** is `_verified_span_findings`, and it
    is the difference between K1 as written and K1 as it was first implemented. Being inside the
    block is not enough: a block is a whole paragraph, so a citation verified for its first
    sentence would otherwise carry a quote from its fourth, which nobody checked, under a claim
    about the fourth. The brief's VERIFIED line prints the exact text of `[char_start, char_end)`
    -- the span migration 0007's trigger re-read and marked `quote_verified` -- so the rule is:
    the review's quote is that span, or a substring of it. This comparison is a set membership
    between two strings the brief already handed us, not a second copy of the database's substring
    rule: what it asks is "which verified span is this quote inside", which no query answers.
  * **Which file a workstream can see** is `litkb.ws_files`, not `main_files`: a source admitted
    inside an open workstream is quotable there before anything promotes it
    (decisions.yaml::litkb-web-source-gate), and a grader reading main's view only would refuse
    exactly the citations an unattended run is supposed to be able to make.

WHAT IT CANNOT CHECK, stated here so nobody reads a pass as more than it is: whether the claim a
sentence makes is the claim its quote supports. The grader checks that a verbatim quote from a
verified block sits under every assertion; a sentence can still say something the quote does not.
That judgement is a reader's, and the grammar doc says so in those words.
"""
import re
import uuid

#: `[work_key p.N #block_id]` -- the one citation form (LITKB_REVIEW_GRAMMAR.md §2).
CITATION_RE = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9_.:+-]*) p\.(\d+) #([0-9a-fA-F][0-9a-fA-F-]*)\]")
#: Anything bracket-shaped carrying a '#'. A token the strict form does not match is reported as
#: `malformed-citation` instead of vanishing: a mangled citation must never read as prose that
#: simply had none, because the K1 failure it would raise names the wrong defect.
LOOSE_CITATION_RE = re.compile(r"\[[^\]\n]*#[^\]\n]*\]")
#: `<!-- litkb-review workstream=<id-or-slug> -->` on the review's first non-blank line. The
#: review declares what it was written from; nothing on the command line can point the grader at
#: a different workstream than the document names.
HEADER_RE = re.compile(r"<!--\s*litkb-review\s+workstream=(\S+)\s*-->")

_CLOSERS = '"”'
_OPENERS = '"“'
_LIST_RE = re.compile(r"\s*(?:[-*+]\s|\d+[.)]\s)")
#: A markdown table's delimiter row (`|---|:--:|`). It and the header row above it assert nothing
#: and carry no citation; every other table row in a claim section is a unit -- see `units`.
_DELIM_ROW = re.compile(r"^\|[\s:|-]+\|?\s*$")
#: The citation unit is the SENTENCE (LITKB_REVIEW_GRAMMAR.md §4), not the paragraph -- see
#: `sentences` for why the splitter is this simple and which direction it errs in.
_SENTENCE_SPLIT = re.compile(r"(?<=[.?!])\s+")

#: Headings whose paragraphs assert nothing and therefore carry no citation. Everything else in
#: the document is a CLAIM section. "" is the preamble (title and header). The list is CLOSED and
#: it is the grammar's §1 list -- `_claim_findings` is where it is applied.
NON_CLAIM = ("", "scope", "expectations not supported", "sources")
#: The two sections that are required to exist by name, and the states K2 makes them carry.
EXPECTATIONS_HEADING = "expectations not supported"
SOURCES_HEADING = "sources"
MUST_DISCLOSE = ("contradicted", "unconfirmed")
NOTICE_DISCLOSE = ("open",)


class ReviewGrammarError(SystemExit):
    """The review cannot be graded at all: no workstream header, or a workstream that is not in
    this database. A refusal, not a finding -- there is nothing to grade against."""


def _f(line, code, detail, severity="fail"):
    return {"line": line, "code": code, "detail": detail, "severity": severity}


def fails(findings):
    return [f for f in findings if f["severity"] == "fail"]


def _line_of(text, idx):
    return text.count("\n", 0, idx) + 1


# ── parsing: the grammar, with no database in sight ────────────────────────────────────────


def header_workstream(text):
    """The workstream the review declares, or None."""
    for raw in text.splitlines():
        if raw.strip():
            m = HEADER_RE.search(raw)
            return m.group(1) if m else None
    return None


def _quote_before(text, idx):
    """The verbatim span a citation carries: the `"..."` (or curly) immediately before its `[`.

    Only spaces and tabs may sit between the closing delimiter and the bracket, so a citation
    always follows its own quote on that quote's last line. Returns None when there is no quote
    at all (reported `citation-without-quote`) and "" for an empty one.
    """
    j = idx - 1
    while j >= 0 and text[j] in " \t":
        j -= 1
    if j < 0 or text[j] not in _CLOSERS:
        return None
    k = j - 1
    while k >= 0 and text[k] not in _OPENERS:
        k -= 1
    return None if k < 0 else text[k + 1:j]


def citations(text):
    """Every strict citation token in the document, in order, each with the quote it carries."""
    out = []
    for m in CITATION_RE.finditer(text):
        out.append({"work_key": m.group(1), "page": int(m.group(2)), "block_id": m.group(3),
                    "raw": m.group(0), "quote": _quote_before(text, m.start()),
                    "line": _line_of(text, m.start()), "start": m.start()})
    return out


def sections(text):
    """[(heading-lowercased, first line no, [(line no, line)], [fence-open line no])].

    Split on `##` and deeper. The preamble (before any `##`) is heading "". A deeper heading does
    NOT open a new section: `### Method` inside a claim section stays inside it, so no writer can
    slip a claim paragraph out of K1 by demoting its heading one level.

    Fenced lines are not returned as prose -- a code fence is not a paragraph -- but the line each
    fence OPENS on is, because dropping a fence silently is what let a claim section hold
    assertions no guard could see (`fenced-in-claims`, `_fenced_findings`).
    """
    out = [("", 1, [], [])]
    fenced = False
    for i, raw in enumerate(text.splitlines(), start=1):
        if raw.startswith("## "):
            # A `##` at column 0 ENDS any open fence before it opens the section. Without this an
            # UNCLOSED fence is a way out of K1 that `fenced-in-claims` cannot see: open one in
            # `Scope` -- where the grammar tells writers a code block belongs -- and every later
            # heading is swallowed, so a whole claim section is dropped before a unit is formed
            # while the fence itself is recorded against `scope`, which is not policed. A `##`
            # line inside a genuine code block is the price, and it costs a false FAIL, never a
            # false pass: that fence's closing ``` then OPENS one inside the claim section.
            fenced = False
            out.append((raw[3:].strip().rstrip("#").strip().lower(), i, [], []))
            continue
        if raw.lstrip().startswith("```"):
            if not fenced:
                out[-1][3].append(i)
            fenced = not fenced
            continue
        if fenced or raw.startswith("#"):
            continue
        out[-1][2].append((i, raw))
    return out


def units(lines):
    """The prose units of a section: [(first line no, text)].

    A unit is a run of text the grader looks at as one thing. A blank line ends one; a list marker
    starts one (so a bulleted section is N units, not one, and a single citation cannot cover a
    list of claims); blockquote lines continue the unit above them, because a block quote is how a
    writer shows the quote its sentence cites.

    A TABLE ROW IS ITS OWN UNIT. It used to be dropped as "not prose", and a findings table -- the
    most natural way for a model to present per-year results -- was therefore entirely outside K1
    (the stage-8 audit's E5, measured: a four-row loss table passed with no citation anywhere).
    Two rows are exempt because neither asserts anything: the delimiter row `|---|---|`, and the
    header row it delimits.
    """
    out, cur = [], None
    for i, (no, raw) in enumerate(lines):
        s = raw.strip()
        if not s or s.startswith("<!--"):
            cur = None
            continue
        if s.startswith("|"):
            cur = None
            nxt = lines[i + 1][1].strip() if i + 1 < len(lines) else ""
            if not (_DELIM_ROW.match(s) or _DELIM_ROW.match(nxt)):
                out.append([no, s])
            continue
        if _LIST_RE.match(raw):
            out.append([no, s])
            cur = out[-1]
            continue
        if cur is None:
            out.append([no, s])
            cur = out[-1]
        else:
            cur[1] += "\n" + s
    return [(no, txt) for no, txt in out]


def _protected(txt):
    """[(start, end)] of the spans a sentence split may not cut: a strict citation together with
    the verbatim quote immediately before it. See `sentences`."""
    out = []
    for m in CITATION_RE.finditer(txt):
        j = m.start() - 1
        while j >= 0 and txt[j] in " \t":
            j -= 1
        k = -1
        if j >= 0 and txt[j] in _CLOSERS:
            k = j - 1
            while k >= 0 and txt[k] not in _OPENERS:
                k -= 1
        out.append((k if k >= 0 else m.start(), m.end()))
    return out


def sentences(txt):
    """The SENTENCES of a unit -- the thing K1 is enforced per, since 2026-09-20.

    It was the paragraph, and the audit measured what that cost: `Canopy fell 40 percent. Two
    species vanished. The work states it: "<quote>" [cite].` passed, three assertions deep, on one
    citation attached to the fourth. A simple splitter on `.`/`?`/`!` + whitespace is deliberate:
    an abbreviation ("et al.", "e.g.") splits a sentence it should not have, and the extra unit
    then has no citation and FAILS. That direction is the safe one, and the grammar tells writers
    to keep the citation in the fragment or spell the abbreviation out.

    The one place it does not split is inside a strict citation's own quote: that text is compared
    byte-for-byte against a VERIFIED span, so a sentence boundary inside it is the PAPER's, not
    the review's, and cutting there would make a faithfully-copied two-sentence quote unwritable.
    """
    spans = _protected(txt)
    out, start = [], 0
    for m in _SENTENCE_SPLIT.finditer(txt):
        if any(a < m.start() < b for a, b in spans):
            continue
        if txt[start:m.start()].strip():
            out.append(txt[start:m.start()])
        start = m.end()
    if txt[start:].strip():
        out.append(txt[start:])
    return out or [txt]


# ── the guards: one BEGIN/END block per kill, each with a row in the mutation harness ───────


def _location_findings(c, row):
    """RC1. The citation names a block this workstream can see, carrying the key and the page it
    claims. `row` is None when no such block is visible."""
    # BEGIN guard: a citation resolves to a visible block at the work key and page it names
    if row is None:
        return [_f(c["line"], "block-not-found",
                   f"{c['raw']}: no block {c['block_id']} in this workstream's view of the "
                   "current extraction run of any active file")]
    if row["work_key"] != c["work_key"]:
        return [_f(c["line"], "work-mismatch",
                   f"{c['raw']}: block {c['block_id']} belongs to {row['work_key']}, "
                   f"not {c['work_key']}")]
    if row["page_no"] != c["page"]:
        return [_f(c["line"], "page-mismatch",
                   f"{c['raw']}: block {c['block_id']} is on page {row['page_no']}, "
                   f"not p.{c['page']}")]
    # END guard: a citation resolves to a visible block at the work key and page it names
    return []


def _verbatim_findings(c, row):
    """RC2. The span the citation carries is VERBATIM in that block's own text -- the database's
    own `position()` over the block bytes, the rule use.locate_quote and migration 0007 apply."""
    # BEGIN guard: the quoted span is verbatim in the cited block's text
    if not c["quote"]:
        return [_f(c["line"], "citation-without-quote",
                   f"{c['raw']}: no verbatim quote immediately before the citation")]
    if row is not None and not row["quote_in_block"]:
        return [_f(c["line"], "quote-not-verbatim",
                   f"{c['raw']}: the quoted span is not a substring of block "
                   f"{c['block_id']}'s text (the database looked)")]
    # END guard: the quoted span is verbatim in the cited block's text
    return []


def _in_brief_findings(c, brief_triples):
    """RC3. The citation is one of the workstream's VERIFIED lines. A real block that no
    promotable use_evidence row anchors is not what K1 means by a verified quote."""
    # BEGIN guard: every citation names a VERIFIED line of this workstream's brief
    if (c["work_key"], c["page"], c["block_id"]) not in brief_triples:
        return [_f(c["line"], "not-in-brief",
                   f"{c['raw']}: no VERIFIED line of this workstream's brief carries "
                   "(work key, page, block id) -- the writer cited outside its brief")]
    # END guard: every citation names a VERIFIED line of this workstream's brief
    return []


def _verified_span_findings(c, brief_spans):
    """RC8. The quoted text lies WITHIN a span the brief verified for that block -- it is the
    VERIFIED quote itself, or a substring of it.

    `brief_spans` maps (work key, page, block id) -> the set of VERIFIED quote texts the brief
    prints for it; each is the exact `[char_start, char_end)` of a promotable `use_evidence` row,
    the span migration 0007's trigger re-read and marked `quote_verified`. A triple absent from
    the map is `not-in-brief`'s business, not this guard's: the two name different defects (no
    evidence at all on that block, versus evidence that does not cover these words).
    """
    # BEGIN guard: the quoted span lies inside a span the brief VERIFIED, not merely inside the block
    spans = brief_spans.get((c["work_key"], c["page"], c["block_id"]))
    if spans is not None and not (c["quote"] and any(c["quote"] in s for s in spans)):
        return [_f(c["line"], "quote-not-verified-span",
                   f"{c['raw']}: the quoted span is not inside any VERIFIED span of this block "
                   "-- it may be in the block, but no promotable use_evidence row covers these "
                   "words, so nothing verified them")]
    # END guard: the quoted span lies inside a span the brief VERIFIED, not merely inside the block
    return []


def _claim_findings(text):
    """RC4 = K1. Every SENTENCE of every unit of a claim section carries at least one citation,
    and no citation appears in a section K1 does not police.

    The second half is the tell. K1 cannot see an uncited sentence in `Scope` -- by construction:
    those sections exist for the writer's own words, and the grammar says in as many words that a
    literature fact asserted there is a violation the grader is blind to. What it CAN see is a
    claim that was MOVED there, because a claim carries its citation with it: a citation token in
    any non-claim section, or a quoted span in the preamble or `Scope`, is refused.
    """
    out = []
    # BEGIN guard: K1 -- every claim sentence carries a citation, and no citation sits in a non-claim section
    for heading, _hl, lines, _fences in sections(text):
        body = units(lines)
        if heading in NON_CLAIM:
            for no, txt in body:
                quoted = heading in ("", "scope") and (_CLOSERS[0] in txt or _OPENERS[1] in txt)
                if CITATION_RE.search(txt) or quoted:
                    out.append(_f(no, "claim-outside-claim-section",
                                  f"a citation or a quoted span in the '{heading or 'preamble'}' "
                                  "section, which K1 does not police: claims belong in a "
                                  "claim section"))
            continue
        for no, txt in body:
            for sent in sentences(txt):
                if not CITATION_RE.search(sent):
                    out.append(_f(no, "uncited-claim",
                                  f"sentence in '{heading}' asserts without a citation: "
                                  f"{sent.strip()[:90]!r}"))
    # END guard: K1 -- every claim sentence carries a citation, and no citation sits in a non-claim section
    return out


def _fenced_findings(text):
    """RC9. A fenced code block inside a claim section is a FAILURE, not invisible text.

    `sections` drops fenced lines before any unit is formed, so everything a writer puts in a
    fence was outside K1 entirely (the audit's E6, measured). Refusing the fence rather than
    grading its contents is the choice that cannot be gamed: fenced text has no sentences to
    police, and a review needing a code block has a non-claim section to put it in.
    """
    out = []
    # BEGIN guard: a fenced block inside a claim section is refused, never graded as absent
    for heading, _hl, _lines, fences in sections(text):
        if heading in NON_CLAIM:
            continue
        for no in fences:
            out.append(_f(no, "fenced-in-claims",
                          f"a fenced code block opens in claim section '{heading}': fenced text "
                          "carries no citation and K1 cannot see it. Put it in Scope, or write "
                          "the claim as a cited sentence"))
    # END guard: a fenced block inside a claim section is refused, never graded as absent
    return out


def _expectation_findings(text, expected):
    """RC5 = K2. The 'Expectations not supported' section exists, and every expectation the
    database resolved CONTRADICTED or UNCONFIRMED is named in it by hunt_request id or by ref.

    This is the load-bearing half of the operational definition: a review in which the machinery
    fired and the document did not say so is exactly the failure `hunt_request` exists to catch.
    An `open` expectation is a NOTICE -- it was never linked to a work, so nothing has yet
    contradicted it, and the grammar still asks the writer to list it.
    """
    out = []
    # BEGIN guard: K2 -- the section exists and names every contradicted/unconfirmed expectation
    found = [(h, hl, ls) for h, hl, ls, _fn in sections(text) if h == EXPECTATIONS_HEADING]
    if not found:
        return [_f(1, "missing-expectations-section",
                   f"no '## {EXPECTATIONS_HEADING.title()}' section: K2 requires the review to "
                   "state what its own expectations failed to support")]
    body = "\n".join(t for _h, _hl, ls in found for _n, t in ls)
    for e in expected:
        state = (e.get("resolution_state") or "").lower()
        if state not in MUST_DISCLOSE and state not in NOTICE_DISCLOSE:
            continue
        named = (e.get("hunt_request_id") or "") in body or (e.get("ref") or "") in body
        if not named:
            out.append(_f(found[0][1],
                          "expectation-not-disclosed",
                          f"hunt_request {e.get('hunt_request_id')} ({e.get('ref')}) came back "
                          f"{state.upper()} and is not named in '{EXPECTATIONS_HEADING}': "
                          f"expected claim {str(e.get('expected_claim'))[:80]!r}",
                          "fail" if state in MUST_DISCLOSE else "notice"))
    # END guard: K2 -- the section exists and names every contradicted/unconfirmed expectation
    return out


def _never_fired_findings(expected):
    """RC10 = K2's FIRST half. The workstream must HOLD at least one expectation the database
    resolved CONTRADICTED or UNCONFIRMED.

    `expected` is the brief's own EXPECTED set, which `brief._require_every_hunt_request` refuses
    to shorten -- so this counts the workstream's whole ledger, not a filtered view of it. A run
    in which every drop-off came back confirmed has not exercised the honesty machinery at all,
    and a green grade on its review would report that the machinery worked.
    """
    # BEGIN guard: K2 first half -- the workstream holds an expectation that came back unsupported
    if not any((e.get("resolution_state") or "").lower() in MUST_DISCLOSE for e in expected):
        return [_f(1, "k2-never-fired",
                   "this workstream holds no hunt_request in state "
                   f"{'/'.join(MUST_DISCLOSE)} ({len(expected)} recorded): K2 requires at least "
                   "one dropped-off expectation to COME BACK unsupported, not merely that the "
                   "review would have disclosed one. Nothing here contradicts or fails to confirm "
                   "anything, so the review's Expectations section proves nothing about the run")]
    # END guard: K2 first half -- the workstream holds an expectation that came back unsupported
    return []


def _sources_findings(text, cited_keys):
    """RC6. Every work the body cites is listed in the Sources table, and the table lists nothing
    the body never cited (a notice: an unread source in a bibliography is a smaller sin than an
    uncited claim, but it is still a source the review did not use)."""
    out = []
    # BEGIN guard: every cited work key is listed in Sources, and Sources lists no work the body never cited
    found = [(h, hl, ls) for h, hl, ls, _fn in sections(text) if h == SOURCES_HEADING]
    if not found:
        return [_f(1, "missing-sources-section",
                   f"no '## {SOURCES_HEADING.title()}' section")]
    hl = found[0][1]
    body = "\n".join(t for _h, _l, ls in found for _n, t in ls)
    for key in sorted(cited_keys):
        if key not in body:
            out.append(_f(hl, "source-not-listed",
                          f"{key} is cited in the body and absent from the Sources table"))
    for m in re.finditer(r"`([A-Za-z0-9][A-Za-z0-9_.:+-]*)`", body):
        if m.group(1) not in cited_keys:
            out.append(_f(hl, "source-never-cited",
                          f"{m.group(1)} is listed in Sources and cited nowhere in the body",
                          "notice"))
    # END guard: every cited work key is listed in Sources, and Sources lists no work the body never cited
    return out


def _malformed_findings(text, strict):
    """RC7. A bracket-shaped token carrying a '#' that the strict form did not match. Without
    this, a mangled citation is invisible and its paragraph fails as `uncited-claim`, which
    names the wrong defect and sends the writer to fix the wrong thing."""
    out = []
    # BEGIN guard: a citation-shaped token the strict grammar rejected is named, never ignored
    ok = {c["start"] for c in strict}
    for m in LOOSE_CITATION_RE.finditer(text):
        if m.start() in ok:
            continue
        out.append(_f(_line_of(text, m.start()), "malformed-citation",
                      f"{m.group(0)!r} is not `[work_key p.N #block_id]`"))
    # END guard: a citation-shaped token the strict grammar rejected is named, never ignored
    return out


# ── the database side ──────────────────────────────────────────────────────────────────────


_BLOCK_SQL = """
SELECT b.page_no, wk.key, coalesce(position(%(q)s in b.text) > 0, false)
  FROM litkb.blocks b
  JOIN litkb.files f ON f.id = b.file_id AND f.current_run_id = b.run_id
  JOIN litkb.ws_files wf ON wf.file_id = f.id AND wf.view_workstream_id = %(ws)s
                        AND wf.status = 'active'
  JOIN litkb.works wk ON wk.id = wf.work_id
 WHERE b.id = %(bid)s::uuid
"""


def _block_row(conn, ws, block_id, quote):
    """The cited block as this workstream sees it, or None. The substring test is Postgres's
    (`position`), on the block's own bytes -- see the module docstring."""
    try:
        uuid.UUID(block_id)
    except ValueError:
        return None
    row = conn.execute(_BLOCK_SQL, {"ws": ws, "bid": block_id, "q": quote or ""}).fetchone()
    return None if not row else {"page_no": row[0], "work_key": row[1], "quote_in_block": row[2]}


def resolve_workstream(conn, ref):
    """id-or-slug -> (id, slug). Raises ReviewGrammarError when this database has no such row."""
    row = conn.execute(
        "SELECT id, slug FROM litkb.workstreams WHERE id::text = %s OR slug = %s",
        (ref, ref)).fetchone()
    if not row:
        raise ReviewGrammarError(f"litkb review-check: no workstream {ref!r} (id or slug)")
    return row[0], row[1]


def check(conn, path_or_text, *, is_text=False, k2_workstream=None):
    """Every finding against this review. [] means it passed; `fails()` is what sets the exit code.

    The brief is built with `litkb.brief.build`, so this grader inherits that export's own gates
    (HB1: a VERIFIED line always carries its location; HB2: no expectation is silently dropped).
    A `BriefInvariantError` is deliberately NOT caught: a brief the exporter would not stand
    behind is not a brief a review can be graded against.

    `k2_workstream` (the CLI's `--workstream`) does NOT redirect the grade: it is an ASSERTION
    that the workstream the caller believes it is grading is the one the document declares, and a
    mismatch is refused. Counting K2's negatives in another workstream's ledger would prove
    nothing about this review, which is the same reason the header is the only place a workstream
    is named (LITKB_REVIEW_GRAMMAR.md §1).
    """
    from litkb import brief as _brief

    text = path_or_text if is_text else _read(path_or_text)
    ref = header_workstream(text)
    if not ref:
        raise ReviewGrammarError(
            "litkb review-check: the review's first non-blank line must be "
            "'<!-- litkb-review workstream=<id-or-slug> -->' (LITKB_REVIEW_GRAMMAR.md §1)")
    ws, _slug = resolve_workstream(conn, ref)
    if k2_workstream is not None:
        named, named_slug = resolve_workstream(conn, k2_workstream)
        if str(named) != str(ws):
            raise ReviewGrammarError(
                f"litkb review-check: --workstream {k2_workstream!r} is {named} ({named_slug}), "
                f"but the review's header declares {ws} ({_slug}). The grade is always against "
                "the workstream the document names; the flag only asserts which one that is")
    expected, verified = _brief.build(conn, ws)
    spans = {}
    for v in verified:
        spans.setdefault((v["work_key"], v["page"], v["block_id"]), set()).add(v["quote"])

    cits = citations(text)
    out = list(_malformed_findings(text, cits))
    for c in cits:
        row = _block_row(conn, ws, c["block_id"], c["quote"])
        out += _location_findings(c, row)
        out += _verbatim_findings(c, row)
        out += _in_brief_findings(c, set(spans))
        out += _verified_span_findings(c, spans)
    out += _claim_findings(text)
    out += _fenced_findings(text)
    out += _expectation_findings(text, expected)
    out += _never_fired_findings(expected)
    out += _sources_findings(text, {c["work_key"] for c in cits})
    return sorted(out, key=lambda f: (f["line"], f["code"]))


def _read(path):
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        raise ReviewGrammarError(f"litkb review-check: no such review {p}")
    # NEWLINE TRANSLATION OFF. `read_text` is universal-newlines: it turns every CRLF in the file
    # into a bare LF before the grader sees a byte, while the block's stored text keeps its CRLF.
    # A quote spanning a line break on such a block then passed in-process and failed through the
    # command line, on the same bytes -- the quote is compared byte-for-byte (Postgres
    # `position()`), so the reader may not rewrite it. `Path.read_text` has no `newline=`
    # parameter, hence the explicit open (LITKB_REVIEW_GRAMMAR.md §2).
    with p.open(encoding="utf-8", newline="") as fh:
        return fh.read()
