-- litkb 0020 — what the first real use of the knowledge base ran into.
--
-- `Reports/LITKB_LINKAGE_REVIEW_2026-09-15.md` §8 is a defect list measured on one session that
-- tried to follow the convention end to end. `Reports/LITKB_P8_REFEREE_2026-09-15.md` §4 classified
-- it. This migration is the database half of the answer; the CLI half is in commands.py.
--
-- ADDITIVE ONLY. Applied migrations are checksum-locked and 0001/0002/0013/0015/0017 are applied on
-- the live `litkb`, so nothing here drops a table or a column. What it does:
--
--  * §8.6 — `_feeds_token_ok` accepted 3 of the 7 token forms the convention documents, so a use
--    that feeds a REPORT could not carry a valid token and the linkage review wrote all 15 of its
--    uses with an EMPTY feeds array. The field exists to record what a work was used FOR; three
--    forms out of seven means that record is lost for every report-level use. The referee called
--    the migration "the right one" and cutting the convention to three "the cheap one". This is the
--    right one: the vocabulary is the convention's, and the validator now enforces all of it.
--  * §8.5 — `admit --doi` alone was refused at check 1 ("no claimed record to compare with the
--    registry and no bound file"). The rule it enforces is real, but it is a rule about a CLAIM: a
--    DOI plus a claimed title that contradicts the registry is the Papadakis/Mandilaras catch the
--    review praised, and it still fires unchanged. What was missing is the case where the admitter
--    makes no claim at all and takes the registry record as the identity. That is now sayable, once,
--    in the identifier's own evidence (`registry_only`), so the admission RECORDS that it was made
--    on the registry record alone instead of inventing a claim nobody made.
--  * P4 §7 — the work title is now the registry title joined with its subtitle (`10.14778/2994509.2994535`
--    entered as "Magellan", losing "toward building entity matching management systems", and minted a
--    truncated key from it). Check 1's "the work is the registry record" guard compared the work title
--    with the registry's BARE title only, so the joined form would have read as a different work. It
--    now accepts any form the registry itself published (`registry_titles`), which is the same list
--    `confirm_s2_candidate` has always taken its max ratio over.
--  * P4 §7 — a claimed title that matches the bare title but lacks the subtitle is a DISCREPANCY,
--    not a refusal, so `discrepancies.source` gains `'admission'` beside `'tracker'` and `'manifest'`.
--  * §8.4 — a source with no PDF (documentation, a blog post) is admitted from a saved text
--    snapshot; `file_versions.copy_kind` gains `'web snapshot'`. Everything else that route needs
--    already has a home: `source_url`, `obtained_at` (the retrieval date) and `txt_extract_path`.
--  * `Reports/LITKB_P4_MERGE_2026-09-15.md` "Migration: none written" — stage 6 parks 658 references,
--    1,182 citation mentions and 13 citation edges as JSONL with NO loader and nowhere to put two of
--    the three. `"references"` and `citation_mentions` exist (0002) and are cleared per run by
--    `clear_extraction_rows` (0017), so they are the home; what they lacked is the stage-6 columns,
--    an `ambiguous` resolution state (19 of the 658 rows are ambiguous and the CHECK refused them),
--    a table for the citation graph, and a write path for `litkb_ingest`.
--
-- WHO MAY WRITE the citation rows: `litkb_ingest`, through the SECURITY DEFINER functions below and
-- nothing else, exactly as 0017 does it. The ingest login is the one credential that never belongs
-- to an agent session.

SET LOCAL search_path = litkb, public;

-- ── §8.6: the feeds vocabulary the convention actually documents ─────────────────────────
-- Scripts/docs/LITERATURE_CONVENTION.md, "`Feeds` token vocabulary (doc-qualified, 2026-09-13)":
-- seven forms. The three that were here are unchanged in meaning; the four added are
-- `narrative §N` (integer only — that document does not subdivide), `gated-plan gate N`,
-- `review §N[.N…]` (any depth) and `report <FILE>#§<loc>` (`loc` alphanumeric: a heading key, or
-- `L<line>` when the citation sits outside any heading). A token is still only a SHAPE here; that
-- the section it names exists is checked against the target document, which the database cannot read.
CREATE OR REPLACE FUNCTION litkb._feeds_token_ok(p_token text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT coalesce(p_token ~ ('^(' ||
    'framework §[0-9]+(\.[0-9]+)*' ||
    '|narrative §[0-9]+' ||
    '|gated-plan gate [0-9]+' ||
    '|review §[0-9]+(\.[0-9]+)*' ||
    '|gap row [0-9]+' ||
    '|decision [a-z0-9][a-z0-9-]*' ||
    '|report [A-Za-z0-9][A-Za-z0-9._-]*\.md#§[A-Za-z0-9][A-Za-z0-9._§-]*' ||
    ')$'), false)
$$;

-- ── §8.5 and P4 §7: check 1 ──────────────────────────────────────────────────────────────
-- Replaced whole (a plpgsql body cannot be patched). Two changes against 0013, both marked below:
--   1. the "work is the registry record" guard accepts any title form the registry published;
--   2. an admission that makes NO claim and holds no bound file passes when the identifier's
--      evidence says `registry_only`, and is refused as before when it does not.
CREATE OR REPLACE FUNCTION litkb._check_registry(p_route text, p_work jsonb, p_identifiers jsonb, p_has_bound_file boolean)
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
  v_forms text[];
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
    -- 0020: the registry publishes a title and, for a work with one, a subtitle; `registry_titles`
    -- is the list of forms it published (bare, and "title: subtitle"). The work's stored title is
    -- the joined form, so comparing it with the bare form alone would read a correctly admitted
    -- work as a different study. Any published form matches; a title from nowhere still does not.
    v_forms := ARRAY[e->>'registry_title'];
    IF jsonb_typeof(e->'registry_titles') = 'array' THEN
      SELECT v_forms || coalesce(array_agg(t), '{}'::text[]) INTO v_forms
        FROM jsonb_array_elements_text(e->'registry_titles') t;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM unnest(v_forms) f
                    WHERE norm_title(f) IS NOT DISTINCT FROM norm_title(p_work->>'title')) THEN
      v_these := v_these || format('%s %s: the work''s title is not a registry title form', i->>'scheme', i->>'value');
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
      -- BEGIN guard: check 1 a registry-only admission says so
      -- 0013: "a DOI alone proves only that SOME work exists; with no claimed record to compare, the
      -- file's binding is the comparison". That stands for an admission that MAKES a claim and for
      -- one that says nothing at all. What is new is the third case: the admitter declares that the
      -- registry record IS the identity, and the declaration is stored on the identifier's evidence
      -- so the admission is auditable as registry-only afterwards. It is not a way round the claim
      -- check — this branch is only reached when there is no claim to check.
      IF coalesce(e->>'registry_only', '') <> 'true' THEN
        v_these := v_these || format('%s %s: no claimed record to compare with the registry, no bound file, and '
                                     'the identifier''s evidence does not say registry_only; claim a record with '
                                     '--title/--authors/--year, or bind a held file with --file',
                                     i->>'scheme', i->>'value');
      END IF;
      -- END guard: check 1 a registry-only admission says so
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

-- ── P4 §7: a claim that lacks the subtitle is review material, not a refusal ─────────────
ALTER TABLE discrepancies DROP CONSTRAINT discrepancies_source_check;
ALTER TABLE discrepancies ADD CONSTRAINT discrepancies_source_check
  CHECK (source IN ('tracker', 'manifest', 'admission'));

-- ── §8.4: a source whose evidence is a saved text snapshot, not a PDF ────────────────────
-- The URL is `source_url`, the retrieval date is `obtained_at`, the snapshot is `txt_extract_path`
-- and `rel_path`; only the KIND had no room. Binding runs against the snapshot, and the admission
-- is still a manual proposal that a second session must approve (check 4 is untouched).
ALTER TABLE file_versions DROP CONSTRAINT file_versions_copy_kind_check;
ALTER TABLE file_versions ADD CONSTRAINT file_versions_copy_kind_check
  CHECK (copy_kind IS NULL OR copy_kind IN ('publisher', 'author manuscript', 'preprint', 'scan', 'web snapshot'));

-- ── stage 6: the citation rows get their columns, their states and their graph ───────────
-- `ambiguous`: stage 6 judges EVERY candidate of a stage and reports two distinct accepted DOIs as
-- resolved-to-nothing (extract/references.py header). 19 of the 658 rows are in that state and the
-- 0002 CHECK refused them. Mapping them onto `candidate` would erase the distinction between "one
-- plausible match" and "two, and we will not choose".
ALTER TABLE "references" DROP CONSTRAINT references_resolution_check;
ALTER TABLE "references" ADD CONSTRAINT references_resolution_check
  CHECK (resolution IN ('resolved', 'candidate', 'ambiguous', 'unresolved'));

ALTER TABLE "references"
  -- GROBID's own id for the entry (`biblStruct/@xml:id`, "b0", "b41"). It is what every mention
  -- and every edge points at, so it is the reference's natural key within its run.
  ADD COLUMN ref_key           text,
  ADD COLUMN ref_index         integer CHECK (ref_index IS NULL OR ref_index >= 0),
  -- the work whose reference list this is. `file_id` already says which FILE it was parsed from;
  -- this is the join every citation-graph query starts from and saves walking file_versions.
  ADD COLUMN citing_work_id    uuid REFERENCES works (id),
  -- the DOI the resolution settled on, normalised. NULL for anything but `resolved`.
  ADD COLUMN resolved_doi      text,
  -- the whole verdict: which stage accepted, the ratio, the refusal name, the rival candidates.
  -- A resolution that cannot be re-read is a number with no derivation.
  ADD COLUMN resolution_detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN mention_count     integer CHECK (mention_count IS NULL OR mention_count >= 0),
  ADD COLUMN pipeline_version  text;
-- one row per (run, reference id): the loader is idempotent on it, and a second ingest of the same
-- run cannot double the reference list.
CREATE UNIQUE INDEX references_one_per_run_key ON "references" (run_id, ref_key) WHERE ref_key IS NOT NULL;
CREATE INDEX references_citing_work ON "references" (citing_work_id) WHERE citing_work_id IS NOT NULL;
CREATE INDEX references_resolved_doi ON "references" (resolved_doi) WHERE resolved_doi IS NOT NULL;

-- A stage-6 mention is one `<ref type="bibr">` ELEMENT in the body: its page, its boxes, and the
-- sentence around it. It is NOT anchored in a canonical block, because stage 6 reads GROBID's TEI
-- and blocks are stage 5's output — a corpus can have the one without the other, and on `litkb`
-- today it does (0 blocks, 1,182 mentions). So the three block-anchored columns become optional and
-- the row stands on its reference instead. Existing rows: there are none, on any database.
ALTER TABLE citation_mentions ALTER COLUMN block_id   DROP NOT NULL;
ALTER TABLE citation_mentions ALTER COLUMN char_start DROP NOT NULL;
ALTER TABLE citation_mentions ALTER COLUMN char_end   DROP NOT NULL;
ALTER TABLE citation_mentions
  ADD COLUMN page          integer CHECK (page IS NULL OR page >= 1),
  ADD COLUMN boxes         jsonb,
  ADD COLUMN marker        text,
  ADD COLUMN sentence      text,
  ADD COLUMN mention_index integer CHECK (mention_index IS NULL OR mention_index >= 0),
  -- either it is anchored in a block (stage 5) or it carries its own page geometry (stage 6);
  -- a row with neither is a mention nobody can locate.
  ADD CONSTRAINT citation_mentions_is_locatable CHECK (block_id IS NOT NULL OR page IS NOT NULL);
CREATE INDEX citation_mentions_reference ON citation_mentions (reference_id);
CREATE UNIQUE INDEX citation_mentions_one_per_element
  ON citation_mentions (reference_id, mention_index) WHERE mention_index IS NOT NULL;

-- The citation graph. An edge exists when a reference of one held work RESOLVED to another held
-- work — never on a title guess: `reference_id` is the evidence, and deleting the reference deletes
-- the edge's basis, which is why `clear_extraction_rows` below removes both together.
CREATE TABLE citation_edges (
  id              uuid PRIMARY KEY DEFAULT uuidv7(),
  citing_work_id  uuid NOT NULL REFERENCES works (id),
  cited_work_id   uuid NOT NULL REFERENCES works (id),
  reference_id    uuid NOT NULL REFERENCES "references" (id),
  run_id          uuid NOT NULL REFERENCES extraction_runs (id),
  cited_doi       text,
  mention_count   integer CHECK (mention_count IS NULL OR mention_count >= 0),
  created_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT citation_edges_not_a_self_loop CHECK (citing_work_id <> cited_work_id),
  UNIQUE (reference_id, cited_work_id)
);
CREATE INDEX citation_edges_citing ON citation_edges (citing_work_id);
CREATE INDEX citation_edges_cited  ON citation_edges (cited_work_id);

COMMENT ON TABLE citation_edges IS
  'The citation graph: one row per reference of a held work that resolved to another held work (stage 6, LITKB_REFERENCES_2026-09-15.md). Written only by litkb_ingest.';

-- The resolution invariant, on every path. `add_reference` refuses a reference that says `resolved`
-- with no DOI, or names a resolved work while saying it is unresolved; the ingest login also holds a
-- direct INSERT on this table (0010), so the same rule is a trigger. A row that claims a resolution
-- it cannot show is the one thing the citation graph must never contain — an edge is drawn from it.
CREATE FUNCTION litkb._reference_resolution_is_shown() RETURNS trigger
LANGUAGE plpgsql SET search_path = litkb, public, pg_temp AS $$
BEGIN
  IF NEW.resolution = 'resolved' AND NEW.resolved_doi IS NULL THEN
    RAISE EXCEPTION 'litkb: reference % is resolved with no DOI', NEW.id USING ERRCODE = '23514';
  END IF;
  IF NEW.resolution <> 'resolved' AND NEW.resolved_work_id IS NOT NULL THEN
    RAISE EXCEPTION 'litkb: reference % is % yet names a resolved work', NEW.id, NEW.resolution
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$$;
-- BEGIN guard: a reference's resolution is shown
CREATE TRIGGER references_resolution_is_shown BEFORE INSERT OR UPDATE ON "references"
  FOR EACH ROW EXECUTE FUNCTION _reference_resolution_is_shown();
-- END guard: a reference's resolution is shown

-- ── the ingest write path ────────────────────────────────────────────────────────────────
-- Every one is idempotent, because an ingest resumed after a kill must not double its rows and a
-- reference has no natural key but its run.
--
-- These functions are the ONLY way into `citation_edges`, which grants INSERT to nobody. They are
-- NOT the only way into `"references"` and `citation_mentions`: the ingest login keeps the direct
-- INSERT 0010 granted it (see the privileges section, and 0017's identical call for blocks), so any
-- rule that must hold on every path is a TRIGGER — `references_resolution_is_shown` above — and the
-- check inside `add_reference` is the same rule stated early, for a better message.

CREATE FUNCTION litkb.add_reference(
    p_file uuid, p_run uuid, p_block uuid, p_ref_key text, p_ref_index integer, p_raw text,
    p_parsed jsonb, p_citing_work uuid, p_resolved_work uuid, p_resolved_doi text,
    p_resolution text, p_resolution_detail jsonb, p_confidence real, p_mention_count integer,
    p_pipeline_version text)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_id uuid;
BEGIN
  -- BEGIN guard: a reference belongs to a run of its own file
  PERFORM 1 FROM extraction_runs r WHERE r.id = p_run AND r.file_id = p_file;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: run % is not a run of file %', p_run, p_file USING ERRCODE = '23514';
  END IF;
  -- END guard: a reference belongs to a run of its own file
  -- BEGIN guard: a reference written here carries the key it is deduplicated on
  -- `ON CONFLICT (run_id, ref_key)` arbitrates nothing when ref_key is NULL — two NULLs are not a
  -- conflict — so an ingest resumed after a kill would silently write the reference twice. The
  -- column stays nullable for a row that arrives another way; a row written through THIS function
  -- is a stage-6 row, and stage 6 always has GROBID's own `biblStruct/@xml:id`.
  IF p_ref_key IS NULL OR btrim(p_ref_key) = '' THEN
    RAISE EXCEPTION 'litkb: add_reference needs the reference key it is deduplicated on (run %)', p_run
      USING ERRCODE = '23514';
  END IF;
  -- END guard: a reference written here carries the key it is deduplicated on
  -- BEGIN guard: a resolved reference names the work it resolved to
  -- The same rule as the trigger, stated early so the message can name the run and the ref key. It
  -- raises the trigger's SQLSTATE deliberately: one rule broken two ways must not look like two
  -- different faults to a caller that matches on the code.
  IF p_resolution = 'resolved' AND p_resolved_doi IS NULL THEN
    RAISE EXCEPTION 'litkb: reference %/% is resolved with no DOI', p_run, p_ref_key USING ERRCODE = '23514';
  END IF;
  IF p_resolution <> 'resolved' AND p_resolved_work IS NOT NULL THEN
    RAISE EXCEPTION 'litkb: reference %/% is % yet names a resolved work', p_run, p_ref_key, p_resolution
      USING ERRCODE = '23514';
  END IF;
  -- END guard: a resolved reference names the work it resolved to
  INSERT INTO "references" (file_id, run_id, block_id, ref_key, ref_index, raw_text, parsed,
                            citing_work_id, resolved_work_id, resolved_doi, resolution,
                            resolution_detail, confidence, mention_count, pipeline_version)
  VALUES (p_file, p_run, p_block, p_ref_key, p_ref_index, p_raw, p_parsed, p_citing_work,
          p_resolved_work, p_resolved_doi, p_resolution, coalesce(p_resolution_detail, '{}'::jsonb),
          p_confidence, p_mention_count, p_pipeline_version)
  ON CONFLICT (run_id, ref_key) WHERE ref_key IS NOT NULL DO NOTHING
  RETURNING id INTO v_id;
  IF v_id IS NULL THEN
    SELECT r.id INTO v_id FROM "references" r WHERE r.run_id = p_run AND r.ref_key = p_ref_key;
  END IF;
  RETURN v_id;
END
$$;

CREATE FUNCTION litkb.add_citation_mention(
    p_reference uuid, p_mention_index integer, p_block uuid, p_char_start integer, p_char_end integer,
    p_page integer, p_boxes jsonb, p_marker text, p_sentence text)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_id uuid;
BEGIN
  -- BEGIN guard: a mention written here carries the index it is deduplicated on
  -- Same reason as add_reference's: ON CONFLICT cannot arbitrate a NULL.
  IF p_mention_index IS NULL THEN
    RAISE EXCEPTION 'litkb: add_citation_mention needs the mention index it is deduplicated on (reference %)',
      p_reference USING ERRCODE = '23514';
  END IF;
  -- END guard: a mention written here carries the index it is deduplicated on
  INSERT INTO citation_mentions (reference_id, mention_index, block_id, char_start, char_end,
                                 page, boxes, marker, sentence)
  VALUES (p_reference, p_mention_index, p_block, p_char_start, p_char_end, p_page, p_boxes,
          p_marker, p_sentence)
  ON CONFLICT (reference_id, mention_index) WHERE mention_index IS NOT NULL DO NOTHING
  RETURNING id INTO v_id;
  IF v_id IS NULL THEN
    SELECT m.id INTO v_id FROM citation_mentions m
     WHERE m.reference_id = p_reference AND m.mention_index = p_mention_index;
  END IF;
  RETURN v_id;
END
$$;

CREATE FUNCTION litkb.add_citation_edge(
    p_citing_work uuid, p_cited_work uuid, p_reference uuid, p_run uuid, p_cited_doi text,
    p_mention_count integer)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_id uuid;
BEGIN
  -- BEGIN guard: an edge's citing work is the reference's own
  PERFORM 1 FROM "references" r
   WHERE r.id = p_reference AND r.run_id = p_run
     AND (r.citing_work_id IS NULL OR r.citing_work_id = p_citing_work);
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: reference % is not a reference of work % in run %', p_reference, p_citing_work, p_run
      USING ERRCODE = '23514';
  END IF;
  -- END guard: an edge's citing work is the reference's own
  INSERT INTO citation_edges (citing_work_id, cited_work_id, reference_id, run_id, cited_doi, mention_count)
  VALUES (p_citing_work, p_cited_work, p_reference, p_run, p_cited_doi, p_mention_count)
  ON CONFLICT (reference_id, cited_work_id) DO NOTHING
  RETURNING id INTO v_id;
  IF v_id IS NULL THEN
    SELECT e.id INTO v_id FROM citation_edges e
     WHERE e.reference_id = p_reference AND e.cited_work_id = p_cited_work;
  END IF;
  RETURN v_id;
END
$$;

-- A candidate raised BY a citation (design §4.3, candidates.source = 'citation'). The agent path is
-- `add_candidate`, which takes a workstream and its token; ingest has neither and never will, so a
-- citation candidate carries no workstream and is admitted by a later agent session or not at all.
CREATE FUNCTION litkb.add_citation_candidate(
    p_reference uuid, p_title text, p_authors jsonb, p_year integer, p_ids jsonb, p_raw jsonb,
    p_detail text)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_id uuid;
BEGIN
  SELECT cd.id INTO v_id FROM candidates cd WHERE cd.citing_reference_id = p_reference AND cd.source = 'citation';
  IF v_id IS NOT NULL THEN
    RETURN v_id;
  END IF;
  INSERT INTO candidates (source, source_detail, citing_reference_id, raw_record, title, authors, year, ids, state)
  VALUES ('citation', p_detail, p_reference, p_raw, p_title, p_authors, p_year, p_ids, 'new')
  RETURNING id INTO v_id;
  RETURN v_id;
END
$$;
CREATE UNIQUE INDEX candidates_one_per_citing_reference
  ON candidates (citing_reference_id) WHERE citing_reference_id IS NOT NULL AND source = 'citation';

-- ── the resume path learns about the new rows ────────────────────────────────────────────
-- 0017 cleared citation_mentions BY BLOCK and "references" by run. A stage-6 mention has no block,
-- so it would have survived its own reference's deletion and been orphaned by the FK. Both are now
-- cleared through the reference, and the edges with them.
CREATE OR REPLACE FUNCTION litkb.clear_extraction_rows(p_run uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
BEGIN
  -- BEGIN guard: an ok run's rows are never cleared
  IF EXISTS (SELECT 1 FROM extraction_runs r WHERE r.id = p_run AND r.status = 'ok') THEN
    RAISE EXCEPTION 'litkb: run % is ok; its text rows are immutable', p_run USING ERRCODE = '22023';
  END IF;
  -- END guard: an ok run's rows are never cleared
  DELETE FROM table_cells WHERE block_id IN (SELECT id FROM blocks WHERE run_id = p_run);
  DELETE FROM tables  WHERE block_id IN (SELECT id FROM blocks WHERE run_id = p_run);
  DELETE FROM figures WHERE block_id IN (SELECT id FROM blocks WHERE run_id = p_run);
  DELETE FROM equations WHERE block_id IN (SELECT id FROM blocks WHERE run_id = p_run);
  DELETE FROM extraction_disagreements WHERE run_id = p_run;
  DELETE FROM citation_edges WHERE run_id = p_run;
  DELETE FROM citation_mentions
   WHERE block_id IN (SELECT id FROM blocks WHERE run_id = p_run)
      OR reference_id IN (SELECT id FROM "references" WHERE run_id = p_run);
  -- A citation candidate raised by a reference this run is about to lose: if nobody has acted on it
  -- yet it goes with the reference, because `add_citation_candidate` looks the row up by the NEW
  -- reference id and would otherwise leave an orphan that the redo cannot find and nothing can
  -- explain. A candidate that has been ADMITTED, rejected or marked duplicate is a decision somebody
  -- made; that survives, and loses only its pointer at the deleted reference.
  DELETE FROM candidates
   WHERE source = 'citation' AND state = 'new'
     AND citing_reference_id IN (SELECT id FROM "references" WHERE run_id = p_run);
  UPDATE candidates SET citing_reference_id = NULL
   WHERE citing_reference_id IN (SELECT id FROM "references" WHERE run_id = p_run);
  DELETE FROM "references" WHERE run_id = p_run;
  UPDATE blocks SET parent_block_id = NULL WHERE run_id = p_run;
  DELETE FROM blocks WHERE run_id = p_run;
  DELETE FROM pages WHERE run_id = p_run;
END
$$;

-- ── privileges ───────────────────────────────────────────────────────────────────────────
-- BEGIN guard: only litkb_ingest writes the citation rows
-- `citation_edges` is new, so it can take 0017's stricter shape: INSERT to nobody, the function is
-- the only way in. `"references"` and `citation_mentions` keep the direct INSERT 0010 granted the
-- ingest login — revoking it would retire a P1-refereed privilege row on an unrefereed change
-- (0017 made the same call for blocks and pages, and for the same reason). Their invariants are
-- therefore enforced by TRIGGER as well, which holds on the direct path too.
REVOKE ALL ON citation_edges FROM PUBLIC;
REVOKE INSERT, UPDATE, DELETE ON citation_edges FROM litkb_reader, litkb_writer, litkb_promoter, litkb_ingest;
REVOKE INSERT, UPDATE, DELETE ON "references", citation_mentions FROM litkb_reader, litkb_writer, litkb_promoter;
GRANT SELECT ON citation_edges TO litkb_reader, litkb_writer, litkb_ingest;
REVOKE EXECUTE ON FUNCTION
  litkb.add_reference(uuid, uuid, uuid, text, integer, text, jsonb, uuid, uuid, text, text, jsonb, real, integer, text),
  litkb.add_citation_mention(uuid, integer, uuid, integer, integer, integer, jsonb, text, text),
  litkb.add_citation_edge(uuid, uuid, uuid, uuid, text, integer),
  litkb.add_citation_candidate(uuid, text, jsonb, integer, jsonb, jsonb, text)
FROM PUBLIC;
GRANT EXECUTE ON FUNCTION
  litkb.add_reference(uuid, uuid, uuid, text, integer, text, jsonb, uuid, uuid, text, text, jsonb, real, integer, text),
  litkb.add_citation_mention(uuid, integer, uuid, integer, integer, integer, jsonb, text, text),
  litkb.add_citation_edge(uuid, uuid, uuid, uuid, text, integer),
  litkb.add_citation_candidate(uuid, text, jsonb, integer, jsonb, jsonb, text)
TO litkb_ingest;
-- END guard: only litkb_ingest writes the citation rows

-- `_feeds_token_ok` is read by `_ws_chains`, which runs as its definer; the writer never calls it
-- directly today. The CLI's `use add` checks tokens BEFORE writing so a bad token is a refusal at
-- the command rather than a chain held at prepare, and one regex is one home for the rule.
GRANT EXECUTE ON FUNCTION litkb._feeds_token_ok(text) TO litkb_writer;

-- end of 0020
