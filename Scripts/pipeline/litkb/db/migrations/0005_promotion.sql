-- litkb 0005 — promotion: promote_prepare(), promote_commit(), promote_abandon().
-- Design §5. The git rule (merge commit reachable from main; prepared commit an ancestor of
-- the merge) is checked by litkb.promote before promote_commit is called — the database
-- cannot run git. Everything below is enforced here.
--
-- A CHAIN is one entity's versions in the workstream, walked from its ws_heads head back
-- through based_on_version_id while the versions belong to this workstream and are still
-- proposed or prepared. Its BASE is where the walk stops (a version outside the chain, or
-- nothing). A chain is promotable only if its base is still main's pointer, its checks
-- pass, and every chain it depends on is promotable — all or nothing, per chain.

SET LOCAL search_path = litkb, public;

-- feeds tokens: the forms §4.5 names (`framework §N`, `gap row N`, `decision <slug>`).
CREATE FUNCTION litkb._feeds_token_ok(p_token text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT coalesce(p_token ~ '^(framework §[0-9]+(\.[0-9]+)*|gap row [0-9]+|decision [a-z0-9][a-z0-9-]*)$', false)
$$;

CREATE FUNCTION litkb._ws_chains(p_ws uuid)
RETURNS TABLE (entity text, entity_id uuid, head uuid, base uuid, conflict boolean,
               version_ids uuid[], states text[], promotion_ids uuid[], evidence_ids uuid[],
               deps text[], problems text[])
LANGUAGE plpgsql STABLE SET search_path = litkb, public, pg_temp AS $$
#variable_conflict use_column
DECLARE
  h record;
  t record;
  v record;
  v_cur uuid;
  v_ids uuid[];
  v_states text[];
  v_pids uuid[];
  v_main uuid;
  v_work uuid;
  v_gap uuid;
  v_probs text[];
  v_deps text[];
  v_ev uuid[];
  v_bad integer;
  v_bad_feeds text[];
BEGIN
  FOR h IN SELECT wh.entity AS e, wh.entity_id AS id, wh.version_id AS head_id
             FROM ws_heads wh WHERE wh.workstream_id = p_ws ORDER BY wh.entity, wh.entity_id LOOP
    SELECT * INTO t FROM _entity_tables(h.e);
    v_ids := '{}'; v_states := '{}'; v_pids := '{}'; v_probs := '{}'; v_deps := '{}'; v_ev := '{}';
    v_cur := h.head_id;
    LOOP
      EXIT WHEN v_cur IS NULL;
      EXECUTE format('SELECT based_on_version_id AS b, workstream_id AS w, state AS s, promotion_id AS p FROM %s WHERE version_id = $1', t.vers)
        INTO v USING v_cur;
      EXIT WHEN v.w IS DISTINCT FROM p_ws OR v.s IS NULL OR v.s NOT IN ('proposed', 'prepared');
      v_ids := array_prepend(v_cur, v_ids);
      v_states := array_prepend(v.s, v_states);
      v_pids := array_prepend(v.p, v_pids);
      v_cur := v.b;
    END LOOP;
    CONTINUE WHEN cardinality(v_ids) = 0;

    EXECUTE format('SELECT current_version_id FROM %s WHERE id = $1', t.ident) INTO v_main USING h.id;

    IF h.e = 'use' THEN
      SELECT u.work_id, u.gap_id INTO v_work, v_gap FROM uses u WHERE u.id = h.id;
      -- dependency: its work, admitted (visible in main) or in this promotion
      IF EXISTS (SELECT 1 FROM ws_heads x WHERE x.workstream_id = p_ws AND x.entity = 'work' AND x.entity_id = v_work) THEN
        v_deps := v_deps || ('work:' || v_work);
      ELSIF NOT EXISTS (SELECT 1 FROM works w WHERE w.id = v_work AND w.current_version_id IS NOT NULL) THEN
        v_probs := v_probs || 'dependency: the work is not admitted in main'::text;
      END IF;
      -- dependency: the gap version it points to, promoted or in this promotion
      IF v_gap IS NOT NULL THEN
        IF EXISTS (SELECT 1 FROM ws_heads x WHERE x.workstream_id = p_ws AND x.entity = 'gap' AND x.entity_id = v_gap) THEN
          v_deps := v_deps || ('gap:' || v_gap);
        ELSIF NOT EXISTS (SELECT 1 FROM gaps g WHERE g.id = v_gap AND g.current_version_id IS NOT NULL) THEN
          v_probs := v_probs || 'dependency: the gap is neither promoted nor in this promotion'::text;
        END IF;
      END IF;
      -- evidence: verified and anchored in its file's current run
      SELECT coalesce(array_agg(e.id ORDER BY e.id), '{}') INTO v_ev
        FROM use_evidence e WHERE e.use_version_id = ANY (v_ids);
      SELECT count(*) INTO v_bad FROM use_evidence_status s
       WHERE s.use_version_id = ANY (v_ids) AND NOT s.promotable;
      IF v_bad > 0 THEN
        v_probs := v_probs || format('evidence: %s row(s) unverified or anchored in a superseded run', v_bad);
      END IF;
      SELECT array_agg(DISTINCT f.tok) INTO v_bad_feeds
        FROM use_versions uv CROSS JOIN LATERAL unnest(uv.feeds) AS f(tok)
       WHERE uv.version_id = ANY (v_ids) AND NOT _feeds_token_ok(f.tok);
      IF v_bad_feeds IS NOT NULL THEN
        v_probs := v_probs || format('feeds: invalid tokens %s', v_bad_feeds);
      END IF;
    END IF;

    entity := h.e;
    entity_id := h.id;
    head := h.head_id;
    base := v_cur;
    conflict := v_cur IS DISTINCT FROM v_main;
    version_ids := v_ids;
    states := v_states;
    promotion_ids := v_pids;
    evidence_ids := v_ev;
    deps := v_deps;
    problems := v_probs;
    RETURN NEXT;
  END LOOP;
END
$$;

-- Identity of what is being promoted: every chain's entity, base, versions and evidence rows.
-- Independent of main's pointer, so a conflict elsewhere does not change it; any new
-- version or evidence in the workstream does.
CREATE FUNCTION litkb._version_set_hash(p_ws uuid) RETURNS text
LANGUAGE sql STABLE SET search_path = litkb, public, pg_temp AS $$
  SELECT encode(sha256(convert_to(coalesce(string_agg(
           c.entity || ':' || c.entity_id || ':' || coalesce(c.base::text, '-') || ':'
           || array_to_string(c.version_ids, ',') || ':' || array_to_string(c.evidence_ids, ','),
           E'\n' ORDER BY c.entity, c.entity_id), ''), 'UTF8')), 'hex')
    FROM _ws_chains(p_ws) c
$$;

CREATE FUNCTION litkb.promote_prepare(p_ws uuid, p_branch_head text, p_report_path text)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  c record;
  t record;
  k text;
  d text;
  v_pid uuid;
  v_status jsonb := '{}'::jsonb;
  v_changed boolean;
  v_conf jsonb := '[]'::jsonb;
  n_ok integer := 0;
  n_held integer := 0;
BEGIN
  PERFORM 1 FROM workstreams w WHERE w.id = p_ws AND w.state = 'open' FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % is not open', p_ws USING ERRCODE = '22023';
  END IF;
  INSERT INTO promotions (workstream_id, branch_head_commit, version_set_hash, report_path)
  VALUES (p_ws, p_branch_head, _version_set_hash(p_ws), p_report_path)
  RETURNING id INTO v_pid;

  FOR c IN SELECT * FROM _ws_chains(p_ws) LOOP
    k := c.entity || ':' || c.entity_id;
    v_status := v_status || jsonb_build_object(k, jsonb_build_object(
      'ok', NOT c.conflict AND cardinality(c.problems) = 0,
      'reasons', to_jsonb(c.problems || CASE WHEN c.conflict
                   THEN ARRAY['conflict: the chain is based on ' || coalesce(c.base::text, 'nothing')
                              || ', which is no longer main''s current version']
                   ELSE '{}'::text[] END),
      'deps', to_jsonb(c.deps),
      'versions', to_jsonb(c.version_ids)));
  END LOOP;

  -- hold every chain that depends on a held (or absent) chain, to a fixpoint
  LOOP
    v_changed := false;
    -- BEGIN guard: dependency hold (prepare)
    FOR k IN SELECT jsonb_object_keys(v_status) LOOP
      CONTINUE WHEN NOT (v_status->k->>'ok')::boolean;
      FOR d IN SELECT jsonb_array_elements_text(v_status->k->'deps') LOOP
        IF NOT coalesce((v_status->d->>'ok')::boolean, false) THEN
          v_status := jsonb_set(v_status, ARRAY[k, 'ok'], 'false'::jsonb);
          v_status := jsonb_set(v_status, ARRAY[k, 'reasons'],
                                (v_status->k->'reasons') || to_jsonb('dependency held: ' || d));
          v_changed := true;
          EXIT;
        END IF;
      END LOOP;
    END LOOP;
    -- END guard: dependency hold (prepare)
    EXIT WHEN NOT v_changed;
  END LOOP;

  FOR k IN SELECT jsonb_object_keys(v_status) ORDER BY 1 LOOP
    IF (v_status->k->>'ok')::boolean THEN
      SELECT * INTO t FROM _entity_tables(split_part(k, ':', 1));
      EXECUTE format('UPDATE %s SET state = ''prepared'', promotion_id = $1 WHERE version_id = ANY ($2)', t.vers)
        USING v_pid, ARRAY(SELECT jsonb_array_elements_text(v_status->k->'versions'))::uuid[];
      n_ok := n_ok + 1;
    ELSE
      v_conf := v_conf || jsonb_build_array(jsonb_build_object('chain', k, 'reasons', v_status->k->'reasons'));
      n_held := n_held + 1;
    END IF;
  END LOOP;

  -- flag (not hold) near-duplicate uses: another use of the same work and gap exists
  FOR c IN SELECT u.id AS use_id, o.id AS other_id
             FROM ws_heads wh
             JOIN uses u ON wh.entity = 'use' AND u.id = wh.entity_id
             JOIN uses o ON o.work_id = u.work_id AND o.gap_id IS NOT DISTINCT FROM u.gap_id AND o.id <> u.id
            WHERE wh.workstream_id = p_ws
            ORDER BY 1, 2 LOOP
    v_conf := v_conf || jsonb_build_array(jsonb_build_object(
      'chain', 'use:' || c.use_id,
      'note', 'near-duplicate: use ' || c.other_id || ' also records this work and gap'));
  END LOOP;

  UPDATE promotions pr
     SET counts = jsonb_build_object('chains', n_ok + n_held, 'prepared', n_ok, 'held', n_held),
         conflicts = v_conf
   WHERE pr.id = v_pid;
  RETURN v_pid;
END
$$;

CREATE FUNCTION litkb.promote_commit(p_promotion uuid, p_merge_commit text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  p record;
  c record;
  t record;
  k text;
  v_status jsonb := '{}'::jsonb;
  v_progress boolean;
  v_hold text;
  v_n bigint;
  v_conf jsonb := '[]'::jsonb;
  n_ok integer := 0;
  n_held integer := 0;
BEGIN
  SELECT * INTO p FROM promotions pr WHERE pr.id = p_promotion FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: no promotion %', p_promotion USING ERRCODE = 'P0002';
  END IF;
  IF p.state <> 'prepared' THEN
    RAISE EXCEPTION 'litkb: promotion % is %, not prepared', p_promotion, p.state USING ERRCODE = '55000';
  END IF;
  IF p_merge_commit IS NULL OR p_merge_commit !~ '^[0-9a-f]{40}$' THEN
    RAISE EXCEPTION 'litkb: merge commit must be a full 40-hex sha' USING ERRCODE = '22023';
  END IF;
  PERFORM 1 FROM workstreams w WHERE w.id = p.workstream_id AND w.state = 'open' FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % is not open', p.workstream_id USING ERRCODE = '55000';
  END IF;
  IF _version_set_hash(p.workstream_id) <> p.version_set_hash THEN
    RAISE EXCEPTION 'litkb: the version set of workstream % changed after promote_prepare; prepare again so the reviewed report matches what is committed',
      p.workstream_id USING ERRCODE = '40001';
  END IF;

  FOR c IN SELECT * FROM _ws_chains(p.workstream_id) LOOP
    k := c.entity || ':' || c.entity_id;
    v_status := v_status || jsonb_build_object(k, jsonb_build_object(
      'entity', c.entity, 'id', c.entity_id, 'head', c.head, 'base', c.base,
      'ready', cardinality(c.problems) = 0
               AND c.states <@ ARRAY['prepared']::text[]
               AND c.promotion_ids <@ ARRAY[p_promotion],
      'done', false, 'ok', false,
      'reasons', to_jsonb(c.problems), 'deps', to_jsonb(c.deps), 'versions', to_jsonb(c.version_ids)));
  END LOOP;

  -- decide chains in dependency order: a chain waits until every chain it depends on is decided
  LOOP
    v_progress := false;
    FOR k IN SELECT jsonb_object_keys(v_status) ORDER BY 1 LOOP
      CONTINUE WHEN (v_status->k->>'done')::boolean;
      CONTINUE WHEN EXISTS (SELECT 1 FROM jsonb_array_elements_text(v_status->k->'deps') dd
                             WHERE v_status ? dd AND NOT (v_status->dd->>'done')::boolean);
      v_hold := NULL;
      -- BEGIN guard: dependency hold (commit)
      SELECT 'dependency held: ' || dd INTO v_hold
        FROM jsonb_array_elements_text(v_status->k->'deps') dd
       WHERE NOT coalesce((v_status->dd->>'ok')::boolean, false)
       LIMIT 1;
      -- END guard: dependency hold (commit)
      IF v_hold IS NULL AND NOT (v_status->k->>'ready')::boolean THEN
        v_hold := 'not prepared in this promotion, or a check failed: ' || (v_status->k->'reasons')::text;
      END IF;
      IF v_hold IS NULL THEN
        SELECT * INTO t FROM _entity_tables(v_status->k->>'entity');
        EXECUTE format('UPDATE %s SET current_version_id = $1 WHERE id = $2 AND current_version_id IS NOT DISTINCT FROM $3', t.ident)
          USING (v_status->k->>'head')::uuid, (v_status->k->>'id')::uuid, (v_status->k->>'base')::uuid;
        GET DIAGNOSTICS v_n = ROW_COUNT;
        IF v_n <> 1 THEN
          v_hold := 'conflict: main''s pointer moved off this chain''s base';
        END IF;
      END IF;
      IF v_hold IS NULL THEN
        EXECUTE format('UPDATE %s SET state = ''promoted'', promoted_at = now() WHERE version_id = ANY ($1)', t.vers)
          USING ARRAY(SELECT jsonb_array_elements_text(v_status->k->'versions'))::uuid[];
        DELETE FROM ws_heads wh
         WHERE wh.workstream_id = p.workstream_id AND wh.entity = v_status->k->>'entity'
           AND wh.entity_id = (v_status->k->>'id')::uuid;
        PERFORM _refresh_mirrors(v_status->k->>'entity', (v_status->k->>'id')::uuid);
        v_status := jsonb_set(v_status, ARRAY[k, 'ok'], 'true'::jsonb);
        n_ok := n_ok + 1;
      ELSE
        v_conf := v_conf || jsonb_build_array(jsonb_build_object('chain', k, 'reason', v_hold));
        n_held := n_held + 1;
      END IF;
      v_status := jsonb_set(v_status, ARRAY[k, 'done'], 'true'::jsonb);
      v_progress := true;
    END LOOP;
    EXIT WHEN NOT v_progress;
  END LOOP;
  -- anything still undecided sits in a dependency cycle
  FOR k IN SELECT jsonb_object_keys(v_status) ORDER BY 1 LOOP
    CONTINUE WHEN (v_status->k->>'done')::boolean;
    v_conf := v_conf || jsonb_build_array(jsonb_build_object('chain', k, 'reason', 'dependency cycle'));
    n_held := n_held + 1;
  END LOOP;

  UPDATE promotions pr
     SET state = 'committed', merge_commit = p_merge_commit, committed_at = now(),
         counts = pr.counts || jsonb_build_object('committed', n_ok, 'held_at_commit', n_held),
         conflicts = pr.conflicts || jsonb_build_array(jsonb_build_object('at_commit', v_conf))
   WHERE pr.id = p_promotion;
  UPDATE workstreams w SET state = 'merged', closed_at = now(), merge_commit = p_merge_commit
   WHERE w.id = p.workstream_id;
  RETURN jsonb_build_object('promotion', p_promotion, 'committed', n_ok, 'held', n_held, 'held_chains', v_conf);
END
$$;

CREATE FUNCTION litkb.promote_abandon(p_promotion uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  e text;
  t record;
BEGIN
  UPDATE promotions pr SET state = 'abandoned' WHERE pr.id = p_promotion AND pr.state = 'prepared';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: promotion % is not prepared', p_promotion USING ERRCODE = '55000';
  END IF;
  FOREACH e IN ARRAY ARRAY['work', 'identifier', 'file', 'gap', 'use'] LOOP
    SELECT * INTO t FROM _entity_tables(e);
    EXECUTE format('UPDATE %s SET state = ''proposed'', promotion_id = NULL WHERE promotion_id = $1 AND state = ''prepared''', t.vers)
      USING p_promotion;
  END LOOP;
END
$$;
