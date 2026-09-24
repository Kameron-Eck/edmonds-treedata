-- litkb 0035 — the operator-bind gate reaches the registry admission's own file (LITKB_WORKPLAN.md "### S4.5"
-- item 1; decisions.yaml `litkb-from-file-version-state`; S4.5 decision D25; integrator-w3).
--
-- WHY. 0034 made every operator-supplied file a PROPOSAL a second session approves — but only on the path
-- through `litkb.attach_file` (`acquire --from-file`, the web landing). `litkb admit --doi D --file F` and the
-- MCP tool `litkb_admit(file=...)` bind the operator's PDF INSIDE the registry admission, through
-- `litkb.admit`, whose file is written in the admission's own mode: a registry admission is a fact, so the
-- operator's file became the version of record with no second session (auditor-B2 round 2 F9; the ruling's
-- question names "Every operator bind" and its why "hand-supplied PDFs"). The orchestrator's ruling D25:
-- "`admit --file` and the MCP `litkb_admit(file=)` join the gate. If this needs SQL beyond the applied
-- 0032-0034, it is a NEW migration (0035 ...) — applied migrations are never edited."
--
-- WHAT CHANGES. `litkb.admit` is re-created from 0032's text VERBATIM except for ONE guard and what it sets:
-- a file whose `source_route` is on `litkb._proposal_source_routes()` (0034's one home: `browser`,
-- `held-in-place`, `web`) is written as a PROPOSAL (`_write_version('proposal', 'file', ...)`), whatever the
-- admission's mode. The work and its identifiers are unchanged: a registry-confirmed work is a fact (the
-- DOI-first rule), and only the operator's claim that THESE bytes are it waits for a second session. Checks 1-4
-- run exactly as before, on the same file evidence, so a file that fails binding or is already held still
-- refuses the admission. The result gains `file_state` (`proposed` / `promoted`); `outcome` keeps its word.
-- The Python front sets `source_route` = `held-in-place` for `admit --file` and the MCP `file=` (the file is
-- admitted where it lies under the literature root — `acquire --from-file`'s in-place route), so
-- `operator_binds_unproposed` (qc/instruments/litkb_hardening_b2.py, OPERATOR_ROUTES) reads them too.
--
-- 0032's text of `litkb.admit` is DEAD from here on (a CREATE OR REPLACE keeps its ACL); the mutation rows
-- on its guards point HERE (qc/instruments/litkb_p2_mutations.py, the integrator-w3 statement).
--
-- NOT DONE HERE: the 0013-0032 admissions that bound a hand-supplied file as a fact are history and are not
-- retro-demoted (S4.5 decision D8's rule for operator binds). The legacy loader (`litkb.migrate_legacy`)
-- passes no `source_route` and is unchanged.
--
-- RELAYED DESIGN, UNVALIDATED (CLAUDE.md §3.4c): the gate's design is 0034's; this migration only extends
-- its reach, and an independent referee scores it on the real rows.

SET LOCAL search_path = litkb, public;

CREATE OR REPLACE FUNCTION litkb.admit(
  p_workstream uuid, p_ws_token text, p_candidate uuid, p_route text, p_key text,
  p_work jsonb, p_identifiers jsonb, p_file jsonb, p_checks jsonb, p_agent text, p_session text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  cand record;
  i jsonb;
  k text;
  v_mode text;
  v_checks jsonb;
  v_c1 jsonb;
  v_c3 jsonb;
  v_hits jsonb;
  v_existing uuid;
  v_strong integer;
  v_adm uuid;
  v_work uuid;
  v_wver uuid;
  v_id uuid;
  v_ver uuid;
  v_ids jsonb;
  v_file uuid;
  v_cname text;
  v_keys text[];
  v_key text;
  v_done boolean := false;
  v_asserted text;
  v_file_mode text;
BEGIN
  -- BEGIN guard: admit presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: admit presents the workstream token
  PERFORM 1 FROM workstreams w WHERE w.id = p_workstream AND w.state = 'open' FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % is not open', p_workstream USING ERRCODE = '22023';
  END IF;
  IF p_route IS NULL OR p_route NOT IN ('registry', 'manual') THEN
    RAISE EXCEPTION 'litkb: route must be registry or manual, got %', p_route USING ERRCODE = '22023';
  END IF;
  IF p_work IS NULL OR jsonb_typeof(p_work) <> 'object' THEN
    RAISE EXCEPTION 'litkb: work must be a JSON object' USING ERRCODE = '22023';
  END IF;
  IF jsonb_typeof(coalesce(p_identifiers, '[]'::jsonb)) = 'array' AND EXISTS (
       SELECT 1 FROM jsonb_array_elements(coalesce(p_identifiers, '[]'::jsonb)) x
        WHERE x->>'scheme' = 'doi' AND coalesce(norm_identifier('doi', x->>'value'), '') = '') THEN
    RAISE EXCEPTION 'litkb: a doi identifier holds no ''10.'' prefix; it is not a DOI' USING ERRCODE = '22023';
  END IF;
  -- BEGIN guard: a harvested identifier enters through record_identifiers, never through admission
  -- 0032: a row derived from another identifier (a Crossref `alternative-id`, an Anna's
  -- `identifiers_unified` key, a zero-request derivation) is HARVEST, and the conflict rule that decides
  -- what happens when it names another work lives in ONE place, litkb.record_identifiers. Admission
  -- takes only the identifiers the admission is about.
  IF jsonb_typeof(coalesce(p_identifiers, '[]'::jsonb)) = 'array' AND EXISTS (
       SELECT 1 FROM jsonb_array_elements(coalesce(p_identifiers, '[]'::jsonb)) x WHERE x ? 'derived_from') THEN
    RAISE EXCEPTION 'litkb: an identifier with derived_from is a harvest row; litkb.record_identifiers takes it'
      USING ERRCODE = '22023';
  END IF;
  -- END guard: a harvested identifier enters through record_identifiers, never through admission
  IF jsonb_typeof(coalesce(p_identifiers, '[]'::jsonb)) = 'array' AND EXISTS (
       SELECT 1 FROM jsonb_array_elements(coalesce(p_identifiers, '[]'::jsonb)) x
        WHERE NOT EXISTS (SELECT 1 FROM scheme_registry sr WHERE sr.scheme = x->>'scheme')) THEN
    RAISE EXCEPTION 'litkb: an identifier names a scheme litkb.scheme_registry does not hold' USING ERRCODE = '22023';
  END IF;
  SELECT * INTO cand FROM candidates cd WHERE cd.id = p_candidate FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: no candidate %', p_candidate USING ERRCODE = 'P0002';
  END IF;
  -- BEGIN guard: the candidate belongs to the admitting workstream
  IF cand.workstream_id IS DISTINCT FROM p_workstream THEN
    RAISE EXCEPTION 'litkb: candidate % belongs to another workstream', p_candidate USING ERRCODE = '42501';
  END IF;
  -- END guard: the candidate belongs to the admitting workstream
  IF cand.state <> 'new' THEN
    RAISE EXCEPTION 'litkb: candidate % is %, not new; record a new candidate to try again', p_candidate, cand.state
      USING ERRCODE = '55000';
  END IF;

  v_checks := coalesce(p_checks, '{}'::jsonb);
  -- check 3 first (check 1 needs to know whether a bound file is present)
  v_c3 := _check_binding(p_work->>'title', p_file);
  v_c1 := _check_registry(p_route, p_work, p_identifiers, v_c3->>'verdict' = 'bound');
  v_checks := v_checks || jsonb_build_object('check1_study_exists', v_c1, 'check3_binding', v_c3);

  -- BEGIN guard: check 4 a manual admission carries a bound file
  IF p_route = 'manual' AND v_c3->>'verdict' <> 'bound' THEN
    v_adm := _refuse_admission(p_workstream, p_candidate, p_route, p_agent, p_session,
                               v_checks || jsonb_build_object('check4_manual', 'a manual admission needs a held file whose first page carries the title'),
                               'rejected', 'manual admission without a bound file', NULL);
    RETURN jsonb_build_object('outcome', 'refused', 'admission_id', v_adm, 'refused_at', 'check4_manual', 'checks', v_checks);
  END IF;
  -- END guard: check 4 a manual admission carries a bound file
  IF v_c1->>'verdict' <> 'pass' OR v_c3->>'verdict' IN ('binding-failed', 'binding-pending') THEN
    v_adm := _refuse_admission(p_workstream, p_candidate, p_route, p_agent, p_session, v_checks, 'rejected',
                               CASE WHEN v_c3->>'verdict' IN ('binding-failed', 'binding-pending') THEN v_c3->>'verdict'
                                    ELSE 'check 1: ' || (v_c1->'reasons')::text END, NULL);
    RETURN jsonb_build_object('outcome', 'refused', 'admission_id', v_adm,
                              'refused_at', CASE WHEN v_c3->>'verdict' IN ('binding-failed', 'binding-pending')
                                                 THEN 'check3_binding' ELSE 'check1_study_exists' END,
                              'checks', v_checks);
  END IF;

  -- check 2: serialise admissions of the same identifiers, then look them up
  -- BEGIN guard: check 2 identifier lock
  FOR k IN SELECT DISTINCT 'litkb:identifier:' || (x->>'scheme') || ':' || norm_identifier(x->>'scheme', x->>'value')
             FROM jsonb_array_elements(coalesce(p_identifiers, '[]'::jsonb)) x ORDER BY 1 LOOP
    PERFORM pg_advisory_xact_lock(hashtextextended(k, 0));
  END LOOP;
  -- END guard: check 2 identifier lock
  -- BEGIN guard: check 2 identifier lookup
  -- 0032: an identifier is a duplicate only where the registry says its value names ONE work
  -- (distinct_values), or — for a type-scoped scheme — where both works are of the scheme's identity types
  -- (isbn: two books; a chapter carrying its book's ISBN is data, not a duplicate).
  SELECT iv.work_id INTO v_existing
    FROM jsonb_array_elements(coalesce(p_identifiers, '[]'::jsonb)) x
    JOIN scheme_registry sr ON sr.scheme = x->>'scheme'
    JOIN identifiers idf ON idf.scheme = x->>'scheme' AND idf.value_norm = norm_identifier(x->>'scheme', x->>'value')
    JOIN identifier_versions iv ON iv.identifier_id = idf.id
   WHERE iv.status = 'active' AND ((idf.active AND iv.version_id = idf.current_version_id) OR iv.state = 'proposed')
     AND (sr.distinct_values
          OR (sr.identity_types IS NOT NULL AND coalesce(p_work->>'type', 'article') = ANY (sr.identity_types)
              AND EXISTS (SELECT 1 FROM works ow JOIN work_versions ov ON ov.work_id = ow.id
                           WHERE ow.id = iv.work_id AND ov.type = ANY (sr.identity_types)
                             AND (ov.version_id = ow.current_version_id OR ov.state = 'proposed'))))
   LIMIT 1;
  IF v_existing IS NOT NULL THEN
    v_checks := v_checks || jsonb_build_object('check2_duplicate', jsonb_build_object('verdict', 'duplicate', 'work_id', v_existing));
    v_adm := _refuse_admission(p_workstream, p_candidate, p_route, p_agent, p_session, v_checks, 'duplicate',
                               'identifier already admitted', v_existing);
    RETURN jsonb_build_object('outcome', 'duplicate', 'admission_id', v_adm, 'work_id', v_existing, 'checks', v_checks);
  END IF;
  -- END guard: check 2 identifier lookup

  -- 0032: identifier-first — the strong schemes are the registry's `identity_strong` rows (0014's list
  -- doi arxiv isbn pmid pmcid jstor, less handle — see the registry's why): a candidate holding one that no
  -- existing work holds is a DIFFERENT record, possibly related (litkb-sibling-edition), never a title
  -- duplicate. A strong scheme counts only where it is THIS candidate's identity: a distinct scheme, or a
  -- type-scoped one whose types include the candidate's (an ISBN on a report or a chapter is not the
  -- report's identity — the lookup above did not look for it, so the title review must still run; auditor-B1 F6)
  SELECT count(*) INTO v_strong FROM jsonb_array_elements(coalesce(p_identifiers, '[]'::jsonb)) x
    JOIN scheme_registry sr ON sr.scheme = x->>'scheme' AND sr.identity_strong
     AND (sr.distinct_values OR coalesce(p_work->>'type', 'article') = ANY (coalesce(sr.identity_types, '{}'::text[])));
  IF v_strong = 0 THEN
    PERFORM pg_advisory_xact_lock(hashtextextended('litkb:title-admission', 0));
    -- BEGIN guard: check 2 title duplicate review
    SELECT coalesce(jsonb_agg(to_jsonb(d) ORDER BY d.similarity DESC), '[]'::jsonb) INTO v_hits
      FROM _title_duplicates(p_work->>'title', CASE WHEN coalesce(p_work->>'year', '') ~ '^[0-9]{4}$'
                                                    THEN (p_work->>'year')::integer END) d;
    IF jsonb_array_length(v_hits) > 0 THEN
      v_checks := v_checks || jsonb_build_object('check2_duplicate', jsonb_build_object(
        'verdict', 'duplicate-review', 'threshold', _title_dup_threshold(), 'matches', v_hits));
      v_adm := _refuse_admission(p_workstream, p_candidate, p_route, p_agent, p_session, v_checks, 'duplicate-review',
                                 'title similar to an existing work; sent to duplicate review', NULL);
      RETURN jsonb_build_object('outcome', 'duplicate-review', 'admission_id', v_adm, 'matches', v_hits, 'checks', v_checks);
    END IF;
    -- END guard: check 2 title duplicate review
  END IF;
  v_checks := v_checks || jsonb_build_object('check2_duplicate', jsonb_build_object('verdict', 'pass'));

  IF p_file IS NOT NULL THEN
    PERFORM pg_advisory_xact_lock(hashtextextended('litkb:file:' || (p_file->>'sha256'), 0));
    -- BEGIN guard: check 2 file sha256 lookup
    SELECT f.id INTO v_existing FROM files f WHERE f.sha256 = p_file->>'sha256';
    IF v_existing IS NOT NULL THEN
      v_adm := _refuse_admission(p_workstream, p_candidate, p_route, p_agent, p_session,
                                 v_checks || jsonb_build_object('file_duplicate', v_existing), 'rejected',
                                 'the file is already held (sha256)', NULL);
      RETURN jsonb_build_object('outcome', 'refused', 'refused_at', 'file_duplicate', 'file_id', v_existing,
                                'admission_id', v_adm, 'checks', v_checks);
    END IF;
    -- END guard: check 2 file sha256 lookup
  END IF;

  v_mode := CASE p_route WHEN 'registry' THEN 'fact' ELSE 'proposal' END;
  -- the default is the unguarded one (the admission's own mode), so removing the guard below leaves code that
  -- RUNS and writes the operator's file as the version of record — the known-bad `operator_binds_unproposed`
  -- counts — rather than an error the harness would report as DID NOT FIRE (CLAUDE.md §3.4c)
  v_file_mode := v_mode;
  -- BEGIN guard: an operator-supplied file admitted with its work is a proposal, never the version of record
  IF p_file IS NOT NULL AND coalesce(p_file->>'source_route', '') = ANY (_proposal_source_routes()) THEN
    v_file_mode := 'proposal';
  END IF;
  -- END guard: an operator-supplied file admitted with its work is a proposal, never the version of record
  v_keys := ARRAY[p_key];
  -- BEGIN guard: a key collision takes the convention's a/b suffix
  IF p_key ~ '^[A-Za-z]+_[0-9]{4}[ab]?_' THEN
    v_keys := v_keys || regexp_replace(p_key, '^([A-Za-z]+_[0-9]{4})[ab]?_', '\1a_')
                     || regexp_replace(p_key, '^([A-Za-z]+_[0-9]{4})[ab]?_', '\1b_');
  END IF;
  -- END guard: a key collision takes the convention's a/b suffix
  FOR v_key IN SELECT u.k FROM unnest(v_keys) WITH ORDINALITY u(k, n)
                GROUP BY u.k ORDER BY min(u.n) LOOP
    v_ids := '[]'::jsonb;
    BEGIN
      SELECT w.entity_id, w.version_id INTO v_work, v_wver
        FROM _write_version(v_mode, 'work', NULL, jsonb_build_object('key', v_key), NULL,
                            p_work, NULL, p_workstream, p_agent, p_session) w;
      FOR i IN SELECT x FROM jsonb_array_elements(coalesce(p_identifiers, '[]'::jsonb)) x LOOP
        v_asserted := nullif(btrim(i->>'asserted_by'), '');
        -- BEGIN guard: an admitted identifier carries who asserted it
        -- 0032 (LINKAGE §3.2 item 2): the caller that handed the identifier in, unless it said otherwise —
        -- a manual admitter, the literature tracker, the legacy corpus, or the admitting caller (a hunt
        -- reference, a CLI flag) whose value the registry then confirms (verified_by)
        v_asserted := coalesce(v_asserted, CASE WHEN p_route = 'manual' THEN 'manual'
                                                WHEN i->>'scheme' = 'tracker' THEN 'tracker'
                                                WHEN i->>'scheme' = 'legacy_stem' THEN 'legacy'
                                                ELSE 'caller' END);
        -- END guard: an admitted identifier carries who asserted it
        SELECT w.entity_id, w.version_id INTO v_id, v_ver
          FROM _write_version(v_mode, 'identifier', NULL, jsonb_build_object('scheme', i->>'scheme'), NULL,
                              jsonb_build_object('work_id', v_work,
                                                 -- D1: the canonical DOI is the stored value
                                                 'value', CASE WHEN i->>'scheme' = 'doi' THEN norm_identifier('doi', i->>'value')
                                                               ELSE i->>'value' END,
                                                 'verified_by', i->>'verified_by',
                                                 'evidence', coalesce(i->'evidence', '{}'::jsonb), 'status', 'active',
                                                 'asserted_by', v_asserted),
                              NULL, p_workstream, p_agent, p_session) w;
        v_ids := v_ids || to_jsonb(v_id);
      END LOOP;
      IF p_file IS NOT NULL THEN
        SELECT w.entity_id INTO v_file
          FROM _write_version(v_file_mode, 'file', NULL, jsonb_build_object('sha256', p_file->>'sha256'), NULL,
                              (p_file - 'sha256' - 'status' - 'status_reason')
                                || jsonb_build_object('work_id', v_work, 'status', 'active'),
                              NULL, p_workstream, p_agent, p_session) w;
      END IF;
      INSERT INTO admissions (candidate_id, work_id, route, admitter_agent, admitter_session, state, checks, workstream_id)
      VALUES (p_candidate, v_work, p_route, p_agent, p_session,
              CASE p_route WHEN 'registry' THEN 'admitted' ELSE 'proposed' END,
              v_checks || CASE WHEN v_key <> p_key
                               THEN jsonb_build_object('key_suffixed', jsonb_build_object('requested', p_key, 'key', v_key))
                               ELSE '{}'::jsonb END,
              p_workstream)
      RETURNING id INTO v_adm;
      UPDATE candidates cd SET state = 'admitted', state_reason = NULL, admitted_work_id = v_work WHERE cd.id = p_candidate;
      v_done := true;
    EXCEPTION WHEN unique_violation THEN
      GET STACKED DIAGNOSTICS v_cname = CONSTRAINT_NAME;
      -- another work holds this key (its identifiers differ: check 2 above passed): try the next suffix
      CONTINUE WHEN v_cname = 'works_key_key';
      -- the second lock: a concurrent admission of the same identifier or file won the index
      v_adm := _refuse_admission(p_workstream, p_candidate, p_route, p_agent, p_session,
                                 v_checks || jsonb_build_object('collided_on', v_cname), 'rejected',
                                 'collided on ' || coalesce(v_cname, 'a unique index'), NULL);
      RETURN jsonb_build_object('outcome', 'collided', 'constraint', v_cname, 'admission_id', v_adm, 'checks', v_checks);
    END;
    EXIT WHEN v_done;
  END LOOP;
  IF NOT v_done THEN
    v_adm := _refuse_admission(p_workstream, p_candidate, p_route, p_agent, p_session,
                               v_checks || jsonb_build_object('collided_on', 'works_key_key', 'keys_tried', to_jsonb(v_keys)),
                               'rejected', 'collided on works_key_key: the key and its a/b suffixes are all taken', NULL);
    RETURN jsonb_build_object('outcome', 'collided', 'constraint', 'works_key_key', 'admission_id', v_adm, 'checks', v_checks);
  END IF;
  RETURN jsonb_build_object('outcome', CASE p_route WHEN 'registry' THEN 'admitted' ELSE 'proposed' END,
                            'admission_id', v_adm, 'work_id', v_work, 'work_version', v_wver, 'key', v_key,
                            'identifier_ids', v_ids, 'file_id', v_file, 'checks', v_checks)
         || CASE WHEN v_file IS NOT NULL
                 THEN jsonb_build_object('file_state', CASE v_file_mode WHEN 'proposal' THEN 'proposed' ELSE 'promoted' END)
                 ELSE '{}'::jsonb END;
END
$$;

-- end of 0035
