-- litkb 0029 — extraction_jobs: the leased, resumable extraction queue. Design §4.3 (the table),
-- §12.3 (enqueue by sweep, claim with a lease, failure and death), §12.4 (skip what is done, one
-- transaction per unit) and §12.5 (a crash loses at most one job).
--
-- ADDITIVE ONLY. Nothing here alters an applied migration: one new table, one unique index, two
-- ordinary indexes and seven functions. `extraction_runs` is untouched — S4 needed no column on
-- it, because `metrics` (jsonb, NOT NULL, 0001_core.sql:222) already carries every per-run number
-- the worker records.
--
-- WHY A TABLE AND NOT A DISK CHECKPOINT. `qc/instruments/litkb_p5_bulk.py` checkpoints on disk
-- (an artifact plus a .sha256 sidecar) and its own docstring says what that cannot do: it makes a
-- killed worker's RESUME safe, and it does nothing at all about two workers doing one file. The
-- only concurrency control in the database today is the `extraction_runs` unique key, which makes
-- a double extraction IDEMPOTENT but not EXCLUSIVE — both workers do the work, and the loser's
-- `clear_extraction_rows` can delete the winner's rows while the winner's run is still `failed`,
-- i.e. mid-flight. That race is what the lease closes.
--
-- THE OWNERSHIP GATE. Every function that MUTATES a job (renew_lease, finish_job, fail_job,
-- classify_job) first calls `litkb._job_lease_held(job, token)`, which raises unless the row is
-- `leased`, its `lease_token` equals the token presented, and its lease has not expired. Without
-- it a worker whose lease ran out — one that was paused, swapped out or simply slow — finishes a
-- job a SECOND worker is now doing, and the two write the same file's rows under two runs. The
-- token is a value the claimer alone receives (claim_jobs RETURNS it; nothing else exposes it to
-- a caller that did not claim), so holding it is the evidence of ownership; it is checked, not
-- the worker NAME, because a name is guessable and a restarted worker legitimately reuses one.
--
-- WHAT "DONE" MEANS FOR WORK THAT PREDATES THE QUEUE. 233 of the 251 active files already carry
-- an `ok` run at today's run key, made by the bulk pass before this table existed. §12.4's rule is
-- "a claimed job whose run key already has an `ok` run is marked done without running the tool",
-- and `enqueue_extraction` applies it at ENQUEUE instead of at claim: the sweep looks for that run
-- and, when it finds one, inserts the job already `done` with `run_id` pointing at it. Same rule,
-- one pass earlier. The ledger is then COMPLETE — every active file has a row saying what happened
-- to it — and the first sweep still queues only the 18 files that have no run, so the queue is not
-- 233 claims that do nothing. The run key is the file's row plus (stage, tool, tool_version,
-- params_hash, pipeline_version): a re-ingest at a new pipeline version is a different key, gets no
-- `ok` run, and is queued for real.
--
-- RESIDUE IS A STATE, NOT A SILENCE. `classified` is a terminal state with a `residue_class`
-- naming WHY a bound file produced no text: `scan-needs-ocr`, `over-page-cap`, `zero-content`,
-- `bad-file` (S4 D1). Before this table those four outcomes were indistinguishable from "nobody
-- has run it yet" — a file with no run, and nothing anywhere saying whether that was a backlog or
-- a refusal. `dead` is the different fact: the tool was run, it failed, and it failed the number
-- of times the caller was willing to spend. A CHECK ties the two together so a `classified` row
-- always carries a class and no other state ever does.
--
-- NO workstream_id, by design §4.7: the table hangs below `files`, a main-owned identity table,
-- so it sits outside the workstream guard. No agent role may INSERT, UPDATE or DELETE a row — the
-- seven functions are the only writers and `litkb_ingest` alone may EXECUTE them, which is what
-- puts the checks in them on every path (the 0017 shape, pinned by the role-privilege matrix in
-- qc/test_litkb_p1.py).

SET LOCAL search_path = litkb, public;

-- ── the queue ────────────────────────────────────────────────────────────────────────────

CREATE TABLE extraction_jobs (
  id               uuid PRIMARY KEY DEFAULT uuidv7(),
  file_id          uuid NOT NULL REFERENCES files (id),
  stage            text NOT NULL CHECK (stage <> ''),
  -- NULL/NULL is the whole file. §12.5 splits a long document into page-range jobs so the unit of
  -- loss stays one job; nothing splits one today, and the columns are here so that when something
  -- does it is not a migration.
  page_start       integer CHECK (page_start IS NULL OR page_start >= 1),
  page_end         integer CHECK (page_end IS NULL OR page_end >= 1),
  tool             text NOT NULL CHECK (tool <> ''),
  tool_version     text NOT NULL CHECK (tool_version <> ''),
  params_hash      text NOT NULL CHECK (params_hash <> ''),
  pipeline_version text NOT NULL CHECK (pipeline_version <> ''),
  state            text NOT NULL DEFAULT 'queued'
                     CHECK (state IN ('queued', 'leased', 'done', 'dead', 'classified')),
  attempts         integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  lease_owner      text,
  lease_token      uuid,
  lease_expires_at timestamptz,
  last_error       text,
  residue_class    text CHECK (residue_class IS NULL OR residue_class IN
                               ('scan-needs-ocr', 'over-page-cap', 'zero-content', 'bad-file')),
  artifact_path    text,
  artifact_sha256  text CHECK (artifact_sha256 IS NULL OR artifact_sha256 ~ '^[0-9a-f]{64}$'),
  run_id           uuid REFERENCES extraction_runs (id),
  -- The ORDERING key, copied from file_versions.pages at enqueue. §12.3's order is "short files
  -- first, the book last", and a claim that had to join file_versions to find that out would make
  -- the hot path depend on a view; NULL is "no page count is known" and sorts LAST, so an unknown
  -- file never jumps the queue ahead of a measured short one.
  pages            integer CHECK (pages IS NULL OR pages >= 0),
  enqueued_at      timestamptz NOT NULL DEFAULT now(),
  finished_at      timestamptz,
  CONSTRAINT extraction_jobs_page_range CHECK
    ((page_start IS NULL) = (page_end IS NULL) AND (page_end IS NULL OR page_end >= page_start)),
  -- A residue class IS the classified state; neither can exist without the other, or "why this
  -- file is unreadable" would be a field some other state could also carry and no count of
  -- classified files would mean anything.
  CONSTRAINT extraction_jobs_residue_is_classified CHECK
    ((residue_class IS NOT NULL) = (state = 'classified')),
  -- A lease is whole or absent: leased iff there is a token, a token iff there is an expiry, and
  -- never a token with no owner. Half a lease is how a row becomes unclaimable — no live holder,
  -- and not queued either.
  CONSTRAINT extraction_jobs_lease_is_whole CHECK
    ((state = 'leased') = (lease_token IS NOT NULL)
     AND (lease_token IS NULL) = (lease_expires_at IS NULL)
     AND (lease_token IS NULL OR lease_owner IS NOT NULL))
);

-- §4.3: UNIQUE on the run key plus the page range. This is what makes a repeated sweep a no-op,
-- and it is a UNIQUE INDEX rather than a table constraint because the range is nullable and two
-- whole-file jobs must collide: under a plain UNIQUE, (…, NULL, NULL) never equals itself.
CREATE UNIQUE INDEX extraction_jobs_key ON extraction_jobs
  (file_id, stage, tool, tool_version, params_hash, pipeline_version,
   coalesce(page_start, 0), coalesce(page_end, 0));
-- the claim's own order: state first (the WHERE), then §12.3's shortest-first
CREATE INDEX extraction_jobs_claimable ON extraction_jobs (state, pages, enqueued_at);
CREATE INDEX extraction_jobs_file ON extraction_jobs (file_id);

-- ── the ownership gate ───────────────────────────────────────────────────────────────────
--
-- One body, called by all four mutating functions, so "who may change this row" is defined once.
-- It is not granted to any role: it is reached only from inside the SECURITY DEFINER functions
-- below, which run as this schema's owner.

CREATE FUNCTION litkb._job_lease_held(p_job uuid, p_token uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
BEGIN
  -- BEGIN guard: a job is mutated only by the holder of its live lease
  IF p_token IS NULL THEN
    RAISE EXCEPTION 'litkb: job % needs the lease token claim_jobs returned', p_job
      USING ERRCODE = '42501';
  END IF;
  PERFORM 1 FROM extraction_jobs j
   WHERE j.id = p_job AND j.state = 'leased' AND j.lease_token = p_token
     AND j.lease_expires_at > now();
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: job % is not leased to the presenter of this token (lost, expired or forged lease)', p_job
      USING ERRCODE = '42501';
  END IF;
  -- END guard: a job is mutated only by the holder of its live lease
  RETURN;
END
$$;

-- ── enqueue ──────────────────────────────────────────────────────────────────────────────

CREATE FUNCTION litkb.enqueue_extraction(
    p_file uuid, p_stage text, p_tool text, p_tool_version text, p_params_hash text,
    p_pipeline_version text, p_page_start integer, p_page_end integer, p_pages integer)
RETURNS TABLE (job_id uuid, job_state text, was_new boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_run uuid;
  v_id  uuid;
  v_new boolean := true;
BEGIN
  -- §12.4: a run key that already holds an `ok` run is done, and the tool is never run for it.
  SELECT r.id INTO v_run FROM extraction_runs r
   WHERE r.file_id = p_file AND r.stage = p_stage AND r.tool = p_tool
     AND r.tool_version = p_tool_version AND r.params_hash = p_params_hash
     AND r.pipeline_version = p_pipeline_version AND r.status = 'ok';

  INSERT INTO extraction_jobs (file_id, stage, page_start, page_end, tool, tool_version,
                               params_hash, pipeline_version, pages, state, run_id, finished_at)
  VALUES (p_file, p_stage, p_page_start, p_page_end, p_tool, p_tool_version,
          p_params_hash, p_pipeline_version, p_pages,
          CASE WHEN v_run IS NULL THEN 'queued' ELSE 'done' END, v_run,
          CASE WHEN v_run IS NULL THEN NULL ELSE now() END)
  ON CONFLICT (file_id, stage, tool, tool_version, params_hash, pipeline_version,
               coalesce(page_start, 0), coalesce(page_end, 0)) DO NOTHING
  RETURNING id INTO v_id;

  IF v_id IS NULL THEN
    v_new := false;
    SELECT j.id INTO v_id FROM extraction_jobs j
     WHERE j.file_id = p_file AND j.stage = p_stage AND j.tool = p_tool
       AND j.tool_version = p_tool_version AND j.params_hash = p_params_hash
       AND j.pipeline_version = p_pipeline_version
       AND coalesce(j.page_start, 0) = coalesce(p_page_start, 0)
       AND coalesce(j.page_end, 0) = coalesce(p_page_end, 0);
  END IF;
  RETURN QUERY SELECT v_id, j.state, v_new FROM extraction_jobs j WHERE j.id = v_id;
END
$$;

-- ── claim ────────────────────────────────────────────────────────────────────────────────
--
-- FOR UPDATE SKIP LOCKED over the claimable set: two workers can never lease one job, and a job
-- another worker is claiming right now is skipped rather than waited for. A `leased` row whose
-- lease has expired is claimable again — that is how a dead worker's jobs come back, and it is
-- why the lease length has to be longer than the longest job (the caller chooses it; the worker
-- renews at half the lease while a tool runs).
CREATE FUNCTION litkb.claim_jobs(p_worker text, p_n integer, p_lease_seconds integer)
RETURNS TABLE (job_id uuid, file_id uuid, stage text, tool text, tool_version text,
               params_hash text, pipeline_version text, page_start integer, page_end integer,
               pages integer, attempts integer, artifact_sha256 text,
               lease_token uuid, lease_expires_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
BEGIN
  IF p_worker IS NULL OR btrim(p_worker) = '' THEN
    RAISE EXCEPTION 'litkb: a claim names its worker' USING ERRCODE = '22023';
  END IF;
  IF coalesce(p_lease_seconds, 0) <= 0 THEN
    RAISE EXCEPTION 'litkb: a lease lasts a positive number of seconds, got %', p_lease_seconds
      USING ERRCODE = '22023';
  END IF;
  -- The ORDER BY is spelled TWICE on purpose. Inside, it decides WHICH jobs are taken (§12.3's
  -- shortest first). Outside, it decides the order they are HANDED BACK in: `UPDATE … RETURNING`
  -- has no defined row order, so a batch claim would otherwise return the same set of jobs in
  -- whatever order the heap gave them, and a worker that takes them in sequence would do the
  -- longest first inside a batch it asked to be ordered.
  RETURN QUERY
  WITH claimed AS (
    UPDATE extraction_jobs j
       SET state = 'leased', lease_owner = p_worker, lease_token = gen_random_uuid(),
           lease_expires_at = now() + make_interval(secs => p_lease_seconds),
           attempts = j.attempts + 1
     WHERE j.id IN (
       SELECT c.id FROM extraction_jobs c
        WHERE c.state = 'queued'
           OR (c.state = 'leased' AND c.lease_expires_at <= now())
        ORDER BY c.pages NULLS LAST, c.enqueued_at
        FOR UPDATE SKIP LOCKED
        LIMIT greatest(coalesce(p_n, 1), 0))
    RETURNING j.id, j.file_id, j.stage, j.tool, j.tool_version, j.params_hash, j.pipeline_version,
              j.page_start, j.page_end, j.pages, j.attempts, j.artifact_sha256,
              j.lease_token, j.lease_expires_at, j.enqueued_at)
  SELECT c.id, c.file_id, c.stage, c.tool, c.tool_version, c.params_hash, c.pipeline_version,
         c.page_start, c.page_end, c.pages, c.attempts, c.artifact_sha256,
         c.lease_token, c.lease_expires_at
    FROM claimed c ORDER BY c.pages NULLS LAST, c.enqueued_at;
END
$$;

-- ── the four mutating functions, each behind the gate ────────────────────────────────────

CREATE FUNCTION litkb.renew_lease(p_job uuid, p_token uuid, p_lease_seconds integer)
RETURNS timestamptz
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_until timestamptz;
BEGIN
  PERFORM litkb._job_lease_held(p_job, p_token);
  IF coalesce(p_lease_seconds, 0) <= 0 THEN
    RAISE EXCEPTION 'litkb: a lease lasts a positive number of seconds, got %', p_lease_seconds
      USING ERRCODE = '22023';
  END IF;
  UPDATE extraction_jobs j SET lease_expires_at = now() + make_interval(secs => p_lease_seconds)
   WHERE j.id = p_job RETURNING j.lease_expires_at INTO v_until;
  RETURN v_until;
END
$$;

-- The finish is called in the SAME transaction as the run row and its text rows (§12.4), so a
-- killed worker leaves either a finished unit or no rows at all.
CREATE FUNCTION litkb.finish_job(p_job uuid, p_token uuid, p_run uuid, p_artifact_sha256 text)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
BEGIN
  PERFORM litkb._job_lease_held(p_job, p_token);
  -- BEGIN guard: a finished job's run is a run of the job's own file
  IF p_run IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM extraction_runs r JOIN extraction_jobs j ON j.id = p_job
        WHERE r.id = p_run AND r.file_id = j.file_id) THEN
    RAISE EXCEPTION 'litkb: run % is not a run of job %''s file', p_run, p_job
      USING ERRCODE = '22023';
  END IF;
  -- END guard: a finished job's run is a run of the job's own file
  UPDATE extraction_jobs j
     SET state = 'done', run_id = coalesce(p_run, j.run_id),
         artifact_sha256 = coalesce(p_artifact_sha256, j.artifact_sha256),
         finished_at = now(), last_error = NULL,
         lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL
   WHERE j.id = p_job;
END
$$;

-- §12.3: the error is recorded and the job returns to the queue. Only after p_max_attempts is it
-- `dead` — and only then does the caller insert an `extraction_runs` row with status `failed`.
-- Returns the state the job is now in, so the caller does not have to re-read it to find out.
CREATE FUNCTION litkb.fail_job(p_job uuid, p_token uuid, p_error text, p_max_attempts integer)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_state text;
BEGIN
  PERFORM litkb._job_lease_held(p_job, p_token);
  UPDATE extraction_jobs j
     SET state = CASE WHEN j.attempts >= greatest(coalesce(p_max_attempts, 3), 1)
                      THEN 'dead' ELSE 'queued' END,
         last_error = left(coalesce(p_error, ''), 4000),
         finished_at = CASE WHEN j.attempts >= greatest(coalesce(p_max_attempts, 3), 1)
                            THEN now() ELSE NULL END,
         lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL
   WHERE j.id = p_job
  RETURNING j.state INTO v_state;
  RETURN v_state;
END
$$;

-- The terminal state for a file that is bound and readable by nobody: the tool was refused before
-- it started (over-page-cap, bad-file, scan-needs-ocr) or it ran and produced nothing
-- (zero-content). No retry — a class is a verdict about the FILE, not about this attempt, and a
-- job that came back queued would be the same verdict again at the cost of another conversion.
CREATE FUNCTION litkb.classify_job(p_job uuid, p_token uuid, p_residue text, p_error text)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
BEGIN
  PERFORM litkb._job_lease_held(p_job, p_token);
  IF p_residue IS NULL THEN
    RAISE EXCEPTION 'litkb: a classified job names its residue class' USING ERRCODE = '22023';
  END IF;
  UPDATE extraction_jobs j
     SET state = 'classified', residue_class = p_residue,
         last_error = left(coalesce(p_error, ''), 4000), finished_at = now(),
         lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL
   WHERE j.id = p_job;
END
$$;

-- ── grants ───────────────────────────────────────────────────────────────────────────────
--
-- The table gets NO direct INSERT, UPDATE or DELETE, for the reason 0017 gives for its own three:
-- the functions are the only writers, so the ownership gate is not optional. SELECT is open to
-- the three agent roles because `queue status`, the readability instrument and any reader asking
-- "why is this file unreadable" all answer from these rows.
GRANT SELECT ON extraction_jobs TO litkb_reader, litkb_writer, litkb_ingest;
GRANT EXECUTE ON FUNCTION litkb.enqueue_extraction(uuid, text, text, text, text, text, integer, integer, integer) TO litkb_ingest;
GRANT EXECUTE ON FUNCTION litkb.claim_jobs(text, integer, integer) TO litkb_ingest;
GRANT EXECUTE ON FUNCTION litkb.renew_lease(uuid, uuid, integer) TO litkb_ingest;
GRANT EXECUTE ON FUNCTION litkb.finish_job(uuid, uuid, uuid, text) TO litkb_ingest;
GRANT EXECUTE ON FUNCTION litkb.fail_job(uuid, uuid, text, integer) TO litkb_ingest;
GRANT EXECUTE ON FUNCTION litkb.classify_job(uuid, uuid, text, text) TO litkb_ingest;
