# Referee — litkb Items 1/2/3 (2026-09-19)

Independent referee, `work/20260919-referee-items123` @ `f30d28d`. I built none of these. Every
item was re-run in a **detached scratch worktree** at the item's own commit (scratchpad), so no
writer ran in an item branch. Worker DB `litkb_test_w12` verified reachable (role `litkb_test`)
and `reset`+migrated to 23 migrations before use — MEASURED. It was **not** free when I arrived:
it held 1,126 `litkb.blocks` rows from a previous user, which my reset destroyed. The
orchestrator's "free" was RELAYED and is contradicted by that residue.
Labels: MEASURED = I ran it · TRACKED = read from a file · RELAYED = unchecked.

## Item 1 — ligature C0 (`da91101`)

| claim | theirs | mine | status |
|---|---|---|---|
| same byte, two ligatures, one file | 0x01 = ff and fi | 0x01: `e␁ects`(ff) and `in␁nitely`(fi), two distinct **current-run** blocks, file `01a0a4d6…` — MEASURED by SQL on live `litkb`, not via their dictionary | REPRODUCED |
| c0 instrument | 681 unresolved / 127 ambiguous / 119 resolved, 1 within-file conflict | identical; output CSV **byte-identical** (sha256 `593acc09…`) — MEASURED | REPRODUCED |
| 0 of 8 live `use_evidence` touch an affected block | 0 | 0 **current-run**; but **1 of 8** cites a C0-carrying block on a superseded run, and 6 of 8 are anchored off-current-run — MEASURED | PARTIALLY REPRODUCED |
| hazard flips (real trigger) | control 8/0, before 44/0, spanning 54/54, after 48/48, 102 true→false, 0 false→true, 60 gone / 42 shifted | identical, on w12 — MEASURED | REPRODUCED |

Stated plainly, as asked: (b) is **real block text + real trigger + invented uses + a placeholder
expansion**. It proves the trigger's own offset predicate — a quote at or after an edit fails,
one before it does not — executes as specified. It does **not** validate any normaliser, and the
"100%" is a property of the predicate, not a measured risk rate. Their report says this; the
mapping is labelled placeholder throughout. Also: `letters+C0+letters` catches non-ligature glyph
codes too — byte 0x5 contributes 111 occurrences, every one `unresolved`, 49 of them with suffix
`L` — so "681 unresolved" is not 681
unresolvable ligatures — the denominator is looser than the word "occurrences" suggests.

**Verdict: ACCEPT WITH CAVEATS** — (1) qualify the "zero live uses" claim with *current-run*;
1 of 8 already cites a C0 block on a superseded run. (2) Say the 681/127/119 denominator includes
non-ligature C0 glyphs. No number was overstated; no normaliser shipped. Back to the Item 1 agent
as wording, not rework.

## Item 2 — Crossref raw-string proposer (`8829558`)

| claim | theirs | mine | status |
|---|---|---|---|
| title/author-blind refs | 50/658 | 50/658 — MEASURED | REPRODUCED |
| proposer never abstains | 50/50 | 50/50, 0 search errors — MEASURED, **fresh cache, 100 live Crossref calls** | REPRODUCED |
| end-to-end gate refuses all | 50/50 `unresolved` | 50/50 `unresolved`; reason histogram identical (33 title_ratio / 11 author_mismatch / 4 type_mismatch / 1 year / 1 review); top-hit DOI identical on **49/50** (the drift row is garbage either way) — MEASURED | REPRODUCED |
| hand scoring 22/3/24/1 | builder's own | blind re-score, 18 rows stratified on reason, 4 already-seen rows excluded, labels hidden until after I graded — 17 of the 18 truly blind, since stratification forced in the single `review_record` row (Burnicki b10), whose verdict my launch prompt had already named: **17/18 strict agreement, 0 right/wrong flips**. One difference (Guo b2 `correct` vs their `edition`) — their note is better informed than my read — MEASURED | REPRODUCED (no re-score of all 50 needed) |
| Burnicki b10 gate false positive | `review_record` from a dropped first author | confirmed: ref author list is `['dean']` (GROBID dropped CARMEL), Crossref's is `['carmel','dean']`, and the record **is the cited work** (IJRS 2004), not a review of it — MEASURED | REPRODUCED |

The load-bearing caveat is in the code, not the CSV. 28 of 50 refs have no parsed title;
`title_match_ratio("", t) == 0.0 < 0.85` — MEASURED — so those 28 refusals are forced by an
empty-string comparison before any evidence is weighed. "100% specificity on the 24 wrong
proposals" and "0% recall" are therefore one fact about the routing condition, not two findings,
and specificity here is not discrimination. The commit message and the module docstring both name
this mechanism; the report's headline framing does not.

**Verdict: ACCEPT WITH CAVEATS** — state the tautology in the headline, not only in the body.
Code, tests, mutation rows and the false-positive finding all hold.

## Item 3 — pix2tex evaluation (`0b2cae0`)

| claim | theirs | mine | status |
|---|---|---|---|
| same 20 gold items as the 11/20 | implied | `p5_gold_2026-09-16.json` sha256 `6eeab1eb…` = the prior referee's published hash — MEASURED. The 40% vs 55% **is** a comparison | REPRODUCED |
| CodeFormula 11/20 | 55% | TRACKED, not re-scored: `score_gold.py` transcribes the prior referee's table (ids match §3 exactly) | REPRODUCED as a transcription |
| pix2tex 8/20 | 40% | my fresh GPU run prints 8/20 — **but only because `PIX2TEX_CORRECT` is a hardcoded id→bool dict**. My run's LaTeX differs from theirs on **10/20**, and two consecutive runs of mine differ from each other on **8/20**: pix2tex is nondeterministic here, undisclosed in the report. The number cannot be recomputed from predictions — MEASURED | NOT REPRODUCED as a measurement (plausible as a verdict) |
| agreement 6/20, both-wrong 0/6 | 6, 0 | 6/20 in all three runs, the **same six ids** (E04,E09,E13,E14,E16,E18); 0/6 holds. Spot-checked the two pivotal grades against the crops myself: E05 pix2tex has `S^{d-1}` (right), E08 drops `1-` in row 3 and a row-4 entry (wrong) — MEASURED | REPRODUCED |
| bulk 24/199, garbling 27/199 and 4/20 | — | 24/199, 27/199, 4/20 exactly, from the tracked predictions with the regex reconstructed from the report's own words — MEASURED | REPRODUCED |
| garbling regex measures garbage | "one output in five to seven is outright garbage" | it measures **token repetition only**. I read the first 110 characters of 10 bulk hits: **2** (`2b196654de`, `8c65b3dbb6`) are a clean decode followed by a `\qquad` run — which the scorer's own `normalize()` strips as meaningless — and the report itself says gold E03's hit is a run of `\:` spacing tokens, so 3 flagged outputs I can name are spacing, not collapse. Of 10 non-hits I read, several are garbage it misses (`\rightarrow\infty` repeats — token >6 chars; `S^{\operatorname{rececosor}9}` symbol salad) — MEASURED | PARTIALLY REPRODUCED (count yes, interpretation no) |
| population | §2/§5 say ingest-**accepted** 6,841, 323 in the verify queue | 6841 + 323 = 7164 — MEASURED. Correctly stated and correctly caveated | REPRODUCED |

**Verdict: ACCEPT WITH CAVEATS** — evaluation-only, no litkb write, and the directional
conclusion (agreement precise but low-coverage) survives. Named defects for the Item 3 agent:
(1) disclose the nondeterminism and that 8/20 is one sample; (2) `score_gold.py` is not a scoring
instrument — both correctness vectors are frozen literals, so it cannot detect a changed decode;
(3) drop "outright garbage" for what the regex actually counts; (4) the PNGs (below).

## 3. Kills I fired myself

| id | mutation applied | tests red | restored |
|---|---|---|---|
| P6-G8 | harness, then **by hand**: `confirm_s2_candidate(...)` → `"confirmed", "...", None` | 4 red: `…still_refused[besag_b11]`, `[besag_b32]`, `…one_reachable_happy_path…`, `…sibling_edition…` | `git checkout --`, sha256 `1f16ab8d…` = pre-mutation; baseline 58 passed before and after |
| P6-G9 | harness: blind class no longer routed to `resolve_by_raw_search` | 2 red: `…one_reachable_happy_path…`, `…routes_the_blind_class…` | sha256 match, baselines green |
| P6-S7 | harness: `normalize_doi` call site becomes its own argument | 2 red: `…normalised_to_lower_case`, `…sibling_edition…` | sha256 match, baselines green |

Item 2's own suites, run read-only in `treedata-crossref`: **75 passed** (`test_litkb_crossref_raw_search.py` + `test_litkb_confirm_asymmetry.py` + `test_litkb_references.py`) — MEASURED.
Note for anyone repeating this: `sha256sum <file>` ≠ `git show <rev>:<path> | sha256sum` on Windows (CRLF); compare working-tree to working-tree.

## 4. Did NOT test

- Item 1: whether font subsetting is the *cause* — the DB cannot show it; that mechanism is INFERRED, not measured. Nothing on `litkb_test_w11`.
- Item 1: no real normaliser exists, so nothing measures a real expansion's offset shifts.
- Item 2: the other 32 hand verdicts outside my blind sample; the two Besag review fixtures against live Crossref.
- Item 3: no fresh bulk decode (199 crops) — the bulk numbers are recomputed from their tracked predictions, so the *decode* there is theirs; crop-fidelity vs the real Colab crop; correctness on the bulk sample (no gold).
- All three items' full `check.py --fast` at their own commits.

## 5. Process findings

- **220 crop PNGs, 2.35 MB, committed into `Scripts/scratch/pix2tex_eval/` in the code repo** (`de40434`, 232 files / 3,789 insertions total) — MEASURED by `git ls-tree -l`. CLAUDE.md §2.3 puts data in the lake; §2.4 calls `scratch/` convention-only with contents archived. Not a science defect; the crops should live in `litkb_derived/`, referenced by path.
- `score_gold.py` / `run_pix2tex_gold.py` hardcode `D:\edmonds-pipeline\treedata-pix2tex\…` absolute worktree paths, so running them from any other checkout writes into that worktree. I repointed copies rather than run them as shipped.
- Neither the catastrophic-garbling regex nor the bulk agreement count has a tracked implementation — §3.4b's instrument rung is missing for two published numbers (both happen to reproduce).
- Item 1's hazard instrument hardcodes `litkb_test_w11`; I changed that one literal to w12 in my copy and nothing else.

## 6. Gate

`cd Scripts && PYTHONUTF8=1 LITKB_TEST_DB=litkb_test_w12 py -3.12 qc/check.py --fast`, run once in
**my** worktree at `f30d28d` — MEASURED: **1 failed, 3,167 passed, 25 skipped, 2 xfailed in
642.09s**, the one failure the known-tolerated `test_pointer_paths_resolve[crown_state_model]`
(exit 1 for that reason). **`litkb Postgres tests: 410 passed, 3 skipped`** against w12. This is an
environment smoke at the base commit — my worktree carries only this report, so it tests none of
the three items. It does, however, settle Item 3's §7: the 414 litkb tests run fine on a worker DB
that exists; only `litkb_test_w13`'s absence stopped them there.

## 7. Blockers

- `litkb_test_w13` does not exist on the server (MEASURED: `FATAL: database "litkb_test_w13" does not exist`) — Item 3's §7 blocker is real; its gate ran zero litkb tests. Needs `provision_workers` by someone with superuser.
- pix2tex nondeterminism means no pix2tex accuracy figure is reproducible without a fixed seed or
  a multi-run protocol. **The 8/20 / 40% is not citable until that is decided** — the agreement
  numbers (6/20, 24/199) are, having held across three independent runs.
