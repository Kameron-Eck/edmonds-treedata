-- litkb 0026 — `quote_verified` compares the block span and the quote with their LINE ENDINGS
-- CANONICAL, and nothing else normalised. Stored bytes are untouched: no block text, no stored
-- quote and no offset is rewritten by this migration, and nothing here writes to any table.
--
-- ── THE DEFECT, measured on the 2026-09-19 dump restored into litkb_test_w3 ───────────────
-- 48.9 % of CURRENT-RUN blocks (51,154 of 104,647) store `\r\n`, and 7 of the project's 8
-- verified spans cross one. The operational proving run (2026-09-20) surfaced what that costs at
-- the RECORDING end: the review writer is an LLM emitting JSON, and no LLM has been observed
-- emitting a raw CR byte, so every quote it sent was LF-only. Three layers then refused it, each
-- measured on block 01a0abc6-8ad9-72e7-8efd-9e850c978b28 with a 117-character span crossing the
-- block's first CRLF:
--     JSON transport          `\r\n` SURVIVES json.dumps/loads — the transport is not the problem
--     mcp/server.py           text.find(LF quote)      = -1   -> refused `quote-not-in-block`
--     use.py::locate_quote    position(LF quote in b.text) = 0 -> refused "in no extracted block"
--     THIS TRIGGER            substring(b.text …) = LF quote  = FALSE, at the correct raw offsets
-- So the writer recorded single-line FRAGMENTS instead (longest newline-free run in a real
-- verified span: 33 characters), and Codex found half the review's sentences overreaching them.
-- The grader had already solved exactly this comparison — `textnorm.canonical_newlines` on the
-- Python side, the same rewrite in SQL on the block side — and the RECORDING path had not.
--
-- ── WHAT CHANGES, AND WHAT DELIBERATELY DOES NOT ─────────────────────────────────────────
-- `litkb.canonical_newlines(text)` is created: ONE line ending -> ONE `\n` (`\r\n` and a lone
-- `\r` both become `\n`). It is the SQL half of `litkb.textnorm.canonical_newlines`, and it
-- exists so there is ONE SQL home for that rule instead of the inline expression this trigger,
-- `use.locate_quote` and `review_check._BLOCK_SQL` would otherwise each carry a copy of. The two
-- halves are bound by qc/test_litkb_review_check.py::
--   test_the_sql_and_python_newline_canonicalisations_agree, which now drives THIS function.
--
-- It is NOT a collapse of consecutive endings: `a\r\n\r\nb` -> `a\n\nb`, never `a\nb`. Collapsing
-- runs would let a quote silently JOIN two paragraphs of the block, which is a change of CONTENT,
-- not of encoding, and `qc/test_litkb_first_use.py::
--   test_a_quote_that_joins_two_paragraphs_by_dropping_a_blank_line_is_refused` is the kill.
--
-- The REVERSE GUARANTEE is unchanged and is the whole reason this is a rewrite of the ENCODING
-- only: `canonical_newlines` preserves every non-newline character, their order, and the NUMBER
-- of breaks, so `canon(span) = canon(quote)` holds exactly when the two agree on every character
-- and every break POSITION and differ only in how a break is WRITTEN. One changed character, one
-- dropped word, one joined paragraph — each still returns false.
--
-- The offsets stay the STORED text's own: `char_start`/`char_end` continue to index `b.text` raw,
-- the D-7 bound below is still `length(b.text)`, and `substring` still cuts the raw block. Only
-- the equality is canonical. That is what keeps the 8 existing verified rows verified (7 of them
-- store a CR), keeps `use_evidence_status.promotable` and `promote prepare` reading the same
-- column they always did, and keeps the grader's span-containment arithmetic (which canonicalises
-- the span text it is handed) pointing at the same bytes.
--
-- 0003:276-294 and 0007:163-189 are the earlier bodies of this trigger; from here they are DEAD
-- TEXT, the way 0007's ok-run rule became dead text when 0017 replaced it. The live definition is
-- the only one worth mutating (litkb_p2_mutations.py, row RC17).
--
-- ── WHY A QUOTE MAY NOT BEGIN OR END WITH A LINE BREAK (auditor-5, found before this migration
--    had been applied anywhere but a worker database, so it is EDITED IN PLACE rather than
--    superseded — no database holds the version without this clause) ────────────────────────
-- Canonicalising the equality pins the CONTENT of the span and, for a quote whose first and last
-- characters are ordinary, its OFFSETS too: each of those characters has exactly one raw index.
-- A break at either END breaks that, because `\r\n` is two raw characters and one canonical one,
-- so the span may start after the `\r` or before it and end before the `\n` or after it.
-- MEASURED on litkb_test_w3, block text `abc\r\ndef`, through this function:
--     quote `abc\n`   verifies at raw [0,4) AND at raw [0,5)     <- two ranges, one quote
--     quote `\ndef`   verifies at raw [3,8) AND at raw [4,8)
--     quote `bc\nde`  verifies at raw [1,7) ONLY ([1,6) and [2,7) are false)
-- The offsets are what `_verified_span_findings` and every later reader trust to say WHICH words
-- somebody checked, and a caller may supply them directly (`litkb_record_use(char_start=…,
-- char_end=…)`), so an ambiguous pair is a real hole and not a curiosity. The rule is therefore:
-- a quote whose CANONICAL form begins or ends with `\n` is not verifiable — refused by
-- `use.locate_in_text` before anything is written, and marked NOT verified here for the caller
-- that named its own offsets. It costs nothing a quoter wants: a quote that opens or closes on a
-- line break carries no word at that end.
--
-- ── A BARE `\r` IS A BREAK TOKEN, AND THAT IS ACCEPTED ────────────────────────────────────
-- MEASURED by auditor-5 on the 2026-09-19 corpus: 1,417 real blocks hold a bare `\r`, and 164 of
-- those have it BETWEEN WORD CHARACTERS — `Intel\rR CoreTM` is the shape, a superscript that the
-- extraction flattened to a control byte rather than a line break. Under this rule `\r` is a line
-- ending wherever it occurs, so a quote written `Intel\nR` verifies against `Intel\rR`. That is
-- STATED, not overlooked: the alternative is a second rule about which `\r` is a break, which
-- would need to know what the PDF meant, and the 0025 ligature work is the standing evidence that
-- per-byte intent cannot be recovered after extraction. Content is still pinned character for
-- character; what a reader loses is the distinction between two spellings of one control byte.

CREATE OR REPLACE FUNCTION litkb.canonical_newlines(t text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  -- BEGIN guard: one line ending is one "\n", and nothing else is normalised (SQL)
  SELECT replace(replace(t, chr(13) || chr(10), chr(10)), chr(13), chr(10))
  -- END guard: one line ending is one "\n", and nothing else is normalised (SQL)
$$;

-- 0001:25 is `ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC`, so a new function
-- is executable by NOBODY but its owner until it is granted — and this one is called from queries
-- the agent roles run: `review_check._BLOCK_SQL` as litkb_reader, `use.locate_quote` as
-- litkb_writer. MEASURED on litkb_test_w3 before this block existed: has_function_privilege was
-- false for reader, writer AND ingest, and no test could see it because the suite logs in as
-- litkb_test, which OWNS the function it just migrated. Same three roles as 0018/0025 grant
-- litkb.norm_search_text, for the same reason. (The verify trigger does not need this: it runs
-- inside litkb.add_evidence, which is SECURITY DEFINER.)
-- BEGIN guard: the agent roles may execute the newline rule
GRANT EXECUTE ON FUNCTION litkb.canonical_newlines(text) TO litkb_reader, litkb_writer, litkb_ingest;
-- END guard: the agent roles may execute the newline rule

COMMENT ON FUNCTION litkb.canonical_newlines(text) IS
  'One line ENDING -> one chr(10). The SQL half of litkb.textnorm.canonical_newlines; bound to it '
  'by qc/test_litkb_review_check.py::test_the_sql_and_python_newline_canonicalisations_agree. Not '
  'a collapse of consecutive endings.';

-- §4.5, as amended above: quote_verified is whether the block's text at [char_start, char_end)
-- equals the quote once both have canonical line endings. Overwritten unconditionally, so a
-- client-supplied value cannot survive. D-7 (0007): an offset range that runs past the text is
-- refused outright — substring would truncate it and let a whole-text quote verify.
CREATE OR REPLACE FUNCTION litkb._use_evidence_verify() RETURNS trigger
LANGUAGE plpgsql SET search_path = litkb, public, pg_temp AS $$
DECLARE
  b record;
  v_q text;
BEGIN
  SELECT bl.text, bl.run_id INTO b FROM blocks bl WHERE bl.id = NEW.block_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'litkb: evidence block % does not exist', NEW.block_id USING ERRCODE = '23503';
  END IF;
  IF NEW.run_id IS DISTINCT FROM b.run_id THEN
    RAISE EXCEPTION 'litkb: evidence run % is not the run of block %', NEW.run_id, NEW.block_id USING ERRCODE = '23514';
  END IF;
  -- BEGIN guard: char_end within the block text (0026 copy; 0007's is dead text)
  IF NEW.char_end > length(b.text) THEN
    RAISE EXCEPTION 'litkb: evidence char_end % is beyond the % characters of block %',
      NEW.char_end, length(b.text), NEW.block_id USING ERRCODE = '23514';
  END IF;
  -- END guard: char_end within the block text (0026 copy; 0007's is dead text)
  v_q := litkb.canonical_newlines(NEW.quote);
  -- BEGIN guard: the quote is the block's own span, up to the encoding of its line endings
  NEW.quote_verified := coalesce(
    litkb.canonical_newlines(substring(b.text FROM NEW.char_start + 1 FOR NEW.char_end - NEW.char_start))
      = v_q
  -- END guard: the quote is the block's own span, up to the encoding of its line endings
  -- BEGIN guard: the quote does not begin or end with a line break, so its offsets are unique
  -- The header says why: `\r\n` is two raw characters and one canonical one, so a break at either
  -- END of the quote leaves TWO raw ranges satisfying the equality above and nothing decides
  -- which words were checked. An interior break is unique and is the ordinary case.
    AND left(v_q, 1) <> chr(10) AND right(v_q, 1) <> chr(10)
  -- END guard: the quote does not begin or end with a line break, so its offsets are unique
    , false);
  RETURN NEW;
END
$$;

-- end of 0026
