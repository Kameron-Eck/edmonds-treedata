-- litkb 0016 — a held candidate says WHY it is held.
--
-- Referee P3, 2026-09-15 (Reports/LITKB_P3_REFEREE_2026-09-15.md §5 F6): all 68 `new` candidates the P3
-- load held carry `state_reason IS NULL`, so why a row is held has to be INFERRED from the absence of an
-- admission — "recorded, flagged, not admitted" holds for the first two only. The load already knows the
-- reason exactly (plan.py's case table: case C, a registry record whose claim the row contradicts with no
-- file to bind; case E, nothing resolved and no file); it simply had nowhere to put it.
--
-- `candidates` carries workstream_id, so it is a GUARDED RELATION (design §4.7, migration 0011): no agent
-- role holds UPDATE on it, and 0011 says in those words that state, state_reason and admitted_work_id are
-- "set by admission (P2), not by the lead". A held row is the one candidate state admission never reaches,
-- so it needs its own token-checked SECURITY DEFINER writer, shaped exactly like record_discrepancy.
--
-- The function is deliberately NARROW: it may only write the reason of a candidate that is still `new` and
-- has no admitted work. It can neither change a state nor overwrite the reason admission wrote.

SET LOCAL search_path = litkb, public;

CREATE FUNCTION litkb.hold_candidate(
  p_workstream uuid, p_ws_token text, p_candidate uuid, p_reason text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_done boolean := false;
BEGIN
  -- BEGIN guard: hold_candidate presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: hold_candidate presents the workstream token
  IF p_reason IS NULL OR btrim(p_reason) = '' THEN
    RAISE EXCEPTION 'litkb: a held candidate needs a reason' USING ERRCODE = '22023';
  END IF;
  -- BEGIN guard: hold_candidate touches only this workstream's unadmitted candidate
  -- The workstream test is the same one record_discrepancy makes: a token for workstream A must not reach
  -- workstream B's rows. The state test is what keeps this out of admission's territory — an admitted,
  -- duplicate or rejected candidate already has a state_reason that admission decided.
  UPDATE candidates cd SET state_reason = p_reason
   WHERE cd.id = p_candidate AND cd.workstream_id = p_workstream
     AND cd.state = 'new' AND cd.admitted_work_id IS NULL;
  -- END guard: hold_candidate touches only this workstream's unadmitted candidate
  GET DIAGNOSTICS v_done = ROW_COUNT;
  IF NOT v_done THEN
    RAISE EXCEPTION 'litkb: candidate % is not an unadmitted candidate of workstream %',
      p_candidate, p_workstream USING ERRCODE = '42501';
  END IF;
  RETURN v_done;
END
$$;

COMMENT ON FUNCTION litkb.hold_candidate(uuid, text, uuid, text) IS
  'Record WHY a candidate is held (referee P3 F6). The only writer of state_reason outside admission; it may write only an unadmitted `new` candidate of the workstream whose token it is given.';

-- ── privileges ───────────────────────────────────────────────────────────────────────────
REVOKE EXECUTE ON FUNCTION litkb.hold_candidate(uuid, text, uuid, text) FROM PUBLIC;
-- BEGIN guard: writer executes hold_candidate and holds no direct write on candidates
GRANT EXECUTE ON FUNCTION litkb.hold_candidate(uuid, text, uuid, text) TO litkb_writer;
-- END guard: writer executes hold_candidate and holds no direct write on candidates

-- ── a binding that waits for OCR records what it measured ────────────────────────────────
-- Referee P3 F9: every `binding-pending` check reads
--   {'verdict': 'binding-pending', 'reasons': ['no text layer ... waits for OCR']}
-- while `binding-failed` carries its ratio. P4's OCR queue needs the numbers the check already had in its
-- hand — how much text page 1 held, and what the best title ratio was — to sort the queue and to prove
-- afterwards that OCR changed something. Nothing about the VERDICT changes: the guard's condition and its
-- reason are copied through byte for byte; only the evidence beside them is added.
CREATE OR REPLACE FUNCTION litkb._check_binding(p_work_title text, p_file jsonb)
RETURNS jsonb LANGUAGE plpgsql STABLE SET search_path = litkb, public, pg_temp AS $$
DECLARE
  b jsonb;
  v_reasons text[] := '{}';
  v_ratio numeric;
  v_evidence jsonb := '{}'::jsonb;
BEGIN
  IF p_file IS NULL THEN
    RETURN jsonb_build_object('verdict', 'none');
  END IF;
  IF coalesce(p_file->>'sha256', '') !~ '^[0-9a-f]{64}$' THEN
    RETURN jsonb_build_object('verdict', 'binding-failed', 'reasons', to_jsonb(ARRAY['the file has no sha256']));
  END IF;
  b := coalesce(p_file->'binding', '{}'::jsonb);
  v_ratio := CASE WHEN coalesce(b->>'ratio', '') ~ '^[0-9]*\.?[0-9]+$' THEN (b->>'ratio')::numeric END;
  -- BEGIN guard: check 3 no text layer waits for OCR
  IF (b->>'text_layer') IS DISTINCT FROM 'true' AND coalesce(v_ratio, 0) < 0.85 THEN
    -- BEGIN guard: a pending binding records the evidence it waited on
    -- Merged onto the verdict, not built into it, so that REMOVING this block leaves the function valid SQL:
    -- a mutation here must change the EVIDENCE and nothing else, or what fires is a syntax error rather than
    -- the guard (CLAUDE.md 3.4c — the harness reported exactly that, as errors instead of failures).
    v_evidence := jsonb_build_object(
      'ratio', v_ratio,
      'page', coalesce((b->>'page')::int, 1),
      'page1_chars', CASE WHEN coalesce(b->>'page1_chars', '') ~ '^[0-9]+$' THEN (b->>'page1_chars')::int END,
      'text_layer', coalesce((b->>'text_layer')::boolean, false),
      'best_any_ratio', CASE WHEN coalesce(b->>'best_any_ratio', '') ~ '^[0-9]*\.?[0-9]+$'
                            THEN (b->>'best_any_ratio')::numeric END);
    -- END guard: a pending binding records the evidence it waited on
    RETURN jsonb_build_object('verdict', 'binding-pending',
                              'reasons', to_jsonb(ARRAY['no text layer on the first page and no PDF title match: waits for OCR (decisions.yaml §15.14)']))
           || v_evidence;
  END IF;
  -- END guard: check 3 no text layer waits for OCR
  -- BEGIN guard: check 3 binding evidence
  IF v_ratio IS NULL OR v_ratio < 0.85 THEN
    v_reasons := v_reasons || format('title ratio %s < 0.85: the registry title is not in the title region of the first page or in the PDF title', coalesce(v_ratio::text, 'missing'));
  END IF;
  IF (b->>'author_found') IS DISTINCT FROM 'true' THEN
    v_reasons := v_reasons || 'the registry first author is not on the first page'::text;
  END IF;
  IF coalesce(btrim(b->>'matched'), '') = '' THEN
    v_reasons := v_reasons || 'no matched line recorded'::text;
  END IF;
  IF norm_title(b->>'registry_title') IS DISTINCT FROM norm_title(p_work_title) THEN
    v_reasons := v_reasons || 'the binding was measured against another title than the work''s'::text;
  END IF;
  -- END guard: check 3 binding evidence
  -- BEGIN guard: check 3 region and author-near evidence
  IF (b->>'title_region') IS DISTINCT FROM 'true' THEN
    v_reasons := v_reasons || 'the binding was not measured under the title-region rule (0014 D2)'::text;
  END IF;
  IF (b->>'author_near_title') IS DISTINCT FROM 'true' THEN
    v_reasons := v_reasons || 'the registry first author is not a whole token near the matched title'::text;
  END IF;
  -- END guard: check 3 region and author-near evidence
  RETURN jsonb_build_object('verdict', CASE WHEN cardinality(v_reasons) = 0 THEN 'bound' ELSE 'binding-failed' END,
                            'ratio', v_ratio, 'reasons', to_jsonb(v_reasons));
END
$$;

-- end of 0016
