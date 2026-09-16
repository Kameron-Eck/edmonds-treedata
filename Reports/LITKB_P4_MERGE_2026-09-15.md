# litkb P4 adapters merged — 2026-09-15

Branch `work/20260913-literature-kb`, worktree `D:\edmonds-pipeline\treedata-litkb`, from `fed255a`.
Three refereed P4 branches merged `--no-ff`, in order, each proved before the next was started.
**The merger wrote none of the three branches**; this report records what was merged, what
conflicted, and what the merged tree measures — not a re-review of the branches' science.

| # | Branch | Tip merged | Merge commit |
|---|---|---|---|
| 1 | `work/20260915-inventory-stage0` (stage 0, inventory) | `cc36b82` | **`d621cfe`** |
| 2 | `work/20260914-grobid-local` (stage 2, GROBID) | `8f985e5` | **`cae333a`** |
| 3 | `work/20260915-docling-local` (stage 3, Docling) | `5b26768` | **`14e3091`** |
| — | merge fallout: two Docling sinks reach the sink checker | — | **`11db0fa`** |

`work/20260915-references` and `work/20260915-colab-l4-formula` were **not** merged, by the brief.

## Conflicts, and how each was resolved

Three, all textual, all "keep both":

* **`Scripts/pipeline/litkb/extract/__init__.py`** — add/add at merges 2 *and* 3: three branches each
  created the package with its own docstring. Resolved to Docling's text, which is the only one
  carrying the load-bearing rule (**no adapter may import its heavy tool at module scope**, design
  referee M9), under inventory's title line naming stages 0–4. Nothing was dropped but wording.
* **`Scripts/requirements-litkb.txt`** — content conflict at merge 2. Both branches added the **same
  pin**, `pypdfium2==5.13.0`, with different justifications. One pin, one merged comment that states
  all three readers' reasons and points here for the ownership question below.
* Predicted but did **not** conflict: `.gitignore` / `.gitattributes` (GROBID only),
  `qc/instruments/litkb_p2_mutations.py` (inventory only — auto-merged), the design doc (GROBID
  only), `qc/test_status_discovery.py` (auto-merged), `pyproject.toml` (Docling only).

**The brief expected three forked copies of the design doc §7/§12 to reconcile. Two of them never
existed:** `git diff` against the merge base shows only `work/20260914-grobid-local` edited
`Scripts/LITERATURE_KB_DESIGN_2026-09-13.md`. Inventory and Docling recorded their §7.1 and §12
findings in their reports and in code docstrings only, so there was no three-way text to reconcile —
their numbers had to be *folded in* instead, which is what the §7.1 / §12.2 / §12.10 / §14 edits in
this merge do.

## One real defect the merge surfaced — `11db0fa`

The Docling branch forked at `4256e4e`, **before the P3 sink checker existed**. Its two new stdout
sinks (`litkb/extract/docling.py::<module>::print`, `litkb/extract/docling_worker.py::main::print`)
were therefore never scanned on their own branch — `--sites` passes there because it does not know
about them. On the merged tree it failed with two PROBLEM lines. Both print a metrics dict (page
counts, seconds, pages/s, peak RSS, a path the caller typed); neither module opens the database or
holds the archive key, and the worker's line is a fixed seven-key projection, so no value outside
that set can reach the sink. Both are now `SINK_ALLOW` rows with that reasoning written out.
**Merge commit `14e3091` fails `--sites` on its own; `14e3091` + `11db0fa` pass it.**

## Proofs, per merge

| After | `--sites` | `check.py --fast` (`LITKB_TEST_DB=litkb_test_w6`) | The branch's own tests, in the merged tree |
|---|---|---|---|
| `d621cfe` | PASS | 2,544 passed, 1 failed — **only** `test_pointer_paths_resolve[crown_state_model]` (the known pre-existing failure); litkb Postgres tests 244 passed | `qc/test_litkb_inventory.py` **60 passed, 1 xfailed** |
| `cae333a` | PASS | 2,587 passed, same single failure; litkb 244 passed | `qc/test_litkb_grobid.py` 40 passed / 14 skipped with the service down; **54 passed, 0 skipped** with GROBID started in WSL (`grobid.sh start`, alive after 18 s) and `LITKB_LIVE=1` + `LITKB_LIVE_PDF` set to a real corpus PDF. Service stopped afterwards (`grobid.sh stop`) — an idle 8 GiB JVM is the defect |
| `14e3091` (+`11db0fa`) | PASS after `11db0fa` | 2,629 passed, same single failure; litkb 244 passed | `qc/test_litkb_docling.py` 37 passed / 3 skipped on fixtures; **40 passed, 0 skipped** with `LITKB_LIVE=1` against the CPU venv `D:\edmonds-pipeline\venv-docling` — that run converts a real PDF, so the live Docling requirement is met |

## After all three

**Parallel mutation harness, `--workers 4 --worker-dbs 1,2,6,9`:**
**155/155 mutations fired; baselines passed; wall-clock 43.0 min over 4 workers** (39 / 39 / 39 / 38
per worker, each reporting its baselines passed). No row was skipped and none had to be re-run.

**Inventory census reproduction.** `py -3.12 -m litkb.extract.inventory --force` re-probed all
**241 files / 5,038 pages in 45.1 s**. The regenerated `phase4/qc/litkb_inventory.csv` is
**byte-identical to the tracked file once the final `seconds` column is masked** (242 lines, header
plus 241 rows; all 172 changed lines are timing-only). The tracked file was restored and the
regenerated `.jsonl` deleted, so this merge changes no measured CSV.

**Migration 0016 applied to `litkb`.** `py -3.12 -m litkb.db.migrate --db litkb` →
`applied 1 (0016_held_reason.sql); 16 recorded`, as `litkb_owner`. P3 deliberately left it pending
because that session held `litkb` read-only; it is additive (one new function, one
`CREATE OR REPLACE`) and P3-accepted. Its known limit stands: the 68 held rows and 10 pending
bindings already in `litkb` keep their NULL reason and bare verdict until they are loaded again.
All four test databases used here (`litkb_test_w1/w2/w6/w9`) were already at 16;
`litkb_test` itself was two behind (0015, 0016) and was brought up before any test ran.

**The P3 gate, re-run read-only against `litkb` after 0016:**
**1,086 changed cells → explained 713, format 243, structural 120, filled 10, UNEXPLAINED 0,
GATE: PASS** — the P3 buckets unchanged, and `phase4/qc/litkb_p3_diff.csv` regenerates with an empty
`git diff`. (The instrument takes the workstream **UUID**, `01a0a494-bb54-7c1b-be26-db0c229a9534`;
the slug `p3-migration` raises `invalid input syntax for type uuid`. The P3 report's command line
gives the slug — a small doc defect, recorded here rather than fixed in a report that is history.)

## Open, and deliberately not closed by this merge

1. **Three `page_frames` readers, one fact.** `litkb.extract.inventory`, `…grobid` and `…docling`
   each read the §7.1 frame. Same `dx`/`dy` arithmetic, but **not interchangeable**: inventory's and
   GROBID's resolve a page that inherits its `/MediaBox` from the page tree and GROBID's raises on a
   missing mediabox, while Docling's copy has neither guard and would raise `TypeError` there.
   Inventory's docstring already claims the role. Collapsing them is a change to code three referees
   measured against, with no referee for the change (CLAUDE.md 3.4c) — so it is recorded in design
   §7.1 as an open item, **to be closed before stage 5 reconciliation is written**, which is the
   first place a disagreement between the copies produces wrong boxes.
2. **Corpus definitions.** Four are now in circulation (216/223; 224/4,712; 219/4,655; 241/5,038).
   §12.2 now names `phase4/qc/litkb_inventory.csv` as the home and marks 219/4,655 superseded, but
   §7.1's older counts are left as the referees wrote them, with their populations stated.
3. **The gates that remain**, recorded in design §14: the **throughput gate** (GROBID measured at
   concurrency 1 only with derived per-worker RSS; Docling measured on 5 gate papers and the book,
   not the corpus; metrics parked as JSONL rather than `extraction_runs.metrics`), and **stage 5
   reconciliation**, which is not built and for which no gate has been written. Also unverified:
   §14's "referee-authored, pre-committed gold" clause — nothing in the three reports records gold
   authored by a referee and committed before the measurement.
4. **Each branch head is an author commit made after its last referee report.** Most pointedly,
   `GROBID_LOCAL_REFEREE2` returned **STAGE 2 NOT READY** on defect D1 and `8f985e5` closes it. The
   fix is real (`enable` now goes through `write_unit()`, which calls `require_concurrency_headroom`
   before writing the unit) and it is exercised by the tests that passed above, but **it has not been
   re-refereed**.

## Housekeeping

The mutation harness's worker **copy** directories are shared across worktrees at
`D:\edmonds-pipeline\_litkb_harness_workers\`. `--workers 4` recreates copies `w1`–`w4` whatever
databases it is pointed at, so a `--worker-dbs 1,2,6,9` run still overwrites copies `w3` and `w4`.
No other session's run was in flight here, but the copy index and the database index are independent
and it is worth knowing before two sessions run the harness at once.

## Corrections to this report's own first draft (same day)

Two, both found by re-checking pointers against the files rather than against notes:

* The design-doc section pointers this merge added were **composed from line numbers, not read off
  headings**, and named sections that do not exist ("§the frame", "§kills", "§throughput"). They now
  quote the real heading text of `LITKB_DOCLING_LOCAL_2026-09-15.md`,
  `…DOCLING_LOCAL_REFEREE_…`, `…DOCLING_A_REFEREE_…` and `LITKB_INVENTORY_2026-09-15.md`.
* The §14 row "the throughput instrument refuses a run with no rate or no peak RSS — FIRES (both
  tools)" **overstated GROBID**. Docling's refusal is measured;
  `qc/instruments/litkb_grobid_throughput.py` records `peak_rss_bytes` but has **no refusal path**,
  and no referee exercised one. The row now reads "FIRES for Docling; NOT SHOWN for GROBID", and it
  is one more clause the throughput gate owes.

## Not done, and named

`qc/landed.py --dry-run` reports its mechanical rungs clean and the CHATLOG entry is appended
(CLAUDE.md §3.12). **The GitHub push was refused by the permission classifier**
("Out-of-Place Publication"), not by git or by credentials; the branch is pushed to `drive-mirror`
(`e9f5a88..c472b32`). Pushing `work/20260913-literature-kb` to `github` is Kam's to allow.
Incidentally, `litkb_test` itself was found two migrations behind (0015, 0016) and brought to 16
before any test ran; the four worker databases were already at 16.

---

# P6 merged

`work/20260915-references` at **`e176707`** merged `--no-ff` into `work/20260913-literature-kb`
(from `8cbed38`) as **`7b8afd7`**, plus one merge-fallout commit **`98f9d1b`**.
**The merger wrote neither side.** `work/20260915-splink`, `…-colab-l4-formula`, `…-embeddings` and
`…-access-layer` were not merged, by the brief.

## Conflicts: none

Every file auto-merged. The three the brief predicted did not conflict, and it is worth saying why,
because "no conflict" is not the same as "no interaction":

* **`litkb/admit/resolver.py`** — P6 changed it (+301 lines: `confirm_s2_candidate`, the review and
  type tests, the `10.48550` refusal at gate 0). **The litkb side never touched it** in
  `8f985e5..8cbed38`, so P3's loader behaviour could not move. The P3 gate below is the check.
* **`qc/instruments/litkb_p2_mutations.py`** — both sides changed it, in different regions: the
  litkb side rewrote the redaction rows and the docstring, P6 added a `tests=` kwarg to `block()`
  and two registrars that append the P6 and P7 rows to the one table. Both survive; the merged
  harness runs 226 rows through one engine and one `--sites`.
* **`requirements-litkb*.txt`** and **`.gitignore`** — P6 changed neither.
* **The design doc** reconciles to **one** stage-6 home: P6's two blocks (§7, after the stage table —
  "the title ratio is a FILTER", "S2 PROPOSES, CROSSREF CONFIRMS") sit where the litkb side has no
  text, whose own additions are in §7.1, §12 and §14. `grep -n "Stage 6"` finds three lines, all in
  that one block. Nothing was dropped and nothing was written twice.

## One real defect the merge surfaced — `98f9d1b`

The same class as `11db0fa`, from the other direction. P6 forked at `8f985e5`, **before the
redaction family (`netutil.redact` / `add_secret` / `run._redacted`) came under the per-call-site
rule on 2026-09-14** — that work is on the litkb side. So `s2.py::request::redact` is a call site of
a governed helper that **neither branch's own `--sites` could see**: P6's table has no RD rows, and
the litkb side has no `s2.py`. On the merged tree `--sites` failed with one PROBLEM line and exit 1.

The site is s2.py's status-0 branch, the one place in the module that puts raw response bytes
(120 of them) into a returned string — a string the `StageBreaker` report and the log then carry.
Row **P7-RD19** passes the `redact()` through; the new test registers a key, has the stub transport
echo it in a status-0 body, and asserts the error carries `<KEY>` and not the key. It **FIRED** in
the full harness. `--sites` after: **75 call sites, 72 covered by a row, 3 equivalent; 16 sinks,
2 redacted, 14 allowed** — no new sink needed allowlisting.

## Proofs on the merged tree

| Proof | Result |
|---|---|
| `--sites` self-check | **PASS** (exit 0) after `98f9d1b`; `7b8afd7` alone fails it |
| P6's own tests, cache-only | `test_litkb_references.py` + `test_litkb_s2.py` + `test_litkb_annas.py`: **191 passed, 3 skipped**. The 3 are `litkb_live: network test; run with LITKB_LIVE=1` — no wire |
| The 293-reference table | `litkb_s2_batching.py --arm confirmed`: **293 references → 20 resolved / 23 ambiguous / 250 unresolved**, unchanged |
| P3 gate, read-only on `litkb` | **1,086 changed cells → explained 713, format 243, structural 120, filled 10, UNEXPLAINED 0, GATE: PASS**, and `phase4/qc/litkb_p3_diff.csv` regenerates with an **empty `git diff`** |
| Full parallel harness, `--workers 3 --worker-dbs 1,6,9` | **226/226 mutations fired**, 0 DID NOT FIRE, wall-clock **115.5 min**. Per worker: 76 (`litkb_test_w1`) / 75 (`litkb_test_w6`) / 75 (`litkb_test_w9`) |

**The 293 run put 0 requests on the wire** — `requests_total 0`, S2 0, Crossref 0, **arXiv 0**, with
211 S2 cache hits. That is not a property of the tree: referee 2 §1 measured 46 arXiv requests on
this arm and §11 recorded 1, because each run warms that cache further. Quote it as "cached here",
not "cache-only by construction".

**Baselines: two workers passed, worker 3 reported FAILED — and it is corpus drift, not the merge.**
The only failing baseline is `test_litkb_inventory.py::test_the_frame_reader_reproduces_the_committed_corpus_census`,
which **failed in worker 3's PRE-MUTATION baseline**, before any source was touched, so no mutation
is implicated and all 75 of its rows still fired. Re-run here on the clean merged tree it fails the
same way: **`assert 246 == 224`** — `D:\edmonds-pipeline\Literture` now holds 246 active PDFs
against a census pinned at 224 (the second failure in its final baseline,
`test_the_boundary_pins_really_are_the_nearest_pages`, is the same class). **The merge diff contains
no inventory file at all**, so this is the data plane moving under a pinned number.

**Where the 22 came from, measured.** All of the growth is in
`Literture\_litkb_staging\filed` (26 PDFs), which is litkb's own acquisition store and sits
**inside** the census root, excluded by nothing — the census excludes only `_quarantine`. The five
newest are timestamped **18:12–18:13 today**, an hour after this merge commit, and are entity-
resolution and bibliographic-matching papers (`Linacre_2022_splink-free-software-probabilistic`,
`Massari_2023_opencitations-meta`, `Guenci_2025_pipeline-matching-bibliographic-references`,
`Papadakis_2020_…`, `Mandilaras_2021_…`), i.e. **another session's `work/20260915-splink`
acquisitions landing in a store this worktree shares**. Nothing in this session wrote them: the
harness deselects live tests and this merge ran no acquisition.

So the honest statement is not "someone must re-pin the numbers" but: **stage 0's census root
contains a store that other workstreams actively grow, and its corpus definition does not exclude
it**, so any number pinned to a file count under `Literture` expires the next time a paper is
acquired. That is a corpus-definition question for the design's §12 — which already carries three
different corpus definitions — not a re-pin job for this merge, and re-pinning refereed numbers on
an unrefereed change is what 3.4c forbids.

## Migration: none written, and one gap named instead

**No `0018_citations.sql`. The trigger did not fire: the tables already exist.** `"references"` and
`citation_mentions` are created in **`0002_text.sql`** (which also adds the `candidates` →
`"references"` FK), and `candidates` in **`0001_core.sql`**. `litkb` was therefore **not touched** —
read-only throughout, and the P3 gate above is the only thing that connected to it.
`extract/references.py` states the same thing in its own header: *"DB-FREE BY CONSTRUCTION … written
by P5's ingest"*.

**The live ingest was not run, because there is nothing to run it with**, and that is the honest
finding rather than a skipped step: `litkb/extract/ingest.py` writes pages, blocks, tables, figures
and equations and contains **no reference to `references` or `citation_mentions`** at all. Stage 6's
output is 658 JSONL rows parked under `{LITKB_DERIVED}/p6/` (plus 645 candidates and 13 edges) with
no loader on either side of this merge.

Two things a future loader will hit, measured here and left alone:

1. **`references.resolution` has a CHECK of `('resolved', 'candidate', 'unresolved')`, and stage 6
   emits `ambiguous`** — 19 of the 658 rows (23 of the 293 under test). Either the CHECK widens or
   the loader maps `ambiguous` onto `candidate`; that is a design call, not a merge call, and
   widening a CHECK on `litkb` is neither additive nor testable against a loader that does not exist.
2. **`edges.jsonl` has no table.** The citation graph is 13 rows on this corpus with nowhere to go.

**And the sentence this merge was addressed by.** `extract/references.py:8` and
`LITKB_REFERENCES_2026-09-15.md:21` both say *"the citation-graph columns are applied at merge"* —
this merge is the one they name. Neither report says which columns, and the branch ships no `.sql`;
gap 2 above is what that sentence is pointing at. **This merge applied none**, because the only
honest column change is the one a loader's shape decides, and there is no loader. The claim is left
standing in P6's own report as history, and answered here.

## The ladder

`PYTHONUTF8=1 LITKB_TEST_DB=litkb_test_w6 py -3.12 qc/check.py --fast`:
secrets PASS, ruff PASS, compile PASS, **3 failed, 2,798 passed, 22 skipped, 2 xfailed in 26.8 min**;
litkb Postgres tests **262 passed**.

**It is not "only `crown_state_model`", and the two extra failures are the corpus drift above, not
this merge.** The three:

* `qc/test_experiments.py::test_pointer_paths_resolve[crown_state_model]` — the known pre-existing one;
* `qc/test_litkb_inventory.py::test_the_frame_reader_reproduces_the_committed_corpus_census`;
* `qc/test_litkb_inventory.py::test_the_boundary_pins_really_are_the_nearest_pages`.

`git diff 8cbed38 HEAD -- Scripts/qc/test_litkb_inventory.py Scripts/pipeline/litkb/extract/inventory.py
phase4/qc/litkb_inventory.csv` is **empty** — the merge changed no byte of the test, the module or the
committed census. What changed is `D:\edmonds-pipeline\Literture`, which now holds **246** active PDFs
against the **224** the census pins. Whoever grew the corpus owns re-running stage 0 and re-pinning the
five numbers; this merge deliberately does not, because re-pinning them silently would retire refereed
numbers on an unrefereed change (CLAUDE.md 3.4c).

---

# P8 merged

2026-09-16. `work/20260915-access-layer` at `fd59bc3` merged `--no-ff` into
`work/20260913-literature-kb` at `7ca8eb0`. Merge commit **`c932bea`**; the decisions it deferred are
**`6afc566`**. Neither side was written by the session that merged them.

## Conflicts — three, all union, none a disagreement

| file | HEAD | P8 | resolution |
|---|---|---|---|
| `litkb/commands.py::main` | added `use`, `inventory` to the dispatch | added `promote` | all three |
| `test_litkb_p1.py::_EXPECTED_EXECUTE` (writer, promoter) | writer gains `_feeds_token_ok` (0020) | reader+writer gain `check_ws_token`/`norm_search_text`/`any_term_query`, promoter gains `promotion_chains` (0018) | the union — both migrations are applied, so both sets of grants exist |
| `test_litkb_p1.py::_EXPECTED_EXECUTE["litkb_ingest"]` | four stage-6 writers (0020) | `norm_search_text` (0018's expression index runs as the INSERTing role) | the union |

Auto-merged and read by hand rather than trusted: `.gitignore` (P8's root `.claude/` whitelist at the
head, HEAD's `*.sha256` / `Reports/gold/` / harness-lock rules at the foot — disjoint), `netutil.py`
(P8's shape redactor at the top, HEAD's `Content-Type` `setdefault` in `_raw_get` — disjoint),
`litkb_p2_mutations.py` (P8's X-rows appended to HEAD's F5*/U* rows; the sink tuple carries both new
pairs, `redact_shapes` and `_require_token`).

## The feeds-validator collision, and what 0021 decides

`_reserved.txt` had recorded this for whoever landed 0018, and it was right. **0018 and 0020 each
`CREATE OR REPLACE litkb._feeds_token_ok` with a different seven-form body**, written independently,
and a `CREATE OR REPLACE` is decided by the order migrations were **applied**, not by their numbers.
Measured on `litkb_test` the moment 0018 landed on top of 0020 — not reasoned, run:

```
framework §13.1.1   -> false    0018's depth rule: at most one sub-level
report notmd#§5     -> TRUE     0018's `[^ ]+`: the file part need not name a document
```

A database built from scratch runs 0018 then 0020 and answers the other way round on both.
`test_litkb_p8.py` asserts the first is refused; `test_litkb_first_use.py` asserts the second is
refused. Neither suite was wrong — the schema was two schemas, with one migration set and one set of
checksums.

Both earlier files were by then applied and checksum-locked, so neither could be the one that
changes. **`0021_feeds_validator_final.sql`** takes the second of the two options `_reserved.txt`
offered: state the definition once, in the highest-numbered file, so it is applied last on every
database whatever order the earlier two arrived in. Each disagreeing clause is settled against
`docs/LITERATURE_CONVENTION.md`, the one home for what a token MEANS:

* **`framework §N` keeps 0018's at-most-one-sub-level.** The convention says it in as many words —
  "`framework §N` at most one (`framework §13.1`)" — and its table spells the token `framework §N[.N]`.
  A strict rule can also be relaxed later without invalidating a stored token; the loose one cannot.
* **`report <FILE>#§<loc>` keeps 0020's `.md` requirement.** `report notmd#§5` resolves to no
  document, which is the defect the 2026-09-13 vocabulary closed when it stopped accepting a bare
  `§N`. A token that names nothing is that same hole wearing a prefix.

The other five clauses are byte-identical in both and are carried over unchanged. 0021 grants nothing
new — `CREATE OR REPLACE` keeps a function's ACL — so the role census is untouched by it.

**Two mutation rows repointed**, because a row on a replaced function body tests nothing. This is the
third time the class has bitten (`MIG16`, `MIG20`, now `MIG21`), and the first time with two branches
open at once, which is what made it produce two schemas rather than one dead row:

* **U1** (coverage) narrows 0021 back to 0005's three forms — caught by the seven-form acceptance
  tests in both suites;
* **X12** (depth) deletes 0021's definition, which falls back to **0020's looser body** on a
  from-scratch build and so takes `framework §13.1.1` — caught by `test_litkb_p8.py`. Deleting the
  block leaves a *valid* migration whose function does the wrong thing, which is what 0018's own
  X11/X13/X14 note demands of a migration row.

One guard, two rows, deliberately: they break different halves of it, and different suites catch them.

## Migrations applied

| database | before | after | by |
|---|---|---|---|
| `litkb` | 18 (…0017, 0020) | **21** | `py -3.12 -m litkb.db.migrate --db litkb` as `litkb_owner` |
| `litkb_test` | 18 | 21 | same, `LITKB_TEST_DB=litkb_test` |
| `litkb_test_w1` / `w6` / `w9` | 18 each | 21 each | same, one per worker |
| `litkb_test_w2` | 19 | **19, untouched** | P8's own worker; left where its referee left it |

`_reserved.txt`'s 0018/0019 lines are deleted with this merge (a number on disk must not also be
reserved), and its collision note is replaced by what closed it.

## Proofs on the merged tree

| Proof | Result |
|---|---|
| `--sites` self-check | **PASS** (exit 0): **89 call sites, 86 covered by a row, 3 equivalent; 18 sinks, 2 redacted, 16 allowed**. The merge dropped none of P8's sinks — no new allowlist entry was needed |
| P8's tests, merged tree | `qc/test_litkb_p8.py` + `qc/test_litkb_first_use.py`: **96 passed, 3 skipped** (the 3 are `litkb_live`) |
| P8's tests **including** the live MCP mini-hunt | `LITKB_LIVE=1 … qc/test_litkb_p8.py` on `litkb_test`: **60 passed, 0 skipped** |
| The feeds vocabulary, both databases | `litkb_test` and `litkb` (as `litkb_writer`, the one role holding EXECUTE): the SAME **12 accepted forms and 14 refused forms**, no disagreement. The 14 are the union of P8's seven rejected shapes and first-use's nine |
| **Apply order no longer decides the schema** — the point of 0021 | `md5(prosrc)` of `litkb._feeds_token_ok` on the two orders that used to diverge: `litkb`, which ran 0020 first and then 0018/0019/0021, and `litkb_test`, reset and re-migrated 0001..0021 from scratch by the pytest session. Both **`982600bf2bd477aab6565c4b3ad0879a` — IDENTICAL**. Before 0021 these two answered differently on `framework §13.1.1` and on `report notmd#§5` |
| P3 gate, read-only on `litkb` | **1,086 changed cells → explained 713, format 243, structural 120, filled 10, UNEXPLAINED 0, GATE: PASS**, and `phase4/qc/litkb_p3_diff.csv` regenerates with an **empty `git diff`** |
| The 293-reference table | `litkb_s2_batching.py --arm confirmed`: **293 references → 20 resolved / 23 ambiguous / 250 unresolved**, unchanged. `requests_total 0`, 211 cache hits — cached here, not cache-only by construction |
| `check.py --fast` under `litkb_test_w6` | Run twice. At `6afc566`: **1 failed, 2,964 passed, 25 skipped, 2 xfailed in 10.9 min**. At the pushed tip, after the harness fixes in `549c5ee`: secrets PASS, ruff PASS, compile PASS, pytest **1 failed, 2,963 passed, 26 skipped, 2 xfailed in 7.6 min**; litkb Postgres tests **360 passed, 3 skipped** both times. The one failure is `test_experiments.py::test_pointer_paths_resolve[crown_state_model]` — **only that**, at both commits. The two inventory census pins that failed at the P6 merge now pass |
| Full parallel harness, `--workers 3 --worker-dbs 1,6,9` | **271/272 mutations fired, wall-clock 71.9 min**. Per worker: 91 rows (`litkb_test_w1`) / 91 (`w6`) / 90 (`w9`). But **`baselines FAILED`, rc 1 from all three**, and one row did not fire — both below. Closed in `549c5ee`; the 20 rows they touched re-ran **20/20 fired, baselines passed, 3.5 min** |

### What the harness found, and why 271/272 is not the headline

The two findings below were produced by the harness, not by reading it, and neither is a defect in
either merged branch. They are what a merge does to a mutation suite.

**1. The baseline was red, so nineteen verdicts in that run are VOID — not wrong, void.** P8 put the
skill, the librarian and the staged hook at the **repository root** under `.claude/` (design §9.1:
Claude Code walks up from the session's cwd, so a root-level directory is what reaches a session
opened in `Scripts/`), and `qc/test_litkb_p8.py` reads all three by path off `SCRIPTS.parent`. None
is under the harness's `COPY_DIRS`, so inside every worker copy all three were missing and the P8
baseline ran at **14 failed / 43 passed** — while the same file passes **60/60** in the real tree.

That is worse than a wrong count. `run_one` calls a mutation FIRED when its run has **any** failure,
comparing nothing against the baseline, so with a baseline already red **all nineteen X rows report
FIRED whatever the mutation does**. The separate baseline check is the only thing standing between
that and a clean-looking table, and it did its job: `baselines FAILED`, rc 1, from all three workers.

The three files join `COPY_FILES`, the list whose own comment already says this in as many words —
*"a test's whole read domain must be inside the copy"*. This is the third entry added to it by a
failing baseline rather than by review. `.claude/settings.json` deliberately does **not** join it: it
is git-ignored, it is the one file P8's design says must not carry the hook registration, and the
test that checks it skips when it is absent — copying an untracked per-session file would make a
worker's verdict depend on whichever session last edited it. After the fix the P8 baseline reads
**57 passed, 3 deselected** in every worker copy, and all nineteen X rows fire against it.

**2. A18 DID NOT FIRE, and it is the replaced-function class a fourth time — created by this merge.**
0019 `CREATE OR REPLACE`s `litkb._ws_chains` for its evidence clause and carries 0013's guard *a fact
chain enters main only through admission approval* along with it. So 0013's copy of that guard is
dead text: deleting it changes no database, and A18 was deleting it there. Repointed to 0019 — where
X15 already pointed — it fires, caught by
`test_litkb_p2.py::test_an_unapproved_manual_admission_is_held_at_promote_prepare`.

That is the same lesson as `MIG16`, `MIG20` and `MIG21`, and the fourth time it has cost something:
**whenever a migration replaces a function, every mutation row on the old body silently stops testing
anything.** The harness now carries a constant for each of the four, so the next one is a lookup.

Worth stating plainly: **X12 fires on exactly the token this merge was about** —
`test_a_feeds_token_outside_the_vocabulary_is_still_refused[framework §13.1.1]`. Delete 0021's
definition and a from-scratch database falls back to 0020's looser depth rule and takes it. That is
the apply-order split, reproduced as a gate.

## `litkb`, read-only after the merge

`litkb_reader`, `SELECT count(*)` per relation:

| relation | count |
|---|---|
| `works` | **447** (433 on main) |
| `files` | **239** (225 on main); `file_versions` active **239**, every one carrying a binding |
| `uses` | **385** (`use_versions` 385; **0 on main** — none has been promoted) |
| `discrepancies` | **914** |
| `"references"` | **643** |
| `citation_mentions` | 969 |
| `citation_edges` | 13 |
| `blocks` | **0** — as expected; the bulk text pass has not run |

## Design §9, amended

Per `LITKB_P8_REFEREE_2026-09-15.md` §5, and written into
`Scripts/LITERATURE_KB_DESIGN_2026-09-13.md` §9 rather than left in a referee's paragraph:
`promote prepare` **is** exposed to agents as `litkb_propose_promotion`, with the credential clause
kept exactly (the tool shells out; the promoter passfile is opened by a process that exits), and with
the reason `commit` and `approve` stay absent written down — `commit` records that *Kam merged*, and
`approve` is a *second session's* act, so an agent holding either would be attesting to its own work.

**One condition of that amendment no longer holds, and it is recorded rather than inherited.** The
referee's condition (i) was that `report_path` is "a recorded string, not a write primitive", because
prepare wrote no file. His own F-5 fix then made prepare write the report, so an agent-supplied
`report_path` now reaches `promote.write_report`, which does `Path(path).parent.mkdir(parents=True,
exist_ok=True)` and `write_text` — used verbatim when absolute, resolved against the worktree when
relative, with no `..` check. **READ FROM SOURCE, not exercised:** `mcp/server.py::_propose_promotion`
sends `report_path` to `--report`; `commands.py::cmd_promote` prepare branch; `promote.py::write_report`.
Scoping that path is a NEW guard on an already-refereed branch, so it was not invented at this merge.
It is Kam's, with condition (iii)'s `decisions.yaml` line, which nothing here stages.

## One test that had encoded transient state

`test_litkb_p1.py::test_an_undeclared_gap_in_the_migration_numbering_is_still_refused` manufactured
nothing: it copied the tree's migrations into a tmp directory and leaned on 0018/0019 being **absent
from disk** while `work/20260915-access-layer` held them. The moment that branch merged the numbering
went contiguous, nothing was refused, and the `pytest.raises` had nothing to catch. It now digs its
own hole — in the MIDDLE, because a missing *last* migration is a shorter list, not a gap, and
`discover()` cannot tell that from a branch that has not written its next one yet.

## Also landed

`Scripts/docs/LITKB_AGENT_BASE_BRIEF.md` — the standing half of every litkb agent launch, previously
pasted from a scratchpad into each prompt, now tracked so a change to it is a diff somebody reviews.
Two edits against the copy it was made from: the census-pin known failures are dropped (they pass, as
the ladder above shows), and the commit-signature line names "the session URL in your launch context"
instead of hard-coding one session's URL, which would have been wrong for every agent after this one.
The migration-number hazard gains the harder case this merge paid for: `_reserved.txt` cannot catch
two branches replacing the SAME function.

## Not closed by this merge

* **`report_path` is unbounded** (above). Kam's, with the §9 amendment.
* **`decisions.yaml` carries no line for the §9 amendment.** Kam's by rule; nothing here staged it.
* **The harness's `run_one` compares nothing against its baseline.** It reports FIRED on any failure
  at all, so a red baseline turns every row answered by that test file into a false positive — which
  is exactly what happened above, and only the separate baseline check stood between it and a clean
  table. The P8 referee flagged the neighbouring blind spot in the same function ("this harness
  counts failures, not errors") and named it as not his branch's to change mid-pass. It is still
  nobody's. Whoever owns the harness next: a row's verdict should be the DIFFERENCE from its own
  baseline, not the absolute count.
* **`litkb_test_w2` stays at 19 migrations.** It is P8's worker; the suite resets and re-migrates
  whichever database it is pointed at, so this costs nothing, but the number is stated rather than
  quietly fixed.
* **The P3 report's "`work/20260915-access-layer` had **not** patched the validator" is now false.**
  It was true when written (checked with `git grep` against `b787fa0`); `65dca14` added the
  seven-form body afterwards. The sentence is left standing in that report as history and corrected
  here, which is what the collision above cost.
