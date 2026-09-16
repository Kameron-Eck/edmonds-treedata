-- litkb 0018 — the access layer's three database-side fixes (Reports/LITKB_P8_REFEREE_2026-09-15.md
-- F-1, F-3, and §2.4's search miss). Every one of them is a database fact the MCP server cannot
-- hold for itself:
--
--   1. check_ws_token()  — the READ tools may now present the worktree's token (referee §3.2: a
--      forged token in a `.litkb-workstream` naming a PUBLISHED workstream id read that
--      workstream's candidates, admissions, attempts and promotions). _require_ws_token(uuid,text)
--      cannot be called by an agent role: it is REVOKEd from PUBLIC (0010:81) and it reads
--      litkb.workstream_tokens, which is REVOKEd from every agent role (0010:63). So the check the
--      reader needs is a SECURITY DEFINER wrapper that returns a BOOLEAN and nothing else — no row,
--      no hash, no slug — and is granted to reader and writer only.
--
--   2. _feeds_token_ok() — the convention names SEVEN feeds forms (docs/LITERATURE_CONVENTION.md,
--      "Feeds token vocabulary (doc-qualified, 2026-09-13)"); 0005:17 enforced three. A session
--      following the convention wrote a use that would not promote and found out at prepare
--      (referee §3.6). The vocabulary is the convention's; the enforcement is brought up to it
--      rather than the convention cut down to the enforcement, because `report <FILE>#§<loc>` is
--      what records "what was this used for" for a report-level use, which is the field's purpose.
--
--   3. norm_search_text() — ONE normaliser for litkb_search, applied to the indexed text and to the
--      query alike (referee §2.4: the gold passage was reachable only by a caller who already knew
--      the extractor had rendered `misclassification` as `misclassi<FFFD>cation` and hyphenated
--      `overesti- mate` across a line break). It lives here, not in Python, for the reason
--      migration 0014 D1 gives about norm_identifier: a normaliser applied on one side in Python
--      and on the other in SQL is two definitions that drift. This is a RETRIEVAL-side repair only;
--      the real fix is upstream in P4/P5's text layer, and the block still stores what the PDF said.

SET LOCAL search_path = litkb, public;

-- ── 1. the read tools' token check ───────────────────────────────────────────────────────

-- BEGIN guard: read tools may verify a workstream token without reading its hash
CREATE FUNCTION litkb.check_ws_token(p_ws uuid, p_token text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
  -- coalesce: an unknown workstream and a NULL token are both FALSE, never NULL — a caller that
  -- treats NULL as "no opinion" would be exactly the bypass 0010 closed for the write path.
  SELECT coalesce((SELECT t.token_hash = encode(sha256(convert_to(p_token, 'UTF8')), 'hex')
                     FROM workstream_tokens t WHERE t.workstream_id = p_ws), false)
$$;
-- END guard: read tools may verify a workstream token without reading its hash
COMMENT ON FUNCTION litkb.check_ws_token(uuid, text) IS
  'Does this token open this workstream? TRUE/FALSE only. SECURITY DEFINER because no agent role may '
  'read litkb.workstream_tokens (0010). The write path keeps _require_ws_token, which RAISEs; this is '
  'for the read tools, which must refuse without having written anything.';
REVOKE EXECUTE ON FUNCTION litkb.check_ws_token(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION litkb.check_ws_token(uuid, text) TO litkb_reader, litkb_writer;

-- The promoter may READ the chains it just prepared, so that `promote prepare` can write the
-- promotion report the skill has always promised (referee F-5). A GRANT on _ws_chains alone is not
-- enough — it calls _entity_tables, which is revoked too — and granting a helper chain one function
-- at a time widens more than the caller needs. So this is one SECURITY DEFINER wrapper: STABLE, no
-- writes, the same rows, and EXECUTE for litkb_promoter only. Reader and writer still cannot call
-- either it or _ws_chains, which is what keeps a tool from reading another workstream's chains.
CREATE FUNCTION litkb.promotion_chains(p_ws uuid)
RETURNS TABLE (entity text, entity_id uuid, head uuid, base uuid, conflict boolean,
               version_ids uuid[], states text[], promotion_ids uuid[], evidence_ids uuid[],
               deps text[], problems text[])
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
  SELECT * FROM litkb._ws_chains(p_ws)
$$;
COMMENT ON FUNCTION litkb.promotion_chains(uuid) IS
  'What `promote prepare` prepared and what it HELD, for the promotion report (0018, referee F-5). '
  'The promoter''s read-only view of _ws_chains; no agent role may execute it.';
REVOKE EXECUTE ON FUNCTION litkb.promotion_chains(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION litkb.promotion_chains(uuid) TO litkb_promoter;

-- ── 2. the feeds vocabulary, all seven forms ─────────────────────────────────────────────

-- BEGIN guard: feeds tokens are the convention's seven doc-qualified forms
CREATE OR REPLACE FUNCTION litkb._feeds_token_ok(p_token text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT coalesce(p_token ~ (
      '^('
      -- a heading in FRAMEWORK_GAPS_SPATIOTEMPORAL_CONSISTENCY_2026-09-11.md; at most one sub-level
      || 'framework §[0-9]+(\.[0-9]+)?'
      -- a heading in MATH_NARRATIVE_SPATIOTEMPORAL_CONSISTENCY_2026-09-12.md; integer only
      || '|narrative §[0-9]+'
      -- a `## Gate N` heading in GATED_PLAN_SPATIOTEMPORAL_CONSISTENCY_2026-09-12.md
      || '|gated-plan gate [0-9]+'
      -- a heading in LIT_REVIEW_SPATIOTEMPORAL_CONSISTENCY_2026-09-10.md; any depth
      || '|review §[0-9]+(\.[0-9]+)*'
      -- a row of the framework's §11 gap ledger
      || '|gap row [0-9]+'
      -- a key in Scripts/decisions.yaml
      || '|decision [a-z0-9][a-z0-9-]*'
      -- any other tracked report: `report <FILE>#§<loc>`, loc alphanumeric (a heading key, or
      -- L<line> when the citation sits outside any heading)
      || '|report [^ ]+#§[A-Za-z0-9][A-Za-z0-9._-]*'
      || ')$'), false)
$$;
-- END guard: feeds tokens are the convention's seven doc-qualified forms
COMMENT ON FUNCTION litkb._feeds_token_ok(text) IS
  'The feeds vocabulary of docs/LITERATURE_CONVENTION.md, all seven forms (0018; 0005 enforced three '
  'of them, which held the skill''s own example token — referee F-3). Whether the section, gate, row or '
  'decision a token names EXISTS is checked against the target document, not here.';

-- ── 3. one search normaliser, for the indexed text and the query alike ───────────────────

-- BEGIN guard: search normalises the extractor's damage on both sides
CREATE FUNCTION litkb.norm_search_text(p_text text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
  SELECT regexp_replace(
           regexp_replace(
             -- U+FFFD (a ligature the text layer could not render) and U+00AD (a soft hyphen)
             -- carry no information; dropping them turns `misclassi<FFFD>cation` into
             -- `misclassication`, which trigram-matches the real word instead of nothing.
             -- chr(), not a string literal: U+00AD is an INVISIBLE character, and the last thing
             -- this repository needs is another guard whose literal nobody can see (the
             -- CRLF bytes committed inside a comparison literal, 2026-09-15). Greppable.
             translate(coalesce(p_text, ''), chr(65533) || chr(173), ''),
             -- a hyphen followed by whitespace is a LINE-BREAK hyphenation: `overesti- mate` ->
             -- `overestimate`. A hyphen inside a word (`multi-state`) is left alone, on both
             -- sides, so it still tokenises the way it always did.
             '-[ \t\r\n]+', '', 'g'),
           '[ \t\r\n]+', ' ', 'g')
$$;
-- END guard: search normalises the extractor's damage on both sides
COMMENT ON FUNCTION litkb.norm_search_text(text) IS
  'Retrieval-side repair of the PDF text layer (referee §2.4): drop U+FFFD/U+00AD, join line-break '
  'hyphenation, collapse whitespace. Applied to the block text and to the query in the same statement '
  'so the two can never drift. The blocks themselves still store what the PDF said; the real fix is '
  'upstream in P4/P5.';
-- litkb_ingest too, and not because it searches: the expression INDEX below calls this
-- function, and an index expression is evaluated as the role doing the INSERT. Without this
-- grant stage 5's ingest fails with `permission denied for function norm_search_text` the
-- moment it writes a block — which is how qc/test_litkb_p1.py::test_ingest_installs_a_run_
-- and_makes_it_current found it, not by review.
GRANT EXECUTE ON FUNCTION litkb.norm_search_text(text) TO litkb_reader, litkb_writer, litkb_ingest;

-- BEGIN guard: a search matches ANY term, not only all of them
-- The second half of the Q3 miss, and the bigger half — measured, not assumed. `plainto_tsquery`
-- ANDs every term, so the gold passage ("The NEs overestimate the transition probabilities and this
-- overesti- mate increases as the misclassi<FFFD>cation probabilities increase.") could not match a
-- query containing `naive estimators` and `misclassification`: it says NEs, and the extractor ate
-- the ligature. ONE absent word drops a passage entirely, however well the rest matches. This builds
-- the same query with OR, so ts_rank sorts by how much of the question a block answers. It is a
-- SECOND leg, not a replacement: the all-terms leg still runs first and reciprocal-rank fusion keeps
-- its hits above the loose ones.
CREATE FUNCTION litkb.any_term_query(p_q text) RETURNS tsquery
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
  w text;
  t tsquery;
  q tsquery := NULL;
BEGIN
  FOR w IN SELECT unnest(tsvector_to_array(to_tsvector('english', litkb.norm_search_text(p_q)))) LOOP
    -- the lexemes are already english-stemmed, so 'simple' keeps them as they are
    t := plainto_tsquery('simple', w);
    CONTINUE WHEN t IS NULL OR t = ''::tsquery;
    q := CASE WHEN q IS NULL THEN t ELSE q || t END;
  END LOOP;
  RETURN q;
END
$$;
-- END guard: a search matches ANY term, not only all of them
COMMENT ON FUNCTION litkb.any_term_query(text) IS
  'The query''s lexemes ORed together (0018). litkb_search''s any-term leg; the all-terms leg keeps '
  'plainto_tsquery. Measured on the P8 referee''s frozen corpus: this is what moves his Q3 gold '
  'passage from a miss to rank 1, and the normaliser alone did not move it at all.';
GRANT EXECUTE ON FUNCTION litkb.any_term_query(text) TO litkb_reader, litkb_writer;

-- The search legs read blocks.text through norm_search_text(), so the plain tsvector index cannot
-- serve them. These are the matching expression indexes; they are what keeps the lexical and
-- trigram legs from becoming sequential scans as the corpus grows past P5's bulk pass. (The
-- trigram leg has never had an index at all — `blocks` carried none before this.)
CREATE INDEX blocks_norm_text_fts ON litkb.blocks
  USING gin (to_tsvector('english', litkb.norm_search_text(text)));
CREATE INDEX blocks_norm_text_trgm ON litkb.blocks
  USING gin (litkb.norm_search_text(text) gin_trgm_ops);
