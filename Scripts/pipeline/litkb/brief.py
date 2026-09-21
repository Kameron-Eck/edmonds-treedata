"""litkb brief -- the per-workstream BRIEF export for the managing agent (WORKPLAN.md "Next
phase" missing piece 2; delta 2026-09-18, Task B).

    expected, verified = build(conn, ws)          # -> ([{"marker": "EXPECTED", ...}], [{"marker": "VERIFIED", ...}])
    write(path, ws_row, expected, verified)       # markdown; untracked (_derived/briefs/, .gitignore)

Read-side only: no new stored state, no migration. Everything here is one query each into two
sources that are ALREADY separate in the schema -- `litkb.hunt_request_status` (migration 0023)
for an agent's unverified PRIOR, and `litkb.use_evidence_status` (migration 0004/0007) for a
quote verified against ingested block bytes -- rendered so the two are never confusable.

THE GOVERNING CONSTRAINT (the delta's own words): only a quote verified against ingested block
bytes is evidence; a hunt_request holds an agent's unverified prior. Enforced here as a GATE, not
a convention (CLAUDE.md 3.4c):

  * `expected_lines()` reads ONLY `litkb.hunt_request_status` -- ref, expected_claim,
    why_relevant, abstract_passage, resolution_state, exactly as the database derives it
    (litkb/hunt_request.py; never recomputed here). It is never given a state to filter on:
    `_require_every_hunt_request` refuses a brief that fetched fewer rows than the workstream
    holds, so an open/unconfirmed/contradicted expectation can never be quietly left out
    (mutation HB2, qc/test_litkb_brief.py).
  * `verified_lines()` reads ONLY `litkb.use_evidence_status` joined to `uses`/`use_versions`/
    `works`/`blocks`. `_VERIFIED_SQL` and this module's own source never name `hunt_requests`,
    `expected_claim` or `abstract_passage` -- qc/test_litkb_brief.py scans both, the same
    spliced-reference kill as qc/test_litkb_hunt_request.py's gate 2 (mutation HB3).
  * `_require_location` refuses a VERIFIED line missing its work key, page or block id: "the
    VERIFIED quote with its location" is not printed without the location that makes it
    re-checkable (mutation HB1).
  * a VERIFIED line's `quote` leaves with canonical line endings (`verified_lines`, mutation
    RC16). That is the EXPORT's one normalisation and it is on the DICT, not on the markdown,
    because the writer agent's input is the MCP tool `litkb_brief` -- these dicts -- and never
    `render`. See `verified_lines` for the whole reason.

Kinds print AS THE DATABASE NAMES THEM (method, theorem, parameter, empirical evidence, negative
result, context, contradiction) -- never remapped to words like "principle" or "data". `kind` is
already the one authoritative vocabulary for what a use supplies (CLAUDE.md 3.3, migration
0001); inventing a second taxonomy on top of it here would be exactly the drift that rule
forbids, for a distinction the database does not draw.

Grouping: EXPECTED lines are one per `hunt_request`, in creation order. VERIFIED lines are one
per promotable `use_evidence` row, grouped by the work's key. A hunt_request's own `work_key`
(once linked) is printed alongside it, so a reader can find that work's VERIFIED section --
there is no cross-query join between the two, only a shared label in the rendered text.
"""
from datetime import datetime, timezone
from pathlib import Path

from litkb.textnorm import canonical_newlines


class BriefInvariantError(RuntimeError):
    """The marking gate refused: a VERIFIED line with no location, or an EXPECTED line dropped."""


#: Both statements below bind `ws` and are therefore visibility widenings, and this comment is
#: what makes this module visible to the `--sites` census of qc/instruments/litkb_p2_mutations.py
#: (VIS_LEDGER rows `litkb/brief.py::expected_lines` and `::verified_lines`). The census opens a
#: module only when its text names FILE_JOIN or visibility, so before 2026-09-20 these two binds
#: sat outside a gate built to enumerate every one of them.
_EXPECTED_SQL = """
SELECT id, ref, ref_scheme, claimed_title, claimed_authors, claimed_year, expected_claim,
       why_relevant, abstract_passage, work_id, resolution_state, n_confirming, n_contradicting,
       created_at
  FROM litkb.hunt_request_status
 WHERE workstream_id = %(ws)s
 ORDER BY created_at
"""


def expected_lines(conn, ws):
    """Every hunt_request this workstream holds, marked EXPECTED. `resolution_state` is the
    database's own derivation (litkb.hunt_request_status), never recomputed here -- see
    litkb/hunt_request.py::status for the same rule. Reads ONLY hunt_request_status: no
    use/use_evidence table is named in this query."""
    out = []
    for (hr_id, ref, scheme, ctitle, cauthors, cyear, claim, why, passage, work_id, state,
         n_conf, n_contra, created) in conn.execute(_EXPECTED_SQL, {"ws": ws}).fetchall():
        work_key = None
        if work_id is not None:
            row = conn.execute("SELECT key FROM litkb.works WHERE id = %s", (work_id,)).fetchone()
            work_key = row[0] if row else None
        out.append({"marker": "EXPECTED", "hunt_request_id": str(hr_id), "ref": ref,
                    "ref_scheme": scheme, "claimed_title": ctitle, "claimed_authors": cauthors,
                    "claimed_year": cyear, "expected_claim": claim, "why_relevant": why,
                    "abstract_passage": passage, "work_id": str(work_id) if work_id else None,
                    "work_key": work_key, "resolution_state": state, "n_confirming": n_conf,
                    "n_contradicting": n_contra, "created_at": created})
    return out


def _require_every_hunt_request(conn, ws, lines):
    """The brief is never a FILTERED view of a workstream's drop-offs -- an unconfirmed or
    contradicted expectation is exactly the thing this export exists to surface, so nothing here
    picks a resolution_state to show and one to hide. Mutation HB2: narrow expected_lines() (or
    this count) to resolution_state = 'confirmed' and a shorter, quieter brief must be refused
    rather than written."""
    # BEGIN guard: every hunt_request the workstream holds appears in the brief
    total = conn.execute("SELECT count(*) FROM litkb.hunt_requests WHERE workstream_id = %s",
                         (ws,)).fetchone()[0]
    if len(lines) != total:
        raise BriefInvariantError(
            f"brief carries {len(lines)} EXPECTED line(s) for a workstream that holds {total} "
            "hunt_request(s): an expectation was dropped rather than marked "
            "unconfirmed/contradicted/open")
    # END guard: every hunt_request the workstream holds appears in the brief


# `_VERIFIED_SQL` is the evidence path's OWN copy of the "never read hunt_request columns" rule
# (migration 0023's constraint 2; qc/test_litkb_hunt_request.py's gate 2 covers litkb_search,
# locate_quote and _record_use -- this constant is the brief's own call site, added after that
# gate, hence its own scan in qc/test_litkb_brief.py rather than an extension of that list).
_VERIFIED_SQL = """
SELECT wk.key, wu.version_id, wu.statement, wu.kind, wu.rationale, wu.status, u.hunt_request_id,
       ev.quote, ev.stance, b.page_no, ev.block_id
  FROM litkb.ws_uses wu
  JOIN litkb.uses u ON u.id = wu.use_id
  JOIN litkb.works wk ON wk.id = wu.work_id
  JOIN litkb.use_evidence_status ev ON ev.use_version_id = wu.version_id AND ev.promotable
  JOIN litkb.blocks b ON b.id = ev.block_id
 WHERE wu.view_workstream_id = %(ws)s AND wu.status <> 'withdrawn'
   AND (wu.workstream_id = %(ws)s OR wu.state = 'promoted')
 ORDER BY wk.key, b.page_no, ev.block_id
"""


def _require_location(line):
    """A VERIFIED line without its own location is not evidence anyone could go re-check --
    refused here rather than printed. Mutation HB1: drop this call (or the fields it checks) and
    a location-less quote prints as if it were checkable."""
    # BEGIN guard: a VERIFIED line always carries work key, page and block id
    missing = [k for k in ("work_key", "page", "block_id") if not line.get(k)]
    if missing:
        raise BriefInvariantError(
            f"VERIFIED line for {line.get('statement')!r} is missing {missing}: a quote without "
            "its own location (work key, page, block id) is not evidence anyone could re-check")
    # END guard: a VERIFIED line always carries work key, page and block id


def verified_lines(conn, ws):
    """Every promotable quote this workstream can see, marked VERIFIED. `promotable`
    (litkb.use_evidence_status, migration 0004/0007) is the database's own verdict -- verified
    AND anchored in the file's CURRENT extraction run -- never recomputed here, the same rule
    litkb/hunt_request.py's resolution_state leans on.

    A VERIFIED line's `quote` leaves here with its LINE ENDINGS CANONICAL
    (`textnorm.canonical_newlines`) -- the same rule `litkb review-check` applies to both sides of
    its comparison, so a quote copied out of a brief is a quote the grader accepts. It is done
    HERE, on the line dict, rather than in `render`, because THE WRITER NEVER SEES `render`: the
    agent's input is the MCP tool `litkb_brief`, which returns exactly these dicts
    (`litkb/mcp/server.py::_brief` -> `build`), and the markdown file is the CLI's convenience.
    Canonicalising only the rendering would have fixed the path nobody walks. Nothing else about
    the quote changes, and the stored `use_evidence` row keeps its own bytes -- this is the
    EXPORT, and the one thing it normalises is the encoding of a line break."""
    out = []
    for (key, uv, statement, kind, rationale, status, hr_id, quote, stance, page, block_id
         ) in conn.execute(_VERIFIED_SQL, {"ws": ws}).fetchall():
        line = {"marker": "VERIFIED", "work_key": key, "use_version_id": str(uv),
                "statement": statement, "kind": kind, "rationale": rationale, "status": status,
                "hunt_request_id": str(hr_id) if hr_id else None,
                # BEGIN guard: a VERIFIED line's quote leaves the brief with canonical line endings
                "quote": canonical_newlines(quote),
                # END guard: a VERIFIED line's quote leaves the brief with canonical line endings
                "stance": stance, "page": page, "block_id": str(block_id)}
        _require_location(line)
        out.append(line)
    return out


def build(conn, ws):
    """(expected, verified) for this workstream. Two independent queries, two independent
    gates -- see the module docstring. Raises BriefInvariantError rather than returning a brief
    the gate could not stand behind."""
    expected = expected_lines(conn, ws)
    _require_every_hunt_request(conn, ws, expected)
    verified = verified_lines(conn, ws)              # _require_location runs per line, inside
    return expected, verified


_STATE_CALLOUT = {
    "open": "OPEN -- not yet linked to a work",
    "unconfirmed": "UNCONFIRMED -- linked, but no ingested text has confirmed or refuted it yet",
    "confirmed": "CONFIRMED -- see the VERIFIED quote(s) below for this work",
    "contradicted": "CONTRADICTED -- a verified quote refutes this expectation",
}


def render(ws_row, expected, verified):
    """Markdown. Every EXPECTED line's `abstract_passage` is printed labelled UNVERIFIED and
    never inside a VERIFIED block; every VERIFIED line prints its own work key/page/block id.

    A VERIFIED line reaches here with its quote already canonical (`verified_lines`, which is
    where the rule belongs because that is what the MCP tool returns). `canonical_newlines` is
    applied again below, and deliberately: it is idempotent, and `render` is also called with
    hand-built line dicts, so the markdown may not depend on who assembled them. Without it the
    rendered brief was worse than uncopyable -- `write()` is `write_text`, Windows turns every
    `\\n` into `\\r\\n` on the way out, and a quote that already held `\\r\\n` came out as
    `\\r\\r\\n`, three times in a real brief of `improve-review-1`
    (auditor-3b-stage8-fixes.md §5.4, measured).
    """
    by_work = {}
    for v in verified:
        by_work.setdefault(v["work_key"], []).append(v)

    lines = [f"# Brief: {ws_row['slug']}", "",
             f"workstream `{ws_row['id']}` ({ws_row['state']}) -- {ws_row['purpose']}",
             f"generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
             "", "## Expected (agent priors, unverified -- hunt_request)", ""]
    if not expected:
        lines.append("_none recorded._")
    for e in expected:
        header = f"### EXPECTED -- {e['ref']} ({e['ref_scheme']})"
        if e["work_key"]:
            header += f" -> {e['work_key']}"
        lines.append(header)
        callout = _STATE_CALLOUT.get(e["resolution_state"], e["resolution_state"].upper())
        lines.append(f"- resolution: **{callout}**")
        if e["claimed_title"]:
            claim_line = f"- claimed: {e['claimed_title']}"
            if e["claimed_authors"]:
                claim_line += f", {e['claimed_authors']}"
            if e["claimed_year"]:
                claim_line += f" ({e['claimed_year']})"
            lines.append(claim_line)
        lines.append(f"- expected claim: {e['expected_claim']}")
        lines.append(f"- why relevant: {e['why_relevant']}")
        if e["abstract_passage"]:
            lines.append(f"- abstract passage (UNVERIFIED, never quotable): {e['abstract_passage']}")
        lines.append("")
    lines += ["## Verified (quotes anchored in ingested block bytes)", ""]
    if not by_work:
        lines.append("_none recorded._")
    for key in sorted(by_work):
        lines.append(f"### {key}")
        for v in by_work[key]:
            lines.append(f'- VERIFIED [{v["kind"]}, {v["stance"]}] '
                         f'"{canonical_newlines(v["quote"])}" -- '
                         f'{key} p.{v["page"]} block `{v["block_id"]}`')
            lines.append(f"  claim: {v['statement']}")
            if v["rationale"]:
                lines.append(f"  rationale: {v['rationale']}")
        lines.append("")
    return "\n".join(lines)


def write(path, ws_row, expected, verified):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(ws_row, expected, verified), encoding="utf-8")
    return path
