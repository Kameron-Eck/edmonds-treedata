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
-- possibilities beside the text as it stands:
--
--   for every  <letters><C0><letters>            (at least one letter on each side), and
--   for every  <word boundary><C0><letters,2+>   (a word-initial ligature, e.g. `<0x1d>oating`),
--   emit: the matched text UNCHANGED, then the byte-dropped form, then the five expansions
--         ff / fi / fl / ffi / ffl of that one word.
--
-- Three properties, each of them the reason for a piece of the rule:
--   * CORRECT UNDER THE AMBIGUITY. The true word is always among the five, so no choice between them
--     has to be made and no file-dependent table has to be right. `e<0x01>ects` and `in<0x01>nitely`
--     both match under one rule.
--   * ADDITIVE FOR THE LEXICAL LEGS. The matched text is re-emitted unchanged, so every lexeme the
--     old function produced is still produced: the old tsvector is a subset of the new one (measured
--     on the first 3,000 blocks by scan order: 0 lose a lexeme). So no match on leg 1 (all-terms) or
--     leg 2 (any-term) can be lost. NOT CLAIMED FOR LEG 3: the trigram leg scores similarity() over
--     the whole normalised string, so on an affected block the added text shifts that score
--     slightly, and a marginal `%` match could move either way. That was not measured.
--   * NO BYTE IS NAMED. The rule keys on the SHAPE (a control byte inside a word), never on which
--     byte it is, because the measurement above says the byte identifies nothing.
--
-- The two-letter floor on the word-initial case is measured, not chosen. Over the 2,960
-- expansion-shape occurrences in current-run blocks:
--   * a byte with ONE letter beside it (1,418 occurrences) recovers a real corpus word in 0 cases,
--     while 1,244 of them would put a real short word into the index — `<0x05>x` (a minus sign, not
--     a ligature) would index as `fix`. Pure noise injection; excluded.
--   * a byte with TWO OR MORE letters beside it (1,542 occurrences) recovers a corpus-attested word
--     in 343 cases, and NONE of the remainder spells any corpus word at all. Included.
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
-- vocabulary: 181 keys collide, covering 386 distinct words (`eect` <- {eect, effect, eflect};
-- `specied` <- {specied, speciffed, specified}), and 93 words collapse to two characters or fewer.
-- It also rewrites the query side, so it is not additive. Expansion costs +0.4% index text on a
-- 3,000-block sample and collides with nothing.
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
  SELECT regexp_replace(
           regexp_replace(
             regexp_replace(
               regexp_replace(
                 -- 0018, unchanged: U+FFFD (a ligature the text layer could not render at all) and
                 -- U+00AD (a soft hyphen) carry no information. chr(), not a literal: U+00AD is an
                 -- INVISIBLE character and this file stays greppable.
                 translate(coalesce(p_text, ''), chr(65533) || chr(173), ''),
                 -- 0018, unchanged: a hyphen followed by whitespace is a LINE-BREAK hyphenation,
                 -- `overesti- mate` -> `overestimate`. A hyphen inside a word is left alone.
                 '-[ \t\r\n]+', '', 'g'),
               -- 0025, case A: a C0 byte with letters on BOTH sides. `\&` re-emits the match with
               -- its byte, which is what makes this additive; then the dropped form, then the five
               -- ligatures. Never a choice between them — see the header's same-file conflict.
               '([A-Za-z]+)[' || k.c0 || ']([A-Za-z]+)',
               '\& \1\2 \1ff\2 \1fi\2 \1fl\2 \1ffi\2 \1ffl\2', 'g'),
             -- 0025, case B: a WORD-INITIAL C0 byte (`<0x1d>oating`), which case A cannot see. The
             -- boundary character is part of the match and is re-emitted by `\&`, so case A's own
             -- output (whose bytes still have letters in front of them) can never be re-expanded
             -- here. Two letters minimum: the one-letter case is measured noise.
             '(^|[^A-Za-z])[' || k.c0 || ']([A-Za-z]{2,})',
             '\& \2 ff\2 fi\2 fl\2 ffi\2 ffl\2', 'g'),
           '[ \t\r\n]+', ' ', 'g')
    -- The C0 class, once: 0x01-0x08, 0x0b, 0x0c, 0x0e-0x1f — every control byte EXCEPT tab, LF and
    -- CR, which are real whitespace in a PDF text layer and are handled by the collapse above.
    -- Built with chr() so no control byte is ever typed into this file.
    FROM (SELECT chr(1) || '-' || chr(8) || chr(11) || chr(12) || chr(14) || '-' || chr(31) AS c0) k
$$;
-- END guard: search normalises the extractor's damage on both sides
COMMENT ON FUNCTION litkb.norm_search_text(text) IS
  'Retrieval-side repair of the PDF text layer. 0018: drop U+FFFD/U+00AD, join line-break '
  'hyphenation, collapse whitespace. 0025: a C0 control byte inside a word is an extracted ligature '
  'of unknown identity (the same byte is ff and fi in one file), so the word is indexed as it '
  'stands PLUS its byte-dropped form PLUS all five ff/fi/fl/ffi/ffl expansions — additive for the '
  'tsvector legs, so no lexical match can be lost (the trigram leg scores the whole string, and its '
  'similarity on an affected block shifts with the added text: not measured). Applied to the block '
  'text and to the query in the '
  'same statement so the two cannot drift. THE STORED BYTES ARE NEVER REWRITTEN (decisions.yaml '
  'litkb-ligature-repair, option c): a recorded quote still verifies against what the PDF said.';

-- 0018 granted these three; CREATE OR REPLACE keeps them. Re-stated so a database built from
-- scratch and one upgraded through 0025 cannot differ, which is the failure 0021 was written for.
GRANT EXECUTE ON FUNCTION litkb.norm_search_text(text) TO litkb_reader, litkb_writer, litkb_ingest;

-- The two expression indexes of 0018, rebuilt against the new function. Not CONCURRENTLY: a
-- migration runs inside one transaction, and a half-applied search layer is worse than a lock.
REINDEX INDEX litkb.blocks_norm_text_fts;
REINDEX INDEX litkb.blocks_norm_text_trgm;
