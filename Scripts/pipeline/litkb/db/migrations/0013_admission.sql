-- litkb 0013 — P2 "Admission + acquisition" (design §4.6 checks 1-5, §4.7, §14 P2 row;
-- decisions.yaml litkb-p0-foundation §15.13, §15.14, §15.15).
--
-- Admission is ONE database transaction. The Python front (litkb.admit) talks to the registries and
-- reads the PDF; it hands this function the registry record, the claimed record it compared, and the
-- binding evidence it measured. The function re-checks every rule it can see in that evidence, refuses
-- what fails, and either writes works + identifiers + files + the admission row together or writes only
-- a refused admission row. What the database cannot do is re-run a registry lookup or re-read the PDF:
-- the ratios are client-measured, so these guards stop an honest mistake in a client, not a forged one
-- (the same limit as the session labels, design §4.6 check 4).
--
--   check 1  _check_registry: a registry route needs an identifier confirmed by a registry whose record
--            is the work's title and year; a claimed record (tracker, manifest) must match it at title
--            ratio >= 0.85 and first author, and its year must equal the registry year, or differ by one
--            only when title and first author both match (decisions.yaml §15.15).
--   check 2  identifiers: the normalised identifier is locked (advisory, transaction-scoped) and looked
--            up; an existing one returns the winner's work (outcome 'duplicate'). The partial unique
--            index of 0001 stays the second lock (outcome 'collided'). No identifier: trigram similarity
--            of the normalised title plus year +/-1 against every work (outcome 'duplicate-review').
--   check 3  _check_binding: a file is admitted only with binding evidence (registry title found on the
--            first page or in the PDF title at ratio >= 0.85, and the first author found). No text layer
--            and no match is 'binding-pending' (waits for OCR, §15.14). Anything else is refused.
--   check 4  manual route: every version is a PROPOSAL in the admitter's workstream; approve_admission,
--            called in another session (the 0009 constraint), moves main's pointers. _ws_chains now holds
--            every work/identifier/file chain, so promotion can never carry an unapproved fact to main.
--   check 5  the schema: statuses and candidate states widened for P2 below.

SET LOCAL search_path = litkb, public;

-- ── statuses ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE acquisition_attempts DROP CONSTRAINT acquisition_attempts_status_check;
ALTER TABLE acquisition_attempts ADD CONSTRAINT acquisition_attempts_status_check CHECK (status IN (
  'ok', 'not-in-archive', 'bad-file', 'binding-failed', 'binding-pending', 'partner-404', 'no-oa-copy',
  'record-mismatch', 'hash-mismatch', 'unresolved', 'api-error', 'blocked', 'duplicate-held', 'quota-stop',
  'manual-step'));

ALTER TABLE candidates DROP CONSTRAINT candidates_state_check;
ALTER TABLE candidates ADD CONSTRAINT candidates_state_check CHECK (
  state IN ('new', 'admitted', 'duplicate', 'duplicate-review', 'rejected'));

-- ── titles ───────────────────────────────────────────────────────────────────────────────
-- lowercase, markup tags removed (Crossref titles carry MathML/JATS), every run of non-alphanumerics
-- collapsed to one space
CREATE FUNCTION litkb.norm_title(p_title text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
  SELECT btrim(regexp_replace(lower(regexp_replace(p_title, '<[^>]*>', ' ', 'g')), '[^[:alnum:]]+', ' ', 'g'))
$$;

-- Calibrated on the tracker's `Duplicate of` pairs (qc/instruments/litkb_title_threshold.py,
-- Reports/litkb_title_threshold_2026-09-14.csv, Reports/LITKB_P2_REPORT_2026-09-14.md): 460 rows, 4 gold pairs
-- (3 share a title, similarity 1.000; 3/50 is a DOI-only duplicate at 0.239 that no title rule can catch),
-- 12,739 non-duplicate pairs within +/-1 year. 0.70 is the lowest 0.05-grid threshold with zero of those
-- flagged (the highest non-duplicate is 0.683). Weak calibration: recall is untested between 0.70 and 1.00.
CREATE FUNCTION litkb._title_dup_threshold() RETURNS real
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT 0.70::real $$;

CREATE INDEX work_versions_norm_title_trgm ON work_versions USING gin (litkb.norm_title(title) gin_trgm_ops);

CREATE FUNCTION litkb._title_duplicates(p_title text, p_year integer)
RETURNS TABLE (work_id uuid, key text, title text, year integer, similarity real)
LANGUAGE sql STABLE SET search_path = litkb, public, pg_temp AS $$
  SELECT DISTINCT ON (w.id) w.id, w.key, v.title, v.year,
         similarity(norm_title(v.title), norm_title(p_title))
    FROM work_versions v JOIN works w ON w.id = v.work_id
   WHERE similarity(norm_title(v.title), norm_title(p_title)) >= _title_dup_threshold()
     AND (p_year IS NULL OR v.year IS NULL OR abs(v.year - p_year) <= 1)
   ORDER BY w.id, similarity(norm_title(v.title), norm_title(p_title)) DESC
$$;

-- ── check 1 ──────────────────────────────────────────────────────────────────────────────
CREATE FUNCTION litkb._check_registry(p_route text, p_work jsonb, p_identifiers jsonb, p_has_bound_file boolean)
RETURNS jsonb LANGUAGE plpgsql STABLE SET search_path = litkb, public, pg_temp AS $$
DECLARE
  i jsonb;
  e jsonb;
  c jsonb;
  v_reasons text[] := '{}';
  v_these text[];
  n_verified integer := 0;
  v_ry integer;
  v_cy integer;
  v_ratio numeric;
BEGIN
  IF coalesce(btrim(p_work->>'title'), '') = '' THEN
    v_reasons := v_reasons || 'the work has no title'::text;
  END IF;
  IF jsonb_typeof(coalesce(p_identifiers, '[]'::jsonb)) <> 'array' THEN
    RETURN jsonb_build_object('verdict', 'fail', 'reasons', to_jsonb(ARRAY['identifiers must be a JSON array']));
  END IF;
  IF p_route = 'manual' THEN
    FOR i IN SELECT x FROM jsonb_array_elements(coalesce(p_identifiers, '[]'::jsonb)) x LOOP
      IF i->>'verified_by' IS DISTINCT FROM 'manual' THEN
        v_reasons := v_reasons || format('manual admission: identifier %s:%s must be verified_by manual', i->>'scheme', i->>'value');
      END IF;
    END LOOP;
    RETURN jsonb_build_object('verdict', CASE WHEN cardinality(v_reasons) = 0 THEN 'pass' ELSE 'fail' END,
                              'route', 'manual', 'reasons', to_jsonb(v_reasons));
  END IF;

  FOR i IN SELECT x FROM jsonb_array_elements(coalesce(p_identifiers, '[]'::jsonb)) x LOOP
    CONTINUE WHEN i->>'scheme' NOT IN ('doi', 'arxiv', 'isbn');
    v_these := '{}';
    IF i->>'verified_by' IS NULL OR i->>'verified_by' NOT IN ('crossref', 'datacite', 'arxiv', 's2') THEN
      v_reasons := v_reasons || format('%s %s is not confirmed by a registry', i->>'scheme', i->>'value');
      CONTINUE;
    END IF;
    e := coalesce(i->'evidence', '{}'::jsonb);
    IF coalesce(btrim(e->>'registry_title'), '') = '' OR coalesce(btrim(e->>'registry_first_author'), '') = ''
       OR coalesce(e->>'registry_year', '') !~ '^[0-9]{4}$' THEN
      v_reasons := v_reasons || format('%s %s: registry evidence lacks title, first author or year', i->>'scheme', i->>'value');
      CONTINUE;
    END IF;
    v_ry := (e->>'registry_year')::integer;
    -- BEGIN guard: check 1 the work is the registry record
    IF norm_title(e->>'registry_title') IS DISTINCT FROM norm_title(p_work->>'title') THEN
      v_these := v_these || format('%s %s: the work''s title is not the registry title', i->>'scheme', i->>'value');
    END IF;
    IF coalesce(p_work->>'year', '') !~ '^[0-9]{4}$' OR (p_work->>'year')::integer <> v_ry THEN
      v_these := v_these || format('%s %s: the work''s year is not the registry year %s', i->>'scheme', i->>'value', v_ry);
    END IF;
    -- END guard: check 1 the work is the registry record
    c := e->'claimed';
    IF c IS NOT NULL AND jsonb_typeof(c) = 'object' THEN
      v_ratio := CASE WHEN coalesce(c->>'title_ratio', '') ~ '^[0-9]*\.?[0-9]+$' THEN (c->>'title_ratio')::numeric END;
      v_cy := CASE WHEN coalesce(c->>'year', '') ~ '^[0-9]{4}$' THEN (c->>'year')::integer END;
      -- BEGIN guard: check 1 claimed record matches the registry
      IF v_ratio IS NULL OR v_ratio < 0.85 THEN
        v_these := v_these || format('%s %s: claimed title ratio %s < 0.85 against the registry title', i->>'scheme', i->>'value', coalesce(v_ratio::text, 'missing'));
      END IF;
      IF (c->>'author_match') IS DISTINCT FROM 'true' THEN
        v_these := v_these || format('%s %s: claimed first author does not match the registry''s', i->>'scheme', i->>'value');
      END IF;
      -- END guard: check 1 claimed record matches the registry
      -- BEGIN guard: check 1 year rule
      -- decisions.yaml §15.15: +/-1 only when title and first author both match; otherwise exact
      IF v_cy IS NULL THEN
        v_these := v_these || format('%s %s: claimed year missing', i->>'scheme', i->>'value');
      ELSIF v_cy = v_ry THEN
        NULL;
      ELSIF abs(v_cy - v_ry) = 1 AND v_ratio >= 0.85 AND (c->>'author_match') = 'true' THEN
        NULL;
      ELSE
        v_these := v_these || format('%s %s: claimed year %s against registry year %s', i->>'scheme', i->>'value', v_cy, v_ry);
      END IF;
      -- END guard: check 1 year rule
    ELSIF NOT coalesce(p_has_bound_file, false) THEN
      -- a DOI alone proves only that SOME work exists; with no claimed record to compare, the file's
      -- binding is the comparison, so a DOI-only admission needs a bound file
      v_these := v_these || format('%s %s: no claimed record to compare with the registry and no bound file', i->>'scheme', i->>'value');
    END IF;
    v_reasons := v_reasons || v_these;
    IF cardinality(v_these) = 0 THEN
      n_verified := n_verified + 1;
    END IF;
  END LOOP;
  -- BEGIN guard: check 1 a registry identifier is confirmed
  IF n_verified = 0 THEN
    v_reasons := v_reasons || 'registry admission: no doi, arxiv or isbn identifier was confirmed by a registry'::text;
  END IF;
  -- END guard: check 1 a registry identifier is confirmed
  RETURN jsonb_build_object('verdict', CASE WHEN cardinality(v_reasons) = 0 THEN 'pass' ELSE 'fail' END,
                            'route', 'registry', 'confirmed', n_verified, 'reasons', to_jsonb(v_reasons));
END
$$;

-- ── check 3 ──────────────────────────────────────────────────────────────────────────────
CREATE FUNCTION litkb._check_binding(p_work_title text, p_file jsonb)
RETURNS jsonb LANGUAGE plpgsql STABLE SET search_path = litkb, public, pg_temp AS $$
DECLARE
  b jsonb;
  v_reasons text[] := '{}';
  v_ratio numeric;
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
    RETURN jsonb_build_object('verdict', 'binding-pending',
                              'reasons', to_jsonb(ARRAY['no text layer on the first page and no PDF title match: waits for OCR (decisions.yaml §15.14)']));
  END IF;
  -- END guard: check 3 no text layer waits for OCR
  -- BEGIN guard: check 3 binding evidence
  IF v_ratio IS NULL OR v_ratio < 0.85 THEN
    v_reasons := v_reasons || format('title ratio %s < 0.85: the registry title is not on the first page or in the PDF title', coalesce(v_ratio::text, 'missing'));
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
  RETURN jsonb_build_object('verdict', CASE WHEN cardinality(v_reasons) = 0 THEN 'bound' ELSE 'binding-failed' END,
                            'ratio', v_ratio, 'reasons', to_jsonb(v_reasons));
END
$$;

-- ── a refused admission is recorded, never silently dropped ─────────────────────────────
CREATE FUNCTION litkb._refuse_admission(p_workstream uuid, p_candidate uuid, p_route text, p_agent text, p_session text,
                                         p_checks jsonb, p_candidate_state text, p_reason text, p_work uuid)
RETURNS uuid LANGUAGE plpgsql SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_id uuid;
BEGIN
  INSERT INTO admissions (candidate_id, work_id, route, admitter_agent, admitter_session, state, checks, workstream_id)
  VALUES (p_candidate, p_work, p_route, p_agent, p_session, 'refused', p_checks, p_workstream)
  RETURNING id INTO v_id;
  UPDATE candidates cd SET state = p_candidate_state, state_reason = p_reason,
                           admitted_work_id = CASE WHEN p_candidate_state = 'duplicate' THEN p_work END
   WHERE cd.id = p_candidate;
  RETURN v_id;
END
$$;

-- ── admission ────────────────────────────────────────────────────────────────────────────
-- p_work         {type, title, subtitle, authors, year, venue, volume, issue, pages, publisher, language, abstract}
-- p_identifiers  [{scheme, value, verified_by, evidence}]
-- p_file         {sha256, rel_path, md5, bytes, pages, has_text_layer, pdf_metadata, copy_kind, source_route,
--                 source_url, obtained_at, txt_extract_path, binding} or NULL
-- p_checks       what the client measured (registry calls, ratios, file facts); the verdicts are added here
CREATE FUNCTION litkb.admit(
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
  v_ids jsonb := '[]'::jsonb;
  v_file uuid;
  v_cname text;
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
  SELECT iv.work_id INTO v_existing
    FROM jsonb_array_elements(coalesce(p_identifiers, '[]'::jsonb)) x
    JOIN identifiers idf ON idf.scheme = x->>'scheme' AND idf.value_norm = norm_identifier(x->>'scheme', x->>'value')
    JOIN identifier_versions iv ON iv.identifier_id = idf.id
   WHERE iv.status = 'active' AND ((idf.active AND iv.version_id = idf.current_version_id) OR iv.state = 'proposed')
   LIMIT 1;
  IF v_existing IS NOT NULL THEN
    v_checks := v_checks || jsonb_build_object('check2_duplicate', jsonb_build_object('verdict', 'duplicate', 'work_id', v_existing));
    v_adm := _refuse_admission(p_workstream, p_candidate, p_route, p_agent, p_session, v_checks, 'duplicate',
                               'identifier already admitted', v_existing);
    RETURN jsonb_build_object('outcome', 'duplicate', 'admission_id', v_adm, 'work_id', v_existing, 'checks', v_checks);
  END IF;
  -- END guard: check 2 identifier lookup

  SELECT count(*) INTO v_strong FROM jsonb_array_elements(coalesce(p_identifiers, '[]'::jsonb)) x
   WHERE x->>'scheme' IN ('doi', 'arxiv', 'isbn', 'pmid', 'pmcid', 'jstor', 'handle');
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
    SELECT f.id INTO v_existing FROM files f WHERE f.sha256 = p_file->>'sha256';
    IF v_existing IS NOT NULL THEN
      v_adm := _refuse_admission(p_workstream, p_candidate, p_route, p_agent, p_session,
                                 v_checks || jsonb_build_object('file_duplicate', v_existing), 'rejected',
                                 'the file is already held (sha256)', NULL);
      RETURN jsonb_build_object('outcome', 'refused', 'refused_at', 'file_duplicate', 'file_id', v_existing,
                                'admission_id', v_adm, 'checks', v_checks);
    END IF;
  END IF;

  v_mode := CASE p_route WHEN 'registry' THEN 'fact' ELSE 'proposal' END;
  BEGIN
    SELECT w.entity_id, w.version_id INTO v_work, v_wver
      FROM _write_version(v_mode, 'work', NULL, jsonb_build_object('key', p_key), NULL,
                          p_work, NULL, p_workstream, p_agent, p_session) w;
    FOR i IN SELECT x FROM jsonb_array_elements(coalesce(p_identifiers, '[]'::jsonb)) x LOOP
      SELECT w.entity_id, w.version_id INTO v_id, v_ver
        FROM _write_version(v_mode, 'identifier', NULL, jsonb_build_object('scheme', i->>'scheme'), NULL,
                            jsonb_build_object('work_id', v_work, 'value', i->>'value', 'verified_by', i->>'verified_by',
                                               'evidence', coalesce(i->'evidence', '{}'::jsonb), 'status', 'active'),
                            NULL, p_workstream, p_agent, p_session) w;
      v_ids := v_ids || to_jsonb(v_id);
    END LOOP;
    IF p_file IS NOT NULL THEN
      SELECT w.entity_id INTO v_file
        FROM _write_version(v_mode, 'file', NULL, jsonb_build_object('sha256', p_file->>'sha256'), NULL,
                            (p_file - 'sha256' - 'status' - 'status_reason')
                              || jsonb_build_object('work_id', v_work, 'status', 'active'),
                            NULL, p_workstream, p_agent, p_session) w;
    END IF;
    INSERT INTO admissions (candidate_id, work_id, route, admitter_agent, admitter_session, state, checks, workstream_id)
    VALUES (p_candidate, v_work, p_route, p_agent, p_session,
            CASE p_route WHEN 'registry' THEN 'admitted' ELSE 'proposed' END, v_checks, p_workstream)
    RETURNING id INTO v_adm;
    UPDATE candidates cd SET state = 'admitted', state_reason = NULL, admitted_work_id = v_work WHERE cd.id = p_candidate;
  EXCEPTION WHEN unique_violation THEN
    -- the second lock: a concurrent admission of the same identifier, key or file won the index
    GET STACKED DIAGNOSTICS v_cname = CONSTRAINT_NAME;
    v_adm := _refuse_admission(p_workstream, p_candidate, p_route, p_agent, p_session,
                               v_checks || jsonb_build_object('collided_on', v_cname), 'rejected',
                               'collided on ' || coalesce(v_cname, 'a unique index'), NULL);
    RETURN jsonb_build_object('outcome', 'collided', 'constraint', v_cname, 'admission_id', v_adm, 'checks', v_checks);
  END;
  RETURN jsonb_build_object('outcome', CASE p_route WHEN 'registry' THEN 'admitted' ELSE 'proposed' END,
                            'admission_id', v_adm, 'work_id', v_work, 'work_version', v_wver,
                            'identifier_ids', v_ids, 'file_id', v_file, 'checks', v_checks);
END
$$;

-- ── approval of a manual admission (check 4) ─────────────────────────────────────────────
-- The approver presents ITS OWN open workstream and token (requiring the admitter's token would force
-- approval into the admitter's worktree). The session sign-off is the 0009 constraint on admissions.
CREATE FUNCTION litkb.approve_admission(p_workstream uuid, p_ws_token text, p_admission uuid,
                                        p_agent text, p_session text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  a record;
  h record;
  t record;
  v_n bigint;
  v_moved jsonb := '[]'::jsonb;
  v_work_moved boolean := false;
BEGIN
  -- BEGIN guard: approve_admission presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: approve_admission presents the workstream token
  PERFORM 1 FROM workstreams w WHERE w.id = p_workstream AND w.state = 'open' FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % is not open', p_workstream USING ERRCODE = '22023';
  END IF;
  SELECT * INTO a FROM admissions ad WHERE ad.id = p_admission FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: no admission %', p_admission USING ERRCODE = 'P0002';
  END IF;
  IF a.route <> 'manual' OR a.state <> 'proposed' THEN
    RAISE EXCEPTION 'litkb: admission % is a % admission in state %; only a proposed manual admission is approved',
      p_admission, a.route, a.state USING ERRCODE = '55000';
  END IF;
  -- the admissions_second_session_signs_off constraint (0009) refuses the admitter's own session (23514)
  UPDATE admissions ad SET state = 'approved', approver_agent = p_agent, approver_session = p_session, approved_at = now()
   WHERE ad.id = p_admission;

  FOR h IN SELECT wh.entity, wh.entity_id, wh.version_id FROM ws_heads wh
            WHERE wh.workstream_id = a.workstream_id
              AND ((wh.entity = 'work' AND wh.entity_id = a.work_id)
                   OR (wh.entity = 'identifier' AND EXISTS (SELECT 1 FROM identifier_versions iv
                                                             WHERE iv.version_id = wh.version_id AND iv.work_id = a.work_id))
                   OR (wh.entity = 'file' AND EXISTS (SELECT 1 FROM file_versions fv
                                                       WHERE fv.version_id = wh.version_id AND fv.work_id = a.work_id)))
            ORDER BY CASE wh.entity WHEN 'work' THEN 0 WHEN 'identifier' THEN 1 ELSE 2 END, wh.entity_id
            FOR UPDATE LOOP
    SELECT * INTO t FROM _entity_tables(h.entity);
    -- BEGIN guard: approval moves main's pointer only from nothing
    EXECUTE format('UPDATE %s SET current_version_id = $1 WHERE id = $2 AND current_version_id IS NULL', t.ident)
      USING h.version_id, h.entity_id;
    -- END guard: approval moves main's pointer only from nothing
    GET DIAGNOSTICS v_n = ROW_COUNT;
    IF v_n <> 1 THEN
      RAISE EXCEPTION 'litkb CAS refused: % % already has a main version', h.entity, h.entity_id USING ERRCODE = '40001';
    END IF;
    EXECUTE format('UPDATE %s SET state = ''promoted'', promoted_at = now() WHERE version_id = $1 AND state = ''proposed''', t.vers)
      USING h.version_id;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    IF v_n <> 1 THEN
      RAISE EXCEPTION 'litkb: % version % is not proposed', h.entity, h.version_id USING ERRCODE = '55000';
    END IF;
    DELETE FROM ws_heads wh WHERE wh.workstream_id = a.workstream_id AND wh.entity = h.entity AND wh.entity_id = h.entity_id;
    PERFORM _refresh_mirrors(h.entity, h.entity_id);
    v_work_moved := v_work_moved OR h.entity = 'work';
    v_moved := v_moved || jsonb_build_object('entity', h.entity, 'id', h.entity_id, 'version', h.version_id);
  END LOOP;
  IF NOT v_work_moved THEN
    RAISE EXCEPTION 'litkb: admission % has no proposed work left in workstream %', p_admission, a.workstream_id
      USING ERRCODE = 'P0002';
  END IF;
  RETURN jsonb_build_object('outcome', 'approved', 'admission_id', p_admission, 'work_id', a.work_id, 'moved', v_moved);
END
$$;

-- ── a file for an admitted work (acquisition, check 3 at attach time) ────────────────────
CREATE FUNCTION litkb.attach_file(p_workstream uuid, p_ws_token text, p_work uuid, p_file jsonb,
                                  p_agent text, p_session text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_title text;
  v_c3 jsonb;
  v_existing record;
  v_file uuid;
  v_ver uuid;
BEGIN
  -- BEGIN guard: attach_file presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: attach_file presents the workstream token
  PERFORM 1 FROM workstreams w WHERE w.id = p_workstream AND w.state = 'open' FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % is not open', p_workstream USING ERRCODE = '22023';
  END IF;
  SELECT v.title INTO v_title FROM works w JOIN work_versions v ON v.version_id = w.current_version_id
   WHERE w.id = p_work FOR SHARE OF w;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: work % is not admitted in main; a file attaches only to an admitted work', p_work
      USING ERRCODE = '55000';
  END IF;
  IF p_file IS NULL OR coalesce(p_file->>'sha256', '') !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'litkb: file must carry a sha256' USING ERRCODE = '22023';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended('litkb:file:' || (p_file->>'sha256'), 0));
  -- BEGIN guard: attach_file sha256 dedupe
  SELECT f.id, fv.work_id INTO v_existing FROM files f LEFT JOIN file_versions fv ON fv.version_id = f.current_version_id
   WHERE f.sha256 = p_file->>'sha256';
  IF FOUND THEN
    RETURN jsonb_build_object('outcome', 'duplicate-file', 'file_id', v_existing.id, 'work_id', v_existing.work_id);
  END IF;
  -- END guard: attach_file sha256 dedupe
  v_c3 := _check_binding(v_title, p_file);
  -- BEGIN guard: attach_file binding
  IF v_c3->>'verdict' <> 'bound' THEN
    RETURN jsonb_build_object('outcome', 'refused', 'binding', v_c3);
  END IF;
  -- END guard: attach_file binding
  SELECT w.entity_id, w.version_id INTO v_file, v_ver
    FROM _write_version('fact', 'file', NULL, jsonb_build_object('sha256', p_file->>'sha256'), NULL,
                        (p_file - 'sha256' - 'status' - 'status_reason') || jsonb_build_object('work_id', p_work, 'status', 'active'),
                        NULL, p_workstream, p_agent, p_session) w;
  RETURN jsonb_build_object('outcome', 'attached', 'file_id', v_file, 'file_version', v_ver, 'binding', v_c3);
END
$$;

-- ── promotion never carries a fact: _ws_chains (0005) with one added hold ───────────────
CREATE OR REPLACE FUNCTION litkb._ws_chains(p_ws uuid)
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

    -- BEGIN guard: a fact chain enters main only through admission approval
    IF h.e IN ('work', 'identifier', 'file') THEN
      v_probs := v_probs || 'admission: a work, identifier or file enters main only through litkb.approve_admission (a proposed manual admission), never through promotion'::text;
    END IF;
    -- END guard: a fact chain enters main only through admission approval

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

-- ── privileges ───────────────────────────────────────────────────────────────────────────
REVOKE EXECUTE ON FUNCTION
  litkb.norm_title(text),
  litkb._title_dup_threshold(),
  litkb._title_duplicates(text, integer),
  litkb._check_registry(text, jsonb, jsonb, boolean),
  litkb._check_binding(text, jsonb),
  litkb._refuse_admission(uuid, uuid, text, text, text, jsonb, text, text, uuid),
  litkb.admit(uuid, text, uuid, text, text, jsonb, jsonb, jsonb, jsonb, text, text),
  litkb.approve_admission(uuid, text, uuid, text, text),
  litkb.attach_file(uuid, text, uuid, jsonb, text, text)
FROM PUBLIC;
-- BEGIN guard: writer executes the admission functions
GRANT EXECUTE ON FUNCTION
  litkb.admit(uuid, text, uuid, text, text, jsonb, jsonb, jsonb, jsonb, text, text),
  litkb.approve_admission(uuid, text, uuid, text, text),
  litkb.attach_file(uuid, text, uuid, jsonb, text, text)
TO litkb_writer;
-- END guard: writer executes the admission functions

-- end of 0013
