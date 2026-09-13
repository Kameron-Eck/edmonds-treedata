-- litkb 0003 — the write path: identifier normalisation, compare-and-set version writes,
-- workstream open/abandon, the current-run pointer, and the quote_verified trigger.
-- Design §4.1 (every write is compare-and-set, facts included), §4.4 (one current run per
-- file), §4.5 (quote_verified computed by the database), §4.6 check 2 (normalised identifiers).
--
-- Every function that moves a pointer or sets a state is SECURITY DEFINER with a pinned
-- search_path; agent roles hold no UPDATE privilege on any table (0006).

SET LOCAL search_path = litkb, public;

CREATE FUNCTION litkb.norm_identifier(p_scheme text, p_value text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
  SELECT CASE p_scheme
    -- DOIs lowercased, https://doi.org/ or doi: prefix stripped (§4.6 check 2)
    WHEN 'doi'   THEN regexp_replace(lower(btrim(p_value)), '^(https?://(dx\.)?doi\.org/|doi:)', '')
    -- arXiv ids with the version suffix stripped (§4.6 check 2)
    WHEN 'arxiv' THEN regexp_replace(regexp_replace(lower(btrim(p_value)), '^arxiv:', ''), 'v[0-9]+$', '')
    ELSE btrim(p_value)
  END
$$;

CREATE FUNCTION litkb._entity_tables(p_entity text, OUT ident regclass, OUT vers regclass, OUT fk text)
LANGUAGE plpgsql STABLE SET search_path = litkb, public, pg_temp AS $$
BEGIN
  CASE p_entity
    WHEN 'work'       THEN ident := 'litkb.works';       vers := 'litkb.work_versions';       fk := 'work_id';
    WHEN 'identifier' THEN ident := 'litkb.identifiers'; vers := 'litkb.identifier_versions'; fk := 'identifier_id';
    WHEN 'file'       THEN ident := 'litkb.files';       vers := 'litkb.file_versions';       fk := 'file_id';
    WHEN 'gap'        THEN ident := 'litkb.gaps';        vers := 'litkb.gap_versions';        fk := 'gap_id';
    WHEN 'use'        THEN ident := 'litkb.uses';        vers := 'litkb.use_versions';        fk := 'use_id';
    ELSE RAISE EXCEPTION 'litkb: unknown entity %', p_entity USING ERRCODE = '22023';
  END CASE;
END
$$;

-- identifiers.active mirrors main's current version; the only writer of that column.
CREATE FUNCTION litkb._refresh_mirrors(p_entity text, p_id uuid) RETURNS void
LANGUAGE plpgsql SET search_path = litkb, public, pg_temp AS $$
BEGIN
  IF p_entity = 'identifier' THEN
    UPDATE identifiers i
       SET active = coalesce((SELECT v.status = 'active' FROM identifier_versions v
                               WHERE v.version_id = i.current_version_id), false)
     WHERE i.id = p_id;
  END IF;
END
$$;

CREATE FUNCTION litkb._create_identity(p_entity text, p_identity jsonb, p_fields jsonb, p_workstream uuid)
RETURNS uuid LANGUAGE plpgsql SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_id uuid;
  v_allowed text[];
  v_bad text[];
BEGIN
  v_allowed := CASE p_entity
    WHEN 'work' THEN ARRAY['key'] WHEN 'identifier' THEN ARRAY['scheme'] WHEN 'file' THEN ARRAY['sha256']
    WHEN 'gap' THEN ARRAY['slug'] WHEN 'use' THEN ARRAY['work_id', 'gap_id'] END;
  SELECT array_agg(k) INTO v_bad FROM jsonb_object_keys(coalesce(p_identity, '{}'::jsonb)) k
   WHERE NOT (k = ANY (v_allowed));
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'litkb: % identity takes only %, got %', p_entity, v_allowed, v_bad USING ERRCODE = '22023';
  END IF;
  CASE p_entity
    WHEN 'work' THEN
      INSERT INTO works (key, created_in_ws) VALUES (p_identity->>'key', p_workstream) RETURNING id INTO v_id;
    WHEN 'identifier' THEN
      INSERT INTO identifiers (scheme, value_norm, created_in_ws)
      VALUES (p_identity->>'scheme', norm_identifier(p_identity->>'scheme', p_fields->>'value'), p_workstream)
      RETURNING id INTO v_id;
    WHEN 'file' THEN
      INSERT INTO files (sha256, created_in_ws) VALUES (p_identity->>'sha256', p_workstream) RETURNING id INTO v_id;
    WHEN 'gap' THEN
      INSERT INTO gaps (slug, created_in_ws) VALUES (p_identity->>'slug', p_workstream) RETURNING id INTO v_id;
    WHEN 'use' THEN
      INSERT INTO uses (work_id, gap_id, created_in_ws)
      VALUES ((p_identity->>'work_id')::uuid, (p_identity->>'gap_id')::uuid, p_workstream) RETURNING id INTO v_id;
  END CASE;
  RETURN v_id;
END
$$;

-- The one version writer. Not granted to any agent role: agents call write_fact /
-- write_proposal; admission (P2) will create facts through it.
--   fact mode:     compare-and-set main's pointer (identity.current_version_id)
--   proposal mode: compare-and-set the workstream's head (ws_heads), whose base when absent
--                  is main's pointer
-- A stale base rolls the whole call back with SQLSTATE 40001: nobody's version is overwritten.
CREATE FUNCTION litkb._write_version(
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
  PERFORM 1 FROM workstreams w WHERE w.id = p_workstream AND w.state = 'open';
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

  -- serialise all writers of this entity
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

-- Correct an existing fact (work, identifier, file) against main's pointer. New facts enter
-- only through admission (P2), which runs checks 1-4 first.
CREATE FUNCTION litkb.write_fact(
  p_entity text, p_entity_id uuid, p_based_on uuid, p_fields jsonb, p_change_reason text,
  p_workstream uuid, p_agent text, p_session text, OUT entity_id uuid, OUT version_id uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
BEGIN
  IF p_entity IS NULL OR p_entity NOT IN ('work', 'identifier', 'file') THEN
    RAISE EXCEPTION 'litkb: write_fact takes work, identifier or file (got %); gaps and uses are proposals', p_entity
      USING ERRCODE = '22023';
  END IF;
  IF p_entity_id IS NULL THEN
    RAISE EXCEPTION 'litkb: new facts enter only through admission; write_fact corrects an existing one'
      USING ERRCODE = '42501';
  END IF;
  SELECT w.entity_id, w.version_id INTO entity_id, version_id
    FROM _write_version('fact', p_entity, p_entity_id, NULL, p_based_on, p_fields, p_change_reason,
                        p_workstream, p_agent, p_session) w;
END
$$;

-- Record a proposal (gap or use) in a workstream's view. p_entity_id NULL creates the entity,
-- with p_identity naming its immutable fields ({"slug"} for a gap, {"work_id","gap_id"} for a use).
CREATE FUNCTION litkb.write_proposal(
  p_entity text, p_entity_id uuid, p_identity jsonb, p_based_on uuid, p_fields jsonb,
  p_change_reason text, p_workstream uuid, p_agent text, p_session text,
  OUT entity_id uuid, OUT version_id uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
BEGIN
  IF p_entity IS NULL OR p_entity NOT IN ('gap', 'use') THEN
    RAISE EXCEPTION 'litkb: write_proposal takes gap or use (got %)', p_entity USING ERRCODE = '22023';
  END IF;
  SELECT w.entity_id, w.version_id INTO entity_id, version_id
    FROM _write_version('proposal', p_entity, p_entity_id, p_identity, p_based_on, p_fields,
                        p_change_reason, p_workstream, p_agent, p_session) w;
END
$$;

CREATE FUNCTION litkb.open_workstream(p_slug text, p_git_branch text, p_worktree_path text,
                                      p_purpose text, p_brief_path text)
RETURNS uuid LANGUAGE sql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
  INSERT INTO workstreams (slug, git_branch, worktree_path, purpose, brief_path)
  VALUES (p_slug, p_git_branch, p_worktree_path, p_purpose, p_brief_path)
  RETURNING id
$$;

CREATE FUNCTION litkb.abandon_workstream(p_workstream uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
BEGIN
  UPDATE workstreams w SET state = 'abandoned', closed_at = now()
   WHERE w.id = p_workstream AND w.state = 'open';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % is not open', p_workstream USING ERRCODE = '22023';
  END IF;
END
$$;

-- files.current_run_id, compare-and-set (§4.4). The composite FK guarantees the run is this file's.
CREATE FUNCTION litkb.set_current_run(p_file uuid, p_expected_run uuid, p_new_run uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_n bigint;
BEGIN
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
CREATE FUNCTION litkb._use_evidence_verify() RETURNS trigger
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
  NEW.quote_verified := coalesce(
    substring(b.text FROM NEW.char_start + 1 FOR NEW.char_end - NEW.char_start) = NEW.quote, false);
  RETURN NEW;
END
$$;

-- BEGIN guard: quote_verified trigger
CREATE TRIGGER use_evidence_verify_quote BEFORE INSERT OR UPDATE ON use_evidence
  FOR EACH ROW EXECUTE FUNCTION _use_evidence_verify();
-- END guard: quote_verified trigger
