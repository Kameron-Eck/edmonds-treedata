"""litkb review-check -- the DETERMINISTIC gate on a written review (stage 8: brief -> review).

    findings = check(conn, path)         # [] means the review passed K1 and K2
    rc = 0 if not fails(findings) else 1

`decisions.yaml::litkb-operational-definition` fixes what "operational" means and states the two
kill criteria, quoted here as the decision words them:

  K1  any claim in the review that does not trace to a VERIFIED quote (work key + page +
      block_id) = FAIL.
  K2  at least one dropped-off expectation must come back CONTRADICTED or UNCONFIRMED **and the
      review must SAY so** -- the honesty machinery is required to FIRE, not merely to exist.

K1 IS ENFORCED HERE IN FULL. **K2 IS NOT, AND THIS FILE IS NOT THE WHOLE GATE.** What
`_expectation_findings` decides is the second clause: *given* an expectation the database resolved
CONTRADICTED or UNCONFIRMED, is it named in the review's own section. The first clause -- that at
least one expectation came back that way AT ALL -- is a property of the RUN, not of the document:
a workstream holding no such expectation produces a review with nothing to disclose, and this
module returns no finding for it. Whoever grades a proving run therefore needs BOTH this command's
exit code AND a count from the workstream:

    py -3.12 -m litkb hunt-request list --state contradicted
    py -3.12 -m litkb hunt-request list --state unconfirmed      # > 0 rows, or K2's first half
                                                                 # was never exercised

Written here rather than left implicit because a reader who takes a green `review-check` for the
whole of K2 would conclude the honesty machinery fired when it may simply have had nothing to fire
on -- which is the exact failure the operational definition calls load-bearing.

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

#: Headings whose paragraphs assert nothing and therefore carry no citation. Everything else in
#: the document is a CLAIM section. "" is the preamble (title and header) -- see `_claims_only`.
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
    """[(heading-lowercased, first line no, [(line no, line)])] -- split on `##` and deeper.

    The preamble (before any `##`) is heading "". A deeper heading does NOT open a new section:
    `### Method` inside a claim section stays inside it, so no writer can slip a claim paragraph
    out of K1 by demoting its heading one level.
    """
    out = [("", 1, [])]
    fenced = False
    for i, raw in enumerate(text.splitlines(), start=1):
        if raw.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced and raw.startswith("## "):
            out.append((raw[3:].strip().rstrip("#").strip().lower(), i, []))
            continue
        if fenced or raw.startswith("#"):
            continue
        out[-1][2].append((i, raw))
    return out


def units(lines):
    """The prose units of a section: [(first line no, text)].

    A unit is what must carry a citation. A blank line ends one; a list marker starts one (so a
    bulleted section is N units, not one, and a single citation cannot cover a list of claims);
    a table row, an HTML comment and a heading are not prose and belong to no unit. Blockquote
    lines continue the unit above them, because a block quote is how a writer shows the quote
    its sentence cites.
    """
    out, cur = [], None
    for no, raw in lines:
        s = raw.strip()
        if not s or s.startswith("|") or s.startswith("<!--"):
            cur = None
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


def _claim_findings(text):
    """RC4 = K1. Every prose unit of a claim section carries at least one citation, and no claim
    leaks into the two sections K1 does not police (the preamble and Scope), which is the one way
    a writer could satisfy K1 by relabelling its claims as scope."""
    out = []
    # BEGIN guard: K1 -- every claim paragraph carries a citation, and claims live only in claim sections
    for heading, _hl, lines in sections(text):
        body = [(no, txt) for no, txt in units(lines)]
        if heading in NON_CLAIM:
            if heading in ("", "scope"):
                for no, txt in body:
                    if CITATION_RE.search(txt) or _CLOSERS[0] in txt or _OPENERS[1] in txt:
                        out.append(_f(no, "claim-outside-claim-section",
                                      f"a citation or a quoted span in the '{heading or 'preamble'}' "
                                      "section, which K1 does not police: claims belong in a "
                                      "claim section"))
            continue
        for no, txt in body:
            if not CITATION_RE.search(txt):
                out.append(_f(no, "uncited-claim",
                              f"paragraph in '{heading}' asserts without a citation: {txt[:90]!r}"))
    # END guard: K1 -- every claim paragraph carries a citation, and claims live only in claim sections
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
    found = [(h, hl, ls) for h, hl, ls in sections(text) if h == EXPECTATIONS_HEADING]
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


def _sources_findings(text, cited_keys):
    """RC6. Every work the body cites is listed in the Sources table, and the table lists nothing
    the body never cited (a notice: an unread source in a bibliography is a smaller sin than an
    uncited claim, but it is still a source the review did not use)."""
    out = []
    # BEGIN guard: every cited work key is listed in Sources, and Sources lists no work the body never cited
    found = [(h, hl, ls) for h, hl, ls in sections(text) if h == SOURCES_HEADING]
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


def check(conn, path_or_text, *, is_text=False):
    """Every finding against this review. [] means it passed; `fails()` is what sets the exit code.

    The brief is built with `litkb.brief.build`, so this grader inherits that export's own gates
    (HB1: a VERIFIED line always carries its location; HB2: no expectation is silently dropped).
    A `BriefInvariantError` is deliberately NOT caught: a brief the exporter would not stand
    behind is not a brief a review can be graded against.
    """
    from litkb import brief as _brief

    text = path_or_text if is_text else _read(path_or_text)
    ref = header_workstream(text)
    if not ref:
        raise ReviewGrammarError(
            "litkb review-check: the review's first non-blank line must be "
            "'<!-- litkb-review workstream=<id-or-slug> -->' (LITKB_REVIEW_GRAMMAR.md §1)")
    ws, _slug = resolve_workstream(conn, ref)
    expected, verified = _brief.build(conn, ws)
    triples = {(v["work_key"], v["page"], v["block_id"]) for v in verified}

    cits = citations(text)
    out = list(_malformed_findings(text, cits))
    for c in cits:
        row = _block_row(conn, ws, c["block_id"], c["quote"])
        out += _location_findings(c, row)
        out += _verbatim_findings(c, row)
        out += _in_brief_findings(c, triples)
    out += _claim_findings(text)
    out += _expectation_findings(text, expected)
    out += _sources_findings(text, {c["work_key"] for c in cits})
    return sorted(out, key=lambda f: (f["line"], f["code"]))


def _read(path):
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        raise ReviewGrammarError(f"litkb review-check: no such review {p}")
    return p.read_text(encoding="utf-8")
