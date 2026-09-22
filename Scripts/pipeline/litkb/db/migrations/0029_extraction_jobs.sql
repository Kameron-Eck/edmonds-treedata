-- litkb 0029 — extraction_jobs: the lease + resume queue (design §4.3's `extraction_jobs` row,
-- §12.3-12.5; LITKB_WORKPLAN.md "### S4"; S4 run 3 decisions D1, D2, D3, D7).
--
-- WHAT IS NEW, AND WHY
--
--  * extraction_jobs — one row per (file, run key, page range). The design's columns, plus what
--    the ownership gate and the S4 counters need that the design did not name:
--      - `refused` + `refusal`: the enqueue/claim guards' verdict. A refused job is terminal and
--        never claimable. Closed vocabulary: over-page-cap · book · probe-error · bad-file ·
--        scan-needs-ocr (brief-A; the file-level residue classes of S4 run 3 decision D8 that a
--        queue guard can decide).
--      - `staged`: a page-range job whose artifact is checkpointed and which waits for the LAST
--        range of its file to assemble them into ONE run (design §12.5). Not a class: a staged
--        job is waiting, exactly as a queued one is.
--      - `lease_seq` + `lease_token_hash`: the lease TOKEN is generated here, returned in
--        plaintext ONCE by claim_jobs, and only its sha256 is stored — the workstream-token
--        pattern of migration 0010. The sequence number counts claims.
--      - `route`, `pages`, `page_chars`: the per-page probe facts the job was enqueued on
--        (litkb.extract.probe), so a cold reader can recompute the scan post-condition.
--      - `blocks_digest`: the content hash of the committed blocks (docs/SCHEMAS.md defines it
--        byte for byte; litkb.extract.queue.blocks_digest is its one implementation).
--      - `metrics`: the job's own measurements (a range job's are not the run's).
--  * extraction_job_leases — append-only history of every claim: which worker, which token hash,
--    when claimed, until when, when superseded by a later claim, when released and how. A cold
--    reader can tell which claim finished a job — the substrate of `mutated_leases_accepted`.
--
-- THE OWNERSHIP GATE is finish_job (brief-A item 1): it RAISES SQLSTATE LKL01 unless the presented
-- token's hash is the job's CURRENT lease and no later claim superseded it. The worker calls it
-- INSIDE the ingest transaction (design §12.4), so a refused finish rolls the blocks back: an
-- expired worker that wakes after reassignment lands nothing. Every other lease-holder call
-- (renew_lease, record_artifact, stage_chunk, fail_job, refuse_job) presents the token through the
-- same helper, each behind its own guard block so each call site can be mutated alone.
--
-- WHO MAY WRITE. No role holds INSERT/UPDATE/DELETE on either table: the SECURITY DEFINER functions
-- below are the only writers, EXECUTE to litkb_ingest only, with no workstream token — files are
-- main-owned identity rows, exactly like set_current_run (design §4.3 row: "No workstream_id").
--
-- STAGE. `5-reconcile` only (S4 run 3 decision D7: stage 6 runs through its own file-keyed driver
-- and is not queued in S4). Widening the CHECK is a later migration.

SET LOCAL search_path = litkb, public;

-- ── the attempt ceiling ───────────────────────────────────────────────────────────────────
-- ONE home: fail_job and claim_jobs read it here, and nothing in Python restates it
-- (litkb.extract.queue reads it back through this function when it needs it).
-- SOURCE: Kam's ruling litkb-extract-page-cap (decisions.yaml; S4 run 3 decision D2): a job is
-- `dead` after 3 failed attempts. Design §12.3 left N "set in P4" and nothing had set it.
CREATE FUNCTION litkb._job_max_attempts() RETURNS integer
LANGUAGE sql IMMUTABLE AS $$ SELECT 3 $$;

-- ── the queue ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE extraction_jobs (
  id               uuid PRIMARY KEY DEFAULT uuidv7(),
  file_id          uuid NOT NULL REFERENCES files (id),
  stage            text NOT NULL CHECK (stage = '5-reconcile'),
  page_start       integer,
  page_end         integer,
  tool             text NOT NULL CHECK (tool <> ''),
  tool_version     text NOT NULL CHECK (tool_version <> ''),
  params_hash      text NOT NULL CHECK (params_hash <> ''),
  pipeline_version text NOT NULL CHECK (pipeline_version <> ''),
  route            text CHECK (route IS NULL OR route IN ('native', 'ocr')),
  pages            integer CHECK (pages IS NULL OR pages >= 1),
  page_chars       integer[],
  state            text NOT NULL DEFAULT 'queued'
                   CHECK (state IN ('queued', 'leased', 'staged', 'done', 'dead', 'refused')),
  refusal          text CHECK (refusal IS NULL OR refusal IN
                   ('over-page-cap', 'book', 'probe-error', 'bad-file', 'scan-needs-ocr')),
  attempts         integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  lease_seq        integer NOT NULL DEFAULT 0 CHECK (lease_seq >= 0),
  lease_owner      text,
  lease_expires_at timestamptz,
  lease_token_hash text CHECK (lease_token_hash IS NULL OR lease_token_hash ~ '^[0-9a-f]{64}$'),
  last_error       text,
  artifact_path    text,
  artifact_sha256  text CHECK (artifact_sha256 IS NULL OR artifact_sha256 ~ '^[0-9a-f]{64}$'),
  run_id           uuid,
  blocks_digest    text CHECK (blocks_digest IS NULL OR blocks_digest ~ '^[0-9a-f]{64}$'),
  metrics          jsonb NOT NULL DEFAULT '{}'::jsonb,
  enqueued_at      timestamptz NOT NULL DEFAULT now(),
  finished_at      timestamptz,
  FOREIGN KEY (file_id, run_id) REFERENCES extraction_runs (file_id, id),
  CONSTRAINT extraction_jobs_range CHECK (
    (page_start IS NULL AND page_end IS NULL) OR (page_start >= 1 AND page_end >= page_start)),
  CONSTRAINT extraction_jobs_refusal CHECK ((state = 'refused') = (refusal IS NOT NULL)),
  CONSTRAINT extraction_jobs_lease CHECK (
    (state = 'leased') = (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL
                          AND lease_token_hash IS NOT NULL)),
  CONSTRAINT extraction_jobs_done CHECK (
    (state = 'done') = (run_id IS NOT NULL) AND (state <> 'done' OR blocks_digest IS NOT NULL)),
  CONSTRAINT extraction_jobs_staged CHECK (
    state <> 'staged' OR (page_start IS NOT NULL AND artifact_sha256 IS NOT NULL)),
  CONSTRAINT extraction_jobs_key UNIQUE NULLS NOT DISTINCT
    (file_id, stage, tool, tool_version, params_hash, pipeline_version, page_start, page_end)
);
CREATE INDEX extraction_jobs_claimable ON extraction_jobs (state, pages, enqueued_at);

CREATE TABLE extraction_job_leases (
  job_id        uuid NOT NULL REFERENCES extraction_jobs (id),
  seq           integer NOT NULL CHECK (seq >= 1),
  owner         text NOT NULL CHECK (owner <> ''),
  token_hash    text NOT NULL CHECK (token_hash ~ '^[0-9a-f]{64}$'),
  lease_seconds integer NOT NULL CHECK (lease_seconds >= 1),
  claimed_at    timestamptz NOT NULL,
  expires_at    timestamptz NOT NULL,
  superseded_at timestamptz,
  released_at   timestamptz,
  outcome       text CHECK (outcome IS NULL OR outcome IN
                ('finished', 'staged', 'failed', 'dead', 'refused')),
  PRIMARY KEY (job_id, seq),
  CONSTRAINT extraction_job_leases_release CHECK ((released_at IS NULL) = (outcome IS NULL))
);

-- APPEND-ONLY. A row is never deleted; its identity (job, seq, owner, token hash, lease length,
-- claimed_at) never changes; superseded_at, released_at and outcome are each written ONCE; and
-- expires_at moves (renew_lease) only while the lease is neither released nor superseded. The
-- history is the only record of which claim finished a job, so it may not be rewritten after the
-- fact — not even by the definer functions that write it.
CREATE FUNCTION litkb._job_lease_history_append_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = litkb, public, pg_temp AS $$
BEGIN
  -- BEGIN guard: the lease history is append-only
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'litkb: extraction_job_leases is append-only' USING ERRCODE = '42501';
  END IF;
  IF NEW.job_id IS DISTINCT FROM OLD.job_id OR NEW.seq IS DISTINCT FROM OLD.seq
     OR NEW.owner IS DISTINCT FROM OLD.owner OR NEW.token_hash IS DISTINCT FROM OLD.token_hash
     OR NEW.lease_seconds IS DISTINCT FROM OLD.lease_seconds
     OR NEW.claimed_at IS DISTINCT FROM OLD.claimed_at
     OR (OLD.superseded_at IS NOT NULL AND NEW.superseded_at IS DISTINCT FROM OLD.superseded_at)
     OR (OLD.released_at IS NOT NULL AND (NEW.released_at IS DISTINCT FROM OLD.released_at
                                          OR NEW.outcome IS DISTINCT FROM OLD.outcome))
     OR (NEW.expires_at IS DISTINCT FROM OLD.expires_at
         AND (OLD.released_at IS NOT NULL OR OLD.superseded_at IS NOT NULL)) THEN
    RAISE EXCEPTION 'litkb: lease history row (job %, seq %) cannot be rewritten', OLD.job_id, OLD.seq
      USING ERRCODE = '42501';
  END IF;
  -- END guard: the lease history is append-only
  RETURN NEW;
END
$$;
CREATE TRIGGER extraction_job_leases_append_only BEFORE UPDATE OR DELETE ON extraction_job_leases
  FOR EACH ROW EXECUTE FUNCTION litkb._job_lease_history_append_only();

-- ── helpers (not granted: only the definer functions below call them) ─────────────────────

CREATE FUNCTION litkb._lease_hash(p_token text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$ SELECT encode(sha256(convert_to(coalesce(p_token, ''), 'UTF8')), 'hex') $$;

-- Is this file's work a book in main? The `litkb-book-policy` rule (S4 never extracts a book),
-- read from the database at enqueue AND at claim, so a job enqueued before a work was retyped is
-- still refused. A file main has no version of yet reads false here; the Python guard
-- (litkb.extract.queue.guard_file) reads the workstream's view for those.
CREATE FUNCTION litkb._job_file_is_book(p_file uuid) RETURNS boolean
LANGUAGE sql STABLE SET search_path = litkb, public, pg_temp AS $$
  SELECT EXISTS (
    SELECT 1 FROM files f
      JOIN file_versions fv ON fv.version_id = f.current_version_id
      JOIN works w ON w.id = fv.work_id
      JOIN work_versions wv ON wv.version_id = w.current_version_id
     WHERE f.id = p_file AND wv.type = 'book')
$$;

-- The lease check every holder call presents. Locks the job row, so a claim and a holder call
-- serialise on it. Raises LKL01 — "litkb lease refused", documented in docs/SCHEMAS.md — unless
-- the job is leased, the token hashes to its CURRENT lease, and no later claim superseded that
-- lease. An expired lease nobody has reclaimed is still current: the work done under it is still
-- the only work done on that job.
CREATE FUNCTION litkb._job_lease_current(p_job uuid, p_token text) RETURNS void
LANGUAGE plpgsql SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_state text; v_seq integer; v_hash text;
BEGIN
  SELECT j.state, j.lease_seq, j.lease_token_hash INTO v_state, v_seq, v_hash
    FROM extraction_jobs j WHERE j.id = p_job FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: no extraction job %', p_job USING ERRCODE = '22023';
  END IF;
  IF v_state IS DISTINCT FROM 'leased' OR v_hash IS DISTINCT FROM _lease_hash(p_token)
     OR EXISTS (SELECT 1 FROM extraction_job_leases l
                 WHERE l.job_id = p_job AND (l.seq > v_seq OR (l.seq = v_seq AND l.superseded_at IS NOT NULL))) THEN
    -- the message names the job, never the token
    RAISE EXCEPTION 'litkb: lease refused for extraction job %: the presented token is not its current lease', p_job
      USING ERRCODE = 'LKL01';
  END IF;
END
$$;

-- The chunk siblings of a page-range job: the same file, stage and run key, page_start not null.
CREATE FUNCTION litkb._job_siblings(p_job uuid) RETURNS SETOF uuid
LANGUAGE sql STABLE SET search_path = litkb, public, pg_temp AS $$
  SELECT s.id FROM extraction_jobs j JOIN extraction_jobs s
      ON s.file_id = j.file_id AND s.stage = j.stage AND s.tool = j.tool
     AND s.tool_version = j.tool_version AND s.params_hash = j.params_hash
     AND s.pipeline_version = j.pipeline_version AND s.page_start IS NOT NULL
   WHERE j.id = p_job AND j.page_start IS NOT NULL AND s.id <> j.id
$$;

-- ── the writers ───────────────────────────────────────────────────────────────────────────

-- Idempotent by the run key plus page range (the UNIQUE above): a second sweep inserts nothing and
-- returns the job already there with inserted=false. A refusal arrives decided by the Python guard
-- (probe, sha256, magic, page cap, OCR switch — facts the database cannot read off disk); the book
-- rule is ALSO decided here, because the work's type is a database fact.
CREATE FUNCTION litkb.enqueue_extraction(
    p_file uuid, p_stage text, p_tool text, p_tool_version text, p_params_hash text,
    p_pipeline_version text, p_page_start integer, p_page_end integer, p_route text,
    p_pages integer, p_page_chars integer[], p_refusal text, p_error text)
RETURNS TABLE (job_id uuid, inserted boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
#variable_conflict use_column
DECLARE
  v_refusal text := p_refusal;
  v_error text := p_error;
  v_id uuid;
BEGIN
  -- BEGIN guard: enqueue_extraction refuses a book's file
  IF _job_file_is_book(p_file) THEN
    v_refusal := 'book';
    v_error := coalesce(v_error, 'the work is a book (litkb-book-policy: S4 never extracts a book)');
  END IF;
  -- END guard: enqueue_extraction refuses a book's file
  INSERT INTO extraction_jobs (file_id, stage, page_start, page_end, tool, tool_version, params_hash,
                               pipeline_version, route, pages, page_chars, state, refusal, last_error,
                               finished_at)
  VALUES (p_file, p_stage, p_page_start, p_page_end, p_tool, p_tool_version, p_params_hash,
          p_pipeline_version, p_route, p_pages, p_page_chars,
          CASE WHEN v_refusal IS NULL THEN 'queued' ELSE 'refused' END, v_refusal,
          CASE WHEN v_refusal IS NULL THEN NULL ELSE left(v_error, 2000) END,
          CASE WHEN v_refusal IS NULL THEN NULL ELSE now() END)
  ON CONFLICT ON CONSTRAINT extraction_jobs_key DO NOTHING
  RETURNING id INTO v_id;
  IF v_id IS NOT NULL THEN
    RETURN QUERY SELECT v_id, true;
    RETURN;
  END IF;
  RETURN QUERY SELECT j.id, false FROM extraction_jobs j
    WHERE j.file_id = p_file AND j.stage = p_stage AND j.tool = p_tool
      AND j.tool_version = p_tool_version AND j.params_hash = p_params_hash
      AND j.pipeline_version = p_pipeline_version
      AND j.page_start IS NOT DISTINCT FROM p_page_start AND j.page_end IS NOT DISTINCT FROM p_page_end;
END
$$;

-- Take up to p_n jobs: queued ones, or leased ones whose lease has EXPIRED (design §12.3; P5 kill
-- (d): reclaim only after expiry). One row at a time under FOR UPDATE SKIP LOCKED, so two workers
-- never lease the same job (P5 kill (c)). Short files first (design §12.3 "Order", a design choice).
-- Returns each claimed job's token in plaintext; only its sha256 is kept. `p_files` (NULL = every
-- file) restricts the claim to those files: `litkb queue work --file`, and the tests, which share
-- one worker database and must not claim each other's jobs.
CREATE FUNCTION litkb.claim_jobs(p_worker text, p_n integer, p_lease_seconds integer,
                                 p_files uuid[] DEFAULT NULL)
RETURNS TABLE (job_id uuid, token text, lease_seq integer, file_id uuid, page_start integer,
               page_end integer, attempts integer, route text, pages integer, page_chars integer[],
               lease_expires_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
#variable_conflict use_column
DECLARE
  r extraction_jobs%ROWTYPE;
  v_now timestamptz;
  v_token text;
  v_n integer := 0;
BEGIN
  IF p_worker IS NULL OR btrim(p_worker) = '' THEN
    RAISE EXCEPTION 'litkb: claim_jobs needs a worker id' USING ERRCODE = '22023';
  END IF;
  IF p_n IS NULL OR p_n < 1 OR p_lease_seconds IS NULL OR p_lease_seconds < 1 THEN
    RAISE EXCEPTION 'litkb: claim_jobs needs n >= 1 and a lease of at least one second' USING ERRCODE = '22023';
  END IF;
  WHILE v_n < p_n LOOP
    v_now := clock_timestamp();
    SELECT j.* INTO r FROM extraction_jobs j
     WHERE (j.state = 'queued' OR (j.state = 'leased' AND j.lease_expires_at <= v_now))
       AND (p_files IS NULL OR j.file_id = ANY (p_files))
     ORDER BY j.pages NULLS LAST, j.enqueued_at, j.page_start NULLS FIRST, j.id
     LIMIT 1 FOR UPDATE SKIP LOCKED;
    EXIT WHEN NOT FOUND;
    IF r.state = 'leased' THEN
      -- the expired claim is superseded; its row stays, unreleased, as the record of a worker that
      -- never came back
      UPDATE extraction_job_leases l SET superseded_at = v_now
       WHERE l.job_id = r.id AND l.seq = r.lease_seq AND l.superseded_at IS NULL;
    END IF;
    -- BEGIN guard: claim_jobs never hands out a book's job
    IF _job_file_is_book(r.file_id) THEN
      UPDATE extraction_jobs j SET state = 'refused', refusal = 'book', lease_owner = NULL,
             lease_expires_at = NULL, lease_token_hash = NULL, finished_at = v_now,
             last_error = 'the work is a book (litkb-book-policy), found at claim'
       WHERE j.id = r.id OR (j.id IN (SELECT _job_siblings(r.id))
                             AND j.state IN ('queued', 'staged', 'leased'));
      CONTINUE;
    END IF;
    -- END guard: claim_jobs never hands out a book's job
    -- BEGIN guard: a job whose every lease expired dies at the attempt ceiling
    IF r.attempts >= _job_max_attempts() THEN
      -- claimed the maximum number of times and never released: every worker died on it
      UPDATE extraction_jobs j SET state = 'dead', lease_owner = NULL, lease_expires_at = NULL,
             lease_token_hash = NULL, finished_at = v_now,
             last_error = left(coalesce(j.last_error || ' | ', '') || 'lease expired on attempt '
                               || j.attempts || ' of ' || _job_max_attempts(), 2000)
       WHERE j.id = r.id;
      CONTINUE;
    END IF;
    -- END guard: a job whose every lease expired dies at the attempt ceiling
    v_token := replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '');
    UPDATE extraction_jobs j SET state = 'leased', attempts = j.attempts + 1, lease_seq = j.lease_seq + 1,
           lease_owner = p_worker, lease_expires_at = v_now + make_interval(secs => p_lease_seconds),
           lease_token_hash = _lease_hash(v_token)
     WHERE j.id = r.id
     RETURNING j.* INTO r;
    INSERT INTO extraction_job_leases (job_id, seq, owner, token_hash, lease_seconds, claimed_at, expires_at)
    VALUES (r.id, r.lease_seq, p_worker, r.lease_token_hash, p_lease_seconds, v_now, r.lease_expires_at);
    v_n := v_n + 1;
    RETURN QUERY SELECT r.id, v_token, r.lease_seq, r.file_id, r.page_start, r.page_end, r.attempts,
                        r.route, r.pages, r.page_chars, r.lease_expires_at;
  END LOOP;
END
$$;

-- The heartbeat. Extends the CURRENT lease by its own length from now.
CREATE FUNCTION litkb.renew_lease(p_job uuid, p_token text) RETURNS timestamptz
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_until timestamptz;
BEGIN
  -- BEGIN guard: renew_lease presents the job's current lease
  PERFORM _job_lease_current(p_job, p_token);
  -- END guard: renew_lease presents the job's current lease
  UPDATE extraction_job_leases l
     SET expires_at = clock_timestamp() + make_interval(secs => l.lease_seconds)
    FROM extraction_jobs j
   WHERE j.id = p_job AND l.job_id = j.id AND l.seq = j.lease_seq
  RETURNING l.expires_at INTO v_until;
  UPDATE extraction_jobs SET lease_expires_at = v_until WHERE id = p_job;
  RETURN v_until;
END
$$;

-- The checkpoint: the job's artifact (a manifest of the tool outputs) and its sha256, so a
-- reclaimed job whose artifact is already on disk under that hash is not extracted again (§12.4).
CREATE FUNCTION litkb.record_artifact(p_job uuid, p_token text, p_path text, p_sha256 text, p_metrics jsonb)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
BEGIN
  -- BEGIN guard: record_artifact presents the job's current lease
  PERFORM _job_lease_current(p_job, p_token);
  -- END guard: record_artifact presents the job's current lease
  UPDATE extraction_jobs SET artifact_path = p_path, artifact_sha256 = p_sha256,
         metrics = metrics || coalesce(p_metrics, '{}'::jsonb)
   WHERE id = p_job;
END
$$;

-- A page-range job whose artifact is recorded. -> true when every OTHER range of its file is
-- already staged: this job is the last one, stays leased, and its holder assembles the file (the
-- one transaction of design §12.5, closed by finish_job). -> false otherwise: the job is staged,
-- its lease released, and it waits. The siblings are locked first, in page order, so two ranges
-- finishing at once serialise here and exactly one of them sees the other staged.
CREATE FUNCTION litkb.stage_chunk(p_job uuid, p_token text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_job extraction_jobs%ROWTYPE;
  v_waiting integer;
BEGIN
  -- BEGIN guard: stage_chunk presents the job's current lease
  PERFORM _job_lease_current(p_job, p_token);
  -- END guard: stage_chunk presents the job's current lease
  SELECT * INTO v_job FROM extraction_jobs WHERE id = p_job;
  IF v_job.page_start IS NULL OR v_job.artifact_sha256 IS NULL THEN
    RAISE EXCEPTION 'litkb: job % is not a page-range job with a recorded artifact', p_job USING ERRCODE = '22023';
  END IF;
  PERFORM 1 FROM extraction_jobs s WHERE s.id IN (SELECT _job_siblings(p_job)) ORDER BY s.page_start FOR UPDATE;
  SELECT count(*) INTO v_waiting FROM extraction_jobs s
   WHERE s.id IN (SELECT _job_siblings(p_job)) AND s.state <> 'staged';
  IF v_waiting = 0 THEN
    RETURN true;
  END IF;
  UPDATE extraction_jobs SET state = 'staged', lease_owner = NULL, lease_expires_at = NULL,
         lease_token_hash = NULL
   WHERE id = p_job;
  UPDATE extraction_job_leases SET released_at = clock_timestamp(), outcome = 'staged'
   WHERE job_id = p_job AND seq = v_job.lease_seq;
  RETURN false;
END
$$;

-- THE OWNERSHIP GATE (brief-A item 1). Called inside the ingest transaction, after the run is ok and
-- the pointer has moved: a refusal here rolls every block of that transaction back. A page-range
-- job finishes its STAGED siblings with it — they are the ranges its run assembled.
CREATE FUNCTION litkb.finish_job(p_job uuid, p_token text, p_run uuid, p_digest text, p_metrics jsonb)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_job extraction_jobs%ROWTYPE;
  v_now timestamptz := clock_timestamp();
BEGIN
  -- BEGIN guard: finish_job accepts only the job's current, unsuperseded lease
  PERFORM _job_lease_current(p_job, p_token);
  -- END guard: finish_job accepts only the job's current, unsuperseded lease
  SELECT * INTO v_job FROM extraction_jobs WHERE id = p_job FOR UPDATE;
  -- BEGIN guard: finish_job points a job only at an ok run of its own file and run key
  PERFORM 1 FROM extraction_runs r
   WHERE r.id = p_run AND r.file_id = v_job.file_id AND r.status = 'ok' AND r.stage = v_job.stage
     AND r.tool = v_job.tool AND r.tool_version = v_job.tool_version
     AND r.params_hash = v_job.params_hash AND r.pipeline_version = v_job.pipeline_version;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: run % is not an ok run of job %''s file at its run key', coalesce(p_run::text, '(none)'), p_job
      USING ERRCODE = '22023';
  END IF;
  -- END guard: finish_job points a job only at an ok run of its own file and run key
  UPDATE extraction_jobs SET state = 'done', run_id = p_run, blocks_digest = p_digest,
         metrics = metrics || coalesce(p_metrics, '{}'::jsonb), finished_at = v_now,
         lease_owner = NULL, lease_expires_at = NULL, lease_token_hash = NULL
   WHERE id = p_job;
  UPDATE extraction_job_leases SET released_at = v_now, outcome = 'finished'
   WHERE job_id = p_job AND token_hash = _lease_hash(p_token) AND released_at IS NULL;
  UPDATE extraction_jobs SET state = 'done', run_id = p_run, blocks_digest = p_digest, finished_at = v_now
   WHERE id IN (SELECT _job_siblings(p_job)) AND state = 'staged';
END
$$;

-- A failed attempt: back to `queued`, or `dead` once attempts reach _job_max_attempts()
-- (Kam ruling litkb-extract-page-cap). -> the new state.
CREATE FUNCTION litkb.fail_job(p_job uuid, p_token text, p_error text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_job extraction_jobs%ROWTYPE;
  v_state text;
BEGIN
  -- BEGIN guard: fail_job presents the job's current lease
  PERFORM _job_lease_current(p_job, p_token);
  -- END guard: fail_job presents the job's current lease
  SELECT * INTO v_job FROM extraction_jobs WHERE id = p_job;
  v_state := CASE WHEN v_job.attempts >= _job_max_attempts() THEN 'dead' ELSE 'queued' END;
  UPDATE extraction_jobs SET state = v_state, last_error = left(p_error, 2000),
         lease_owner = NULL, lease_expires_at = NULL, lease_token_hash = NULL,
         finished_at = CASE WHEN v_state = 'dead' THEN clock_timestamp() END
   WHERE id = p_job;
  UPDATE extraction_job_leases SET released_at = clock_timestamp(),
         outcome = CASE WHEN v_state = 'dead' THEN 'dead' ELSE 'failed' END
   WHERE job_id = p_job AND seq = v_job.lease_seq;
  RETURN v_state;
END
$$;

-- A guard that fired AFTER the claim: the claim-time re-check (a job enqueued before a guard
-- changed) or the scan post-condition. Terminal. A file-level refusal refuses every unfinished
-- range of the file with it.
CREATE FUNCTION litkb.refuse_job(p_job uuid, p_token text, p_refusal text, p_error text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_job extraction_jobs%ROWTYPE;
  v_now timestamptz := clock_timestamp();
BEGIN
  -- BEGIN guard: refuse_job presents the job's current lease
  PERFORM _job_lease_current(p_job, p_token);
  -- END guard: refuse_job presents the job's current lease
  SELECT * INTO v_job FROM extraction_jobs WHERE id = p_job;
  UPDATE extraction_jobs SET state = 'refused', refusal = p_refusal, last_error = left(p_error, 2000),
         lease_owner = NULL, lease_expires_at = NULL, lease_token_hash = NULL, finished_at = v_now
   WHERE id = p_job;
  UPDATE extraction_job_leases SET released_at = v_now, outcome = 'refused'
   WHERE job_id = p_job AND seq = v_job.lease_seq;
  UPDATE extraction_job_leases l SET superseded_at = v_now
    FROM extraction_jobs s
   WHERE s.id IN (SELECT _job_siblings(p_job)) AND s.state = 'leased'
     AND l.job_id = s.id AND l.seq = s.lease_seq AND l.superseded_at IS NULL;
  UPDATE extraction_jobs SET state = 'refused', refusal = p_refusal,
         last_error = left('refused with its file''s range ' || v_job.page_start || '-' || v_job.page_end
                           || ': ' || coalesce(p_error, ''), 2000),
         lease_owner = NULL, lease_expires_at = NULL, lease_token_hash = NULL, finished_at = v_now
   WHERE id IN (SELECT _job_siblings(p_job)) AND state IN ('queued', 'leased', 'staged');
END
$$;

-- ── grants ───────────────────────────────────────────────────────────────────────────────
-- No direct write for anyone: the functions are the only writers (the role matrix in
-- qc/test_litkb_p1.py pins it). SELECT for the readers the S4 counters and `litkb queue status`
-- use. The token hashes are readable: each is the sha256 of 244 random bits and a lease is
-- ephemeral, so the hash lets nobody present the token — the counters need the history, not the
-- tokens.
REVOKE ALL ON extraction_jobs, extraction_job_leases FROM PUBLIC;
GRANT SELECT ON extraction_jobs, extraction_job_leases TO litkb_reader, litkb_writer, litkb_ingest;

REVOKE EXECUTE ON FUNCTION litkb._job_max_attempts(), litkb._lease_hash(text),
  litkb._job_file_is_book(uuid), litkb._job_lease_current(uuid, text), litkb._job_siblings(uuid),
  litkb._job_lease_history_append_only() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION
  litkb.enqueue_extraction(uuid, text, text, text, text, text, integer, integer, text, integer, integer[], text, text),
  litkb.claim_jobs(text, integer, integer, uuid[]),
  litkb.renew_lease(uuid, text),
  litkb.record_artifact(uuid, text, text, text, jsonb),
  litkb.stage_chunk(uuid, text),
  litkb.finish_job(uuid, text, uuid, text, jsonb),
  litkb.fail_job(uuid, text, text),
  litkb.refuse_job(uuid, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
  litkb.enqueue_extraction(uuid, text, text, text, text, text, integer, integer, text, integer, integer[], text, text),
  litkb.claim_jobs(text, integer, integer, uuid[]),
  litkb.renew_lease(uuid, text),
  litkb.record_artifact(uuid, text, text, text, jsonb),
  litkb.stage_chunk(uuid, text),
  litkb.finish_job(uuid, text, uuid, text, jsonb),
  litkb.fail_job(uuid, text, text),
  litkb.refuse_job(uuid, text, text, text) TO litkb_ingest;
