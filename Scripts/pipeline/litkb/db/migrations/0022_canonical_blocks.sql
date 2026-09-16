-- litkb 0022 — one canonical block per region, and an honest word for every stored LaTeX string.
--
-- Closes three of the caveats in Reports/LITKB_P5_FINAL_REFEREE_2026-09-16.md. ADDITIVE ONLY:
-- blocks, equations and extraction_disagreements were built by 0002 and 0017 and applied
-- migrations are checksum-locked, so this file widens a CHECK, adds a column and adds a trigger,
-- and rewrites nothing.
--
-- 1. THE DUPLICATE CANONICAL BLOCK (referee §4: 63 groups at an identical (file, page, bbox), in
--    6 runs). The reconciler now emits ONE block per region — `litkb.extract.reconcile
--    ._merge_regions` — and this is the guard that makes "one block per region" a property of the
--    DATABASE rather than of one function nobody re-reads. An exact `(run_id, page_no, bbox)`
--    repeat among canonical blocks is refused at INSERT.
--
--    WHY A TRIGGER AND NOT A UNIQUE INDEX, which is what a reader expects here. `litkb` already
--    HOLDS those 63 groups, inside `ok` runs. An `ok` run's rows cannot be deleted by anyone:
--    `litkb.clear_extraction_rows` (0017) refuses a run whose status is `ok`, and the ingest login
--    holds no DELETE on any table. So `CREATE UNIQUE INDEX` would succeed on a freshly migrated
--    `litkb_test` and FAIL on the live database — the same migration set producing two different
--    schemas, which is the exact defect 0021 was written to undo. A BEFORE INSERT trigger fires
--    on new rows only: every run made from here carries the property, the superseded runs keep
--    their history, and both databases end with one schema.
--
--    Scope is the RUN, not the file. One file legitimately has several runs (a re-ingest at a new
--    pipeline version is a new run beside the old one), and each of them describes the same
--    rectangles; a file-scoped rule would refuse the second run's first block.
--
-- 2. THE TWO NEW DISAGREEMENT KINDS. §7 stage 5 says a disputed region is KEPT and marked, never
--    silently resolved, and 0017's CHECK names the five shapes the first reconciler could
--    produce. The merge produces two more, and both are the record of a block that is no longer
--    emitted — without them the merge would be a deletion:
--      * `duplicate_region` — two readings of one region; one canonical block was emitted and the
--        other reading is stored here.
--      * `superset_region`  — one tool merged a region the other segmented (the referee's Pengra
--        p7 case: a 3,392-character GROBID <p> holding the page's two table captions and its body
--        text, each of which is also its own block). The segmented blocks are canonical and the
--        merged reading is stored here.
--
-- 3. equations.latex_status — referee §3: 9 of 20 sampled LaTeX strings are wrong, and NOTHING in
--    the database says which. The L4 pass's own verdict (`ok` / `unstable` / `degenerate`) was
--    used as a FILTER and then thrown away, so a decode the pass refused to stand behind and an
--    equation the pass never saw were both stored as a NULL `latex` and could not be told apart.
--    Five values, each a different fact about the same row:
--      stable       the L4 pass returned `ok` and the crop it decoded held no text from outside
--                   the equation's own box.
--      contaminated the L4 pass returned `ok` and the crop DID hold text from outside the box
--                   (docling's own 0.18 expansion factor around a tall equation reaches several
--                   printed lines), which is the referee's E01/E06/E11/E19 class. The LaTeX is
--                   stored; it is NOT called stable.
--      unstable     the pass's own re-decode did not reproduce. `latex` stays NULL.
--      degenerate   the pass detected a repetition loop. `latex` stays NULL.
--      unverified   no L4 row exists for this equation at all. `latex` stays NULL.
--    NOT a claim that a `stable` string is RIGHT. Nothing in this system has scored a decode
--    against the page, and the referee's twenty draws are the only measurement that exists; this
--    column records what IS known — the pass's verdict, and whether the crop was clean — and the
--    words are chosen so that neither can be read as the other.

SET LOCAL search_path = litkb, public;

-- BEGIN: the two disagreement shapes the merge produces
ALTER TABLE litkb.extraction_disagreements DROP CONSTRAINT extraction_disagreements_kind_check;
ALTER TABLE litkb.extraction_disagreements ADD CONSTRAINT extraction_disagreements_kind_check
  CHECK (kind IN ('kind_conflict', 'text_conflict', 'partial_overlap',
                  'grobid_only', 'docling_only',
                  'duplicate_region', 'superset_region'));
-- END

-- BEGIN guard: a run never holds the same canonical rectangle twice
CREATE FUNCTION litkb._block_region_is_canonical_once() RETURNS trigger
LANGUAGE plpgsql SET search_path = litkb, public, pg_temp AS $$
BEGIN
  IF NEW.canonical IS NOT TRUE OR NEW.bbox IS NULL THEN
    RETURN NEW;
  END IF;
  PERFORM 1 FROM blocks b
   WHERE b.run_id = NEW.run_id AND b.page_no = NEW.page_no AND b.canonical
     AND b.bbox = NEW.bbox AND b.id IS DISTINCT FROM NEW.id;
  IF FOUND THEN
    RAISE EXCEPTION 'litkb: run % already has a canonical block at page % bbox %',
                    NEW.run_id, NEW.page_no, NEW.bbox
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
$$;

CREATE TRIGGER blocks_region_is_canonical_once BEFORE INSERT ON blocks
  FOR EACH ROW EXECUTE FUNCTION litkb._block_region_is_canonical_once();
-- END guard

-- BEGIN: what is known about each stored LaTeX string
ALTER TABLE litkb.equations ADD COLUMN latex_status text;
ALTER TABLE litkb.equations ADD CONSTRAINT equations_latex_status_check
  CHECK (latex_status IS NULL OR latex_status IN
         ('stable', 'contaminated', 'unstable', 'degenerate', 'unverified'));
-- A string the pass refused to stand behind must never be STORED as the equation: that is the
-- one gate between the L4 pass's own refusals and the corpus (referee kill R8), and it belongs
-- in the schema as well as in the loader, because the loader is one caller.
ALTER TABLE litkb.equations ADD CONSTRAINT equations_refused_decode_is_not_stored
  CHECK (latex IS NULL OR latex_status IS NULL
         OR latex_status IN ('stable', 'contaminated'));
-- END
