"""Stage 6's coverage, read from the database: which files still owe a reference stage, and how
many references anchor against the denominator that can say anything about the matcher.

    rows = pending_files(conn)            the files the stage-6 driver would run over, by rel_path
    c = reference_counters(conn)          files_without_reference_stage, reference_anchor_rate, ...
    line = format_counters(c)             one `k=v` line, every ratio as numerator/denominator

DB-only and read-only: every statement here is a SELECT, so a `litkb_reader` connection is
enough (the S4 plan's REPORTED counters are measured read-only on the live `litkb`). Nothing is
printed here — the callers print (the sink rule of `qc/instruments/litkb_p2_mutations.py`).

ONE PREDICATE, TWO READERS. "A file with a current stage-5 run and blocks and no ok
`6-references` run at the CURRENT key" is written ONCE, in :data:`_OWES_STAGE6`, and both the
driver's selector (:func:`pending_files`) and the counter (:func:`reference_counters`) read it.
Two copies would let the driver skip a file the counter still counts, or the reverse, and the
counter would then stop measuring what the driver does (CLAUDE.md §3.3). The current key is
`references_ingest.run_key` — the same six columns 0001's UNIQUE is on — so a run made at an
older `params_hash` or `pipeline_version`, or a killed run left `failed`, does NOT count as the
stage having run. That is what makes a rerun resume: the driver's own rerun selects exactly the
files this counter says are without.

WHAT "STAGE 5 WITH BLOCKS" MEANS HERE. The file's CURRENT run (``files.current_run_id``, the one
`set_current_run` moves) is an ok ``5-reconcile`` run (`litkb.extract.ingest.STAGE`) holding at
least one block. A ``5-text-snapshot`` current run (`ingest.TEXT_STAGE`) is a web page's saved
text: there is no PDF for GROBID to read, so it is out of stage 6's reach by construction and is
reported on its own (`text_snapshot_files_with_blocks`) rather than counted as owing a stage it can
never have. Only ``main_files`` rows with ``status = 'active'`` are considered — the file's
current version, never a path composed from a key.

THE ANCHOR RATE'S DENOMINATOR (Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md §1.2, R4's
kill line): anchored references / references whose resolved DOI is a held work's ACTIVE DOI. The
held set is `references_ingest.doi_index` — the one DOI join the loader anchors on — read from
there, never re-spelled. anchored / all references is printed beside it, labelled, because on the
2026-09-22 slice those two read 100 % and 2.6 % and only the first says anything about the matcher.
The reference population is the references of ok stage-6 runs AT THE CURRENT KEY, so a later
re-resolution under a new key is a new population rather than a double count.
"""


def _ingest():
    from litkb.extract import ingest

    return ingest


def _refingest():
    from litkb.extract import references_ingest

    return references_ingest


def current_key():
    """The stage-6 run key's five non-file columns, from `references_ingest.run_key` (one home)."""
    k = _refingest().run_key(None)
    return {c: k[c] for c in ("stage", "tool", "tool_version", "params_hash", "pipeline_version")}


#: Run ``r6`` is an ok stage-6 run at the current key. `%(k_*)s` are :func:`current_key`. Read by
#: BOTH the owed-file predicate and the reference population, so "the stage ran" means one thing.
_OK_RUN_AT_KEY = (
    "r6.stage = %(k_stage)s AND r6.tool = %(k_tool)s AND r6.tool_version = %(k_tool_version)s "
    "AND r6.params_hash = %(k_params_hash)s AND r6.pipeline_version = %(k_pipeline_version)s "
    "AND r6.status = 'ok'")

#: An ok stage-6 run of file ``f`` at the current key.
_OK_STAGE6_AT_KEY = f"SELECT 1 FROM litkb.extraction_runs r6 WHERE r6.file_id = f.file_id AND {_OK_RUN_AT_KEY}"

#: The file's current run is an ok stage-5 reconcile run holding blocks. `cr` is that run.
_HAS_STAGE5_BLOCKS = (
    "f.status = 'active' AND cr.stage = %(stage5)s AND cr.status = 'ok' "
    "AND EXISTS (SELECT 1 FROM litkb.blocks b WHERE b.run_id = f.current_run_id)")

# BEGIN guard: stage 6 owed = stage-5 blocks and no ok stage-6 run at the current key
_OWES_STAGE6 = f"NOT EXISTS ({_OK_STAGE6_AT_KEY})"
# END guard: stage 6 owed = stage-5 blocks and no ok stage-6 run at the current key


def _params(file_ids=None):
    p = {f"k_{c}": v for c, v in current_key().items()}
    p["stage5"] = _ingest().STAGE
    p["text_stage"] = _ingest().TEXT_STAGE
    p["file_ids"] = [str(x) for x in file_ids] if file_ids is not None else None
    return p


#: Restrict to the caller's files when `file_ids` is given (a scope, never a filter on the rule).
_SCOPE = "(%(file_ids)s::uuid[] IS NULL OR f.file_id = ANY(%(file_ids)s::uuid[]))"


def pending_files(conn, *, file_ids=None, limit=None):
    """-> [{"file_id", "work_id", "rel_path", "sha256", "current_run_id", "stage5_artifact"}]: every
    file that owes stage 6 at the current key (module header), in BYTE order of rel_path (``COLLATE
    "C"``) so a run's order does not depend on the server's locale."""
    sql = ("SELECT f.file_id, f.work_id, f.rel_path, f.sha256, f.current_run_id, cr.artifact_path "
           "FROM litkb.main_files f JOIN litkb.extraction_runs cr ON cr.id = f.current_run_id "
           f"WHERE {_HAS_STAGE5_BLOCKS} AND {_OWES_STAGE6} AND {_SCOPE} "
           'ORDER BY f.rel_path COLLATE "C", f.file_id')
    p = _params(file_ids)
    if limit is not None:
        sql += " LIMIT %(limit)s"
        p["limit"] = int(limit)
    cols = ("file_id", "work_id", "rel_path", "sha256", "current_run_id", "stage5_artifact")
    return [dict(zip(cols, row)) for row in conn.execute(sql, p).fetchall()]


def reference_counters(conn, *, file_ids=None):
    """The S4 REPORTED counters, each as a (numerator, denominator) pair or a plain count.

    -> {"files_with_stage5_blocks", "files_without_reference_stage", "files_with_reference_stage",
        "text_snapshot_files_with_blocks", "references", "references_resolved",
        "references_with_held_doi", "references_anchored", "anchored_with_held_doi",
        "anchored_outside_held_doi", "citation_edges", "anchored_with_citation_edge",
        "key": current_key()}
    and the three ratios the plan names, as pairs: "files_without_reference_stage_ratio",
    "reference_anchor_rate" (R4's real denominator), "references_anchored_ratio"."""
    p = _params(file_ids)
    files = conn.execute(
        "SELECT count(*), count(*) FILTER (WHERE " + _OWES_STAGE6 + ") "
        "FROM litkb.main_files f JOIN litkb.extraction_runs cr ON cr.id = f.current_run_id "
        f"WHERE {_HAS_STAGE5_BLOCKS} AND {_SCOPE}", p).fetchone()
    snapshots = conn.execute(
        "SELECT count(*) FROM litkb.main_files f JOIN litkb.extraction_runs cr "
        "ON cr.id = f.current_run_id WHERE f.status = 'active' AND cr.stage = %(text_stage)s "
        "AND cr.status = 'ok' AND EXISTS (SELECT 1 FROM litkb.blocks b WHERE b.run_id = "
        f"f.current_run_id) AND {_SCOPE}", p).fetchone()[0]
    # the held-DOI set is the loader's own (references_ingest.doi_index), passed in, never re-derived
    p["held"] = sorted(_refingest().doi_index(conn))
    refs = conn.execute(
        "WITH runs AS (SELECT r6.id FROM litkb.extraction_runs r6 JOIN litkb.main_files f "
        f"              ON f.file_id = r6.file_id WHERE {_OK_RUN_AT_KEY} AND {_SCOPE}), "
        '     refs AS (SELECT x.*, (x.resolution = \'resolved\' AND x.resolved_doi = ANY(%(held)s::text[])) '
        '                  AS held_doi FROM litkb."references" x WHERE x.run_id IN (SELECT id FROM runs)) '
        "SELECT count(*), "
        "       count(*) FILTER (WHERE resolution = 'resolved'), "
        "       count(*) FILTER (WHERE held_doi), "
        "       count(*) FILTER (WHERE resolved_work_id IS NOT NULL), "
        "       count(*) FILTER (WHERE held_doi AND resolved_work_id IS NOT NULL), "
        "       count(*) FILTER (WHERE NOT held_doi AND resolved_work_id IS NOT NULL), "
        "       (SELECT count(*) FROM litkb.citation_edges e WHERE e.run_id IN (SELECT id FROM runs)), "
        "       count(*) FILTER (WHERE resolved_work_id IS NOT NULL AND EXISTS "
        "              (SELECT 1 FROM litkb.citation_edges e WHERE e.reference_id = refs.id)) "
        "FROM refs", p).fetchone()
    with_blocks, without = files
    total, resolved, held, anchored, anchored_held, anchored_out, edges, anchored_edge = refs
    return {
        "key": current_key(),
        "files_with_stage5_blocks": with_blocks,
        "files_without_reference_stage": without,
        "files_with_reference_stage": with_blocks - without,
        "text_snapshot_files_with_blocks": snapshots,
        "references": total,
        "references_resolved": resolved,
        "references_with_held_doi": held,
        "references_anchored": anchored,
        "anchored_with_held_doi": anchored_held,
        "anchored_outside_held_doi": anchored_out,
        "citation_edges": edges,
        "anchored_with_citation_edge": anchored_edge,
        # the ratios the plan names, each a (numerator, denominator) pair — never a bare quotient
        "files_without_reference_stage_ratio": (without, with_blocks),
        "reference_anchor_rate": (anchored_held, held),
        "references_anchored_ratio": (anchored, total),
        "anchored_with_citation_edge_ratio": (anchored_edge, anchored),
    }


#: The order :func:`format_counters` prints in: the two REPORTED counters first (plan "### S4" (b)).
_LINE = ("files_without_reference_stage_ratio", "reference_anchor_rate", "references_anchored_ratio",
         "anchored_with_citation_edge_ratio", "citation_edges", "anchored_outside_held_doi",
         "text_snapshot_files_with_blocks")


def _pct(n, d):
    return "n/a" if not d else f"{100.0 * n / d:.1f}%"


def format_counters(c):
    """One line, `k=v` separated by spaces; a ratio prints as ``num/den(pct)``. The `_ratio`
    suffix is dropped in print so the two plan names read exactly as the plan spells them."""
    out = []
    for k in _LINE:
        v = c[k]
        name = k[:-len("_ratio")] if k.endswith("_ratio") else k
        out.append(f"{name}={v[0]}/{v[1]}({_pct(*v)})" if isinstance(v, tuple) else f"{name}={v}")
    return " ".join(out)
