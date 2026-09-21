-- litkb 0030 — retiring a superseded extraction run set: a THIRD status, and one function that
-- may set it.
--
-- WHY. 229 of the 233 files that hold blocks hold them under more than one run, and 267,545 of
-- 372,305 blocks (71.9 %, measured on the 2026-09-21 live dump) belong to a run that is no longer
-- any file's `current_run_id`. Nothing in the schema said so. "Superseded" was COMPUTED — `NOT
-- EXISTS (SELECT 1 FROM files f WHERE f.current_run_id = r.id)` — and hand-spelled at five read
-- sites (mcp/server.py:325 and :747, use.py:191, review_check.py:787, review_context.py:50), so a
-- sixth reader that forgot the join saw 3.55x the corpus, most of it stale text that is no longer
-- the file's answer. Every one of those stale blocks also carried `canonical = true`, which made
-- the word mean "ordered within its own run" rather than "the live text of this file".
--
-- WHAT THIS DOES NOT DO: DELETE. Design §12.4 — no deletes. A retired run keeps its row, its
-- metrics, its blocks and every child row hanging off them; what changes is that the run SAYS it
-- is superseded and its blocks say they are not canonical. The provenance of a quote taken against
-- that run in the past is therefore still readable, which is the whole reason `clear_extraction_
-- rows` (0017) refuses to delete an `ok` run's text and why this file does not widen that refusal.
--
-- 1. THE THIRD STATUS. `extraction_runs.status` was `CHECK (status IN ('ok','failed'))`
--    (0001_core.sql:219). 0022's DROP-then-ADD pattern is used rather than an edit to 0001,
--    because applied migrations are checksum-locked and editing 0001 would give a freshly built
--    database a different schema from the live one — the defect 0021 exists to undo.
--    `superseded` is deliberately NOT accepted by `litkb.finish_extraction_run` (0017), which
--    still refuses anything but ok/failed: a run is finished ok or failed, and it becomes
--    superseded LATER, by this file's function and by nothing else.
--
-- 2. `litkb.retire_run(p_run uuid) RETURNS integer` — the number of blocks it took out of the
--    canonical set. SECURITY DEFINER, EXECUTE granted to `litkb_ingest` alone, on 0017's rule:
--    the ingest login holds no DELETE and no UPDATE on `extraction_runs`, so a function with its
--    own guards is the only door, and the guards cannot be walked around.
--
--    IT REFUSES, in this order:
--      a. no such run                                 — 23503
--      b. the run is its file's `current_run_id`      — 22023. Retiring the pointer's own target
--         would leave the file with a current run whose blocks are all non-canonical, i.e. a file
--         that reads `extracted` and answers nothing. Re-point first (`set_current_run`), then
--         retire.
--      c. a `use_evidence` row anchors a block of this run — 22023. This is the one refusal that
--         is about somebody ELSE's record rather than about consistency.
--
--    WHICH TABLES REFERENCE `blocks`, checked against the restored 2026-09-21 corpus rather than
--    assumed (pg_constraint, contype='f', confrelid='litkb.blocks'): eleven foreign keys in ten
--    columns — blocks.parent_block_id, citation_mentions.block_id, equations.block_id,
--    extraction_disagreements.block_id, figures.block_id, figures.caption_block_id,
--    "references".block_id, table_cells.block_id, tables.block_id, tables.caption_block_id and
--    use_evidence.block_id. TEN of those eleven are rows of the SAME extraction run — the
--    structures the reconciler emitted beside the block, which are superseded exactly when it is
--    and are left alone here for the same provenance reason the blocks are. `use_evidence` is the
--    eleventh and the only one written by a different actor at a different time: it is a USE's
--    quote anchor (0002_text.sql:111-125, one row per quote, `run_id` beside `block_id`), and
--    `use_evidence_status.promotable` (0004_views.sql:60) already compares that `run_id` against
--    `files.current_run_id`. Retiring a run an evidence row is anchored in would turn a promotable
--    use into one anchored in text the database now calls non-canonical, silently, so it is
--    refused and the caller is told which use.
--
-- 3. WHAT `canonical = false` MEANS AFTER THIS FILE: not searchable, not quotable, not gradable.
--    The predicate is NOT a view and not a SQL function here, and that is deliberate — the same
--    reasoning `litkb.visibility`'s module docstring gives for `FILE_JOIN`: a function would need
--    every reader to have this migration applied before it could be called, and between a merge
--    and its migration the live database would raise `UndefinedFunction` at every search. So the
--    rule is ONE Python SQL fragment, `litkb.readability.current_run_join()`, which spells
--    `f.current_run_id = b.run_id AND b.canonical` and replaces all five hand-written copies.
--    The two GIN indexes on `blocks` (`blocks_norm_text_fts`, `blocks_norm_text_trgm`, 0018/0025)
--    index every block regardless of `canonical` and are left as they are: they are the index, the
--    predicate is the gate, and a partial index here would have to be rebuilt by every future
--    change to the word. `blocks_canonical_order` (0022, UNIQUE on (run_id, reading_order) WHERE
--    canonical) simply loses the retired rows, which is correct: they are no longer canonical.
--
-- SCOPE: one CHECK constraint replaced, one new function, one grant. No existing function body is
-- replaced, so the two-branches-one-function hazard `_reserved.txt` warns about does not apply.

SET LOCAL search_path = litkb, public;

-- BEGIN: a run may also be superseded
ALTER TABLE extraction_runs DROP CONSTRAINT extraction_runs_status_check;
ALTER TABLE extraction_runs ADD CONSTRAINT extraction_runs_status_check
  CHECK (status IN ('ok', 'failed', 'superseded'));
-- END

CREATE FUNCTION litkb.retire_run(p_run uuid) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_status text;
  v_file   uuid;
  v_use    uuid;
  v_n      integer;
BEGIN
  SELECT r.status, r.file_id INTO v_status, v_file FROM extraction_runs r WHERE r.id = p_run;
  -- BEGIN guard: retire_run names a run that exists
  IF v_status IS NULL THEN
    RAISE EXCEPTION 'litkb: no extraction run %', p_run USING ERRCODE = '23503';
  END IF;
  -- END guard: retire_run names a run that exists
  -- Already retired: a no-op, not a refusal. `retire-runs --apply` re-run over the same file must
  -- be safe, and the second call has nothing to do rather than something to complain about.
  IF v_status = 'superseded' THEN
    RETURN 0;
  END IF;
  -- BEGIN guard: the file's current run is never retired
  PERFORM 1 FROM files f WHERE f.id = v_file AND f.current_run_id = p_run;
  IF FOUND THEN
    RAISE EXCEPTION 'litkb: run % is the current run of file %; re-point the file first '
                    '(set_current_run), then retire it', p_run, v_file USING ERRCODE = '22023';
  END IF;
  -- END guard: the file's current run is never retired
  -- BEGIN guard: a run a use quotes is never retired
  SELECT e.use_version_id INTO v_use FROM use_evidence e
    JOIN blocks b ON b.id = e.block_id
   WHERE b.run_id = p_run LIMIT 1;
  IF v_use IS NOT NULL THEN
    RAISE EXCEPTION 'litkb: run % is quoted by use version % (use_evidence); retiring it would '
                    'leave that evidence anchored in text the database calls non-canonical',
                    p_run, v_use USING ERRCODE = '22023';
  END IF;
  -- END guard: a run a use quotes is never retired
  UPDATE blocks SET canonical = false WHERE run_id = p_run AND canonical;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  UPDATE extraction_runs SET status = 'superseded' WHERE id = p_run;
  RETURN v_n;
END
$$;

GRANT EXECUTE ON FUNCTION litkb.retire_run(uuid) TO litkb_ingest;

COMMENT ON FUNCTION litkb.retire_run(uuid) IS
  'Mark one extraction run superseded and take its blocks out of the canonical set. Refuses the '
  'file''s current run and any run a use_evidence row is anchored in. Never deletes (design '
  '§12.4); the blocks stay for provenance. Driven by `litkb retire-runs --apply`.';
