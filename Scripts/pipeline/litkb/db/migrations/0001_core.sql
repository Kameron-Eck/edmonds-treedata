-- litkb 0001 — core schema: workstreams, promotions, the five versioned entities
-- (works, identifiers, files, gaps, uses), ws_heads, and the process tables.
-- Design: Scripts/LITERATURE_KB_DESIGN_2026-09-13.md §3, §4.1–§4.3, §4.5, §4.6 (checks 2, 4, 5).
--
-- Versioning pattern (§4.1): an identity row carries current_version_id (main's view), moved
-- only by the compare-and-set functions of 0003/0005; <entity>_versions rows are append-only.
-- Immutable identity fields (works.key, identifiers.scheme/value_norm, files.sha256,
-- gaps.slug, uses.work_id/gap_id) live on the identity row: they are what the entity IS.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
    RAISE EXCEPTION 'litkb: extension "vector" is not installed in database %; run py -3.12 -m litkb.db.provision as postgres first', current_database();
  END IF;
END
$$;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;

CREATE SCHEMA litkb;
REVOKE ALL ON SCHEMA litkb FROM PUBLIC;
-- functions are EXECUTE-able by PUBLIC by default; per-schema default privileges cannot
-- revoke a global default, so the global default for this owner is changed too (and 0006
-- revokes explicitly).
ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
SET LOCAL search_path = litkb, public;

-- ── process: workstreams and promotions ──────────────────────────────────────────────────

CREATE TABLE workstreams (
  id            uuid PRIMARY KEY DEFAULT uuidv7(),
  slug          text NOT NULL CHECK (slug <> ''),
  git_branch    text NOT NULL CHECK (git_branch <> ''),
  worktree_path text,
  purpose       text NOT NULL,
  brief_path    text,
  state         text NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'merged', 'abandoned')),
  opened_at     timestamptz NOT NULL DEFAULT now(),
  closed_at     timestamptz,
  merge_commit  text CHECK (merge_commit ~ '^[0-9a-f]{40}$'),
  CONSTRAINT workstreams_closed_iff_not_open CHECK ((state = 'open') = (closed_at IS NULL)),
  CONSTRAINT workstreams_merged_iff_commit CHECK ((state = 'merged') = (merge_commit IS NOT NULL))
);
CREATE UNIQUE INDEX workstreams_open_slug ON workstreams (slug) WHERE state = 'open';

CREATE TABLE promotions (
  id                 uuid PRIMARY KEY DEFAULT uuidv7(),
  workstream_id      uuid NOT NULL REFERENCES workstreams (id),
  state              text NOT NULL DEFAULT 'prepared' CHECK (state IN ('prepared', 'committed', 'abandoned')),
  prepared_at        timestamptz NOT NULL DEFAULT now(),
  branch_head_commit text NOT NULL CHECK (branch_head_commit ~ '^[0-9a-f]{40}$'),
  version_set_hash   text NOT NULL CHECK (version_set_hash ~ '^[0-9a-f]{64}$'),
  report_path        text,
  merge_commit       text CHECK (merge_commit ~ '^[0-9a-f]{40}$'),
  committed_at       timestamptz,
  counts             jsonb NOT NULL DEFAULT '{}'::jsonb,
  conflicts          jsonb NOT NULL DEFAULT '[]'::jsonb,
  CONSTRAINT promotions_committed_fields
    CHECK ((state = 'committed') = (merge_commit IS NOT NULL AND committed_at IS NOT NULL))
);
CREATE UNIQUE INDEX promotions_one_prepared_per_ws ON promotions (workstream_id) WHERE state = 'prepared';

-- ── works ────────────────────────────────────────────────────────────────────────────────

CREATE TABLE works (
  id                 uuid PRIMARY KEY DEFAULT uuidv7(),
  -- the file stem, Scripts/docs/LITERATURE_CONVENTION.md "File name": Surname (ASCII letters),
  -- 4-digit year with an optional a/b collision suffix, a 2-5 word lowercase hyphenated slug,
  -- whole name under 60 characters. Legacy stems are identifiers (scheme legacy_stem), not keys.
  key                text NOT NULL UNIQUE
                     CHECK (key ~ '^[A-Za-z]+_[0-9]{4}[ab]?_[a-z0-9]+(-[a-z0-9]+){1,4}$' AND length(key) < 60),
  created_at         timestamptz NOT NULL DEFAULT now(),
  created_in_ws      uuid NOT NULL REFERENCES workstreams (id),
  current_version_id uuid
);

CREATE TABLE work_versions (
  version_id          uuid PRIMARY KEY DEFAULT uuidv7(),
  work_id             uuid NOT NULL REFERENCES works (id),
  version_no          integer NOT NULL CHECK (version_no >= 1),
  type                text NOT NULL CHECK (type IN ('article', 'book', 'chapter', 'proceedings', 'report', 'thesis', 'preprint', 'dataset')),
  title               text NOT NULL CHECK (title <> ''),
  subtitle            text,
  authors             jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(authors) = 'array'),
  year                integer,
  venue               text,
  volume              text,
  issue               text,
  pages               text,
  publisher           text,
  language            text,
  abstract            text,
  change_reason       text,
  based_on_version_id uuid,
  workstream_id       uuid NOT NULL REFERENCES workstreams (id),
  agent               text NOT NULL CHECK (agent <> ''),
  session_id          text NOT NULL CHECK (session_id <> ''),
  created_at          timestamptz NOT NULL DEFAULT now(),
  state               text NOT NULL DEFAULT 'proposed' CHECK (state IN ('proposed', 'prepared', 'promoted', 'rejected', 'withdrawn')),
  promoted_at         timestamptz,
  promotion_id        uuid REFERENCES promotions (id),
  UNIQUE (work_id, version_no),
  UNIQUE (work_id, version_id),
  FOREIGN KEY (work_id, based_on_version_id) REFERENCES work_versions (work_id, version_id),
  CONSTRAINT work_versions_base_rule CHECK (
    CASE WHEN version_no = 1 THEN based_on_version_id IS NULL
         ELSE based_on_version_id IS NOT NULL AND coalesce(btrim(change_reason), '') <> '' END),
  CONSTRAINT work_versions_promoted_at CHECK ((state = 'promoted') = (promoted_at IS NOT NULL))
);
ALTER TABLE works ADD CONSTRAINT works_current_version_fk
  FOREIGN KEY (id, current_version_id) REFERENCES work_versions (work_id, version_id)
  DEFERRABLE INITIALLY DEFERRED;

-- ── identifiers ──────────────────────────────────────────────────────────────────────────

CREATE TABLE identifiers (
  id                 uuid PRIMARY KEY DEFAULT uuidv7(),
  scheme             text NOT NULL CHECK (scheme IN ('doi', 'arxiv', 'jstor', 'isbn', 'pmid', 'pmcid', 'openalex', 's2', 'handle', 'url', 'tracker', 'legacy_stem')),
  value_norm         text NOT NULL CHECK (value_norm <> ''),
  -- mirror of "main's current version has status active"; written ONLY by
  -- litkb._refresh_mirrors, in the same transaction as the pointer move. It exists so the
  -- partial unique index below can enforce check 2 against concurrent admissions.
  active             boolean NOT NULL DEFAULT false,
  created_at         timestamptz NOT NULL DEFAULT now(),
  created_in_ws      uuid NOT NULL REFERENCES workstreams (id),
  current_version_id uuid
);
CREATE UNIQUE INDEX identifiers_active_scheme_value ON identifiers (scheme, value_norm) WHERE active;

CREATE TABLE identifier_versions (
  version_id          uuid PRIMARY KEY DEFAULT uuidv7(),
  identifier_id       uuid NOT NULL REFERENCES identifiers (id),
  version_no          integer NOT NULL CHECK (version_no >= 1),
  work_id             uuid NOT NULL REFERENCES works (id),
  value               text NOT NULL CHECK (value <> ''),
  verified_by         text CHECK (verified_by IN ('crossref', 'datacite', 'arxiv', 's2', 'manual')),
  evidence            jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(evidence) = 'object'),
  status              text NOT NULL CHECK (status IN ('active', 'retracted')),
  change_reason       text,
  based_on_version_id uuid,
  workstream_id       uuid NOT NULL REFERENCES workstreams (id),
  agent               text NOT NULL CHECK (agent <> ''),
  session_id          text NOT NULL CHECK (session_id <> ''),
  created_at          timestamptz NOT NULL DEFAULT now(),
  state               text NOT NULL DEFAULT 'proposed' CHECK (state IN ('proposed', 'prepared', 'promoted', 'rejected', 'withdrawn')),
  promoted_at         timestamptz,
  promotion_id        uuid REFERENCES promotions (id),
  UNIQUE (identifier_id, version_no),
  UNIQUE (identifier_id, version_id),
  FOREIGN KEY (identifier_id, based_on_version_id) REFERENCES identifier_versions (identifier_id, version_id),
  CONSTRAINT identifier_versions_base_rule CHECK (
    CASE WHEN version_no = 1 THEN based_on_version_id IS NULL
         ELSE based_on_version_id IS NOT NULL AND coalesce(btrim(change_reason), '') <> '' END),
  CONSTRAINT identifier_versions_promoted_at CHECK ((state = 'promoted') = (promoted_at IS NOT NULL))
);
ALTER TABLE identifiers ADD CONSTRAINT identifiers_current_version_fk
  FOREIGN KEY (id, current_version_id) REFERENCES identifier_versions (identifier_id, version_id)
  DEFERRABLE INITIALLY DEFERRED;

-- ── files ────────────────────────────────────────────────────────────────────────────────

CREATE TABLE files (
  id                 uuid PRIMARY KEY DEFAULT uuidv7(),
  sha256             text NOT NULL UNIQUE CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  created_at         timestamptz NOT NULL DEFAULT now(),
  created_in_ws      uuid NOT NULL REFERENCES workstreams (id),
  current_version_id uuid,
  current_run_id     uuid   -- FK to extraction_runs added below; moved only by set_current_run()
);

CREATE TABLE file_versions (
  version_id          uuid PRIMARY KEY DEFAULT uuidv7(),
  file_id             uuid NOT NULL REFERENCES files (id),
  version_no          integer NOT NULL CHECK (version_no >= 1),
  work_id             uuid NOT NULL REFERENCES works (id),
  rel_path            text NOT NULL CHECK (rel_path <> ''),
  md5                 text CHECK (md5 ~ '^[0-9a-f]{32}$'),
  bytes               bigint CHECK (bytes >= 0),
  pages               integer CHECK (pages >= 0),
  has_text_layer      boolean,
  pdf_metadata        jsonb,
  copy_kind           text CHECK (copy_kind IN ('publisher', 'author manuscript', 'preprint', 'scan')),
  source_route        text,
  source_url          text,
  obtained_at         timestamptz,
  txt_extract_path    text,
  binding             jsonb,
  status              text NOT NULL CHECK (status IN ('active', 'quarantined', 'superseded')),
  status_reason       text,
  change_reason       text,
  based_on_version_id uuid,
  workstream_id       uuid NOT NULL REFERENCES workstreams (id),
  agent               text NOT NULL CHECK (agent <> ''),
  session_id          text NOT NULL CHECK (session_id <> ''),
  created_at          timestamptz NOT NULL DEFAULT now(),
  state               text NOT NULL DEFAULT 'proposed' CHECK (state IN ('proposed', 'prepared', 'promoted', 'rejected', 'withdrawn')),
  promoted_at         timestamptz,
  promotion_id        uuid REFERENCES promotions (id),
  UNIQUE (file_id, version_no),
  UNIQUE (file_id, version_id),
  FOREIGN KEY (file_id, based_on_version_id) REFERENCES file_versions (file_id, version_id),
  CONSTRAINT file_versions_base_rule CHECK (
    CASE WHEN version_no = 1 THEN based_on_version_id IS NULL
         ELSE based_on_version_id IS NOT NULL AND coalesce(btrim(change_reason), '') <> '' END),
  CONSTRAINT file_versions_promoted_at CHECK ((state = 'promoted') = (promoted_at IS NOT NULL))
);
ALTER TABLE files ADD CONSTRAINT files_current_version_fk
  FOREIGN KEY (id, current_version_id) REFERENCES file_versions (file_id, version_id)
  DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE extraction_runs (
  id               uuid PRIMARY KEY DEFAULT uuidv7(),
  file_id          uuid NOT NULL REFERENCES files (id),
  stage            text NOT NULL CHECK (stage <> ''),
  tool             text NOT NULL CHECK (tool <> ''),
  tool_version     text NOT NULL CHECK (tool_version <> ''),
  params_hash      text NOT NULL CHECK (params_hash <> ''),
  pipeline_version text NOT NULL CHECK (pipeline_version <> ''),
  host             text NOT NULL CHECK (host IN ('colab', 'local')),
  status           text NOT NULL CHECK (status IN ('ok', 'failed')),
  artifact_path    text,
  metrics          jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (file_id, stage, tool, tool_version, params_hash, pipeline_version),
  UNIQUE (file_id, id)
);
ALTER TABLE files ADD CONSTRAINT files_current_run_fk
  FOREIGN KEY (id, current_run_id) REFERENCES extraction_runs (file_id, id);

CREATE TABLE file_checks (
  id         uuid PRIMARY KEY DEFAULT uuidv7(),
  file_id    uuid NOT NULL REFERENCES files (id),
  check_kind text NOT NULL CHECK (check_kind IN ('hash', 'content_vs_registry', 'archive_record')),
  verdict    text NOT NULL CHECK (verdict IN ('pass', 'fail')),
  detail     jsonb NOT NULL DEFAULT '{}'::jsonb,
  run_at     timestamptz NOT NULL DEFAULT now()
);

-- ── gaps ─────────────────────────────────────────────────────────────────────────────────

CREATE TABLE gaps (
  id                 uuid PRIMARY KEY DEFAULT uuidv7(),
  slug               text NOT NULL UNIQUE CHECK (slug <> ''),
  created_at         timestamptz NOT NULL DEFAULT now(),
  created_in_ws      uuid NOT NULL REFERENCES workstreams (id),
  current_version_id uuid
);

CREATE TABLE gap_versions (
  version_id          uuid PRIMARY KEY DEFAULT uuidv7(),
  gap_id              uuid NOT NULL REFERENCES gaps (id),
  version_no          integer NOT NULL CHECK (version_no >= 1),
  question            text NOT NULL CHECK (question <> ''),
  framework_pointer   text,
  brief_path          text,
  -- design §4.5 calls this "state"; renamed so it cannot be confused with the version state
  gap_state           text NOT NULL CHECK (gap_state IN ('open', 'closed', 'abandoned')),
  change_reason       text,
  based_on_version_id uuid,
  workstream_id       uuid NOT NULL REFERENCES workstreams (id),
  agent               text NOT NULL CHECK (agent <> ''),
  session_id          text NOT NULL CHECK (session_id <> ''),
  created_at          timestamptz NOT NULL DEFAULT now(),
  state               text NOT NULL DEFAULT 'proposed' CHECK (state IN ('proposed', 'prepared', 'promoted', 'rejected', 'withdrawn')),
  promoted_at         timestamptz,
  promotion_id        uuid REFERENCES promotions (id),
  UNIQUE (gap_id, version_no),
  UNIQUE (gap_id, version_id),
  FOREIGN KEY (gap_id, based_on_version_id) REFERENCES gap_versions (gap_id, version_id),
  CONSTRAINT gap_versions_base_rule CHECK (
    CASE WHEN version_no = 1 THEN based_on_version_id IS NULL
         ELSE based_on_version_id IS NOT NULL AND coalesce(btrim(change_reason), '') <> '' END),
  CONSTRAINT gap_versions_promoted_at CHECK ((state = 'promoted') = (promoted_at IS NOT NULL))
);
ALTER TABLE gaps ADD CONSTRAINT gaps_current_version_fk
  FOREIGN KEY (id, current_version_id) REFERENCES gap_versions (gap_id, version_id)
  DEFERRABLE INITIALLY DEFERRED;

-- ── uses ─────────────────────────────────────────────────────────────────────────────────

CREATE TABLE uses (
  id                 uuid PRIMARY KEY DEFAULT uuidv7(),
  work_id            uuid NOT NULL REFERENCES works (id),
  gap_id             uuid REFERENCES gaps (id),
  created_at         timestamptz NOT NULL DEFAULT now(),
  created_in_ws      uuid NOT NULL REFERENCES workstreams (id),
  current_version_id uuid
);

CREATE TABLE use_versions (
  version_id          uuid PRIMARY KEY DEFAULT uuidv7(),
  use_id              uuid NOT NULL REFERENCES uses (id),
  version_no          integer NOT NULL CHECK (version_no >= 1),
  statement           text NOT NULL CHECK (statement <> ''),
  kind                text NOT NULL CHECK (kind IN ('method', 'theorem', 'parameter', 'empirical evidence', 'negative result', 'context', 'contradiction')),
  status              text NOT NULL CHECK (status IN ('proposed', 'supported', 'refuted', 'superseded', 'withdrawn')),
  confidence          text,
  feeds               text[] NOT NULL DEFAULT '{}',
  rationale           text,
  change_reason       text,
  based_on_version_id uuid,
  workstream_id       uuid NOT NULL REFERENCES workstreams (id),
  agent               text NOT NULL CHECK (agent <> ''),
  session_id          text NOT NULL CHECK (session_id <> ''),
  created_at          timestamptz NOT NULL DEFAULT now(),
  state               text NOT NULL DEFAULT 'proposed' CHECK (state IN ('proposed', 'prepared', 'promoted', 'rejected', 'withdrawn')),
  promoted_at         timestamptz,
  promotion_id        uuid REFERENCES promotions (id),
  UNIQUE (use_id, version_no),
  UNIQUE (use_id, version_id),
  FOREIGN KEY (use_id, based_on_version_id) REFERENCES use_versions (use_id, version_id),
  CONSTRAINT use_versions_base_rule CHECK (
    CASE WHEN version_no = 1 THEN based_on_version_id IS NULL
         ELSE based_on_version_id IS NOT NULL AND coalesce(btrim(change_reason), '') <> '' END),
  CONSTRAINT use_versions_promoted_at CHECK ((state = 'promoted') = (promoted_at IS NOT NULL))
);
ALTER TABLE uses ADD CONSTRAINT uses_current_version_fk
  FOREIGN KEY (id, current_version_id) REFERENCES use_versions (use_id, version_id)
  DEFERRABLE INITIALLY DEFERRED;

-- ── a workstream's view: its heads (pointers, moved only by compare-and-set) ─────────────

CREATE TABLE ws_heads (
  workstream_id uuid NOT NULL REFERENCES workstreams (id),
  entity        text NOT NULL CHECK (entity IN ('work', 'identifier', 'file', 'gap', 'use')),
  entity_id     uuid NOT NULL,
  version_id    uuid NOT NULL,
  PRIMARY KEY (workstream_id, entity, entity_id)
);

-- ── candidates, admissions, acquisition attempts ─────────────────────────────────────────

CREATE TABLE candidates (
  id                  uuid PRIMARY KEY DEFAULT uuidv7(),
  source              text NOT NULL CHECK (source IN ('paper-search', 'citation', 'manual')),
  source_detail       text,
  query               text,
  citing_reference_id uuid,   -- FK to "references" added in 0002
  raw_record          jsonb,
  title               text,
  authors             jsonb,
  year                integer,
  ids                 jsonb,
  state               text NOT NULL DEFAULT 'new' CHECK (state IN ('new', 'admitted', 'duplicate', 'rejected')),
  state_reason        text,
  admitted_work_id    uuid REFERENCES works (id),
  workstream_id       uuid REFERENCES workstreams (id),
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE admissions (
  id               uuid PRIMARY KEY DEFAULT uuidv7(),
  candidate_id     uuid REFERENCES candidates (id),
  work_id          uuid REFERENCES works (id),
  route            text NOT NULL CHECK (route IN ('registry', 'manual')),
  admitter_agent   text NOT NULL CHECK (admitter_agent <> ''),
  admitter_session text NOT NULL CHECK (admitter_session <> ''),
  state            text NOT NULL DEFAULT 'proposed' CHECK (state IN ('admitted', 'proposed', 'approved', 'refused')),
  approver_agent   text,
  approver_session text,
  approved_at      timestamptz,
  checks           jsonb NOT NULL DEFAULT '{}'::jsonb,
  workstream_id    uuid REFERENCES workstreams (id),
  created_at       timestamptz NOT NULL DEFAULT now(),
  -- §4.6 check 4 + decisions.yaml litkb-p0-foundation §15.13: a manual admission is signed
  -- off by a second agent session; the database refuses admitter = approver.
  CONSTRAINT admissions_second_agent_signs_off CHECK (
    (approver_agent IS NULL AND approver_session IS NULL AND approved_at IS NULL)
    OR (approver_agent IS NOT NULL AND approver_session IS NOT NULL AND approved_at IS NOT NULL
        AND approver_agent <> admitter_agent AND approver_session <> admitter_session)),
  CONSTRAINT admissions_approved_has_approver CHECK (state <> 'approved' OR approver_agent IS NOT NULL),
  CONSTRAINT admissions_manual_is_a_proposal CHECK (route <> 'manual' OR state IN ('proposed', 'approved', 'refused'))
);

CREATE TABLE acquisition_attempts (
  id              uuid PRIMARY KEY DEFAULT uuidv7(),
  work_id         uuid REFERENCES works (id),
  candidate_id    uuid REFERENCES candidates (id),
  route           text NOT NULL CHECK (route IN ('open_access', 'annas', 'scihub', 'browser')),
  identifier_used text,
  status          text NOT NULL CHECK (status IN ('ok', 'not-in-archive', 'bad-file', 'binding-failed', 'partner-404')),
  detail          jsonb NOT NULL DEFAULT '{}'::jsonb,
  http_codes      integer[],
  at              timestamptz NOT NULL DEFAULT now(),
  workstream_id   uuid REFERENCES workstreams (id),
  CHECK (work_id IS NOT NULL OR candidate_id IS NOT NULL)
);
