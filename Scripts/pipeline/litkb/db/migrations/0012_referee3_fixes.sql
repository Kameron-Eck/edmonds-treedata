-- litkb 0012 — fixes after the third P1 referee (Reports/LITKB_P1_REFEREE3_2026-09-13.md, F-2 and F-3).
-- Applied migrations are checksum-locked, so this file REPLACES two functions defined earlier. The live
-- definitions of abandon_workstream (0010) and add_use_embedding (0011) are the ones below; the earlier
-- bodies are history, and a mutation of them is dead code. CREATE OR REPLACE with the same signature
-- keeps each function's EXECUTE grants (the writer's), so no GRANT is repeated here.
--
--   F-2  abandon_workstream locks the workstream row FOR UPDATE (the lock promote_prepare and
--        promote_commit take) and refuses (55000) while the workstream has a prepared promotion. Before
--        this, a session could abandon a workstream whose prepared report was already on the branch Kam
--        reviews: commit was then refused (not open), rebase was refused (not merged), and the chain was
--        stranded (the D-2 stranding by another door).
--   F-3  add_use_embedding mirrors add_evidence: FOR SHARE on the workstream row, which waits for a
--        prepare or commit in flight; the workstream must be open (22023); the use version must belong
--        to it (42501) and be proposed (55000). Before this, a session holding its own token could put an
--        unreviewed vector on main's promoted version, also after its workstream was merged or abandoned,
--        and occupy that (use_version_id, model) slot so the indexer's write failed 23505.

SET LOCAL search_path = litkb, public;

CREATE OR REPLACE FUNCTION litkb.abandon_workstream(p_workstream uuid, p_ws_token text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
BEGIN
  -- BEGIN guard: abandon_workstream presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: abandon_workstream presents the workstream token
  -- BEGIN guard: abandon locks the workstream row
  -- waits for a promote_prepare in flight, so the check below sees the promotion it inserts
  PERFORM 1 FROM workstreams w WHERE w.id = p_workstream FOR UPDATE;
  -- END guard: abandon locks the workstream row
  -- BEGIN guard: no abandon while a promotion is prepared
  PERFORM 1 FROM promotions pr WHERE pr.workstream_id = p_workstream AND pr.state = 'prepared';
  IF FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % has a prepared promotion; commit or abandon the promotion before abandoning the workstream', p_workstream
      USING ERRCODE = '55000';
  END IF;
  -- END guard: no abandon while a promotion is prepared
  UPDATE workstreams w SET state = 'abandoned', closed_at = now()
   WHERE w.id = p_workstream AND w.state = 'open';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % is not open', p_workstream USING ERRCODE = '22023';
  END IF;
END
$$;

CREATE OR REPLACE FUNCTION litkb.add_use_embedding(
  p_workstream uuid, p_ws_token text, p_use_version uuid, p_model text, p_dim integer, p_vector halfvec)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v record;
BEGIN
  -- BEGIN guard: add_use_embedding presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: add_use_embedding presents the workstream token
  -- BEGIN guard: embedding workstream open
  PERFORM 1 FROM workstreams ws WHERE ws.id = p_workstream AND ws.state = 'open' FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % is not open', p_workstream USING ERRCODE = '22023';
  END IF;
  -- END guard: embedding workstream open
  SELECT uv.workstream_id AS ws, uv.state AS st INTO v FROM use_versions uv WHERE uv.version_id = p_use_version;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: no use version %', p_use_version USING ERRCODE = 'P0002';
  END IF;
  -- BEGIN guard: embedding version belongs to the workstream
  IF v.ws IS DISTINCT FROM p_workstream THEN
    RAISE EXCEPTION 'litkb: use version % belongs to another workstream', p_use_version USING ERRCODE = '42501';
  END IF;
  -- END guard: embedding version belongs to the workstream
  -- BEGIN guard: embedding version is proposed
  IF v.st IS DISTINCT FROM 'proposed' THEN
    RAISE EXCEPTION 'litkb: use version % is %, an embedding is added only to a proposed version', p_use_version, v.st
      USING ERRCODE = '55000';
  END IF;
  -- END guard: embedding version is proposed
  INSERT INTO use_embeddings (use_version_id, model, dim, vector)
  VALUES (p_use_version, p_model, p_dim, p_vector);
END
$$;

-- end of 0012
