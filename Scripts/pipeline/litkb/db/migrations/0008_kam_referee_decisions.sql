-- litkb 0008 — Kam's decisions on the P1 referee findings (decisions.yaml litkb-p0-foundation,
-- "After the P1 referee"; Reports/LITKB_P1_REFEREE_2026-09-13.md D-2, D-3, D-4).
-- Applied migrations are checksum-locked, so this file REPLACES the admissions constraint of
-- 0001 rather than editing it there; 0001's constraint text (and its comment "the database
-- refuses admitter = approver") is history.
--
--   D-2  promote_rebase(): the chains a merged workstream still holds (held at prepare or at
--        commit) are copied, one new version per chain, into a fresh open workstream, based on
--        main's CURRENT version as the caller names it (compare-and-set: a stale name is
--        refused, 40001). Each new version carries rebased_from_version_id = the old head; the
--        old chain versions are marked state 'rebased' (superseded by rebase), never deleted;
--        evidence rows are copied onto the new version (the trigger re-verifies each quote);
--        every rebase is recorded in litkb.rebases. EXECUTE: litkb_promoter (and the owner).
--   D-3  the database cannot run git; the promote TOOL refuses a merge that is not on main.
--        Enforced here: reader and writer hold no EXECUTE on any promotion function (tested).
--   D-4  a manual admission's approver needs only a different SESSION; agent names are
--        client-supplied labels, so the same name in another session is allowed.

SET LOCAL search_path = litkb, public;

-- ── D-4 ──────────────────────────────────────────────────────────────────────────────────
ALTER TABLE admissions DROP CONSTRAINT admissions_second_agent_signs_off;
ALTER TABLE admissions ADD CONSTRAINT admissions_second_session_signs_off CHECK (
  (approver_agent IS NULL AND approver_session IS NULL AND approved_at IS NULL)
  OR (approver_agent IS NOT NULL AND approver_session IS NOT NULL AND approved_at IS NOT NULL
      AND approver_session <> admitter_session));

-- ── D-2: schema ──────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
  v_table text;
  v_fk text;
BEGIN
  FOR v_table, v_fk IN VALUES ('work_versions', 'work_id'), ('identifier_versions', 'identifier_id'),
                              ('file_versions', 'file_id'), ('gap_versions', 'gap_id'),
                              ('use_versions', 'use_id') LOOP
    EXECUTE format('ALTER TABLE litkb.%I ADD COLUMN rebased_from_version_id uuid', v_table);
    EXECUTE format('ALTER TABLE litkb.%I ADD CONSTRAINT %I FOREIGN KEY (%I, rebased_from_version_id) '
                   'REFERENCES litkb.%I (%I, version_id)',
                   v_table, v_table || '_rebased_from_fk', v_fk, v_table, v_fk);
    EXECUTE format('ALTER TABLE litkb.%I DROP CONSTRAINT %I', v_table, v_table || '_state_check');
    EXECUTE format('ALTER TABLE litkb.%I ADD CONSTRAINT %I CHECK (state IN '
                   '(''proposed'', ''prepared'', ''promoted'', ''rejected'', ''withdrawn'', ''rebased''))',
                   v_table, v_table || '_state_check');
    -- a rebased copy is never version 1 and may sit on NO base (a chain that creates its
    -- entity has none: main's pointer is still NULL); it still needs a change_reason
    EXECUTE format('ALTER TABLE litkb.%I DROP CONSTRAINT %I', v_table, v_table || '_base_rule');
    EXECUTE format('ALTER TABLE litkb.%I ADD CONSTRAINT %I CHECK ('
                   'CASE WHEN version_no = 1 THEN based_on_version_id IS NULL AND rebased_from_version_id IS NULL '
                   '     WHEN rebased_from_version_id IS NOT NULL THEN coalesce(btrim(change_reason), '''') <> '''' '
                   '     ELSE based_on_version_id IS NOT NULL AND coalesce(btrim(change_reason), '''') <> '''' END)',
                   v_table, v_table || '_base_rule');
  END LOOP;
END
$$;

CREATE TABLE rebases (
  id                   uuid PRIMARY KEY DEFAULT uuidv7(),
  source_workstream_id uuid NOT NULL REFERENCES workstreams (id),
  target_workstream_id uuid NOT NULL REFERENCES workstreams (id),
  held_in_promotion_id uuid REFERENCES promotions (id),
  entity               text NOT NULL CHECK (entity IN ('work', 'identifier', 'file', 'gap', 'use')),
  entity_id            uuid NOT NULL,
  old_head_version_id  uuid NOT NULL,
  old_version_ids      uuid[] NOT NULL,
  old_base_version_id  uuid,
  onto_version_id      uuid,
  new_version_id       uuid NOT NULL,
  evidence_copied      integer NOT NULL DEFAULT 0,
  agent                text NOT NULL CHECK (agent <> ''),
  session_id           text NOT NULL CHECK (session_id <> ''),
  created_at           timestamptz NOT NULL DEFAULT now(),
  CHECK (source_workstream_id <> target_workstream_id)
);
GRANT SELECT ON litkb.rebases TO litkb_reader, litkb_writer, litkb_promoter;

-- ── D-2: the function ────────────────────────────────────────────────────────────────────
-- p_onto: {"<entity>:<entity_id>": "<main's current version_id, or null>"} naming EVERY chain
-- the source workstream still holds — the main version the caller reviewed the rebase against.
CREATE FUNCTION litkb.promote_rebase(p_source_ws uuid, p_target_ws uuid, p_onto jsonb,
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
      INSERT INTO use_evidence (use_version_id, block_id, run_id, page, quote, char_start, char_end, stance)
      SELECT v_new, e.block_id, e.run_id, e.page, e.quote, e.char_start, e.char_end, e.stance
        FROM use_evidence e WHERE e.use_version_id = ANY (c.version_ids) ORDER BY e.id;
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

REVOKE EXECUTE ON FUNCTION litkb.promote_rebase(uuid, uuid, jsonb, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION litkb.promote_rebase(uuid, uuid, jsonb, text, text) TO litkb_promoter;

-- end of 0008
