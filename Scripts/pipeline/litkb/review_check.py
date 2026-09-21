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
    ONE thing is canonicalised before that comparison, on BOTH sides: the LINE ENDING encoding
    (`textnorm.canonical_newlines`, and `_CANON_TEXT` for the block). 48.9 % of current-run blocks
    carry `\r\n` and 7 of the project's 8 verified spans cross one, so the rule "quote within one
    stored line" truncated almost every existing verified quote -- once to 33 characters that
    assert nothing -- and the only alternative it left was an LLM writer emitting a raw CR byte,
    which nobody has ever observed. Content still has to match byte for byte; only the encoding of
    a line break may differ (LITKB_REVIEW_GRAMMAR.md §2).
  * **Whether the quoted span is the span anyone VERIFIED** is `_verified_span_findings`, and it
    is the difference between K1 as written and K1 as it was first implemented. Being inside the
    block is not enough: a block is a whole paragraph, so a citation verified for its first
    sentence would otherwise carry a quote from its fourth, which nobody checked, under a claim
    about the fourth. The brief's VERIFIED line prints the stored quote of `[char_start,
    char_end)` -- the span the verify trigger re-read and marked `quote_verified`, equal to it in
    every character and every break POSITION and possibly not in how a break is ENCODED (migration
    0026, and the brief canonicalises what it prints anyway) -- so the rule is:
    the review's quote is that span, or a substring of it. This comparison is a set membership
    between two strings the brief already handed us, not a second copy of the database's substring
    rule: what it asks is "which verified span is this quote inside", which no query answers.
  * **Which file a workstream can see** is `litkb.ws_files`, not `main_files`: a source admitted
    inside an open workstream is quotable there before anything promotes it
    (decisions.yaml::litkb-web-source-gate), and a grader reading main's view only would refuse
    exactly the citations an unattended run is supposed to be able to make.

WHAT IT CANNOT CHECK, stated here so nobody reads a pass as more than it is:

  * **Whether the claim a sentence makes is the claim its quote supports.** The grader checks that
    a verbatim quote from a verified block sits under every assertion; a sentence can still say
    something the quote does not. That judgement is a reader's, and the grammar doc says so in
    those words.
  * **Whether a disclosure is COMPLETE.** `_expectation_findings` proves that every contradicted
    or unconfirmed expectation is NAMED; nothing here can ask whether the entry tells the whole of
    what its cited blocks hold. The proving run's Kaiser entry named two losses and omitted, from
    the very block it cited for them, that the OSM-only model still beat the smaller baseline by
    1.5 percent points -- honest, and not the full picture (codex-review-proving-run2.md §2).
    Grammar §5 requires the partial support to be named; only a reader can check that it was.
"""
import re
import uuid

from litkb.textnorm import canonical_newlines, sql_canonical_newlines

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
#: The shortest quote that may carry a claim, in CANONICALISED characters. See
#: `_quote_length_findings`: below this the quote is a fragment inside almost every verified span.
#: The corpus number behind the choice: verified spans run 83-295 characters (median 150), and the
#: longest newline-free run inside a paragraph block has median 68 -- so 25 refuses the degenerate
#: end without reaching anything a writer would legitimately quote.
MIN_QUOTE_CHARS = 25
#: The longest heading that is still a LABEL rather than an assertion, in words. It governs BOTH
#: a `###`-or-deeper heading (`_deep_heading_findings`) and a claim section's own `##` title
#: (`_title_findings`).
HEADING_LABEL_WORDS = 6
#: The ONE sentence a review may write in `Scope` about its OWN sourcing, verbatim.
#:
#: It is RENDERED for the writer in exactly two places, both as a FENCED CODE BLOCK and never as
#: a block quote, a list item or bold text: LITKB_REVIEW_GRAMMAR.md §1 and
#: `.claude/agents/review-writer.md`. `test_the_scope_template_is_rendered_copy_exact` compares
#: both fences to this constant BYTE FOR BYTE, with no stripping of any kind, because that is the
#: only comparison that proves what a writer copying the displayed text actually gets.
#:
#: The fence is not cosmetic. Until 2026-09-20 the one rendered copy was a wrapped markdown block
#: quote, so the sentence a writer could see began `> ` -- and auditor-6 measured that copying it
#: as displayed FAILED `scope-self-claim` naming `outside`, while the binding test stripped the
#: `>` that `_scope_findings` does not. The test passed over the exact mismatch it existed to
#: prevent. Narrowing the vocabulary below happens to remove that sentence's refused word, so the
#: `> ` copy no longer fails; the fence is what stops the next widening from re-opening it.
#:
#: It carries no apostrophe and no quotation mark for the same class of reason: a writer that
#: renders `'` as `’` would produce a sentence the grader cannot match, and the failure would
#: name the wrong defect.
SCOPE_TEMPLATE = ("Every citation in this review names a VERIFIED line of the brief for this "
                  "workstream; nothing outside that brief is cited.")
#: The terms that make a `Scope` sentence a claim about the review's own SOURCING. Three, and
#: each one names a SOURCE the review might claim to have used or avoided -- not a quantity, a
#: place or a measurement. See `_scope_findings` for what that boundary cost to find, and grammar
#: §7 for what escapes it in both directions.
#:
#: The boundary is `[A-Za-z0-9]` and NOT `\b`, so `_` reads as a boundary: `abstract_passage` --
#: the field name both docs tell writers to use -- matches, where `\babstract\b` did not, because
#: `_` is a word character (auditor-6 §2, measured). `abstracts` still escapes, by the same rule
#: in the other direction, and §7 says so.
_SELF_CLAIM_RE = re.compile(r"(?<![A-Za-z0-9])(abstract|memory|knowledge\s+base)(?![A-Za-z0-9])",
                            re.IGNORECASE)


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
    """[(heading-lowercased, first line no, [(line no, line)], [fence-open line no],
        [(line no, heading text)])].

    Split on `##` and deeper. The preamble (before any `##`) is heading "". A deeper heading does
    NOT open a new section: `### Method` inside a claim section stays inside it, so no writer can
    slip a claim paragraph out of K1 by demoting its heading one level.

    Fenced lines are not returned as prose -- a code fence is not a paragraph -- but the line each
    fence OPENS on is, because dropping a fence silently is what let a claim section hold
    assertions no guard could see (`fenced-in-claims`, `_fenced_findings`).

    THE FIFTH ELEMENT is every OTHER `#`-prefixed line of the section: `###` and deeper, and also
    a `#`-with-no-space line, which is not a heading to a markdown renderer at all. They are kept
    apart from prose rather than dropped, because dropping them was the same class of hole as the
    fence: the docstring above is true of the PARAGRAPH under a demoted heading and was false of
    the HEADING TEXT ITSELF, so `### Edmonds lost four fifths of its canopy` was never graded
    (auditor-3b-stage8-fixes.md §1.9, measured). `_deep_heading_findings` grades them.
    """
    out = [("", 1, [], [], [])]
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
            out.append((raw[3:].strip().rstrip("#").strip().lower(), i, [], [], []))
            continue
        if raw.lstrip().startswith("```"):
            if not fenced:
                out[-1][3].append(i)
            fenced = not fenced
            continue
        if fenced:
            continue
        if raw.startswith("#"):
            out[-1][4].append((i, raw.lstrip("#").strip().rstrip("#").strip()))
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
    own `position()` over the block bytes, the rule use.locate_quote and migration 0007 apply,
    with the line ENDING encoding canonicalised on both sides (see `_block_row`)."""
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
    prints for it; each is the `[char_start, char_end)` of a promotable `use_evidence` row -- the
    span the verify trigger re-read and marked `quote_verified`, which since migration 0026 may
    differ from the stored bytes in the ENCODING of a line break and in nothing else (and this
    guard canonicalises both sides anyway, below). A triple absent from
    the map is `not-in-brief`'s business, not this guard's: the two name different defects (no
    evidence at all on that block, versus evidence that does not cover these words).

    CONTAINMENT IS TESTED ON THE CANONICALISED SPAN TEXT, not on the block with offsets mapped.
    Both are available; this one is the one whose correctness is a one-line argument.
    `canonical_newlines` rewrites line ENDINGS and nothing else, so it preserves every
    non-newline character, their order, and the number of breaks -- therefore
    `canon(quote) in canon(span)` holds exactly when the quote and that part of the span agree on
    every character and every break POSITION and differ only in how the breaks are ENCODED. The
    offset route would have had to map `char_start`/`char_end` through a length-changing rewrite
    of the block, which is more code for the same answer and a place for an off-by-one to hide.
    """
    # BEGIN guard: the quoted span lies inside a span the brief VERIFIED, not merely inside the block
    spans = brief_spans.get((c["work_key"], c["page"], c["block_id"]))
    quote = canonical_newlines(c["quote"])
    if spans is not None and not (quote and any(quote in canonical_newlines(s) for s in spans)):
        return [_f(c["line"], "quote-not-verified-span",
                   f"{c['raw']}: the quoted span is not inside any VERIFIED span of this block "
                   "-- it may be in the block, but no promotable use_evidence row covers these "
                   "words, so nothing verified them")]
    # END guard: the quoted span lies inside a span the brief VERIFIED, not merely inside the block
    return []


def _quote_length_findings(c):
    """RC11. A citation's quote must be long enough to be evidence of something.

    Measured on the fixed grader (auditor-3b-stage8-fixes.md §1.6): `" "` -- a single space --
    is a substring of essentially every verified span, so one space plus a real citation token
    satisfied every byte-exact guard in this file, under any claim at all. `'C'`, `'by'` and
    `' '` all passed under the invented claim *"Edmonds lost four fifths of its canopy and every
    conifer died"*. Length is not fidelity, and no threshold makes a quote support a sentence
    (that is grammar §7's disclosure and always will be); what it does is close the degenerate
    end, where the quote carries no information at all.

    The floor is on the CANONICALISED quote, so a line break costs one character and not two --
    the same text may not pass or fail on which machine wrote the file.
    """
    # BEGIN guard: a citation's quote is long enough to carry information
    q = canonical_newlines(c["quote"]) or ""
    if q and len(q) < MIN_QUOTE_CHARS:
        return [_f(c["line"], "quote-too-short",
                   f"{c['raw']}: the quote is {len(q)} character(s), under the {MIN_QUOTE_CHARS} "
                   f"this grammar requires ({q!r}). A fragment that short is inside almost every "
                   "verified span and is evidence of nothing; quote the words that carry the "
                   "claim")]
    # END guard: a citation's quote is long enough to carry information
    return []


def _duplicate_section_findings(text):
    """RC12. A non-claim section name may appear ONCE in the document.

    `NON_CLAIM` is matched per heading OCCURRENCE, so a second `## Scope` anywhere turned
    everything after it into unpoliced prose until the next heading -- the writer did not even
    have to move its claims up into the section a reader inspects, it could open a fresh `##
    Scope` under its findings and keep writing (auditor-3b-stage8-fixes.md §1.7, measured: a
    document with uncited claims under a second `## Scope` returned 0 findings). Grammar §1 says
    the four non-claim sections are a closed set of NAMES; this is what makes each a single
    section as well.

    Only the non-claim names are policed. Two claim sections may share a name: both are graded,
    so nothing hides in the second one.
    """
    out = []
    # BEGIN guard: a non-claim section name opens at most once in the document
    seen = {}
    for heading, hl, _lines, _fences, _deep in sections(text):
        if not heading or heading not in NON_CLAIM:
            continue
        if heading in seen:
            out.append(_f(hl, "duplicate-section",
                          f"'## {heading}' opens again at line {hl} (already open at line "
                          f"{seen[heading]}): a non-claim section is where K1 cannot look, so a "
                          "second one re-opens that blind spot below the findings"))
        else:
            seen[heading] = hl
    # END guard: a non-claim section name opens at most once in the document
    return out


def _deep_heading_findings(text):
    """RC13. A `###`-or-deeper heading in a claim section is graded like any other unit.

    `sections` dropped every `#`-prefixed line before a unit was formed, so a section heading --
    the most natural place for a model to put a summary assertion ("### Canopy fell by 11
    percent, 2000-2020") -- was never graded at all, and neither was a `#Edmonds lost...` line,
    which is not a heading to a renderer either (auditor-3b-stage8-fixes.md §1.9, both measured
    as PASS). Same class as the fence: text dropped before K1 could see it.

    A heading of `MIN`-or-fewer words is exempt, because a heading that short is a LABEL for the
    section under it ("### Method", "### 2005-2012") and cannot carry a finding. Above that, it
    asserts, and an assertion carries a citation wherever it sits.
    """
    out = []
    # BEGIN guard: a deep heading in a claim section asserts nothing without a citation
    for heading, _hl, _lines, _fences, deep in sections(text):
        if heading in NON_CLAIM:
            continue
        for no, txt in deep:
            if len(txt.split()) <= HEADING_LABEL_WORDS or CITATION_RE.search(txt):
                continue
            out.append(_f(no, "uncited-heading",
                          f"a heading in claim section '{heading}' asserts without a citation: "
                          f"{txt[:90]!r}. A heading of more than {HEADING_LABEL_WORDS} words is a "
                          "finding, not a label: cite it, shorten it, or write it as a sentence"))
    # END guard: a deep heading in a claim section asserts nothing without a citation
    return out


def _title_findings(text):
    """RC26. A CLAIM SECTION'S OWN `##` TITLE is a label too, and it has no citation escape.

    `_deep_heading_findings` graded `###` and deeper and stopped there, so the one heading a
    review is certain to have -- the section title itself -- was the one heading nothing looked
    at. The proving run wrote `## Canopy reference products and imagery that spans dates` over a
    section whose own body, and whose own ledger entry, say the "reference product" half of that
    expectation was never confirmed (codex-review-proving-run2.md §2). Every citation in it was
    SUPPORTED; the status was asserted by the title, where no guard was.

    Two differences from the deep-heading rule, both because a `##` line is a section boundary and
    not prose:

    * **No citation exempts it.** `sections()` opens a new section on a `## ` line and never hands
      that text to `units()`, so a citation written into a title is half-graded -- `citations()`
      finds it, so RC1/RC2/RC3/RC8/RC11 all run on it, while K1 never sees the sentence it is
      supposed to support. A title therefore cannot carry evidence at all, and the only honest
      title is a LABEL: `HEADING_LABEL_WORDS` words or fewer.
    * **Non-claim titles are not graded**, and cannot be: their four names are fixed by grammar
      §1, they are the same on every review, and each is already at most four words.
    """
    out = []
    # BEGIN guard: a claim section's title is a label, not an assertion
    raw = text.splitlines()
    for heading, hl, _lines, _fences, _deep in sections(text):
        if heading in NON_CLAIM or len(heading.split()) <= HEADING_LABEL_WORDS:
            continue
        shown = raw[hl - 1].strip() if 0 < hl <= len(raw) else heading
        out.append(_f(hl, "uncited-heading",
                      f"a claim section's title asserts: {shown[:90]!r}. A title of more than "
                      f"{HEADING_LABEL_WORDS} words is a finding, not a label -- and a title "
                      "cannot carry a citation, because K1 never reads it. Shorten it to a label "
                      "and make the claim a cited sentence in the section"))
    # END guard: a claim section's title is a label, not an assertion
    return out


def _scope_findings(text):
    """RC27. `Scope` may characterise the review's OWN SOURCING in exactly one sentence: the
    grammar's, verbatim (`SCOPE_TEMPLATE`).

    `Scope` is the section K1 cannot look inside (grammar §7), which is the hole the grammar
    creates on purpose -- and the proving run walked into it from a direction nobody had guarded:
    not by moving a claim about the LITERATURE there, but by writing a claim about the review's
    own PROCESS. "nothing was read from an abstract, from memory, or from outside the knowledge
    base" was simply false: two of the review's thirteen citations quote an ingested Kaiser block
    whose first word is "Abstract-" (codex-review-proving-run2.md §2). An ingested, DB-verified
    block is legitimate evidence wherever in the paper it sits; the only barred abstract text is
    the `abstract_passage` of an EXPECTED hunt_request line, which nothing ever verified.

    A grader cannot check whether a self-description is true -- it is a claim about a process, not
    about a document. So the rule is not "be accurate", it is **there is one permitted sentence**,
    and it is one the grader itself enforces: every citation names a VERIFIED brief line, which is
    exactly what `_in_brief_findings` and `_verified_span_findings` refuse to let through. Anything
    else about sourcing is refused by its words: a `Scope` sentence carrying `abstract`, `memory`
    or `knowledge base` that is not the template is `scope-self-claim`.

    WHY THOSE THREE, AND NOT THE FOUR THIS SHIPPED WITH. `outside` and `measured` were in the list
    until auditor-6 measured what they refused: "Sites outside the Pacific Northwest are not
    represented" and "No measured canopy value for Edmonds is in the knowledge base" are LIMITS,
    which is what `Scope` is for, and the first is not about sourcing at all. A vocabulary that
    refuses the section's own purpose teaches a writer to avoid the section, so the list is now
    the terms that name a SOURCE -- where evidence came from -- and nothing that names a quantity
    or a place. Grammar §1 was rewritten in the same change, because it had been inviting exactly
    the sentences this refused ("what it read, what it did not").

    THE TEMPLATE'S EXEMPTION IS NOW A FORWARD GUARD, NOT A LIVE BRANCH, and that is worth saying
    rather than leaving for someone to discover: `SCOPE_TEMPLATE` contains none of the three
    terms, so it passes on its words and the `s == template` test below never decides anything
    today. It stays because the list may widen, and a widening that swallowed the one permitted
    sentence would fail every conforming review at once.

    The terms are matched on `[A-Za-z0-9]` boundaries and are not stemmed, so `abstract_passage`
    matches (deliberately -- it is the field name the docs name) while `abstracts` escapes, and a
    sentence avoiding all three makes any process claim it likes. Both directions are disclosed in
    grammar §7 rather than pretending the list is exhaustive.
    """
    out = []
    # BEGIN guard: Scope describes the review's own sourcing only in the template's exact words
    template = " ".join(SCOPE_TEMPLATE.split())
    for heading, _hl, lines, _fences, _deep in sections(text):
        if heading != "scope":
            continue
        for no, txt in units(lines):
            for sent in sentences(txt):
                s = " ".join(sent.split())
                if not s or s == template:
                    continue
                m = _SELF_CLAIM_RE.search(s)
                if m:
                    out.append(_f(no, "scope-self-claim",
                                  f"a Scope sentence says {m.group(0)!r} and is not the one "
                                  f"permitted sentence: {s[:90]!r}. Scope is the section K1 "
                                  "cannot look inside, so a review may not characterise its own "
                                  f"sourcing there except verbatim: {SCOPE_TEMPLATE!r}"))
    # END guard: Scope describes the review's own sourcing only in the template's exact words
    return out


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
    for heading, _hl, lines, _fences, _deep in sections(text):
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
    for heading, _hl, _lines, fences, _deep in sections(text):
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
    found = [(h, hl, ls) for h, hl, ls, _fn, _dp in sections(text) if h == EXPECTATIONS_HEADING]
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
    found = [(h, hl, ls) for h, hl, ls, _fn, _dp in sections(text) if h == SOURCES_HEADING]
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


#: The block's own bytes with LINE ENDINGS canonicalised -- the database half of
#: `textnorm.canonical_newlines`. It was written inline here until 2026-09-20; migration 0026 made
#: it `litkb.canonical_newlines(text)`, because the RECORDING path needs the same rewrite in the
#: verify trigger and in `use.locate_quote`, and three inline copies of one rule is the drift
#: CLAUDE.md 3.3 is about. `textnorm.sql_canonical_newlines` is the ONE Python spelling of that
#: call, and the two halves are bound by test_the_sql_and_python_newline_canonicalisations_agree,
#: which now drives the function itself.
_CANON_TEXT = sql_canonical_newlines("b.text")

#: Its `ws_files` clause is a file-visibility widening, and this comment is what makes this module
#: visible to the `--sites` census of qc/instruments/litkb_p2_mutations.py (VIS_LEDGER row
#: `litkb/review_check.py::_block_row`). The census opens a module only when its text names
#: FILE_JOIN or visibility, so before 2026-09-20 this bind sat outside a gate built to enumerate
#: every one of them -- found by review_context.py, which mentioned the word in prose.
_BLOCK_SQL = f"""
SELECT b.page_no, wk.key, coalesce(position(%(q)s in {_CANON_TEXT}) > 0, false)
  FROM litkb.blocks b
  JOIN litkb.files f ON f.id = b.file_id AND f.current_run_id = b.run_id
  JOIN litkb.ws_files wf ON wf.file_id = f.id AND wf.view_workstream_id = %(ws)s
                        AND wf.status = 'active'
  JOIN litkb.works wk ON wk.id = wf.work_id
 WHERE b.id = %(bid)s::uuid
"""


def _block_row(conn, ws, block_id, quote):
    """The cited block as this workstream sees it, or None. The substring test is Postgres's
    (`position`), on the block's own bytes with only their LINE ENDINGS canonicalised -- the
    quote is canonicalised by the same rule before it is sent (`textnorm.canonical_newlines`),
    so the two sides differ in nothing else. See the module docstring."""
    try:
        uuid.UUID(block_id)
    except ValueError:
        return None
    # BEGIN guard: a database older than this grader is NAMED, not raised as a driver error
    # `_BLOCK_SQL` calls `litkb.canonical_newlines`, which migration 0026 creates. Against a
    # database that has not had it applied -- which live is between this branch's merge and the
    # migration -- psycopg raised a bare `UndefinedFunction: function litkb.canonical_newlines(text)
    # does not exist`, which names a symbol rather than a thing to do. This is the sentence
    # `use.locate_quote` refuses with, so the two halves of the same change fail the same way.
    try:
        row = conn.execute(
            _BLOCK_SQL, {"ws": ws, "bid": block_id, "q": canonical_newlines(quote) or ""}).fetchone()
    except Exception as e:                                       # noqa: BLE001 - re-raised below
        if type(e).__name__ != "UndefinedFunction":
            raise
        raise ReviewGrammarError(
            "litkb review-check: this database has no litkb.canonical_newlines — migration 0026 "
            "has not been applied, so a quote cannot be compared by the same rule the verify "
            "trigger uses. Apply the migrations (py -3.12 -m litkb.db.migrate --db <db>) before "
            "grading a review against it.") from e
    # END guard: a database older than this grader is NAMED, not raised as a driver error
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
        out += _quote_length_findings(c)
    out += _claim_findings(text)
    out += _fenced_findings(text)
    out += _duplicate_section_findings(text)
    out += _deep_heading_findings(text)
    out += _title_findings(text)
    out += _scope_findings(text)
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
