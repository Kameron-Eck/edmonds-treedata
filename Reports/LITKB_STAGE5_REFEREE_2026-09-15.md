# litkb stage 5 — independent referee — 2026-09-15

Referee for `Reports/LITKB_STAGE5_INGEST_2026-09-15.md` (P4 stage 5 "Reconciliation" and the P5
ingest schema). Worktree `D:\edmonds-pipeline\treedata-litkb`, branch `work/20260913-literature-kb`,
HEAD at review `e123948`. `litkb` was read ONLY — nothing but `SELECT`s, and no migration applied
to it (§8); every write and every mutation ran on `litkb_test_w6` / `litkb_test_w9`.

**Verdict: STAGE 5 READY WITH FIXES.** The three defects the builder found in its own output are
genuinely fixed at `e123948`, and my gold — authored from rendered pages before any tool touched
them — confirms the reading-order fix against a HUMAN order rather than against Docling's own
(which is what the builder scored). Four things must change before this schema carries the
archive: **`Benedek_2015` cannot be ingested at all** — NUL bytes in Docling's text abort the
transaction — the four thresholds are not pinned by any test at ±20 %, figures are entered two to
three times each, and a GROBID paragraph that crosses a column break is unioned into a page-wide box
that lands ahead of the column it belongs to.

## 1. The gold — authored first, committed first

`Reports/gold/stage5_gold_2026-09-15.json`
sha256 **`d9cfbba0779d4674804ddb7ce7778173bdf815948e77a80331f989e65fb8dbfa`** (the LF bytes as
written; the working copy is converted to CRLF by `core.autocrlf`, so the immutable identity is the
git blob **`948f66673a1d338b59904af4cb63ea17980670b8`**), commit **`398e4a1`**, made **before**
step 2 and before `reconcile()` was run on any of its pages.

Pages, chosen as the brief names them plus one for captions, which none of the others has:
Benedek_2015 **pp2–3** (two-column body), **p4** (two full-width figures, two captions),
Alwan_1988 **p3** (two-column, rotated margin stamp), Almon_1965 **p1** (JSTOR cover sheet),
Schneider_2008 **p463** (an uncaptioned two-column symbol table at the head of the page).

Method: `pypdfium2` render at scale 2.0 → PNG → read the image and transcribe. The Docling JSON,
the TEI and `reconcile()` were not opened until after the commit — **with one exception I have to
disclose, because the gold's own `_what` line overstates it:** choosing WHICH Schneider page to
annotate used the Docling artifact's list of table pages (9, 10, 11, 463, 670…), from which I picked
463. That was page SELECTION; every annotation on it was made from the render alone, as on the other
five pages. The `_what` line in the committed JSON should have said so and does not. 54 ordered body
snippets, a kind
per block, furniture listed separately, two caption→figure links, and three paragraphs verbatim
**with their spaces**. The scoring is done by my own comparator
(`scratchpad/score_gold.py`), NOT by `reconcile.order_violations` — a checker that shares a bug
with the producer passes both.

## 2. The three self-found defects, at `e123948`

| defect | status at HEAD | evidence |
|---|---|---|
| reading order re-derived from geometry, interleaving two-column pages | **FIXED** | `_assign_order` sorts by the carried `tool_order`; against my gold, **0 of 105** ordered pairs out of order on Benedek p2 and **0 of 105** on p3 (the builder's pre-fix figure was 21 of 23 snippets, scored against Docling) |
| native text returned with the spaces stripped | **FIXED** | all three gold paragraphs match **exactly** after whitespace collapse, `text_source="native"`, spaces present. V1 Alwan p3, V2 Almon p1, V3 Benedek p3: 1 exact-match block each |
| the caption fix in `reconcile.py` but not `ingest.py` | **FIXED** | `ingest.py:147` inserts `litkb.figures (block_id)` only; my mutation F4, which puts the caption back into `description`, fails `test_ingest_writes_blocks_and_moves_the_pointer_last` |

## 3. Gold comparison, measured

Reconciliation from the existing artifacts (GROBID TEI under `_tmp\litkb_tei`, Docling under
`_tmp\litkb_docling`); no tool was re-run.

| page | gold body snippets found | ordered pairs out of order | kind correct |
|---|---|---|---|
| Benedek p2 | 15/15 | **0 / 105** | 15/15 |
| Benedek p3 | 15/15 | **0 / 105** | 15/15 |
| Benedek p4 | 2/2 | 0 / 1 | 0/2 tightest-block, 2/2 any-block — see below |
| Alwan p3 | 12/13 | **10 / 66** | 12/12 |
| Almon p1 | 4/4 | 0 / 6 | 4/4 |
| Schneider p463 | 5/5 | 0 / 10 | 5/5 |
| **total** | **53 / 54** | **10 / 293** | **51 / 53** tightest-block, **53 / 53** any-block |

The two p4 "wrong" kinds are an artifact of my scorer's tightest-containing-block rule, not a stage-5
error: the design deliberately makes a figure's caption the FIGURE block's text, so the tightest
block carrying "Fig. 1. Structure of…" is a `figure`. A standalone `caption` block also exists for
each. Both readings are given above so the number cannot be misread either way.

Captions (Benedek p4): Fig. 1's caption lands on **1** figure block, Fig. 2's on **2**.

**Ingested, not just reconciled.** Each gold page set was ingested into `litkb_test_w9` as
`litkb_ingest` (pages filtered, reading order renumbered; nothing else changed):

| ingested | blocks | disagreements | `litkb.figures` rows / with `description` | duplicate reading orders |
|---|---|---|---|---|
| Benedek pp2–4 | 45 | 20 | **4 / 0** (for **2** real figures) | 0 |
| Alwan p3 | 17 | 7 | 0 / 0 | 0 |
| Almon p1 | 16 | 14 | 2 / 0 | 0 |
| Schneider p463 | 19 | 13 | 0 / 0 | 0 |

Every run moved the pointer last, wrote its `pages` rows, and left `figures.description` NULL —
the third defect's fix confirmed in the database, not only in the source. Block types on
Schneider p463: 1 table, 8 equation, 8 paragraph, 2 page_header — the gold's table region is a
`table` with its cells, as the gold requires.

## 4. Four findings the builder's report does not carry

**(0) `Benedek_2015` cannot be ingested at all — `psycopg.DataError: PostgreSQL text fields cannot
contain NUL (0x00) bytes`.** I hit this trying to ingest the whole file before falling back to the
gold pages. Measured across the four files: Benedek has **6 canonical blocks (pp 6, 8, 9) and 10
disagreement rows** whose text carries a NUL, all `source="docling"`, `text_source="tool"` — i.e.
Docling's own string for a region with no usable native layer. Alwan, Almon and Schneider have
none. The transaction aborts and the file lands nothing. It is invisible today because the
end-to-end test ingests Alwan and Anderson only, and the §5 run table never opens a database.
**Fix:** strip `\x00` from every text field at the reconcile boundary (block text, `latex`, cell
text, and both sides of a disagreement), and add a test that ingests a file containing one.
This is the one finding here that blocks a full-archive ingest outright.


**(a) A GROBID paragraph that crosses the column break becomes a page-wide box, ordered before the
page.** On Alwan p3, gold regions 6 (left column, last paragraph) and 7 (right column, first
paragraph) resolve to ONE canonical block, `grobid`-sourced, box `[14, 245, 561, 728]` — the full
page width including the rotated margin stamp — at `reading_order` 38, ahead of the whole left
column (41–46). `union_boxes` unions an element's per-line boxes per page, and that element's lines
sit in two columns, so the union is not a rectangle on either. `_anchor` then overlaps everything
horizontally and anchors it early. That single block is the whole of the 10/66 out-of-order pairs
and the reason two gold regions have no block of their own. **Not caught by any test:** the
order tests use hand-built single-column blocks, and the one real-file order assertion is scored
against Docling, which does not produce this box.

**(b) Every figure is entered two or three times.** Benedek p4 holds two real figures and
**six** blocks for them: `figure` from GROBID's `<figure>` region, `figure` from Docling's
picture (matched, `source="both"`), and a Docling `caption` block — twice over. Whole file:
**24 figure blocks and 16 caption blocks for 8 figures.** `ingest.py` inserts one `litkb.figures`
row per figure block, and the ingest above measures the consequence in the database:
**4 `litkb.figures` rows for the 2 figures on p4**, both of each pair carrying the caption as their
text. The builder's §5 table reports "fig 24, cap 16" as a
count and never as a duplication. GROBID `<figure>` regions enter `_grobid_regions` through
`GROBID_REGIONS`, and nothing removes them once the dedicated figure pass has run — the same
reason `_docling_regions` already excludes Docling's tables and pictures.

**(c) Furniture is not recognised on every page.** On Benedek p4 the page number `4`, the running
head and the "Please cite this article in press" footer all come out `paragraph`
(`source="docling"`), while the identical items on pp2–3 come out `furniture`. **Measured in the
artifact:** Docling labels all three of p4's furniture items `text`, not `page_header`/`page_footer`
(`D.blocks()` on `Benedek_2015__cpu-t4.docling.json`, page 4). Docling's own label varies; stage 5
passes it through. The effect is that furniture enters the body reading order — visible in the
ingest above as `page_header 4, page_footer 2` across pp2–4, i.e. none on p4.

**(d) The native layer's hyphens come back as U+FFFE, and that is now in `blocks.text`.** V1's
block reads `"detect any spe￾cial causes"`: `pypdfium2` emits the noncharacter U+FFFE at every
line-break hyphen, `native_text_in` slices it through, and it was written into
`litkb_test_w9.blocks.text` by the ingest in §3. I had to strip it in my own comparator to match the
gold at all. Non-blocking for stage 5, but stage 6/7 quote verification and chunking against
`blocks.text` will fail on every hyphenated line until it is normalised — fix it in the same place
as the NUL strip.

One apparent miss is NOT stage 5's: Alwan gold region 8 is the heading "SHEWHART'S **DEFINITION**
OF A STATE"; the PDF's own text layer reads "DEFINIT**B**ON", so the block exists and is correctly
typed `heading` — the source document's native layer is wrong.

## 5. Thresholds — none of the four is pinned at ±20 %

Replay: set the constant, run `qc/test_litkb_reconcile.py` (39 tests, `litkb_test_w6`), restore.

| constant | −20 % | +20 % | any test fails? |
|---|---|---|---|
| `IOU_MATCH` 0.5 | 0.4 | 0.6 | **no**, both directions (39 passed) |
| `IOU_TOUCH` 0.1 | 0.08 | 0.12 | **no** |
| `TEXT_AGREE` 0.90 | 0.72 | 0.99 | **no** |
| `COVERAGE_FLOOR` 0.80 | 0.64 | 0.96 | **no** |

Eight moves, eight clean passes. The report's claim that the constants "are pinned by tests and by
mutation rows, which stops them drifting unnoticed" holds only at the extremes the harness uses:
`R53` 0.5→0.02, `R54` 0.5→0.999, `R55` 0.80→0.0. `IOU_TOUCH` and `TEXT_AGREE` have **no mutation
row at all**. A drift of a fifth is invisible.

What the move actually costs, measured on the artifacts:

| file | matched at 0.5 | at 0.4 | at 0.6 |
|---|---|---|---|
| Benedek_2015 | 171 | 174 | 167 |
| Alwan_1988 | 84 | 86 | 83 |
| Almon_1965 | 31 | 32 | 31 |

`IOU_TOUCH` ±20 % moves 0–1 regions on all three. The corpus pages nearest each cut:

* `IOU_MATCH` 0.5 — **Benedek p7** at IoU 0.5334 (just inside) and **Benedek p9** at 0.4559 (just
  outside); Alwan p5 at 0.4906; Almon p4 at 0.4558. Only 11 / 4 / 1 candidate pairs lie in
  [0.40, 0.60) at all.
* `IOU_TOUCH` 0.1 — Benedek p5 at 0.1029, Alwan p8 at 0.1003, Almon p5 at 0.1020.
* `TEXT_AGREE` 0.90 — Benedek p9 at 0.9015, Alwan p8 at 0.9048, Almon p4 at 0.8932.
* `COVERAGE_FLOOR` 0.80 — **no page in the three files is anywhere near it.** Minimum share:
  Benedek 0.9989 (p6), Alwan 0.9918 (p6), Almon 1.0000. At floors 0.64, 0.80 and 0.96 alike the
  count of failing pages is **0, 0, 0**. The floor is not a gate at the operating point; it is a
  catastrophe detector, and it should be described as one.

**Kind precedence is not a number and is barely exercised.** Docling wins kind; GROBID's reading is
kept as `kind_alt`. Across all three files there are 3 / 5 / 9 `kind_conflict` rows, and — checked
on every gold page of all four files, Almon p1 and Schneider p463 included — **zero on any gold
page**, so the gold cannot score the rule. The commonest conflict is (GROBID `figure`,
Docling `caption`) — 3 on Alwan, 3 on Almon — where my gold agrees with Docling.

## 6. The coverage blind spot, and a metric that sees it

Plant on a gold page (Alwan p3): remove the ONE canonical block that is gold region 3 ("In the light
of the widespread use of ARIMA models"), `source="both"`, box `[65, 187, 302, 370]`, 885 characters,
overlapped by 2 other canonical blocks.

| metric | before | after | gate |
|---|---|---|---|
| **A** covered share (shipped) | 1.0000 | **1.0000** | **MISSES** — floor 0.80, and the number does not move at all |
| **B** coverage multiplicity — mean blocks responsible per character | 2.6756 | 2.5318 | 5.4 % relative drop; a 5 % per-page drop gate **FIRES**, and it needs no gold |
| **C** gold-region recall — per REGION, does some block *begin* at it | 10/13 | 9/13 | **FIRES** and names the lost region |

This is a sharper demonstration than the builder's "drop the largest block on p4", quoted there as
1.0000 → 0.9723 (I did not reproduce that figure; my plant is the stronger case and the verdict does
not rest on theirs): here the shipped metric does not move by one character, because the removed
paragraph's ink is entirely inside two surviving overlapping blocks. **Recommendation:** keep A as
the page-body gate, add **B** as the cheap per-page regression gate (no gold, monotone in blocks),
and use **C** wherever gold exists. Note that C's baseline is already 10/13, not 13/13 — the three
it misses are exactly finding §4(a) and the DEFINITBON text-layer error, which A reports as 1.0000.

## 7. GROBID vs Docling: it is granularity **and** structural exclusion, not silent loss of prose

Every Docling region bucketed against GROBID's:

| | Almon_1965 (48 vs 398) | Benedek_2015 (233 vs 430) |
|---|---|---|
| matched (IoU ≥ 0.5) | 31 | 171 |
| touching (0.1 ≤ IoU < 0.5) | 13 | 15 |
| furniture (a label GROBID never emits) | 52 | 32 |
| **granularity** (≥ 80 % of its area inside a GROBID region) | 69 | 110 |
| **lost** (non-furniture, no GROBID box overlapping) | **233** | **102** |

GROBID's TEI body holds **40** elements for Almon and **224** for Benedek (1,077 and 1,464 raw
per-line boxes; `union_boxes` turns them into 48 and 233 regions — the extra are elements split at a
page break, which is correct). So GROBID is not regioning at a finer grain that the matcher is
missing; it is emitting far fewer regions, and the difference resolves as:

* **Structural exclusion.** GROBID regions **nothing at all** on Almon pp1, 2, 19, 20 (JSTOR cover
  sheet, title page, and the two reference pages) and on Benedek p16 (references). Those four/one
  pages carry 49 and 37 of the lost regions. References are not lost from the reconciliation —
  they come back through the `biblStruct` pass — but they are lost from the body matcher, and the
  cover sheet is genuinely dropped.
* **Docling exploding tabular pages.** Almon p15 alone contributes **109** lost regions and p11
  contributes 32 (`list_item` per line of a numeric table); Benedek p15 contributes 33. That is
  Docling at line grain where GROBID has nothing.
* **Genuine granularity**, 69 and 110 regions: Docling splitting inside a GROBID paragraph.

**Therefore:** `partial_overlap` is under-reporting, and one-to-one greedy matching is the wrong
shape for the 69 + 110 granularity bucket — many-to-one (a Docling region assigned to the GROBID
region that contains it) would recover those and stop them being emitted as `docling_only`
disagreements, which is what inflates the disagreement counts in §5 of the builder's report. It is
**not** true that regions of body prose are being lost: outside front matter, reference pages and
Docling's line-grain table splitting, the lost bucket is small (Benedek: 15 regions across pp4–9).

## 8. Ingest kills — my own, on `litkb_test_w9`

| kill | result |
|---|---|
| duplicate ingest inserts nothing | **PASS** — second call `inserted=False`, same `run_id`, blocks 40 → 40, one run row |
| a real mid-file process kill leaves no duplicates | **PASS** — child hung with blocks inserted, `taskkill /F /T`; another session saw **0 blocks and 0 run rows** during and after; re-ingest then inserted 40 with one run row |
| writer role cannot insert a block | **PASS** — `InsufficientPrivilege: permission denied for table blocks`; `add_disagreement` likewise |
| `set_current_run` refuses a failed run | **PASS** — SQLSTATE 22023, "is not an ok extraction run" |
| the `tables.cells` retirement trigger | **PASS** — an INSERT carrying a cells blob is refused, 22023 |

**A correction to the report's §4 wording.** Under correct behaviour a killed worker leaves
*nothing*, not a carcass: the run row is opened inside the same transaction, so the rollback takes
it too. The `clear_extraction_rows` resume path is therefore unreachable in normal operation —
defence in depth against the per-page-commit variant, which is exactly what `R515` mutates into
existence. It is right to keep it; it should be described as unreachable-unless-broken rather than
as the thing that happens after a kill.

**Is applying 0017 to `litkb` safe? YES.** The trigger is
`BEFORE INSERT OR UPDATE ON tables … IF NEW.cells IS NOT NULL THEN RAISE`. It validates nothing at
apply time, so it changes nothing about existing rows *as they stand*; what it changes is that any
existing row with a non-NULL `cells` blob becomes un-UPDATE-able, because an UPDATE carries the old
blob forward as `NEW.cells`. Measured on `litkb` (read-only SELECTs, 2026-09-15):
`litkb.tables` **0 rows**, `cells IS NOT NULL` **0 rows**, and `blocks`, `pages`,
`extraction_runs`, `figures`, `equations`, `chunks`, `references` all **0 rows** (`files` holds
192). There is no row the trigger can strand and no writer filling the column. Apply it.

**That yes covers the SCHEMA only.** Apply `0017` to `litkb`; do **not** ingest real files into it
until §4(0) (the NUL bytes) and §4(b) (doubled figures) are fixed, or the first archive ingest will
die on Benedek and record two `litkb.figures` rows per figure for everything that does land.

## 9. Harness, gates, secrets

Six mutations written in my own words (not copied from `litkb_p2_mutations.py`), each applied to
the real source, scored by `qc/test_litkb_reconcile.py`, restored with `git checkout --`:

| mine | fires on |
|---|---|
| F1 reading order re-derived from geometry | `test_assign_order_keeps_doclings_order_across_two_columns` |
| F2 the anchor stops requiring the same column | `test_a_region_only_grobid_saw_anchors_inside_its_own_column` |
| F3 native text back to joining the ink | `test_native_text_is_a_slice_of_the_page_and_keeps_its_spaces` |
| F4 ingest writes the caption into `figures.description` | `test_ingest_writes_blocks_and_moves_the_pointer_last` |
| F5 `IOU_MATCH` → 0.999 | `test_two_tools_boxing_the_same_paragraph_slightly_differently_still_match` |
| F6 the `tables_cells_retired` trigger is not created | `test_kill_the_retired_tables_cells_json_is_refused` |

**6/6 fired**, working tree clean afterwards.

`py -3.12 qc/check.py --fast` under `LITKB_TEST_DB=litkb_test_w6`, on the final tree (the report is
the only change in it): **1 failed, 2,672 passed, 22 skipped, 2 xfailed**, 31 min 07 s; litkb
Postgres tests **261 passed**. The single failure is
`qc/test_experiments.py::test_pointer_paths_resolve[crown_state_model]`, the known pre-existing one
the builder also reports — `check.py` therefore exits at the `pytest` rung, as it did for the
builder. `secrets`, `ruff` and `compile` passed ahead of it.

`git log -p 9e9f511..e123948` (9 commits), scanned for `password|secret|api[_-]?key|PRIVATE KEY|
postgres://|pgpass`: **no matches**. No credential material in the range.

## 10. What must change before stage 5 carries the archive

0. **Strip NUL bytes before ingest** (§4(0)). Without it `Benedek_2015` — and any file whose
   Docling text carries a 0x00 — cannot be ingested at all. Normalise U+FFFE (§4(d)) in the same
   place, before stage 6 reads `blocks.text`.
1. **Pin the thresholds or stop calling them pinned.** Add mutation rows at ±20 % for all four, or
   state in `reconcile.py` that they are unpinned within a fifth. `IOU_TOUCH` and `TEXT_AGREE` have
   no row at all.
2. **Stop entering a figure twice.** Exclude GROBID `<figure>` from `_grobid_regions` the way
   Docling's pictures and tables are already excluded, or drop the GROBID figure region once the
   dedicated figure pass has claimed it. As it stands `litkb.figures` will hold two rows per figure.
3. **Do not union a GROBID element's line boxes across a column gutter.** Split by column (a gap in
   horizontal overlap between consecutive lines) the way the page break is already split, or the
   cross-column paragraph keeps landing ahead of the page as a full-width box.
4. **Add coverage metric B** (multiplicity, 5 % per-page relative-drop gate). It costs one pass over
   the same points, needs no gold, and it is the only one of the three that fires on the plant in §6
   without gold.
5. **Say the coverage floor is unexercised.** No page in the gate set is within 0.19 of it.
6. Consider many-to-one matching for the 69 + 110 granularity regions before stage 6 reads the
   `docling_only` disagreements as evidence of anything.

---

*Referee: Claude Opus 5, session https://claude.ai/code/session_015MUcyGTfX2koRdYAjW5kED.
Scoring scripts live in the session scratchpad, not the repo; every number above is reproducible
from the committed gold, the tracked source at `e123948` and the artifacts under
`D:\edmonds-pipeline\_tmp`.*
