-- litkb 0027 — `hunt_requests.ref_scheme` gains `'title'`. One CHECK is replaced; no row is
-- read, rewritten or deleted, and no function body changes.
--
-- ── WHY ──────────────────────────────────────────────────────────────────────────────────
-- S1 (LITKB_WORKPLAN.md "### S1 — The front door") gives discovery to a lit-scout whose ONLY
-- write into litkb is a drop-off. A scout works from search results, and a search result very
-- often carries a title, an author and a year and NO identifier at all — Crossref's own
-- `query.bibliographic` is the route litkb already resolves such a reference by
-- (`litkb.admit.resolver.resolve_doi`). Before this migration the scout had two ways to record
-- that find and both were wrong: call it `'other'`, which says nothing a later hunt can act on,
-- or call it `'url'` and hand the hunt a search-engine link that is not the document. `'title'`
-- says what the reference IS, and `litkb hunt` now validates and resolves it
-- (`litkb/hunt.py::validate_ref` -> `resolve_doi` -> the UNCHANGED confirm gate -> admit).
--
-- ── THE MEASURED BEFORE-STATE ────────────────────────────────────────────────────────────
-- On litkb_test_w1, 2026-09-20, migrations 0001..0026 applied:
--
--   SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
--    WHERE conrelid = 'litkb.hunt_requests'::regclass AND contype = 'c' ORDER BY conname;
--
--   hunt_requests_ref_scheme_check | CHECK ((ref_scheme = ANY (ARRAY['doi'::text, 'arxiv'::text,
--     'jstor'::text, 'isbn'::text, 'pmid'::text, 'pmcid'::text, 'openalex'::text, 's2'::text,
--     'handle'::text, 'url'::text, 'tracker'::text, 'legacy_stem'::text, 'other'::text])))
--
-- The constraint is UNNAMED in 0023 (an inline column CHECK), so Postgres named it
-- `hunt_requests_ref_scheme_check`. That measured name is what is dropped and re-created below,
-- rather than a guessed one, and the new constraint carries the SAME name so anything that
-- reports a violation by constraint name keeps reporting it.
--
-- ── WHAT ELSE RE-VALIDATES THE SCHEME: NOTHING IN SQL, CHECKED ───────────────────────────
-- `litkb.record_hunt_request` (0023, lines 102-104 of that file) is deliberately thin: "every
-- NOT NULL field the table itself requires is enforced by the table's own CHECK constraints", and
-- its body passes `p_ref_scheme` straight into the INSERT. It holds no vocabulary of its own, so
-- it is NOT replaced here — which also keeps this migration clear of the CREATE OR REPLACE
-- hazard `_reserved.txt` records (0018 vs 0020): a function two branches replace ends up with a
-- body decided by APPLY order. Verified by reading 0023 and by
-- `git grep -n "hunt_requests\|record_hunt_request"` over the migrations directory of every local
-- and remote `work/*` / `fix/*` ref, 2026-09-20: 0023 is the only migration that names either,
-- and no open branch holds a migration numbered 0024 or above (0024 is RETIRED).
--
-- The PYTHON half of the vocabulary is `litkb.hunt_request.REF_SCHEMES` — ONE constant, imported
-- by `litkb/hunt.py`, `litkb/commands.py` and `litkb/mcp/server.py` (CLAUDE.md §3.3, one fact one
-- home). `qc/test_litkb_hunt_request.py::test_the_sql_check_and_the_python_vocabulary_agree`
-- parses the CHECK out of these migration files, takes the HIGHEST-numbered one that states it,
-- and asserts set equality with that constant — so a future migration that widens the SQL
-- vocabulary and forgets the Python constant (or the reverse) fails the suite. That gate is the
-- reason this file may be read by a test: the alternative is a stale copy in Python refusing a
-- scheme the database accepts, at the MCP layer, where the scout's first `title` drop-off would
-- have died.

SET LOCAL search_path = litkb, public;

ALTER TABLE hunt_requests DROP CONSTRAINT hunt_requests_ref_scheme_check;
ALTER TABLE hunt_requests ADD CONSTRAINT hunt_requests_ref_scheme_check CHECK (ref_scheme IN
  ('doi', 'arxiv', 'jstor', 'isbn', 'pmid', 'pmcid', 'openalex', 's2',
   'handle', 'url', 'tracker', 'legacy_stem', 'title', 'other'));

COMMENT ON COLUMN hunt_requests.ref_scheme IS
  'The vocabulary of the CHECK above, and its Python twin litkb.hunt_request.REF_SCHEMES '
  '(one fact, one home: qc/test_litkb_hunt_request.py asserts the two are equal). '
  '''title'' (migration 0027) is a reference carried as title + author + year with no identifier '
  'at all — what a web search result usually is. `litkb hunt` resolves it through '
  'litkb.admit.resolver.resolve_doi and the unchanged confirm gate; a title with no author '
  'surname or no year is refused (malformed-ref), because the resolver needs both and guessing '
  'either is how a wrong work gets admitted.';

-- end of 0027
