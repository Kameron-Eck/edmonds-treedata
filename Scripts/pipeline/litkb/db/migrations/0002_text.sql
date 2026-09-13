-- litkb 0002 — text and structure (derived, immutable per extraction run), evidence, embeddings.
-- Design §4.4, §4.5 (use_evidence, use_embeddings). No rows are loaded in P1.
-- Embedding vectors are pgvector halfvec with the dimension recorded per row, so models can
-- be swapped or compared (§4.4); per-model indexes are created when a model is chosen (P7).

SET LOCAL search_path = litkb, public;

CREATE TABLE pages (
  file_id          uuid NOT NULL REFERENCES files (id),
  run_id           uuid NOT NULL REFERENCES extraction_runs (id),
  page_no          integer NOT NULL CHECK (page_no >= 1),
  width            double precision,
  height           double precision,
  rotation         integer CHECK (rotation IN (0, 90, 180, 270)),
  text_layer_chars integer CHECK (text_layer_chars >= 0),
  needs_ocr        boolean,
  image_path       text,
  PRIMARY KEY (run_id, page_no)
);

CREATE TABLE blocks (
  id              uuid PRIMARY KEY DEFAULT uuidv7(),
  file_id         uuid NOT NULL REFERENCES files (id),
  run_id          uuid NOT NULL REFERENCES extraction_runs (id),
  page_no         integer NOT NULL CHECK (page_no >= 1),
  -- canonical frame (§7.1): PDF points, top-left origin as displayed, (x0, y0, x1, y1)
  bbox            double precision[] CHECK (bbox IS NULL OR cardinality(bbox) = 4),
  reading_order   integer,
  type            text NOT NULL CHECK (type IN ('title', 'author', 'affiliation', 'abstract', 'heading', 'paragraph', 'list_item', 'footnote', 'caption', 'table', 'figure', 'equation', 'reference', 'page_header', 'page_footer', 'page_number', 'sidebar', 'other')),
  section_path    text[],
  text            text,
  latex           text,
  parent_block_id uuid REFERENCES blocks (id),
  extractor       text,
  confidence      real,
  canonical       boolean NOT NULL DEFAULT false
);
CREATE INDEX blocks_run_page ON blocks (run_id, page_no);

CREATE TABLE tables (
  block_id         uuid PRIMARY KEY REFERENCES blocks (id),
  n_rows           integer CHECK (n_rows >= 0),
  n_cols           integer CHECK (n_cols >= 0),
  cells            jsonb,
  caption_block_id uuid REFERENCES blocks (id)
);

CREATE TABLE figures (
  block_id          uuid PRIMARY KEY REFERENCES blocks (id),
  crop_path         text,
  caption_block_id  uuid REFERENCES blocks (id),
  description       text,
  description_model text
);

CREATE TABLE equations (
  block_id uuid PRIMARY KEY REFERENCES blocks (id),
  latex    text,
  display  text CHECK (display IN ('display', 'inline')),
  label    text
);

CREATE TABLE "references" (
  id               uuid PRIMARY KEY DEFAULT uuidv7(),
  file_id          uuid NOT NULL REFERENCES files (id),
  run_id           uuid NOT NULL REFERENCES extraction_runs (id),
  block_id         uuid REFERENCES blocks (id),
  raw_text         text NOT NULL,
  parsed           jsonb,
  resolved_work_id uuid REFERENCES works (id),
  resolution       text NOT NULL CHECK (resolution IN ('resolved', 'candidate', 'unresolved')),
  confidence       real
);
ALTER TABLE candidates ADD CONSTRAINT candidates_citing_reference_fk
  FOREIGN KEY (citing_reference_id) REFERENCES "references" (id);

CREATE TABLE citation_mentions (
  id           uuid PRIMARY KEY DEFAULT uuidv7(),
  block_id     uuid NOT NULL REFERENCES blocks (id),
  reference_id uuid NOT NULL REFERENCES "references" (id),
  char_start   integer NOT NULL CHECK (char_start >= 0),
  char_end     integer NOT NULL,
  CHECK (char_end > char_start)
);

CREATE TABLE chunks (
  id           uuid PRIMARY KEY DEFAULT uuidv7(),
  file_id      uuid NOT NULL REFERENCES files (id),
  work_id      uuid NOT NULL REFERENCES works (id),
  run_id       uuid NOT NULL REFERENCES extraction_runs (id),
  block_ids    uuid[] NOT NULL,
  kind         text NOT NULL CHECK (kind IN ('abstract', 'prose', 'table', 'caption', 'equation', 'reference')),
  section_path text[],
  page_start   integer,
  page_end     integer,
  text         text NOT NULL,
  tokens       integer CHECK (tokens >= 0)
);
CREATE INDEX chunks_run ON chunks (run_id);

CREATE TABLE embeddings (
  chunk_id uuid NOT NULL REFERENCES chunks (id),
  model    text NOT NULL CHECK (model <> ''),
  dim      integer NOT NULL CHECK (dim > 0),
  vector   halfvec NOT NULL,
  created  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (chunk_id, model),
  CHECK (vector_dims(vector) = dim)
);

CREATE TABLE use_evidence (
  id             uuid PRIMARY KEY DEFAULT uuidv7(),
  use_version_id uuid NOT NULL REFERENCES use_versions (version_id),
  block_id       uuid NOT NULL REFERENCES blocks (id),
  run_id         uuid NOT NULL REFERENCES extraction_runs (id),
  page           integer,
  quote          text NOT NULL CHECK (quote <> ''),
  char_start     integer NOT NULL CHECK (char_start >= 0),
  char_end       integer NOT NULL,
  stance         text NOT NULL CHECK (stance IN ('supports', 'refutes', 'context')),
  -- computed by the database (trigger in 0003); no role but the owner may name this column
  quote_verified boolean NOT NULL DEFAULT false,
  created_at     timestamptz NOT NULL DEFAULT now(),
  CHECK (char_end > char_start)
);
CREATE INDEX use_evidence_version ON use_evidence (use_version_id);

CREATE TABLE use_embeddings (
  use_version_id uuid NOT NULL REFERENCES use_versions (version_id),
  model          text NOT NULL CHECK (model <> ''),
  dim            integer NOT NULL CHECK (dim > 0),
  vector         halfvec NOT NULL,
  created        timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (use_version_id, model),
  CHECK (vector_dims(vector) = dim)
);
