-- litkb 0021 — one definition of the feeds validator, so the schema stops depending on apply order.
--
-- THE DEFECT THIS CLOSES is not a bug in either branch. `work/20260915-access-layer` (0018) and
-- `work/20260913-literature-kb` (0020) both widened `litkb._feeds_token_ok` from three of the
-- convention's seven feeds forms to all seven, independently, without either seeing the other. Both
-- are CREATE OR REPLACE, and a CREATE OR REPLACE is decided by the order the migrations were
-- APPLIED, not by their numbers. So:
--
--   * `litkb`, `litkb_test` and the worker databases already held 0020 when 0018 arrived at the
--     merge, so they ended with 0018's body;
--   * a database built from scratch runs 0018 then 0020 and ends with 0020's.
--
-- Same migration set, same checksums, two different schemas — and each body refuses something the
-- other accepts, so each one fails a test the other passes. Measured on `litkb_test` immediately
-- after 0018 landed on top of 0020 (2026-09-16):
--
--     framework §13.1.1        -> false   (0018's depth rule: at most one sub-level)
--     report notmd#§5          -> TRUE    (0018's `[^ ]+`: the file part need not be a .md file)
--
-- and a from-scratch build would have answered the other way round on both. `test_litkb_p8.py`
-- asserts the first is refused; `test_litkb_first_use.py` asserts the second is refused. Neither
-- suite was wrong; the schema was two schemas.
--
-- 0020 is applied and checksum-locked, and 0018 is now applied too, so neither can be the one that
-- changes (`litkb.db.migrate`: "an applied migration may never change"). The remaining move is the
-- one `_reserved.txt` named — "a later migration states the definition once" — and this is it.
-- Because 0021 is the HIGHEST number it is applied LAST on every database, whatever order the
-- earlier two arrived in, so its body is the body everywhere.
--
-- WHICH BODY. The two differ in exactly two clauses, and each disagreement is settled against
-- `Scripts/docs/LITERATURE_CONVENTION.md`, which is the one home for what a token MEANS (this regex
-- is the one home for its SHAPE):
--
--   1. `framework §N` — 0018 allows at most one sub-level, 0020 any depth. The convention's own
--      closing line says "`review §N` may carry any number of sub-levels (`review §4.18.4`);
--      `framework §N` at most one (`framework §13.1`)", and its table spells the token
--      `framework §N[.N]`. 0018's clause is the convention's; it is kept. The stricter rule is also
--      the one that can be relaxed later without invalidating a stored token, which the looser one
--      cannot.
--   2. `report <FILE>#§<loc>` — 0018 allows any non-space FILE part, 0020 requires it to name a
--      `.md` file and allows `§` inside `loc`. The convention says "any other tracked report", and
--      every tracked report in `Reports/` is a `.md` file; `report notmd#§5` names no document at
--      all, and the whole point of the 2026-09-13 vocabulary is that "a bare `§N` is no longer valid
--      on its own" — a token that cannot be resolved to a document is that same defect wearing a
--      prefix. 0020's clause is kept.
--
-- The other five clauses are byte-identical in both and are carried over unchanged.
--
-- NOTHING ELSE IS IN THIS MIGRATION. It replaces one function body and grants nothing new: 0020
-- already granted EXECUTE to `litkb_writer`, and CREATE OR REPLACE keeps a function's ACL, so the
-- role census (`qc/test_litkb_p1.py::test_role_privilege_matrix`) is unchanged by this file. The
-- GRANT below is restated anyway, outside the guard, so that the migration is true on its own and so
-- that deleting the guarded block leaves a VALID migration whose function does the WRONG thing —
-- which is what a mutation row has to be able to do (0018's X11/X13/X14 note: "a row that breaks the
-- FILE proves the file is load-bearing; only a row that breaks the RULE proves the rule is").

SET LOCAL search_path = litkb, public;

-- BEGIN guard: the feeds vocabulary has one definition, independent of apply order
-- Seven clauses, one per line, in the convention's table order. A token is only a SHAPE here; that
-- the section, gate, row or decision it names EXISTS is checked against the target document, which
-- the database cannot read.
CREATE OR REPLACE FUNCTION litkb._feeds_token_ok(p_token text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
  SELECT coalesce(p_token ~ ('^(' ||
    'framework §[0-9]+(\.[0-9]+)?' ||
    '|narrative §[0-9]+' ||
    '|gated-plan gate [0-9]+' ||
    '|review §[0-9]+(\.[0-9]+)*' ||
    '|gap row [0-9]+' ||
    '|decision [a-z0-9][a-z0-9-]*' ||
    '|report [A-Za-z0-9][A-Za-z0-9._-]*\.md#§[A-Za-z0-9][A-Za-z0-9._§-]*' ||
    ')$'), false)
$$;
-- END guard: the feeds vocabulary has one definition, independent of apply order

COMMENT ON FUNCTION litkb._feeds_token_ok(text) IS
  'The feeds vocabulary of docs/LITERATURE_CONVENTION.md, all seven forms — the ONE definition '
  '(0021). 0018 and 0020 each replaced this function with a different seven-form body, so the '
  'schema depended on which order they were applied in; 0021 is applied last everywhere and settles '
  'it: framework §N takes at most one sub-level (the convention''s rule), a report token names a .md '
  'file and a location. Whether the section, gate, row or decision a token names EXISTS is checked '
  'against the target document, not here.';

-- Idempotent: 0020 granted this already and CREATE OR REPLACE does not reset a function's ACL. It is
-- restated so this file states the whole rule, and so the block above can be deleted by a mutation
-- without leaving a GRANT on a function that no longer exists.
GRANT EXECUTE ON FUNCTION litkb._feeds_token_ok(text) TO litkb_writer;

-- end of 0021
