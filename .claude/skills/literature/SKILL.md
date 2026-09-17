---
name: literature
description: Find, admit, acquire, read and cite any paper the project relies on, through the litkb knowledge base. Use whenever a claim needs a source, a paper is mentioned by DOI or title, the literature tracker or manifest comes up, or you are about to reach for a web search or paper-search tool for a paper. Also for "what does the literature say about X" and "have we used this paper before".
---

# Literature: the hunt protocol

**The rule (decisions.yaml `litkb-p0-foundation` §15.17):** a paper is admitted, acquired and cited
through the knowledge base **whenever it supports a claim in the project**. Ad-hoc reading that
supports no claim is outside this rule — read whatever you like. The moment a paper is going to be
cited, quoted, or written into a report as evidence, it goes through the steps below.

Why the steps are worth the friction: the tracker, the manifest and every "we read X" in a report
used to be hand-written, and three of them disagreed. Now each is printed from one database whose
checks refuse a work whose DOI does not match its title, and refuse a quote it cannot find on the
page. The steps are how a claim becomes checkable by someone who was not there.

The convention this skill points at, and does not copy: `Scripts/docs/LITERATURE_CONVENTION.md`.

---

## 0. Before anything: ask the knowledge base

`litkb_search` first, every time — before a web search, before paper-search, before opening a PDF.

- `litkb_search(query, scope="all")` — hits in extracted text and in recorded uses. Each block hit
  carries `work_key`, `page`, `section_path` and a **`block_id`**; the `block_id` is what step 4
  quotes from, so keep it.
  **Page furniture and bibliographies are OUT by default.** `page_header`, `page_footer`,
  `page_number`, `other` and `reference` are excluded, because a running head is the same 42
  characters on every odd page and used to take eight of the top ten. Pass `kinds="all"` to bring
  them back, or a comma-separated list (`kinds="reference"`) to ask for one; an unknown type name
  is REFUSED, never silently dropped, and the result states which types were left out. Titles,
  authors and affiliations stay IN. The `page` on a hit is the page the text is PRINTED on: a
  paragraph crossing a page break is stored as one block per page.
- `litkb_work(doi=…)` or `litkb_work(key=…)` — one work in full: **which of four states it is in**,
  identifiers, held files (and their stems), every use recorded against it, and any discrepancy
  between what a legacy record claimed and what the registry says.
- `litkb_my_uses()` — the uses **this** workstream has recorded: statement, work, gap, feeds, and
  whether the database verified each quote. `litkb_work` cannot show them and neither can
  `litkb_search` — a use stays `proposed` until Kam merges — so this is the only way to read back
  your own work before offering it. Check it before step 5: a use whose `quote_status` is
  `UNVERIFIED` will be **refused** at promotion, and it is cheaper to fix now.

**"litkb_search found nothing" means three different things, and `litkb_work` is what tells them
apart.** Its `state` is one of:

| state | what it means | what to do |
|---|---|---|
| `absent` | no such work is admitted in main's view | step 2 — admit it |
| `held` | admitted, **no file bound** — the PDF may well be on disk already | step 3 — `litkb_acquire(key=…, from_file=…)` binds a PDF you have; don't re-fetch |
| `bound-unextracted` | a PDF is bound but never extracted, so search cannot see one word of it | **do not fetch it again.** `litkb_hunt(ref=…)` extracts and ingests that file; the P5 bulk path does the corpus |
| `extracted` | N blocks are searchable | quote from a `block_id` `litkb_search` returns |

Two of those four used to be indistinguishable from "not held" — a session either re-fetched a
paper it already had, or called a paper missing while its PDF sat in `Literture\` (measured:
`Reports/LITKB_OPERATIONAL_REFEREE_2026-09-16.md` §4).

**The vector leg is off until P7.** Search is lexical, in three legs fused by reciprocal rank: all
terms, any term, and trigram. A paraphrase that shares no words with the text will still not be
found. What it no longer needs is your guess at the extractor's damage — the text and your query are
both normalised (replacement characters dropped, `overesti- mate` rejoined), and a block that
answers most of your question is returned even if one word is missing from it.

**The base is extracted and searchable.** P5's bulk pass landed ~102k blocks over 225 documents
(2026-09-16), and the operational test found six real passages at ranks 1–4. Do not reach for a web
search because you assume the base is empty. Re-derive the count rather than trusting this line:

```
psql -U litkb_reader -d litkb -At -c "select count(*) from litkb.blocks"
```

**Copy the quote out of the `litkb_search` result's `text` field — never out of a PDF, a rendered
view, or another extraction of the same page.** The database locates your quote by a literal
`find()` in the block's own stored text, so a quote that is right about the *paper* and wrong about
the *block* is refused (`quote-not-in-block`). That is the gate working, not a bug: the offsets it
re-checks have to be offsets into the stored text. It refused the project's own frozen gold
passages for exactly this reason — the gold was grepped from a different extractor, whose text layer
renders the same characters differently.

If the base already holds what you need — quote it and stop. Steps 1–5 are for what it does not.

---

## 1. Open a workstream

`litkb_ws_open(slug, purpose)`.

Every write names a workstream and presents its secret token. The token is written to
`.litkb-workstream` in the worktree root and is **never** a tool parameter, never printed, never
committed. You do not handle it; the server reads it from the file.

`litkb_ws_status()` at any point: what has been admitted, what was attempted, what is proposed.

Nothing you write reaches other sessions until Kam merges the branch. That is deliberate.

---

## 1a. Or do steps 2, 3 and the extraction in one call — `litkb_hunt`

`litkb_hunt(ref="10.…" | "https://…/doc.pdf", title="…", author="…", year=…)` runs resolve → admit →
bind → extract → ingest without an operator between them, and returns the state it reached, the
blocks by kind, the coverage, the first headings, the seconds per stage and every refusal with its
reason. It answers from the database FIRST: a reference already extracted comes back with its run
having fetched, converted and written nothing, so calling it twice is safe and costs a round trip.

Where it stops, and why that is not a failure:

- **a DOI** is admitted and then stops at `held`, because choosing an acquisition route is a SPEND.
  The next move is in `refusals`: `litkb_acquire(key=…)`, or `from_file=…` for a PDF you have. Hunt
  the DOI again afterwards and it picks up at the bound file.
- **a URL** is a web source with no registry to ask, so **pass `title` and `author`** — a PDF's own
  `/Title` usually names the file, not the work. It is admitted as a manual PROPOSAL with the URL,
  the retrieval date and the document's own first-page text, and its blocks are real and ingested
  but **invisible to `litkb_search` until a SECOND session approves the admission**. The result says
  so every time; quote it through the `block_id`, which `litkb_record_use` accepts.

Steps 2-4 below are still the way to drive each stage on its own, and what step 4 does is not part
of a hunt: a hunt gets the text in, and recording what the work SUPPLIES is yours.

---

## 2. Admit — the DOI-first rule

`litkb_admit(doi="10.…", title="…", authors="…", year="…")`, optionally `file="…"` to bind a PDF
already on disk.

**Give the title, authors and year — a bare DOI is refused.** Admission COMPARES what you claim with
what the registry says, so a call carrying neither a claimed record nor a bound file is refused at
`check1_study_exists`: a DOI on its own proves only that *some* work exists, not that it is the one
you mean. (Measured, P8 referee §2.2.)

**Identity is the registry record plus the verified file, never the claim.** A DOI is checked
against Crossref; the title, first author and year must agree; the bound PDF must carry the title on
its first page. Two real corrections came out of that check — a DOI in the old manifest pointed at a
completely different paper, and had done for months.

- No DOI and no arXiv id? That is a **manual admission**: a *proposal*, not a fact, and a **second
  session** signs it off. Run `py -3.12 -m litkb admit --manual --title … --authors … --year … --file … --source-note "…"`
  at the CLI, then ask for a different session to approve it. There is no MCP tool for either step,
  because the sign-off must not come from the session that made the claim.
- Refused at binding? The refusal names which check failed. A refusal is usually right — the usual
  cause is a wrong DOI, not a wrong checker.

---

## 3. Acquire

`litkb_acquire(key=…)` — open access first, then the archive, then Sci-Hub, a browser last.
`from_file=…` binds a PDF you already have.

**Never fetch a PDF outside a workstream.** Every attempt is logged whether it succeeds or not, so a
paper that could not be got is a recorded gap rather than a thing everyone re-tries quarterly.

**When a route is blocked** — paywall, challenge page, quota, nothing open access:

1. Do not fall back to a web search or a paper-search download. That is exactly the leak the rule
   exists to close, and it leaves no record.
2. The attempt is already logged; `litkb_ws_status()` shows it. Say plainly in your report that the
   work is admitted but **not obtained**, and cite it as `METADATA` grade, never as if read.
3. If the claim genuinely needs the full text, ask Kam. Sci-Hub is his call
   (memory `scihub-fetch-method`), and so is anything that spends the archive's quota.
4. An abstract is evidence about the abstract. Do not quote a paper you have not read.

---

## 4. Record the use — with a quote the database verifies

`litkb_record_use(statement, kind, quote, block_id, gap, gap_question=…, feeds=…)`.

- `statement` — what this work *supplies* to the question, in your words. It may not be blank and is
  length-capped (the refusal names the limit). **It is not gated for truth**, so keep it to what the
  quote beside it actually carries: a statement that reaches past its quote promotes clean and is
  wrong in main.
- `kind` — one of `method`, `theorem`, `parameter`, `empirical evidence`, `negative result`,
  `context`, `contradiction`.
- `gap` — the question it answers (a slug); pass `gap_question` to open a new one.
- `quote` — **verbatim** from the block you name. Paraphrase in the statement, never in the quote.
- `feeds` — semicolon-separated tokens from the convention's vocabulary, **all seven doc-qualified
  forms** (`Scripts/docs/LITERATURE_CONVENTION.md`), each naming a document *and* a place in it:

  | token | means |
  |---|---|
  | `framework §N[.N]` | a heading in `Reports/FRAMEWORK_GAPS_SPATIOTEMPORAL_CONSISTENCY_2026-09-11.md` (at most one sub-level) |
  | `narrative §N` | a heading in `Reports/MATH_NARRATIVE_SPATIOTEMPORAL_CONSISTENCY_2026-09-12.md` (integer only) |
  | `gated-plan gate N` | a `## Gate N` heading in `Reports/GATED_PLAN_SPATIOTEMPORAL_CONSISTENCY_2026-09-12.md` |
  | `review §N[.N…]` | a heading in `Reports/LIT_REVIEW_SPATIOTEMPORAL_CONSISTENCY_2026-09-10.md` (any depth) |
  | `gap row N` | a row of the framework's §11 gap ledger |
  | `decision <slug>` | a key in `Scripts/decisions.yaml` |
  | `report <FILE>#§<loc>` | any other tracked report; `loc` alphanumeric (a heading key, or `L<line>`) |

  All seven are enforced by the database — **at `litkb_record_use`, immediately**, and again at
  `promote prepare` (migrations 0018/0021). A token outside the vocabulary is refused `bad-feeds`
  and names itself; nothing is written, not even the gap. It used to be stored unvalidated and first
  checked a whole session later at prepare.

  What the check does **not** do is open the document: it validates the token's SHAPE, never that
  the section, gate, row or decision it names exists or is the right one. `gap row 6` on a result
  that belongs to row 5 passes silently, and the operational referee found exactly that
  (`LITKB_OPERATIONAL_REFEREE_2026-09-16.md` §1.4). Read the row before you cite it.

The server finds the quote's offsets in the block and the **database** recomputes whether the text
at those offsets really is your quote. If it is not, the use is stored but **`promote prepare` will
refuse it**. `quote_verified: false` in the result means the citation is not yet real — fix it now,
not at promotion.

**A use with no quote at all is held too** (`no-verified-evidence`, migration 0019). Until that
migration lands in `litkb` it is not: a use with zero evidence rows prepared clean, which is how the
convention's sentence came to be false (P8 referee §3.6, §4.1). Record the quote with the use.

**Never cite a work that is not admitted**, and never edit an export to make it say something the
database does not.

---

## 5. Offer it to main

Read back what you are about to offer first: `litkb_my_uses()`. Anything whose `quote_status` is not
`verified` will be **held**, and fixing it now costs one call.

`litkb_propose_promotion()` groups your proposed versions into chains, re-runs the checks, and
writes the promotion report to **`_derived/promotions/<promotion_id>.md` in the worktree** (or to
`report_path=` if you name one). **Commit it with the branch** — that is how it reaches Kam inside
the merge he reviews; prepare writes the file, it does not stage or commit it. Plain
`git add _derived/promotions/<id>.md` works: that path is whitelisted in `.gitignore`. Until
2026-09-16 it was not, and this instruction staged nothing and said nothing.

The result names every chain it prepared and every chain it **held**, with the database's reason.
A held chain is not an error; it is work that may not enter main yet. Fix the reason and prepare
again.

`promote commit` is not a tool and is not yours: it runs after Kam has merged, from a session that
can see the merge commit. **`main` is Kam's** (CLAUDE.md §3.1).

---

## The exports are printed, never edited

`Reports/literature_tracker.csv`, `Literature_Tracker.xlsx` and every `manifest.csv` are generated:
`py -3.12 -m litkb export tracker` / `export manifest` / `export all --diff`. Hand-editing one makes
it disagree with the database, which is the state this whole system was built to end.

## Handing off to the librarian

For "what does the literature say about X", use the **librarian** subagent: it answers from the
knowledge base only, returns work key, page, quote and whether a use already exists, and records
candidates in your open workstream. It cannot promote and holds no privileged credential.
