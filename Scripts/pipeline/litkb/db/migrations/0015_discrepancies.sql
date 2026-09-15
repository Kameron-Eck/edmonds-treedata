-- litkb 0015 — discrepancies: what the legacy tracker and manifest claim, where it disagrees
-- with the registry record that was actually admitted.
--
-- decisions.yaml `litkb-p0-foundation`, "P3 load (Kam, 2026-09-14)": identity comes from the
-- registry record and the verified file; EVERY tracker or manifest field that disagrees with
-- the registry is kept as a flagged discrepancy for later review, nothing dropped; no
-- correction pass on the old tracker before loading.
--
-- The table carries workstream_id, so it is a GUARDED RELATION (design §4.7, migration 0011):
-- no agent role gets INSERT on it. The only writer is the token-checked SECURITY DEFINER
-- function below, exactly like admit() and attach_file().

SET LOCAL search_path = litkb, public;

CREATE TABLE discrepancies (
  id            uuid PRIMARY KEY DEFAULT uuidv7(),
  source        text NOT NULL CHECK (source IN ('tracker', 'manifest')),
  source_row    text NOT NULL CHECK (source_row <> ''),   -- tracker ID, or manifest stem
  field         text NOT NULL CHECK (field <> ''),
  claimed_value text,                                     -- what the legacy row says
  registry_value text,                                    -- what the admitted record says
  ratio         numeric,                                  -- the comparator's ratio, where one applies
  detail        jsonb NOT NULL DEFAULT '{}'::jsonb,
  -- one of these two is set: the work when the row was admitted, the candidate when it was not
  work_id       uuid REFERENCES works (id),
  candidate_id  uuid REFERENCES candidates (id),
  workstream_id uuid NOT NULL REFERENCES workstreams (id),
  agent         text NOT NULL CHECK (agent <> ''),
  session_id    text NOT NULL CHECK (session_id <> ''),
  created_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT discrepancies_has_a_subject CHECK (work_id IS NOT NULL OR candidate_id IS NOT NULL)
);

-- idempotency: loading the same legacy row twice records the same discrepancy once
CREATE UNIQUE INDEX discrepancies_one_per_field
  ON discrepancies (workstream_id, source, source_row, field);

CREATE INDEX discrepancies_by_work ON discrepancies (work_id) WHERE work_id IS NOT NULL;

COMMENT ON TABLE discrepancies IS
  'Legacy tracker/manifest fields that disagree with the admitted registry record (P3, decisions.yaml litkb-p0-foundation). Review material, never a correction.';

-- ── the one writer ───────────────────────────────────────────────────────────────────────
CREATE FUNCTION litkb.record_discrepancy(
  p_workstream uuid, p_ws_token text, p_source text, p_source_row text, p_field text,
  p_claimed text, p_registry text, p_ratio numeric, p_detail jsonb,
  p_work uuid, p_candidate uuid, p_agent text, p_session text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_id uuid;
BEGIN
  -- BEGIN guard: record_discrepancy presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: record_discrepancy presents the workstream token
  PERFORM 1 FROM workstreams w WHERE w.id = p_workstream AND w.state = 'open' FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % is not open', p_workstream USING ERRCODE = '22023';
  END IF;
  -- BEGIN guard: a discrepancy names the work or the candidate it belongs to
  IF p_work IS NULL AND p_candidate IS NULL THEN
    RAISE EXCEPTION 'litkb: a discrepancy names a work or a candidate' USING ERRCODE = '22023';
  END IF;
  -- END guard: a discrepancy names the work or the candidate it belongs to
  -- BEGIN guard: a discrepancy's candidate belongs to its workstream
  IF p_candidate IS NOT NULL THEN
    PERFORM 1 FROM candidates cd WHERE cd.id = p_candidate AND cd.workstream_id = p_workstream;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'litkb: candidate % is not this workstream''s', p_candidate USING ERRCODE = '42501';
    END IF;
  END IF;
  -- END guard: a discrepancy's candidate belongs to its workstream
  INSERT INTO discrepancies (source, source_row, field, claimed_value, registry_value, ratio, detail,
                             work_id, candidate_id, workstream_id, agent, session_id)
  VALUES (p_source, p_source_row, p_field, p_claimed, p_registry, p_ratio, coalesce(p_detail, '{}'::jsonb),
          p_work, p_candidate, p_workstream, p_agent, p_session)
  ON CONFLICT (workstream_id, source, source_row, field) DO NOTHING
  RETURNING id INTO v_id;
  IF v_id IS NULL THEN
    SELECT d.id INTO v_id FROM discrepancies d
     WHERE d.workstream_id = p_workstream AND d.source = p_source
       AND d.source_row = p_source_row AND d.field = p_field;
  END IF;
  RETURN v_id;
END
$$;

-- ── a workstream's view of its discrepancies, and main's ─────────────────────────────────
CREATE VIEW discrepancy_report AS
  SELECT d.*, w.key AS work_key, ws.slug AS workstream
    FROM discrepancies d
    LEFT JOIN works w ON w.id = d.work_id
    JOIN workstreams ws ON ws.id = d.workstream_id;

-- ── privileges ───────────────────────────────────────────────────────────────────────────
REVOKE EXECUTE ON FUNCTION
  litkb.record_discrepancy(uuid, text, text, text, text, text, text, numeric, jsonb, uuid, uuid, text, text)
FROM PUBLIC;
-- BEGIN guard: writer executes record_discrepancy and holds no direct write on discrepancies
GRANT EXECUTE ON FUNCTION
  litkb.record_discrepancy(uuid, text, text, text, text, text, text, numeric, jsonb, uuid, uuid, text, text)
TO litkb_writer;
GRANT SELECT ON discrepancies, discrepancy_report TO litkb_reader, litkb_writer, litkb_ingest;
-- END guard: writer executes record_discrepancy and holds no direct write on discrepancies

-- end of 0015
