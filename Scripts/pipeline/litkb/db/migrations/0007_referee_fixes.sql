-- litkb 0007 — fixes after the independent P1 referee (Reports/LITKB_P1_REFEREE_2026-09-13.md).
-- Applied migrations are checksum-locked, so this file REPLACES functions defined in 0003
-- rather than editing them there. The live definitions of _write_version, set_current_run and
-- _use_evidence_verify are the ones below; the 0003 bodies are history.
--
--   D-1  _write_version locks the workstream row FOR SHARE, so a write cannot land in a
--        workstream while promote_prepare / promote_commit (FOR UPDATE) is deciding it.
--        Under READ COMMITTED the locked row is re-checked after the wait: a writer that
--        waited behind a commit sees state = 'merged' and is refused (22023).
--   D-5  evidence enters only through add_evidence (SECURITY DEFINER): the use version must be
--        'proposed', belong to the named workstream, that workstream must be open (locked
--        FOR SHARE) and have no prepared promotion. The writer's direct INSERT is revoked.
--        set_current_run moves a file only to an existing 'ok' run of that file.
--   D-7  quote verification refuses char_end beyond the block text.
--   D-8  the identity-row FOR UPDATE stays; it makes the losing writer's error 40001.

SET LOCAL search_path = litkb, public;

CREATE OR REPLACE FUNCTION litkb._write_version(
  p_mode text, p_entity text, p_entity_id uuid, p_identity jsonb, p_based_on uuid,
  p_fields jsonb, p_change_reason text, p_workstream uuid, p_agent text, p_session text,
  OUT entity_id uuid, OUT version_id uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  t record;
  v_entity uuid;
  v_version uuid;
  v_main uuid;
  v_no integer;
  v_merged jsonb;
  v_cols text;
  v_bad text[];
  v_n bigint;
BEGIN
  IF p_mode IS NULL OR p_mode NOT IN ('fact', 'proposal') THEN
    RAISE EXCEPTION 'litkb: mode must be fact or proposal, got %', p_mode USING ERRCODE = '22023';
  END IF;
  SELECT * INTO t FROM _entity_tables(p_entity);
  -- D-1: FOR SHARE conflicts with promote_prepare/promote_commit's FOR UPDATE on this row and
  -- is held to the end of the write, so the workstream cannot close under a write in flight.
  PERFORM 1 FROM workstreams w WHERE w.id = p_workstream AND w.state = 'open' FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % is not open', p_workstream USING ERRCODE = '22023';
  END IF;
  IF p_fields IS NULL OR jsonb_typeof(p_fields) <> 'object' THEN
    RAISE EXCEPTION 'litkb: fields must be a JSON object' USING ERRCODE = '22023';
  END IF;
  SELECT array_agg(k) INTO v_bad FROM jsonb_object_keys(p_fields) k
   WHERE k = ANY (ARRAY['version_id', t.fk, 'version_no', 'change_reason', 'based_on_version_id',
                        'workstream_id', 'agent', 'session_id', 'created_at', 'state',
                        'promoted_at', 'promotion_id']);
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'litkb: fields may not set controlled columns %', v_bad USING ERRCODE = '42501';
  END IF;
  SELECT array_agg(k) INTO v_bad FROM jsonb_object_keys(p_fields) k
   WHERE NOT EXISTS (SELECT 1 FROM pg_attribute a
                      WHERE a.attrelid = t.vers AND a.attname = k AND a.attnum > 0 AND NOT a.attisdropped);
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'litkb: % has no columns %', t.vers, v_bad USING ERRCODE = '42703';
  END IF;

  IF p_entity_id IS NULL THEN
    IF p_based_on IS NOT NULL THEN
      RAISE EXCEPTION 'litkb: a new % cannot be based on a version', p_entity USING ERRCODE = '22023';
    END IF;
    v_entity := _create_identity(p_entity, p_identity, p_fields, p_workstream);
  ELSE
    IF p_identity IS NOT NULL AND p_identity <> '{}'::jsonb THEN
      RAISE EXCEPTION 'litkb: identity fields of an existing % are immutable', p_entity USING ERRCODE = '22023';
    END IF;
    v_entity := p_entity_id;
  END IF;

  -- serialise all writers of this entity (D-8: without it the loser gets 23505, not 40001)
  EXECUTE format('SELECT current_version_id FROM %s WHERE id = $1 FOR UPDATE', t.ident)
    INTO v_main USING v_entity;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  IF v_n <> 1 THEN
    RAISE EXCEPTION 'litkb: no % with id %', p_entity, v_entity USING ERRCODE = 'P0002';
  END IF;

  IF p_entity = 'identifier' THEN
    PERFORM 1 FROM identifiers i
     WHERE i.id = v_entity AND i.value_norm = norm_identifier(i.scheme, p_fields->>'value');
    IF NOT FOUND THEN
      RAISE EXCEPTION 'litkb: identifier value does not normalise to identifier %', v_entity USING ERRCODE = '22023';
    END IF;
  END IF;

  EXECUTE format('SELECT coalesce(max(version_no), 0) + 1 FROM %s WHERE %I = $1', t.vers, t.fk)
    INTO v_no USING v_entity;
  v_version := uuidv7();
  v_merged := p_fields || jsonb_build_object(
    'version_id', v_version, t.fk, v_entity, 'version_no', v_no,
    'change_reason', p_change_reason, 'based_on_version_id', p_based_on,
    'workstream_id', p_workstream, 'agent', p_agent, 'session_id', p_session,
    'state', CASE p_mode WHEN 'fact' THEN 'promoted' ELSE 'proposed' END,
    'promoted_at', CASE p_mode WHEN 'fact' THEN now() END);
  SELECT string_agg(quote_ident(k), ', ') INTO v_cols FROM jsonb_object_keys(v_merged) k;
  EXECUTE format('INSERT INTO %s (%s) SELECT %s FROM jsonb_populate_record(NULL::%s, $1)',
                 t.vers, v_cols, v_cols, t.vers) USING v_merged;

  IF p_mode = 'fact' THEN
    EXECUTE format('UPDATE %s SET current_version_id = $1 WHERE id = $2 AND current_version_id IS NOT DISTINCT FROM $3', t.ident)
      USING v_version, v_entity, p_based_on;
    GET DIAGNOSTICS v_n = ROW_COUNT;
  ELSE
    PERFORM 1 FROM ws_heads h
     WHERE h.workstream_id = p_workstream AND h.entity = p_entity AND h.entity_id = v_entity
       FOR UPDATE;
    IF FOUND THEN
      UPDATE ws_heads h SET version_id = v_version
       WHERE h.workstream_id = p_workstream AND h.entity = p_entity AND h.entity_id = v_entity
         AND h.version_id = p_based_on;
    ELSE
      INSERT INTO ws_heads (workstream_id, entity, entity_id, version_id)
      SELECT p_workstream, p_entity, v_entity, v_version
       WHERE p_based_on IS NOT DISTINCT FROM v_main;
    END IF;
    GET DIAGNOSTICS v_n = ROW_COUNT;
  END IF;
  IF v_n <> 1 THEN
    RAISE EXCEPTION 'litkb CAS refused: % % is no longer at version % in this view; re-read and redo the change',
      p_entity, v_entity, coalesce(p_based_on::text, '(none)') USING ERRCODE = '40001';
  END IF;

  IF p_mode = 'fact' THEN
    PERFORM _refresh_mirrors(p_entity, v_entity);
  END IF;
  entity_id := v_entity;
  version_id := v_version;
END
$$;

-- files.current_run_id, compare-and-set (§4.4). D-5: the new run must exist, be this file's,
-- and have status 'ok' — a failed run, another file's run, or NULL is refused (the composite
-- FK files_current_run_fk remains as the second lock on "this file's").
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
END
$$;

-- §4.5: quote_verified is whether the block's text at [char_start, char_end) equals the quote
-- exactly. Overwritten unconditionally, so a client-supplied value cannot survive.
-- D-7: an offset range that runs past the text is refused outright (substring would truncate
-- it and let a whole-text quote verify).
CREATE OR REPLACE FUNCTION litkb._use_evidence_verify() RETURNS trigger
LANGUAGE plpgsql SET search_path = litkb, public, pg_temp AS $$
DECLARE
  b record;
BEGIN
  SELECT bl.text, bl.run_id INTO b FROM blocks bl WHERE bl.id = NEW.block_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: evidence block % does not exist', NEW.block_id USING ERRCODE = '23503';
  END IF;
  IF NEW.run_id IS DISTINCT FROM b.run_id THEN
    RAISE EXCEPTION 'litkb: evidence run % is not the run of block %', NEW.run_id, NEW.block_id USING ERRCODE = '23514';
  END IF;
  -- BEGIN guard: char_end within the block text
  IF NEW.char_end > length(b.text) THEN
    RAISE EXCEPTION 'litkb: evidence char_end % is beyond the % characters of block %',
      NEW.char_end, length(b.text), NEW.block_id USING ERRCODE = '23514';
  END IF;
  -- END guard: char_end within the block text
  NEW.quote_verified := coalesce(
    substring(b.text FROM NEW.char_start + 1 FOR NEW.char_end - NEW.char_start) = NEW.quote, false);
  RETURN NEW;
END
$$;

-- D-5: the one way an agent adds evidence. "Ownership" is the workstream the use version was
-- written in (workstreams carry no owner column): the caller names its workstream and the
-- version must belong to it.
CREATE FUNCTION litkb.add_evidence(
  p_workstream uuid, p_use_version uuid, p_block uuid, p_run uuid, p_page integer,
  p_quote text, p_char_start integer, p_char_end integer, p_stance text,
  OUT evidence_id uuid, OUT verified boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v record;
BEGIN
  -- BEGIN guard: evidence workstream open
  PERFORM 1 FROM workstreams ws WHERE ws.id = p_workstream AND ws.state = 'open' FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % is not open', p_workstream USING ERRCODE = '22023';
  END IF;
  -- END guard: evidence workstream open
  SELECT uv.workstream_id AS ws, uv.state AS st INTO v FROM use_versions uv WHERE uv.version_id = p_use_version;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: no use version %', p_use_version USING ERRCODE = 'P0002';
  END IF;
  -- BEGIN guard: evidence version belongs to the workstream
  IF v.ws IS DISTINCT FROM p_workstream THEN
    RAISE EXCEPTION 'litkb: use version % belongs to another workstream', p_use_version USING ERRCODE = '42501';
  END IF;
  -- END guard: evidence version belongs to the workstream
  -- BEGIN guard: evidence version is proposed
  IF v.st IS DISTINCT FROM 'proposed' THEN
    RAISE EXCEPTION 'litkb: use version % is %, evidence is added only to a proposed version', p_use_version, v.st
      USING ERRCODE = '55000';
  END IF;
  -- END guard: evidence version is proposed
  -- BEGIN guard: no evidence while a promotion is prepared
  PERFORM 1 FROM promotions pr WHERE pr.workstream_id = p_workstream AND pr.state = 'prepared';
  IF FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % has a prepared promotion; commit or abandon it before adding evidence', p_workstream
      USING ERRCODE = '55000';
  END IF;
  -- END guard: no evidence while a promotion is prepared
  INSERT INTO use_evidence (use_version_id, block_id, run_id, page, quote, char_start, char_end, stance)
  VALUES (p_use_version, p_block, p_run, p_page, p_quote, p_char_start, p_char_end, p_stance)
  RETURNING id, quote_verified INTO evidence_id, verified;
END
$$;

REVOKE EXECUTE ON FUNCTION
  litkb.add_evidence(uuid, uuid, uuid, uuid, integer, text, integer, integer, text)
FROM PUBLIC;

-- BEGIN guard: writer has no direct evidence INSERT
REVOKE INSERT ON litkb.use_evidence FROM litkb_writer;
-- END guard: writer has no direct evidence INSERT

GRANT EXECUTE ON FUNCTION
  litkb.add_evidence(uuid, uuid, uuid, uuid, integer, text, integer, integer, text)
TO litkb_writer;

-- end of 0007
