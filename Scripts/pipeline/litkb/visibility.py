"""Which files a caller may READ text from — main's, plus its own workstream's proposals.

    sql = f"SELECT … FROM litkb.blocks b JOIN litkb.files f ON f.id = b.file_id {FILE_JOIN} …"
    conn.execute(sql, {"ws": ws_id_or_None, …})

ONE definition, three call sites (`mcp/server.py::_BLOCK_FROM`, `mcp/server.py::_record_use`,
`use.py::locate_quote`), because it is one rule: *a block is readable when its file is the version
main points at, or the version THIS workstream proposed.*

WHY IT IS NOT `main_files` ANY MORE (decisions.yaml `litkb-web-source-gate`, decided 2026-09-19).
A web source is admitted by the manual route, and `litkb.admit` writes every version of a manual
admission in `proposal` mode (migration 0013, `v_mode`): the identity rows exist, but
`files.current_version_id` and `works.current_version_id` stay NULL until a SECOND session calls
`litkb.approve_admission`. `main_files`/`main_works` join through exactly those pointers
(migration 0004), so the join itself was the gate — a block of an unapproved proposal was invisible
to every caller, including the session that had just proposed it. That is what stalled an
unattended loop: the first stage of the pipeline is open-web discovery, and nothing found there
could be read back, quoted or reasoned over until a human appeared.

Kam's decision MOVES the boundary rather than removing it. The gate exists to protect the
AUTHORITATIVE record, and promotion is where that record is written; search visibility inside one
open workstream is not. So the predicate below adds the caller's own `ws_heads` version — its
proposals, nobody else's — and:

  * with no open workstream (`ws` is NULL) it reduces, clause by clause, to the old one: the
    correlated subquery returns NULL, `coalesce` falls back to `f.current_version_id`, and the
    `EXISTS` is false, so the work must be in main. A tree with no `.litkb-workstream` sees exactly
    what it saw before;
  * another workstream's proposal is never reached: `ws_heads` is keyed by workstream, and one
    workstream's id does not select another's row;
  * the PROMOTED record is untouched. A use that quotes such a block is still held at
    `promote prepare` — `_ws_chains` gives the use a dependency on its work, and a work chain of a
    manual admission always carries the problem "a work, identifier or file enters main only
    through litkb.approve_admission" (migration 0013/0019), so the dependency-hold fixpoint in
    `promote_prepare` holds the use too. `qc/test_litkb_web_gate.py` runs that, and names the
    reason it comes back with.

The caller's workstream id is resolved from `<worktree>/.litkb-workstream` and is CHECKED against
`litkb.check_ws_token` before it is used (`server._caller_workstream`), on the P8 referee's F-1
rule: a workstream id is not a secret, so a file naming a real workstream with a wrong token must
buy nothing. There is no tool parameter for it and no environment override.

Expressed as a SQL fragment rather than a SQL FUNCTION on purpose. A function would need a
migration, and until that migration was applied the three call sites would raise
`UndefinedFunction` against every database that did not yet have it — including the live one
between this branch's merge and its migration. The fragment reads only tables that have existed
since migration 0001 and that `litkb_reader` has held SELECT on since 0006
(`qc/test_litkb_web_gate.py::test_the_reader_role_may_read_the_visibility_tables` measures that
rather than trusting it).

A workstream's proposals are visible to it only while it is OPEN. `litkb.check_ws_token`
(migration 0018) reads `workstream_tokens` and nothing else, so it answers TRUE for a workstream
that has been merged or abandoned — the write functions refuse on `workstreams.state` themselves
(`_write_version`, 0007:39-44), the read path had no such check, and this decision is what made
`ws_heads` load-bearing for SEARCH. A merged workstream's `.litkb-workstream` survives the merge
(nothing deletes it), so without `is_open` below a finished worktree would go on searching, briefing
and quoting material that never entered main. `is_open` is that check, in Python rather than in a
new migration, and it is asked AFTER the token is presented at every site that asks it: a
workstream's state is told to nobody who has not presented its token.

THE TOKEN IS PRESENTED AT EVERY WIDENING SITE, and that is what makes it safe to grant this
widening on a file sitting in the worktree (the P8 referee's F-1: a workstream id is not a secret —
a tracked report prints one). `server._caller_workstream` (search), `server._record_use` (the quote
path) and `server._brief` each call `_require_token` before the id below is bound. `_record_use`
did not, for one day: it had always left the token to the DATABASE's check on the write, which was
sound while its block lookup joined `main_files` and an unverified id bought nothing — and stopped
being sound the moment that lookup began binding `ws`, because the refusals built from the block
(`quote-not-in-block` carries `work_key`) then describe a source the caller may not read
(`qc/test_litkb_web_gate.py::test_i_record_use_presents_the_token_before_it_widens`). The CLI's
`use.locate_quote` takes `ws` from its caller and defaults to None; `commands.py` passes none.
"""


def is_open(conn, ws_id):
    """True when `ws_id` is an OPEN workstream of this database — the condition for widening.

    A workstream that does not exist is not open either, so a token file naming a workstream from
    another database narrows to main rather than raising. Read as a plain SELECT on
    `litkb.workstreams`, which `litkb_reader` may read (`litkb_ws_status` already does;
    `qc/test_litkb_web_gate.py::test_the_reader_role_may_read_the_visibility_tables` measures it).
    """
    row = conn.execute("SELECT state FROM litkb.workstreams WHERE id = %s", (ws_id,)).fetchone()
    return bool(row) and row[0] == "open"


#: Joins `litkb.file_versions fv` and `litkb.works w` onto an already-joined `litkb.files f`.
#: Binds ONE named parameter, `ws` — the caller's open workstream id, or None. Every statement that
#: interpolates it must therefore pass its parameters as a dict.
FILE_JOIN = """
  JOIN litkb.file_versions fv ON fv.version_id = coalesce(
         (SELECT h.version_id FROM litkb.ws_heads h
           WHERE h.workstream_id = %(ws)s::uuid AND h.entity = 'file' AND h.entity_id = f.id),
         f.current_version_id)
  JOIN litkb.works w ON w.id = fv.work_id
   AND (w.current_version_id IS NOT NULL
        OR EXISTS (SELECT 1 FROM litkb.ws_heads hw
                    WHERE hw.workstream_id = %(ws)s::uuid AND hw.entity = 'work'
                      AND hw.entity_id = w.id))
"""
