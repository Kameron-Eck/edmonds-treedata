-- litkb 0031 — retiring superseded extraction run sets: a deliberate op that MARKS, never deletes.
--
-- WHY (LITKB_WORKPLAN.md §S4, Work bullet 3; S4 run 3 decision D6). Every change of a run key's
-- params_hash or pipeline_version makes a NEW run beside the old one and moves the file's pointer
-- (litkb.extract.ingest); the old run's rows stay, because an ok run's rows are immutable
-- (0017 clear_extraction_rows refuses them) and history rows point at them (0017 file_current_run).
-- Measured 2026-09-22 (survey-data D6): 676 non-current 5-reconcile runs hold 267,545 of the
-- 372,305 blocks, and 6 of those runs carry use_evidence. Deleting them is destructive and is not
-- S4's call (D6). What this migration adds is a RECORD: which runs a deliberate op retired, when,
-- by which login and session, and why — so "these rows are superseded and nobody needs them" is a
-- fact in the database instead of an inference every reader has to redo.
--
-- ADDITIVE, with ONE exception. No existing table, CHECK or trigger is changed, so every existing
-- reader keeps its meaning: search, use.locate_quote and promotion's run_is_current already read
-- only a file's CURRENT run, and a retired run is never current — the op refuses the current run,
-- and (the exception, orchestrator ruling Q2, at the end of this file) set_current_run is
-- re-created as 0017's definition byte for byte plus one guard refusing a retired run, so the
-- pointer can never be moved back onto one.
--
-- WHAT "SUPERSEDED AT ITS STAGE" MEANS — two rules, one per kind of stage, both in
-- run_retirement_status below and nowhere else:
--   * a run that was EVER a file's current run (a file_current_run row names it) is superseded
--     when the file's pointer has since moved to ANOTHER ok run of the SAME stage. That is every
--     5-reconcile run the pointer left behind.
--   * a run that was NEVER current — stage 6 (6-references) never moves the pointer
--     (litkb.extract.references_ingest header) — is superseded when the file holds a NEWER ok run
--     at the stage's current key, which the caller names (p_keys, keyed by stage; the CLI reads it
--     from litkb.extract.references_ingest.run_key, never a copy). "Newer" is the database's own
--     check on the caller: a key naming an OLDER run as current supersedes nothing.
--   Only ok runs are ever superseded; a failed run is a carcass the resume path already clears.
--
-- REFUSED, each by its own guard in retire_extraction_runs: a file's current run; a run any
-- use_evidence row cites (by run_id, or by a block of the run); a run that is not superseded at
-- its stage; a run already retired.

SET LOCAL search_path = litkb, public;

CREATE TABLE run_retirement_ops (
  op_id         uuid PRIMARY KEY DEFAULT uuidv7(),
  retired_at    timestamptz NOT NULL DEFAULT now(),
  -- session_user, not current_user: inside the SECURITY DEFINER function current_user is the
  -- owner (0017 file_current_run.set_by, same reason)
  retired_by    text NOT NULL DEFAULT session_user,
  session_label text NOT NULL CHECK (btrim(session_label) <> ''),
  reason        text NOT NULL CHECK (btrim(reason) <> ''),
  runs          integer NOT NULL CHECK (runs >= 1),
  -- the stage keys the op was given (p_keys), kept so the "superseded" verdict can be re-read
  keys          jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE run_retirements (
  run_id        uuid PRIMARY KEY REFERENCES extraction_runs (id),   -- a run is retired at most once
  op_id         uuid NOT NULL REFERENCES run_retirement_ops (op_id),
  file_id       uuid NOT NULL REFERENCES files (id),
  stage         text NOT NULL CHECK (stage <> ''),
  -- the run that superseded it at the moment of retirement
  superseded_by uuid NOT NULL REFERENCES extraction_runs (id),
  -- the run's rows at the moment of retirement (they are not touched; this is what was marked)
  blocks        bigint NOT NULL CHECK (blocks >= 0),
  pages         bigint NOT NULL CHECK (pages >= 0),
  reference_rows bigint NOT NULL CHECK (reference_rows >= 0),
  CONSTRAINT run_retirements_not_self CHECK (superseded_by <> run_id)
);
CREATE INDEX run_retirements_op ON run_retirements (op_id);

COMMENT ON TABLE run_retirement_ops IS
  'One deliberate retirement op (litkb runs retire --apply, migration 0031): who, when, why. Written only by retire_extraction_runs.';
COMMENT ON TABLE run_retirements IS
  'Runs a retirement op MARKED superseded. Nothing is deleted: the run row and its blocks, pages and references stay. Written only by retire_extraction_runs.';

-- ── the one home of the rule ─────────────────────────────────────────────────────────────
-- One row per extraction run (or per run of p_runs), with the facts the op decides on and the
-- verdict: refusal NULL means the run may be retired now. SECURITY INVOKER: the reader calls it
-- for the dry run with its own SELECT rights; retire_extraction_runs calls it as the owner.
CREATE FUNCTION litkb.run_retirement_status(p_keys jsonb DEFAULT NULL, p_runs uuid[] DEFAULT NULL)
RETURNS TABLE (run_id uuid, file_id uuid, stage text, pipeline_version text, status text,
               is_current boolean, was_current boolean, evidence_rows bigint,
               superseded_by uuid, retired_op uuid, refusal text)
LANGUAGE sql STABLE SET search_path = litkb, public, pg_temp AS $$
  WITH cited AS (
    SELECT e.run_id AS rid FROM use_evidence e
    UNION ALL
    SELECT b.run_id FROM use_evidence e JOIN blocks b ON b.id = e.block_id),
  facts AS (
    SELECT r.id, r.file_id, r.stage, r.pipeline_version, r.status, r.created_at,
           r.tool, r.tool_version, r.params_hash,
           EXISTS (SELECT 1 FROM files f WHERE f.current_run_id = r.id) AS is_current,
           EXISTS (SELECT 1 FROM file_current_run h WHERE h.run_id = r.id) AS was_current,
           (SELECT count(*) FROM cited c WHERE c.rid = r.id) AS evidence_rows,
           (SELECT x.op_id FROM run_retirements x WHERE x.run_id = r.id) AS retired_op,
           f.current_run_id AS file_current
      FROM extraction_runs r JOIN files f ON f.id = r.file_id
     WHERE p_runs IS NULL OR r.id = ANY (p_runs)),
  judged AS (
    SELECT fa.*,
           CASE
             WHEN fa.status <> 'ok' THEN NULL
             -- rule 1: the pointer left this run for another ok run of the same stage
             WHEN fa.was_current THEN
               (SELECT c.id FROM extraction_runs c
                 WHERE c.id = fa.file_current AND c.id <> fa.id
                   AND c.stage = fa.stage AND c.status = 'ok')
             -- rule 2: a never-current run, and a NEWER ok run at the stage's named current key
             ELSE
               (SELECT n.id FROM extraction_runs n
                 WHERE p_keys ? fa.stage
                   AND n.file_id = fa.file_id AND n.stage = fa.stage AND n.status = 'ok'
                   AND n.id <> fa.id AND n.created_at > fa.created_at
                   AND n.tool = p_keys -> fa.stage ->> 'tool'
                   AND n.tool_version = p_keys -> fa.stage ->> 'tool_version'
                   AND n.params_hash = p_keys -> fa.stage ->> 'params_hash'
                   AND n.pipeline_version = p_keys -> fa.stage ->> 'pipeline_version'
                   AND (fa.tool, fa.tool_version, fa.params_hash, fa.pipeline_version)
                       IS DISTINCT FROM (n.tool, n.tool_version, n.params_hash, n.pipeline_version)
                 ORDER BY n.created_at DESC LIMIT 1)
           END AS superseded_by
      FROM facts fa)
  SELECT j.id, j.file_id, j.stage, j.pipeline_version, j.status, j.is_current, j.was_current,
         j.evidence_rows, j.superseded_by, j.retired_op,
         CASE
           WHEN j.is_current THEN 'current'
           WHEN j.evidence_rows > 0 THEN 'evidence'
           WHEN j.retired_op IS NOT NULL THEN 'already-retired'
           WHEN j.superseded_by IS NULL THEN 'not-superseded'
         END
    FROM judged j
$$;

-- ── the op ───────────────────────────────────────────────────────────────────────────────
CREATE FUNCTION litkb.retire_extraction_runs(p_runs uuid[], p_session text, p_reason text,
                                             p_keys jsonb DEFAULT NULL)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_op  uuid;
  v_bad text;
BEGIN
  IF p_runs IS NULL OR cardinality(p_runs) = 0 THEN
    RAISE EXCEPTION 'litkb: a retirement op names at least one run' USING ERRCODE = '22023';
  END IF;
  IF (SELECT count(DISTINCT x) FROM unnest(p_runs) x) <> cardinality(p_runs) THEN
    RAISE EXCEPTION 'litkb: a retirement op names each run once' USING ERRCODE = '22023';
  END IF;
  SELECT string_agg(x::text, ', ') INTO v_bad FROM unnest(p_runs) x
   WHERE NOT EXISTS (SELECT 1 FROM extraction_runs r WHERE r.id = x);
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'litkb: no extraction run %', v_bad USING ERRCODE = '23503';
  END IF;
  -- the files' pointers cannot move under the verdict: set_current_run UPDATEs this row, and
  -- waits here until the op commits
  PERFORM 1 FROM files f WHERE f.id IN (SELECT r.file_id FROM extraction_runs r WHERE r.id = ANY (p_runs))
     FOR UPDATE;

  -- BEGIN guard: a file's current run is never retired
  SELECT string_agg(s.run_id::text, ', ') INTO v_bad FROM run_retirement_status(p_keys, p_runs) s
   WHERE s.is_current;
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'litkb: run(s) % are a file''s current run and are never retired', v_bad
      USING ERRCODE = '22023';
  END IF;
  -- END guard: a file's current run is never retired

  -- BEGIN guard: a run use_evidence cites is never retired
  SELECT string_agg(s.run_id::text, ', ') INTO v_bad FROM run_retirement_status(p_keys, p_runs) s
   WHERE s.evidence_rows > 0;
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'litkb: run(s) % are cited by use_evidence and are never retired', v_bad
      USING ERRCODE = '22023';
  END IF;
  -- END guard: a run use_evidence cites is never retired

  -- BEGIN guard: only a run superseded at its stage is retired
  SELECT string_agg(s.run_id::text, ', ') INTO v_bad FROM run_retirement_status(p_keys, p_runs) s
   WHERE s.superseded_by IS NULL;
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'litkb: run(s) % are not superseded at their stage', v_bad
      USING ERRCODE = '22023';
  END IF;
  -- END guard: only a run superseded at its stage is retired

  -- BEGIN guard: a run is retired once
  SELECT string_agg(s.run_id::text, ', ') INTO v_bad FROM run_retirement_status(p_keys, p_runs) s
   WHERE s.retired_op IS NOT NULL;
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'litkb: run(s) % are already retired', v_bad USING ERRCODE = '23505';
  END IF;
  -- END guard: a run is retired once

  INSERT INTO run_retirement_ops (session_label, reason, runs, keys)
  VALUES (p_session, p_reason, cardinality(p_runs), coalesce(p_keys, '{}'::jsonb))
  RETURNING op_id INTO v_op;
  INSERT INTO run_retirements (run_id, op_id, file_id, stage, superseded_by, blocks, pages, reference_rows)
  SELECT s.run_id, v_op, s.file_id, s.stage, s.superseded_by,
         (SELECT count(*) FROM blocks b WHERE b.run_id = s.run_id),
         (SELECT count(*) FROM pages p WHERE p.run_id = s.run_id),
         (SELECT count(*) FROM "references" x WHERE x.run_id = s.run_id)
    FROM run_retirement_status(p_keys, p_runs) s;
  RETURN v_op;
END
$$;

-- ── grants ───────────────────────────────────────────────────────────────────────────────
-- No role holds a direct write on either table: retire_extraction_runs is their only writer.
REVOKE ALL ON run_retirement_ops, run_retirements FROM PUBLIC;
GRANT SELECT ON run_retirement_ops, run_retirements TO litkb_reader, litkb_ingest;
REVOKE EXECUTE ON FUNCTION litkb.run_retirement_status(jsonb, uuid[]) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION litkb.retire_extraction_runs(uuid[], text, text, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION litkb.run_retirement_status(jsonb, uuid[]) TO litkb_reader;
GRANT EXECUTE ON FUNCTION litkb.retire_extraction_runs(uuid[], text, text, jsonb) TO litkb_ingest;


-- ── set_current_run refuses a retired run (orchestrator ruling Q2, 2026-09-22) ──────────────
-- 0017's definition BYTE FOR BYTE, plus the one guard marked below: every other rule (ok run of
-- this file, compare-and-set, SQLSTATE 22023/40001, the file_current_run history row) is
-- unchanged. CREATE OR REPLACE keeps the function's owner and ACL, so the grants (0010: EXECUTE
-- to litkb_ingest, revoked from litkb_writer) and the role matrix are unchanged.
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
  -- BEGIN guard: a retired run never becomes current
  -- 0031: a run a retirement op marked superseded stays superseded. Without this the pointer
  -- could be moved back onto it and the file's current run would be a retired one.
  IF EXISTS (SELECT 1 FROM run_retirements x WHERE x.run_id = p_new_run) THEN
    RAISE EXCEPTION 'litkb: run % is retired and never becomes current again', p_new_run
      USING ERRCODE = '22023';
  END IF;
  -- END guard: a retired run never becomes current
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

-- end of 0031
