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
- `litkb_work(doi=…)` or `litkb_work(key=…)` — one work in full: identifiers, held files, every use
  recorded against it, and any discrepancy between what a legacy record claimed and what the
  registry says.

**The vector leg is off until P7.** Search is lexical: a paraphrase that shares no words with the
text will not be found. Try the author's own wording before concluding the base has nothing.

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

## 2. Admit — the DOI-first rule

`litkb_admit(doi="10.…")`, optionally `file="…"` to bind a PDF already on disk.

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

- `statement` — what this work *supplies* to the question, in your words.
- `kind` — one of `method`, `theorem`, `parameter`, `empirical evidence`, `negative result`,
  `context`, `contradiction`.
- `gap` — the question it answers (a slug); pass `gap_question` to open a new one.
- `quote` — **verbatim** from the block you name. Paraphrase in the statement, never in the quote.
- `feeds` — semicolon-separated tokens from the convention's vocabulary
  (`framework §N`, `gap row N`, `decision <slug>`, `report <FILE>#§<loc>`).

The server finds the quote's offsets in the block and the **database** recomputes whether the text
at those offsets really is your quote. If it is not, the use is stored but **`promote prepare` will
refuse it**. `quote_verified: false` in the result means the citation is not yet real — fix it now,
not at promotion.

**Never cite a work that is not admitted**, and never edit an export to make it say something the
database does not.

---

## 5. Offer it to main

`litkb_propose_promotion()` groups your proposed versions into chains, re-runs the checks, and
writes the promotion report **onto the work branch**, so it reaches Kam inside the merge he reviews.

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
