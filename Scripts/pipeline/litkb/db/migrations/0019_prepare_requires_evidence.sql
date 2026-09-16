-- litkb 0019 — a use reaches `prepared` only on VERIFIED evidence.
--
-- The convention says "a use with no verifiable quote is refused at prepare". It was not true, and
-- the referee did not read that from the SQL — he ran it: a use with ZERO use_evidence rows reached
-- `prepared` in the same promotion as five others (Reports/LITKB_P8_REFEREE_2026-09-15.md §3.6,
-- prediction P3 CONFIRMED; the linkage review had met the same thing as §8.2).
--
-- The mechanism is one clause. 0005:78-85, unchanged in 0013:575-582, counts the evidence rows that
-- are NOT promotable:
--
--     SELECT count(*) INTO v_bad FROM use_evidence_status s
--      WHERE s.use_version_id = ANY (v_ids) AND NOT s.promotable;
--     IF v_bad > 0 THEN … 'evidence: %s row(s) unverified …'
--
-- Zero rows is zero BAD rows, so a claim with no quote at all passed a check written to catch a
-- claim with a bad quote. Below, the chain is held unless it has at least one row and EVERY row is
-- promotable — one count of the promotable rows covers both halves. `no-verified-evidence` is the
-- reason word the access layer and the promotion report use for it.
--
-- What this invalidates, stated rather than discovered later: every use written before stage 5
-- exists carries no evidence row, including the 15 the linkage review wrote. They are not deleted
-- and not altered — they simply stop being promotable until a verified quote is attached, which is
-- what the convention always claimed was already happening.
--
-- Written and applied on the ACCESS branch against litkb_test / the harness workers only. litkb
-- itself applies it at Kam's merge (Reports/LITKB_P8_ACCESS_2026-09-15.md §7).

SET LOCAL search_path = litkb, public;

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
  v_good integer;
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
      -- BEGIN guard: a use is prepared only on at least one verified evidence row
      -- 0019. Counting the PROMOTABLE rows is what covers both halves at once: no rows at all, and
      -- rows that are all unverified, both leave v_good = 0. The v_bad clause above stays, because
      -- a use with one good quote and one bad one must still say which.
      SELECT count(*) INTO v_good FROM use_evidence_status s
       WHERE s.use_version_id = ANY (v_ids) AND s.promotable;
      IF v_good = 0 THEN
        v_probs := v_probs || 'no-verified-evidence: a use is a claim about a work, and a claim reaches main only on a quote the database verified. Record one with litkb_record_use.'::text;
      END IF;
      -- END guard: a use is prepared only on at least one verified evidence row
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
