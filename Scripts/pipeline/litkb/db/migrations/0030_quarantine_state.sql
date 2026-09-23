-- litkb 0030 — the database-visible quarantine state (LITKB_WORKPLAN.md "### S4", "A database-visible
-- quarantine state"; S4 run 3 decision D5).
--
-- WHY. `_quarantine/` was a directory and nothing else. `Store.to_quarantine` writes the status and
-- the sha into the FILENAME and no code reads that name back; the `.reason.json` sidecar is written
-- by some callers only; `hunt.land_download` and the staging reaper leave no database row at all
-- (S4 run 3 code survey C7). Measured on the live store 2026-09-22 (data survey D4): 69 payloads,
-- 42 of them with no database trace whatever, and the 27 that have one reachable only through
-- `acquisition_attempts.detail` JSON. A refused file was invisible to `litkb_work`.
--
-- WHY A NEW TABLE and not `file_versions.status = 'quarantined'` (decision D5): `file_versions.work_id`
-- is NOT NULL (0001), and most refused bytes have no admitted work — a bot-challenge page served for
-- an open-access link, a staging orphan, a legacy download. One row per refused PAYLOAD, keyed by
-- its path relative to the literature root. `file_versions` is not touched.
--
-- TWO KINDS OF ROW, told apart by the path:
--   * a payload MOVED into `_quarantine/` — the row names where the bytes now lie;
--   * a file REFUSED WHERE IT LIES — a bound file the readability classifier refuses (`bad-file`,
--     `zero-content`), or an admission file whose page count could not be read (`probe-error`,
--     admission never moves a file). The bytes are NOT moved: the row IS the state, recorded
--     against the current path, with the file_id when there is one.
--
-- THE TWO WRITERS (the table is a GUARDED RELATION: it carries workstream_id, so no agent role may
-- hold a direct write on it — qc/test_litkb_p1.py builds that rule from the catalog):
--   record_quarantine         writer-side, presents the workstream token (the acquisition and hunt
--                             callers run as litkb_writer inside a workstream: record_acquisition_attempt's
--                             shape, 0011). Origins acquisition-guard, bind-refusal, hunt-url only.
--   record_quarantine_system  ingest-side, no token, for system operations on main-owned state (the
--                             reaper, the classifier, the backfill: set_current_run's shape, 0017).
--                             Origins reaper, classifier, legacy-backfill only.
-- Both are IDEMPOTENT ON THE PATH: a second call for a recorded path with the same sha256 returns the
-- existing id and writes nothing; a call for a recorded path with DIFFERENT bytes is refused, because
-- a store that never overwrites (acquire/store.py) cannot put two payloads at one path, and a row
-- that silently kept the first sha would describe bytes that are no longer there.
--
-- CLEARING (orchestrator ruling on builder-B's question 6, 2026-09-22; amended INTO 0030 because 0030
-- had been applied to worker databases only). A `classifier` row on a BOUND file — the only kind of
-- row whose bytes were never moved — carries `cleared_at` / `cleared_by` / `cleared_reason`. When
-- the classifier later classes that file `extracted`, it clears its OWN row through
-- `clear_quarantine_system` (ingest, no token). A moved-payload row (acquisition guard, bind refusal,
-- hunt-url, reaper, backfill) is NEVER cleared: those bytes stay refused. A cleared row that the
-- classifier refuses again is RE-OPENED by the same idempotent write (`_record_quarantine_row`).
--
-- The vocabularies below have ONE home in Python, `litkb.quarantine.REASONS` / `.ORIGINS`;
-- qc/test_litkb_quarantine.py holds this CHECK equal to them.

SET LOCAL search_path = litkb, public;

CREATE TABLE quarantine_payloads (
  id            uuid PRIMARY KEY DEFAULT uuidv7(),
  rel_path      text NOT NULL UNIQUE CHECK (rel_path <> '' AND rel_path !~ '^/' AND rel_path !~ '\\'),
  sha256        text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  bytes         bigint NOT NULL CHECK (bytes >= 0),
  reason        text NOT NULL CHECK (reason IN (
                  -- the shapes store.pdf_shape names (acquisition guard, --from-file, hunt.land_download)
                  'not-a-pdf', 'truncated-pdf',
                  -- the route statuses a route hands back WITH bytes (open_access, scihub, annas)
                  'blocked', 'bad-file', 'not-in-archive', 'partner-404', 'hash-mismatch',
                  -- the binding verdicts and attach outcomes land_and_attach quarantines under
                  'binding-failed', 'binding-pending', 'duplicate-held',
                  -- the legacy annas.fetch_one labels still on disk
                  'duplicate-hash', 'content-mismatch',
                  -- the staging reaper's label
                  'staging-orphan',
                  -- S4: the fail-closed page probe, and the classifier's refusal of a file with no text
                  'probe-error', 'zero-content',
                  -- a pre-litkb name that carries no label at all
                  'legacy')),
  origin        text NOT NULL CHECK (origin IN (
                  'acquisition-guard', 'bind-refusal', 'hunt-url',
                  'reaper', 'classifier', 'legacy-backfill')),
  work_id       uuid REFERENCES works (id),
  file_id       uuid REFERENCES files (id),
  attempt_id    uuid REFERENCES acquisition_attempts (id),
  workstream_id uuid REFERENCES workstreams (id),
  detail        jsonb NOT NULL DEFAULT '{}'::jsonb,
  recorded_at   timestamptz NOT NULL DEFAULT now(),
  cleared_at     timestamptz,
  cleared_by     text,
  cleared_reason text,
  CONSTRAINT quarantine_payloads_cleared_together CHECK (
    (cleared_at IS NULL) = (cleared_by IS NULL) AND (cleared_at IS NULL) = (cleared_reason IS NULL)),
  -- BEGIN guard: only a classifier row on a bound file can ever be cleared
  CONSTRAINT quarantine_payloads_cleared_only_in_place CHECK (
    cleared_at IS NULL OR (origin = 'classifier' AND file_id IS NOT NULL AND rel_path NOT LIKE '\_quarantine/%')),
  -- END guard: only a classifier row on a bound file can ever be cleared
  -- BEGIN guard: a row outside _quarantine/ is a file refused where it lies, and names why
  -- Only the classifier (a bound file: file_id) and an admission's probe refusal (an in-place file
  -- that was never attached) record a path the bytes were NOT moved from.
  CONSTRAINT quarantine_payloads_in_place_rule CHECK (
    rel_path LIKE '\_quarantine/%'
    OR (origin = 'classifier' AND file_id IS NOT NULL)
    OR (origin = 'bind-refusal' AND reason = 'probe-error')),
  -- END guard: a row outside _quarantine/ is a file refused where it lies, and names why
  -- a system row belongs to no workstream; a writer row always to one
  CONSTRAINT quarantine_payloads_workstream_rule CHECK (
    (origin IN ('reaper', 'classifier', 'legacy-backfill')) = (workstream_id IS NULL))
);
CREATE INDEX quarantine_payloads_by_sha ON quarantine_payloads (sha256);
CREATE INDEX quarantine_payloads_by_file ON quarantine_payloads (file_id) WHERE file_id IS NOT NULL;
CREATE INDEX quarantine_payloads_by_work ON quarantine_payloads (work_id) WHERE work_id IS NOT NULL;

COMMENT ON TABLE quarantine_payloads IS
  'One row per refused payload, keyed by its path under the literature root (LITKB_WORKPLAN.md S4, '
  'decision D5). A path under _quarantine/ is where the refused bytes were moved; any other path is '
  'a file refused where it lies (the row is the state). GUARDED RELATION: written only by '
  'record_quarantine (writer, token) and record_quarantine_system (ingest). Vocabularies: '
  'litkb.quarantine.REASONS / ORIGINS, docs/SCHEMAS.md "litkb.quarantine_payloads".';

-- The one body both writers share. NOT granted to anyone: it runs only inside the two SECURITY
-- DEFINER functions below, as their owner.
CREATE FUNCTION litkb._record_quarantine_row(
  p_rel_path text, p_sha256 text, p_bytes bigint, p_reason text, p_origin text, p_work_id uuid,
  p_file_id uuid, p_attempt_id uuid, p_workstream uuid, p_detail jsonb) RETURNS uuid
LANGUAGE plpgsql SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_id uuid;
  v_sha text;
BEGIN
  INSERT INTO quarantine_payloads (rel_path, sha256, bytes, reason, origin, work_id, file_id, attempt_id,
                                   workstream_id, detail)
  VALUES (p_rel_path, p_sha256, p_bytes, p_reason, p_origin, p_work_id, p_file_id, p_attempt_id,
          p_workstream, coalesce(p_detail, '{}'::jsonb))
  ON CONFLICT (rel_path) DO NOTHING
  RETURNING id INTO v_id;
  IF v_id IS NOT NULL THEN
    RETURN v_id;
  END IF;
  SELECT q.id, q.sha256 INTO v_id, v_sha FROM quarantine_payloads q WHERE q.rel_path = p_rel_path;
  -- BEGIN guard: one path holds one payload
  IF v_sha IS DISTINCT FROM p_sha256 THEN
    RAISE EXCEPTION 'litkb: % is already recorded as quarantined bytes % and is now offered as %',
      p_rel_path, v_sha, p_sha256 USING ERRCODE = '23505';
  END IF;
  -- END guard: one path holds one payload
  -- a CLEARED row refused again is re-opened: the refusal is current once more
  UPDATE quarantine_payloads q
     SET cleared_at = NULL, cleared_by = NULL, cleared_reason = NULL, reason = p_reason,
         detail = coalesce(p_detail, '{}'::jsonb), recorded_at = now()
   WHERE q.id = v_id AND q.cleared_at IS NOT NULL;
  RETURN v_id;
END
$$;
REVOKE EXECUTE ON FUNCTION
  litkb._record_quarantine_row(text, text, bigint, text, text, uuid, uuid, uuid, uuid, jsonb) FROM PUBLIC;

CREATE FUNCTION litkb.record_quarantine(
  p_workstream uuid, p_ws_token text, p_rel_path text, p_sha256 text, p_bytes bigint, p_reason text,
  p_origin text, p_work_id uuid, p_file_id uuid, p_attempt_id uuid, p_detail jsonb) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
BEGIN
  -- BEGIN guard: record_quarantine presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: record_quarantine presents the workstream token
  -- BEGIN guard: record_quarantine writes only the workstream-side origins
  IF p_origin IS NULL OR p_origin NOT IN ('acquisition-guard', 'bind-refusal', 'hunt-url') THEN
    RAISE EXCEPTION 'litkb: origin % is a system origin; record_quarantine takes acquisition-guard, bind-refusal or hunt-url',
      p_origin USING ERRCODE = '42501';
  END IF;
  -- END guard: record_quarantine writes only the workstream-side origins
  -- BEGIN guard: record_quarantine links only this workstream's own attempt
  IF p_attempt_id IS NOT NULL THEN
    PERFORM 1 FROM acquisition_attempts a WHERE a.id = p_attempt_id AND a.workstream_id = p_workstream;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'litkb: acquisition attempt % is not workstream %''s', p_attempt_id, p_workstream
        USING ERRCODE = '42501';
    END IF;
  END IF;
  -- END guard: record_quarantine links only this workstream's own attempt
  RETURN _record_quarantine_row(p_rel_path, p_sha256, p_bytes, p_reason, p_origin, p_work_id, p_file_id,
                                p_attempt_id, p_workstream, p_detail);
END
$$;

CREATE FUNCTION litkb.record_quarantine_system(
  p_rel_path text, p_sha256 text, p_bytes bigint, p_reason text, p_origin text, p_work_id uuid,
  p_file_id uuid, p_attempt_id uuid, p_detail jsonb) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
BEGIN
  -- BEGIN guard: record_quarantine_system writes only the system origins
  IF p_origin IS NULL OR p_origin NOT IN ('reaper', 'classifier', 'legacy-backfill') THEN
    RAISE EXCEPTION 'litkb: origin % needs a workstream token; record_quarantine_system takes reaper, classifier or legacy-backfill',
      p_origin USING ERRCODE = '42501';
  END IF;
  -- END guard: record_quarantine_system writes only the system origins
  RETURN _record_quarantine_row(p_rel_path, p_sha256, p_bytes, p_reason, p_origin, p_work_id, p_file_id,
                                p_attempt_id, NULL, p_detail);
END
$$;

-- The classifier clears ITS OWN row once the file it refused is classed `extracted`. Once only: a
-- cleared row stays as it was cleared until a new refusal re-opens it. Returns true when it cleared.
CREATE FUNCTION litkb.clear_quarantine_system(p_id uuid, p_session text, p_reason text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_n integer;
BEGIN
  IF coalesce(btrim(p_session), '') = '' OR coalesce(btrim(p_reason), '') = '' THEN
    RAISE EXCEPTION 'litkb: clearing a quarantine row needs a session and a reason' USING ERRCODE = '22023';
  END IF;
  -- BEGIN guard: only the classifier's own row on a bound file is cleared, never a moved payload
  PERFORM 1 FROM quarantine_payloads q
   WHERE q.id = p_id AND q.origin = 'classifier' AND q.file_id IS NOT NULL
     AND q.rel_path NOT LIKE '\_quarantine/%';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: quarantine row % is not a classifier row on a bound file; moved payloads stay refused',
      p_id USING ERRCODE = '42501';
  END IF;
  -- END guard: only the classifier's own row on a bound file is cleared, never a moved payload
  UPDATE quarantine_payloads q SET cleared_at = now(), cleared_by = p_session, cleared_reason = p_reason
   WHERE q.id = p_id AND q.cleared_at IS NULL;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  RETURN v_n > 0;
END
$$;

-- ── privileges ───────────────────────────────────────────────────────────────────────────
REVOKE EXECUTE ON FUNCTION
  litkb.record_quarantine(uuid, text, text, text, bigint, text, text, uuid, uuid, uuid, jsonb),
  litkb.record_quarantine_system(text, text, bigint, text, text, uuid, uuid, uuid, jsonb),
  litkb.clear_quarantine_system(uuid, text, text)
FROM PUBLIC;
-- BEGIN guard: the writer records workstream quarantines and the ingest login system ones, neither a direct write
GRANT EXECUTE ON FUNCTION
  litkb.record_quarantine(uuid, text, text, text, bigint, text, text, uuid, uuid, uuid, jsonb)
TO litkb_writer;
GRANT EXECUTE ON FUNCTION
  litkb.record_quarantine_system(text, text, bigint, text, text, uuid, uuid, uuid, jsonb),
  litkb.clear_quarantine_system(uuid, text, text)
TO litkb_ingest;
-- END guard: the writer records workstream quarantines and the ingest login system ones, neither a direct write
GRANT SELECT ON quarantine_payloads TO litkb_reader, litkb_writer, litkb_ingest;

-- end of 0030
