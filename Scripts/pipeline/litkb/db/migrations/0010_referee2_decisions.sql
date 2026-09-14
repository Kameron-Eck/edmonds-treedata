-- litkb 0010 — Kam's decisions after the second P1 referee (decisions.yaml litkb-p0-foundation,
-- "After the second P1 referee"; Reports/LITKB_P1_REFEREE2_2026-09-13.md E-5 and residual gaps 1-2).
-- Applied migrations are checksum-locked, so this file REPLACES functions defined earlier. The live
-- definitions of promote_rebase (0008), add_evidence (0007), write_fact, write_proposal,
-- open_workstream and abandon_workstream (0003) are the ones below; the earlier bodies are history,
-- and a mutation of them is dead code.
--
--   E-5    promote_rebase copies ONLY the evidence attached to the held chain's head version, which
--          is exactly what promotion would carry: on the promote path main's current version is the
--          head, and use_evidence_status is keyed by use_version_id, so rows on earlier chain
--          versions never reach main. Every copied column is the source's; quote_verified is not
--          copied, the trigger recomputes it.
--   token  open_workstream returns a secret token ONCE. Only its sha256 is stored, in
--          workstream_tokens, which no agent role can read. write_fact, write_proposal,
--          add_evidence and abandon_workstream take the token and refuse (42501) inside the
--          SECURITY DEFINER function when it does not hash to the named workstream's. The old
--          token-less signatures are DROPPED: a CREATE with an added parameter would otherwise
--          leave the old overload callable. Promotion functions take no token (the promoter acts
--          on every workstream); the owner-only _write_version takes none either.
--   ingest a new role litkb_ingest owns INSERT on the extraction tables (extraction_runs,
--          file_checks and the derived text tables) and EXECUTE on set_current_run. The writer
--          loses both: it could otherwise install an ok run and make it current (un-promoting
--          that file's evidence), or insert a block whose text matches any quote.

SET LOCAL search_path = litkb, public;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'litkb_ingest') THEN
    RAISE EXCEPTION 'litkb: role litkb_ingest does not exist; run py -3.12 -m litkb.db.provision as postgres first';
  END IF;
END
$$;

-- ── ingest role ──────────────────────────────────────────────────────────────────────────
GRANT USAGE ON SCHEMA litkb TO litkb_ingest;
GRANT SELECT ON ALL TABLES IN SCHEMA litkb TO litkb_ingest;
GRANT EXECUTE ON FUNCTION litkb.norm_identifier(text, text) TO litkb_ingest;

-- BEGIN guard: writer has no INSERT on extraction tables
REVOKE INSERT ON litkb.extraction_runs, litkb.file_checks, litkb.pages, litkb.blocks, litkb.tables,
  litkb.figures, litkb.equations, litkb."references", litkb.citation_mentions, litkb.chunks,
  litkb.embeddings FROM litkb_writer;
-- END guard: writer has no INSERT on extraction tables
-- BEGIN guard: writer cannot move a file's current run
REVOKE EXECUTE ON FUNCTION litkb.set_current_run(uuid, uuid, uuid) FROM litkb_writer;
-- END guard: writer cannot move a file's current run
-- BEGIN guard: ingest inserts extraction tables
GRANT INSERT ON litkb.extraction_runs, litkb.file_checks, litkb.pages, litkb.blocks, litkb.tables,
  litkb.figures, litkb.equations, litkb."references", litkb.citation_mentions, litkb.chunks,
  litkb.embeddings TO litkb_ingest;
-- END guard: ingest inserts extraction tables
-- BEGIN guard: ingest moves a file's current run
GRANT EXECUTE ON FUNCTION litkb.set_current_run(uuid, uuid, uuid) TO litkb_ingest;
-- END guard: ingest moves a file's current run

-- ── workstream tokens ────────────────────────────────────────────────────────────────────
CREATE TABLE workstream_tokens (
  workstream_id uuid PRIMARY KEY REFERENCES workstreams (id),
  token_hash    text NOT NULL CHECK (token_hash ~ '^[0-9a-f]{64}$')
);
-- BEGIN guard: no agent role reads token hashes
REVOKE ALL ON litkb.workstream_tokens FROM PUBLIC, litkb_reader, litkb_writer, litkb_promoter, litkb_ingest;
-- END guard: no agent role reads token hashes

CREATE FUNCTION litkb._require_ws_token(p_ws uuid, p_token text) RETURNS void
LANGUAGE plpgsql STABLE SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_ok boolean;
BEGIN
  v_ok := (SELECT t.token_hash = encode(sha256(convert_to(p_token, 'UTF8')), 'hex')
             FROM workstream_tokens t WHERE t.workstream_id = p_ws);
  -- a NULL token, or a workstream without a token row, leaves v_ok NULL; NOT NULL is NULL and an
  -- IF on NULL does not raise, so NULL must count as refused
  IF NOT coalesce(v_ok, false) THEN
    -- the message names the workstream, never the token
    RAISE EXCEPTION 'litkb: workstream token refused for workstream %', p_ws USING ERRCODE = '42501';
  END IF;
END
$$;
REVOKE EXECUTE ON FUNCTION litkb._require_ws_token(uuid, text) FROM PUBLIC;

-- BEGIN guard: old token-less signatures are dropped
DROP FUNCTION litkb.open_workstream(text, text, text, text, text);
DROP FUNCTION litkb.abandon_workstream(uuid);
DROP FUNCTION litkb.write_fact(text, uuid, uuid, jsonb, text, uuid, text, text);
DROP FUNCTION litkb.write_proposal(text, uuid, jsonb, uuid, jsonb, text, uuid, text, text);
DROP FUNCTION litkb.add_evidence(uuid, uuid, uuid, uuid, integer, text, integer, integer, text);
-- END guard: old token-less signatures are dropped

CREATE FUNCTION litkb.open_workstream(p_slug text, p_git_branch text, p_worktree_path text,
                                      p_purpose text, p_brief_path text,
                                      OUT workstream_id uuid, OUT token text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
BEGIN
  -- 64 hex characters from two server-generated random UUIDs (122 random bits each)
  token := replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '');
  INSERT INTO workstreams (slug, git_branch, worktree_path, purpose, brief_path)
  VALUES (p_slug, p_git_branch, p_worktree_path, p_purpose, p_brief_path)
  RETURNING id INTO workstream_id;
  INSERT INTO workstream_tokens (workstream_id, token_hash)
  VALUES (workstream_id, encode(sha256(convert_to(token, 'UTF8')), 'hex'));
END
$$;

CREATE FUNCTION litkb.abandon_workstream(p_workstream uuid, p_ws_token text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
BEGIN
  -- BEGIN guard: abandon_workstream presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: abandon_workstream presents the workstream token
  UPDATE workstreams w SET state = 'abandoned', closed_at = now()
   WHERE w.id = p_workstream AND w.state = 'open';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % is not open', p_workstream USING ERRCODE = '22023';
  END IF;
END
$$;

-- Correct an existing fact (work, identifier, file) against main's pointer. New facts enter
-- only through admission (P2), which runs checks 1-4 first.
CREATE FUNCTION litkb.write_fact(
  p_entity text, p_entity_id uuid, p_based_on uuid, p_fields jsonb, p_change_reason text,
  p_workstream uuid, p_ws_token text, p_agent text, p_session text,
  OUT entity_id uuid, OUT version_id uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
BEGIN
  -- BEGIN guard: write_fact presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: write_fact presents the workstream token
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
  p_change_reason text, p_workstream uuid, p_ws_token text, p_agent text, p_session text,
  OUT entity_id uuid, OUT version_id uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
BEGIN
  -- BEGIN guard: write_proposal presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: write_proposal presents the workstream token
  IF p_entity IS NULL OR p_entity NOT IN ('gap', 'use') THEN
    RAISE EXCEPTION 'litkb: write_proposal takes gap or use (got %)', p_entity USING ERRCODE = '22023';
  END IF;
  SELECT w.entity_id, w.version_id INTO entity_id, version_id
    FROM _write_version('proposal', p_entity, p_entity_id, p_identity, p_based_on, p_fields,
                        p_change_reason, p_workstream, p_agent, p_session) w;
END
$$;

-- D-5 (0007) plus the token: the one way an agent adds evidence. "Ownership" is the workstream the
-- use version was written in; the caller names that workstream and presents its token.
CREATE FUNCTION litkb.add_evidence(
  p_workstream uuid, p_ws_token text, p_use_version uuid, p_block uuid, p_run uuid, p_page integer,
  p_quote text, p_char_start integer, p_char_end integer, p_stance text,
  OUT evidence_id uuid, OUT verified boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v record;
BEGIN
  -- BEGIN guard: add_evidence presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: add_evidence presents the workstream token
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
  litkb.open_workstream(text, text, text, text, text),
  litkb.abandon_workstream(uuid, text),
  litkb.write_fact(text, uuid, uuid, jsonb, text, uuid, text, text, text),
  litkb.write_proposal(text, uuid, jsonb, uuid, jsonb, text, uuid, text, text, text),
  litkb.add_evidence(uuid, text, uuid, uuid, uuid, integer, text, integer, integer, text)
FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
  litkb.open_workstream(text, text, text, text, text),
  litkb.abandon_workstream(uuid, text),
  litkb.write_fact(text, uuid, uuid, jsonb, text, uuid, text, text, text),
  litkb.write_proposal(text, uuid, jsonb, uuid, jsonb, text, uuid, text, text, text),
  litkb.add_evidence(uuid, text, uuid, uuid, uuid, integer, text, integer, integer, text)
TO litkb_writer;

-- ── E-5: promote_rebase, head evidence only ──────────────────────────────────────────────
-- p_onto: {"<entity>:<entity_id>": "<main's current version_id, or null>"} naming EVERY chain
-- the source workstream still holds — the main version the caller reviewed the rebase against.
CREATE OR REPLACE FUNCTION litkb.promote_rebase(p_source_ws uuid, p_target_ws uuid, p_onto jsonb,
                                                p_agent text, p_session text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  c record;
  t record;
  k text;
  v_keys text[];
  v_main uuid;
  v_onto uuid;
  v_pid uuid;
  v_no integer;
  v_new uuid;
  v_cols text;
  v_reason text;
  v_head_reason text;
  v_ev integer;
  v_out jsonb := '[]'::jsonb;
BEGIN
  IF p_onto IS NULL OR jsonb_typeof(p_onto) <> 'object' THEN
    RAISE EXCEPTION 'litkb: onto must be a JSON object of chain -> main version' USING ERRCODE = '22023';
  END IF;
  -- BEGIN guard: rebase source is merged
  PERFORM 1 FROM workstreams w WHERE w.id = p_source_ws AND w.state = 'merged' FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % is not merged; only chains a merged workstream still holds are rebased', p_source_ws
      USING ERRCODE = '22023';
  END IF;
  -- END guard: rebase source is merged
  -- BEGIN guard: rebase target is open
  PERFORM 1 FROM workstreams w WHERE w.id = p_target_ws AND w.state = 'open' FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: target workstream % is not open', p_target_ws USING ERRCODE = '22023';
  END IF;
  -- END guard: rebase target is open
  -- BEGIN guard: rebase target has no prepared promotion
  PERFORM 1 FROM promotions pr WHERE pr.workstream_id = p_target_ws AND pr.state = 'prepared';
  IF FOUND THEN
    RAISE EXCEPTION 'litkb: target workstream % has a prepared promotion; commit or abandon it first', p_target_ws
      USING ERRCODE = '55000';
  END IF;
  -- END guard: rebase target has no prepared promotion

  SELECT array_agg(x.entity || ':' || x.entity_id ORDER BY x.entity || ':' || x.entity_id) INTO v_keys
    FROM _ws_chains(p_source_ws) x;
  IF v_keys IS NULL THEN
    RAISE EXCEPTION 'litkb: workstream % holds no chain to rebase', p_source_ws USING ERRCODE = '22023';
  END IF;
  IF (SELECT array_agg(j ORDER BY j) FROM jsonb_object_keys(p_onto) j) IS DISTINCT FROM v_keys THEN
    RAISE EXCEPTION 'litkb: onto must name exactly the held chains %', v_keys USING ERRCODE = '22023';
  END IF;
  SELECT pr.id INTO v_pid FROM promotions pr
   WHERE pr.workstream_id = p_source_ws AND pr.state = 'committed' ORDER BY pr.committed_at DESC LIMIT 1;

  FOR c IN SELECT * FROM _ws_chains(p_source_ws) ORDER BY entity, entity_id LOOP
    k := c.entity || ':' || c.entity_id;
    SELECT * INTO t FROM _entity_tables(c.entity);
    v_onto := (p_onto->>k)::uuid;
    EXECUTE format('SELECT current_version_id FROM %s WHERE id = $1 FOR UPDATE', t.ident)
      INTO v_main USING c.entity_id;
    -- BEGIN guard: rebase onto main's current version
    IF v_main IS DISTINCT FROM v_onto THEN
      RAISE EXCEPTION 'litkb CAS refused: main''s % % is at %, not %; re-read main and review the rebase again',
        c.entity, c.entity_id, coalesce(v_main::text, '(none)'), coalesce(v_onto::text, '(none)')
        USING ERRCODE = '40001';
    END IF;
    -- END guard: rebase onto main's current version
    -- BEGIN guard: rebase target has no head for the entity
    PERFORM 1 FROM ws_heads h WHERE h.workstream_id = p_target_ws AND h.entity = c.entity AND h.entity_id = c.entity_id;
    IF FOUND THEN
      RAISE EXCEPTION 'litkb: target workstream % already has a chain for % %', p_target_ws, c.entity, c.entity_id
        USING ERRCODE = '22023';
    END IF;
    -- END guard: rebase target has no head for the entity

    EXECUTE format('SELECT coalesce(max(version_no), 0) + 1 FROM %s WHERE %I = $1', t.vers, t.fk)
      INTO v_no USING c.entity_id;
    EXECUTE format('SELECT change_reason FROM %s WHERE version_id = $1', t.vers) INTO v_head_reason USING c.head;
    v_reason := format('rebase of %s (workstream %s, held at promotion %s) onto %s', c.head, p_source_ws,
                       coalesce(v_pid::text, '(none)'), coalesce(v_onto::text, '(nothing)'))
                || coalesce(': ' || nullif(btrim(v_head_reason), ''), '');
    v_new := uuidv7();
    -- the head's content columns, copied verbatim; every controlled column is set here
    SELECT string_agg(quote_ident(a.attname), ', ' ORDER BY a.attnum) INTO v_cols
      FROM pg_attribute a
     WHERE a.attrelid = t.vers AND a.attnum > 0 AND NOT a.attisdropped
       AND a.attname NOT IN ('version_id', 'version_no', 'change_reason', 'based_on_version_id',
                             'workstream_id', 'agent', 'session_id', 'created_at', 'state',
                             'promoted_at', 'promotion_id', 'rebased_from_version_id');
    EXECUTE format('INSERT INTO %s (%s, version_id, version_no, change_reason, based_on_version_id, '
                   'workstream_id, agent, session_id, state, rebased_from_version_id) '
                   'SELECT %s, $1, $2, $3, $4, $5, $6, $7, ''proposed'', version_id FROM %s WHERE version_id = $8',
                   t.vers, v_cols, v_cols, t.vers)
      USING v_new, v_no, v_reason, v_onto, p_target_ws, p_agent, p_session, c.head;
    INSERT INTO ws_heads (workstream_id, entity, entity_id, version_id)
    VALUES (p_target_ws, c.entity, c.entity_id, v_new);

    v_ev := 0;
    -- BEGIN guard: rebase carries evidence
    IF c.entity = 'use' THEN
      -- E-5: the HEAD's evidence only, as promotion carries it; every column is the source's, and
      -- quote_verified is left to the trigger
      INSERT INTO use_evidence (use_version_id, block_id, run_id, page, quote, char_start, char_end, stance)
      SELECT v_new, e.block_id, e.run_id, e.page, e.quote, e.char_start, e.char_end, e.stance
        FROM use_evidence e WHERE e.use_version_id = c.head ORDER BY e.id;
      GET DIAGNOSTICS v_ev = ROW_COUNT;
    END IF;
    -- END guard: rebase carries evidence

    -- BEGIN guard: rebased originals are marked
    EXECUTE format('UPDATE %s SET state = ''rebased'' WHERE version_id = ANY ($1)', t.vers)
      USING c.version_ids;
    -- END guard: rebased originals are marked
    -- BEGIN guard: held chain leaves the source workstream
    DELETE FROM ws_heads h
     WHERE h.workstream_id = p_source_ws AND h.entity = c.entity AND h.entity_id = c.entity_id;
    -- END guard: held chain leaves the source workstream

    INSERT INTO rebases (source_workstream_id, target_workstream_id, held_in_promotion_id, entity, entity_id,
                         old_head_version_id, old_version_ids, old_base_version_id, onto_version_id,
                         new_version_id, evidence_copied, agent, session_id)
    VALUES (p_source_ws, p_target_ws, v_pid, c.entity, c.entity_id, c.head, c.version_ids, c.base, v_onto,
            v_new, v_ev, p_agent, p_session);
    v_out := v_out || jsonb_build_array(jsonb_build_object(
      'chain', k, 'old_head', c.head, 'onto', v_onto, 'new_version', v_new, 'evidence_copied', v_ev));
  END LOOP;
  RETURN jsonb_build_object('source', p_source_ws, 'target', p_target_ws, 'rebased', jsonb_array_length(v_out),
                            'chains', v_out);
END
$$;

-- end of 0010
