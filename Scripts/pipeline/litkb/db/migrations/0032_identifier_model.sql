-- litkb 0032 — the IDENTIFIER MODEL (LITKB_WORKPLAN.md "### S4.5" item 1; the linkage survey round 3,
-- Reports/LITKB_LINKAGE_IDENTIFIERS_SURVEY_2026-09-22.md §3 and §4.5). Builder B1, workstream ladder-1.
--
-- Every mechanism here is a RELAYED design (CLAUDE.md §3.4c): read in fatcat, Invenio, WikidataIntegrator,
-- oc_graphenricher, Zotero, isbnlib and idutils by the survey's crawlers, UNVALIDATED until an independent
-- referee scores it on litkb's own rows (E21's pair, E06, 187, the crosswalk probe's rows).
--
-- What it does, in order:
--   1. litkb.scheme_registry — the closed `identifiers.scheme` CHECK of 0001 becomes DATA: one row per scheme
--      with its label, url template, regex, normaliser, and `distinct_values` (does a value name at most ONE
--      work?). Seeded with the twelve 0001 schemes, the six a rung cannot fire without (md5 pii core bibcode
--      ocaid oai) and the second tier (issn oclc lccn olid htid gbooks sha1 sha256 zlib lgrsnf lgrsfic lgli
--      nexusstc wikidata mag dblp hal). The Python twin of the seed is `litkb.identifiers.SCHEMES`; the
--      suite holds the two equal. `identity_strong` and `registry_confirmed` carry the two scheme lists that
--      were written into admit (0014) and _check_registry (0020), now read from here — `identity_strong`
--      less `handle`, which the plan makes non-distinct: a strong scheme must be identity somewhere
--      (distinct, or type-scoped), and counts as strong only where it is identity for THIS candidate.
--   2. `identifiers.scheme` references the registry (the CHECK is dropped).
--   3. litkb.norm_identifier gains a normaliser per scheme (0014's DOI and arXiv branches are unchanged).
--   4. The partial unique index covers ONLY the distinct schemes, so a book's ISBN on its chapters is data and
--      not a violation; the migration refuses to finish unless the index predicate and the registry agree.
--   5. Provenance per identifier: `asserted_by` beside `verified_by` (Invenio's provider/client split),
--      `derived_from_scheme` / `derived_from_value` (the INPUT identifier an edge was derived from — what
--      oc_graphenricher computes and throws away), `provenance_backfilled` (set by the reviewed backfill op
--      alone). `verified_by` widens to the survey's service list; `deterministic` is a first-class source.
--   6. `works.part_of_work_id` / `works.version_of_work_id` — parent columns for the common cases (chapter ->
--      book, preprint -> version of record, arXiv version -> concept), filled only from a registry relation,
--      monotone (a later source fills a NULL and never overwrites — fatcat's merge).
--   7. litkb.work_relations — the edge table for everything else, with the THIRD STATE (`none_returned`: a
--      registry was asked and returned no relation — not evidence of absence).
--   8. litkb.identifier_conflicts — fatcat's collision rule COUNTED: a distinct-valued identifier harvested
--      for one work that another work already holds is dropped, a conflict-resolution edge is asserted, and
--      the conflict is a row here (the `conflicts_uncounted` counter reads both). litkb.identifier_claims
--      records EVERY claim record_identifiers weighs, before it is resolved, with its outcome — so a claim
--      the rule failed to resolve (one that hit the unique index instead) is a durable row, not a lost error
--      (Codex X4 / auditor-B1 F4: a unique index keeps the duplicate from persisting, so the EVENT is counted).
--   9. litkb.record_identifiers / litkb.record_work_relations — the one write path for HARVESTED identifiers
--      and relations (writer, token-checked); litkb.backfill_identifier_provenance — the reviewed backfill
--      (ingest login, dry-run unless told otherwise).
--  10. litkb.admit (0014) and litkb._check_registry (0020) replaced: check 2 is identifier-first over DISTINCT
--      schemes only, ISBN is type-scoped (identity only between two books), the strong-scheme and
--      registry-scheme lists come from the registry, every admitted identifier carries `asserted_by`, and a
--      harvest row (one with `derived_from`) is refused at admission — record_identifiers takes it.
--
-- THE MUTATION ROWS on the replaced bodies move here (qc/instruments/litkb_p2_mutations.py, builder B1's block):
-- every guard marker and every replace-row target string of 0014's admit and norm_identifier and of 0020's
-- _check_registry is kept VERBATIM, exactly once, in this file — the class MIG16/MIG20/MIG21/MIG19 already name.

SET LOCAL search_path = litkb, public;

-- ── 1. the scheme registry ───────────────────────────────────────────────────────────────────────────
CREATE TABLE scheme_registry (
  scheme             text PRIMARY KEY CHECK (scheme ~ '^[a-z][a-z0-9_]*$'),
  label              text NOT NULL CHECK (btrim(label) <> ''),
  url_template       text CHECK (url_template IS NULL OR url_template LIKE '%{value}%'),
  regex              text,
  normaliser         text NOT NULL CHECK (normaliser IN ('doi', 'arxiv', 'isbn', 'pmcid', 'pmid', 'issn', 'pii',
                                                         'lower', 'upper', 'upper_last_segment', 'handle', 'oclc',
                                                         'lccn', 'hal', 'trim')),
  distinct_values    boolean NOT NULL,
  identity_strong    boolean NOT NULL DEFAULT false,
  registry_confirmed boolean NOT NULL DEFAULT false,
  identity_types     text[],
  tier               smallint NOT NULL CHECK (tier IN (0, 1, 2)),
  why                text NOT NULL CHECK (btrim(why) <> ''),
  -- a type-scoped scheme is never distinct: its identity is the type rule, not the index
  CONSTRAINT scheme_registry_type_scope_not_distinct CHECK (identity_types IS NULL OR NOT distinct_values),
  -- a STRONG scheme (check 2 skips the title review for it) is identity somewhere: distinct, or type-scoped.
  -- A strong non-distinct scheme skipped the review while check 2's lookup could no longer find its value
  -- (auditor-B1 F6: the same handle, or a report's ISBN, admitted twice was silently a second work)
  CONSTRAINT scheme_registry_strong_is_identity CHECK (NOT identity_strong OR distinct_values OR identity_types IS NOT NULL)
);

INSERT INTO scheme_registry (scheme, label, url_template, regex, normaliser, distinct_values, identity_strong,
                             registry_confirmed, identity_types, tier, why) VALUES
  ('doi', 'DOI', 'https://doi.org/{value}', '^10\.[0-9]{4,9}(\.[0-9]+)*/.+$', 'doi',
   true, true, true, NULL, 0,
   'plan: distinct'),
  ('arxiv', 'arXiv id', 'https://arxiv.org/abs/{value}', '^([0-9]{4}\.[0-9]{4,5}|[a-z-]+(\.[a-z]{2})?/[0-9]{7})$', 'arxiv',
   true, true, true, NULL, 0,
   'plan: distinct (the 10.48550 DOI is versionless; the id is stored versionless)'),
  ('jstor', 'JSTOR stable id', 'https://www.jstor.org/stable/{value}', '^[0-9]+$', 'trim',
   true, true, false, NULL, 0,
   'decided: a stable id names one JSTOR item; carried over as a strong scheme from 0014'),
  ('isbn', 'ISBN-13', 'https://openlibrary.org/isbn/{value}', '^97[89][0-9]{10}$', 'isbn',
   false, true, true, ARRAY['book'], 0,
   'plan: NOT distinct — a book''s ISBN on its chapters is data (fatcat sets it on chapters)'),
  ('pmid', 'PubMed id', 'https://pubmed.ncbi.nlm.nih.gov/{value}/', '^[0-9]{1,9}$', 'pmid',
   true, true, false, NULL, 0,
   'plan: distinct'),
  ('pmcid', 'PubMed Central id', 'https://www.ncbi.nlm.nih.gov/pmc/articles/{value}/', '^PMC[0-9]+$', 'pmcid',
   true, true, false, NULL, 0,
   'plan: distinct; stored WITH the PMC prefix (LINKAGE §3.6 trap 3)'),
  ('openalex', 'OpenAlex work id', 'https://openalex.org/{value}', '^W[0-9]+$', 'upper_last_segment',
   true, false, false, NULL, 0,
   'plan: distinct'),
  ('s2', 'Semantic Scholar id', 'https://www.semanticscholar.org/paper/{value}', '^([0-9a-f]{40}|[0-9]+)$', 'lower',
   true, false, false, NULL, 0,
   'plan: distinct (the 40-hex paperId, or the CorpusId)'),
  ('handle', 'Handle', 'https://hdl.handle.net/{value}', '^[^/\s]+/\S+$', 'handle',
   false, false, false, NULL, 0,
   'plan: NOT distinct — mirroring repositories share handles; so NOT strong either (0014 listed it strong): a value that names no one work cannot show that two records are different works'),
  ('url', 'URL', NULL, '^https?://\S+$', 'trim',
   true, false, false, NULL, 0,
   'decided: a web source''s URL names that source (E06''s scheme); 0001''s index held it distinct and nothing measured contradicts that'),
  ('tracker', 'literature tracker row', NULL, '^[0-9]+$', 'trim',
   true, false, false, NULL, 0,
   'decided: one tracker row is one reference; 0001''s index held it distinct'),
  ('legacy_stem', 'legacy file stem', NULL, NULL, 'trim',
   true, false, false, NULL, 0,
   'decided: one legacy corpus file stem is one work; 0001''s index held it distinct'),
  ('md5', 'MD5 (shadow-library work address)', NULL, '^[0-9a-f]{32}$', 'lower',
   false, false, false, NULL, 1,
   'plan: NOT distinct — one work legitimately has many files (LINKAGE §3.3)'),
  ('pii', 'Elsevier PII', 'https://www.sciencedirect.com/science/article/pii/{value}', '^[SB][0-9X]{16}$', 'pii',
   true, false, false, NULL, 1,
   'decided: distinct for practical purposes (LINKAGE §3.1; Elsevier''s native key)'),
  ('core', 'CORE id', 'https://core.ac.uk/works/{value}', '^[0-9]+$', 'trim',
   true, false, false, NULL, 1,
   'decided: distinct (LINKAGE §3.1; the B17 byte rung is keyed on it)'),
  ('bibcode', 'ADS bibcode', 'https://ui.adsabs.harvard.edu/abs/{value}', '^[0-9]{4}[A-Za-z&.]\S{13}[A-Za-z.]$', 'trim',
   true, false, false, NULL, 1,
   'plan: distinct'),
  ('ocaid', 'Internet Archive identifier', 'https://archive.org/details/{value}', '^[A-Za-z0-9._-]+$', 'trim',
   true, false, false, NULL, 1,
   'decided: distinct (LINKAGE §3.1: an IA item is one scan)'),
  ('oai', 'OAI identifier', NULL, '^oai:\S+$', 'trim',
   false, false, false, NULL, 1,
   'plan: NOT distinct across mirroring repositories'),
  ('issn', 'ISSN', 'https://portal.issn.org/resource/ISSN/{value}', '^[0-9]{4}-[0-9]{3}[0-9X]$', 'issn',
   false, false, false, NULL, 2,
   'plan: NOT distinct — a container key shared by every article in the journal'),
  ('oclc', 'OCLC number', 'https://www.worldcat.org/oclc/{value}', '^[0-9]+$', 'oclc',
   false, false, false, NULL, 2,
   'decided: NOT distinct — a book-level record its chapters share'),
  ('lccn', 'LCCN', 'https://lccn.loc.gov/{value}', '^[a-z]{0,3}[0-9]{8,10}$', 'lccn',
   false, false, false, NULL, 2,
   'decided: NOT distinct — book-level'),
  ('olid', 'Open Library id', 'https://openlibrary.org/books/{value}', '^OL[0-9]+[MWA]$', 'upper',
   false, false, false, NULL, 2,
   'decided: NOT distinct — edition-level'),
  ('htid', 'HathiTrust volume id', 'https://hdl.handle.net/2027/{value}', NULL, 'trim',
   false, false, false, NULL, 2,
   'decided: NOT distinct — volume-level'),
  ('gbooks', 'Google Books id', 'https://books.google.com/books?id={value}', NULL, 'trim',
   false, false, false, NULL, 2,
   'decided: NOT distinct — volume-level'),
  ('sha1', 'SHA-1 file digest', NULL, '^[0-9a-f]{40}$', 'lower',
   false, false, false, NULL, 2,
   'decided: NOT distinct — a file digest, and one work has many files'),
  ('sha256', 'SHA-256 file digest', NULL, '^[0-9a-f]{64}$', 'lower',
   false, false, false, NULL, 2,
   'decided: NOT distinct — a file digest'),
  ('zlib', 'Z-Library id', NULL, '^[0-9]+$', 'trim',
   false, false, false, NULL, 2,
   'decided: NOT distinct — a shadow-library FILE record'),
  ('lgrsnf', 'LibGen non-fiction id', NULL, '^[0-9]+$', 'trim',
   false, false, false, NULL, 2,
   'decided: NOT distinct — a shadow-library FILE record'),
  ('lgrsfic', 'LibGen fiction id', NULL, '^[0-9]+$', 'trim',
   false, false, false, NULL, 2,
   'decided: NOT distinct — a shadow-library FILE record'),
  ('lgli', 'LibGen.li id', NULL, '^[0-9]+$', 'trim',
   false, false, false, NULL, 2,
   'decided: NOT distinct — a shadow-library FILE record'),
  ('nexusstc', 'Nexus/STC id', NULL, NULL, 'trim',
   false, false, false, NULL, 2,
   'decided: NOT distinct — an STC record carries several files (LINKAGE §3.3)'),
  ('wikidata', 'Wikidata QID', 'https://www.wikidata.org/wiki/{value}', '^Q[0-9]+$', 'upper_last_segment',
   true, false, false, NULL, 2,
   'decided: distinct — one item per work (Wikidata''s own distinct-values constraint on its external-id properties is the shape WikidataIntegrator reads, LINKAGE §3.3)'),
  ('mag', 'Microsoft Academic id', NULL, '^[0-9]+$', 'trim',
   true, false, false, NULL, 2,
   'plan: distinct'),
  ('dblp', 'dblp key', 'https://dblp.org/rec/{value}', '^[a-z]+/[A-Za-z0-9_-]+/\S+$', 'trim',
   true, false, false, NULL, 2,
   'decided: distinct — one dblp record per publication'),
  ('hal', 'HAL id', 'https://hal.science/{value}', '^[a-z]+-[0-9]{8}$', 'hal',
   true, false, false, NULL, 2,
   'decided: distinct — one deposit (versions stripped, as arXiv)');

-- ── 2. the closed CHECK becomes the registry ─────────────────────────────────────────────────────────
ALTER TABLE identifiers DROP CONSTRAINT identifiers_scheme_check;
ALTER TABLE identifiers ADD CONSTRAINT identifiers_scheme_registered
  FOREIGN KEY (scheme) REFERENCES scheme_registry (scheme);

-- ── 3. a normaliser per scheme ───────────────────────────────────────────────────────────────────────
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
    -- 0032: the schemes the registry added, each with its normaliser (scheme_registry.normaliser names it;
    -- the Python twin is litkb.identifiers.norm, held equal by qc/test_litkb_s45_identity.py)
    -- ISBN: a leading ISBN / ISBN-10: / ISBN-13: label dropped, every character but 0-9 and X removed; a VALID
    -- ISBN-10 (weights 10..1, mod 11, not the all-zero sentinels) is stored as its ISBN-13 (978 + nine digits +
    -- the EAN-13 check digit, weights 1,3). Anything else stays its cleaned characters: never coerced.
    WHEN 'isbn'  THEN (SELECT CASE
                         WHEN c ~ '^[0-9]{9}[0-9X]$' AND c NOT IN ('0000000000', '000000000X')
                              AND (SELECT sum((11 - g) * CASE WHEN substr(c, g, 1) = 'X' THEN 10
                                                               ELSE substr(c, g, 1)::integer END)
                                     FROM generate_series(1, 10) g) % 11 = 0
                         THEN '978' || substr(c, 1, 9)
                              || ((10 - (SELECT sum(CASE WHEN g % 2 = 1 THEN 1 ELSE 3 END
                                                    * substr('978' || substr(c, 1, 9), g, 1)::integer)
                                           FROM generate_series(1, 12) g) % 10) % 10)::text
                         ELSE c END
                       FROM (SELECT regexp_replace(upper(regexp_replace(btrim(p_value), '^\s*isbn(-1[03])?\s*:?\s*', '', 'i')),
                                                   '[^0-9X]', '', 'g') AS c) s)
    -- PMCID stored WITH its PMC prefix (LINKAGE §3.6 trap 3); asked without it (identifiers.pmcid_for_provider)
    WHEN 'pmcid' THEN CASE WHEN btrim(p_value) ~* '^(pmc)?\s*[0-9]+$'
                           THEN 'PMC' || substring(btrim(p_value) from '[0-9]+$') ELSE btrim(p_value) END
    WHEN 'pmid'  THEN regexp_replace(btrim(p_value), '^pmid:\s*', '', 'i')
    WHEN 'issn'  THEN (SELECT CASE WHEN c ~ '^[0-9]{7}[0-9X]$' THEN substr(c, 1, 4) || '-' || substr(c, 5) ELSE c END
                       FROM (SELECT regexp_replace(upper(btrim(p_value)), '[\s-]', '', 'g') AS c) s)
    -- Elsevier PII: the punctuated form S0034-4257(20)30123-4 and the bare S0034425720301234 are one key
    WHEN 'pii'   THEN regexp_replace(upper(btrim(p_value)), '[^0-9A-Z]', '', 'g')
    WHEN 'handle' THEN regexp_replace(btrim(p_value), '^(hdl:\s*|(https?://)?hdl\.handle\.net/)', '', 'i')
    WHEN 'oclc'  THEN regexp_replace(lower(btrim(p_value)), '^(\(ocolc\)|ocm|ocn|on)', '')
    WHEN 'lccn'  THEN regexp_replace(lower(p_value), '\s', '', 'g')
    WHEN 'hal'   THEN regexp_replace(lower(btrim(p_value)), 'v[0-9]+$', '')
    WHEN 'md5'   THEN lower(btrim(p_value))
    WHEN 'sha1'  THEN lower(btrim(p_value))
    WHEN 'sha256' THEN lower(btrim(p_value))
    WHEN 's2'    THEN lower(btrim(p_value))
    WHEN 'olid'  THEN upper(btrim(p_value))
    WHEN 'openalex' THEN upper(regexp_replace(rtrim(btrim(p_value), '/'), '^.*/', ''))
    WHEN 'wikidata' THEN upper(regexp_replace(rtrim(btrim(p_value), '/'), '^.*/', ''))
    ELSE btrim(p_value)
  END
$$;

-- the existing rows, before anything relies on the new normalisers (0014's discipline): every stored
-- value_norm must already be what its scheme's normaliser returns. The schemes whose rule changed here
-- (handle, isbn, pmid, pmcid, openalex, s2) hold no row on the live base (survey-code §0), so this refuses
-- nothing there — and would name what it found instead of rewriting it.
DO $$
DECLARE
  v_bad text;
BEGIN
  SELECT string_agg(format('%s %s:%s -> %s', i.id, i.scheme, i.value_norm, litkb.norm_identifier(i.scheme, i.value_norm)), '; ')
    INTO v_bad
    FROM litkb.identifiers i
   WHERE i.value_norm IS DISTINCT FROM litkb.norm_identifier(i.scheme, i.value_norm);
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'litkb 0032: stored identifiers are not canonical under the new normalisers; review them by hand first: %', v_bad;
  END IF;
END
$$;

-- ── 4. uniqueness is per-scheme DATA ─────────────────────────────────────────────────────────────────
-- A partial index predicate cannot read a table, so the distinct schemes are written into it — generated
-- from litkb.identifiers.distinct_schemes(), and checked against the registry below: the migration refuses
-- to finish if the two disagree in either direction. The live counter `nondistinct_schemes_in_unique_index`
-- (qc/instruments/litkb_hardening_b1.py) re-reads the predicate from the catalog on every grade.
DROP INDEX identifiers_active_scheme_value;
CREATE UNIQUE INDEX identifiers_active_scheme_value ON identifiers (scheme, value_norm)
  WHERE active AND scheme IN ('doi', 'arxiv', 'jstor', 'pmid', 'pmcid', 'openalex', 's2', 'url', 'tracker', 'legacy_stem', 'pii', 'core', 'bibcode', 'ocaid', 'wikidata', 'mag', 'dblp', 'hal');

DO $$
DECLARE
  v_pred text;
  v_in text[];
  v_want text[];
BEGIN
  SELECT pg_get_expr(x.indpred, x.indrelid) INTO v_pred
    FROM pg_index x WHERE x.indexrelid = 'litkb.identifiers_active_scheme_value'::regclass;
  SELECT coalesce(array_agg(m[1] ORDER BY m[1]), '{}') INTO v_in
    FROM regexp_matches(coalesce(v_pred, ''), '''([a-z0-9_]+)''::text', 'g') m;
  SELECT coalesce(array_agg(scheme ORDER BY scheme), '{}') INTO v_want
    FROM litkb.scheme_registry WHERE distinct_values;
  -- BEGIN guard: the unique index covers exactly the registry's distinct schemes
  IF v_in IS DISTINCT FROM v_want THEN
    RAISE EXCEPTION 'litkb 0032: identifiers_active_scheme_value covers % but the registry''s distinct schemes are %',
      v_in, v_want;
  END IF;
  -- END guard: the unique index covers exactly the registry's distinct schemes
END
$$;

-- ── 5. provenance per identifier ─────────────────────────────────────────────────────────────────────
ALTER TABLE identifier_versions DROP CONSTRAINT identifier_versions_verified_by_check;
ALTER TABLE identifier_versions ADD CONSTRAINT identifier_versions_verified_by_check
  CHECK (verified_by IS NULL OR verified_by IN ('crossref', 'datacite', 'arxiv', 's2', 'openalex', 'opencitations', 'pubmed', 'pmc_idconv', 'europepmc', 'unpaywall', 'core', 'doaj', 'openaire', 'ads', 'wikidata', 'handle', 'isbnlib', 'openlibrary', 'internetarchive', 'hathitrust', 'gbooks', 'worldcat', 'fatcat', 'annas', 'libgen', 'nexusstc', 'deterministic', 'manual'));
ALTER TABLE identifier_versions
  ADD COLUMN asserted_by text,
  ADD COLUMN derived_from_scheme text REFERENCES scheme_registry (scheme),
  ADD COLUMN derived_from_value text,
  ADD COLUMN provenance_backfilled boolean NOT NULL DEFAULT false;
-- NULL is allowed on purpose: every row written before 0032 has no asserted_by, and that is a measured fact
-- (`identifiers_without_provenance`), closed by the reviewed backfill, never by a default that would invent it
ALTER TABLE identifier_versions ADD CONSTRAINT identifier_versions_asserted_by_check
  CHECK (asserted_by IS NULL OR asserted_by IN ('crossref', 'datacite', 'arxiv', 's2', 'openalex', 'opencitations', 'pubmed', 'pmc_idconv', 'europepmc', 'unpaywall', 'core', 'doaj', 'openaire', 'ads', 'wikidata', 'handle', 'isbnlib', 'openlibrary', 'internetarchive', 'hathitrust', 'gbooks', 'worldcat', 'fatcat', 'annas', 'libgen', 'nexusstc', 'deterministic', 'manual', 'caller', 'tracker', 'legacy'));
ALTER TABLE identifier_versions ADD CONSTRAINT identifier_versions_derived_from_pair
  CHECK ((derived_from_scheme IS NULL) = (derived_from_value IS NULL)
         AND (derived_from_value IS NULL OR btrim(derived_from_value) <> ''));

-- the views expand `v.*` at creation, so they are re-stated to carry the new columns (appended at the end,
-- which CREATE OR REPLACE VIEW allows)
CREATE OR REPLACE VIEW main_identifiers AS
  SELECT i.scheme, i.value_norm, i.active, v.*
    FROM identifiers i JOIN identifier_versions v ON v.version_id = i.current_version_id;

CREATE OR REPLACE VIEW ws_identifiers AS
  SELECT ws.id AS view_workstream_id, i.scheme, i.value_norm, v.*
    FROM workstreams ws CROSS JOIN identifiers i
    LEFT JOIN ws_heads h ON h.workstream_id = ws.id AND h.entity = 'identifier' AND h.entity_id = i.id
    JOIN identifier_versions v ON v.version_id = coalesce(h.version_id, i.current_version_id);

-- ── 6. parent columns for the common cases ───────────────────────────────────────────────────────────
ALTER TABLE works
  ADD COLUMN part_of_work_id uuid REFERENCES works (id),
  ADD COLUMN version_of_work_id uuid REFERENCES works (id),
  ADD CONSTRAINT works_parent_not_self CHECK (part_of_work_id IS DISTINCT FROM id AND version_of_work_id IS DISTINCT FROM id);

-- fatcat's merge, as a rule the table enforces: a parent is filled once and never overwritten
CREATE FUNCTION litkb._works_parent_monotone() RETURNS trigger
LANGUAGE plpgsql SET search_path = litkb, public, pg_temp AS $$
BEGIN
  -- BEGIN guard: a work's parent is filled once and never overwritten
  IF (OLD.part_of_work_id IS NOT NULL AND NEW.part_of_work_id IS DISTINCT FROM OLD.part_of_work_id)
     OR (OLD.version_of_work_id IS NOT NULL AND NEW.version_of_work_id IS DISTINCT FROM OLD.version_of_work_id) THEN
    RAISE EXCEPTION 'litkb: work % already has its parent; a later source fills a NULL and never overwrites', OLD.id
      USING ERRCODE = '23514';
  END IF;
  -- END guard: a work's parent is filled once and never overwritten
  RETURN NEW;
END
$$;
CREATE TRIGGER works_parent_monotone BEFORE UPDATE OF part_of_work_id, version_of_work_id ON works
  FOR EACH ROW EXECUTE FUNCTION litkb._works_parent_monotone();

CREATE OR REPLACE VIEW main_works AS
  SELECT w.key, v.*, w.part_of_work_id, w.version_of_work_id
    FROM works w JOIN work_versions v ON v.version_id = w.current_version_id;

CREATE OR REPLACE VIEW ws_works AS
  SELECT ws.id AS view_workstream_id, w.key, v.*, w.part_of_work_id, w.version_of_work_id
    FROM workstreams ws CROSS JOIN works w
    LEFT JOIN ws_heads h ON h.workstream_id = ws.id AND h.entity = 'work' AND h.entity_id = w.id
    JOIN work_versions v ON v.version_id = coalesce(h.version_id, w.current_version_id);

-- ── 7. the edge table, with the third state ──────────────────────────────────────────────────────────
CREATE TABLE work_relations (
  id                  uuid PRIMARY KEY DEFAULT uuidv7(),
  work_id             uuid NOT NULL REFERENCES works (id),
  relation            text CHECK (relation IN ('is_part_of', 'has_part', 'is_version_of', 'has_version', 'is_new_version_of', 'is_previous_version_of', 'is_preprint_of', 'has_preprint', 'is_manuscript_of', 'has_manuscript', 'is_identical_to', 'is_same_as', 'is_variant_form_of', 'is_original_form_of', 'is_supplement_to', 'is_supplemented_by', 'is_correction_of', 'has_correction', 'is_review_of', 'has_review', 'is_translation_of', 'has_translation', 'is_replaced_by', 'replaces', 'is_derived_from', 'has_derivation', 'is_expression_of', 'has_expression', 'is_manifestation_of', 'has_manifestation', 'other')),
  state               text NOT NULL CHECK (state IN ('asserted', 'none_returned')),
  source_relation     text,
  target_scheme       text REFERENCES scheme_registry (scheme),
  target_value        text,
  target_value_norm   text,
  target_work_id      uuid REFERENCES works (id),
  asserted_by         text NOT NULL CHECK (asserted_by IN ('crossref', 'datacite', 'arxiv', 's2', 'openalex', 'opencitations', 'pubmed', 'pmc_idconv', 'europepmc', 'unpaywall', 'core', 'doaj', 'openaire', 'ads', 'wikidata', 'handle', 'isbnlib', 'openlibrary', 'internetarchive', 'hathitrust', 'gbooks', 'worldcat', 'fatcat', 'annas', 'libgen', 'nexusstc', 'deterministic', 'manual', 'caller', 'tracker', 'legacy', 'conflict-resolution')),
  derived_from_scheme text REFERENCES scheme_registry (scheme),
  derived_from_value  text,
  conflict_source     text REFERENCES scheme_registry (scheme),
  evidence            jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(evidence) = 'object'),
  workstream_id       uuid NOT NULL REFERENCES workstreams (id),
  agent               text NOT NULL CHECK (agent <> ''),
  session_id          text NOT NULL CHECK (session_id <> ''),
  created_at          timestamptz NOT NULL DEFAULT now(),
  -- the third state has no relation and no target; an asserted edge has both
  CONSTRAINT work_relations_state_shape CHECK (
    (state = 'asserted' AND relation IS NOT NULL AND target_scheme IS NOT NULL AND coalesce(target_value_norm, '') <> '')
    OR (state = 'none_returned' AND relation IS NULL AND target_scheme IS NULL AND target_value IS NULL
        AND target_work_id IS NULL)),
  CONSTRAINT work_relations_not_self CHECK (target_work_id IS DISTINCT FROM work_id),
  CONSTRAINT work_relations_derived_from_pair CHECK ((derived_from_scheme IS NULL) = (derived_from_value IS NULL)),
  -- only the conflict rule names the scheme that collided, and it always does
  CONSTRAINT work_relations_conflict_source CHECK ((asserted_by = 'conflict-resolution') = (conflict_source IS NOT NULL))
);
CREATE INDEX work_relations_work ON work_relations (work_id);
CREATE INDEX work_relations_target_work ON work_relations (target_work_id);

CREATE FUNCTION litkb._relation_inverse(p_relation text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
  SELECT CASE p_relation
    WHEN 'is_part_of' THEN 'has_part'
    WHEN 'is_version_of' THEN 'has_version'
    WHEN 'is_new_version_of' THEN 'is_previous_version_of'
    WHEN 'is_preprint_of' THEN 'has_preprint'
    WHEN 'is_manuscript_of' THEN 'has_manuscript'
    WHEN 'is_variant_form_of' THEN 'is_original_form_of'
    WHEN 'is_supplement_to' THEN 'is_supplemented_by'
    WHEN 'is_correction_of' THEN 'has_correction'
    WHEN 'is_review_of' THEN 'has_review'
    WHEN 'is_translation_of' THEN 'has_translation'
    WHEN 'is_replaced_by' THEN 'replaces'
    WHEN 'is_derived_from' THEN 'has_derivation'
    WHEN 'is_expression_of' THEN 'has_expression'
    WHEN 'is_manifestation_of' THEN 'has_manifestation'
    WHEN 'has_part' THEN 'is_part_of'
    WHEN 'has_version' THEN 'is_version_of'
    WHEN 'is_previous_version_of' THEN 'is_new_version_of'
    WHEN 'has_preprint' THEN 'is_preprint_of'
    WHEN 'has_manuscript' THEN 'is_manuscript_of'
    WHEN 'is_original_form_of' THEN 'is_variant_form_of'
    WHEN 'is_supplemented_by' THEN 'is_supplement_to'
    WHEN 'has_correction' THEN 'is_correction_of'
    WHEN 'has_review' THEN 'is_review_of'
    WHEN 'has_translation' THEN 'is_translation_of'
    WHEN 'replaces' THEN 'is_replaced_by'
    WHEN 'has_derivation' THEN 'is_derived_from'
    WHEN 'has_expression' THEN 'is_expression_of'
    WHEN 'has_manifestation' THEN 'is_manifestation_of'
    WHEN 'is_identical_to' THEN 'is_identical_to'
    WHEN 'is_same_as' THEN 'is_same_as'
    WHEN 'other' THEN 'other'
  END
$$;

-- ── 8. the conflict rule, counted ────────────────────────────────────────────────────────────────────
CREATE TABLE identifier_conflicts (
  id                  uuid PRIMARY KEY DEFAULT uuidv7(),
  scheme              text NOT NULL REFERENCES scheme_registry (scheme),
  value               text NOT NULL,
  value_norm          text NOT NULL,
  claimed_by_work_id  uuid NOT NULL REFERENCES works (id),
  held_by_work_id     uuid NOT NULL REFERENCES works (id),
  edge_id             uuid NOT NULL REFERENCES work_relations (id),
  asserted_by         text NOT NULL CHECK (asserted_by IN ('crossref', 'datacite', 'arxiv', 's2', 'openalex', 'opencitations', 'pubmed', 'pmc_idconv', 'europepmc', 'unpaywall', 'core', 'doaj', 'openaire', 'ads', 'wikidata', 'handle', 'isbnlib', 'openlibrary', 'internetarchive', 'hathitrust', 'gbooks', 'worldcat', 'fatcat', 'annas', 'libgen', 'nexusstc', 'deterministic', 'manual', 'caller', 'tracker', 'legacy')),
  derived_from_scheme text REFERENCES scheme_registry (scheme),
  derived_from_value  text,
  resolution          text NOT NULL DEFAULT 'dropped' CHECK (resolution IN ('dropped')),
  evidence            jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(evidence) = 'object'),
  workstream_id       uuid NOT NULL REFERENCES workstreams (id),
  agent               text NOT NULL CHECK (agent <> ''),
  session_id          text NOT NULL CHECK (session_id <> ''),
  created_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT identifier_conflicts_two_works CHECK (claimed_by_work_id <> held_by_work_id),
  CONSTRAINT identifier_conflicts_once UNIQUE (scheme, value_norm, claimed_by_work_id, held_by_work_id)
);

-- Every claim record_identifiers weighs (a registered scheme, a value that normalises, provenance named) is a
-- row here, INSERTED BEFORE the claim is resolved and given its outcome after: `written` (a new identifier
-- version), `held` (the work already holds it — fatcat's monotone merge), `conflict` (another work holds it as
-- identity: dropped, edge asserted, counted in identifier_conflicts), `collided` (the unique index refused the
-- write: a conflict the rule did NOT resolve — kept here so it cannot vanish into a rolled-back error). The
-- counter `conflicts_uncounted` reads the EVENTS here against the resolutions in identifier_conflicts (Codex
-- X4: a unique index means the duplicate never persists, so a surviving-duplicate query alone is blind).
CREATE TABLE identifier_claims (
  id                  uuid PRIMARY KEY DEFAULT uuidv7(),
  work_id             uuid NOT NULL REFERENCES works (id),
  scheme              text NOT NULL REFERENCES scheme_registry (scheme),
  value               text NOT NULL,
  value_norm          text NOT NULL,
  asserted_by         text NOT NULL CHECK (asserted_by IN ('crossref', 'datacite', 'arxiv', 's2', 'openalex', 'opencitations', 'pubmed', 'pmc_idconv', 'europepmc', 'unpaywall', 'core', 'doaj', 'openaire', 'ads', 'wikidata', 'handle', 'isbnlib', 'openlibrary', 'internetarchive', 'hathitrust', 'gbooks', 'worldcat', 'fatcat', 'annas', 'libgen', 'nexusstc', 'deterministic', 'manual', 'caller', 'tracker', 'legacy')),
  derived_from_scheme text REFERENCES scheme_registry (scheme),
  derived_from_value  text,
  -- NULL only between the INSERT and the resolution inside one call; a committed NULL is a claim whose
  -- resolution was never recorded, and conflicts_uncounted counts it
  outcome             text CHECK (outcome IS NULL OR outcome IN ('written', 'held', 'conflict', 'collided')),
  held_by_work_id     uuid REFERENCES works (id),
  error               text,
  workstream_id       uuid NOT NULL REFERENCES workstreams (id),
  agent               text NOT NULL CHECK (agent <> ''),
  session_id          text NOT NULL CHECK (session_id <> ''),
  created_at          timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT identifier_claims_conflict_names_holder CHECK ((outcome = 'conflict') = (held_by_work_id IS NOT NULL)),
  CONSTRAINT identifier_claims_collided_says_why CHECK ((outcome = 'collided') = (error IS NOT NULL))
);
CREATE INDEX identifier_claims_value ON identifier_claims (scheme, value_norm);

-- ── 9. the harvest's write path ──────────────────────────────────────────────────────────────────────
-- The mode a harvested fact is written in: a work in main takes it as a fact, as registry admission writes
-- its identifiers (litkb.admit, fact mode); a work that is still this workstream's own proposal (a manual
-- admission not yet approved) takes it as a proposal, so it travels with the work's chain.
CREATE FUNCTION litkb._harvest_mode(p_workstream uuid, p_work uuid) RETURNS text
LANGUAGE plpgsql STABLE SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_main uuid;
BEGIN
  SELECT w.current_version_id INTO v_main FROM works w WHERE w.id = p_work;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: no work %', p_work USING ERRCODE = 'P0002';
  END IF;
  IF v_main IS NOT NULL THEN
    RETURN 'fact';
  END IF;
  PERFORM 1 FROM ws_heads h WHERE h.workstream_id = p_workstream AND h.entity = 'work' AND h.entity_id = p_work;
  IF FOUND THEN
    RETURN 'proposal';
  END IF;
  RAISE EXCEPTION 'litkb: work % is neither in main nor a proposal of workstream %', p_work, p_workstream
    USING ERRCODE = '42501';
END
$$;

-- a work's type as this workstream sees it (main's version, else its own proposal)
CREATE FUNCTION litkb._work_type(p_workstream uuid, p_work uuid) RETURNS text
LANGUAGE sql STABLE SET search_path = litkb, public, pg_temp AS $$
  SELECT v.type FROM works w
    LEFT JOIN ws_heads h ON h.workstream_id = p_workstream AND h.entity = 'work' AND h.entity_id = w.id
    JOIN work_versions v ON v.version_id = coalesce(h.version_id, w.current_version_id)
   WHERE w.id = p_work
$$;

-- the work that holds (scheme, value_norm) in a way that makes it that work's identity: a DISTINCT scheme,
-- or a type-scoped scheme where both works are of its identity types. NULL when none.
CREATE FUNCTION litkb._identity_holder(p_workstream uuid, p_scheme text, p_value_norm text, p_work uuid) RETURNS uuid
LANGUAGE sql STABLE SET search_path = litkb, public, pg_temp AS $$
  SELECT iv.work_id
    FROM scheme_registry sr
    JOIN identifiers idf ON idf.scheme = sr.scheme AND idf.value_norm = p_value_norm
    JOIN identifier_versions iv ON iv.identifier_id = idf.id
   WHERE sr.scheme = p_scheme AND iv.work_id <> p_work AND iv.status = 'active'
     AND ((idf.active AND iv.version_id = idf.current_version_id) OR iv.state = 'proposed')
     AND (sr.distinct_values
          OR (sr.identity_types IS NOT NULL
              AND _work_type(p_workstream, p_work) = ANY (sr.identity_types)
              AND _work_type(p_workstream, iv.work_id) = ANY (sr.identity_types)))
   ORDER BY iv.created_at
   LIMIT 1
$$;

CREATE FUNCTION litkb.record_identifiers(p_workstream uuid, p_ws_token text, p_work uuid, p_identifiers jsonb,
                                         p_agent text, p_session text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  i jsonb;
  sr record;
  v_mode text;
  v_norm text;
  v_other uuid;
  v_id uuid;
  v_ver uuid;
  v_edge uuid;
  v_rel text;
  v_claim uuid;
  v_written jsonb := '[]'::jsonb;
  v_held jsonb := '[]'::jsonb;
  v_conflicts jsonb := '[]'::jsonb;
  v_refused jsonb := '[]'::jsonb;
  v_collided jsonb := '[]'::jsonb;
BEGIN
  -- BEGIN guard: record_identifiers presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: record_identifiers presents the workstream token
  PERFORM 1 FROM workstreams w WHERE w.id = p_workstream AND w.state = 'open' FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % is not open', p_workstream USING ERRCODE = '22023';
  END IF;
  IF norm_label(coalesce(p_agent, '')) = '' OR norm_label(coalesce(p_session, '')) = '' THEN
    RAISE EXCEPTION 'litkb: an agent and a session label are required' USING ERRCODE = '22023';
  END IF;
  IF jsonb_typeof(coalesce(p_identifiers, '[]'::jsonb)) <> 'array' THEN
    RAISE EXCEPTION 'litkb: identifiers must be a JSON array' USING ERRCODE = '22023';
  END IF;
  v_mode := _harvest_mode(p_workstream, p_work);
  FOR i IN SELECT x FROM jsonb_array_elements(coalesce(p_identifiers, '[]'::jsonb)) x LOOP
    SELECT * INTO sr FROM scheme_registry r WHERE r.scheme = i->>'scheme';
    IF NOT FOUND THEN
      v_refused := v_refused || jsonb_build_object('scheme', i->>'scheme', 'value', i->>'value',
                                                   'reason', 'a scheme litkb.scheme_registry does not hold');
      CONTINUE;
    END IF;
    -- BEGIN guard: a harvested identifier names who asserted it
    IF coalesce(btrim(i->>'asserted_by'), '') = '' THEN
      RAISE EXCEPTION 'litkb: identifier %:% names no asserted_by; a harvested identifier always names its source',
        i->>'scheme', i->>'value' USING ERRCODE = '22023';
    END IF;
    -- END guard: a harvested identifier names who asserted it
    v_norm := norm_identifier(sr.scheme, i->>'value');
    IF coalesce(v_norm, '') = '' THEN
      v_refused := v_refused || jsonb_build_object('scheme', sr.scheme, 'value', i->>'value',
                                                   'reason', 'normalises to nothing');
      CONTINUE;
    END IF;
    -- BEGIN guard: a CANDIDATE identifier is written only once a registry confirms it
    -- A zero-request derivation that is only a candidate (`litkb.identifiers.arxiv_to_doi`: the 10.48550 DOI
    -- arXiv mints, a candidate until DataCite confirms it — plan item 3) carries evidence.candidate; it is
    -- refused here until its caller names the registry that confirmed it (verified_by). Auditor-B1 F12.
    -- A REGISTRY: `deterministic` is the derivation itself and `manual` a person, so neither confirms a candidate
    -- (auditor-B1 round 2 N1: both wrote the arXiv DOI as an active fact; integrator-w2).
    IF coalesce(i->'evidence'->>'candidate', '') = 'true'
       AND coalesce(btrim(i->>'verified_by'), '') IN ('', 'deterministic', 'manual') THEN
      v_refused := v_refused || jsonb_build_object('scheme', sr.scheme, 'value', i->>'value',
                                                   'reason', 'a candidate identifier waits for a registry''s confirmation (verified_by)');
      CONTINUE;
    END IF;
    -- END guard: a CANDIDATE identifier is written only once a registry confirms it
    PERFORM pg_advisory_xact_lock(hashtextextended('litkb:identifier:' || sr.scheme || ':' || v_norm, 0));
    -- BEGIN guard: every claim of an identifier is recorded before its resolution
    INSERT INTO identifier_claims (work_id, scheme, value, value_norm, asserted_by, derived_from_scheme,
                                   derived_from_value, workstream_id, agent, session_id)
    VALUES (p_work, sr.scheme, i->>'value', v_norm, i->>'asserted_by', i->'derived_from'->>'scheme',
            i->'derived_from'->>'value', p_workstream, p_agent, p_session)
    RETURNING id INTO v_claim;
    -- END guard: every claim of an identifier is recorded before its resolution
    -- fatcat's merge: a value the work already holds is filled already; nothing is overwritten
    IF EXISTS (SELECT 1 FROM identifiers idf JOIN identifier_versions iv ON iv.identifier_id = idf.id
                WHERE idf.scheme = sr.scheme AND idf.value_norm = v_norm AND iv.work_id = p_work
                  AND iv.status = 'active' AND (iv.version_id = idf.current_version_id OR iv.state = 'proposed')) THEN
      UPDATE identifier_claims SET outcome = 'held' WHERE id = v_claim;
      v_held := v_held || jsonb_build_object('scheme', sr.scheme, 'value', v_norm);
      CONTINUE;
    END IF;
    -- BEGIN guard: two works claiming one distinct-valued identifier are a counted conflict, never a second row
    v_other := _identity_holder(p_workstream, sr.scheme, v_norm, p_work);
    IF v_other IS NOT NULL THEN
      IF EXISTS (SELECT 1 FROM identifier_conflicts c
                  WHERE c.scheme = sr.scheme AND c.value_norm = v_norm AND c.claimed_by_work_id = p_work
                    AND c.held_by_work_id = v_other) THEN
        UPDATE identifier_claims SET outcome = 'conflict', held_by_work_id = v_other WHERE id = v_claim;
        v_conflicts := v_conflicts || jsonb_build_object('scheme', sr.scheme, 'value', v_norm,
                                                         'held_by', v_other, 'already_counted', true);
        CONTINUE;
      END IF;
      -- the grouping: two books with one ISBN are the same edition; a distinct identifier of another work
      -- makes this work a version of it (a preprint offered its article's DOI) — or what the caller names
      v_rel := coalesce(nullif(i->>'conflict_relation', ''),
                        CASE WHEN sr.distinct_values THEN 'is_version_of' ELSE 'is_identical_to' END);
      IF v_rel NOT IN ('is_version_of', 'is_identical_to') THEN
        RAISE EXCEPTION 'litkb: conflict_relation must be is_version_of or is_identical_to, got %', v_rel
          USING ERRCODE = '22023';
      END IF;
      INSERT INTO work_relations (work_id, relation, state, source_relation, target_scheme, target_value,
                                  target_value_norm, target_work_id, asserted_by, derived_from_scheme,
                                  derived_from_value, conflict_source, evidence, workstream_id, agent, session_id)
      VALUES (p_work, v_rel, 'asserted', NULL, sr.scheme, i->>'value', v_norm, v_other, 'conflict-resolution',
              i->'derived_from'->>'scheme', i->'derived_from'->>'value', sr.scheme,
              jsonb_build_object('dropped', i), p_workstream, p_agent, p_session)
      RETURNING id INTO v_edge;
      -- BEGIN guard: a conflict is counted
      INSERT INTO identifier_conflicts (scheme, value, value_norm, claimed_by_work_id, held_by_work_id, edge_id,
                                        asserted_by, derived_from_scheme, derived_from_value, evidence,
                                        workstream_id, agent, session_id)
      VALUES (sr.scheme, i->>'value', v_norm, p_work, v_other, v_edge, i->>'asserted_by',
              i->'derived_from'->>'scheme', i->'derived_from'->>'value', coalesce(i->'evidence', '{}'::jsonb),
              p_workstream, p_agent, p_session);
      -- END guard: a conflict is counted
      UPDATE identifier_claims SET outcome = 'conflict', held_by_work_id = v_other WHERE id = v_claim;
      v_conflicts := v_conflicts || jsonb_build_object('scheme', sr.scheme, 'value', v_norm, 'held_by', v_other,
                                                       'edge_id', v_edge, 'relation', v_rel);
      CONTINUE;
    END IF;
    -- END guard: two works claiming one distinct-valued identifier are a counted conflict, never a second row
    BEGIN
      SELECT w.entity_id, w.version_id INTO v_id, v_ver
        FROM _write_version(v_mode, 'identifier', NULL, jsonb_build_object('scheme', sr.scheme), NULL,
                            jsonb_build_object('work_id', p_work,
                                               'value', CASE WHEN sr.scheme = 'doi' THEN v_norm ELSE i->>'value' END,
                                               'verified_by', nullif(i->>'verified_by', ''),
                                               'evidence', coalesce(i->'evidence', '{}'::jsonb), 'status', 'active',
                                               'asserted_by', i->>'asserted_by',
                                               'derived_from_scheme', i->'derived_from'->>'scheme',
                                               'derived_from_value', i->'derived_from'->>'value'),
                            NULL, p_workstream, p_agent, p_session) w;
      UPDATE identifier_claims SET outcome = 'written' WHERE id = v_claim;
      v_written := v_written || jsonb_build_object('scheme', sr.scheme, 'value', v_norm, 'identifier_id', v_id,
                                                   'version_id', v_ver, 'mode', v_mode);
    EXCEPTION WHEN unique_violation THEN
      -- BEGIN guard: a claim that collides on the unique index is recorded, never lost
      -- The conflict rule above did not see a holder, yet the index did: a conflict the rule failed to
      -- resolve (a race, or the rule broken). The write is rolled back to this block; the claim row, written
      -- before it, stays and says so — conflicts_uncounted counts it. Only unique_violation is caught: every
      -- other error still aborts the call.
      UPDATE identifier_claims SET outcome = 'collided', error = SQLERRM WHERE id = v_claim;
      v_collided := v_collided || jsonb_build_object('scheme', sr.scheme, 'value', v_norm, 'error', SQLERRM);
      -- END guard: a claim that collides on the unique index is recorded, never lost
    END;
  END LOOP;
  RETURN jsonb_build_object('written', v_written, 'held', v_held, 'conflicts', v_conflicts, 'refused', v_refused,
                            'collided', v_collided);
END
$$;

-- a parent column filled from a relation whose direction the registry stated (monotone; see the trigger)
CREATE FUNCTION litkb._fill_parent(p_child uuid, p_column text, p_parent uuid) RETURNS text
LANGUAGE plpgsql SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_now uuid;
BEGIN
  IF p_column = 'part_of' THEN
    SELECT part_of_work_id INTO v_now FROM works WHERE id = p_child FOR UPDATE;
    IF v_now IS NULL THEN
      UPDATE works SET part_of_work_id = p_parent WHERE id = p_child;
      RETURN 'filled';
    END IF;
  ELSE
    SELECT version_of_work_id INTO v_now FROM works WHERE id = p_child FOR UPDATE;
    IF v_now IS NULL THEN
      UPDATE works SET version_of_work_id = p_parent WHERE id = p_child;
      RETURN 'filled';
    END IF;
  END IF;
  RETURN CASE WHEN v_now = p_parent THEN 'held' ELSE 'kept-existing' END;
END
$$;

CREATE FUNCTION litkb.record_work_relations(p_workstream uuid, p_ws_token text, p_work uuid, p_relations jsonb,
                                            p_agent text, p_session text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  r jsonb;
  v_state text;
  v_rel text;
  v_scheme text;
  v_norm text;
  v_target uuid;
  v_edge uuid;
  v_parent text;
  v_prior_target uuid;
  v_prior_rel text;
  v_out jsonb := '[]'::jsonb;
BEGIN
  -- BEGIN guard: record_work_relations presents the workstream token
  PERFORM _require_ws_token(p_workstream, p_ws_token);
  -- END guard: record_work_relations presents the workstream token
  PERFORM 1 FROM workstreams w WHERE w.id = p_workstream AND w.state = 'open' FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: workstream % is not open', p_workstream USING ERRCODE = '22023';
  END IF;
  IF norm_label(coalesce(p_agent, '')) = '' OR norm_label(coalesce(p_session, '')) = '' THEN
    RAISE EXCEPTION 'litkb: an agent and a session label are required' USING ERRCODE = '22023';
  END IF;
  IF jsonb_typeof(coalesce(p_relations, '[]'::jsonb)) <> 'array' THEN
    RAISE EXCEPTION 'litkb: relations must be a JSON array' USING ERRCODE = '22023';
  END IF;
  PERFORM _harvest_mode(p_workstream, p_work);           -- the work exists and this workstream may see it
  FOR r IN SELECT x FROM jsonb_array_elements(coalesce(p_relations, '[]'::jsonb)) x LOOP
    v_state := coalesce(nullif(r->>'state', ''), 'asserted');
    IF v_state = 'none_returned' THEN
      -- the third state, once per (work, source, input): asked, and nothing came back
      IF NOT EXISTS (SELECT 1 FROM work_relations e
                      WHERE e.work_id = p_work AND e.state = 'none_returned' AND e.asserted_by = r->>'asserted_by'
                        AND e.derived_from_value IS NOT DISTINCT FROM r->'derived_from'->>'value') THEN
        INSERT INTO work_relations (work_id, relation, state, asserted_by, derived_from_scheme, derived_from_value,
                                    evidence, workstream_id, agent, session_id)
        VALUES (p_work, NULL, 'none_returned', r->>'asserted_by', r->'derived_from'->>'scheme',
                r->'derived_from'->>'value', coalesce(r->'evidence', '{}'::jsonb), p_workstream, p_agent, p_session)
        RETURNING id INTO v_edge;
        v_out := v_out || jsonb_build_object('state', 'none_returned', 'edge_id', v_edge);
      ELSE
        v_out := v_out || jsonb_build_object('state', 'none_returned', 'held', true);
      END IF;
      CONTINUE;
    END IF;
    v_rel := r->>'relation';
    v_scheme := r->>'target_scheme';
    v_norm := norm_identifier(v_scheme, r->>'target_value');
    IF v_rel IS NULL OR v_scheme IS NULL OR coalesce(v_norm, '') = '' OR coalesce(btrim(r->>'asserted_by'), '') = '' THEN
      v_out := v_out || jsonb_build_object('relation', v_rel, 'refused',
                                           'an asserted edge needs a relation, a target identifier and its source');
      CONTINUE;
    END IF;
    v_target := _identity_holder(p_workstream, v_scheme, v_norm, p_work);
    -- BEGIN guard: a relation's target through a type-scoped identifier is the work of that type
    -- `_identity_holder` asks whether a value is identity BETWEEN two works (isbn: both books), so a chapter's
    -- `is_part_of isbn:<its book's ISBN>` found no target and chapter -> book — the plan's first common case —
    -- never filled part_of_work_id (auditor-B1 F13). A relation TARGET named by a type-scoped scheme is the
    -- work of one of that scheme's identity types holding the value, whatever this work's own type.
    IF v_target IS NULL THEN
      SELECT iv.work_id INTO v_target
        FROM scheme_registry sr
        JOIN identifiers idf ON idf.scheme = sr.scheme AND idf.value_norm = v_norm
        JOIN identifier_versions iv ON iv.identifier_id = idf.id
       WHERE sr.scheme = v_scheme AND sr.identity_types IS NOT NULL AND iv.work_id <> p_work
         AND iv.status = 'active' AND ((idf.active AND iv.version_id = idf.current_version_id) OR iv.state = 'proposed')
         AND _work_type(p_workstream, iv.work_id) = ANY (sr.identity_types)
       ORDER BY iv.created_at
       LIMIT 1;
    END IF;
    -- END guard: a relation's target through a type-scoped identifier is the work of that type
    -- one fact, recorded once: the same edge, or its inverse from the other side — including an inverse
    -- written BEFORE this work existed, whose target is one of this work's identifiers but whose
    -- target_work_id is still NULL: that NULL is FILLED now (a later source fills a null), and the parent
    -- column its direction names is filled with it
    SELECT e.id, e.target_work_id, e.relation INTO v_edge, v_prior_target, v_prior_rel FROM work_relations e
     WHERE e.state = 'asserted'
       AND ((e.work_id = p_work AND e.relation = v_rel AND e.target_scheme = v_scheme AND e.target_value_norm = v_norm)
            OR (v_target IS NOT NULL AND e.work_id = v_target AND e.relation = _relation_inverse(v_rel)
                AND (e.target_work_id = p_work
                     OR (e.target_work_id IS NULL AND EXISTS (
                           SELECT 1 FROM identifiers idf JOIN identifier_versions iv ON iv.identifier_id = idf.id
                            WHERE iv.work_id = p_work AND iv.status = 'active' AND idf.scheme = e.target_scheme
                              AND idf.value_norm = e.target_value_norm
                              AND (iv.version_id = idf.current_version_id OR iv.state = 'proposed'))))))
     LIMIT 1;
    IF v_edge IS NOT NULL THEN
      v_parent := NULL;
      -- BEGIN guard: an edge whose target arrived later gets its target work, and the parent it names
      IF v_prior_target IS NULL AND v_target IS NOT NULL THEN
        UPDATE work_relations SET target_work_id = p_work WHERE id = v_edge AND target_work_id IS NULL;
        -- the earlier edge is v_target -[v_prior_rel]-> this work
        v_parent := CASE
          WHEN v_prior_rel = 'is_part_of' THEN _fill_parent(v_target, 'part_of', p_work)
          WHEN v_prior_rel = 'has_part' THEN _fill_parent(p_work, 'part_of', v_target)
          WHEN v_prior_rel IN ('is_preprint_of', 'is_version_of') THEN _fill_parent(v_target, 'version_of', p_work)
          WHEN v_prior_rel IN ('has_preprint', 'has_version') THEN _fill_parent(p_work, 'version_of', v_target)
        END;
      END IF;
      -- END guard: an edge whose target arrived later gets its target work, and the parent it names
      v_out := v_out || jsonb_build_object('relation', v_rel, 'edge_id', v_edge, 'held', true, 'parent', v_parent);
      CONTINUE;
    END IF;
    INSERT INTO work_relations (work_id, relation, state, source_relation, target_scheme, target_value,
                                target_value_norm, target_work_id, asserted_by, derived_from_scheme,
                                derived_from_value, evidence, workstream_id, agent, session_id)
    VALUES (p_work, v_rel, 'asserted', r->>'source_relation', v_scheme, r->>'target_value', v_norm, v_target,
            r->>'asserted_by', r->'derived_from'->>'scheme', r->'derived_from'->>'value',
            coalesce(r->'evidence', '{}'::jsonb), p_workstream, p_agent, p_session)
    RETURNING id INTO v_edge;
    v_parent := NULL;
    -- BEGIN guard: a parent column is filled only from a relation whose direction the registry stated
    IF v_target IS NOT NULL THEN
      v_parent := CASE
        WHEN v_rel = 'is_part_of' THEN _fill_parent(p_work, 'part_of', v_target)
        WHEN v_rel = 'has_part' THEN _fill_parent(v_target, 'part_of', p_work)
        WHEN v_rel IN ('is_preprint_of', 'is_version_of') THEN _fill_parent(p_work, 'version_of', v_target)
        WHEN v_rel IN ('has_preprint', 'has_version') THEN _fill_parent(v_target, 'version_of', p_work)
      END;
    END IF;
    -- END guard: a parent column is filled only from a relation whose direction the registry stated
    v_out := v_out || jsonb_build_object('relation', v_rel, 'edge_id', v_edge, 'target_work_id', v_target,
                                         'parent', v_parent);
  END LOOP;
  RETURN jsonb_build_object('edges', v_out);
END
$$;

-- ── the reviewed backfill of historical provenance (the ingest login; dry run unless p_apply) ─────────
-- Every row written before 0032 has asserted_by NULL. The source is re-derived from what the row itself says,
-- and nothing else: a `tracker` row came from the literature tracker, a `legacy_stem` row from the legacy
-- corpus, a row `verified_by='manual'` from a manual admitter, and every other admitted row from the caller
-- that handed the identifier in. A NULL is FILLED and marked `provenance_backfilled`; nothing is overwritten.
CREATE FUNCTION litkb.backfill_identifier_provenance(p_apply boolean, p_session text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = litkb, public, pg_temp AS $$
DECLARE
  v_plan jsonb;
  v_n bigint := 0;
BEGIN
  IF norm_label(coalesce(p_session, '')) = '' THEN
    RAISE EXCEPTION 'litkb: a session label is required' USING ERRCODE = '22023';
  END IF;
  SELECT coalesce(jsonb_object_agg(k, n), '{}'::jsonb) INTO v_plan FROM (
    SELECT i.scheme || ' -> ' || _backfill_source(i.scheme, v.verified_by) AS k, count(*) AS n
      FROM identifier_versions v JOIN identifiers i ON i.id = v.identifier_id
     WHERE v.asserted_by IS NULL GROUP BY 1) s;
  IF coalesce(p_apply, false) THEN
    UPDATE identifier_versions v
       SET asserted_by = _backfill_source(i.scheme, v.verified_by), provenance_backfilled = true
      FROM identifiers i
     WHERE i.id = v.identifier_id AND v.asserted_by IS NULL;
    GET DIAGNOSTICS v_n = ROW_COUNT;
  END IF;
  RETURN jsonb_build_object('apply', coalesce(p_apply, false), 'plan', v_plan, 'updated', v_n, 'session', p_session);
END
$$;

CREATE FUNCTION litkb._backfill_source(p_scheme text, p_verified_by text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path = litkb, public, pg_temp AS $$
  SELECT CASE WHEN p_scheme = 'tracker' THEN 'tracker'
              WHEN p_scheme = 'legacy_stem' THEN 'legacy'
              WHEN p_verified_by = 'manual' THEN 'manual'
              ELSE 'caller' END
$$;

-- ── 10. check 1 and admission, replaced ──────────────────────────────────────────────────────────────
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
    -- 0032: the schemes check 1 confirms against a registry are the registry's `registry_confirmed`
    -- rows (doi, arxiv, isbn — 0020's list, unchanged), not a list written into this body
    CONTINUE WHEN NOT EXISTS (SELECT 1 FROM scheme_registry sr
                               WHERE sr.scheme = i->>'scheme' AND sr.registry_confirmed);
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
  v_asserted text;
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
  -- BEGIN guard: a harvested identifier enters through record_identifiers, never through admission
  -- 0032: a row derived from another identifier (a Crossref `alternative-id`, an Anna's
  -- `identifiers_unified` key, a zero-request derivation) is HARVEST, and the conflict rule that decides
  -- what happens when it names another work lives in ONE place, litkb.record_identifiers. Admission
  -- takes only the identifiers the admission is about.
  IF jsonb_typeof(coalesce(p_identifiers, '[]'::jsonb)) = 'array' AND EXISTS (
       SELECT 1 FROM jsonb_array_elements(coalesce(p_identifiers, '[]'::jsonb)) x WHERE x ? 'derived_from') THEN
    RAISE EXCEPTION 'litkb: an identifier with derived_from is a harvest row; litkb.record_identifiers takes it'
      USING ERRCODE = '22023';
  END IF;
  -- END guard: a harvested identifier enters through record_identifiers, never through admission
  IF jsonb_typeof(coalesce(p_identifiers, '[]'::jsonb)) = 'array' AND EXISTS (
       SELECT 1 FROM jsonb_array_elements(coalesce(p_identifiers, '[]'::jsonb)) x
        WHERE NOT EXISTS (SELECT 1 FROM scheme_registry sr WHERE sr.scheme = x->>'scheme')) THEN
    RAISE EXCEPTION 'litkb: an identifier names a scheme litkb.scheme_registry does not hold' USING ERRCODE = '22023';
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
  -- 0032: an identifier is a duplicate only where the registry says its value names ONE work
  -- (distinct_values), or — for a type-scoped scheme — where both works are of the scheme's identity types
  -- (isbn: two books; a chapter carrying its book's ISBN is data, not a duplicate).
  SELECT iv.work_id INTO v_existing
    FROM jsonb_array_elements(coalesce(p_identifiers, '[]'::jsonb)) x
    JOIN scheme_registry sr ON sr.scheme = x->>'scheme'
    JOIN identifiers idf ON idf.scheme = x->>'scheme' AND idf.value_norm = norm_identifier(x->>'scheme', x->>'value')
    JOIN identifier_versions iv ON iv.identifier_id = idf.id
   WHERE iv.status = 'active' AND ((idf.active AND iv.version_id = idf.current_version_id) OR iv.state = 'proposed')
     AND (sr.distinct_values
          OR (sr.identity_types IS NOT NULL AND coalesce(p_work->>'type', 'article') = ANY (sr.identity_types)
              AND EXISTS (SELECT 1 FROM works ow JOIN work_versions ov ON ov.work_id = ow.id
                           WHERE ow.id = iv.work_id AND ov.type = ANY (sr.identity_types)
                             AND (ov.version_id = ow.current_version_id OR ov.state = 'proposed'))))
   LIMIT 1;
  IF v_existing IS NOT NULL THEN
    v_checks := v_checks || jsonb_build_object('check2_duplicate', jsonb_build_object('verdict', 'duplicate', 'work_id', v_existing));
    v_adm := _refuse_admission(p_workstream, p_candidate, p_route, p_agent, p_session, v_checks, 'duplicate',
                               'identifier already admitted', v_existing);
    RETURN jsonb_build_object('outcome', 'duplicate', 'admission_id', v_adm, 'work_id', v_existing, 'checks', v_checks);
  END IF;
  -- END guard: check 2 identifier lookup

  -- 0032: identifier-first — the strong schemes are the registry's `identity_strong` rows (0014's list
  -- doi arxiv isbn pmid pmcid jstor, less handle — see the registry's why): a candidate holding one that no
  -- existing work holds is a DIFFERENT record, possibly related (litkb-sibling-edition), never a title
  -- duplicate. A strong scheme counts only where it is THIS candidate's identity: a distinct scheme, or a
  -- type-scoped one whose types include the candidate's (an ISBN on a report or a chapter is not the
  -- report's identity — the lookup above did not look for it, so the title review must still run; auditor-B1 F6)
  SELECT count(*) INTO v_strong FROM jsonb_array_elements(coalesce(p_identifiers, '[]'::jsonb)) x
    JOIN scheme_registry sr ON sr.scheme = x->>'scheme' AND sr.identity_strong
     AND (sr.distinct_values OR coalesce(p_work->>'type', 'article') = ANY (coalesce(sr.identity_types, '{}'::text[])));
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
        v_asserted := nullif(btrim(i->>'asserted_by'), '');
        -- BEGIN guard: an admitted identifier carries who asserted it
        -- 0032 (LINKAGE §3.2 item 2): the caller that handed the identifier in, unless it said otherwise —
        -- a manual admitter, the literature tracker, the legacy corpus, or the admitting caller (a hunt
        -- reference, a CLI flag) whose value the registry then confirms (verified_by)
        v_asserted := coalesce(v_asserted, CASE WHEN p_route = 'manual' THEN 'manual'
                                                WHEN i->>'scheme' = 'tracker' THEN 'tracker'
                                                WHEN i->>'scheme' = 'legacy_stem' THEN 'legacy'
                                                ELSE 'caller' END);
        -- END guard: an admitted identifier carries who asserted it
        SELECT w.entity_id, w.version_id INTO v_id, v_ver
          FROM _write_version(v_mode, 'identifier', NULL, jsonb_build_object('scheme', i->>'scheme'), NULL,
                              jsonb_build_object('work_id', v_work,
                                                 -- D1: the canonical DOI is the stored value
                                                 'value', CASE WHEN i->>'scheme' = 'doi' THEN norm_identifier('doi', i->>'value')
                                                               ELSE i->>'value' END,
                                                 'verified_by', i->>'verified_by',
                                                 'evidence', coalesce(i->'evidence', '{}'::jsonb), 'status', 'active',
                                                 'asserted_by', v_asserted),
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

-- ── privileges ───────────────────────────────────────────────────────────────────────────────────────
REVOKE ALL ON scheme_registry, work_relations, identifier_conflicts, identifier_claims FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION
  litkb.record_identifiers(uuid, text, uuid, jsonb, text, text),
  litkb.record_work_relations(uuid, text, uuid, jsonb, text, text),
  litkb.backfill_identifier_provenance(boolean, text),
  litkb._works_parent_monotone(), litkb._relation_inverse(text), litkb._harvest_mode(uuid, uuid),
  litkb._work_type(uuid, uuid), litkb._identity_holder(uuid, text, text, uuid), litkb._fill_parent(uuid, text, uuid),
  litkb._backfill_source(text, text)
FROM PUBLIC;
-- BEGIN guard: the writer records harvested identifiers and relations, the ingest login the backfill, neither a direct write
GRANT EXECUTE ON FUNCTION
  litkb.record_identifiers(uuid, text, uuid, jsonb, text, text),
  litkb.record_work_relations(uuid, text, uuid, jsonb, text, text)
TO litkb_writer;
GRANT EXECUTE ON FUNCTION litkb.backfill_identifier_provenance(boolean, text) TO litkb_ingest;
-- END guard: the writer records harvested identifiers and relations, the ingest login the backfill, neither a direct write
GRANT SELECT ON scheme_registry, work_relations, identifier_conflicts, identifier_claims TO litkb_reader, litkb_writer, litkb_promoter;

-- end of 0032
