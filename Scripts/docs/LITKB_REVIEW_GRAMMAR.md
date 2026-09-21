# litkb review grammar — the one home for what a written review must look like

A review is the last stage of the literature pipeline: a brief goes in
(`py -3.12 -m litkb brief`), a cited `.md` comes out under `Reports/reviews/`. This file is the
**only** authoritative statement of its form. The writer agent
(`.claude/agents/review-writer.md`) points here rather than restating it, and the grader
(`Scripts/pipeline/litkb/review_check.py`, `litkb review-check`) implements it. A rule written
in two places is a bug — fix this file, not the copy (CLAUDE.md §3.3).

The grammar exists to make `decisions.yaml::litkb-operational-definition` machine-checkable:

> **K1** any claim in the review that does not trace to a verified quote (work key + page +
> block_id) = FAIL.
> **K2** at least one dropped-off expectation must return CONTRADICTED or UNCONFIRMED **and the
> review must say so** — the honesty machinery is required to FIRE, not merely to be present.

---

## 1. The document

```markdown
<!-- litkb-review workstream=<workstream id or slug> -->

# <title>

## Scope
…the topic question; the template sentence below, verbatim or not at all; and this review's
limits written as what it did NOT read — which works, which years, which languages, which
operation it makes no claim about. NEVER a characterisation of the review's own process or of
its sources. No citations, no quotes.

## <any claim section>       ← its title is a LABEL: six words or fewer
…every SENTENCE carries at least one citation.

## Expectations not supported
…REQUIRED. One entry per expectation that did not come back confirmed.

## Sources
…REQUIRED. A markdown table, one row per work cited.
```

There are exactly **four non-claim sections**, and the list is closed: the **preamble** (anything
before the first `##`), **`Scope`**, **`Expectations not supported`** and **`Sources`**. Every
other `##` heading is a claim section, whatever it is called — and **its title must be a label of
six words or fewer**, because a title can carry no citation (§4).

**`Scope` may say exactly one thing about the review's own sourcing, and these are its words.
Copy the line inside this code block, exactly, or write nothing of the kind:**

```text
Every citation in this review names a VERIFIED line of the brief for this workstream; nothing outside that brief is cited.
```

It is shown in a code block and not as a block quote, a bullet or bold text because **what you can
see is what the grader compares.** The rendered copy was a wrapped block quote until 2026-09-20,
and an auditor measured that copying it as displayed — `> ` and all — was refused, while the test
binding the two copies stripped the `>` that the grader does not. The block above is byte-for-byte
the constant `review_check.SCOPE_TEMPLATE`, and a test compares them with no stripping at all, so
this line and `.claude/agents/review-writer.md`'s copy of it cannot drift from the code.

**Any other `Scope` sentence containing `abstract`, `memory` or `knowledge base` fails as
`scope-self-claim`.** The reason is that `Scope` is the one section the grader cannot look inside,
and the proving run of 2026-09-20 walked into that hole from a direction nobody had guarded: it
wrote *"nothing was read from an abstract, from memory, or from outside the knowledge base"* while
two of its thirteen citations quoted an ingested block that its adversarial reader records as
beginning `Abstract—` (`jobs/litkb-operational/codex-review-proving-run2.md` §2). All thirteen
citations were supported; the false statement was about the review's own process, which no grader
can verify. So there is one permitted sentence, and it is one the grader itself enforces
(`not-in-brief`, `quote-not-verified-span`).

The three terms are the ones that name a **source**. `outside` and `measured` were in this list
for one day and were removed: they refused *"Sites outside the Pacific Northwest are not
represented"* and *"No measured canopy value for Edmonds is in the knowledge base"* — the first is
not about sourcing at all and both are LIMITS, which is what this section is for. The skeleton
above was rewritten in the same change, because *"what it read, what it did not"* was inviting the
sentences the guard then refused. Write a limit as **what was not read** — "This review reads no
work published after 2019", "no German-language work was hunted", "it makes no assessment of
canopy accuracy for any year of the Edmonds archive" — and not as a statement about what the
knowledge base contains. §7 has what this leaves open in both directions.

**Each of those names may open ONCE.** A second `## Scope` (or `## Sources`) anywhere in the
document fails as `duplicate-section`. They are the sections K1 cannot look inside, so a second
one re-opens that blind spot *below* the findings — a writer never had to move anything upward,
it could open a fresh `## Scope` under its own results and keep asserting. Two claim sections may
share a name: both are graded, so nothing hides in the second.

The **first non-blank line** is the header comment. It is the only place the workstream is
named: `litkb review-check` takes the workstream from the document, because a review graded
against a workstream it was not written from would satisfy K2 by holding no expectations at all.
The CLI's `--workstream <id|slug|current>` does not override that — it *asserts* which workstream
the caller believes it is grading, and the grader refuses the run by name when the header
declares another.

Headings are matched case-insensitively at `##`. A deeper heading (`###`) does not open a new
section — it stays inside the section above it, so demoting a heading cannot move a claim
paragraph out of K1.

## 2. The citation token

```
[work_key p.N #block_id]
```

* `work_key` — the key exactly as the brief prints it (`Test_2020_abcd1234-paper`).
* `p.N` — the page the brief's VERIFIED line gives, a plain integer.
* `#block_id` — the block uuid the brief's VERIFIED line gives.

Every citation must be **immediately preceded by the verbatim quote it rests on**, in double
quotes, with nothing but spaces or tabs between the closing quote and the `[`:

```markdown
Douglas-fir crowns keep their shape through leaf-off: "the optimism identity holds under an
arbitrary joint model" [Test_2020_abcd1234-paper p.1 #0199a7d2-…-4c1b].
```

Straight (`"…"`) and curly (`“…”`) delimiters are both accepted. A quote may not itself contain
a delimiter. The citation must follow the closing delimiter on that delimiter's own line.

**The quote must be a BYTE-EXACT substring of the stored block, in everything but the encoding of
a line break.** Whitespace is not normalised, quotation marks are not normalised, words are not
normalised. The grader asks Postgres whether the quoted span is a substring of the block's own
text, and since migration 0026 that is *exactly* the question the verify trigger asks of a
recorded use — both sides canonicalised by the same `litkb.canonical_newlines`, so a quote that
can be RECORDED can be CITED and the reverse. The review file is read with newline translation
**off** so that what you typed is what is compared.

The one canonicalisation, applied to **both sides** (`textnorm.canonical_newlines`):

* Every line **ending** becomes a single `\n` — `\r\n` → `\n`, a lone `\r` → `\n`. Nothing else
  changes, and the *number* of breaks is preserved: `\n\n` stays two, so a quote can never
  silently join two paragraphs of the block.

So, for a writer:

* **A quote MAY span lines.** Write the line breaks in your file however your editor writes them
  — LF is fine, and you never need to emit a raw CR. About half of every stored block carries
  `\r\n` (48.9 % of current-run blocks on 2026-09-19) and 7 of the project's 8 verified spans
  cross one, so the older rule — *quote within one stored line* — truncated almost every quote
  the project had verified, once to 33 characters that asserted nothing.
* **Break the quote where the block breaks it, and nowhere else.** Re-wrapping, joining lines
  with a space, dropping a blank line, or adding one still produce `quote-not-verbatim`: the
  reader may not rewrite the paper.
* **Continuation lines start at column 0.** Leading whitespace is content — indenting the second
  line of a quote to line it up inside a list item changes the bytes and fails. If you need the
  quote inside a bullet, keep the whole quote on that bullet's first line or shorten it.
* **A quote must be at least 25 characters** (after that canonicalisation) or it fails as
  `quote-too-short`. A one-word — or one-space — fragment is inside nearly every verified span
  and is evidence of nothing; the shortest verified span the project holds is 83 characters, so
  this floor is nowhere near anything you would legitimately want to quote.

## 3. What a citation may name

Only a **VERIFIED line of this workstream's brief** — the (work key, page, block id) triple, as
printed. A block that exists in the database but that no promotable `use_evidence` row anchors
is not what K1 means by a verified quote, and citing one fails as `not-in-brief`.

**And the words you quote must be inside the span that line verified.** The brief prints each
VERIFIED line's quote verbatim; that text is the `[char_start, char_end)` the database re-read
and marked `quote_verified` — the same characters and the same breaks in the same places,
possibly written with a different line-break encoding (the brief canonicalises what it prints).
Your quote must be that text or a **substring** of it.
Being inside the block is not enough, and the difference is not pedantic: a block is a whole
paragraph, so a block verified for its first sentence would otherwise let you quote its fourth —
which nobody checked — under a claim about the fourth. Quoting outside every verified span fails
as `quote-not-verified-span`.

In practice: **copy the quote out of the brief and shorten it if you must.** Never extend it,
and never go back to the block for more words. If you need a different span of the same block,
that is a new `use` with its own verified quote, recorded through `litkb use add` — not a
citation you can write.

The `abstract_passage` of an EXPECTED line is **never quotable**. It is an agent's unverified
prior, the brief labels it so, and a review that quotes one is asserting from an
`abstract_passage` — a claim nothing in the database ever checked against an ingested byte.

**That is the ONLY barred abstract text, and the distinction matters.** A block of an ingested
PDF is evidence wherever in the paper it sits: a paragraph beginning `Abstract—` is as citable as
one on page 9, provided a VERIFIED line of the brief anchors it. What is barred is the
`abstract_passage` FIELD of a hunt_request, because nobody verified it. The proving run got this
backwards in its `Scope` and told its reader the opposite of what it had done (§1).

## 4. Claim sections and K1

Every section that is not `Scope`, `Expectations not supported` or `Sources` is a **claim
section**. The unit K1 is enforced per is the **SENTENCE**, not the paragraph.

It was the paragraph until 2026-09-20, and the stage-8 audit measured what that cost: three
uncited assertions followed by one cited one passed as a single unit. So:

* **Every sentence of every unit carries at least one citation.** A unit is a paragraph
  (consecutive non-blank lines), **each list item separately** (one citation cannot cover a
  bulleted list of five claims), or a **table row**; a block quote (`>`) belongs to the unit
  above it, and an HTML comment and a heading are not prose.
* **Table rows are units.** A findings table is the most natural way to present per-year results
  and it used to be outside K1 entirely. Every data row needs its own citation. Exempt: the
  delimiter row (`|---|---|`) and the header row directly above it, which assert nothing.
* **A `###`-or-deeper heading in a claim section is a unit too**, unless it is short enough to be
  a label: **6 words or fewer** is exempt, 7 or more must carry a citation or it fails as
  `uncited-heading`. A heading is the most natural place for a model to put a summary assertion
  ("### Canopy fell by 11 percent between 2000 and 2020") and it used to be dropped before any
  unit was formed — the same class of hole as the fence. `### Method` and `#### 2005 to 2012` are
  labels and are fine. A line beginning `#` with no space after it is not a heading to a markdown
  renderer either, and is graded the same way.
* **A claim section's own `##` TITLE is held to the same six words, and has no citation escape.**
  More than six words fails as `uncited-heading`, full stop: a `##` line opens a section, so the
  grader never hands its text to K1, and a citation written into a title would be half-graded —
  checked for being verbatim and in the brief, never checked against the sentence it is supposed
  to support. A title therefore cannot carry evidence and must be a LABEL. The proving run of
  2026-09-20 is why: `## Canopy reference products and imagery that spans dates` granted a
  "reference product" status that the section's own body, and its own ledger entry, both say was
  never confirmed — over thirteen citations that were each individually supported. Non-claim
  titles are not graded; their four names are fixed above.
* **A fenced code block in a claim section is a FAIL** (`fenced-in-claims`). Fenced text carries
  no citation and the grader cannot see inside it, so it is refused rather than ignored. Put a
  code block in `Scope`, or write the claim as a cited sentence. A `## ` heading at the start of
  a line **ends any open fence**, so an unclosed fence cannot swallow the sections after it (that
  was the way round this guard the guard itself could not see). The cost is that a `## ` line
  inside a genuine code block splits it — which fails loudly rather than hiding anything.

**The sentence splitter is deliberately simple:** `.`, `?` or `!` followed by whitespace. It does
not know abbreviations, and it does not need to, because it errs toward FAIL — a split that
should not have happened leaves a fragment with no citation, which you will see. The one that
will actually bite a literature review is **`et al.`**: `Smith et al. found X "…" [cite].` splits
into `Smith et al.` (uncited, FAIL) and the rest. Write `Smith and colleagues`, or keep the
citation in that fragment. The splitter **does not** cut inside a citation's own quote, so a
faithfully copied two-sentence quote is safe.

The preamble and `Scope` are places K1 cannot police, so they may contain **no** citation and
**no** quoted span; `Expectations not supported` and `Sources` may contain no citation token
either. A citation in a non-claim section fails as `claim-outside-claim-section`. Put the
question, the method and the limits in `Scope`, in your own words. (What a citation in a
non-claim section catches, and what it cannot, is §7.)

## 5. Expectations not supported, and K2

This section is required **unconditionally**, even when it holds nothing — "every expectation
was confirmed" is a claim about the run and must be stated, not left to silence.

For every EXPECTED line of the brief whose `resolution_state` is:

| state | what the review must do | grader |
|---|---|---|
| `contradicted` | name it (hunt_request id or ref), give its `expected_claim`, and say what the verified quote actually said | **fail** if absent |
| `unconfirmed` | name it, and say that nothing ingested has confirmed or refuted it | **fail** if absent |
| `open` | name it, and say it was never linked to a work | notice if absent |
| `confirmed` | nothing (its quote carries the claim in the body) | — |

"Name it" means the hunt_request's **id or its ref appears literally** in the section. A
paraphrase the grader cannot match is, to the grader, an omission.

This section is non-claim, so it carries **no citation token**. To show what the verified quote
actually said, write that as a cited sentence in a claim section and refer to it here by the
hunt_request id; the entry here is about the expectation, not about the evidence.

**An entry must name the PARTIAL support its own cited blocks contain.** A `contradicted` or
`unconfirmed` expectation is rarely a clean loss, and an entry that reports only the losses is
honest about the verdict and misleading about the evidence. If a block you cite for the refutation
also holds a result that goes the expectation's way, that result is part of what the block says:
write it as its own cited sentence in a claim section, and name it here alongside the refutation.
The proving run's Kaiser entry is the case — it gave two losses (a small-training-set deficit and
a 10-percent-point deficit at matched label quantity) from a block that, in the same paragraph,
records the OSM-trained model beating the smaller manual baseline by 1.5 percent points. Nothing
it wrote was false; a reader was pointed at half of what the block supports.
**This rule is not machine-checkable** — §7 says so, and only a reader can enforce it.

**K2 also has a first half, and it is now checked.** The workstream must HOLD at least one
expectation the database resolved `contradicted` or `unconfirmed`. A workstream in which every
drop-off came back confirmed fails as `k2-never-fired` — not because the review is badly
written, but because a run that never contradicted anything has not exercised the machinery this
section exists to report. That check is on by default and cannot be turned off; it was a
human-run `hunt-request list --state contradicted` count until 2026-09-20, and a step whose
skipping is invisible is not a gate.

## 6. Sources

A markdown table, one row per work cited, with the key in backticks so the grader can read it:

```markdown
| work | key | pages cited |
|---|---|---|
| Author (2020), Title | `Test_2020_abcd1234-paper` | 1, 4 |
```

A key cited in the body and missing from the table **fails** (`source-not-listed`). A key listed
and never cited is a **notice** (`source-never-cited`) — a bibliography of things the review did
not use.

## 7. What the grader does NOT check

Stated here so a PASS is never read as more than it is:

* **Whether the claim a sentence makes is the claim its quote supports.** The grader proves a
  verbatim quote from a verified block sits under every assertion. It cannot prove the sentence
  says what the quote says. Paraphrase fidelity is a reader's judgement, and it is the single
  largest thing a green `review-check` does not buy you.
* **A literature fact asserted in a NON-CLAIM section.** This is the one hole the grammar creates
  on purpose, and it must be said in as many words: `Scope`, `Expectations not supported` and
  `Sources` exist for the writer's own words, so an **uncited sentence asserting something about
  the literature, placed there, is a grammar violation the grader cannot see.** It is a violation
  — the rule is that claims live in claim sections — and nothing machine-checks it. What the
  grader does catch is the cheap version: a claim that was *moved* there brings its citation or
  its quote with it, and a citation token in a non-claim section fails. A writer who strips the
  citation to hide a claim in `Scope` has broken this grammar and produced an unsourced claim,
  and only a reader can catch it.
* **A false claim about the review's own PROCESS, beyond the three terms `scope-self-claim`
  watches — and, in the other direction, honest sentences those three terms refuse.** §1 fixes one
  permitted sourcing sentence and refuses any other `Scope` sentence carrying `abstract`, `memory`
  or `knowledge base`. Both sides of that are real and neither is a bug to be fixed by tuning:
  * **What escapes.** The terms are matched on letter/digit boundaries and are not stemmed, so
    `abstracts` passes where `abstract_passage` is caught, and any sentence avoiding all three
    makes whatever process claim it likes — *"this review read only what the hunt returned"* is
    unverifiable and passes. The rule closes the sentence the proving run actually wrote and the
    shapes nearest it; it does not make self-description safe.
  * **What it refuses although it is honest.** A limit phrased as a statement about the knowledge
    base's contents — *"no such measurement is in the knowledge base"* — fails, even though it is
    true and is exactly the kind of limit `Scope` exists for. That is deliberate: the grader
    cannot tell a true statement about the corpus from a false one, so the grammar asks for the
    limit in the form it CAN leave alone (what this review did not read). Rephrase, do not argue
    with the finding. The previous list also refused *"Sites outside the Pacific Northwest are
    not represented"*, which is not about sourcing at all; that was a defect and `outside` and
    `measured` were dropped for it. One residue of the same kind survives in `memory`, which has
    a non-sourcing sense — *"held in the memory of the device"* would be refused — and it is kept
    because a literature review's `Scope` has no other use for the word.
* **Whether a disclosure is COMPLETE.** The grader proves every contradicted or unconfirmed
  expectation is NAMED (§5). It cannot ask whether the entry tells the whole of what its cited
  blocks hold — the partial-support rule in §5 is a reader's to enforce, and the proving run
  passed this grader while pointing its reader at two losses and omitting a 1.5-percent-point win
  from the very block it cited.
* **That the writer stayed inside its OWN workstream's hunt.** `not-in-brief` confines a citation
  to a **VERIFIED line of the brief**, and a brief's VERIFIED lines are every promotable use this
  workstream can see — which, by `brief._VERIFIED_SQL`'s `wu.state = 'promoted'` clause, includes
  **every promoted use in the database**, hunted by anyone, at any time. That is by design:
  promoted is the project's shared record, and a review may legitimately cite it. But it means a
  green grade does **not** say the review used what this run went and found. A fresh workstream
  that hunted nothing at all still inherits every promoted quote as citable (measured
  2026-09-20: 20 of them, from another test module's promotions). If you need "this run's own
  evidence", read the workstream's own `uses`, not the grader's verdict. K2 is the half that does
  constrain this run — it counts *this* workstream's ledger.
* **Whether the review is balanced, complete, or read the right literature.** Coverage is a
  question for the brief and the hunt, not for this file.
* **Whether a `confirmed` expectation was confirmed for the right reason.** The database derives
  `resolution_state` from stance-bearing verified quotes; the grader takes that verdict as given.
* **Prose quality, ordering, or the reasoning between citations.**

## 8. Running it

```bash
cd <worktree>/Scripts
PYTHONPATH=pipeline PYTHONUTF8=1 py -3.12 -m litkb review-check ../Reports/reviews/<slug>.md
PYTHONPATH=pipeline PYTHONUTF8=1 py -3.12 -m litkb review-check <path> --workstream current
```

**It only reaches the LIVE database.** `commands._default_connect` connects as `litkb_writer`,
and the passfile holds `litkb_writer` for database `litkb` only, so `litkb review-check --db
litkb_test_wN` fails with *no password supplied* (measured 2026-09-20). That is a fact about the
credentials, not about this command, and it is left alone deliberately: the fix is a pgpass entry
(and the GRANTs behind it), which is Kam's, not code. Until then a worker-database run goes
through `review_check.check(conn, path)` with its own connection — which is what every test here
does — and the unattended loop inherits the same limit.

**The writer does not run this; the orchestrator does.** `review-writer` holds no `Bash` tool,
deliberately: the proposer never scores its own proposal (CLAUDE.md §3.4c). The agent hands back
a path and says the review is ready for `review-check`; whoever dispatched it runs the grader.

One JSON object per finding (`line`, `code`, `detail`, `severity`), then a summary line. Exit 1
when any finding has `severity: fail`. The finding codes are `malformed-citation`,
`block-not-found`, `work-mismatch`, `page-mismatch`, `citation-without-quote`,
`quote-not-verbatim`, `quote-not-verified-span`, `quote-too-short`, `not-in-brief`,
`uncited-claim`, `uncited-heading`, `scope-self-claim`, `fenced-in-claims`, `duplicate-section`,
`claim-outside-claim-section`, `missing-expectations-section`, `expectation-not-disclosed`,
`k2-never-fired`, `missing-sources-section`, `source-not-listed`, `source-never-cited`.

**A green grade is not the end of the review stage.** §7 is the list of what this grader cannot
see, and the ADVERSARIAL READ is what answers the first item on it — whether the claim a sentence
makes is the claim its quote supports. Its input is `py -3.12 -m litkb review-context <review.md>
--out <ctx.md>`, which writes the whole block behind every citation; its runner is
`qc/instruments/litkb_codex_review.py`; its gate is `qc/instruments/litkb_acceptance.py codex`.
This grammar is the deterministic half and that stage is the read, and neither substitutes for the
other — the proving run of 2026-09-20 passed this grader with 0/13 overreaching citations and was
still refused by its reader, for two claims made where K1 does not look.

`uncited-heading` is raised by two guards, on the two kinds of heading: `###` and deeper
(`_deep_heading_findings`, RC13) and a claim section's own `##` title (`_title_findings`, RC26).
They are separate rows because they are separate holes — removing either leaves the other closed.

Each of those is produced by a guard with a mutation row in
`qc/instruments/litkb_p2_mutations.py` (RC1–RC16 and RC25–RC27; RC17–RC24 are the RECORDING end of
the same newline rule, in `use.py` and migration 0026) and a test in
`qc/test_litkb_review_check.py`: a gate that has never been shown to fire is not known to work
(CLAUDE.md §3.4c).

---

*Added 2026-09-20 with stage 8 (brief → written review). Authored here, in the repository,
because it is a rule and not a measurement (CLAUDE.md §2.3).*
