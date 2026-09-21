"""ONE rule for "can this work be read", and ONE spelling of "the current run's canonical text".

Two things lived in five and three places respectively until S4, and both had drifted into
something a reader could not check:

  * **the current-run join.** ``JOIN litkb.files f ON f.id = b.file_id AND f.current_run_id =
    b.run_id`` was hand-written at ``mcp/server.py::_BLOCK_FROM`` and ``::_work``, ``use.py::locate_quote``,
    ``review_check.py::_BLOCK_SQL`` and ``review_context.py::_BLOCK_TEXT_SQL``. Five copies of one rule with no
    constraint behind it: a sixth reader that forgot the join saw 3.55x the corpus on the
    2026-09-21 live dump (372,305 blocks, of which 267,545 belong to a run no file points at).
  * **the state of a work.** ``if not files: held / elif not any(current_run_id): bound-unextracted
    / else: extracted`` was written out at ``mcp/server.py::_work``, ``mcp/server.py::_absent_kind`` and
    ``hunt.py::look_up``. All three agreed, and all three were wrong in the same two ways:
    ONE extracted file beside one unreadable file read ``extracted`` (``any()``), and a current run
    holding zero blocks read ``extracted, blocks: 0``. Neither had ever fired on real data — live,
    0 works hold more than one active file and 0 files have a current run with no blocks — so the
    rule was unexercised rather than merely untested, which is why it could stay wrong.

THE COMPLETENESS RULE (S4 decision D1). A work reads ``extracted`` only when EVERY active file has
a current run whose canonical block count is greater than zero. Anything less is
``bound-unextracted`` with a reason that says WHICH less:

    extracted            every active file has current-run canonical text
    bound-unextracted/partial      the files disagree — some readable, some not
    bound-unextracted/zero-content a current run exists and holds no canonical block
    bound-unextracted/already-bound a file is bound and no run has been made for it
    bound-unextracted/<residue>    a classification row says why it cannot be read
                                   (scan-needs-ocr, over-page-cap, zero-content, bad-file)
    held                 no active file at all
    held/no-file-any-route  ... and every acquisition route that was attempted is terminal

A run with 0 canonical blocks NEVER moves ``current_run_id`` (that is the ingest's job and it
already refuses: ``finish_extraction_run`` will not declare a ``5-reconcile`` run ok with no
blocks). This module is the reader's half: when such a pointer does exist — an older run, a
retired one, a hand-repaired row — the work is reported ``zero-content`` and not ``extracted``,
because "the extractor ran and found nothing" is a different problem from "the extractor never
ran" and telling them apart is the whole point of the ladder. The distinction the old comment made
is kept; what changes is that BOTH are named, instead of the first being silently called extracted.

WHY THE JOIN IS A FRAGMENT AND NOT A VIEW OR A SQL FUNCTION. The reasoning is
``litkb.visibility``'s, clause for clause: a view or a function would need its migration applied
before any reader could call it, so between a merge and its migration every search on the live
database would raise ``UndefinedFunction``. A fragment reads only columns that have existed since
0001/0017 and works against a database at any tip.

``b.canonical`` IS PART OF THAT FRAGMENT since migration 0030. Before it, ``canonical`` meant
"ordered within its own run" (the unique index ``blocks_canonical_order`` is per run) and all
372,305 blocks carried it, stale ones included. 0030's ``litkb.retire_run`` flips it to false for a
retired run's blocks, and this fragment is what makes that mean *not searchable, not quotable, not
gradable* — one predicate, every read site.
"""

#: What a FILE can be, beside `extracted`. These are `hunt.REASONS["bound-unextracted"]`'s S4
#: additions and they are the file-level residue classes of S4 decision D1: a file IS bound, no
#: canonical text exists for it, and here is why. `already-bound` (nothing has been tried yet) and
#: `fresh-bound` (this hunt landed it) are the two that predate them and stay in hunt.py, which is
#: where a hunt's own history is known.
RESIDUE_CLASSES = ("scan-needs-ocr", "over-page-cap", "zero-content", "bad-file")

#: The work-level word for "the active files disagree" — some readable, some not.
PARTIAL = "partial"

#: A file is bound and no extraction run has been made for it, and nothing has classified it.
ALREADY_BOUND = "already-bound"

#: Terminal acquisition statuses, per route: `litkb.acquire.run.DEAD_STATUSES` (a route that
#: answered one of these is not retried without `--retry-dead`), plus `blocked`, which
#: `acquire/run.py` records when a host refuses this client or spending stops. Read from the
#: module rather than retyped, so the two cannot drift; `blocked` is added here because it is a
#: stop rather than a dead end and `DEAD_STATUSES` does not carry it.
def _terminal_statuses():
    from litkb.acquire.run import DEAD_STATUSES

    out = {"blocked"}
    for statuses in DEAD_STATUSES.values():
        out |= set(statuses)
    return out


def current_run_join(block="b", file="f", table="litkb.files"):
    """The ONE spelling of "this block is the file's current, canonical text".

    -> a SQL fragment joining `table` (aliased `file`) onto an already-selected blocks alias.
    `table` is `litkb.main_files` at the one site that reads through main's view (its file id
    column is `file_id`, not `id`), `litkb.files` everywhere else; `file`/`block` are that site's
    own aliases. Nothing here is interpolated from a caller's input — the three arguments are
    literals at every call site, and this function exists so that there is one string to change
    and one mutation row to break, not five.
    """
    fid = "file_id" if table.endswith("main_files") else "id"
    return (f" JOIN {table} {file} ON {file}.{fid} = {block}.file_id "
            f"  AND {file}.current_run_id = {block}.run_id AND {block}.canonical ")


#: The five sites this fragment replaced, kept here so the census in
#: `qc/instruments/litkb_p2_mutations.py --sites` and any reader can find them without a grep:
#: `mcp/server.py::_BLOCK_FROM` (search), `mcp/server.py::_work` (the block count),
#: `use.py::locate_quote` (the quote anchor), `review_check.py::_BLOCK_SQL` (the grader) and
#: `review_context.py::_BLOCK_TEXT_SQL` (the context file).
CURRENT_RUN_SITES = ("mcp/server.py::_BLOCK_FROM", "mcp/server.py::_work",
                     "use.py::locate_quote", "review_check.py::_BLOCK_SQL",
                     "review_context.py::_BLOCK_TEXT_SQL")


def extracted_reason(metrics, *, fresh=True):
    """WHICH tools produced a current run's blocks, from the run's own `metrics`.

    `grobid-only` / `docling-only` mean the reconciliation ran on one tool because the other
    produced nothing. Until S4 this was derived from ARTIFACT EXISTENCE at `hunt.py::_finish` — "is
    there a .docling.json on disk" — and that is not the same question: the live `Maiti_2022` run
    `01a0c263` has a `.docling.json` beside it, 69 `grobid_regions`, 0 `docling_regions` and not
    one block with `source = 'docling'`, and the hunt called it `fresh`. The artifact is the
    reconciler's own output naming convention; the metrics are what each tool contributed.

    `fresh` is what THIS hunt produced; `already-extracted` is the same two-tool run found already
    in the database. That difference is the caller's history, not the row's, so it is a keyword.
    """
    m = metrics or {}
    g = int(m.get("grobid_regions") or 0)
    d = int(m.get("docling_regions") or 0)
    if g > 0 and d == 0:
        return "grobid-only"
    if d > 0 and g == 0:
        return "docling-only"
    return "fresh" if fresh else "already-extracted"


def _classified(conn, file_id):
    """The residue class a classification row gives this file, or None.

    Reads `litkb.extraction_jobs` — builder Q1's table, migration 0029 — ONLY when it exists.
    `to_regclass` is asked every call rather than cached, because code on main must keep working
    against a live database at 0028, where the table does not exist and the honest answer is "no
    classification", not an `UndefinedTable`.
    """
    if not conn.execute("SELECT to_regclass('litkb.extraction_jobs')").fetchone()[0]:
        return None
    row = conn.execute(
        "SELECT state, reason FROM litkb.extraction_jobs WHERE file_id = %s "
        " ORDER BY updated_at DESC NULLS LAST LIMIT 1", (file_id,)).fetchone()
    if not row or (row[0] or "") != "classified":
        return None
    return row[1] if row[1] in RESIDUE_CLASSES else None


def file_state(conn, file_id):
    """-> (state, reason, detail) for ONE file. `state` is `extracted` or `bound-unextracted`.

    `detail` is the per-file row `litkb_work` reports: file_id, current_run_id, blocks (CANONICAL
    blocks of that current run — the number a search can actually return), pages.
    """
    row = conn.execute(
        "SELECT f.current_run_id::text, v.pages FROM litkb.files f "
        "  LEFT JOIN litkb.file_versions v ON v.version_id = f.current_version_id "
        " WHERE f.id = %s", (file_id,)).fetchone()
    run_id, pages = (row or (None, None))
    detail = {"file_id": str(file_id), "current_run_id": run_id, "blocks": 0, "pages": pages}
    if not run_id:
        # BEGIN guard: a classified file is named by its residue class, never by already-bound
        residue = _classified(conn, file_id)
        # END guard: a classified file is named by its residue class, never by already-bound
        return "bound-unextracted", residue or ALREADY_BOUND, detail
    detail["blocks"] = conn.execute(
        "SELECT count(*) FROM litkb.blocks b WHERE b.run_id = %s AND b.file_id = %s "
        "   AND b.canonical", (run_id, file_id)).fetchone()[0]
    # BEGIN guard: a current run with no canonical block is zero-content, never extracted
    if detail["blocks"] == 0:
        return "bound-unextracted", "zero-content", detail
    # END guard: a current run with no canonical block is zero-content, never extracted
    metrics = conn.execute("SELECT metrics FROM litkb.extraction_runs WHERE id = %s",
                           (run_id,)).fetchone()
    detail["metrics"] = metrics[0] if metrics else None
    return "extracted", extracted_reason(detail["metrics"], fresh=False), detail


def held_reason(conn, work_id):
    """Why a work with no file has none: `no-file-any-route` when at least one acquisition route
    was attempted and EVERY attempt is terminal, else `no-file`.

    Terminal = `litkb.acquire.run.DEAD_STATUSES` for that route, or `blocked`. An `ok` attempt that
    did not end in a bound file (a duplicate-held, a binding that failed) is NOT terminal: the
    route worked and something downstream did not, and re-running it is a reasonable next move.
    """
    rows = conn.execute("SELECT route, status FROM litkb.acquisition_attempts WHERE work_id = %s",
                        (work_id,)).fetchall()
    # BEGIN guard: no-file-any-route needs at least one attempt and every attempt terminal
    if not rows:
        return "no-file"
    terminal = _terminal_statuses()
    return "no-file-any-route" if all(s in terminal for _r, s in rows) else "no-file"
    # END guard: no-file-any-route needs at least one attempt and every attempt terminal


#: The active files of a work, by view. `ws_id` None reads main's; otherwise the workstream's own
#: view, which is what `hunt.look_up` and `litkb_work`'s in-this-workstream branch read (a manual
#: proposal lives only there). `status = 'active'` is both views' own predicate, spelled once.
_MAIN_FILES = ("SELECT file_id::text FROM litkb.main_files WHERE work_id = %s "
               "   AND status = 'active' ORDER BY rel_path")
_WS_FILES = ("SELECT file_id::text FROM litkb.ws_files WHERE view_workstream_id = %s "
             "   AND work_id = %s AND status = 'active' ORDER BY rel_path")


def work_state(conn, work_id, *, ws_id=None):
    """-> (state, reason, files) — the ONE completeness rule, over every ACTIVE file of the work.

    `files` is the per-file detail, one dict per active file, each carrying its own `state` and
    `reason`: a work that is `partial` is useless to a caller who cannot see WHICH file is the
    unreadable one, and that list is what `litkb_work` now returns.

    The work's reason when every file is extracted: the WEAKEST of the file reasons, because an
    extraction that ran on one tool is a weaker extraction and a work is only as readable as its
    least-readable file. `grobid-only` and `docling-only` both present is reported as
    `grobid-only` — arbitrary between two equally one-tool answers, and deterministic, which is
    what a ledger word has to be.
    """
    rows = (conn.execute(_WS_FILES, (ws_id, work_id)).fetchall() if ws_id
            else conn.execute(_MAIN_FILES, (work_id,)).fetchall())
    # BEGIN guard: a work with no active file is held
    if not rows:
        return "held", held_reason(conn, work_id), []
    # END guard: a work with no active file is held
    files = []
    for (fid,) in rows:
        st, why, detail = file_state(conn, fid)
        files.append(detail | {"state": st, "reason": why})
    # BEGIN guard: extracted means EVERY active file has current-run canonical text
    if all(f["state"] == "extracted" for f in files):
        reasons = {f["reason"] for f in files}
        for weak in ("grobid-only", "docling-only"):
            if weak in reasons:
                return "extracted", weak, files
        return "extracted", "already-extracted" if len(files) > 1 else files[0]["reason"], files
    # END guard: extracted means EVERY active file has current-run canonical text
    # BEGIN guard: files that disagree are partial
    unread = [f["reason"] for f in files if f["state"] != "extracted"]
    if len(unread) < len(files) or len(set(unread)) > 1:
        return "bound-unextracted", PARTIAL, files
    # END guard: files that disagree are partial
    return "bound-unextracted", unread[0], files


# ── retiring superseded run sets ───────────────────────────────────────────────────────────
#
# A run is SUPERSEDED when its file points somewhere else. That was never a column — there is no
# `superseded_by`, no `retired_at` and, until 0030, no third status — so it was computed, in prose,
# by `use_evidence_status.promotable` and by the five joins above. `retire_run` (0030) writes it
# down, and this is the query that chooses what to hand it.
#
# THE SAME STAGE, and this is the one judgment in the query. A file's runs are not one series:
# `5-reconcile` is the stage a `current_run_id` ever points at (233 of 233 live), and the 17
# `6-references` runs are a later pass that is current for nothing and would read as "superseded"
# under a stage-blind rule. On the 2026-09-21 corpus they hold 0 blocks, so retiring them would
# change no number and would still have said something false about them.

#: One row per retirable run: the file, the run, its block count and whether a `use_evidence` row
#: anchors one of its blocks. `%s` is an optional file id filter (NULL = every file).
SUPERSEDED_RUNS = """
SELECT r.file_id::text, r.id::text, r.stage, r.created_at,
       coalesce(b.n, 0) AS blocks,
       EXISTS (SELECT 1 FROM litkb.use_evidence e
                 JOIN litkb.blocks eb ON eb.id = e.block_id
                WHERE eb.run_id = r.id) AS referenced
  FROM litkb.extraction_runs r
  JOIN litkb.files f ON f.id = r.file_id
  LEFT JOIN (SELECT run_id, count(*) AS n FROM litkb.blocks WHERE canonical GROUP BY 1) b
         ON b.run_id = r.id
 WHERE r.status = 'ok'
   AND f.current_run_id IS NOT NULL
   AND r.id <> f.current_run_id
   AND r.stage = (SELECT cr.stage FROM litkb.extraction_runs cr WHERE cr.id = f.current_run_id)
   AND (%(file)s::uuid IS NULL OR r.file_id = %(file)s::uuid)
 ORDER BY r.file_id, r.created_at
"""


def superseded_runs(conn, file_id=None):
    """-> [{file_id, run_id, stage, created_at, blocks, referenced}] — the retirable run sets.

    A read, on any login that may SELECT. `blocks` counts CANONICAL blocks only, so a run already
    retired reports 0 and re-running the census after an apply shows the work as done rather than
    as still to do.
    """
    cols = ("file_id", "run_id", "stage", "created_at", "blocks", "referenced")
    return [dict(zip(cols, r)) for r in
            conn.execute(SUPERSEDED_RUNS, {"file": file_id}).fetchall()]
