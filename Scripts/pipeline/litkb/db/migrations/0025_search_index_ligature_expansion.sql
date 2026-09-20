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
--   * ADDITIVE FOR THE LEXICAL LEGS, BY CONSTRUCTION AND BY COUNT. 0018's output is carried
--     through unchanged and the spellings are PREPENDED, so the pre-0025 string is a literal
--     SUFFIX of the new one, starting immediately after a space. Nothing is inserted into it and
--     nothing is deleted from it, so no token of it can be disturbed. Measured on all
--     372,192 blocks of the 2026-09-19 dump — full scan, every row counted, no LIMIT and no
--     sampling: 0 blocks lose a lexeme the pre-0025 function produced, 0
--     lexemes. Instrument: qc/instruments/litkb_norm_additivity.py.
--
--     WHY NOT BESIDE THE WORD, which is the obvious design and was the first two versions of this
--     migration. Both were measured on the same 372,192 blocks by the same instrument:
--
--        rule                                                     blocks losing a lexeme / lexemes
--        d6a0a29: spellings written in, match ends at the last letter        570 / 809
--        same, match extended to the end of the whitespace-delimited run      78 / 268
--        THIS FILE: spellings prepended, the text never written into           0 /   0
--
--     The 570 is the 2026-09-20 audit's: the inserted space cut `u<0x05>L1(BR(0))` in half, the
--     lexeme `l1` vanished, `uffll1` was manufactured, and `L1` fell from 297 to 280 visible leg-1
--     hits. The 78 is what survives when the match is carried to the end of the whitespace run so
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
--     The inline design also cost RECALL, because `g` matching does not overlap and a second
--     damaged word inside the same whitespace run was swallowed by the first match's tail:
--     `misclassification` recovered 117 -> 157 visible leg-1 hits under it, and 117 -> 187 here.
--     The instrument's --mutate mode re-installs BOTH rejected rules and counts them again, so
--     the three numbers above are a gate that has been SHOWN to fire, not an assertion.
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
    SELECT string_agg(x, ' ') AS extra FROM (
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
  '0018''s output follows them unchanged. The old string is a literal suffix of the new one, so no '
  'lexeme the pre-0025 function produced can be lost: measured on all 372,192 blocks of the '
  '2026-09-19 dump, 0 blocks lose one (qc/instruments/litkb_norm_additivity.py). Writing the '
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
-- REINDEXed, and that is a measured choice rather than a style one (2026-09-20, litkb_test_w2, the
-- 2026-09-19 dump):
--
--   CREATE OR REPLACE + REINDEX, run the way migrate.apply() runs it — the whole file in ONE
--   psycopg execute inside one transaction — left the fts index holding PRE-0025 entries. The
--   function answered `misclassification` on 906 blocks; the same query served from that index
--   answered 722. Same database, same instant. Through psql (`-1`, the same single transaction)
--   the identical file REINDEXed correctly, so the trigger is the execution path and not the SQL.
--   A defect that appears on one client and not another is not one to rely on either way.
--
--   DROP + CREATE measured 906 on both paths. A new index has no prior expression state to
--   inherit. A stale search index is the worst thing this migration could ship — every leg reads
--   through it, the repair would look like it had not worked, and NOTHING in the proof would have
--   caught it: those probes fetch one block by primary key, which never touches this index.
--   qc/instruments/litkb_norm_index_proof.py now compares the index-served count against the same
--   query forced to a sequential scan and fails if they differ.
--
-- Not CONCURRENTLY: a migration runs inside one transaction, and a half-applied search layer is
-- worse than a lock. The two definitions are 0018:166-169 verbatim.
DROP INDEX litkb.blocks_norm_text_fts;
CREATE INDEX blocks_norm_text_fts ON litkb.blocks
  USING gin (to_tsvector('english', litkb.norm_search_text(text)));
DROP INDEX litkb.blocks_norm_text_trgm;
CREATE INDEX blocks_norm_text_trgm ON litkb.blocks
  USING gin (litkb.norm_search_text(text) gin_trgm_ops);
