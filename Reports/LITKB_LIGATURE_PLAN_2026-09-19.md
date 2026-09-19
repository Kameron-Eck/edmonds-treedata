# Ligature C0 normaliser — Item 1: findings and the re-verification plan (2026-09-19)

Builder session, `work/20260919-ligature` @ `f30d28d`, worker DB `litkb_test_w11`. Scope: measure
only; nothing here has touched live `litkb`. Instruments: `qc/instruments/litkb_ligature_c0.py`
(part a), `qc/instruments/litkb_ligature_quote_hazard.py` (part b). Raw data:
`Reports/litkb_ligature_c0_2026-09-19.csv`, `Reports/litkb_ligature_quote_hazard_2026-09-19.csv`.

## (a) The byte does not name the ligature — no normaliser was built

Mechanism: PDF subset fonts number their own custom glyphs from 1 in the font's Differences
array; a ligature glyph (ff/fi/fl/ffi/ffl) with no ToUnicode entry extracts as that raw glyph
code — a C0 control byte — instead of letters. Font subsets are per embedded font (body vs.
heading vs. italic can each subset separately), so **the same byte can name a different glyph in
a different subset of the same file.**

Measured proof, not inference: file `01a0a4d6-6db4-7343-965a-aca7b3c090d4` emits `\x01` for "ff"
in "Modelling covariate e\x01ects" (a heading) and for "fi" in "observation sequence becomes
in\x01nitely long" (body text) — same file, same byte, two different ligatures.

`qc/instruments/litkb_ligature_c0.py` turned that from an existence proof into a bounded
measurement: for every current-run block with a `letters+C0+letters` span (479 blocks, 927
occurrences across 31 files — not the delta's relayed 16,315/106, which spans superseded runs),
try each of the five ligatures and check whether the resulting word is spelled out, in full,
somewhere in a C0-free current-run block anywhere in the corpus (38,595 distinct clean words,
built in ~4s — cheap enough to use the whole corpus rather than invent a wordlist).

Result: **681 unresolved, 127 ambiguous, 119 resolved.** Byte→ligature majority among resolved
occurrences: `0x01`→fi (91), `0x04`→ffi (12), `0x1f`→ff (9), `0x1e`→fi (3), `0x1c`→ffi (1),
`0x06`→fi (1) — and **one measured within-file conflict**: file `01a0a4d6-6db4-7343-965a-...`,
byte `0x01`, resolving to both `ff` and `fi`.

**Per CLAUDE.md 3.2 ("never invent") and 3.4c ("the proposer never scores its own proposal") and
the delta's own rule 10 ("a real design ambiguity: stop and report"), no fixed byte→ligature
table was built, and no normaliser landed at the write path this round.** A context-free table is
provably wrong for at least one byte in at least one file; shipping it would silently write a
wrong ligature into an unknown fraction of the corpus's remaining 681+127 unresolved/ambiguous
occurrences. This is a decision for Kam, not a default to reach for. Options, for the record:

1. **Fix extraction** (grobid/docling reading the PDF's own font Differences/ToUnicode tables)
   — the only approach that can be *correct* rather than *probable*, because it uses the
   information the byte itself discards. Cost: real engineering in `extract/grobid.py` /
   `extract/docling.py`; naturally produces a new extraction run (different tool output).
2. **Word-shape/dictionary heuristic at the write path** (what the instrument does) — cheap,
   applies to future ingests only, but resolves only ~13% of occurrences in this sample and must
   leave the rest (unresolved/ambiguous) untouched rather than guess.
3. **Do nothing yet, gate on option 1** — given (b) below, there is no live cost to waiting.

## (b) The hazard, measured on `litkb_test_w11` only

**Zero of the 8 real `use_evidence` rows in live `litkb` reference a current-run block that
carries a ligature C0 byte** (`SELECT count(*) FROM use_evidence ue JOIN blocks b ... WHERE
b.text ~ '[C0]'` → 0). Nothing live breaks today. That is a fact about today's tiny recorded-use
corpus, not about the mechanism — so the mechanism was measured directly instead.

Method (real block text, the real trigger, run only on `litkb_test_w11`):
- **Control group**: the 8 real `use_evidence` rows, copied verbatim (their blocks carry no C0
  byte).
- **Affected group**: 54 blocks sampled from `litkb_ligature_c0_2026-09-19.csv` — the measured
  conflict file guaranteed included, plus a capped spread across resolved/ambiguous/unresolved
  rows. No real uses exist against these blocks, so three use_evidence rows were **synthesised**
  per block (quote entirely BEFORE the block's first C0 byte / SPANNING it / entirely AFTER it) —
  labelled synthetic throughout; this is real corpus text with an invented recorded use, built
  only to exercise the mechanism.
- Rows were inserted through the real `use_evidence` table so `litkb._use_evidence_verify()`
  (migration 0007's trigger) computed `quote_verified` for real — that IS the baseline, not a
  copy of one. Affected blocks' text was then rewritten with a **stated placeholder** expansion
  (the (a) instrument's resolved byte majority where available, else a literal "fi" — explicitly
  not a validated general mapping). `UPDATE use_evidence SET stance = stance` re-fired the same
  real trigger, and its new `quote_verified` was read back.

Results (`Reports/litkb_ligature_quote_hazard_2026-09-19.csv`, 154 rows):

| group | rows | flips |
|---|---|---|
| control (real uses, untouched blocks) | 8 | **0** |
| affected — before first C0 | 44 | **0** |
| affected — spanning the C0 | 54 | **54 (100%)** |
| affected — after the C0 | 48 | **48 (100%)** |

Every flip is `true → false` (zero `false → true`, i.e. normalisation never manufactures a
false positive here). Of the 102 affected flips: 60 rows can no longer find their quote text
**anywhere** in the block (the byte's expansion, or the surrounding shift, ate the substring);
42 rows still contain the quote text but at a **shifted offset** — `char_end`/`char_start` are
stale, not just `quote_verified`. This exactly matches the SQL predicate (first C0 position
relative to `[char_start, char_end)`): a quote entirely before the edit is untouched; a quote
touching or downstream of it is not.

## (c) In-place UPDATE, or re-extraction? — **re-extraction, a new canonical run**

**Not an in-place `UPDATE litkb.blocks SET text = ...`.** Two independent reasons converge:

1. **(b) measured that it invalidates evidence.** Any recorded quote spanning or downstream of a
   normalised byte flips `quote_verified` from true to false — deterministically, 100% of the
   time in this sample. `extract/ingest.py`'s own design principle is "an ok run's rows cannot be
   deleted by anyone... that is the design, and it is what protects evidence that cites them" —
   an in-place text mutation on a promoted run is the same hazard as a delete: it changes the
   bytes evidence was verified against, silently, after the fact. This project has already been
   burned twice by exactly this shape of mistake (the `¼`/`�` and hyphenation-drift gold-quote
   refusals; the dy clamp silently changing block text on Higham) — a third instance, at 16,315
   blocks, is not a proportionate risk to take for a fix that (a) shows cannot even be done
   correctly with a fixed table.
2. **(a) means there is nothing safe to write in place yet.** Even setting the evidence hazard
   aside, no table exists that could losslessly reconstruct every occurrence; an in-place UPDATE
   would have to guess on the 681 unresolved and 127 ambiguous cases, which is exactly the
   "never invent" line.

**The correct fix is at extraction**, and by the project's own `CORPUS_PARAMS` precedent
(`extract/ingest.py`: a new `latex_source`/`merge_rule` value is a *different extraction*, not a
patch to the old one), resolving ligatures via the PDF's actual font encoding is a different
extraction of the same file — it belongs in a **new run** (new `params_hash`/`tool_version`,
however the eventual fix identifies itself), reached the normal way: `already_ingested` sees no
matching run, `ingest_file` writes fresh blocks, `set_current_run` moves the pointer only once
the new run is `ok`. The old run's rows are never touched; `clear_extraction_rows` already refuses
to delete an `ok` run, and this plan adds nothing that needs it to do more.

**What this means for the 8 existing (and any future) uses:** measured fact from (b) — none of
today's 8 real uses cite an affected block, so **nothing needs re-anchoring right now.** The
cheapest sequencing is to land the extraction fix *before* any use gets recorded against a
currently-corrupted block, which avoids the re-anchoring problem entirely for anything written
from today forward. For the case the project will eventually hit — a **promoted** use's evidence
citing a block whose run gets superseded — there is a real, currently unbuilt gap worth flagging
now rather than discovering under pressure: `add_evidence` (0007) requires the use version be
`proposed` (`IF v.st IS DISTINCT FROM 'proposed' THEN RAISE...`), so re-anchoring a promoted use's
evidence to a new run needs either a new use_version via `based_on` (a real edit, going through
`write_proposal`/promotion like any other content change) or a DB path that does not exist yet.
This plan does not build that path; it names it so the decision is made before it is needed.

## What Kam decides next

1. Which of the (a) options (fix extraction / dictionary heuristic at ingest / wait) to pursue,
   and on what timeline relative to any campaign that will record new uses.
2. Whether the eventual extraction fix's re-run should be scoped to the 105 affected current-run
   files only, or run corpus-wide as a matter of course.
3. Whether the promoted-use re-anchoring gap (end of §c) should be designed now or deferred until
   the first promoted use actually cites a superseded run.
