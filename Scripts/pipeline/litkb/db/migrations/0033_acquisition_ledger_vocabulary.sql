-- litkb 0033 — the acquisition ledger's vocabulary and the per-route back-off state
-- (LITKB_WORKPLAN.md "### S4.5", items 1 and 2; builder C1a; S4.5 decisions D1-D4).
--
-- WHY. The acquisition ledger had four words for a miss and no way to say WHY. A hunt that landed
-- nothing ended `held/not-acquired` while the attempt row held `bad-file` or `blocked` and the
-- reason lived only in free-text `detail`; a route that was skipped (a dead route, a DOI-only route
-- with no DOI) wrote no row at all, so the census measured a broken instrument (PDF-sources survey
-- §1 guard 14); `blocked` was retried on every hunt because nothing kept the refusal between runs
-- (§1 guard 2); the sha256 of the bytes a route served lived only inside `detail`, and only on the
-- rows that happened to quarantine them, so a byte-identical challenge page could be quarantined
-- again and again (E13's 58-byte DNS-error string sits in `_quarantine/` three times under one
-- sha, a8df0738…, recorded 2026-09-16 x2 and 2026-09-21).
--
-- WHAT. On `acquisition_attempts`, one column per fact the ladder now records (every column and
-- value a docs/SCHEMAS.md row, "litkb.acquisition_attempts (0033 ledger vocabulary)"):
--   sub_status + sub_status_basis   WHY the status: the S4.5 CONTRACTS vocabulary, held CONSISTENT
--                                   with `status` by a CHECK (a `bad-file` sub-status on a `bad-file`
--                                   row only, ...); NULL where the status carries none, and on the
--                                   historical rows until the reviewed backfill types them
--   terminal_url / _status_code / _dt   the response that decided the attempt (survey §3.4, the
--                                   "single cheapest schema change")
--   retriable                       per attempt, never per status word (guard 15)
--   kind                            pdf | jats | text | html-doc | cached_text | snippet (§3.4)
--   served_sha256                   the sha of the bytes the route SERVED, on every attempt that
--                                   received bytes, landed or not (item 1)
--   retry_of                        a scheduled in-run transient retry names the attempt it retries,
--                                   so it is distinguishable from a re-spend (the rehunt counter)
-- The status CHECK gains four words, none of them a hunt STATE (the hunt's closed STATES/REASONS
-- and the acceptance instrument's CLOSED_STATES pin are untouched): `skipped` (a skip is an attempt
-- with a reason, guard 14), `budget-stop` (the ladder budget ran out, guard 12), `measured` (a rung
-- answered a hit in MEASURE mode and nothing was landed, S4.5 decision D9), `known-bad` (a route
-- served bytes whose sha matches refused bytes, and nothing was written: the rejected-hash lookup).
-- The route CHECK is widened to the S4.5 CONTRACTS route list (one Python home:
-- litkb.acquire.policy.ROUTES_ALL). `unverified_keep` (guard 17) lives as a sub-status of an `ok` or
-- `measured` row: the file was landed (or would have been) although a check that needs metadata
-- could not run — a third outcome the counters report, never a silent pass.
--
-- `file_versions.word_count` is the column; `copy_kind` is NOT given a new column or a new value:
-- its existing `publisher` / `author manuscript` / `preprint` ARE the article versions
-- published / accepted / submitted (guard 23), and what S4.5 adds is that every landing WRITES it
-- where the route knows the version (litkb.acquire.policy.COPY_KIND_OF_VERSION). The COMMENT below
-- says so, so the column's meaning is extended where it is defined.
--
-- `route_backoff` is the per-(route, work) refusal ladder, PERSISTED (guard 2) so a second hunt
-- inside the window does not re-spend; keyed on the attempt facts (route, status, http codes, at),
-- never on the hunt's state word; one row per (route, work), NEVER per host (guard 29: MDPI answers
-- 403 per article, and a host-wide suppression would retire the corpus's largest publisher after
-- one article). Its one writer is record_route_backoff (writer role, token, citing an attempt of
-- the caller's own workstream).
--
-- `acquisition_backfills` is the reviewed backfill's decision log: one row per applied run of
-- backfill_attempt_sub_status / backfill_file_word_count (ingest role), so a historical typing is
-- always traceable to the CSV it came from.
--
-- ONE SIGNATURE. record_acquisition_attempt is DROPPED and re-created with the new parameters
-- DEFAULTed, so the nine-argument calls every existing caller makes still resolve and exactly one
-- signature exists (qc/test_litkb_p1.py::test_token_functions_have_exactly_one_signature — a CREATE
-- with added parameters would have made an overload that still took writes on the old grant).
--
-- SCOPE. 0032 and 0034 are reserved by other open S4.5 branches (_reserved.txt); nothing here
-- touches a function either of them owns (litkb.admit, _check_registry, norm_identifier,
-- attach_file, approve_admission): the only function body replaced is
-- record_acquisition_attempt, whose one owner is this migration (S4.5 decision D4).

SET LOCAL search_path = litkb, public;

-- ── routes and statuses ─────────────────────────────────────────────────────────────────────
ALTER TABLE acquisition_attempts DROP CONSTRAINT acquisition_attempts_route_check;
ALTER TABLE acquisition_attempts ADD CONSTRAINT acquisition_attempts_route_check CHECK (route IN (
  -- 0001 + 0028
  'open_access', 'annas', 'scihub', 'browser', 'hunt-url',
  -- a ladder-level row: a budget stop, a policy refusal, a skip no route applies to
  'ladder',
  -- Stage A (zero network) and Stage B (metadata fan-out)
  'arxiv', 'openalex', 'crossref-link', 's2', 'datacite', 'core', 'doaj', 'openaire', 'osf',
  'europepmc', 'venue', 'zenodo', 'hal', 'figshare', 'opencitations', 'ncbi-idconv',
  'eartharxiv', 'publisher-url',
  -- Stage C (landing page to bytes)
  'landing',
  -- the shadow tier's new front
  'bban',
  -- Stage E (recovery)
  'wayback', 'ia', 'commoncrawl'));

ALTER TABLE acquisition_attempts DROP CONSTRAINT acquisition_attempts_status_check;
ALTER TABLE acquisition_attempts ADD CONSTRAINT acquisition_attempts_status_check CHECK (status IN (
  -- 0013
  'ok', 'not-in-archive', 'bad-file', 'binding-failed', 'binding-pending', 'partner-404', 'no-oa-copy',
  'record-mismatch', 'hash-mismatch', 'unresolved', 'api-error', 'blocked', 'duplicate-held',
  'quota-stop', 'manual-step',
  -- 0033: attempt words, never hunt states
  'skipped', 'budget-stop', 'measured', 'known-bad'));

-- ── the new facts on every attempt ──────────────────────────────────────────────────────────
ALTER TABLE acquisition_attempts
  ADD COLUMN sub_status           text,
  ADD COLUMN sub_status_basis     text,
  ADD COLUMN terminal_url         text,
  ADD COLUMN terminal_status_code integer,
  ADD COLUMN terminal_dt          timestamptz,
  ADD COLUMN retriable            boolean,
  ADD COLUMN kind                 text,
  ADD COLUMN served_sha256        text,
  ADD COLUMN retry_of             uuid REFERENCES acquisition_attempts (id);

-- BEGIN guard: a sub-status belongs to its status
ALTER TABLE acquisition_attempts ADD CONSTRAINT acquisition_attempts_sub_status_check CHECK (
  sub_status IS NULL
  OR (status = 'bad-file' AND sub_status IN (
        'html_response', 'too_small', 'missing_pdf_header', 'corrupt_pdf_header',
        'early_eof_with_trailing_payload', 'stub_not_article', 'volume_not_article',
        'cited_document_not_this_article', 'compressed_or_archived_payload'))
  OR (status = 'blocked' AND sub_status IN (
        'identity_required', 'challenge_or_bot_check', 'not_found', 'html_or_reader'))
  OR (status = 'not-in-archive' AND sub_status IN ('not_in_corpus', 'no_pdf_link'))
  OR (status = 'skipped' AND sub_status IN (
        'dead_route', 'dead_in_run', 'no_identifier', 'policy_refused', 'backoff_window'))
  OR (status = 'budget-stop' AND sub_status IN ('budget_seconds', 'budget_attempts'))
  OR (status IN ('ok', 'measured') AND sub_status = 'unverified_keep'));
-- END guard: a sub-status belongs to its status
-- BEGIN guard: a skip or a budget stop always says why
ALTER TABLE acquisition_attempts ADD CONSTRAINT acquisition_attempts_skip_has_reason CHECK (
  status NOT IN ('skipped', 'budget-stop') OR sub_status IS NOT NULL);
-- END guard: a skip or a budget stop always says why
ALTER TABLE acquisition_attempts ADD CONSTRAINT acquisition_attempts_sub_status_basis_check CHECK (
  (sub_status IS NULL) = (sub_status_basis IS NULL)
  AND (sub_status_basis IS NULL OR sub_status_basis IN ('live', 'bytes', 'detail', 'inferred')));
ALTER TABLE acquisition_attempts ADD CONSTRAINT acquisition_attempts_kind_check CHECK (
  kind IS NULL OR kind IN ('pdf', 'jats', 'text', 'html-doc', 'cached_text', 'snippet'));
ALTER TABLE acquisition_attempts ADD CONSTRAINT acquisition_attempts_served_sha256_check CHECK (
  served_sha256 IS NULL OR served_sha256 ~ '^[0-9a-f]{64}$');
ALTER TABLE acquisition_attempts ADD CONSTRAINT acquisition_attempts_terminal_status_code_check CHECK (
  terminal_status_code IS NULL OR terminal_status_code BETWEEN 0 AND 999);
-- the ladder route carries only the rows no single rung owns
ALTER TABLE acquisition_attempts ADD CONSTRAINT acquisition_attempts_ladder_route_check CHECK (
  route <> 'ladder' OR status IN ('skipped', 'budget-stop'));
ALTER TABLE acquisition_attempts ADD CONSTRAINT acquisition_attempts_retry_not_self CHECK (
  retry_of IS NULL OR retry_of <> id);
CREATE INDEX acquisition_attempts_by_served_sha ON acquisition_attempts (served_sha256)
  WHERE served_sha256 IS NOT NULL;
CREATE INDEX acquisition_attempts_by_work_route ON acquisition_attempts (work_id, route, at);

COMMENT ON COLUMN acquisition_attempts.sub_status IS
  'WHY the status (0033; S4.5 CONTRACTS vocabulary, one Python home litkb.acquire.policy.SUB_STATUSES). '
  'Consistent with status by acquisition_attempts_sub_status_check. docs/SCHEMAS.md.';
COMMENT ON COLUMN acquisition_attempts.served_sha256 IS
  'sha256 of the bytes the route SERVED on this attempt, landed or not (0033, S4.5 item 1).';
COMMENT ON COLUMN acquisition_attempts.retry_of IS
  'A scheduled in-run transient retry names the attempt it retries (0033); NULL on every other row.';

-- ── file_versions ───────────────────────────────────────────────────────────────────────────
ALTER TABLE file_versions ADD COLUMN word_count integer CHECK (word_count IS NULL OR word_count >= 0);
COMMENT ON COLUMN file_versions.word_count IS
  'Whitespace-separated tokens in the version''s text extract (txt_extract_path), '
  'litkb.acquire.ledger.word_count_of (0033, S4.5 item 2; survey §3.4, the stub heuristics'' input).';
COMMENT ON COLUMN file_versions.copy_kind IS
  'Which copy this is. publisher / author manuscript / preprint ARE the article versions '
  'published / accepted / submitted (NISO JAV; Unpaywall and Zotero articleVersion), so the version '
  'of record is carried here and not in a new column (0033, S4.5 item 2, guard 23); scan and '
  'web snapshot are forms. Written by every landing whose route knows the version '
  '(litkb.acquire.policy.COPY_KIND_OF_VERSION); NULL where it does not.';

-- ── the per-(route, work) refusal ladder, persisted ─────────────────────────────────────────
CREATE TABLE route_backoff (
  route             text NOT NULL CHECK (route IN (
                      'open_access', 'annas', 'scihub', 'browser', 'hunt-url', 'ladder',
                      'arxiv', 'openalex', 'crossref-link', 's2', 'datacite', 'core', 'doaj', 'openaire',
                      'osf', 'europepmc', 'venue', 'zenodo', 'hal', 'figshare', 'opencitations',
                      'ncbi-idconv', 'eartharxiv', 'publisher-url', 'landing', 'bban', 'wayback', 'ia',
                      'commoncrawl')),
  work_id           uuid NOT NULL REFERENCES works (id),
  refusals          integer NOT NULL CHECK (refusals >= 0),
  window_started_at timestamptz,
  next_allowed_at   timestamptz,
  last_attempt_id   uuid NOT NULL REFERENCES acquisition_attempts (id),
  last_status       text NOT NULL,
  last_http_codes   integer[],
  last_at           timestamptz NOT NULL,
  updated_at        timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (route, work_id),
  CONSTRAINT route_backoff_window_rule CHECK (
    (refusals = 0) = (next_allowed_at IS NULL) AND (refusals = 0) = (window_started_at IS NULL))
);
COMMENT ON TABLE route_backoff IS
  'The per-(route, work) refusal ladder (0033, S4.5 item 1; PDF-sources survey guard 2, NO host '
  'suppression per guard 29). Written only by record_route_backoff. Constants and the step rule: '
  'litkb.acquire.backoff. docs/SCHEMAS.md "litkb.route_backoff".';

-- ── the backfill decision log ───────────────────────────────────────────────────────────────
CREATE TABLE acquisition_backfills (
  id           uuid PRIMARY KEY DEFAULT uuidv7(),
  op           text NOT NULL CHECK (op IN ('sub_status', 'word_count')),
  session      text NOT NULL CHECK (btrim(session) <> ''),
  source       text NOT NULL CHECK (btrim(source) <> ''),
  offered      integer NOT NULL CHECK (offered >= 0),
  applied      integer NOT NULL CHECK (applied >= 0),
  skipped      jsonb NOT NULL DEFAULT '{}'::jsonb,
  at           timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE acquisition_backfills IS
  'One row per APPLIED reviewed backfill run (0033): which op, which session, which source (the '
  'CSV path and its sha256), how many rows were offered and applied, and why the rest were not. '
  'Written only by backfill_attempt_sub_status and backfill_file_word_count.';

-- ── the one attempt writer, re-created with the new facts ───────────────────────────────────
-- BEGIN guard: the old record_acquisition_attempt signature is dropped
DROP FUNCTION litkb.record_acquisition_attempt(uuid, text, uuid, uuid, text, text, text, jsonb, integer[]);
-- END guard: the old record_acquisition_attempt signature is dropped

CREATE FUNCTION litkb.record_acquisition_attempt(
  p_workstream uuid, p_ws_token text, p_work_id uuid, p_candidate_id uuid, p_route text,
  p_identifier_used text, p_status text, p_detail jsonb, p_http_codes integer[],
  p_sub_status text DEFAULT NULL, p_served_sha256 text DEFAULT NULL,
  p_terminal_url text DEFAULT NULL, p_terminal_status_code integer DEFAULT NULL,
  p_terminal_dt timestamptz DEFAULT NULL, p_retriable boolean DEFAULT NULL, p_kind text DEFAULT NULL,
  p_retry_of uuid DEFAULT NULL)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_id uuid;
BEGIN
  -- BEGIN guard: record_acquisition_attempt presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: record_acquisition_attempt presents the workstream token
  -- BEGIN guard: a retry names an attempt of the same work, route and workstream
  IF p_retry_of IS NOT NULL THEN
    PERFORM 1 FROM acquisition_attempts a
     WHERE a.id = p_retry_of AND a.workstream_id = p_workstream AND a.route = p_route
       AND a.work_id IS NOT DISTINCT FROM p_work_id AND a.candidate_id IS NOT DISTINCT FROM p_candidate_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'litkb: attempt % is not a % attempt of this work in workstream %', p_retry_of, p_route,
        p_workstream USING ERRCODE = '42501';
    END IF;
  END IF;
  -- END guard: a retry names an attempt of the same work, route and workstream
  -- a live writer types what it saw: the basis of every sub-status written here is `live`; the
  -- historical bases (bytes / detail / inferred) are the reviewed backfill's alone
  INSERT INTO acquisition_attempts (work_id, candidate_id, route, identifier_used, status, detail,
                                    http_codes, workstream_id, sub_status, sub_status_basis, served_sha256,
                                    terminal_url, terminal_status_code, terminal_dt, retriable, kind, retry_of)
  VALUES (p_work_id, p_candidate_id, p_route, p_identifier_used, p_status, coalesce(p_detail, '{}'::jsonb),
          p_http_codes, p_workstream, p_sub_status, CASE WHEN p_sub_status IS NOT NULL THEN 'live' END,
          p_served_sha256, p_terminal_url, p_terminal_status_code, p_terminal_dt, p_retriable, p_kind, p_retry_of)
  RETURNING id INTO v_id;
  RETURN v_id;
END
$$;

-- ── the refusal ladder's one writer ─────────────────────────────────────────────────────────
-- The caller computes the step (litkb.acquire.backoff.BackoffPolicy.step, one home for the rule);
-- the database checks that the row it overwrites is being moved by an attempt of the caller's own
-- workstream on the same route and work, and that the attempt is not older than the one already
-- recorded (a late writer never rolls the ladder back).
CREATE FUNCTION litkb.record_route_backoff(
  p_workstream uuid, p_ws_token text, p_attempt_id uuid, p_refusals integer,
  p_window_started_at timestamptz, p_next_allowed_at timestamptz) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  a record;
BEGIN
  -- BEGIN guard: record_route_backoff presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: record_route_backoff presents the workstream token
  SELECT x.id, x.route, x.work_id, x.status, x.http_codes, x.at, x.workstream_id INTO a
    FROM acquisition_attempts x WHERE x.id = p_attempt_id;
  IF NOT FOUND OR a.work_id IS NULL THEN
    RAISE EXCEPTION 'litkb: % is not a work attempt', p_attempt_id USING ERRCODE = '22023';
  END IF;
  -- BEGIN guard: the back-off state moves only on an attempt of the caller's own workstream
  IF a.workstream_id IS DISTINCT FROM p_workstream THEN
    RAISE EXCEPTION 'litkb: attempt % is not a work attempt of workstream %', p_attempt_id, p_workstream
      USING ERRCODE = '42501';
  END IF;
  -- END guard: the back-off state moves only on an attempt of the caller's own workstream
  INSERT INTO route_backoff AS b (route, work_id, refusals, window_started_at, next_allowed_at,
                                  last_attempt_id, last_status, last_http_codes, last_at, updated_at)
  VALUES (a.route, a.work_id, p_refusals, p_window_started_at, p_next_allowed_at, a.id, a.status,
          a.http_codes, a.at, now())
  ON CONFLICT (route, work_id) DO UPDATE
     SET refusals = EXCLUDED.refusals, window_started_at = EXCLUDED.window_started_at,
         next_allowed_at = EXCLUDED.next_allowed_at, last_attempt_id = EXCLUDED.last_attempt_id,
         last_status = EXCLUDED.last_status, last_http_codes = EXCLUDED.last_http_codes,
         last_at = EXCLUDED.last_at, updated_at = now()
   -- BEGIN guard: an older attempt never rolls the ladder back
   WHERE b.last_at <= EXCLUDED.last_at
   -- END guard: an older attempt never rolls the ladder back
  ;
END
$$;

-- ── the reviewed backfills (ingest role, no token: system operations on history) ────────────
-- p_rows: [{"attempt_id": uuid, "sub_status": text, "basis": "bytes"|"detail"|"inferred"}, ...].
-- FILL-NULL ONLY: a row already typed is never overwritten (fatcat's monotone rule, LINKAGE §3);
-- a sub-status that does not belong to the row's status is refused per row, never forced.
CREATE FUNCTION litkb.backfill_attempt_sub_status(p_session text, p_source text, p_rows jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  r jsonb;
  v_status text;
  v_sub text;
  v_basis text;
  v_now_sub text;
  v_offered integer := 0;
  v_applied integer := 0;
  v_missing integer := 0;
  v_typed integer := 0;
  v_wrong integer := 0;
  v_basis_bad integer := 0;
  v_id uuid;
BEGIN
  IF coalesce(btrim(p_session), '') = '' OR coalesce(btrim(p_source), '') = '' THEN
    RAISE EXCEPTION 'litkb: a backfill needs a session and a source' USING ERRCODE = '22023';
  END IF;
  IF p_rows IS NULL OR jsonb_typeof(p_rows) <> 'array' THEN
    RAISE EXCEPTION 'litkb: backfill rows must be a JSON array' USING ERRCODE = '22023';
  END IF;
  FOR r IN SELECT * FROM jsonb_array_elements(p_rows) LOOP
    v_offered := v_offered + 1;
    v_sub := r->>'sub_status';
    v_basis := r->>'basis';
    -- BEGIN guard: a backfilled typing names how it was typed
    IF v_basis IS NULL OR v_basis NOT IN ('bytes', 'detail', 'inferred') THEN
      v_basis_bad := v_basis_bad + 1;
      CONTINUE;
    END IF;
    -- END guard: a backfilled typing names how it was typed
    SELECT a.status, a.sub_status INTO v_status, v_now_sub FROM acquisition_attempts a
     WHERE a.id = (r->>'attempt_id')::uuid FOR UPDATE;
    IF NOT FOUND THEN
      v_missing := v_missing + 1;
      CONTINUE;
    END IF;
    -- BEGIN guard: a backfill fills a null and never overwrites a typing
    IF v_now_sub IS NOT NULL THEN
      v_typed := v_typed + 1;
      CONTINUE;
    END IF;
    -- END guard: a backfill fills a null and never overwrites a typing
    IF NOT ((v_status = 'bad-file' AND v_sub IN (
               'html_response', 'too_small', 'missing_pdf_header', 'corrupt_pdf_header',
               'early_eof_with_trailing_payload', 'stub_not_article', 'volume_not_article',
               'cited_document_not_this_article', 'compressed_or_archived_payload'))
            OR (v_status = 'blocked' AND v_sub IN (
               'identity_required', 'challenge_or_bot_check', 'not_found', 'html_or_reader'))
            OR (v_status = 'not-in-archive' AND v_sub IN ('not_in_corpus', 'no_pdf_link'))) THEN
      v_wrong := v_wrong + 1;
      CONTINUE;
    END IF;
    UPDATE acquisition_attempts a SET sub_status = v_sub, sub_status_basis = v_basis
     WHERE a.id = (r->>'attempt_id')::uuid AND a.sub_status IS NULL;
    v_applied := v_applied + 1;
  END LOOP;
  INSERT INTO acquisition_backfills (op, session, source, offered, applied, skipped)
  VALUES ('sub_status', p_session, p_source, v_offered, v_applied,
          jsonb_build_object('missing', v_missing, 'already_typed', v_typed, 'wrong_family', v_wrong,
                             'bad_basis', v_basis_bad))
  RETURNING id INTO v_id;
  RETURN jsonb_build_object('backfill_id', v_id, 'offered', v_offered, 'applied', v_applied,
                            'missing', v_missing, 'already_typed', v_typed, 'wrong_family', v_wrong,
                            'bad_basis', v_basis_bad);
END
$$;

-- p_rows: [{"version_id": uuid, "word_count": integer}, ...]. FILL-NULL ONLY, like the above.
CREATE FUNCTION litkb.backfill_file_word_count(p_session text, p_source text, p_rows jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  r jsonb;
  v_n integer;
  v_offered integer := 0;
  v_applied integer := 0;
  v_skipped integer := 0;
  v_id uuid;
BEGIN
  IF coalesce(btrim(p_session), '') = '' OR coalesce(btrim(p_source), '') = '' THEN
    RAISE EXCEPTION 'litkb: a backfill needs a session and a source' USING ERRCODE = '22023';
  END IF;
  IF p_rows IS NULL OR jsonb_typeof(p_rows) <> 'array' THEN
    RAISE EXCEPTION 'litkb: backfill rows must be a JSON array' USING ERRCODE = '22023';
  END IF;
  FOR r IN SELECT * FROM jsonb_array_elements(p_rows) LOOP
    v_offered := v_offered + 1;
    -- BEGIN guard: a word count fills a null and never overwrites one
    UPDATE file_versions fv SET word_count = (r->>'word_count')::integer
     WHERE fv.version_id = (r->>'version_id')::uuid AND fv.word_count IS NULL;
    -- END guard: a word count fills a null and never overwrites one
    GET DIAGNOSTICS v_n = ROW_COUNT;
    IF v_n = 1 THEN
      v_applied := v_applied + 1;
    ELSE
      v_skipped := v_skipped + 1;
    END IF;
  END LOOP;
  INSERT INTO acquisition_backfills (op, session, source, offered, applied, skipped)
  VALUES ('word_count', p_session, p_source, v_offered, v_applied,
          jsonb_build_object('missing_or_already_counted', v_skipped))
  RETURNING id INTO v_id;
  RETURN jsonb_build_object('backfill_id', v_id, 'offered', v_offered, 'applied', v_applied,
                            'missing_or_already_counted', v_skipped);
END
$$;

-- ── privileges ──────────────────────────────────────────────────────────────────────────────
REVOKE EXECUTE ON FUNCTION
  litkb.record_acquisition_attempt(uuid, text, uuid, uuid, text, text, text, jsonb, integer[], text, text, text,
                                   integer, timestamptz, boolean, text, uuid),
  litkb.record_route_backoff(uuid, text, uuid, integer, timestamptz, timestamptz),
  litkb.backfill_attempt_sub_status(text, text, jsonb),
  litkb.backfill_file_word_count(text, text, jsonb)
FROM PUBLIC;
-- BEGIN guard: the writer records attempts and back-off with its token; the ingest login alone backfills history
GRANT EXECUTE ON FUNCTION
  litkb.record_acquisition_attempt(uuid, text, uuid, uuid, text, text, text, jsonb, integer[], text, text, text,
                                   integer, timestamptz, boolean, text, uuid),
  litkb.record_route_backoff(uuid, text, uuid, integer, timestamptz, timestamptz)
TO litkb_writer;
GRANT EXECUTE ON FUNCTION
  litkb.backfill_attempt_sub_status(text, text, jsonb),
  litkb.backfill_file_word_count(text, text, jsonb)
TO litkb_ingest;
-- END guard: the writer records attempts and back-off with its token; the ingest login alone backfills history
GRANT SELECT ON route_backoff, acquisition_backfills TO litkb_reader, litkb_writer, litkb_ingest;

-- end of 0033
