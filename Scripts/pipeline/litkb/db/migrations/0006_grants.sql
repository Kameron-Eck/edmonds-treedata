-- litkb 0006 — role privileges (design §4.7, §4.6 check 5).
--   litkb_reader    SELECT
--   litkb_writer    SELECT; INSERT into proposals (gap_versions, use_versions), candidates,
--                   admissions, acquisition attempts, extraction tables, evidence; EXECUTE
--                   the write functions. No UPDATE or DELETE anywhere, and no column
--                   privilege on quote_verified, any state column, the promotion fields, or
--                   the admission approver fields. Fact version tables and identity rows are
--                   written only through the functions.
--   litkb_promoter  SELECT; EXECUTE promote_prepare / promote_commit / promote_abandon
-- The owner (litkb_owner on litkb, litkb_test on litkb_test) holds everything else.

SET LOCAL search_path = litkb, public;

REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA litkb FROM PUBLIC;
GRANT USAGE ON SCHEMA litkb TO litkb_reader, litkb_writer, litkb_promoter;

GRANT SELECT ON ALL TABLES IN SCHEMA litkb TO litkb_reader, litkb_writer, litkb_promoter;

DO $$
DECLARE
  v_table text;
  v_cols text;
BEGIN
  FOREACH v_table IN ARRAY ARRAY[
    'gap_versions', 'use_versions',
    'candidates', 'admissions', 'acquisition_attempts',
    'extraction_runs', 'file_checks', 'pages', 'blocks', 'tables', 'figures', 'equations',
    'references', 'citation_mentions', 'chunks', 'embeddings',
    'use_evidence', 'use_embeddings'] LOOP
    SELECT string_agg(quote_ident(a.attname), ', ' ORDER BY a.attnum) INTO v_cols
      FROM pg_attribute a
     WHERE a.attrelid = format('litkb.%I', v_table)::regclass
       AND a.attnum > 0 AND NOT a.attisdropped
       AND a.attname NOT IN ('state', 'promoted_at', 'promotion_id', 'quote_verified',
                             'approver_agent', 'approver_session', 'approved_at');
    EXECUTE format('GRANT INSERT (%s) ON litkb.%I TO litkb_writer', v_cols, v_table);
  END LOOP;
END
$$;

GRANT EXECUTE ON FUNCTION
  litkb.norm_identifier(text, text),
  litkb.write_fact(text, uuid, uuid, jsonb, text, uuid, text, text),
  litkb.write_proposal(text, uuid, jsonb, uuid, jsonb, text, uuid, text, text),
  litkb.open_workstream(text, text, text, text, text),
  litkb.abandon_workstream(uuid),
  litkb.set_current_run(uuid, uuid, uuid)
TO litkb_writer;

GRANT EXECUTE ON FUNCTION litkb.norm_identifier(text, text) TO litkb_reader, litkb_promoter;

GRANT EXECUTE ON FUNCTION
  litkb.promote_prepare(uuid, text, text),
  litkb.promote_commit(uuid, text),
  litkb.promote_abandon(uuid)
TO litkb_promoter;

-- end of grants
