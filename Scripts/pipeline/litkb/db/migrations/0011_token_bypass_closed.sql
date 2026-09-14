-- litkb 0011 — close the last bypass of the workstream token (decisions.yaml litkb-p0-foundation,
-- "After the second P1 referee": each workstream gets a secret token its session must present).
-- 0010 put the token on every writer FUNCTION that names a workstream, but 0006 had also granted
-- the writer direct column INSERT on tables whose rows belong to a workstream. Those inserts were
-- not token-checked (Reports/LITKB_P1_REPORT_2026-09-13.md, "Residual, not fixed").
--
-- Enumerated from the catalog on litkb and litkb_test before this migration (has_table_privilege
-- and has_column_privilege for INSERT/UPDATE/DELETE/TRUNCATE, roles reader, writer, promoter,
-- ingest): the only agent write rights on workstream-bearing tables were the writer's column
-- INSERT on
--   gap_versions, use_versions            workstream_id column          -> write_proposal (0010)
--   candidates, acquisition_attempts      workstream_id column          -> add_candidate, record_acquisition_attempt (new)
--   admissions                            workstream_id column          -> no writer path in P1; P2's admit
--   use_embeddings                        FK to use_versions (one hop)  -> add_use_embedding (new)
-- Every one is revoked here. REVOKE INSERT on a table also revokes the column-level INSERT grants
-- on it, so 0006's column lists are now history (a mutation of them is dead code).
--
-- "Workstream-bearing" (the rule qc/test_litkb_p1.py builds from the catalog): a table with a
-- foreign key to litkb.workstreams, or with a foreign key to a table that has a workstream_id
-- column. The extraction tables stay out: they reference files/extraction_runs, whose
-- created_in_ws is creation provenance on a main-owned identity row, not a workstream's view.

SET LOCAL search_path = litkb, public;

-- ── revoke the direct writes ─────────────────────────────────────────────────────────────
-- BEGIN guard: writer has no direct INSERT on gap_versions
REVOKE INSERT ON litkb.gap_versions FROM litkb_writer;
-- END guard: writer has no direct INSERT on gap_versions
-- BEGIN guard: writer has no direct INSERT on use_versions
REVOKE INSERT ON litkb.use_versions FROM litkb_writer;
-- END guard: writer has no direct INSERT on use_versions
-- BEGIN guard: writer has no direct INSERT on candidates
REVOKE INSERT ON litkb.candidates FROM litkb_writer;
-- END guard: writer has no direct INSERT on candidates
-- BEGIN guard: writer has no direct INSERT on admissions
REVOKE INSERT ON litkb.admissions FROM litkb_writer;
-- END guard: writer has no direct INSERT on admissions
-- BEGIN guard: writer has no direct INSERT on acquisition_attempts
REVOKE INSERT ON litkb.acquisition_attempts FROM litkb_writer;
-- END guard: writer has no direct INSERT on acquisition_attempts
-- BEGIN guard: writer has no direct INSERT on use_embeddings
REVOKE INSERT ON litkb.use_embeddings FROM litkb_writer;
-- END guard: writer has no direct INSERT on use_embeddings

-- ── the token-checked replacements ───────────────────────────────────────────────────────
-- A candidate recorded by a session, in its workstream. The admission outcome columns (state,
-- state_reason, admitted_work_id) are not taken: they are set by admission (P2), not by the lead.
CREATE FUNCTION litkb.add_candidate(
  p_workstream uuid, p_ws_token text, p_source text, p_source_detail text, p_query text,
  p_citing_reference_id uuid, p_raw_record jsonb, p_title text, p_authors jsonb, p_year integer,
  p_ids jsonb)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_id uuid;
BEGIN
  -- BEGIN guard: add_candidate presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: add_candidate presents the workstream token
  INSERT INTO candidates (source, source_detail, query, citing_reference_id, raw_record, title, authors,
                          year, ids, workstream_id)
  VALUES (p_source, p_source_detail, p_query, p_citing_reference_id, p_raw_record, p_title, p_authors,
          p_year, p_ids, p_workstream)
  RETURNING id INTO v_id;
  RETURN v_id;
END
$$;

CREATE FUNCTION litkb.record_acquisition_attempt(
  p_workstream uuid, p_ws_token text, p_work_id uuid, p_candidate_id uuid, p_route text,
  p_identifier_used text, p_status text, p_detail jsonb, p_http_codes integer[])
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_id uuid;
BEGIN
  -- BEGIN guard: record_acquisition_attempt presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: record_acquisition_attempt presents the workstream token
  INSERT INTO acquisition_attempts (work_id, candidate_id, route, identifier_used, status, detail,
                                    http_codes, workstream_id)
  VALUES (p_work_id, p_candidate_id, p_route, p_identifier_used, p_status, coalesce(p_detail, '{}'::jsonb),
          p_http_codes, p_workstream)
  RETURNING id INTO v_id;
  RETURN v_id;
END
$$;

-- An embedding of a use version belongs to that version's workstream: the caller names the
-- workstream, presents its token, and the version must have been written in it (as add_evidence).
CREATE FUNCTION litkb.add_use_embedding(
  p_workstream uuid, p_ws_token text, p_use_version uuid, p_model text, p_dim integer, p_vector halfvec)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_ws uuid;
BEGIN
  -- BEGIN guard: add_use_embedding presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: add_use_embedding presents the workstream token
  SELECT uv.workstream_id INTO v_ws FROM use_versions uv WHERE uv.version_id = p_use_version;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: no use version %', p_use_version USING ERRCODE = 'P0002';
  END IF;
  -- BEGIN guard: embedding version belongs to the workstream
  IF v_ws IS DISTINCT FROM p_workstream THEN
    RAISE EXCEPTION 'litkb: use version % belongs to another workstream', p_use_version USING ERRCODE = '42501';
  END IF;
  -- END guard: embedding version belongs to the workstream
  INSERT INTO use_embeddings (use_version_id, model, dim, vector)
  VALUES (p_use_version, p_model, p_dim, p_vector);
END
$$;

REVOKE EXECUTE ON FUNCTION
  litkb.add_candidate(uuid, text, text, text, text, uuid, jsonb, text, jsonb, integer, jsonb),
  litkb.record_acquisition_attempt(uuid, text, uuid, uuid, text, text, text, jsonb, integer[]),
  litkb.add_use_embedding(uuid, text, uuid, text, integer, halfvec)
FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
  litkb.add_candidate(uuid, text, text, text, text, uuid, jsonb, text, jsonb, integer, jsonb),
  litkb.record_acquisition_attempt(uuid, text, uuid, uuid, text, text, text, jsonb, integer[]),
  litkb.add_use_embedding(uuid, text, uuid, text, integer, halfvec)
TO litkb_writer;

-- end of 0011
