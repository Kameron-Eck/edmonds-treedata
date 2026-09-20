-- litkb 0025 — decisions.yaml `litkb-ligature-repair`, option (c): the ligature defect is repaired
-- in the SEARCH INDEX ONLY. litkb.norm_search_text() is replaced; NO stored block text is rewritten
-- by this migration, and nothing here writes to litkb.blocks at all. That is the whole point of (c):
-- no byte a recorded quote points at moves, so the 54/54-spanning and 48/48-after quote_verified
-- breakage measured for an in-place UPDATE (work/20260919-ligature da91101, refereed 2734331)
-- cannot occur.
--
-- ── THE DEFECT ───────────────────────────────────────────────────────────────────────────
-- A PDF subset font numbers its own glyphs from 1 in the font's Differences array. A ligature glyph
-- (ff/fi/fl/ffi/ffl) with no ToUnicode entry extracts as that raw glyph code — a C0 control byte —
-- instead of letters. `floating point` is stored as `<0x1d>oating point` and indexes as `oating`, so
-- the query `floating point` cannot reach it.
--
-- ── WHY THERE IS NO BYTE TABLE HERE ──────────────────────────────────────────────────────
-- Font subsets are built per embedded font, so the same byte names a different glyph in a different
-- subset OF THE SAME FILE. Measured, not assumed — file 01a0a4d6-6db4-7343-965a-aca7b3c090d4,
-- byte 0x01, two current-run blocks:
--     01a0abc7-429d-7a0d-b7fb-252dab0c32ec  'Modelling covariate e<0x01>ects'   -> ff (effects)
--     01a0abc7-42ad-7050-b607-63aacd8a50c8  'in<0x01>nitely long'               -> fi (infinitely)
-- Each expansion is confirmed against the corpus's own vocabulary (38,595 distinct clean 4–25-letter
-- words from C0-free current-run blocks): `effects` and `infinitely` are attested, `efiects` and
-- `inffnitely` are not. A fixed byte->ligature table is therefore WRONG BY CONSTRUCTION: the
-- measured 0x01 majority (fi) recovers `infinitely` and silently fails `effects` in the same file.
--
-- ── THE RULE ─────────────────────────────────────────────────────────────────────────────
-- Treat a C0 control byte that sits in a word as a ligature of UNKNOWN identity, and index all five
-- possibilities ALONGSIDE the text as it stands — which the text itself never learns about:
--
--   for every  <letters><C0><letters>            (at least one letter on each side), and
--   for every  <word boundary><C0><letters,2+>   (a word-initial ligature, e.g. `<0x1d>oating`),
--   collect the byte-dropped form and the five spellings ff / fi / fl / ffi / ffl of that one word,
--   and PREPEND all of them, as their own whitespace-separated run, to 0018's output — which is
--   carried through byte for byte.
--
-- NOTHING IS SUBSTITUTED INTO THE TEXT. That is the whole design, and it is the thing the first two
-- versions of this migration got wrong by writing the spellings in beside the word they repair.
-- See the second property below for what that cost, measured.
--
-- Three properties, each of them the reason for a piece of the rule:
--   * CORRECT UNDER THE AMBIGUITY. The true word is always among the five, so no choice between them
--     has to be made and no file-dependent table has to be right. `e<0x01>ects` and `in<0x01>nitely`
--     both match under one rule.
--   * ADDITIVE FOR THE LEXICAL LEGS, BY THE BYTE-SUFFIX PROPERTY AND BY COUNT. Two measurements,
--     both on all 372,192 blocks of the 2026-09-19 dump — full scan, every row counted, no LIMIT
--     and no sampling:
--        BYTE SUFFIX  `right(new, length(old)) = old` on 372,192 / 372,192 blocks. 0018's output is
--                     carried through unchanged and the spellings are PREPENDED, so the pre-0025
--                     string really is a literal SUFFIX of the new one, as bytes and not only as a
--                     lexeme set. (2026-09-20 audit, §1.)
--        COUNT        0 blocks lose a lexeme the pre-0025 function produced, 0 lexemes.
--                     Instrument: qc/instruments/litkb_norm_additivity.py.
--
--     THIS IS NOT A "BY CONSTRUCTION" CLAIM, and this file said it was until 2026-09-20. The
--     argument would be "nothing is inserted into the old string and nothing is deleted from it, so
--     no token of it can be disturbed" — and it does not follow, for the reason the rejected rules
--     below are rejected for: this parser's tokens can absorb the whitespace in FRONT of them, so
--     `base`'s own first token is not protected by an argument. What protects it is the count, on
--     THIS dump. A future ingest is covered by re-running the instrument, not by the reasoning.
--
--     WHY NOT BESIDE THE WORD, which is the obvious design and was the first two versions of this
--     migration. Both were measured on the same 372,192 blocks by the same instrument:
--
--        rule                                                     blocks losing a lexeme / lexemes
--        d6a0a29: spellings written in, match ends at the last letter        570 / 809
--        same, match extended to the end of the whitespace-delimited run      78 / 268
--        THIS FILE: spellings prepended, the text never written into           0 /   0
--
--     The 570 is the 2026-09-20 audit's, reproduced here exactly: the inserted space cut
--     `u<0x05>L1(BR(0))` in half, the lexeme `l1` vanished and `uffll1` was manufactured, and the
--     recall table below puts the audit's `L1` 297 -> 280 alongside it. The 78 is what survives
--     when the match is carried to the end of the whitespace run so
--     the inserted space can only land where a space already was — and it is NOT zero, which is
--     the measurement that killed that design:
--
--       IN THIS DATABASE A LEXEME CAN CONTAIN A SPACE. `english`, libc collation
--       `English_United States.1252` over a UTF-8 corpus: blocks of mixed-script equation
--       mojibake tokenise into lexemes like `'1 ψ a'`, `'∑ n i'`, `' # +'`. Whitespace is
--       therefore NOT an unconditional separator here, and no insertion point inside such a
--       block is safe — inserting the harmless string ` zzz` at the same offset loses the same
--       two lexemes the expansion did. Which characters the parser keeps in one token is
--       context-dependent and cannot be written as a character class at all: measured with
--       ts_debug, `L1` is one token (numword), `ects-based` one (asciihword), `v2.0` one (file),
--       `x.com/a` four (protocol/url/host/url_path), `a_b` two, and a C0 byte is itself `blank`.
--       Prepending sidesteps the whole question: the old string is untouched and unsplit.
--
--     RECALL under each of the three rules, all counted from the FUNCTION with index scans
--     disabled — never read through an expression index, for the reason the index section below
--     gives. Visible leg-1 hits (DEFAULT_KINDS + the main_files/main_works joins):
--
--        rule                                         `misclassification`        `L1`
--        pre-0025 (0018)                                        117               297
--        d6a0a29: spellings written in                          187               280
--        same, match to the end of the run                      187               297
--        THIS FILE                                              187               297
--
--     READ THE SECOND COLUMN. All three rules recover `misclassification` equally — the repair is
--     not what separates them. What separates them is that d6a0a29 DESTROYS 17 `L1` hits it was
--     never asked to touch, which is the audit's 297 -> 280, reproduced here from the function.
--     The run-extended rule costs nothing on either query and still loses 78 blocks / 268 lexemes
--     elsewhere, which is why it is rejected too: a loss that does not show up in the query you
--     happened to measure is still a loss. Every number in both tables is counted with index scans
--     DISABLED, from the function itself — see the index section below for what a number read
--     through an expression index was worth on 2026-09-20. The instrument's --mutate mode
--     re-installs BOTH rejected rules and counts all of this again, so every row is a gate that
--     has been SHOWN to fire.
--     NOT CLAIMED FOR LEG 3: the trigram leg scores similarity() over the whole normalised
--     string, so on an affected block the added text shifts that score slightly, and a marginal
--     `%` match could move either way. That was not measured.
--   * NO BYTE IS NAMED. The rule keys on the SHAPE (a control byte inside a word), never on which
--     byte it is, because the measurement above says the byte identifies nothing.
--
-- The two-letter floor on the word-initial case is measured, not chosen. Script:
-- qc/instruments/litkb_norm_floor.py, output Reports/litkb_norm_floor_2026-09-20.csv — the numbers
-- below are read from it, not typed here (they were prose until 2026-09-20, which is the thing
-- CLAUDE.md 3.4b forbids). Over the 2,960 expansion-shape occurrences in current-run
-- blocks, classified by how many letters follow the byte and then asked ONE question — does the
-- expansion spell a word the corpus itself attests?
--   * ONE letter (1,418 occurrences): 0 spell a real word of 4+ letters, and
--     1,244 spell a real word of ANY length — `<0x05>x` (a minus sign, not a ligature)
--     would index as `fix`. At one letter the only words reachable are short ones, and none of them
--     is the word that was damaged. Pure noise injection; excluded.
--   * TWO OR MORE letters (1,542 occurrences): 343 spell a real word of 4+
--     letters. READ THIS HONESTLY: the two buckets are the SAME event counted against the same
--     vocabulary, split by letter count — so the ≥2 bucket cannot show "injection" at all (its
--     any-length count is 343, identical to its 4+ count by construction, because at
--     two letters plus a two-letter ligature every hit is already 4+). What the split establishes is
--     the ONE-letter bucket's asymmetry: 0 recoveries against 1,244 short-word hits. That
--     asymmetry is the floor's justification; the ≥2 row is context, not a second measurement.
--
-- ── WHAT WAS MEASURED AND LEFT ALONE ─────────────────────────────────────────────────────
-- * DE-HYPHENATION IS ALREADY DONE by 0018's `-[ \t\r\n]+` join and is carried through here
--   unchanged. Measured on the 2026-09-19 dump in litkb_test_w2: 211 current-run blocks carry a
--   lowercase word split across a line break, and the 0018 function already joins them
--   (`abund- ant` -> `abundant`, block 01a0abc8-4a18-7ca5-88e5-6dac9bf744f0). The Hampel
--   "Robust Statis- tics" string named in the decision does NOT exist in that corpus (0 blocks
--   match `Statis-`); its reference block reads `Robust Statistics` already. So the decision's
--   "folded into the same pass" is satisfied by what 0018 does, and nothing was rebuilt for it.
-- * 0x05 (the decision's open question) is NOT a ligature here. It has 2,162 current-run
--   occurrences, of which 424 fall in the expansion shape and 0 resolve to a corpus-attested
--   ligature word; its contexts are a minus sign in Elsevier-style mojibake (`ð1 <0x05> lOtÞ`) and
--   an accented letter (`Qu<0x05>ebec`). It is the same MECHANISM (an unmapped subset glyph) and a
--   different glyph class. It is neither singled out nor excluded: the shape rule covers it, its
--   junk expansions spell nothing, and its byte-dropped form is what makes `Quebec` findable. A
--   byte list that excluded it would be the byte table this migration exists to avoid.
-- * U+FFFD keeps 0018's plain drop. In this corpus it is not ligature-shaped: 17 current-run
--   occurrences, none of them followed by a letter, so expansion would add nothing.
--
-- ── THE ALTERNATIVE THAT WAS REJECTED, WITH ITS NUMBER ────────────────────────────────────
-- "Match by tolerating the missing ligature" — delete ffi|ffl|ff|fi|fl from BOTH sides, so the query
-- `floating` and the stored `<0x1d>oating` meet at `oating`. Measured on the same 38,595-word
-- vocabulary by qc/instruments/litkb_norm_floor.py: 101 keys collide, covering
-- 210 distinct words (`eect` <- {eect, effect, eflect}; `specied` <- {specied, speciffed,
-- specified}), and 80 words collapse to two characters or fewer.
-- THESE NUMBERS REPLACE THE 181 / 386 / 93 THIS PARAGRAPH USED TO CARRY. Those were prose with no
-- script behind them and they do not reproduce: under the definition now in the instrument (the
-- 4-25-letter vocabulary, `regexp_replace(w,'ffi|ffl|ff|fi|fl','','g')`, keys shared by two or more
-- distinct words) the corpus gives the figures above, and a single-pass delete gives 100/205/73.
-- The definition the old numbers came from is not recorded anywhere, so it cannot be checked. The
-- conclusion is unchanged and now derivable: the alternative collides and this one does not.
-- It also rewrites the query side, so it is not additive. The spellings cost +0.42% index text
-- over the WHOLE corpus (67,473,804 -> 67,758,222 characters, full scan of every block).
--
-- ── THIS FILE WAS EDITED IN PLACE AFTER ITS FIRST COMMIT ─────────────────────────────────
-- 0025 has NEVER been applied to live litkb and has therefore never been checksum-locked by
-- litkb_meta.schema_migrations (migrate.apply() re-checks the recorded sha256 of every APPLIED
-- migration; an unapplied file has no recorded hash). It has only ever run on worker databases,
-- which are reset and re-migrated from scratch. So the 2026-09-20 additivity fix is an edit to this
-- file rather than an 0026 on top of it — deliberately, and said out loud here because editing an
-- applied migration is the thing the gate refuses.
--
-- ── THE INDEXES MUST BE REBUILT IN THIS MIGRATION ────────────────────────────────────────
-- 0018's two expression indexes store the OLD function's output. CREATE OR REPLACE does not touch
-- them, and Postgres has no way to know they are stale — a search would keep reading pre-0025
-- entries and the repair would appear not to work. Both are rebuilt below, in the same transaction
-- as the replacement, so no committed state ever has the new function with an old index.

SET LOCAL search_path = litkb, public;

-- BEGIN guard: search normalises the extractor's damage on both sides
CREATE OR REPLACE FUNCTION litkb.norm_search_text(p_text text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
  -- The C0 class, once: 0x01-0x08, 0x0b, 0x0c, 0x0e-0x1f — every control byte EXCEPT tab, LF and
  -- CR, which are real whitespace in a PDF text layer and are handled by the collapse below.
  -- Built with chr() so no control byte is ever typed into this file.
  WITH k AS (SELECT chr(1) || '-' || chr(8) || chr(11) || chr(12) || chr(14) || '-' || chr(31) AS c0),
  -- 0018's normalisation, carried through UNCHANGED. Everything 0025 adds is added AROUND this
  -- value; not one character of it is rewritten, which is what makes the rule additive.
  base AS (
    SELECT regexp_replace(
             regexp_replace(
                 -- 0018, unchanged: U+FFFD (a ligature the text layer could not render at all) and
                 -- U+00AD (a soft hyphen) carry no information. chr(), not a literal: U+00AD is an
                 -- INVISIBLE character and this file stays greppable.
                 translate(coalesce(p_text, ''), chr(65533) || chr(173), ''),
                 -- 0018, unchanged: a hyphen followed by whitespace is a LINE-BREAK hyphenation,
                 -- `overesti- mate` -> `overestimate`. A hyphen inside a word is left alone.
                 '-[ \t\r\n]+', '', 'g'),
             '[ \t\r\n]+', ' ', 'g') AS t),
  -- 0025: every alternative spelling this text could have, collected — NOT substituted into it.
  -- regexp_matches(...,'g') reads the damage; nothing writes back into `base.t`.
  spellings AS (
    -- ORDER BY is not cosmetic. This function also backs a TRIGRAM index, and a trigram set depends
    -- on the boundaries BETWEEN these tokens: reorder them and the index entry changes. An
    -- unordered string_agg leaves the output formally order-unspecified, which an IMMUTABLE
    -- function backing an index may not be.
    SELECT string_agg(x, ' ' ORDER BY x) AS extra FROM (
      -- case A: a C0 byte with letters on BOTH sides. The byte-dropped form, then the five
      -- ligatures. Never a choice between them — see the header's same-file conflict.
      SELECT m[1] || m[2] || ' ' || m[1] || 'ff' || m[2] || ' ' || m[1] || 'fi' || m[2] || ' '
             || m[1] || 'fl' || m[2] || ' ' || m[1] || 'ffi' || m[2] || ' ' || m[1] || 'ffl' || m[2]
             AS x
        FROM base, k,
             LATERAL regexp_matches(base.t, '([A-Za-z]+)[' || k.c0 || ']([A-Za-z]+)', 'g') m
      UNION ALL
      -- case B: a WORD-INITIAL C0 byte (`<0x1d>oating`), which case A cannot see — it requires a
      -- letter in front. Two letters minimum: the one-letter case is measured noise (the floor).
      SELECT m[2] || ' ff' || m[2] || ' fi' || m[2] || ' fl' || m[2] || ' ffi' || m[2]
             || ' ffl' || m[2]
        FROM base, k,
             LATERAL regexp_matches(base.t, '(^|[^A-Za-z])[' || k.c0 || ']([A-Za-z]{2,})', 'g') m
    ) q)
  -- THE ADDITIVITY CLAUSE. The spellings go in FRONT, as their own whitespace-separated run, and
  -- 0018's output follows them byte for byte. The pre-0025 string is a literal SUFFIX of this one,
  -- so no token of it can be disturbed by what was added. `coalesce`: string_agg over zero matches
  -- is NULL, and a text with no damage must come out of here EXACTLY as it went in — the query side
  -- runs through this same function.
  SELECT coalesce(s.extra || ' ', '') || base.t FROM base, spellings s
$$;
-- END guard: search normalises the extractor's damage on both sides
COMMENT ON FUNCTION litkb.norm_search_text(text) IS
  'Retrieval-side repair of the PDF text layer. 0018: drop U+FFFD/U+00AD, join line-break '
  'hyphenation, collapse whitespace. 0025: a C0 control byte inside a word is an extracted ligature '
  'of unknown identity (the same byte is ff and fi in one file), so the byte-dropped form and all '
  'five ff/fi/fl/ffi/ffl spellings of that word are PREPENDED to the text as their own run, and '
  '0018''s output follows them unchanged. ADDITIVE BY MEASUREMENT, NOT BY CONSTRUCTION: on all '
  '372,192 blocks of the 2026-09-19 dump the old string is a literal byte suffix of the new one '
  '(372,192/372,192) and 0 blocks lose a lexeme the pre-0025 function produced '
  '(qc/instruments/litkb_norm_additivity.py). The reasoning alone does not carry it — this '
  'parser''s tokens can absorb the whitespace in front of them — so a future corpus is covered by '
  're-running that instrument. Writing the '
  'spellings BESIDE the damaged word instead loses them — 570 blocks the first way, 78 the second; '
  'the instrument re-runs both. Not claimed for the trigram leg, which scores the whole string and '
  'whose similarity on an affected block shifts with the added text: not measured. Applied to the '
  'block '
  'text and to the query in the '
  'same statement so the two cannot drift. THE STORED BYTES ARE NEVER REWRITTEN (decisions.yaml '
  'litkb-ligature-repair, option c): a recorded quote still verifies against what the PDF said.';

-- 0018 granted these three; CREATE OR REPLACE keeps them. Re-stated so a database built from
-- scratch and one upgraded through 0025 cannot differ, which is the failure 0021 was written for.
GRANT EXECUTE ON FUNCTION litkb.norm_search_text(text) TO litkb_reader, litkb_writer, litkb_ingest;

-- The two expression indexes of 0018, rebuilt against the new function. DROPPED AND RECREATED, not
-- REINDEXed. THAT IS INSURANCE, NOT A DEMONSTRATED FIX, and this comment claimed more than that
-- until 2026-09-20 (litkb_test_w2 and litkb_test_w5, the 2026-09-19 dump):
--
--   WHAT WAS SEEN ONCE. CREATE OR REPLACE + REINDEX, run the way migrate.apply() runs it — the
--   whole file in ONE psycopg execute inside one transaction — left the fts index answering
--   `misclassification` on 722 blocks on the builder's database. The function answered 906. The
--   PRE-0025 function answered 612. The index agreed with NEITHER.
--
--   WHAT WAS THEN TRIED AND FAILED TO REPRODUCE IT. The 2026-09-20 audit ran migrate.apply() on
--   THREE fresh restores — the committed rule with REINDEX, d6a0a29's exact file with REINDEX, and
--   this file as it stands — and every one gave index == seqscan on all five probes, with equal id
--   sets and not merely equal counts. It also installed nine candidate function bodies and counted
--   `misclassification` under each: every one answers 612 or 906, NONE answers 722, and the two
--   sets nest (612 ⊂ 906, 294 new), so 722 = 612 + 110 has the arithmetic shape of a PARTIALLY
--   POPULATED index rather than an index built from some other definition. The database that
--   showed it was not preserved. Stated plainly: an unexplained one-off that nobody has reproduced.
--
--   SO WHY KEEP DROP + CREATE. Because a new index has no prior expression state to inherit, and a
--   stale search index is the worst thing this migration could ship — every leg reads through it,
--   the repair would look like it had not worked, and NOTHING in the proof would have caught it:
--   those probes fetch one block by primary key, which never touches this index. It is a cheap
--   hedge against a failure mode nobody can currently trigger on demand, kept on those terms.
--
--   IT IS NOT BOUGHT WITH TIME, and this comment used to say it was. Measured with the FUNCTION
--   held fixed and only the DDL varied: REINDEX 87.5 s (n=1) against DROP+CREATE 84.7-91.6 s —
--   no difference. The jump the builder attributed to DROP+CREATE (34.6 s -> 82.5 s) is the NEW
--   CTE-shaped norm_search_text being more expensive to evaluate: d6a0a29's rule with REINDEX is
--   55.6 s, the committed rule with REINDEX is 87.5 s, same DDL both times. There is no 45 s to
--   save by going back to REINDEX.
--
--   IT IS NOT BOUGHT WITH LOCKS EITHER, in the only sense that matters to a reader. The lock MODES
--   differ (REINDEX takes ShareLock on litkb.blocks; DROP+CREATE takes AccessExclusiveLock), which
--   reads as if REINDEX let readers through. Measured, it does not: with either statement held open
--   in one transaction, a second session at statement_timeout=5s was CANCELLED on both a
--   primary-key fetch of one block and a leg-1 search, and both succeeded the moment that
--   transaction rolled back — the planner opens every index on the table when it plans any query
--   against it. PLAN THE LIVE CUTOVER AS A ~90 s OUTAGE OF litkb.blocks under either form.
--
--   qc/instruments/litkb_norm_index_proof.py compares the index-served count against the same
--   query forced to a sequential scan and fails if they differ. It needs a dump restore, so it is
--   an operator step, not a ladder rung; the ladder's version of the same check is
--   qc/test_litkb_textnorm_index.py::test_the_expression_indexes_agree_with_the_function, and what
--   THAT one can and cannot see is written out in its own docstring.
--
-- Not CONCURRENTLY: a migration runs inside one transaction, and a half-applied search layer is
-- worse than a lock. The two definitions are 0018:166-169 verbatim.
DROP INDEX litkb.blocks_norm_text_fts;
CREATE INDEX blocks_norm_text_fts ON litkb.blocks
  USING gin (to_tsvector('english', litkb.norm_search_text(text)));
DROP INDEX litkb.blocks_norm_text_trgm;
CREATE INDEX blocks_norm_text_trgm ON litkb.blocks
  USING gin (litkb.norm_search_text(text) gin_trgm_ops);
