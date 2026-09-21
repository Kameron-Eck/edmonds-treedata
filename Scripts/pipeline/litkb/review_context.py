r"""`litkb review-context <review.md> --out <context.md>` -- the FULL BLOCK behind every citation.

WHY THIS EXISTS, measured. The adversarial reader of a review is asked one question per citation:
does the SENTENCE assert more than the QUOTE, read with everything around it, supports. It cannot
answer that from the quote, because the quote is the part the writer chose. The proving run of
2026-09-20 ran the same reviewer twice: run 1 saw the review alone and returned 6 OVERREACH rows
out of 12; run 2 saw the review together with a hand-made file holding each cited block's whole
text and returned 0 out of 13 (`jobs/litkb-operational/codex-review-proving-run.md`,
`codex-review-proving-run2.md`). Both runs also changed the review, so that pair is not a
controlled before/after of the context alone -- run 2's own bookkeeping note says so, and this
module makes no claim that it is. What it does is make the file that took a human afternoon a
COMMAND, so the reviewer's input stops depending on who assembled it.

WHAT IT IS NOT. It is not a grader. `litkb review-check` decides whether a citation may be
written at all (the quote is verbatim, inside a verified span, on a VERIFIED line of this
workstream's brief); this command assumes nothing about any of that and simply prints what the
database holds for each block a citation names. Run the grader first: a context file assembled
for a review the grader refuses is context for a document that is not a review.

THE CITATION PARSER IS `review_check.citations`, IMPORTED, NOT COPIED. The grammar's one citation
form has one home (LITKB_REVIEW_GRAMMAR.md §2, `review_check.CITATION_RE`). A second regex here
would be a second grammar, and the first review that drifted between them would produce a context
file missing exactly the citation the grader was arguing about.

A HOLE IS NAMED, AND THE COMMAND FAILS. When the workstream cannot see a cited block -- a bad
uuid, a block of a file whose extraction run is no longer current, a block of a work this
workstream holds no active `ws_files` row for -- the section says `BLOCK NOT VISIBLE` and
`build()` reports it, and the CLI exits 1. A context file with a hole must not look complete:
the reviewer reads the sections it was given and has no way to know that the one citation whose
block was missing is the one it was never shown.

    cd <worktree>/Scripts
    PYTHONPATH=pipeline PYTHONUTF8=1 py -3.12 -m litkb review-context \
        ../Reports/reviews/<slug>.md --out <context.md>
"""
import hashlib
import uuid
from pathlib import Path

from litkb.review_check import _read, citations, header_workstream, resolve_workstream

#: The cited block's own text, as THIS workstream sees it. The visibility join is
#: `review_check._BLOCK_SQL`'s, clause for clause -- current extraction run, an ACTIVE `ws_files`
#: row for this workstream -- because a context file must show what the grader graded and nothing
#: wider. What differs is the projection: the grader asks Postgres a substring question and needs
#: no bytes back, this needs the whole block.
_BLOCK_TEXT_SQL = """
SELECT b.page_no, wk.key, b.text
  FROM litkb.blocks b
  JOIN litkb.files f ON f.id = b.file_id AND f.current_run_id = b.run_id
  JOIN litkb.ws_files wf ON wf.file_id = f.id AND wf.view_workstream_id = %(ws)s
                        AND wf.status = 'active'
  JOIN litkb.works wk ON wk.id = wf.work_id
 WHERE b.id = %(bid)s::uuid
"""

#: What a section says instead of a block when the workstream cannot see one. It is a literal a
#: reader greps for and a test asserts on; `build()` also returns the count, so no caller has to
#: parse the markdown to find out whether the file is whole.
NOT_VISIBLE = "BLOCK NOT VISIBLE"

#: The machine-readable header. It carries the review's path and the sha256 of its RAW BYTES --
#: not of its canonicalised text -- because the wrapper and the gate that read this file run on
#: the same file on the same machine within one session, and the question they ask is "is this
#: the report for THIS file", not "is this the same document as in the repository". (The repo
#: hands this Windows checkout CRLF where it stores LF, deliberately: `.gitattributes`. A digest
#: that had to survive a checkout would have to canonicalise, and would then also accept a file
#: whose line endings a tool had rewritten under the reviewer.)
HEADER_COMMENT = "<!-- litkb-review-context review={path} review_sha256={sha} -->"


def sha256_file(path):
    """sha256 of a file's raw bytes. The one definition, shared by the context header, the
    wrapper's stamp and the acceptance gate, so the three can never disagree about what was
    hashed."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _block(conn, ws, block_id):
    """(page_no, work_key, text) for a block this workstream can see, or None. An id that is not
    a uuid is NOT VISIBLE rather than a driver error -- a malformed citation is the grader's
    finding to raise, and this command's job is to say which block it could not show."""
    try:
        uuid.UUID(block_id)
    except ValueError:
        return None
    row = conn.execute(_BLOCK_TEXT_SQL, {"ws": ws, "bid": block_id}).fetchone()
    return None if not row else {"page_no": row[0], "work_key": row[1], "text": row[2]}


def build(conn, path, *, is_text=False, review_path=None, review_sha256=None):
    """(markdown, report) for one review.

    `report` is `{"citations": n, "blocks": n, "missing": [block_id, ...]}` -- `missing` is what
    makes the CLI exit 1, and it is returned rather than printed so a caller that is not the CLI
    still cannot mistake a holed file for a whole one.

    ONE SECTION PER DISTINCT BLOCK, IN CITATION ORDER. A review cites the same block more than
    once on purpose (run 2 carried 13 occurrences over 6 blocks); repeating a paragraph six times
    would spend the reviewer's attention on the same bytes. The section header is the citation
    token of the block's FIRST occurrence; when a later citation names the same block under a
    different work key or page -- which the grader would refuse as `work-mismatch` or
    `page-mismatch`, but this command does not grade -- that token is listed under `Also cited
    as:` rather than dropped, so the disagreement is visible here too.
    """
    text = path if is_text else _read(path)
    ref = header_workstream(text)
    if not ref:
        raise SystemExit("litkb review-context: the review's first non-blank line must be "
                         "'<!-- litkb-review workstream=<id-or-slug> -->' "
                         "(LITKB_REVIEW_GRAMMAR.md §1)")
    ws, _slug = resolve_workstream(conn, ref)

    cits = citations(text)
    order, seen = [], {}
    for c in cits:
        token = f'[{c["work_key"]} p.{c["page"]} #{c["block_id"]}]'
        if c["block_id"] not in seen:
            seen[c["block_id"]] = {"token": token, "also": []}
            order.append(c["block_id"])
        elif token != seen[c["block_id"]]["token"] and token not in seen[c["block_id"]]["also"]:
            seen[c["block_id"]]["also"].append(token)

    shown = review_path if review_path is not None else ("<text>" if is_text else str(path))
    sha = review_sha256 if review_sha256 is not None else (
        "" if is_text else sha256_file(path))
    out = [f"# Block context for every citation in {Path(shown).name if shown != '<text>' else shown}",
           "",
           HEADER_COMMENT.format(path=shown, sha=sha),
           "",
           f"{len(cits)} citation(s) over {len(order)} distinct block(s), in citation order. "
           "Each block is the whole paragraph the database holds, not the quoted span.",
           ""]
    missing = []
    for bid in order:
        entry = seen[bid]
        out.append(f"## {entry['token']}")
        out.append("")
        for extra in entry["also"]:
            out.append(f"Also cited as: {extra}")
        if entry["also"]:
            out.append("")
        row = _block(conn, ws, bid)
        # BEGIN guard: a cited block this workstream cannot see is NAMED and COUNTED
        # Removing this leaves a section holding an EMPTY fenced block and an empty `missing`
        # list, so the command exits 0 over a file with a hole in it -- which is the whole
        # failure this module's docstring is about, and why the fallback below is written to
        # degrade into it rather than to crash. A crash would be caught by any test; a silent
        # hole is what a reviewer cannot see (harness row CX1).
        if row is None:
            missing.append(bid)
            out.append(NOT_VISIBLE)
            out.append("")
            out.append(f"This workstream cannot see block `{bid}`: no current-run block of an "
                       "active file of this workstream has that id. Nothing is shown for it, and "
                       "`litkb review-context` exits 1 rather than hand a reviewer a file whose "
                       "hole it cannot see.")
            out.append("")
            continue
        # END guard: a cited block this workstream cannot see is NAMED and COUNTED
        out.append("```")
        # The block's own bytes. Its line breaks are left exactly as stored -- about half of the
        # corpus's blocks carry CRLF (LITKB_REVIEW_GRAMMAR.md §2) -- so a reviewer comparing a
        # quote against this file compares what the grader compared.
        out.append(row["text"] if row else "")
        out.append("```")
        out.append("")
    return "\n".join(out), {"citations": len(cits), "blocks": len(order), "missing": missing}


def write(conn, path, out_path):
    """Write the context file and return its report. The CLI's one call."""
    md, report = build(conn, path)
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # newline="" so the block bytes above reach the file unchanged: `open` in text mode would
    # translate every \n this joined into the platform's ending and rewrite the paper's breaks.
    with p.open("w", encoding="utf-8", newline="") as fh:
        fh.write(md)
    report["written"] = str(p)
    return report
