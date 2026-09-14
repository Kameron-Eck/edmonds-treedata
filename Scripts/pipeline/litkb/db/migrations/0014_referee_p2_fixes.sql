-- litkb 0014 — fixes after the P2 referee (Reports/LITKB_P2_REFEREE_2026-09-14.md, D1-D7).
-- Applied migrations are checksum-locked, so this file REPLACES functions and constraints defined earlier.
-- The live definitions of norm_identifier (0003), _check_binding, admit and approve_admission (0013) and of the
-- admissions label constraints (0009) are the ones below; the earlier texts are history, and a mutation of them is
-- dead code. CREATE OR REPLACE with the same signature keeps each function's EXECUTE grants.
--
--   D1  ONE DOI normaliser. norm_identifier('doi', v): remove every invisible character (the class of norm_label),
--       lower-case ASCII letters only, cut everything before the first '10.', strip trailing / . , ; :
--       Its Python twin is litkb.textnorm.normalize_doi; qc/test_litkb_p2.py drives both over
--       qc/testdata/litkb_p2/doi_forms.csv. admit() stores the normalised DOI as the identifier's value, and
--       refuses a DOI that normalises to '' (no '10.'). Percent-encoded DOIs are not decoded.
--   D2  _check_binding also requires the evidence of the D2 binding rule: the title was sought only in the title
--       region (title_region) and the first author was a whole token near it (author_near_title).
--   D3  approve_admission locks the ADMITTER's workstream row FOR SHARE and requires it open, so an abandon in
--       flight makes approval wait (and then refuse), and an approval in flight makes abandon wait.
--   D5  a key collision between different works takes the convention's a/b year suffix
--       (Scripts/docs/LITERATURE_CONVENTION.md): the second work is <Surname>_<year>a_<slug>, the third ..b_..;
--       a fourth still collides.
--   D6  the file sha256 lookup in admit() carries guard markers (the harness row R9 removes it).
--   D7  session and agent labels are compared after norm_label() removes every invisible character (Unicode
--       whitespace and format characters: NBSP, zero-width, BOM, Zs/Zl/Zp/Cf), wherever they occur. Case is kept
--       (0009 E-4). Its Python twin is litkb.textnorm.norm_label.
--
-- The existing rows are checked first: the migration refuses (and names them) if any stored DOI's value_norm is
-- not already canonical, or if two works carry DOIs that are equal under the new rule. Nothing is merged.

SET LOCAL search_path = litkb, public;

-- ── D7 / D1: the invisible-character class ───────────────────────────────────────────────
-- Generated from litkb.textnorm.INVISIBLE_RANGES (Python 3.12, Unicode 15.0: isspace or category Zs/Zl/Zp/Cf).
-- The same literal is inlined in norm_identifier: a SQL function that called norm_label would need EXECUTE on it
-- for every role that may call norm_identifier (qc/test_litkb_p1.py _EXPECTED_EXECUTE).
CREATE FUNCTION litkb.norm_label(p_label text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
  -- BEGIN guard: labels lose invisible characters (SQL)
  SELECT regexp_replace(p_label, '[	--  ­؀-؅؜۝܏࢐-࢑࣢ ᠎ -‏ -  -⁤⁦-⁯　﻿￹-￻\U000110BD\U000110CD\U00013430-\U0001343F\U0001BCA0-\U0001BCA3\U0001D173-\U0001D17A\U000E0001\U000E0020-\U000E007F]', '', 'g')
  -- END guard: labels lose invisible characters (SQL)
$$;

CREATE OR REPLACE FUNCTION litkb.norm_identifier(p_scheme text, p_value text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
  SELECT CASE p_scheme
    -- DOIs: invisible characters removed, ASCII lower-cased, cut to the first '10.', trailing / . , ; : stripped
    -- (0014 D1; twin: litkb.textnorm.normalize_doi)
    WHEN 'doi'   THEN regexp_replace(
                        coalesce(substring(
                          translate(
                            regexp_replace(p_value, '[	--  ­؀-؅؜۝܏࢐-࢑࣢ ᠎ -‏ -  -⁤⁦-⁯　﻿￹-￻\U000110BD\U000110CD\U00013430-\U0001343F\U0001BCA0-\U0001BCA3\U0001D173-\U0001D17A\U000E0001\U000E0020-\U000E007F]', '', 'g'),
                            'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')
                          from '10\..*$'), ''),
                        '[/.,;:]+$', '')
    -- arXiv ids with the version suffix stripped (§4.6 check 2)
    WHEN 'arxiv' THEN regexp_replace(regexp_replace(lower(btrim(p_value)), '^arxiv:', ''), 'v[0-9]+$', '')
    ELSE btrim(p_value)
  END
$$;

-- ── the existing rows, before anything relies on the new rule ───────────────────────────
DO $$
DECLARE
  v_bad text;
BEGIN
  SELECT string_agg(format('%s (value_norm %s, canonical %s)', i.id, i.value_norm, litkb.norm_identifier('doi', i.value_norm)), '; ')
    INTO v_bad
    FROM litkb.identifiers i
   WHERE i.scheme = 'doi' AND i.value_norm IS DISTINCT FROM litkb.norm_identifier('doi', i.value_norm);
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'litkb 0014: stored DOIs are not canonical under the D1 rule; merge them by hand first: %', v_bad;
  END IF;
  SELECT string_agg(format('%s -> works %s', d.norm, d.works), '; ')
    INTO v_bad
    FROM (SELECT litkb.norm_identifier('doi', v.value) AS norm, array_agg(DISTINCT v.work_id::text) AS works
            FROM litkb.identifier_versions v JOIN litkb.identifiers i ON i.id = v.identifier_id
           WHERE i.scheme = 'doi' AND v.status = 'active'
           GROUP BY 1 HAVING count(DISTINCT v.work_id) > 1) d;
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'litkb 0014: works already duplicate under the D1 DOI rule; merge them by hand first: %', v_bad;
  END IF;
END
$$;

-- ── D7: the label constraints (0009) compare without invisible characters ──────────────
ALTER TABLE admissions DROP CONSTRAINT admissions_admitter_not_blank;
-- BEGIN guard: admitter labels non-blank after invisible characters are removed
ALTER TABLE admissions ADD CONSTRAINT admissions_admitter_not_blank CHECK (
  litkb.norm_label(admitter_agent) <> '' AND litkb.norm_label(admitter_session) <> '');
-- END guard: admitter labels non-blank after invisible characters are removed

ALTER TABLE admissions DROP CONSTRAINT admissions_second_session_signs_off;
ALTER TABLE admissions ADD CONSTRAINT admissions_second_session_signs_off CHECK (
  (approver_agent IS NULL AND approver_session IS NULL AND approved_at IS NULL)
  OR (approver_agent IS NOT NULL AND approver_session IS NOT NULL AND approved_at IS NOT NULL
      AND litkb.norm_label(approver_agent) <> ''
      AND litkb.norm_label(approver_session) <> ''
      AND litkb.norm_label(approver_session) <> litkb.norm_label(admitter_session)));

-- ── D2: check 3 re-checks the evidence of the region and author-near rule ───────────────
CREATE OR REPLACE FUNCTION litkb._check_binding(p_work_title text, p_file jsonb)
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

-- ── admission (0013 with D1, D5 and D6) ──────────────────────────────────────────────────
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
        SELECT w.entity_id, w.version_id INTO v_id, v_ver
          FROM _write_version(v_mode, 'identifier', NULL, jsonb_build_object('scheme', i->>'scheme'), NULL,
                              jsonb_build_object('work_id', v_work,
                                                 -- D1: the canonical DOI is the stored value
                                                 'value', CASE WHEN i->>'scheme' = 'doi' THEN norm_identifier('doi', i->>'value')
                                                               ELSE i->>'value' END,
                                                 'verified_by', i->>'verified_by',
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
                            'identifier_ids', v_ids, 'file_id', v_file, 'checks', v_checks);
END
$$;

-- ── approval of a manual admission (0013 with D3) ────────────────────────────────────────
CREATE OR REPLACE FUNCTION litkb.approve_admission(p_workstream uuid, p_ws_token text, p_admission uuid,
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
  -- BEGIN guard: approve_admission locks the admitter's workstream open
  -- FOR SHARE waits for an abandon in flight (it holds FOR UPDATE) and re-reads the row, so an abandon that commits
  -- first leaves nothing to lock; an approval in flight makes abandon_workstream wait instead
  PERFORM 1 FROM workstreams w WHERE w.id = a.workstream_id AND w.state = 'open' FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: admission % was proposed in workstream %, which is not open; it cannot be approved',
      p_admission, a.workstream_id USING ERRCODE = '22023';
  END IF;
  -- END guard: approve_admission locks the admitter's workstream open
  -- the admissions_second_session_signs_off constraint (0014) refuses the admitter's own session (23514)
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

REVOKE EXECUTE ON FUNCTION litkb.norm_label(text) FROM PUBLIC;

-- end of 0014
