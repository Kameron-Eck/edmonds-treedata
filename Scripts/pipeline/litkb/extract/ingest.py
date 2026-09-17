"""Stage 5 ingest — the reconciliation's rows into the database, as ``litkb_ingest`` (design §7).

    run = ingest_file(conn, file_id, pdf_path, canonical, disagreements, stats, pages)

ONE TRANSACTION PER FILE. The run row, its pages, its blocks and everything below them are
committed together or not at all. That is not tidiness: §14 P5's kill is "the kill fires when
ingest is mutated to commit text rows outside the run's transaction", and a per-page commit is
exactly what leaves half a file behind when a worker is killed. Resuming then finds a run that
exists with some of its blocks and adds the rest — duplicates, with no unique key able to see
them, because a block has no natural key.

IDEMPOTENT BY (file sha256, pipeline version). The identity is 0001's UNIQUE on
(file, stage, tool, tool_version, params_hash, pipeline_version) — the file row IS the sha256
(``files.sha256`` is unique) and the rest is the pipeline version in the sense §4.4 means.
:func:`ingest_file` asks :func:`already_ingested` first and does nothing at all when the run is
there and ``ok``. A run that exists but is NOT ok is a killed worker's carcass: its rows are
deleted and the file is redone, inside the same transaction, so at no point do two sets of
blocks exist.

The current-run pointer moves LAST, and only for the reconciliation stage (§7): until
``set_current_run`` runs, the new blocks are invisible to search, exports and evidence, so a
half-finished ingest cannot be read as the file's answer.
"""
import json

STAGE = "5-reconcile"
TOOL = "litkb-reconcile"

#: The reconciliation parameters THE CORPUS was ingested under — the ``params`` half of the run
#: key, and therefore what decides whether a second pass over a file is the same extraction or a
#: different one. It lives here, beside :func:`params_hash`, rather than in the bulk driver,
#: because ``litkb hunt`` ingests one file through the same key and a second copy of this dict
#: would silently make every hunted file a different extraction from the corpus around it
#: (CLAUDE.md §3.3). ``qc/instruments/litkb_p5_bulk.py`` reads it from here as ``P5_PARAMS``.
#:
#: ``latex_source`` / ``latex_status``: what makes the corpus pass a different EXTRACTION of a file
#: from a bare stage-5 reconcile — the L4 formula LaTeX, and the word migration 0022 puts on every
#: equation for how far it can be trusted.
#:
#: ``merge_rule`` is the third, and it is here because of something that happened on 2026-09-16
#: rather than because it was designed in. The first stage5-3 ingest ran with a canonical merge
#: that grouped a page's readings into CONNECTED COMPONENTS; containment is not transitive, so on
#: a page where a large block nests several small ones the whole page chained into one group and
#: merged nothing. 213 documents were written that way before migration 0022's trigger stopped
#: the run on Angelopoulos_2022 p7, where 21 exact-duplicate rectangles survived. The rule is now
#: pairwise and greedy. An ``ok`` run's rows cannot be deleted by anyone — that is the design, and
#: it is what protects evidence that cites them — so the repaired ingest has to be a DIFFERENT
#: run, and ``params_hash`` is the field that says which reconciliation a run is.
#: ``merge_rule`` moved once more, in the same campaign and for the same reason: the first
#: pairwise corpus kept the SMALLER of two boxes, and coverage — which asks which of a page's
#: characters lie inside some canonical block — fell on 52 of 229 documents, Guo_2018 from 0.9913
#: to 0.4098. The merged block's box is now the UNION of the two, and an over-merge is dropped
#: only when the characters inside it are held by blocks that are staying. Third value, third set
#: of runs; the two earlier ones are superseded and their rows stand.
CORPUS_PARAMS = {"latex_source": "codeformula-l4", "latex_status": "0022",
                 "merge_rule": "pairwise-union-charcover"}


def _tool_version():
    from litkb.extract import reconcile

    return reconcile.PIPELINE_VERSION


def params_hash(params=None):
    """A stable hash of the thresholds the reconciliation ran with.

    The thresholds ARE parameters: a run made at IOU_MATCH 0.5 and one made at 0.6 are different
    extractions of the same file and must not collide on the run key.
    """
    import hashlib

    from litkb.extract import reconcile

    payload = dict(params or {})
    payload.setdefault("iou_match", reconcile.IOU_MATCH)
    payload.setdefault("iou_touch", reconcile.IOU_TOUCH)
    payload.setdefault("text_agree", reconcile.TEXT_AGREE)
    payload.setdefault("coverage_floor", reconcile.COVERAGE_FLOOR)
    # The canonical-block merge's own thresholds, on the same rule: a run that merged two boxes
    # at 80 % containment and one that required 90 % are different extractions of one file, and
    # they must not collide on the run key. Added 2026-09-16 with _merge_regions.
    payload.setdefault("contain_match", reconcile.CONTAIN_MATCH)
    payload.setdefault("overmerge_children", reconcile.OVERMERGE_CHILDREN)
    payload.setdefault("overmerge_cover", reconcile.OVERMERGE_COVER)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def run_key(file_id, pipeline_version=None, params=None):
    return dict(file_id=file_id, stage=STAGE, tool=TOOL,
                tool_version=pipeline_version or _tool_version(),
                params_hash=params_hash(params), pipeline_version=pipeline_version or _tool_version())


def already_ingested(conn, file_id, pipeline_version=None, params=None):
    """-> (run_id, status) for this file at this pipeline version, or (None, None)."""
    k = run_key(file_id, pipeline_version, params)
    row = conn.execute(
        "SELECT id, status FROM litkb.extraction_runs WHERE file_id = %(file_id)s AND stage = %(stage)s "
        "AND tool = %(tool)s AND tool_version = %(tool_version)s AND params_hash = %(params_hash)s "
        "AND pipeline_version = %(pipeline_version)s", k).fetchone()
    return (row[0], row[1]) if row else (None, None)


def _clear_run(conn, run_id):
    """Remove every text row of a run that is NOT ok — a killed worker's leftovers.

    The deletion lives in ``litkb.clear_extraction_rows`` (migration 0017), not here: the ingest
    login holds no DELETE on any table, and the function refuses a run whose status is ``ok``,
    so no holder of this privilege can pull a live run's text out from under the evidence that
    cites it.
    """
    conn.execute("SELECT litkb.clear_extraction_rows(%s)", (run_id,))


def ingest_file(conn, file_id, canonical, disagreements, stats, pages=(), *,
                artifact_path=None, host="local", pipeline_version=None, params=None,
                make_current=True, commit=True, _after_blocks=None):
    """-> {"run_id": …, "inserted": bool, "blocks": n, "disagreements": n}.

    ``pages`` is an iterable of dicts with page_no, width, height, rotation, text_layer_chars,
    needs_ocr, page_class, native_chars, covered_chars, coverage_share.

    ``_after_blocks`` is a test hook: a callable invoked after the blocks are inserted and
    before the transaction commits, which is where the simulated mid-file kill is raised.
    """
    from psycopg.types.json import Jsonb

    k = run_key(file_id, pipeline_version, params)
    existing, status = already_ingested(conn, file_id, pipeline_version, params)
    if existing and status == "ok":
        return {"run_id": existing, "inserted": False,
                "blocks": conn.execute("SELECT count(*) FROM litkb.blocks WHERE run_id = %s",
                                       (existing,)).fetchone()[0],
                "disagreements": conn.execute(
                    "SELECT count(*) FROM litkb.extraction_disagreements WHERE run_id = %s",
                    (existing,)).fetchone()[0]}

    was_autocommit = conn.autocommit
    conn.autocommit = False
    try:
        run_id = conn.execute(
            "SELECT litkb.open_extraction_run(%(file_id)s, %(stage)s, %(tool)s, %(tool_version)s, "
            "%(params_hash)s, %(pipeline_version)s, %(host)s, 'failed', %(artifact)s, %(metrics)s)",
            dict(k, host=host, artifact=artifact_path, metrics=Jsonb(stats or {}))).fetchone()[0]
        # A run that exists and is not ok is a killed worker's leftovers. They are removed in
        # THIS transaction, so the file never holds two sets of blocks, not even momentarily.
        _clear_run(conn, run_id)

        for p in pages:
            conn.execute(
                "INSERT INTO litkb.pages (file_id, run_id, page_no, width, height, rotation, "
                "text_layer_chars, needs_ocr, page_class, native_chars, covered_chars, coverage_share) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (file_id, run_id, p["page_no"], p.get("width"), p.get("height"), p.get("rotation"),
                 p.get("text_layer_chars"), p.get("needs_ocr"), p.get("page_class"),
                 p.get("native_chars"), p.get("covered_chars"), p.get("coverage_share")))

        ids = []
        for b in canonical:
            bid = conn.execute(
                "INSERT INTO litkb.blocks (file_id, run_id, page_no, bbox, reading_order, type, "
                "text, latex, extractor, confidence, canonical, provenance, text_source, source) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, %s, %s, %s) RETURNING id",
                (file_id, run_id, b.page, list(b.bbox), b.reading_order, b.db_type(),
                 b.text, b.latex, b.extractor.get("bbox", b.source), b.confidence,
                 Jsonb(b.extractor), b.text_source, b.source)).fetchone()[0]
            ids.append(bid)
            if b.kind == "table":
                conn.execute("INSERT INTO litkb.tables (block_id, n_rows, n_cols) VALUES (%s, %s, %s)",
                             (bid, b.payload.get("n_rows"), b.payload.get("n_cols")))
                for c in b.payload.get("cells") or []:
                    conn.execute(
                        "SELECT litkb.add_table_cell(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (bid, c["row"], c["col"], c["row_span"], c["col_span"], c["text"],
                         [c["x0"], c["y0"], c["x1"], c["y1"]],
                         c.get("column_header", False), c.get("row_header", False)))
            elif b.kind == "figure":
                # NO description. §4.4's `figures.description` is stage 8's vision field, paired
                # with `description_model`; the caption is already the block's own text, and
                # writing it here would read later as a model's description of the picture.
                conn.execute("INSERT INTO litkb.figures (block_id) VALUES (%s)", (bid,))
            elif b.kind == "equation":
                # `latex_status` travels WITH the string, in the same INSERT. A second pass that
                # filled it afterwards could be interrupted between the two, and a LaTeX row with
                # no word for how far it can be trusted is the state migration 0022 exists to
                # end — the referee's §3 measured 3,472 of them, about half wrong, with nothing
                # in the database saying which.
                conn.execute(
                    "INSERT INTO litkb.equations (block_id, latex, latex_status) "
                    "VALUES (%s, %s, %s)", (bid, b.latex, b.latex_status))

        if _after_blocks is not None:
            _after_blocks(conn, run_id)

        for d in disagreements:
            conn.execute(
                "SELECT litkb.add_disagreement(%s, %s, %s, %s, %s, %s, %s, 'grobid', %s, %s, "
                "'docling', %s, %s, NULL)",
                (file_id, run_id, d.page, d.kind, d.detail, d.iou,
                 list(d.bbox) if d.bbox else None,
                 d.grobid_kind, d.grobid_text, d.docling_kind, d.docling_text))

        conn.execute("SELECT litkb.finish_extraction_run(%s, 'ok', %s)", (run_id, Jsonb(stats or {})))
        if make_current:
            current = conn.execute("SELECT current_run_id FROM litkb.files WHERE id = %s",
                                   (file_id,)).fetchone()[0]
            conn.execute("SELECT litkb.set_current_run(%s, %s, %s)", (file_id, current, run_id))
        if commit:
            conn.commit()
        return {"run_id": run_id, "inserted": True, "blocks": len(ids),
                "disagreements": len(disagreements)}
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.autocommit = was_autocommit
