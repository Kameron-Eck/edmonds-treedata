# litkb — referee of the operational test (`LITKB_OPERATIONAL_TEST_2026-09-16.md`)

Independent pass, 2026-09-16. Worktree `D:\edmonds-pipeline\treedata-access`, branch
`work/20260915-access-layer`, HEAD `f6586fc`. Database: live `litkb` read as `litkb_reader`
throughout — **102,008 blocks, 242 extraction runs, 447 works, 433 in main's view**
(`psql -At -c "select (select count(*) from litkb.blocks), …"`), the same corpus the session
measured, so no rank here is explained by the corpus moving.

Everything below was re-derived. No number is taken from the report under review, and no
number is taken from the database's own summary of itself where the underlying rows could be
read instead (CLAUDE.md 3.4c). The MCP server was driven as a **real stdio subprocess**
(`py -3.12 -m litkb.mcp.server`, `mcp.client.stdio.stdio_client` + `ClientSession`,
`LITKB_DB=litkb`, `LITKB_AGENT=referee`, `LITKB_SESSION=optest-referee-1`); handshake
`server: litkb, version: 0.1.0`, nine tools, matching the session's. Workstream `op-test-1`
was **not written to**: `litkb_ws_status` read `{"gap": 6, "use": 6}` before my probes and
`{"gap": 6, "use": 6}` after them.

**The headline.** The evidence machinery does what the report says it does — every quote is
byte-exact at the offsets recorded, every refusal fired, the promotion's hash recomputes.
What the report gets wrong is smaller and all of one kind: **claims about the corpus that were
stated from one reading and not checked against the source.** Four of them are wrong, and the
most expensive is the sentence in its own verdict — "`litkb_work` … One column name."

---

## 1. The three fresh uses, against the papers

Each quote was checked three ways: byte-exact in the live block (`text.find`, the same literal
match `server.py:592` makes), present on the **rendered PDF page** the use cites, and the
`feeds` tokens opened and read in the documents they name.

| | use | grade |
|---|---|---|
| **F1** | `01a0aa62-343e-79d5-875e-f35e332bcb7b` — Mousavi_2009 p2 | **answers** |
| **F2** | `01a0aa62-34f7-7baf-b380-58757b756807` — Gasparrini_2010 p3 | **answers** |
| **F3** | `01a0aa62-3555-7177-bcb5-4c7c65f946ef` — Efron_1986 p3 | **partially** |

### 1.1 Offsets and bytes

```
F1: find=326 len=295 reported=(326,621) computed=(326,621)  MATCH
F2: find=0   len=145 reported=(0,145)   computed=(0,145)    MATCH
F3: find=0   len=166 reported=(0,166)   computed=(0,166)    MATCH
```

All three quotes are present in the live block, literally, at exactly the character range the
report prints and the database stored (`litkb.use_evidence.char_start/char_end`, all six rows
`quote_verified = t`). Nothing here is paraphrase, and nothing depends on trusting the
session's transcript.

### 1.2 F1 — Mousavi & Reynolds 2009 p2 — **answers**

PDF page 2 rendered (footer "Vol. 41, No. 4, October 2009 … 401 … www.asq.org") is the title and
abstract page. The abstract reads, verbatim: *"It is shown that both the Shewhart p-chart and
the most efficient chart for independent observations, the Bernoulli CUSUM chart, are not
robust to autocorrelation, and that adjusting the control limits of these traditional charts to
account for the autocorrelation is not an efficient approach."* The block differs from the page
only by the line break the extractor kept between `control` and `limits`.

The question posed — *keep the Bernoulli CUSUM by adjusting limits, or a different chart?* — is
answered squarely and in the paper's own words, and the next sentence of the same abstract names
the replacement ("a Markov binary CUSUM (MBCUSUM) chart based on a log-likelihood-ratio
statistic"). `feeds` checks out three for three: framework **§19.6** (line 1641, "Same-day
addendum — the dependence half of row 20 has a published chart") is about this paper and this
sentence; gap ledger **row 20** (line 486) is "CUSUM under dependence and multiplicity"; narrative
**§7** (lines 311–346) is "Step 6 — detecting change" and names Mousavi & Reynolds at line 340.

*Caveat, not a deduction:* the evidence is the **abstract**, the authors' own summary, not the
analysis that supports it. For a [Q] that retires a design compromise that is thin; the body's
Sections 3–5 carry the demonstration. The system cannot see the difference — a block is a block.

### 1.3 F2 — Gasparrini, Armstrong & Kenward 2010 p3 — **answers**, with the diagnosis wrong

PDF page 3 rendered (journal page 2226, *Statistics in Medicine* 29:2224–2234), last paragraph
before §3.3:

> **Here** the choice of the basis to derive **C** can be considered as the application of a
> constraint to the shape of the distributed lag curve described by **β̂**.

The stored block is `e choice of the basis to derive C … described by bˆ`, and the quote is
literally a substring of the page. The question posed — *what does the choice of `C` impose on
the fitted lag curve?* — is answered in one sentence. `feeds` checks out: framework **§19.2**
(line 1573) quotes this very sentence; gap row **19** (line 485) is the distributed-lag-GLM row;
narrative **§5** (lines 213–286) carries the cross-basis at lines 242–243.

**Two corrections.**

1. The report says *"The extractor's block boundary cut 'The' to 'e'."* The source word is
   **"Here"**, not "The" — the extractor dropped `Her`, not `Th`. Measured by rendering the page;
   the framework's own quote at line 1577 starts lowercase `the choice`, which is only correct
   if the preceding word is `Here`. A one-word error, but it is the report's own explanation of
   its only damaged citation, and it was never checked against the paper.
2. The block writes **`bˆ`** where the paper writes **`β̂`**. A reader quoting the stored block
   into a report silently changes a Greek parameter to a Latin one. The quote gate cannot see
   this: it verifies the quote against the block, and the block is what drifted from the page.

The report's friction item 7 claim — that this is the *only* block in the corpus carrying the
sentence — **holds**: `select … where mw.key='Gasparrini_2010_distributed-lag-non-linear' and
b.text like '%choice of the basis%'` returns exactly one row.

### 1.4 F3 — Efron 1986 p3 — **partially**

PDF page 3 rendered (header "Journal of the American Statistical Association, June 1986", page
462), opening of §3 "Optimism of the Apparent Error Rate": *"This section considers estimating the expected optimism of the apparent error
rate, in other words the downward bias of e̅rr as an estimate of the true error rate."* Verbatim
(the block renders `e̅rr` as `err`, losing the overbar). (a) passes; (b) passes — the quantity is
the expected optimism, the direction is downward.

**(c) is where it comes apart.** The three tokens are `framework §5.1`, `gap row 6`,
`narrative §8`.

* `narrative §8` — **exact.** Line 353: "true error = apparent error + `Ω` … (Efron 1986; 2004
  Theorem…)". This paper, named.
* `framework §5.1` — **topically right, wrongly sourced.** §5.1 (line 293) opens
  `**[Q]** (Efron 2004 Thm 1 and Remark F, review §4.12.3)`. The section states the identity
  this quote's direction belongs to, but the authority it cites is a **different Efron paper**.
  The use points at a section whose own [Q] is Efron 2004.
* `gap row 6` — **mis-targeted.** Row 6 (line 472) is *"Covariance penalty under spatially /
  class-correlated error"*, and its kill is "independent-Bernoulli bootstrap must under-estimate
  `Ω` on an injected correlated field; correlated one must not". Efron 1986 is the
  **independence** case — the block itself says "by independent binary sampling" — so the quote
  supplies the baseline row 6 departs from, not anything row 6 tests.

The recorded statement then over-reaches: *"which is why row 6 needs Omega per stratum and not a
citywide average."* Per-stratum summing is **§5.1's** rule and §5.1 gives its own reason — "an
average-risk estimate blesses a launderer when change is rare" — which is about rarity, not
sign. The quote is true, the framework claim it is attached to is true, and the link asserted
between them is the session's, unsupported by the passage.

### 1.5 The framing all three share

**None of the three is a question the corpus had not already answered in the project's own
documents.** Framework §19.6 lines 1645–1647 quotes F1's sentence; framework §19.2 lines
1577–1578 quotes F2's sentence; narrative §8 line 353 cites F3's paper for exactly this identity.
The report calls them "Three fresh questions the framework actually raises … searched cold and
answered from a held paper". What actually happened is **citation verification** — three quotes
the project was already relying on, checked byte-for-byte against a stored extraction with
recorded offsets for the first time. That is worth doing and is arguably the more valuable
result; it is not what the section claims, and the difference matters because a reader will take
§2 as evidence the system closes *open* questions.

### 1.6 The statement is not gated, and nothing checks a `feeds` token

Two structural observations that F2 and F3 both expose. The quote gate verifies the **quote**;
the **statement** is free text, and both F2's "nested models rather than rival estimators" and
F3's "which is why row 6 needs Omega per stratum" are inferences the quoted sentence does not
carry. And `feeds` validation is by shape only — migration 0018's own comment says so:
*"Whether the section, gate, row or decision a token names EXISTS is checked against the target
document, not here."* So `gap row 6` on an independence-only result passes silently.

---

## 2. Gold ranks, re-run

Three `litkb_search` calls at the tool's default `limit=10`, `scope="all"`, through the stdio
server, gold block ids taken from `Reports/gold/p8_gold_2026-09-15.json`:

| gold | work | rank of the gold block | report said |
|---|---|---|---|
| Q1 | Bellettini_2002 p3 `…e991…` | **1** | 1 |
| Q2 | Jackson_2011 p3 `…a961…` | **2** | 2 |
| Q3 | Rosychuk_2003 p16 `…2f48…` | **2** | 2 |

Reproduced exactly. All three clear gold's top-5 bar. The three fresh searches reproduce too:
F1 chosen block at rank **2**, F2 at rank **1**, F3 at rank **4** — the report's own figures.

Two counts in the report do not reproduce, both understating how far one work dominates its own
query: F1's query returns Mousavi at ranks **1,2,3,4,5,6,8** (report: "1, 2, 3, 5, 6"), and F3's
returns Efron at **all ten** (report: "ranks 1–8"). The chosen-block ranks — the load-bearing
numbers — are right.

### 2.1 The gold-quote refusals are text drift, byte for byte

`text.find(gold_quote)` returns **-1** in all three live blocks. The differing bytes, gold → live:

| gold | gold byte | live byte | what it is |
|---|---|---|---|
| Q1 | `U+0020` ×2 | `U+000D U+000A` ×2 | the `.txt` collapsed wraps; the blocks keep CRLF |
| Q1 | `U+FFFD` | `U+00BC` (`¼`) | `.txt` extractor emitted a replacement char; docling emits the glyph |
| Q2 | `U+0020` | `U+000D U+000A` | as Q1 |
| Q3 | `overesti-·mate` | `overestimate` | grobid de-hyphenates across the line break |
| Q3 | `U+FFFD` | `U+00FF` (`ÿ`) | as Q1 |

Not a verifier defect, and the report's diagnosis is right as far as it goes — but it stops one
step short of the decisive point. The gold's own `_quote_rule` says *"Line wrapping in the
extract is collapsed to single spaces"*, so **a gold quote spanning a line break can never
literally occur in any stored block that preserves line breaks**, whatever the extractor. The
refusal was guaranteed by the gold's construction rule before any extractor difference was
reached; the `U+FFFD` substitutions are a second, independent cause. `litkb_search` finds them
anyway because both sides go through `litkb.norm_search_text` (`server.py:387–389`).

*Aside, non-blocking:* the gold's `extract_lines` pointers are stale — Q1's passage is at
`.txt` lines 189–192 not 187–189, Q3's at 854–857 not 839–840. The passages are all genuinely
in the files (`.txt` mtimes 2026-09-12, three days before the gold), so this is imprecision in a
frozen provenance pointer, not a fabricated one.

---

## 3. Verification independence — five probes, five refusals, nothing written

Driven through the stdio server as a write-capable session (`LITKB_AGENT=referee`). Every probe
carried gap slug `referee-backstop-slug-never-create` with **no** `gap_question`, so
`unknown-gap` (`server.py:619–623`) stood as a backstop write-barrier behind the guard under
test; no probe passed `char_start`/`char_end`, which would have skipped the locate and stored an
unverified row.

| probe | what | result | fired? |
|---|---|---|---|
| A | F1's verified quote, one character changed (`approach.` → `approacZ.`), its own block | `quote-not-in-block` | **yes** |
| B | Mousavi's verified quote against **Efron's** block, `work_key=Mousavi…` | `quote-not-in-block` | yes (see below) |
| C | Efron's own quote and block, `work_key=Mousavi…` | **`work-mismatch`** — *"the block belongs to Efron_1986…, not Mousavi_2009…"* | **yes** |
| D | Efron's own quote and block, `doi=10.1080/00224065.2009.11917794` (Mousavi's real DOI) | **`work-mismatch`** — *"the block's work is not the work named"* | **yes** |
| E | backstop reached once (probe with a wrong DOI that resolved to nothing) | `unknown-gap` | yes |

`litkb_ws_status` read `{"gap": 6, "use": 6}` before and after. Nothing was written.

**The task's stated route cannot reach `work-mismatch`, and that is not a fault.** `server.py`
locates the quote at line 592 and checks the work at line 605, so a quote from paper A against
paper B's block is refused as `quote-not-in-block` first (probe B). The work guard is reachable
only when the quote *is* in the block and the caller names a different work (probes C and D) —
both branches fire, with distinct messages. The integrity property holds on either path anyway,
because `work_id` is **derived from the block** (`server.py:578–581`) and never taken from the
caller: there is no argument combination that files A's quote as evidence about B. Probe B's
refusal even names `work_key: Efron_1986_how-biased-apparent-error` — the block's true work,
contradicting the caller's claim in the same payload.

Probe A is the one that matters for the report's central claim. One character, in a quote whose
other 294 characters are exact, at the correct block: refused. The verifier is byte-literal, not
fuzzy.

---

## 4. The three gaps — the report's diagnosis is wrong for Mei, and the real hole is bigger

Read-only. The report says Mei_2010 *"is admitted in main and holds 0 blocks (`psql`: held,
unextracted)"*.

**Measured:**

| work | in main? | file bound in DB | blocks | PDF on disk |
|---|---|---|---|---|
| `Mei_2010_efficient-scalable-schemes-monitoring` | yes (promoted) | **0** | 0 | **yes** — `Validation/Mei_2010_efficient-scalable-schemes-monitoring.pdf` |
| `Platanios_2014_estimating-accuracy-unlabeled-data` | no | 1, state `proposed`, ws `p3-migration` (**open**) | 0 | yes |
| `Platanios_2016_estimating-accuracy-unlabeled-data` | no | 1, state `proposed`, ws `p3-migration` (**open**) | 0 | yes |
| GUM / JCGM | — | — | — | **no such work and no such file** |

So **"held, unextracted" is wrong for Mei.** The PDF is on disk, the work is promoted in main,
and **no file version binds them** — there is nothing for an extraction run to target. The
remedy is not "extract Mei", it is "bind the file, then extract", and the report sends the next
session at the wrong one. GUM is correctly diagnosed: nothing on disk, nothing admitted.

**Should the bulk pass have covered them? No — and its coverage of what it could see is
complete.**

```
main files with zero blocks .................. 0     <- the bulk pass missed nothing in main
main works with no file at all ............... 208 of 433
works with a bound file but zero blocks ...... 14   (all state 'proposed', all in OPEN workstreams:
                                                     p3-migration x12, edge-pre1990 x1, linkage-review x1)
PDFs in Literture\Validation ................. 207
distinct Validation rel_paths bound in DB .... 187
Validation PDFs bound nowhere (any root) ..... 17
  ... of which the work exists with 0 files .. 10   Anderson_1957, Hudson_1978, Hwang_1982,
                                                    Kingman_1962, Maragos_1989, Marsan_2008,
                                                    Mei_2010, Ogata_1998, Stehman_1998, Vixie_2007
  ... of which no work carries the key ....... 5    Girard_2019b, Jaffe_2015, Kats_2019b,
                                                    Politis_1994, Schneider_2008
  ... benign (a second copy is bound under
      _litkb_staging/, the work IS extracted) .. 2  Ratner_2017, VargasMunoz_2019
```

Two distinct, standing recall holes, neither named in the report and neither visible through the
tool surface:

1. **Ten admitted works whose PDF sits in the literature root unbound.** Every one is
   unreachable by search forever, and each looks identical to "not held" from inside a session.
   Mei_2010 is one instance; Jaffe_2015 (framework §19.4's third source) and Marsan_2008
   (narrative §5's EM) are two more the framework leans on.
2. **Fourteen acquired, bound PDFs stranded in open workstreams**, twelve of them in
   `p3-migration` (open since 2026-09-15 03:20). They are outside main, therefore outside the
   bulk pass, therefore invisible. Platanios ×2 — framework §19.4's [Q] for the identifiability
   condition — are in this set, alongside Batson_2019 (Noise2Self, narrative §8), Raykar_2010 and
   Krähenbühl ×2.

`litkb_work(key="Platanios_2014_…")` answers this correctly and helpfully today
(`found: false` + the "admitted in another open workstream" hint) because the miss path never
reaches the broken statement. For Mei it crashes. That is the report's own observation, and §5
shows it is worse than reported.

---

## 5. The dead tool — **two** column names, not one

Reproduced through the stdio server on `key=Efron_1986_how-biased-apparent-error`,
`key=Mei_2010_efficient-scalable-schemes-monitoring`, and `doi=10.1093/biomet/asq010`:

```
{"ok": false, "refused": "error",
 "message": "UndefinedColumn: column \"container\" does not exist\nLINE 1: SELECT type, title, authors, year, container, publisher, wor...",
 "tool": "_work"}
```

`litkb.main_works` has **`venue`**. Confirmed by `\d litkb.main_works`. So far the report is
right. But running `_work`'s statements one at a time as `litkb_reader` finds a **second** one,
masked by the first:

```
-- server.py:426,428
SELECT f.sha256, v.path, v.bytes, v.pages, f.current_run_id::text ... ORDER BY v.path
ERROR:  column v.path does not exist
```

`litkb.main_files` has **`rel_path`**. Line 421 raises before line 426 is ever reached, so
`container` hides `path` exactly as `_work`'s miss path hides `container`. **The report's verdict
sentence — "One column name." — is false, and a fix applied from it would ship a tool that still
crashes on the first work it is asked about.** The other four statements (identifiers, files-join
shape, uses, discrepancies) run clean.

**The fix, stated and not applied** (three edits, one function, `server.py`):

* line 421 — `container` → `venue`
* line 426 — `v.path` → `v.rel_path`
* line 428 — `ORDER BY v.path` → `ORDER BY v.rel_path`

Payload keys at 437 (`"container"`) and 439 (`"path"`) are a naming choice, not a bug; I would
rename 437's to `venue` so the key a model sees is the column a reader can query, and leave 439's
`path` (it is a relative path and the value says so). Verified by running all six corrected
statements as `litkb_reader`, with `server.py` untouched:

```
Efron_1986_how-biased-apparent-error: OK  venue='Journal of the American Statistical Association'
                                          ids=1 files=1 uses=0 disc=4
                                          file: Validation/Efron_1986_how-biased-apparent-error-rate.pdf 11 pages
Mei_2010_efficient-scalable-schemes-monitoring: OK  venue='Biometrika'  ids=2 files=0 uses=0 disc=0
```

That second line is the point. With the fix, `litkb_work` answers the skill's step-0 question for
Mei in one call — **admitted, and `files: []`** — which is the diagnosis §4 above needed `psql` to
reach.

**Why no test caught it**, confirmed rather than inferred: `grep -n litkb_work
Scripts/qc/test_litkb_p8.py` returns four lines (118, 136, 138, 315); the only call is
`one("litkb_work", {})` at 136, asserting `no-selector`, and the one at 315 builds a record in
Python and passes it to `_out()` without a connection. No test has ever called `litkb_work` on a
work the database holds. The report says this; it is right.

---

## 6. The promotion — 12/0, and the hash recomputes

`litkb.promotions` for `op-test-1` (`01a0aa5c-382d-7990-ad7b-b7bd5cd5bb0a`):

```
id            01a0aa62-7229-790c-ae84-08f3e0b41d71     state  prepared
branch_head   fd59bc32697b22c14a0296829d43dbccc47655e1
counts        {"held": 0, "chains": 12, "prepared": 12}     conflicts  []
report_path   (empty)        -- the §7.5 caveat, on live data
```

`litkb_reader` may not call `litkb._version_set_hash` or `litkb._ws_chains`, so the hash was
**recomputed from the base tables** by reimplementing `_version_set_hash`'s formula
(`0005_promotion.sql:113–120`) over `litkb.ws_heads`, the five `*_versions` tables and
`litkb.use_evidence`:

```
ws_heads rows: 12   (6 gap, 6 use; every chain 1 version, base NULL, no conflict;
                     every use exactly 1 evidence row)
recomputed  0544c66d89d01b1612a09164c622011bacac169ddd6c945d38e30eaa1b3b8446
stored      0544c66d89d01b1612a09164c622011bacac169ddd6c945d38e30eaa1b3b8446   MATCH
```

So the prepared set still is the workstream's current version set — `promote commit`'s
`40001` guard (`0005_promotion.sql:237`) would pass today. The six use ids and six gap slugs in
`_derived/promotions/01a0aa62-….md` match `ws_heads` one for one, and all six
`use_evidence.quote_verified` are `t` at the offsets §1.1 reproduces. `held: []` is real, not a
gate that never ran: the hold path is exercised by the P8 suite's quote kill, and §3 above shows
the upstream refusals firing live.

The report's friction item 3 also **holds**: `git check-ignore -v --no-index` on the promotion
report returns `.gitignore:2:/*`, so `SKILL.md` step 5's "Commit it with the branch" stages
nothing without `-f`. And item 5 holds: `SKILL.md` §0 still says *"The base holds almost no
blocks yet"* against 102,008.

---

## 7. Defects

| id | what | evidence | fired? |
|---|---|---|---|
| R-1 | `litkb_work` has **two** wrong column names (`container`, `v.path`); "One column name" in the report's verdict is false | §5; `\d litkb.main_works`, `\d litkb.main_files`, per-statement run as reader | yes |
| R-2 | Mei_2010 diagnosed "held, unextracted"; it is **admitted with no bound file** while the PDF sits in `Literture\Validation` | §4 | yes |
| R-3 | 10 admitted works have an unbound PDF on disk; 14 bound PDFs are stranded in open workstreams — neither hole named anywhere | §4 | yes |
| R-4 | F2's extractor-damage diagnosis names the wrong word (`The`→`e`; it is `Here`→`e`) | §1.3, PDF p3 rendered | yes |
| R-5 | F3's `gap row 6` feeds token points at the *correlated-error* row; the quote is the independence case, and §5.1's own [Q] is Efron **2004** | §1.4, framework lines 293, 472 | yes |
| R-6 | Recorded `statement`s carry inferences the quotes do not (F2 "nested models", F3 "why row 6 needs Omega per stratum") — the gate cannot see this | §1.4, §1.6 | yes |
| R-7 | §2's framing as "fresh questions … searched cold" — all three passages were already quoted or cited in the framework/narrative | §1.5 | yes |
| R-8 | Q3's duplicate blocks are **two grobid blocks of the same page in the same run** (reading_order 243/244) plus a third page — not "once per extraction of the same page" | `select … where b.id in (…)` | yes |
| R-9 | Two rank counts overstate precision (F1 "1,2,3,5,6" vs 1,2,3,4,5,6,8; F3 "1–8" vs all ten) | §2 | yes |
| R-10 | Gold's `extract_lines` are stale (Q3 by 15 lines); passages are genuinely present | §2.1 | yes (non-blocking) |
| — | quote gate byte-literal; work guard both branches; nothing written by a refusal | §3 | **not a defect — verified working** |
| — | promotion 12/0 and version-set hash | §6 | **not a defect — verified working** |

R-8's mechanism is worth a line, because friction item 8 treats duplicates as a docling-vs-grobid
artefact: for Efron that is right (`…e845` docling, `…e846` grobid, same run, reading_order 66/67,
both `canonical`), but Rosychuk's pair is `…2f48`/`…2f4a`, **both grobid**, same run, same page,
same 1,818 characters, both `canonical`. So the duplicate canonical block problem is not only
cross-extractor fusion; one extractor's output is being stored twice within a single run. Fixing
only the fusion side would leave half of it.

---

## 8. Verdict on "operational"

**A session can do a literature task through this system today, if it is a task of one
particular shape: finding and citing a passage from a paper that is already extracted.** For
that shape the answer is an unqualified yes, and this pass confirms it independently — six real
questions, six passages at ranks 1–4, six quotes the database verified byte-exactly at recorded
offsets, every forgery route refused, twelve chains prepared with a hash that still recomputes.
Nothing in §1–§6 required reading a PDF to *find* anything; reading them was how I checked.

**It is not yet operational for the question the skill puts first.** `SKILL.md` step 0 says:
"check `litkb_work(doi=…)` before concluding the work is absent." That call is dead for every
work the base holds, so a session cannot distinguish *absent* from *held-but-unextracted* from
*admitted-with-no-file*. The distinction is not academic — §4 found all three states live, and
the report itself got one of them wrong while holding a `psql` prompt. A session without database
access cannot get it right at all; it will either fetch a paper it already has, or conclude a
paper is missing when the work is admitted and the PDF is on disk.

**The smallest set of fixes to make it true without caveats** — four, in cost order:

1. **`server.py:421,426,428`** — `container`→`venue`, `v.path`→`v.rel_path` (×2). Restores step 0.
   Add the test that would have caught it: one `litkb_work` call on a work the database holds,
   asserting `found: true` and a non-empty `files` — the suite has never made one (§5).
2. **`SKILL.md` §0, two sentences.** Replace "The base holds almost no blocks yet" with the live
   count and the rule this test discovered the hard way: **copy the quote out of the
   `litkb_search` result's `text` field, never out of a PDF, a rendered view, or another
   extraction.** Both the gold refusals (§2.1) and probe A (§3) are that rule.
3. **`SKILL.md` step 5** — say `git add -f`, or move the promotion report out of the ignored
   root. Today the instruction silently does nothing (§6).
4. **Surface the two invisible holes** (§4) as a one-command report: works admitted with no bound
   file, and bound files stranded in open workstreams. Ten and fourteen works respectively, several
   of them the framework's own [Q] sources. Until a session can see them, "litkb_search found
   nothing" will keep meaning three different things.

Three further things are *not* on that list and should be said plainly, because each is a real
limit the report treats as settled: the statement a use records is ungated free text and can
over-reach its quote (R-6); a `feeds` token is shape-checked and never resolved against the
document it names (§1.6), so a use can point at the wrong gap row and promote clean; and the
vector leg is off, so every result in both reports came from a query lexically close to its
target. A session that knows the sentence it wants will find it. A session that only knows the
question has not been tested.

---

*Read-only against `litkb`; `op-test-1` left open and unwritten; nothing under
`D:\edmonds-pipeline\Literture\` touched; no downloads. Instruments were throwaway scripts in the
session scratchpad — every number above is reproducible from the commands quoted beside it.*
