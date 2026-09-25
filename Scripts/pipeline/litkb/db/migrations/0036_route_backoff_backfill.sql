-- litkb 0036 — the reviewed backfill that seeds `route_backoff` from the ledger's history (LITKB_WORKPLAN.md
-- "### S4.5" item 1; the S4.5 fix wave, builder FX-S item 1; referee-substrate note N1).
--
-- WHY. 0033 made the per-(route, work) refusal ladder PERSISTED (`route_backoff`, guard 2), and the ladder's one
-- writer moves a row only on an attempt it makes (`litkb.acquire.run._move_backoff` -> record_route_backoff). The
-- ledger's refusals from BEFORE 0033 were never replayed into it, so for a pair whose earlier refusal predates the
-- table the in-run skip rule (`run._skip_reason` -> `backoff.load`) reads a ladder that never saw that refusal,
-- while the gated counter `rehunt_route_spends` replays the WHOLE ledger with the reference policy. MEASURED
-- (referee-substrate §2, and builder FX-S's read of live as litkb_reader, 2026-09-24): 10 open_access pairs stored
-- 1 refusal / a 15 min window where the reference replay gives 2 / 6 h, and 21 scihub pairs hold refusals the
-- table has no row for at all. A re-hunt inside the replayed window is ALLOWED by the enforcement and COUNTED by
-- the gate.
--
-- WHAT CHANGES. One ingest-only function, `litkb.backfill_route_backoff(session, source, rows)`, in the reviewed-
-- backfill family 0033 began (`backfill_attempt_sub_status`, `backfill_file_word_count`: ingest role, no token —
-- system operations on history — one `acquisition_backfills` row per applied run). The caller computes each
-- state (litkb.acquire.backoff.BackoffPolicy.replay over the pair's whole ledger history: the ONE home of the
-- rule, the same replay the gate runs); the database checks what it can check without a second copy of the rule:
--   * the cited attempt is a work attempt and is the pair's LATEST attempt (so the state is as of the newest fact,
--     and a plan made before a newer attempt arrived is refused per row, never applied);
--   * the state is a refusal state (refusals >= 1, a window start no later than the cited attempt and a
--     next-allowed instant after the window start): a backfill never writes a reset, which is the absence of a
--     row;
--   * the row's `last_*` facts are the attempt that last MOVED the row (the caller's `moved_attempt_id`,
--     litkb.acquire.backoff.BackoffPolicy.last_mover — the ladder's writer rule), which must be an attempt of the
--     SAME pair, not after the cited one, and never a skip (S4.5 decision D56, integrator-w4, before this migration
--     was applied anywhere but worker databases; auditor-FX-S F2: citing the latest attempt wrote a
--     `skipped/policy_refused` row into `last_*` for 13 of the 21 no_row pairs on live, against SCHEMAS' "the
--     attempt that last moved the row");
--   * an older attempt never rolls a row back (the same rule record_route_backoff keeps, for a writer that moved
--     the row between the check above and this write).
-- `acquisition_backfills.op` gains the value `route_backoff`.
--
-- NOT DONE HERE: no row is written by the migration itself. The orchestrator runs the op live, dry run first
-- (`py -3.12 -m litkb.acquire.backoff backfill --session <label> --out <plan.csv>`, then `--apply --csv <plan.csv>`).
-- Numbered 0036 with nothing to reserve (pipeline/litkb/db/migrations/_reserved.txt says why and what was checked).

SET LOCAL search_path = litkb, public;

-- ── the decision log gains the op ───────────────────────────────────────────────────────────
ALTER TABLE acquisition_backfills DROP CONSTRAINT acquisition_backfills_op_check;
ALTER TABLE acquisition_backfills ADD CONSTRAINT acquisition_backfills_op_check
  CHECK (op IN ('sub_status', 'word_count', 'route_backoff'));
COMMENT ON TABLE acquisition_backfills IS
  'One row per APPLIED reviewed backfill run (0033; op route_backoff 0036): which op, which session, which source '
  '(the CSV path and its sha256), how many rows were offered and applied, and why the rest were not. Written only by '
  'backfill_attempt_sub_status, backfill_file_word_count and backfill_route_backoff.';

-- ── the backfill ────────────────────────────────────────────────────────────────────────────
-- p_rows: [{"attempt_id": uuid, "moved_attempt_id": uuid, "refusals": int, "window_started_at": timestamptz,
--           "next_allowed_at": timestamptz}, ...] — one per (route, work) pair; `attempt_id` (the pair's latest attempt)
-- names the pair, `moved_attempt_id` the attempt whose facts the row's `last_*` columns carry.
CREATE FUNCTION litkb.backfill_route_backoff(p_session text, p_source text, p_rows jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  r jsonb;
  a record;
  mv record;
  v_mover_ok boolean;
  v_n integer;
  v_refusals integer;
  v_start timestamptz;
  v_next timestamptz;
  v_latest boolean;
  v_state_ok boolean;
  v_offered integer := 0;
  v_applied integer := 0;
  v_missing integer := 0;
  v_not_latest integer := 0;
  v_bad_state integer := 0;
  v_newer integer := 0;
  v_bad_mover integer := 0;
  v_id uuid;
BEGIN
  IF coalesce(btrim(p_session), '') = '' OR coalesce(btrim(p_source), '') = '' THEN
    RAISE EXCEPTION 'litkb: a backfill needs a session and a source' USING ERRCODE = '22023';
  END IF;
  IF p_rows IS NULL OR jsonb_typeof(p_rows) <> 'array' THEN
    RAISE EXCEPTION 'litkb: backfill rows must be a JSON array' USING ERRCODE = '22023';
  END IF;
  FOR r IN SELECT * FROM jsonb_array_elements(p_rows) LOOP
    v_offered := v_offered + 1;
    SELECT x.id, x.route, x.work_id, x.status, x.http_codes, x.at INTO a
      FROM acquisition_attempts x WHERE x.id = (r->>'attempt_id')::uuid;
    IF NOT FOUND OR a.work_id IS NULL THEN
      v_missing := v_missing + 1;
      CONTINUE;
    END IF;
    v_latest := true;             -- the unguarded default: any attempt of the pair may carry the state
    -- BEGIN guard: a backfilled state is the state as of the pair's latest attempt
    v_latest := NOT EXISTS (
      SELECT 1 FROM acquisition_attempts y
       WHERE y.route = a.route AND y.work_id = a.work_id AND (y.at, y.id) > (a.at, a.id));
    -- END guard: a backfilled state is the state as of the pair's latest attempt
    IF NOT v_latest THEN
      v_not_latest := v_not_latest + 1;
      CONTINUE;
    END IF;
    v_refusals := (r->>'refusals')::integer;
    v_start := (r->>'window_started_at')::timestamptz;
    v_next := (r->>'next_allowed_at')::timestamptz;
    v_state_ok := true;           -- the unguarded default: whatever state the caller sends is written
    -- BEGIN guard: a backfill writes a refusal state only
    v_state_ok := coalesce(v_refusals, 0) >= 1 AND v_start IS NOT NULL AND v_next IS NOT NULL
                  AND v_start <= a.at AND v_next > v_start;
    -- END guard: a backfill writes a refusal state only
    IF NOT v_state_ok THEN
      v_bad_state := v_bad_state + 1;
      CONTINUE;
    END IF;
    mv := a;                      -- the unguarded default: the cited (latest) attempt's facts, a skip included
    v_mover_ok := true;
    -- BEGIN guard: a backfilled row's last facts are the attempt that last moved it, never a skip
    SELECT m.id, m.route, m.work_id, m.status, m.http_codes, m.at INTO mv
      FROM acquisition_attempts m
     WHERE m.id = (r->>'moved_attempt_id')::uuid AND m.route = a.route AND m.work_id = a.work_id
       AND (m.at, m.id) <= (a.at, a.id)
       AND m.status NOT IN ('skipped', 'budget-stop', 'manual-step', 'quota-stop');
    v_mover_ok := FOUND;
    -- END guard: a backfilled row's last facts are the attempt that last moved it, never a skip
    IF NOT v_mover_ok THEN
      v_bad_mover := v_bad_mover + 1;
      CONTINUE;
    END IF;
    INSERT INTO route_backoff AS b (route, work_id, refusals, window_started_at, next_allowed_at,
                                    last_attempt_id, last_status, last_http_codes, last_at, updated_at)
    VALUES (a.route, a.work_id, coalesce(v_refusals, 0), v_start, v_next, mv.id, mv.status, mv.http_codes, mv.at,
            now())
    ON CONFLICT (route, work_id) DO UPDATE
       SET refusals = EXCLUDED.refusals, window_started_at = EXCLUDED.window_started_at,
           next_allowed_at = EXCLUDED.next_allowed_at, last_attempt_id = EXCLUDED.last_attempt_id,
           last_status = EXCLUDED.last_status, last_http_codes = EXCLUDED.last_http_codes,
           last_at = EXCLUDED.last_at, updated_at = now()
     -- record_route_backoff's rule: an older attempt never rolls the row back (here it holds against a writer
     -- that moved the row after the latest-attempt check above, in the same instant; not separately tested)
     WHERE b.last_at <= EXCLUDED.last_at;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    IF v_n = 1 THEN
      v_applied := v_applied + 1;
    ELSE
      v_newer := v_newer + 1;
    END IF;
  END LOOP;
  INSERT INTO acquisition_backfills (op, session, source, offered, applied, skipped)
  VALUES ('route_backoff', p_session, p_source, v_offered, v_applied,
          jsonb_build_object('missing', v_missing, 'not_latest', v_not_latest, 'bad_state', v_bad_state,
                             'bad_mover', v_bad_mover, 'newer_row', v_newer))
  RETURNING id INTO v_id;
  RETURN jsonb_build_object('backfill_id', v_id, 'offered', v_offered, 'applied', v_applied,
                            'missing', v_missing, 'not_latest', v_not_latest, 'bad_state', v_bad_state,
                            'bad_mover', v_bad_mover, 'newer_row', v_newer);
END
$$;

-- ── privileges ──────────────────────────────────────────────────────────────────────────────
REVOKE EXECUTE ON FUNCTION litkb.backfill_route_backoff(text, text, jsonb) FROM PUBLIC;
-- the ingest login alone backfills the refusal ladder (qc/test_litkb_p1.py's role matrix holds it)
GRANT EXECUTE ON FUNCTION litkb.backfill_route_backoff(text, text, jsonb) TO litkb_ingest;

-- end of 0036
