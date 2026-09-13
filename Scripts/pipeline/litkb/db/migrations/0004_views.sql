-- litkb 0004 — views. Design §4.1: main's view is the version the identity row's pointer
-- names (never "the highest version"); a workstream's view is its ws_heads row if one
-- exists, else main's pointer. §4.5: use_evidence_status.

SET LOCAL search_path = litkb, public;

CREATE VIEW main_works AS
  SELECT w.key, v.*
    FROM works w JOIN work_versions v ON v.version_id = w.current_version_id;

CREATE VIEW main_identifiers AS
  SELECT i.scheme, i.value_norm, i.active, v.*
    FROM identifiers i JOIN identifier_versions v ON v.version_id = i.current_version_id;

CREATE VIEW main_files AS
  SELECT f.sha256, f.current_run_id, v.*
    FROM files f JOIN file_versions v ON v.version_id = f.current_version_id;

CREATE VIEW main_gaps AS
  SELECT g.slug, v.*
    FROM gaps g JOIN gap_versions v ON v.version_id = g.current_version_id;

CREATE VIEW main_uses AS
  SELECT u.work_id, u.gap_id, v.*
    FROM uses u JOIN use_versions v ON v.version_id = u.current_version_id;

-- one row per (workstream, entity) the workstream can see; filter on view_workstream_id
CREATE VIEW ws_works AS
  SELECT ws.id AS view_workstream_id, w.key, v.*
    FROM workstreams ws CROSS JOIN works w
    LEFT JOIN ws_heads h ON h.workstream_id = ws.id AND h.entity = 'work' AND h.entity_id = w.id
    JOIN work_versions v ON v.version_id = coalesce(h.version_id, w.current_version_id);

CREATE VIEW ws_identifiers AS
  SELECT ws.id AS view_workstream_id, i.scheme, i.value_norm, v.*
    FROM workstreams ws CROSS JOIN identifiers i
    LEFT JOIN ws_heads h ON h.workstream_id = ws.id AND h.entity = 'identifier' AND h.entity_id = i.id
    JOIN identifier_versions v ON v.version_id = coalesce(h.version_id, i.current_version_id);

CREATE VIEW ws_files AS
  SELECT ws.id AS view_workstream_id, f.sha256, f.current_run_id, v.*
    FROM workstreams ws CROSS JOIN files f
    LEFT JOIN ws_heads h ON h.workstream_id = ws.id AND h.entity = 'file' AND h.entity_id = f.id
    JOIN file_versions v ON v.version_id = coalesce(h.version_id, f.current_version_id);

CREATE VIEW ws_gaps AS
  SELECT ws.id AS view_workstream_id, g.slug, v.*
    FROM workstreams ws CROSS JOIN gaps g
    LEFT JOIN ws_heads h ON h.workstream_id = ws.id AND h.entity = 'gap' AND h.entity_id = g.id
    JOIN gap_versions v ON v.version_id = coalesce(h.version_id, g.current_version_id);

CREATE VIEW ws_uses AS
  SELECT ws.id AS view_workstream_id, u.work_id, u.gap_id, v.*
    FROM workstreams ws CROSS JOIN uses u
    LEFT JOIN ws_heads h ON h.workstream_id = ws.id AND h.entity = 'use' AND h.entity_id = u.id
    JOIN use_versions v ON v.version_id = coalesce(h.version_id, u.current_version_id);

-- §4.5: is the evidence's run still its file's current run? promotion refuses evidence that
-- is unverified or anchored in a superseded run.
CREATE VIEW use_evidence_status AS
  SELECT e.*, b.file_id, f.current_run_id,
         coalesce(e.run_id = f.current_run_id, false)                      AS run_is_current,
         coalesce(e.quote_verified AND e.run_id = f.current_run_id, false) AS promotable
    FROM use_evidence e
    JOIN blocks b ON b.id = e.block_id
    JOIN files f  ON f.id = b.file_id;
