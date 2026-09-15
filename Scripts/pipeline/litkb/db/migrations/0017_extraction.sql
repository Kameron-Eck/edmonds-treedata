-- litkb 0017 — the P5 ingest schema: stage 5's canonical blocks, their tables, figures,
-- equations, the disagreements the two tools left behind, and the history of the current-run
-- pointer. Design §4.4 (text and structure), §7 stage 5, §14 P5.
--
-- ADDITIVE ONLY. pages, blocks, tables, figures, equations and extraction_runs were built by
-- 0001/0002 and applied migrations are checksum-locked, so this file ADDs columns to them and
-- creates only what did not exist: table_cells, extraction_disagreements, file_current_run.
--
-- WHAT IS NEW, AND WHY
--
--  * table_cells — 0002 stores a table's cells as one `tables.cells` JSON blob. A cell grid is
--    the thing stage 6/7 queries (a cell's text, its span, its box), and a blob cannot be
--    queried, indexed or joined. The rows move to their own table and `tables.cells` is RETIRED
--    by a trigger rather than by a drop: dropping it would rewrite a table 0002 owns, and the
--    trigger makes the retirement enforceable instead of documented (CLAUDE.md §3.3 — one fact,
--    one home; a JSON copy beside the rows IS the second home).
--  * extraction_disagreements — §7 stage 5 says a region the tools disagree on is KEPT and
--    marked, never silently resolved. With no table for them the only way to store a conflict
--    is to drop one tool's reading, which is the thing the rule forbids.
--  * file_current_run — files.current_run_id is a pointer with no history, so "which run was
--    current when this evidence was recorded" is unanswerable after the pointer moves. This is
--    the append-only version log of that pointer, written INSIDE set_current_run so it cannot
--    drift from it.
--  * blocks.provenance / blocks.text_source — stage 5 chooses different tools for different
--    FIELDS of one region (the native layer's characters, Docling's order, GROBID's kind is the
--    ordinary outcome). The single `extractor` column would have to name one and lie about the
--    rest; it keeps the summary and the dict goes here.
--  * pages.page_class / coverage columns — the §14 coverage metric is "share of native-layer
--    characters assigned to a canonical block", which is a per-page fact and is reported per
--    page TYPE, so both live on the page.
--
-- WHO MAY WRITE. Every insert below goes through a SECURITY DEFINER function that litkb_ingest
-- alone may EXECUTE. The three new tables grant INSERT to nobody: the function is the only
-- path, so the checks in it cannot be walked around. (blocks, pages and the rest keep the
-- direct INSERT 0010 granted the ingest login — revoking it would retire two P1-refereed tests
-- on an unrefereed change, CLAUDE.md §3.4c. Their invariants are therefore enforced by TRIGGER
-- as well, which holds on every path including the direct one.)

SET LOCAL search_path = litkb, public;

-- ── columns on the existing tables ───────────────────────────────────────────────────────

ALTER TABLE blocks
  ADD COLUMN provenance  jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN text_source text CHECK (text_source IS NULL OR text_source IN ('native', 'ocr', 'tool')),
  ADD COLUMN source      text CHECK (source IS NULL OR source IN ('grobid', 'docling', 'both'));

ALTER TABLE pages
  ADD COLUMN page_class       text CHECK (page_class IS NULL OR page_class IN ('text', 'partial', 'image-only', 'empty')),
  ADD COLUMN native_chars     integer CHECK (native_chars IS NULL OR native_chars >= 0),
  ADD COLUMN covered_chars    integer CHECK (covered_chars IS NULL OR covered_chars >= 0),
  -- NULL, never 0 and never 1, on a page with no native layer: an image-only scan has no
  -- denominator and any number there would claim a measurement that was not made.
  ADD COLUMN coverage_share   double precision
     CHECK (coverage_share IS NULL OR (coverage_share >= 0 AND coverage_share <= 1)),
  ADD CONSTRAINT pages_coverage_is_a_share CHECK (covered_chars IS NULL OR native_chars IS NULL
                                                  OR covered_chars <= native_chars);

-- ── table cells ──────────────────────────────────────────────────────────────────────────

CREATE TABLE table_cells (
  block_id      uuid NOT NULL REFERENCES blocks (id),
  row_idx       integer NOT NULL CHECK (row_idx >= 0),
  col_idx       integer NOT NULL CHECK (col_idx >= 0),
  row_span      integer NOT NULL DEFAULT 1 CHECK (row_span >= 1),
  col_span      integer NOT NULL DEFAULT 1 CHECK (col_span >= 1),
  text          text NOT NULL DEFAULT '',
  bbox          double precision[] CHECK (bbox IS NULL OR cardinality(bbox) = 4),
  column_header boolean NOT NULL DEFAULT false,
  row_header    boolean NOT NULL DEFAULT false,
  PRIMARY KEY (block_id, row_idx, col_idx)
);

-- BEGIN guard: tables.cells JSON is retired in favour of table_cells
CREATE FUNCTION litkb._tables_cells_retired() RETURNS trigger
LANGUAGE plpgsql SET search_path = litkb, public, pg_temp AS $$
BEGIN
  IF NEW.cells IS NOT NULL THEN
    RAISE EXCEPTION 'litkb: tables.cells is retired; a table''s cells are rows in table_cells'
      USING ERRCODE = '22023';
  END IF;
  RETURN NEW;
END
$$;

CREATE TRIGGER tables_cells_retired BEFORE INSERT OR UPDATE ON tables
  FOR EACH ROW EXECUTE FUNCTION litkb._tables_cells_retired();
-- END guard: tables.cells JSON is retired in favour of table_cells

-- ── disagreements ────────────────────────────────────────────────────────────────────────

CREATE TABLE extraction_disagreements (
  id           uuid PRIMARY KEY DEFAULT uuidv7(),
  file_id      uuid NOT NULL REFERENCES files (id),
  run_id       uuid NOT NULL REFERENCES extraction_runs (id),
  page_no      integer NOT NULL CHECK (page_no >= 1),
  kind         text NOT NULL CHECK (kind IN ('kind_conflict', 'text_conflict', 'partial_overlap',
                                             'grobid_only', 'docling_only')),
  detail       text NOT NULL CHECK (detail <> ''),
  iou          double precision CHECK (iou IS NULL OR (iou >= 0 AND iou <= 1)),
  bbox         double precision[] CHECK (bbox IS NULL OR cardinality(bbox) = 4),
  -- BOTH readings are kept. A disagreement row that carried only the losing side would be a
  -- record that something was discarded, not a record of what the two tools said.
  left_tool    text NOT NULL CHECK (left_tool <> ''),
  left_kind    text,
  left_text    text NOT NULL DEFAULT '',
  right_tool   text NOT NULL CHECK (right_tool <> ''),
  right_kind   text,
  right_text   text NOT NULL DEFAULT '',
  block_id     uuid REFERENCES blocks (id)
);
CREATE INDEX extraction_disagreements_run ON extraction_disagreements (run_id, page_no);

-- ── the current-run pointer, versioned ───────────────────────────────────────────────────

CREATE TABLE file_current_run (
  id              uuid PRIMARY KEY DEFAULT uuidv7(),
  file_id         uuid NOT NULL REFERENCES files (id),
  version_no      integer NOT NULL CHECK (version_no >= 1),
  run_id          uuid NOT NULL REFERENCES extraction_runs (id),
  previous_run_id uuid REFERENCES extraction_runs (id),
  set_at          timestamptz NOT NULL DEFAULT now(),
  -- session_user, not current_user: inside a SECURITY DEFINER function current_user is the
  -- function's owner, which would record every move as litkb_owner's.
  set_by          text NOT NULL DEFAULT session_user,
  UNIQUE (file_id, version_no),
  CONSTRAINT file_current_run_moves CHECK (run_id IS DISTINCT FROM previous_run_id)
);

-- ── set_current_run, keeping every rule 0007 gave it, plus the history row ────────────────
--
-- 0007's two guards are reproduced verbatim in effect: the new run must exist, be this file's,
-- and be 'ok' (a failed run, another file's run and NULL are all refused with the same message
-- and SQLSTATE the P1 tests match on), and the pointer moves only by compare-and-set. The one
-- addition is the file_current_run row, written in the SAME transaction as the UPDATE so the
-- history cannot disagree with the pointer.
CREATE OR REPLACE FUNCTION litkb.set_current_run(p_file uuid, p_expected_run uuid, p_new_run uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_n bigint;
BEGIN
  -- BEGIN guard: current run is an ok run of this file
  PERFORM 1 FROM extraction_runs r
   WHERE r.id = p_new_run
     AND r.file_id = p_file
     AND r.status = 'ok';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: run % is not an ok extraction run of file %', coalesce(p_new_run::text, '(none)'), p_file
      USING ERRCODE = '22023';
  END IF;
  -- END guard: current run is an ok run of this file
  UPDATE files f SET current_run_id = p_new_run
   WHERE f.id = p_file AND f.current_run_id IS NOT DISTINCT FROM p_expected_run;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  IF v_n <> 1 THEN
    RAISE EXCEPTION 'litkb CAS refused: file % is no longer at run %', p_file, coalesce(p_expected_run::text, '(none)')
      USING ERRCODE = '40001';
  END IF;
  INSERT INTO file_current_run (file_id, version_no, run_id, previous_run_id)
  SELECT p_file, coalesce(max(version_no), 0) + 1, p_new_run, p_expected_run
    FROM file_current_run WHERE file_id = p_file;
END
$$;

-- ── the checked writers ──────────────────────────────────────────────────────────────────

-- Idempotent by the run key (file sha256 is the file row; stage, tool, tool_version,
-- params_hash and pipeline_version are the rest of 0001's UNIQUE). A second call with the same
-- key INSERTS NOTHING and returns the run that is already there, which is what lets a killed
-- worker resume: it finds its own run and its own rows instead of making a second set.
CREATE FUNCTION litkb.open_extraction_run(
    p_file uuid, p_stage text, p_tool text, p_tool_version text, p_params_hash text,
    p_pipeline_version text, p_host text, p_status text, p_artifact text, p_metrics jsonb)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_id uuid;
BEGIN
  INSERT INTO extraction_runs (file_id, stage, tool, tool_version, params_hash, pipeline_version,
                               host, status, artifact_path, metrics)
  VALUES (p_file, p_stage, p_tool, p_tool_version, p_params_hash, p_pipeline_version,
          p_host, p_status, p_artifact, coalesce(p_metrics, '{}'::jsonb))
  ON CONFLICT (file_id, stage, tool, tool_version, params_hash, pipeline_version) DO NOTHING
  RETURNING id INTO v_id;
  IF v_id IS NULL THEN
    SELECT id INTO v_id FROM extraction_runs
     WHERE file_id = p_file AND stage = p_stage AND tool = p_tool AND tool_version = p_tool_version
       AND params_hash = p_params_hash AND pipeline_version = p_pipeline_version;
  END IF;
  RETURN v_id;
END
$$;

CREATE FUNCTION litkb.finish_extraction_run(p_run uuid, p_status text, p_metrics jsonb)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
BEGIN
  IF p_status NOT IN ('ok', 'failed') THEN
    RAISE EXCEPTION 'litkb: extraction status % is neither ok nor failed', p_status USING ERRCODE = '22023';
  END IF;
  -- BEGIN guard: a reconciliation run with no blocks cannot be declared ok
  -- Only the reconciliation stage: stage 0 writes pages and no blocks, and refusing THAT run
  -- would be this guard firing on a correct input.
  IF p_status = 'ok'
     AND EXISTS (SELECT 1 FROM extraction_runs r WHERE r.id = p_run AND r.stage = '5-reconcile')
     AND NOT EXISTS (SELECT 1 FROM blocks WHERE run_id = p_run) THEN
    RAISE EXCEPTION 'litkb: reconciliation run % has no blocks and cannot be ok', p_run
      USING ERRCODE = '22023';
  END IF;
  -- END guard: a reconciliation run with no blocks cannot be declared ok
  UPDATE extraction_runs SET status = p_status,
         metrics = coalesce(p_metrics, metrics)
   WHERE id = p_run;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: no extraction run %', p_run USING ERRCODE = '23503';
  END IF;
END
$$;

-- The resume path. A run that exists and is NOT ok is a killed worker's carcass; its rows are
-- removed inside the resuming transaction so the file never holds two sets of blocks. The
-- ingest login holds no DELETE on any table, so this is the only way to do it — and the guard
-- below is why that is the right shape: an OK run's text can never be deleted, by anyone
-- holding only this function, so a live run's evidence cannot be pulled out from under it.
CREATE FUNCTION litkb.clear_extraction_rows(p_run uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
BEGIN
  -- BEGIN guard: an ok run's rows are never cleared
  IF EXISTS (SELECT 1 FROM extraction_runs r WHERE r.id = p_run AND r.status = 'ok') THEN
    RAISE EXCEPTION 'litkb: run % is ok; its text rows are immutable', p_run USING ERRCODE = '22023';
  END IF;
  -- END guard: an ok run's rows are never cleared
  DELETE FROM table_cells WHERE block_id IN (SELECT id FROM blocks WHERE run_id = p_run);
  DELETE FROM tables  WHERE block_id IN (SELECT id FROM blocks WHERE run_id = p_run);
  DELETE FROM figures WHERE block_id IN (SELECT id FROM blocks WHERE run_id = p_run);
  DELETE FROM equations WHERE block_id IN (SELECT id FROM blocks WHERE run_id = p_run);
  DELETE FROM extraction_disagreements WHERE run_id = p_run;
  DELETE FROM citation_mentions WHERE block_id IN (SELECT id FROM blocks WHERE run_id = p_run);
  DELETE FROM "references" WHERE run_id = p_run;
  UPDATE blocks SET parent_block_id = NULL WHERE run_id = p_run;
  DELETE FROM blocks WHERE run_id = p_run;
  DELETE FROM pages WHERE run_id = p_run;
END
$$;

CREATE FUNCTION litkb.add_table_cell(
    p_block uuid, p_row integer, p_col integer, p_row_span integer, p_col_span integer,
    p_text text, p_bbox double precision[], p_column_header boolean, p_row_header boolean)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
BEGIN
  -- BEGIN guard: a cell belongs to a table block
  PERFORM 1 FROM blocks b WHERE b.id = p_block AND b.type = 'table';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: block % is not a table block; a cell cannot hang below it', p_block
      USING ERRCODE = '22023';
  END IF;
  -- END guard: a cell belongs to a table block
  INSERT INTO table_cells (block_id, row_idx, col_idx, row_span, col_span, text, bbox,
                           column_header, row_header)
  VALUES (p_block, p_row, p_col, coalesce(p_row_span, 1), coalesce(p_col_span, 1),
          coalesce(p_text, ''), p_bbox, coalesce(p_column_header, false), coalesce(p_row_header, false))
  ON CONFLICT (block_id, row_idx, col_idx) DO NOTHING;
END
$$;

CREATE FUNCTION litkb.add_disagreement(
    p_file uuid, p_run uuid, p_page integer, p_kind text, p_detail text, p_iou double precision,
    p_bbox double precision[], p_left_tool text, p_left_kind text, p_left_text text,
    p_right_tool text, p_right_kind text, p_right_text text, p_block uuid)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_id uuid;
BEGIN
  -- BEGIN guard: the disagreement's run is the file's run
  PERFORM 1 FROM extraction_runs r WHERE r.id = p_run AND r.file_id = p_file;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: run % is not a run of file %', p_run, p_file USING ERRCODE = '22023';
  END IF;
  -- END guard: the disagreement's run is the file's run
  INSERT INTO extraction_disagreements (file_id, run_id, page_no, kind, detail, iou, bbox,
                                        left_tool, left_kind, left_text,
                                        right_tool, right_kind, right_text, block_id)
  VALUES (p_file, p_run, p_page, p_kind, p_detail, p_iou, p_bbox,
          p_left_tool, p_left_kind, coalesce(p_left_text, ''),
          p_right_tool, p_right_kind, coalesce(p_right_text, ''), p_block)
  RETURNING id INTO v_id;
  RETURN v_id;
END
$$;

-- ── invariants that hold on EVERY path, the direct INSERT included ────────────────────────

-- BEGIN guard: a block's run belongs to the block's file
CREATE FUNCTION litkb._block_run_matches_file() RETURNS trigger
LANGUAGE plpgsql SET search_path = litkb, public, pg_temp AS $$
BEGIN
  PERFORM 1 FROM extraction_runs r WHERE r.id = NEW.run_id AND r.file_id = NEW.file_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: run % is not a run of file %', NEW.run_id, NEW.file_id
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$$;

CREATE TRIGGER blocks_run_matches_file BEFORE INSERT OR UPDATE ON blocks
  FOR EACH ROW EXECUTE FUNCTION litkb._block_run_matches_file();
CREATE TRIGGER pages_run_matches_file BEFORE INSERT OR UPDATE ON pages
  FOR EACH ROW EXECUTE FUNCTION litkb._block_run_matches_file();
-- END guard: a block's run belongs to the block's file

-- A canonical block is the reconciliation's output and must carry a reading order: a canonical
-- set with a NULL order cannot be read back in order, and stage 7's chunks are built from it.
-- BEGIN guard: a canonical block carries a reading order
ALTER TABLE blocks ADD CONSTRAINT blocks_canonical_has_order
  CHECK (NOT canonical OR reading_order IS NOT NULL);
-- END guard: a canonical block carries a reading order

-- Exactly one canonical block per (run, reading_order): stage 5 numbers them 0..n-1, and two
-- blocks at one position is the interleaved-order defect arriving in the database.
CREATE UNIQUE INDEX blocks_canonical_order ON blocks (run_id, reading_order) WHERE canonical;

-- ── grants ───────────────────────────────────────────────────────────────────────────────
--
-- The three new tables get NO direct INSERT. The functions are the only writers, so their
-- checks are not optional, and the role matrix test (qc/test_litkb_p1.py) pins that.
GRANT SELECT ON table_cells, extraction_disagreements, file_current_run TO litkb_reader, litkb_writer, litkb_ingest;
GRANT EXECUTE ON FUNCTION litkb.open_extraction_run(uuid, text, text, text, text, text, text, text, text, jsonb) TO litkb_ingest;
GRANT EXECUTE ON FUNCTION litkb.finish_extraction_run(uuid, text, jsonb) TO litkb_ingest;
GRANT EXECUTE ON FUNCTION litkb.clear_extraction_rows(uuid) TO litkb_ingest;
GRANT EXECUTE ON FUNCTION litkb.add_table_cell(uuid, integer, integer, integer, integer, text, double precision[], boolean, boolean) TO litkb_ingest;
GRANT EXECUTE ON FUNCTION litkb.add_disagreement(uuid, uuid, integer, text, text, double precision, double precision[], text, text, text, text, text, text, uuid) TO litkb_ingest;
