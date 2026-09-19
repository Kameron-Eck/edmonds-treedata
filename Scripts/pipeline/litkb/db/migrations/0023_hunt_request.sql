-- litkb 0023 — hunt_request: the drop-off record (WORKPLAN.md "Next phase", missing piece 1).
--
-- A review agent that decides a paper is worth hunting holds, at that moment, identifiers, the
-- CLAIM it expects the paper to support, WHY it is relevant, and the abstract passage it reasoned
-- from. Today that evaporates: it becomes searchable evidence only if and when a LATER session
-- hunts the paper, extracts it and writes a verified use — and nothing records the expectation
-- that motivated the hunt, so a verified use can never be checked against it.
--
-- THE GOVERNING CONSTRAINT (delta, 2026-09-18): litkb exists so that only a quote verified
-- against ingested block bytes counts as evidence. A hunt_request holds the OPPOSITE — an agent's
-- unverified prior. The two must never be confusable:
--
--   1. Resolution state is DERIVED, never free-written. There is no stored resolution_state
--      column anywhere — `hunt_request_status` (below) computes it from joins every time it is
--      read, so "reject a direct write of confirmed" is structural: no writer, no column, exists
--      to accept one. confirmed/contradicted require a LINKED verified-use row
--      (uses.hunt_request_id, nullable FK, link direction use -> request, never reverse);
--      unconfirmed is a linked work with no such use; open is no linked work at all.
--   2. The evidence path (litkb_search's six queries, use.py::locate_quote, _record_use's block
--      SELECT, use_evidence_status, add_evidence, _use_evidence_verify, _ws_chains' evidence
--      clause) never reads expected_claim or abstract_passage. Nothing in this migration touches
--      any of those objects; qc/test_litkb_hunt_request.py asserts it stays that way.
--   3. abstract_passage is unverified by construction (web/registry metadata, not ingested
--      bytes): its COMMENT says so and it is never a quote source.
--
-- WHY NOT `discrepancies` (0015). Read before building this: discrepancies is "a legacy
-- tracker/manifest FIELD disagrees with the admitted REGISTRY record" — two records of the same
-- kind of fact (metadata), reconciled by a comparator ratio, written by the P3 loader. A
-- hunt_request's contradiction is a different shape entirely: an AGENT'S CLAIM about what a paper
-- would show, checked against a VERIFIED QUOTE the paper's own extracted text supports or refutes
-- — no comparator ratio, no legacy source, and the resolver is `stance` on a promotable
-- use_evidence row, not a claimed-vs-registry diff. Reusing discrepancies would also put
-- expectation text on `_work`'s existing discrepancies read path, which is exactly what
-- constraint 2 forbids. record_hunt_request/link_hunt_request/hunt_request_status is a parallel,
-- narrower mechanism for a narrower fact.
--
-- Table shape follows the drop-off CSVs the closed loop already produced by hand
-- (Reports/litkb_improvement_review_{A,B}_2026-09-16.csv, WORKPLAN.md "Improvement reviews"):
-- doi_or_arxiv/title/year/venue -> ref/ref_scheme/claimed_title/claimed_authors/claimed_year;
-- key_claim -> expected_claim; why_useful -> why_relevant; passage -> abstract_passage.

SET LOCAL search_path = litkb, public;

CREATE TABLE hunt_requests (
  id                 uuid PRIMARY KEY DEFAULT uuidv7(),
  workstream_id      uuid NOT NULL REFERENCES workstreams (id),
  ref                text NOT NULL CHECK (ref <> ''),       -- the identifier/URL/citation AS GIVEN
  ref_scheme         text NOT NULL CHECK (ref_scheme IN
                       ('doi', 'arxiv', 'jstor', 'isbn', 'pmid', 'pmcid', 'openalex', 's2',
                        'handle', 'url', 'tracker', 'legacy_stem', 'other')),
  claimed_title      text,
  claimed_authors    text,
  claimed_year       integer,
  expected_claim     text NOT NULL CHECK (expected_claim <> ''),
  why_relevant       text NOT NULL CHECK (why_relevant <> ''),
  abstract_passage   text,                                  -- see COMMENT below: never quotable
  gap_id             uuid REFERENCES gaps (id),
  -- set ONCE, only through link_hunt_request, once `litkb hunt` resolves this request to a work
  work_id            uuid REFERENCES works (id),
  agent              text NOT NULL CHECK (agent <> ''),
  session_id         text NOT NULL CHECK (session_id <> ''),
  created_at         timestamptz NOT NULL DEFAULT now(),
  linked_at          timestamptz,
  linked_by_agent    text,
  linked_by_session  text,
  CONSTRAINT hunt_requests_link_consistency CHECK ((work_id IS NULL) = (linked_at IS NULL)),
  CONSTRAINT hunt_requests_link_labels CHECK (
    (linked_at IS NULL) = (linked_by_agent IS NULL) AND (linked_at IS NULL) = (linked_by_session IS NULL))
);
CREATE INDEX hunt_requests_by_workstream ON hunt_requests (workstream_id);
CREATE INDEX hunt_requests_by_work ON hunt_requests (work_id) WHERE work_id IS NOT NULL;

COMMENT ON TABLE hunt_requests IS
  'The review agent''s drop-off, written BEFORE the full text exists (WORKPLAN.md "Next phase"): '
  'an unverified prior (expected_claim, why_relevant, abstract_passage) that a later verified use '
  'can be checked against. GUARDED RELATION (workstream_id): the only writers are '
  'record_hunt_request (create) and link_hunt_request (name the resolved work, once). Resolution '
  'is read through hunt_request_status, never a column here.';

COMMENT ON COLUMN hunt_requests.abstract_passage IS
  'UNVERIFIED BY CONSTRUCTION: copied from web/registry metadata (an abstract, a search-result '
  'snippet), never ingested block bytes. Never quotable as evidence: litkb_record_use / '
  'add_evidence require a block_id from litkb.blocks, and the evidence path (litkb_search''s six '
  'queries, use_evidence_status, main_uses, _ws_chains'' evidence clause) must never reference '
  'this column or expected_claim (qc/test_litkb_hunt_request.py holds this as a gate, not a '
  'convention).';

COMMENT ON COLUMN hunt_requests.expected_claim IS
  'The agent''s PRIOR at hunt time: what it expected the paper to support. Not evidence, and not '
  'read by anything that serves evidence — hunt_request_status derives resolution_state only from '
  'a LINKED use''s verified, promotable quote (use_evidence.stance), never from this text.';

-- ── uses.hunt_request_id: the link direction is USE -> REQUEST, never reverse ──────────────
ALTER TABLE uses ADD COLUMN hunt_request_id uuid REFERENCES hunt_requests (id);
CREATE INDEX uses_by_hunt_request ON uses (hunt_request_id) WHERE hunt_request_id IS NOT NULL;
COMMENT ON COLUMN uses.hunt_request_id IS
  'Which drop-off, if any, this use circles back to. Set once, at creation, as identity (like '
  'work_id/gap_id) — see litkb._create_identity''s ''use'' case, migration 0023.';

-- ── the two writers (GUARDED RELATION: no agent role holds a direct write on hunt_requests) ─

-- The review agent's drop-off. Deliberately thin: every NOT NULL field the table itself requires
-- is enforced by the table's own CHECK constraints (record_discrepancy's pattern, 0015), so this
-- function adds only the workstream-open check no CHECK constraint can express.
CREATE FUNCTION litkb.record_hunt_request(
  p_workstream uuid, p_ws_token text, p_ref text, p_ref_scheme text, p_expected_claim text,
  p_why_relevant text, p_abstract_passage text, p_claimed_title text, p_claimed_authors text,
  p_claimed_year integer, p_gap uuid, p_agent text, p_session text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_id uuid;
BEGIN
  -- BEGIN guard: record_hunt_request presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: record_hunt_request presents the workstream token
  -- BEGIN guard: record_hunt_request writes only into an open workstream
  PERFORM 1 FROM workstreams w WHERE w.id = p_workstream AND w.state = 'open' FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % is not open', p_workstream USING ERRCODE = '22023';
  END IF;
  -- END guard: record_hunt_request writes only into an open workstream
  INSERT INTO hunt_requests (workstream_id, ref, ref_scheme, expected_claim, why_relevant,
                             abstract_passage, claimed_title, claimed_authors, claimed_year,
                             gap_id, agent, session_id)
  VALUES (p_workstream, p_ref, p_ref_scheme, p_expected_claim, p_why_relevant, p_abstract_passage,
          p_claimed_title, p_claimed_authors, p_claimed_year, p_gap, p_agent, p_session)
  RETURNING id INTO v_id;
  RETURN v_id;
END
$$;

-- Named by `litkb hunt` / `litkb_hunt` once a reference resolves to a work (any ladder rung —
-- held, bound-unextracted or extracted: linking records WHICH work, not that extraction finished;
-- hunt_request_status reads the real extraction state itself). Narrow and idempotent, shaped like
-- hold_candidate (0016): it may set work_id only once, and only to a work this workstream can see.
CREATE FUNCTION litkb.link_hunt_request(
  p_workstream uuid, p_ws_token text, p_hunt_request uuid, p_work uuid, p_agent text,
  p_session text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_done boolean := false;
BEGIN
  -- BEGIN guard: link_hunt_request presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: link_hunt_request presents the workstream token
  IF coalesce(btrim(p_agent), '') = '' OR coalesce(btrim(p_session), '') = '' THEN
    RAISE EXCEPTION 'litkb: link_hunt_request needs an agent and a session' USING ERRCODE = '22023';
  END IF;
  -- BEGIN guard: link_hunt_request names a work this workstream can see
  PERFORM 1 FROM ws_works w WHERE w.view_workstream_id = p_workstream AND w.work_id = p_work;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: work % is not visible to workstream %', p_work, p_workstream
      USING ERRCODE = '42501';
  END IF;
  -- END guard: link_hunt_request names a work this workstream can see
  -- BEGIN guard: link_hunt_request touches only this workstream's request, and sets work_id once
  UPDATE hunt_requests hr SET work_id = p_work, linked_at = now(),
         linked_by_agent = p_agent, linked_by_session = p_session
   WHERE hr.id = p_hunt_request AND hr.workstream_id = p_workstream
     AND (hr.work_id IS NULL OR hr.work_id = p_work);
  -- END guard: link_hunt_request touches only this workstream's request, and sets work_id once
  GET DIAGNOSTICS v_done = ROW_COUNT;
  IF NOT v_done THEN
    PERFORM 1 FROM hunt_requests hr WHERE hr.id = p_hunt_request AND hr.workstream_id = p_workstream;
    IF FOUND THEN
      RAISE EXCEPTION 'litkb: hunt request % is already linked to a different work', p_hunt_request
        USING ERRCODE = '55000';
    END IF;
    RAISE EXCEPTION 'litkb: hunt request % is not workstream %''s', p_hunt_request, p_workstream
      USING ERRCODE = '42501';
  END IF;
  RETURN true;
END
$$;

-- ── _create_identity: a use's identity may name the request it circles back to ────────────
-- CREATE OR REPLACEs the 0003 definition (never touched since; no other open branch redefines
-- it — checked against every work/* and fix/* ref at HEAD, 2026-09-18). Adds ONE allowed identity
-- key for 'use' and the ownership check that goes with it; every other branch is untouched.
CREATE OR REPLACE FUNCTION litkb._create_identity(p_entity text, p_identity jsonb, p_fields jsonb, p_workstream uuid)
RETURNS uuid LANGUAGE plpgsql SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_id uuid;
  v_allowed text[];
  v_bad text[];
  v_hr uuid;
BEGIN
  v_allowed := CASE p_entity
    WHEN 'work' THEN ARRAY['key'] WHEN 'identifier' THEN ARRAY['scheme'] WHEN 'file' THEN ARRAY['sha256']
    WHEN 'gap' THEN ARRAY['slug'] WHEN 'use' THEN ARRAY['work_id', 'gap_id', 'hunt_request_id'] END;
  SELECT array_agg(k) INTO v_bad FROM jsonb_object_keys(coalesce(p_identity, '{}'::jsonb)) k
   WHERE NOT (k = ANY (v_allowed));
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'litkb: % identity takes only %, got %', p_entity, v_allowed, v_bad USING ERRCODE = '22023';
  END IF;
  -- BEGIN guard: a use naming a hunt_request may only name one of its own workstream's
  IF p_entity = 'use' AND (p_identity->>'hunt_request_id') IS NOT NULL THEN
    v_hr := (p_identity->>'hunt_request_id')::uuid;
    PERFORM 1 FROM hunt_requests hr WHERE hr.id = v_hr AND hr.workstream_id = p_workstream;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'litkb: hunt request % is not workstream %''s', v_hr, p_workstream USING ERRCODE = '42501';
    END IF;
  END IF;
  -- END guard: a use naming a hunt_request may only name one of its own workstream's
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
      INSERT INTO uses (work_id, gap_id, hunt_request_id, created_in_ws)
      VALUES ((p_identity->>'work_id')::uuid, (p_identity->>'gap_id')::uuid, v_hr, p_workstream) RETURNING id INTO v_id;
  END CASE;
  RETURN v_id;
END
$$;

-- ── resolution state, DERIVED (no stored column exists to write) ──────────────────────────
-- open         hr.work_id IS NULL: not yet ingested.
-- unconfirmed  hr.work_id IS NOT NULL and no linked use carries promotable supporting/refuting
--              evidence: hunt/ingest may be done, nothing has circled back yet.
-- confirmed    a use with u.hunt_request_id = hr.id, read at its HEAD version in hr's OWN
--              workstream (ws_uses, the same "this workstream's view" every other read uses),
--              carries a use_evidence row that is promotable (use_evidence_status: verified AND
--              anchored in the file's current run, §4.5) with stance = 'supports'.
-- contradicted the same, stance = 'refutes'. Wins over confirmed if a request has both: a
--              conflict between two verified uses is exactly the case discrepancies (0015) never
--              silently drops, and this mechanism doesn't either.
CREATE VIEW hunt_request_status AS
  SELECT hr.*,
         coalesce(agg.n_confirming, 0)    AS n_confirming,
         coalesce(agg.n_contradicting, 0) AS n_contradicting,
         CASE
           WHEN coalesce(agg.n_contradicting, 0) > 0 THEN 'contradicted'
           WHEN coalesce(agg.n_confirming, 0) > 0     THEN 'confirmed'
           WHEN hr.work_id IS NOT NULL                THEN 'unconfirmed'
           ELSE 'open'
         END AS resolution_state
    FROM hunt_requests hr
    LEFT JOIN LATERAL (
      SELECT count(*) FILTER (WHERE ues.promotable AND ues.stance = 'supports') AS n_confirming,
             count(*) FILTER (WHERE ues.promotable AND ues.stance = 'refutes')  AS n_contradicting
        FROM uses u
        JOIN ws_uses wu ON wu.view_workstream_id = hr.workstream_id AND wu.use_id = u.id
        JOIN use_evidence_status ues ON ues.use_version_id = wu.version_id
       WHERE u.hunt_request_id = hr.id
    ) agg ON true;

COMMENT ON VIEW hunt_request_status IS
  'Resolution state is DERIVED, never free-written: there is no stored resolution_state column '
  'anywhere for an agent role to set — this view computes it fresh from hunt_requests.work_id and '
  'promotable use_evidence on a linked use, every read. confirmed/contradicted therefore cannot be '
  'reached without a linked, verified-use row (gate 1, qc/test_litkb_hunt_request.py).';

-- ── privileges ───────────────────────────────────────────────────────────────────────────
REVOKE EXECUTE ON FUNCTION
  litkb.record_hunt_request(uuid, text, text, text, text, text, text, text, text, integer, uuid, text, text),
  litkb.link_hunt_request(uuid, text, uuid, uuid, text, text)
FROM PUBLIC;
-- BEGIN guard: writer executes record_hunt_request/link_hunt_request and holds no direct write on hunt_requests
GRANT EXECUTE ON FUNCTION
  litkb.record_hunt_request(uuid, text, text, text, text, text, text, text, text, integer, uuid, text, text),
  litkb.link_hunt_request(uuid, text, uuid, uuid, text, text)
TO litkb_writer;
-- END guard: writer executes record_hunt_request/link_hunt_request and holds no direct write on hunt_requests
GRANT SELECT ON hunt_requests, hunt_request_status TO litkb_reader, litkb_writer, litkb_ingest;

-- end of 0023
