-- litkb 0034 — adjudication: the refuse verb, the decision log, withdraw_version, the batched
-- approval of a lone proposed file version, and the operator-bind gate (LITKB_WORKPLAN.md "### S4.5"
-- item 1; decisions.yaml `litkb-from-file-version-state`; S4.5 builder-B2).
--
-- WHY. Until this migration ONE verb moved a proposal: `approve_admission` (0014). A proposed
-- manual admission could be approved or left proposed for ever — there was no way to say no
-- (live 2026-09-23: 194's `Center_2015_ortho-image15c-point-gis`, proposed by `s3-wrap-hunts-2`,
-- 34 h old and still proposed, because nothing could refuse it). And the version tables' states
-- `rejected` and `withdrawn` (0001) had NO writer in any migration (grep, survey-code §3.2): the
-- schema had a place to record a reversed decision and no verb reached it.
--
-- RELAYED DESIGN, UNVALIDATED (CLAUDE.md §3.4c). The shape is round 4's
-- (Reports/LITKB_LOOP_ENGINEERING_SURVEY_2026-09-22.md §1.8 R1/R2/R4): the refuse verb is approve's
-- guards with the pointer loop replaced, an append-only decision log sits beside it, and the
-- two-session rule is litkb's own (§1.8: the largest open bibliographic database does NOT enforce
-- two-person review; litkb's rule is stricter and is not weakened by analogy). Where this file
-- departs from the survey, it says so at the object.
--
-- WHAT IT ADDS
--   admissions.state 'declined'   the REVIEWER's refusal of a proposed manual admission. NOT
--                                 'refused': 0013's `_refuse_admission` already owns that word for
--                                 the MACHINE's check failure (survey §1.8 R2), and the 18 live
--                                 `refused` rows mean "the checks said no", never "a reviewer said no".
--   litkb.adjudications           the append-only decision log: who (workstream, agent, session)
--                                 decided which verb, when, on which admission or version, why.
--   litkb.refuse_admission        the refuse verb (a SECOND session): the admission -> 'declined', its
--                                 proposed work/identifier/file versions -> 'rejected', its
--                                 workstream heads removed. Nothing in main moves.
--   litkb.withdraw_version        the proposer retracts its OWN proposal -> 'withdrawn'.
--   litkb.decide_file_versions    approve or refuse, BATCHED, lone proposed FILE versions on works
--                                 already in main (`approve_admission` cannot move one: it requires
--                                 the admission's WORK to move from nothing, survey-code §5.1).
--   litkb.attach_file             re-created from 0013 with ONE added guard: a file whose
--                                 source_route is an operator's (`browser` = `acquire --from-file`,
--                                 `held-in-place` = `--from-file` of a topic-folder file) or a web
--                                 landing (`web`) is written as a PROPOSAL, never as the version of
--                                 record (`litkb-from-file-version-state`, Kam 2026-09-22).
--
-- THE TWO-SESSION RULE, two places, one per verb family:
--   approve_admission  the 0014 constraint `admissions_second_session_signs_off` (unchanged);
--   refuse_admission, decide_file_versions  the constraint `adjudications_second_session_decides`
--                      on the decision row every call writes — the row is written in the SAME
--                      transaction as the state change, so a refused row rolls the change back.
--   The Python front (`litkb.admit.front`) compares the labels again before it calls, after
--   invisible characters are removed (the 0014 D7 rule): "both guards" of the plan.
--
-- NOT DONE HERE, deliberately: the decision log does NOT back-fill or duplicate `approve_admission`'s
-- decisions — those already live on the admissions row (approver_agent/approver_session/approved_at,
-- 0001), and one fact has one home (CLAUDE.md §3.3). survey §1.8 R3 (per-field provenance) and the
-- `reopen` verb of R2 are not built (the plan's item 1 names neither).
--
-- THE 17 HISTORICAL OPERATOR BINDS (live: 6 `browser`, 11 `held-in-place`, all `promoted`) are not
-- touched: S4.5 decision D8 reports them as `operator_binds_historical` and never retro-demotes them.

SET LOCAL search_path = litkb, public;

-- ── admissions: the reviewer's refusal is 'declined' ─────────────────────────────────────
-- 0001's column CHECK (auto-named admissions_state_check) is widened by one word; the manual-route
-- rule follows it, and a declined admission can only be a manual one (only a proposal is refused).
ALTER TABLE admissions DROP CONSTRAINT admissions_state_check;
ALTER TABLE admissions ADD CONSTRAINT admissions_state_check
  CHECK (state IN ('admitted', 'proposed', 'approved', 'refused', 'declined'));
ALTER TABLE admissions DROP CONSTRAINT admissions_manual_is_a_proposal;
ALTER TABLE admissions ADD CONSTRAINT admissions_manual_is_a_proposal
  CHECK (route <> 'manual' OR state IN ('proposed', 'approved', 'refused', 'declined'));
ALTER TABLE admissions ADD CONSTRAINT admissions_declined_is_manual
  CHECK (state <> 'declined' OR route = 'manual');

-- ── the decision log ─────────────────────────────────────────────────────────────────────
-- One row per decision. Subject: an ADMISSION (verb 'refuse' only — an admission's approval is
-- recorded on the admissions row itself, see the header) or a VERSION (entity + version_id).
-- `versions` lists every version row the decision changed, so the log alone says what moved.
-- `decided_by` is the LOGIN (session_user: inside a SECURITY DEFINER function current_user is the
-- owner — 0031 run_retirement_ops.retired_by, same reason); agent/session_id are the labels.
CREATE TABLE adjudications (
  id                  uuid PRIMARY KEY DEFAULT uuidv7(),
  verb                text NOT NULL CHECK (verb IN ('approve', 'refuse', 'withdraw')),
  admission_id        uuid REFERENCES admissions (id),
  entity              text CHECK (entity IN ('work', 'identifier', 'file', 'gap', 'use')),
  version_id          uuid,
  versions            jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(versions) = 'array'),
  proposer_workstream uuid NOT NULL REFERENCES workstreams (id),
  proposer_agent      text NOT NULL,
  proposer_session    text NOT NULL,
  reason              text,
  workstream_id       uuid NOT NULL REFERENCES workstreams (id),
  agent               text NOT NULL,
  session_id          text NOT NULL,
  decided_by          text NOT NULL DEFAULT session_user,
  decided_at          timestamptz NOT NULL DEFAULT now(),
  -- (the two guard constraints come first and each carries its own comma, so deleting either block —
  -- the mutation rows' known-bad — leaves a table that still parses)
  -- BEGIN guard: the proposing session never decides its own proposal
  CONSTRAINT adjudications_second_session_decides CHECK (
    verb = 'withdraw' OR litkb.norm_label(session_id) <> litkb.norm_label(proposer_session)),
  -- END guard: the proposing session never decides its own proposal
  -- BEGIN guard: only the proposer's own workstream withdraws its proposal
  CONSTRAINT adjudications_withdraw_is_the_proposers CHECK (
    verb <> 'withdraw' OR workstream_id = proposer_workstream),
  -- END guard: only the proposer's own workstream withdraws its proposal
  CONSTRAINT adjudications_one_subject CHECK (
    (admission_id IS NOT NULL AND entity IS NULL AND version_id IS NULL)
    OR (admission_id IS NULL AND entity IS NOT NULL AND version_id IS NOT NULL)),
  CONSTRAINT adjudications_admission_is_refused_only CHECK (admission_id IS NULL OR verb = 'refuse'),
  CONSTRAINT adjudications_labels_not_blank CHECK (
    litkb.norm_label(agent) <> '' AND litkb.norm_label(session_id) <> ''),
  -- a refusal and a withdrawal say why; an approval may (the reviewer's note), and need not
  CONSTRAINT adjudications_reason_given CHECK (
    verb = 'approve' OR litkb.norm_label(coalesce(reason, '')) <> '')
);
CREATE INDEX adjudications_by_admission ON adjudications (admission_id) WHERE admission_id IS NOT NULL;
CREATE INDEX adjudications_by_version ON adjudications (version_id) WHERE version_id IS NOT NULL;

COMMENT ON TABLE adjudications IS
  'The append-only decision log (LITKB_WORKPLAN.md S4.5 item 1; migration 0034): refuse / approve / '
  'withdraw, who decided, when, on which admission or version, why. GUARDED RELATION: no role holds '
  'INSERT, UPDATE or DELETE; written only by refuse_admission, withdraw_version and '
  'decide_file_versions; a trigger refuses UPDATE, DELETE and TRUNCATE even to the owner. '
  'docs/SCHEMAS.md "litkb.adjudications".';

-- Append-only for EVERYONE, the owner included: the grants below keep every agent role out, and this
-- trigger keeps the migration runner out too — a decision is corrected by a NEW decision, never by
-- rewriting the old one (survey §1.8 R1 kill criterion: "deleting or overwriting any earlier review
-- row -> RED"). Granted to nobody; a trigger function needs no EXECUTE at fire time.
CREATE FUNCTION litkb._adjudications_append_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = litkb, public, pg_temp AS $$
BEGIN
  RAISE EXCEPTION 'litkb: the decision log is append-only; % on litkb.adjudications is refused', TG_OP
    USING ERRCODE = '42501';
END
$$;
-- BEGIN guard: the decision log refuses UPDATE, DELETE and TRUNCATE to every role
CREATE TRIGGER adjudications_append_only BEFORE UPDATE OR DELETE ON adjudications
  FOR EACH ROW EXECUTE FUNCTION litkb._adjudications_append_only();
CREATE TRIGGER adjudications_no_truncate BEFORE TRUNCATE ON adjudications
  FOR EACH STATEMENT EXECUTE FUNCTION litkb._adjudications_append_only();
-- END guard: the decision log refuses UPDATE, DELETE and TRUNCATE to every role

-- ── the operator-bind gate's route list: ONE home ─────────────────────────────────────────
-- The source routes whose file is a PROPOSAL (a second session approves it), never the version of
-- record. `browser`: `acquire --from-file` landing a copy (acquire.run.land_and_attach);
-- `held-in-place`: `acquire --from-file` of a file already in a topic folder
-- (acquire.run.attach_in_place) — the two routes of `litkb-from-file-version-state`. `web`: a URL
-- landing offered to an existing work after its own admission was refused as a duplicate
-- (hunt._offer_refused_landing); a web source is a manual proposal on every other path (admit_web).
-- Granted to nobody; qc/test_litkb_adjudicate.py holds the Python mirrors equal to it.
CREATE FUNCTION litkb._proposal_source_routes() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT ARRAY['browser', 'held-in-place', 'web']::text[] $$;

-- ── a file for an admitted work: 0013's body, plus the operator-bind gate ───────────────
-- Byte for byte 0013's definition except `v_mode` and the guard that sets it. The 0013 text of this
-- function is DEAD from here on; the mutation rows on its guards point here
-- (qc/instruments/litkb_p2_mutations.py, the B2 block). CREATE OR REPLACE keeps the 0013 ACL.
CREATE OR REPLACE FUNCTION litkb.attach_file(p_workstream uuid, p_ws_token text, p_work uuid, p_file jsonb,
                                             p_agent text, p_session text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_title text;
  v_c3 jsonb;
  v_existing record;
  v_file uuid;
  v_ver uuid;
  -- the default is the unguarded one, so removing the guard below leaves code that RUNS and binds
  -- the file as the version of record — the known-bad `operator_binds_unproposed` counts — rather
  -- than an error the harness would report as DID NOT FIRE (CLAUDE.md §3.4c)
  v_mode text := 'fact';
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
  -- BEGIN guard: an operator-supplied file is a proposal, never the version of record
  IF coalesce(p_file->>'source_route', '') = ANY (_proposal_source_routes()) THEN
    v_mode := 'proposal';
  END IF;
  -- END guard: an operator-supplied file is a proposal, never the version of record
  SELECT w.entity_id, w.version_id INTO v_file, v_ver
    FROM _write_version(v_mode, 'file', NULL, jsonb_build_object('sha256', p_file->>'sha256'), NULL,
                        (p_file - 'sha256' - 'status' - 'status_reason') || jsonb_build_object('work_id', p_work, 'status', 'active'),
                        NULL, p_workstream, p_agent, p_session) w;
  -- `outcome` stays 'attached' (the bytes are bound and owned by a version row either way, and
  -- acquire.run reads only that word); `state` says whether main can see it yet
  RETURN jsonb_build_object('outcome', 'attached', 'file_id', v_file, 'file_version', v_ver, 'binding', v_c3,
                            'state', CASE v_mode WHEN 'proposal' THEN 'proposed' ELSE 'promoted' END);
END
$$;

-- ── the refuse verb: a second session declines a proposed manual admission ──────────────
-- approve_admission's guards (0014) with the pointer loop REPLACED: nothing in main moves. Every
-- proposed version of the admission's work, identifiers and files in the admitter's workstream
-- (the whole chain, head to its base) becomes 'rejected', and the admitter's heads for them are
-- removed, so the refused proposal leaves the workstream's view and promote_prepare never meets it.
-- DEPARTS from survey §1.8 R2 ("versions stay proposed … nothing moves"): the plan's item 1 makes
-- this verb the writer of the dead `rejected` state, so the versions move and the admission is not
-- re-openable by a verb here (a reopen is not built — the report names it).
CREATE FUNCTION litkb.refuse_admission(p_workstream uuid, p_ws_token text, p_admission uuid, p_reason text,
                                       p_agent text, p_session text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  a record;
  h record;
  t record;
  v record;
  v_cur uuid;
  v_n bigint;
  v_moved jsonb := '[]'::jsonb;
  v_log uuid;
BEGIN
  -- BEGIN guard: refuse_admission presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: refuse_admission presents the workstream token
  PERFORM 1 FROM workstreams w WHERE w.id = p_workstream AND w.state = 'open' FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % is not open', p_workstream USING ERRCODE = '22023';
  END IF;
  SELECT * INTO a FROM admissions ad WHERE ad.id = p_admission FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: no admission %', p_admission USING ERRCODE = 'P0002';
  END IF;
  -- BEGIN guard: only a proposed manual admission is refused
  IF a.route <> 'manual' OR a.state <> 'proposed' THEN
    RAISE EXCEPTION 'litkb: admission % is a % admission in state %; only a proposed manual admission is refused',
      p_admission, a.route, a.state USING ERRCODE = '55000';
  END IF;
  -- END guard: only a proposed manual admission is refused
  -- BEGIN guard: refuse_admission locks the admitter's workstream open
  PERFORM 1 FROM workstreams w WHERE w.id = a.workstream_id AND w.state = 'open' FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: admission % was proposed in workstream %, which is not open; it cannot be refused',
      p_admission, a.workstream_id USING ERRCODE = '22023';
  END IF;
  -- END guard: refuse_admission locks the admitter's workstream open
  UPDATE admissions ad SET state = 'declined' WHERE ad.id = p_admission;

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
    v_cur := h.version_id;
    LOOP
      EXIT WHEN v_cur IS NULL;
      EXECUTE format('SELECT based_on_version_id AS b, workstream_id AS w, state AS s FROM %s WHERE version_id = $1 FOR UPDATE',
                     t.vers) INTO v USING v_cur;
      EXIT WHEN v.w IS DISTINCT FROM a.workstream_id OR v.s IS DISTINCT FROM 'proposed';
      -- BEGIN guard: a refused admission's proposed versions become rejected
      EXECUTE format('UPDATE %s SET state = ''rejected'' WHERE version_id = $1 AND state = ''proposed''', t.vers)
        USING v_cur;
      -- END guard: a refused admission's proposed versions become rejected
      v_moved := v_moved || jsonb_build_object('entity', h.entity, 'id', h.entity_id, 'version', v_cur,
                                               'from', 'proposed', 'to', 'rejected');
      -- (without the step below the loop re-reads the head it just rejected and exits: the base of a
      -- longer chain is left `proposed` — a known-bad that answers worse, never an endless loop. No
      -- API writes such a chain for an admission's work today — write_proposal takes gap/use, admit
      -- and attach_file write version 1 — so the walk is pinned by an owner-level CONSTRUCTED chain,
      -- qc/test_litkb_adjudicate.py)
      -- BEGIN guard: a refused admission's chain is walked from its head to its base
      v_cur := v.b;
      -- END guard: a refused admission's chain is walked from its head to its base
    END LOOP;
    -- BEGIN guard: a refused proposal leaves its workstream's view
    DELETE FROM ws_heads wh WHERE wh.workstream_id = a.workstream_id AND wh.entity = h.entity AND wh.entity_id = h.entity_id;
    -- END guard: a refused proposal leaves its workstream's view
  END LOOP;

  -- the decision row LAST and in the same transaction: adjudications_second_session_decides refuses
  -- the admitter's own session (23514), and that refusal rolls back every change above
  INSERT INTO adjudications (verb, admission_id, versions, proposer_workstream, proposer_agent, proposer_session,
                             reason, workstream_id, agent, session_id)
  VALUES ('refuse', p_admission, v_moved, a.workstream_id, a.admitter_agent, a.admitter_session,
          p_reason, p_workstream, p_agent, p_session)
  RETURNING id INTO v_log;
  RETURN jsonb_build_object('outcome', 'declined', 'admission_id', p_admission, 'work_id', a.work_id,
                            'rejected', v_moved, 'decision_id', v_log);
END
$$;

-- ── withdraw_version: the proposer retracts its own proposal ─────────────────────────────
-- Only a `proposed` version, only the workstream's HEAD for its entity (withdraw from the top of a
-- chain down), only from the workstream that proposed it (the token proves which), and never a
-- version an OPEN manual admission proposed — that proposal is adjudicated by approve_admission or
-- refuse_admission, and withdrawing a piece of it would leave approve with nothing to move. The
-- head falls back to the version it was based on when that is this workstream's own proposal;
-- otherwise the head is removed and the workstream sees main again. DEPARTS from survey §1.8 R4
-- (which withdraws a PROMOTED version and moves main's pointer back): the brief's verb is the
-- proposer's retraction; nothing in main moves here.
CREATE FUNCTION litkb.withdraw_version(p_workstream uuid, p_ws_token text, p_entity text, p_version uuid,
                                       p_reason text, p_agent text, p_session text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  t record;
  v record;
  v_base_ws uuid;
  v_base_state text;
  v_work uuid;
  v_head uuid;
  v_log uuid;
  v_n bigint;
  v_now text;
  v_fallback boolean;
BEGIN
  -- BEGIN guard: withdraw_version presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: withdraw_version presents the workstream token
  PERFORM 1 FROM workstreams w WHERE w.id = p_workstream AND w.state = 'open' FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % is not open', p_workstream USING ERRCODE = '22023';
  END IF;
  SELECT * INTO t FROM _entity_tables(p_entity);
  EXECUTE format('SELECT %I AS eid, workstream_id AS w, state AS s, based_on_version_id AS b, agent AS ag, '
                 'session_id AS se FROM %s WHERE version_id = $1 FOR UPDATE', t.fk, t.vers)
    INTO v USING p_version;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  IF v_n <> 1 THEN
    RAISE EXCEPTION 'litkb: no % version %', p_entity, p_version USING ERRCODE = 'P0002';
  END IF;
  -- (the workstream rule is the decision log's constraint adjudications_withdraw_is_the_proposers)
  -- BEGIN guard: only a proposed version is withdrawn
  IF v.s IS DISTINCT FROM 'proposed' THEN
    RAISE EXCEPTION 'litkb: % version % is %, not proposed; only a proposal is withdrawn', p_entity, p_version, v.s
      USING ERRCODE = '55000';
  END IF;
  -- END guard: only a proposed version is withdrawn
  IF p_entity IN ('work', 'identifier', 'file') THEN
    EXECUTE format('SELECT work_id FROM %s WHERE version_id = $1', t.vers) INTO v_work USING p_version;
  END IF;
  -- BEGIN guard: a version an open admission proposed is adjudicated, not withdrawn
  IF v_work IS NOT NULL AND EXISTS (SELECT 1 FROM admissions ad
                                     WHERE ad.work_id = v_work AND ad.route = 'manual' AND ad.state = 'proposed'
                                       AND ad.workstream_id = v.w) THEN
    RAISE EXCEPTION 'litkb: % version % belongs to a proposed manual admission; a second session approves or refuses it',
      p_entity, p_version USING ERRCODE = '55000';
  END IF;
  -- END guard: a version an open admission proposed is adjudicated, not withdrawn
  SELECT wh.version_id INTO v_head FROM ws_heads wh
   WHERE wh.workstream_id = v.w AND wh.entity = p_entity AND wh.entity_id = v.eid FOR UPDATE;
  -- BEGIN guard: a proposal is withdrawn from its head down
  IF v_head IS DISTINCT FROM p_version THEN
    RAISE EXCEPTION 'litkb: % version % is not its workstream''s head (the head is %); withdraw the head first',
      p_entity, p_version, coalesce(v_head::text, 'none') USING ERRCODE = '55000';
  END IF;
  -- END guard: a proposal is withdrawn from its head down
  EXECUTE format('UPDATE %s SET state = ''withdrawn'' WHERE version_id = $1 AND state = ''proposed''', t.vers)
    USING p_version;
  IF v.b IS NOT NULL THEN
    EXECUTE format('SELECT workstream_id, state FROM %s WHERE version_id = $1', t.vers) INTO v_base_ws, v_base_state
      USING v.b;
  END IF;
  v_fallback := v.b IS NOT NULL;
  -- (a base that is MAIN's version — promoted, or another workstream's — is not this workstream's to hold: pinning
  -- the head to it would freeze the workstream's view at that version while main moves on, so the head is removed
  -- and the view follows main again; qc/test_litkb_adjudicate.py withdraws an edit of a PROMOTED gap). "This
  -- workstream's own proposal" is the set 0019's `_ws_chains` walks: `proposed` AND `prepared` — a version a
  -- promotion has taken but not committed is still the workstream's chain, and removing the head over it orphaned
  -- it from every view, chain and verb (auditor-B2 round 3 F1; integrator-w2)
  -- BEGIN guard: a withdrawn head falls back only to this workstream's own proposal, else the head is removed
  v_fallback := v_fallback AND v_base_ws IS NOT DISTINCT FROM v.w
                AND coalesce(v_base_state IN ('proposed', 'prepared'), false);
  -- END guard: a withdrawn head falls back only to this workstream's own proposal, else the head is removed
  IF v_fallback THEN
    UPDATE ws_heads wh SET version_id = v.b
     WHERE wh.workstream_id = v.w AND wh.entity = p_entity AND wh.entity_id = v.eid;
    v_now := v.b::text;
  ELSE
    DELETE FROM ws_heads wh WHERE wh.workstream_id = v.w AND wh.entity = p_entity AND wh.entity_id = v.eid;
  END IF;
  INSERT INTO adjudications (verb, entity, version_id, versions, proposer_workstream, proposer_agent, proposer_session,
                             reason, workstream_id, agent, session_id)
  VALUES ('withdraw', p_entity, p_version,
          jsonb_build_array(jsonb_build_object('entity', p_entity, 'id', v.eid, 'version', p_version,
                                               'from', 'proposed', 'to', 'withdrawn')),
          v.w, v.ag, v.se, p_reason, p_workstream, p_agent, p_session)
  RETURNING id INTO v_log;
  RETURN jsonb_build_object('outcome', 'withdrawn', 'entity', p_entity, 'entity_id', v.eid, 'version', p_version,
                            'head', v_now, 'decision_id', v_log);
END
$$;

-- ── decide_file_versions: a second session approves or refuses lone proposed file versions ─
-- BATCHED (`litkb-from-file-version-state`: "approvals BATCHED so one headless session clears
-- many"), ALL OR NOTHING: one refused version refuses the whole call, and the caller's dry run
-- (`litkb approve-files --dry-run`) lists what would refuse before anything is sent. Each version
-- must be `proposed`, on a work ALREADY in main (a proposal whose work is not in main is an
-- admission: approve_admission / refuse_admission), its workstream's head, and its workstream
-- open (D3, as approve_admission). approve moves main's file pointer by compare-and-set from the
-- version it was based on; refuse moves nothing in main. One decision row per version.
CREATE FUNCTION litkb.decide_file_versions(p_workstream uuid, p_ws_token text, p_verb text, p_versions uuid[],
                                           p_reason text, p_agent text, p_session text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  fv record;
  v_head uuid;
  v_n bigint;
  v_seen integer := 0;
  v_out jsonb := '[]'::jsonb;
  v_log uuid;
BEGIN
  -- BEGIN guard: decide_file_versions presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: decide_file_versions presents the workstream token
  PERFORM 1 FROM workstreams w WHERE w.id = p_workstream AND w.state = 'open' FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % is not open', p_workstream USING ERRCODE = '22023';
  END IF;
  IF p_verb IS NULL OR p_verb NOT IN ('approve', 'refuse') THEN
    RAISE EXCEPTION 'litkb: the verb is approve or refuse, got %', p_verb USING ERRCODE = '22023';
  END IF;
  IF p_versions IS NULL OR cardinality(p_versions) = 0 THEN
    RAISE EXCEPTION 'litkb: no file versions named' USING ERRCODE = '22023';
  END IF;
  FOR fv IN SELECT v.version_id, v.file_id, v.work_id, v.state, v.based_on_version_id, v.workstream_id,
                   v.agent, v.session_id
              FROM file_versions v
             WHERE v.version_id = ANY (p_versions)
             ORDER BY v.version_id
               FOR UPDATE OF v LOOP
    v_seen := v_seen + 1;
    -- BEGIN guard: a lone file version is decided only on a work already in main
    PERFORM 1 FROM works w WHERE w.id = fv.work_id AND w.current_version_id IS NOT NULL FOR SHARE OF w;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'litkb: file version % belongs to work %, which is not in main; that is an admission, decided by approve_admission or refuse_admission',
        fv.version_id, fv.work_id USING ERRCODE = '55000';
    END IF;
    -- END guard: a lone file version is decided only on a work already in main
    -- BEGIN guard: decide_file_versions locks the proposer's workstream open
    PERFORM 1 FROM workstreams w WHERE w.id = fv.workstream_id AND w.state = 'open' FOR SHARE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'litkb: file version % was proposed in workstream %, which is not open', fv.version_id,
        fv.workstream_id USING ERRCODE = '22023';
    END IF;
    -- END guard: decide_file_versions locks the proposer's workstream open
    SELECT wh.version_id INTO v_head FROM ws_heads wh
     WHERE wh.workstream_id = fv.workstream_id AND wh.entity = 'file' AND wh.entity_id = fv.file_id FOR UPDATE;
    -- BEGIN guard: only its workstream's proposed head is decided
    -- (one guard, not two: a file chain is never `prepared` — promote_prepare holds every fact chain — so a
    -- non-proposed file version is never a head, and a separate state check could not fire on its own)
    IF fv.state <> 'proposed' OR v_head IS DISTINCT FROM fv.version_id THEN
      RAISE EXCEPTION 'litkb: file version % is %, and its workstream''s head is %; only a proposed head is decided',
        fv.version_id, fv.state, coalesce(v_head::text, 'none') USING ERRCODE = '55000';
    END IF;
    -- END guard: only its workstream's proposed head is decided
    IF p_verb = 'approve' THEN
      -- BEGIN guard: file approval moves main's pointer only from the version it was based on
      UPDATE files f SET current_version_id = fv.version_id
       WHERE f.id = fv.file_id AND f.current_version_id IS NOT DISTINCT FROM fv.based_on_version_id;
      GET DIAGNOSTICS v_n = ROW_COUNT;
      IF v_n <> 1 THEN
        RAISE EXCEPTION 'litkb CAS refused: file % is no longer at version %', fv.file_id,
          coalesce(fv.based_on_version_id::text, '(none)') USING ERRCODE = '40001';
      END IF;
      -- END guard: file approval moves main's pointer only from the version it was based on
      UPDATE file_versions v SET state = 'promoted', promoted_at = now()
       WHERE v.version_id = fv.version_id AND v.state = 'proposed';
    ELSE
      UPDATE file_versions v SET state = 'rejected' WHERE v.version_id = fv.version_id AND v.state = 'proposed';
    END IF;
    DELETE FROM ws_heads wh WHERE wh.workstream_id = fv.workstream_id AND wh.entity = 'file' AND wh.entity_id = fv.file_id;
    PERFORM _refresh_mirrors('file', fv.file_id);
    INSERT INTO adjudications (verb, entity, version_id, versions, proposer_workstream, proposer_agent,
                               proposer_session, reason, workstream_id, agent, session_id)
    VALUES (p_verb, 'file', fv.version_id,
            jsonb_build_array(jsonb_build_object('entity', 'file', 'id', fv.file_id, 'version', fv.version_id,
                                                 'from', 'proposed',
                                                 'to', CASE p_verb WHEN 'approve' THEN 'promoted' ELSE 'rejected' END)),
            fv.workstream_id, fv.agent, fv.session_id, p_reason, p_workstream, p_agent, p_session)
    RETURNING id INTO v_log;
    v_out := v_out || jsonb_build_object('file_id', fv.file_id, 'work_id', fv.work_id, 'version', fv.version_id,
                                         'decision_id', v_log);
  END LOOP;
  -- the loop meets only the versions that EXIST: a named id with no row (a typo) would otherwise be
  -- skipped and the rest decided — the only guard, since the CLI sends explicit ids as given
  -- BEGIN guard: decide_file_versions refuses the batch when a named version does not exist
  IF v_seen <> (SELECT count(DISTINCT x) FROM unnest(p_versions) x) THEN
    RAISE EXCEPTION 'litkb: % of the % distinct file versions named exist; nothing is decided', v_seen,
      (SELECT count(DISTINCT x) FROM unnest(p_versions) x) USING ERRCODE = 'P0002';
  END IF;
  -- END guard: decide_file_versions refuses the batch when a named version does not exist
  RETURN jsonb_build_object('outcome', CASE p_verb WHEN 'approve' THEN 'approved' ELSE 'refused' END,
                            'decided', v_out);
END
$$;

-- ── privileges ───────────────────────────────────────────────────────────────────────────
REVOKE ALL ON adjudications FROM PUBLIC;
GRANT SELECT ON adjudications TO litkb_reader, litkb_writer, litkb_promoter;
REVOKE EXECUTE ON FUNCTION
  litkb._adjudications_append_only(),
  litkb._proposal_source_routes(),
  litkb.refuse_admission(uuid, text, uuid, text, text, text),
  litkb.withdraw_version(uuid, text, text, uuid, text, text, text),
  litkb.decide_file_versions(uuid, text, text, uuid[], text, text, text)
FROM PUBLIC;
-- BEGIN guard: writer executes the adjudication verbs
GRANT EXECUTE ON FUNCTION
  litkb.refuse_admission(uuid, text, uuid, text, text, text),
  litkb.withdraw_version(uuid, text, text, uuid, text, text, text),
  litkb.decide_file_versions(uuid, text, text, uuid[], text, text, text)
TO litkb_writer;
-- END guard: writer executes the adjudication verbs

-- end of 0034
